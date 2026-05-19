
"""Tests for CadenceTracker."""
from __future__ import annotations

import math

import pytest

from substrate.cadence.cadence_tracker import (
    DEFAULT_CADENCE_CONFIG,
    CadenceConfig,
    CadenceEvent,
    CadenceEventKind,
    CadenceTracker,
    CouplingStatus,
)


def _events(timestamps: list[float], a: str = "alice", b: str = "bob") -> tuple[CadenceEvent, ...]:
    return tuple(
        CadenceEvent(timestamp=t, pair_id_a=a, pair_id_b=b)
        for t in timestamps
    )


class TestCadenceEventValidation:
    def test_round_trip(self) -> None:
        e = CadenceEvent(timestamp=1.0, pair_id_a="a", pair_id_b="b")
        assert e.kind is CadenceEventKind.INTERACTION

    def test_negative_timestamp_rejected(self) -> None:
        with pytest.raises(ValueError, match="timestamp"):
            CadenceEvent(timestamp=-1.0, pair_id_a="a", pair_id_b="b")

    def test_empty_pair_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="pair_id_a"):
            CadenceEvent(timestamp=0.0, pair_id_a="", pair_id_b="b")
        with pytest.raises(ValueError, match="pair_id_b"):
            CadenceEvent(timestamp=0.0, pair_id_a="a", pair_id_b="")

    def test_same_pair_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="pair_id_a and pair_id_b"):
            CadenceEvent(timestamp=0.0, pair_id_a="a", pair_id_b="a")

    def test_canonical_pair(self) -> None:
        e = CadenceEvent(timestamp=0.0, pair_id_a="bob", pair_id_b="alice")
        assert e.canonical_pair == ("alice", "bob")


class TestCadenceConfig:
    def test_defaults(self) -> None:
        cfg = CadenceConfig()
        assert cfg.weakening_threshold > cfg.decoupling_threshold

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("weakening_threshold", 1.5, "weakening_threshold"),
            ("decoupling_threshold", 0.6, "decoupling_threshold"),
            ("ghosting_skip_multiples", 1.0, "ghosting_skip_multiples"),
            ("min_history_for_pattern", 1, "min_history_for_pattern"),
            ("field_strength_clamp", 0.0, "field_strength_clamp"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            CadenceConfig(**{field: value})  # pyright: ignore[reportArgumentType]


class TestComputePattern:
    def setup_method(self) -> None:
        self.t = CadenceTracker()

    def test_empty_events_none(self) -> None:
        assert self.t.compute_pattern(()) is None

    def test_single_event_none(self) -> None:
        assert self.t.compute_pattern(_events([1.0])) is None

    def test_too_few_events_none(self) -> None:
        assert self.t.compute_pattern(_events([1.0, 2.0])) is None

    def test_three_events_yields_pattern(self) -> None:
        pattern = self.t.compute_pattern(_events([1.0, 2.0, 3.0]))
        assert pattern is not None
        assert pattern.mean_interval == 1.0
        assert pattern.sample_size == 2

    def test_variance(self) -> None:
        pattern = self.t.compute_pattern(_events([0.0, 1.0, 4.0]))
        assert pattern is not None
        assert pattern.mean_interval == 2.0
        assert pattern.stdev_interval > 0


class TestComputeFieldStrength:
    def setup_method(self) -> None:
        self.t = CadenceTracker()

    def test_no_events(self) -> None:
        out = self.t.compute_field_strength(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=10.0,
            events=(),
        )
        assert out.coupling_status is CouplingStatus.INSUFFICIENT_DATA
        assert math.isinf(out.time_since_last_coupling)

    def test_explicit_close(self) -> None:
        events = _events([1.0, 2.0]) + (
            CadenceEvent(
                timestamp=3.0,
                pair_id_a="alice",
                pair_id_b="bob",
                kind=CadenceEventKind.EXPLICIT_CLOSE,
            ),
        )
        out = self.t.compute_field_strength(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=20.0,
            events=events,
        )
        assert out.coupling_status is CouplingStatus.EXPLICITLY_CLOSED

    def test_at_expected_cadence_active(self) -> None:
        events = _events([1.0, 2.0, 3.0])
        out = self.t.compute_field_strength(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=4.0,
            events=events,
        )
        assert out.field_strength == 1.0
        assert out.coupling_status is CouplingStatus.ACTIVE

    def test_inverse_square_decay(self) -> None:
        # expected cadence = 1.0; elapsed = 2.0 → field = (1/2)² = 0.25
        events = _events([1.0, 2.0, 3.0])
        out = self.t.compute_field_strength(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=5.0,
            events=events,
        )
        assert abs(out.field_strength - 0.25) < 1e-9
        assert out.coupling_status is CouplingStatus.WEAKENING

    def test_decoupled_status(self) -> None:
        # field strength < decoupling threshold (0.1) but skip < 3x
        events = _events([1.0, 2.0, 3.0])  # cadence=1.0
        out = self.t.compute_field_strength(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=5.9,  # elapsed=2.9, field=(1/2.9)²≈0.119
            events=events,
        )
        assert out.coupling_status is CouplingStatus.WEAKENING
        out = self.t.compute_field_strength(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=6.0,  # elapsed=3.0, field≈0.111 - but skip=3.0 == threshold
            events=events,
        )
        # skip == 3.0 multiples → GHOSTED
        assert out.coupling_status is CouplingStatus.GHOSTED

    def test_ghosted_status(self) -> None:
        events = _events([1.0, 2.0, 3.0])
        out = self.t.compute_field_strength(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=10.0,  # elapsed=7.0, skip=7x
            events=events,
        )
        assert out.coupling_status is CouplingStatus.GHOSTED

    def test_pair_order_canonical(self) -> None:
        events = _events([1.0, 2.0, 3.0], a="alice", b="bob")
        out_ab = self.t.compute_field_strength(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=4.0,
            events=events,
        )
        out_ba = self.t.compute_field_strength(
            pair_id_a="bob",
            pair_id_b="alice",
            current_time=4.0,
            events=events,
        )
        assert out_ab.field_strength == out_ba.field_strength

    def test_same_pair_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="pair_id_a"):
            self.t.compute_field_strength(
                pair_id_a="alice",
                pair_id_b="alice",
                current_time=0.0,
                events=(),
            )

    def test_negative_time_rejected(self) -> None:
        with pytest.raises(ValueError, match="current_time"):
            self.t.compute_field_strength(
                pair_id_a="alice",
                pair_id_b="bob",
                current_time=-1.0,
                events=(),
            )


class TestDetectGhosting:
    def setup_method(self) -> None:
        self.t = CadenceTracker()

    def test_no_ghosting_active(self) -> None:
        events = _events([1.0, 2.0, 3.0])
        ev = self.t.detect_ghosting(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=4.0,
            events=events,
        )
        assert ev is None

    def test_ghosting_returned(self) -> None:
        events = _events([1.0, 2.0, 3.0])
        ev = self.t.detect_ghosting(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=15.0,
            events=events,
        )
        assert ev is not None
        assert ev.skipped_cadence_multiples > 3.0

    def test_explicit_close_blocks_ghosting(self) -> None:
        events = _events([1.0, 2.0]) + (
            CadenceEvent(
                timestamp=3.0,
                pair_id_a="alice",
                pair_id_b="bob",
                kind=CadenceEventKind.EXPLICIT_CLOSE,
            ),
        )
        ev = self.t.detect_ghosting(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=100.0,
            events=events,
        )
        assert ev is None


class TestAlertDecouplingRisk:
    def setup_method(self) -> None:
        self.t = CadenceTracker()

    def test_no_events(self) -> None:
        assert self.t.alert_decoupling_risk(
            agent_id="alice", current_time=0.0, events=(),
        ) == ()

    def test_finds_weakening_pairs_for_agent(self) -> None:
        events = (
            *_events([1.0, 2.0, 3.0], a="alice", b="bob"),
            *_events([1.0, 2.0, 3.0], a="alice", b="carol"),
            *_events([1.0, 2.0, 3.0], a="dave", b="erin"),
        )
        risks = self.t.alert_decoupling_risk(
            agent_id="alice", current_time=5.0, events=events,
        )
        assert len(risks) == 2
        pairs = {(r.pair_id_a, r.pair_id_b) for r in risks}
        assert ("alice", "bob") in pairs
        assert ("alice", "carol") in pairs

    def test_excludes_active_pairs(self) -> None:
        events = _events([1.0, 2.0, 3.0])
        risks = self.t.alert_decoupling_risk(
            agent_id="alice", current_time=4.0, events=events,
        )
        assert risks == ()

    def test_empty_agent_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            self.t.alert_decoupling_risk(
                agent_id="", current_time=0.0, events=(),
            )

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_CADENCE_CONFIG.weakening_threshold == 0.5


class TestIntegration:
    def test_inverse_square_law_verbatim(self) -> None:
        # cadence=2.0, elapsed=4.0 → field = (2/4)² = 0.25
        events = _events([0.0, 2.0, 4.0])
        tracker = CadenceTracker()
        out = tracker.compute_field_strength(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=8.0,
            events=events,
        )
        assert abs(out.field_strength - 0.25) < 1e-9

    def test_ghosting_signal_path(self) -> None:
        events = _events([0.0, 2.0, 4.0])  # cadence = 2.0
        tracker = CadenceTracker()
        # elapsed = 10.0, skip = 5.0 multiples → GHOSTED
        ev = tracker.detect_ghosting(
            pair_id_a="alice",
            pair_id_b="bob",
            current_time=14.0,
            events=events,
        )
        assert ev is not None
        assert ev.skipped_cadence_multiples == pytest.approx(5.0)
