"""Tests for TitForTatReciprocalProtocol."""
from __future__ import annotations

import pytest

from substrate.reciprocity.tit_for_tat import (
    DEFAULT_TIT_FOR_TAT_CONFIG,
    InteractionRecord,
    PatternShiftKind,
    ReciprocalAction,
    ReciprocalDecision,
    TitForTatConfig,
    TitForTatReciprocalProtocol,
    TitForTatStrategy,
)

def _cooperative(seq: int, peer: str = "bob", ts: int = 0) -> InteractionRecord:
    return InteractionRecord(
        sequence=seq,
        peer_id=peer,
        peer_action=ReciprocalAction.COOPERATE,
        own_action=ReciprocalAction.COOPERATE,
        peer_misaligned=False,
        misalignment_severity=0.0,
        timestamp=ts,
    )

def _misaligned(
    seq: int, severity: float = 0.5, peer: str = "bob", ts: int = 0,
) -> InteractionRecord:
    return InteractionRecord(
        sequence=seq,
        peer_id=peer,
        peer_action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
        own_action=ReciprocalAction.COOPERATE,
        peer_misaligned=True,
        misalignment_severity=severity,
        timestamp=ts,
    )

class TestInteractionRecord:
    def test_round_trip(self) -> None:
        rec = _cooperative(seq=0)
        assert rec.sequence == 0
        assert not rec.peer_misaligned

    def test_negative_sequence_rejected(self) -> None:
        with pytest.raises(ValueError, match="sequence"):
            InteractionRecord(
                sequence=-1,
                peer_id="bob",
                peer_action=ReciprocalAction.COOPERATE,
                own_action=ReciprocalAction.COOPERATE,
                peer_misaligned=False,
                misalignment_severity=0.0,
                timestamp=0,
            )

    def test_empty_peer_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="peer_id"):
            InteractionRecord(
                sequence=0,
                peer_id="",
                peer_action=ReciprocalAction.COOPERATE,
                own_action=ReciprocalAction.COOPERATE,
                peer_misaligned=False,
                misalignment_severity=0.0,
                timestamp=0,
            )

    def test_severity_range(self) -> None:
        with pytest.raises(ValueError, match="misalignment_severity"):
            InteractionRecord(
                sequence=0,
                peer_id="bob",
                peer_action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
                own_action=ReciprocalAction.COOPERATE,
                peer_misaligned=True,
                misalignment_severity=1.5,
                timestamp=0,
            )

    def test_misalignment_consistency(self) -> None:
        with pytest.raises(
            ValueError, match="severity must be > 0 when peer_misaligned"
        ):
            InteractionRecord(
                sequence=0,
                peer_id="bob",
                peer_action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
                own_action=ReciprocalAction.COOPERATE,
                peer_misaligned=True,
                misalignment_severity=0.0,
                timestamp=0,
            )

    def test_alignment_zero_severity(self) -> None:
        with pytest.raises(
            ValueError, match="severity must be 0 when peer_misaligned is False"
        ):
            InteractionRecord(
                sequence=0,
                peer_id="bob",
                peer_action=ReciprocalAction.COOPERATE,
                own_action=ReciprocalAction.COOPERATE,
                peer_misaligned=False,
                misalignment_severity=0.1,
                timestamp=0,
            )

class TestReciprocalDecision:
    def test_proportional_requires_severity(self) -> None:
        with pytest.raises(ValueError, match="PROPORTIONATE_CONSEQUENCE"):
            ReciprocalDecision(
                action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
                strategy_used=TitForTatStrategy.TIT_FOR_TAT,
                rationale="x",
                severity_proportion=0.0,
            )

    def test_cooperative_zero_severity(self) -> None:
        dec = ReciprocalDecision(
            action=ReciprocalAction.COOPERATE,
            strategy_used=TitForTatStrategy.TIT_FOR_TAT,
            rationale="x",
        )
        assert dec.is_cooperative
        assert dec.severity_proportion == 0.0

    def test_forgive_cooperative(self) -> None:
        dec = ReciprocalDecision(
            action=ReciprocalAction.FORGIVE,
            strategy_used=TitForTatStrategy.GENEROUS_TIT_FOR_TAT,
            rationale="forgiveness",
        )
        assert dec.is_cooperative

    def test_severity_range(self) -> None:
        with pytest.raises(ValueError, match="severity_proportion"):
            ReciprocalDecision(
                action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
                strategy_used=TitForTatStrategy.TIT_FOR_TAT,
                rationale="x",
                severity_proportion=1.5,
            )

class TestTitForTatConfig:
    def test_defaults_ok(self) -> None:
        cfg = TitForTatConfig()
        assert cfg.two_tats_window >= 2

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("two_tats_window", 1, "two_tats_window"),
            ("generosity_threshold", 0.0, "generosity_threshold"),
            ("generosity_threshold", 1.5, "generosity_threshold"),
            ("generosity_window", 1, "generosity_window"),
            ("pattern_shift_window", 1, "pattern_shift_window"),
            ("oscillation_min_flips", 1, "oscillation_min_flips"),
        ],
    )
    def test_bad_fields(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            TitForTatConfig(**{field: value})

class TestInitialAction:
    def test_initial_cooperates(self) -> None:
        proto = TitForTatReciprocalProtocol()
        dec = proto.initial_action("bob")
        assert dec.action is ReciprocalAction.COOPERATE
        assert "first interaction" in dec.rationale

    def test_empty_peer_id_rejected(self) -> None:
        proto = TitForTatReciprocalProtocol()
        with pytest.raises(ValueError, match="peer_id"):
            proto.initial_action("")

    def test_strategy_property(self) -> None:
        proto = TitForTatReciprocalProtocol(
            strategy=TitForTatStrategy.GENEROUS_TIT_FOR_TAT,
        )
        assert proto.strategy is TitForTatStrategy.GENEROUS_TIT_FOR_TAT

class TestBasicTFT:
    def setup_method(self) -> None:
        self.proto = TitForTatReciprocalProtocol(
            strategy=TitForTatStrategy.TIT_FOR_TAT,
        )

    def test_empty_history_initial(self) -> None:
        dec = self.proto.response_action("bob", ())
        assert dec.action is ReciprocalAction.COOPERATE
        assert "first interaction" in dec.rationale

    def test_other_peer_history_ignored(self) -> None:
        history = (
            _misaligned(seq=0, peer="carol"),
            _misaligned(seq=1, peer="carol"),
        )
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.COOPERATE

    def test_peer_cooperated_cooperate(self) -> None:
        history = (_cooperative(seq=0),)
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.COOPERATE

    def test_peer_misaligned_mirror(self) -> None:
        history = (_misaligned(seq=0, severity=0.4),)
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.PROPORTIONATE_CONSEQUENCE
        assert dec.severity_proportion == 0.4
        assert dec.triggered_by is history[0]

    def test_history_unsorted_uses_max_sequence(self) -> None:
        history = (
            _misaligned(seq=2, severity=0.6),
            _cooperative(seq=0),
            _cooperative(seq=1),
        )
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.PROPORTIONATE_CONSEQUENCE

    def test_return_to_cooperation(self) -> None:
        history = (
            _misaligned(seq=0, severity=0.5),
            _cooperative(seq=1),
        )
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.COOPERATE

class TestTitForTwoTats:
    def setup_method(self) -> None:
        self.proto = TitForTatReciprocalProtocol(
            strategy=TitForTatStrategy.TIT_FOR_TWO_TATS,
        )

    def test_single_misalignment_cooperate(self) -> None:
        history = (_cooperative(seq=0), _misaligned(seq=1, severity=0.5))
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.COOPERATE

    def test_two_misalignments_retaliate(self) -> None:
        history = (
            _misaligned(seq=0, severity=0.3),
            _misaligned(seq=1, severity=0.5),
        )
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.PROPORTIONATE_CONSEQUENCE
        assert dec.severity_proportion == 0.5

    def test_misaligned_cooperate_misaligned_no_retaliate(self) -> None:
        history = (
            _misaligned(seq=0),
            _cooperative(seq=1),
            _misaligned(seq=2),
        )
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.COOPERATE

class TestGenerousTFT:
    def setup_method(self) -> None:
        self.proto = TitForTatReciprocalProtocol(
            strategy=TitForTatStrategy.GENEROUS_TIT_FOR_TAT,
            config=TitForTatConfig(
                generosity_threshold=0.5, generosity_window=4,
            ),
        )

    def test_peer_cooperated_cooperate(self) -> None:
        history = (_cooperative(seq=0),)
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.COOPERATE

    def test_low_rate_forgive(self) -> None:
        history = (
            _cooperative(seq=0),
            _cooperative(seq=1),
            _cooperative(seq=2),
            _misaligned(seq=3, severity=0.6),
        )
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.FORGIVE
        assert "forgive" in dec.rationale

    def test_high_rate_mirror(self) -> None:
        history = (
            _misaligned(seq=0, severity=0.5),
            _misaligned(seq=1, severity=0.5),
            _misaligned(seq=2, severity=0.5),
            _misaligned(seq=3, severity=0.5),
        )
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.PROPORTIONATE_CONSEQUENCE
        assert dec.severity_proportion == 0.5

class TestWinStayLoseShift:
    def setup_method(self) -> None:
        self.proto = TitForTatReciprocalProtocol(
            strategy=TitForTatStrategy.WIN_STAY_LOSE_SHIFT,
        )

    def test_both_cooperated_stay_cooperate(self) -> None:
        history = (_cooperative(seq=0),)
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.COOPERATE
        assert "stay" in dec.rationale

    def test_we_retaliated_peer_cooperated_shift_to_cooperate(self) -> None:
        history = (
            InteractionRecord(
                sequence=0,
                peer_id="bob",
                peer_action=ReciprocalAction.COOPERATE,
                own_action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
                peer_misaligned=False,
                misalignment_severity=0.0,
                timestamp=0,
            ),
        )
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.COOPERATE
        assert "shift" in dec.rationale

    def test_we_cooperated_peer_misaligned_shift_to_retaliate(self) -> None:
        history = (_misaligned(seq=0, severity=0.6),)
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.PROPORTIONATE_CONSEQUENCE
        assert dec.severity_proportion == 0.6

    def test_both_misaligned_stay_retaliate(self) -> None:
        history = (
            InteractionRecord(
                sequence=0,
                peer_id="bob",
                peer_action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
                own_action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
                peer_misaligned=True,
                misalignment_severity=0.3,
                timestamp=0,
            ),
        )
        dec = self.proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.PROPORTIONATE_CONSEQUENCE
        assert dec.severity_proportion == 0.3

class TestPatternShifts:
    def setup_method(self) -> None:
        self.proto = TitForTatReciprocalProtocol(
            config=TitForTatConfig(pattern_shift_window=3),
        )

    def test_no_history_no_shift(self) -> None:
        assert self.proto.detect_pattern_shifts("bob", ()) is None

    def test_short_history_no_shift(self) -> None:
        history = tuple(_cooperative(seq=i) for i in range(4))
        assert self.proto.detect_pattern_shifts("bob", history) is None

    def test_misalignment_shift(self) -> None:
        history = (
            _cooperative(seq=0),
            _cooperative(seq=1),
            _cooperative(seq=2),
            _misaligned(seq=3),
            _misaligned(seq=4),
            _misaligned(seq=5),
        )
        shift = self.proto.detect_pattern_shifts("bob", history)
        assert shift is not None
        assert shift.kind is PatternShiftKind.MISALIGNMENT_SHIFT
        assert shift.pivot_sequence == 3

    def test_realignment_shift(self) -> None:
        history = (
            _misaligned(seq=0),
            _misaligned(seq=1),
            _misaligned(seq=2),
            _cooperative(seq=3),
            _cooperative(seq=4),
            _cooperative(seq=5),
        )
        shift = self.proto.detect_pattern_shifts("bob", history)
        assert shift is not None
        assert shift.kind is PatternShiftKind.REALIGNMENT_SHIFT

    def test_oscillation(self) -> None:
        # 6 records with 5 flips → oscillation (min_flips=3 default)
        history = (
            _cooperative(seq=0),
            _misaligned(seq=1),
            _cooperative(seq=2),
            _misaligned(seq=3),
            _cooperative(seq=4),
            _misaligned(seq=5),
        )
        shift = self.proto.detect_pattern_shifts("bob", history)
        assert shift is not None
        assert shift.kind is PatternShiftKind.OSCILLATION

    def test_filters_by_peer(self) -> None:
        history = (
            _misaligned(seq=0, peer="carol"),
            _misaligned(seq=1, peer="carol"),
            _misaligned(seq=2, peer="carol"),
            _misaligned(seq=3, peer="carol"),
            _misaligned(seq=4, peer="carol"),
            _misaligned(seq=5, peer="carol"),
        )
        assert self.proto.detect_pattern_shifts("bob", history) is None

    def test_empty_peer_rejected(self) -> None:
        with pytest.raises(ValueError, match="peer_id"):
            self.proto.detect_pattern_shifts("", ())

class TestIntegrationScenarios:
    def test_axelrod_recover_after_one_off_misalignment(self) -> None:
        proto = TitForTatReciprocalProtocol()
        history = (
            _cooperative(seq=0),
            _cooperative(seq=1),
            _misaligned(seq=2, severity=0.5),
            _cooperative(seq=3),
        )
        dec = proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.COOPERATE

    def test_generous_default_threshold(self) -> None:
        proto = TitForTatReciprocalProtocol(
            strategy=TitForTatStrategy.GENEROUS_TIT_FOR_TAT,
            config=DEFAULT_TIT_FOR_TAT_CONFIG,
        )
        # 1 misaligned out of 5 = 0.2 not strictly less than default 0.2
        history = (
            _cooperative(seq=0),
            _cooperative(seq=1),
            _cooperative(seq=2),
            _cooperative(seq=3),
            _misaligned(seq=4, severity=0.4),
        )
        dec = proto.response_action("bob", history)
        assert dec.action is ReciprocalAction.PROPORTIONATE_CONSEQUENCE

    def test_returns_to_cooperation_promptly(self) -> None:
        proto = TitForTatReciprocalProtocol()
        history = (
            _cooperative(seq=0),
            _misaligned(seq=1, severity=0.8),
            _misaligned(seq=2, severity=0.8),
            _cooperative(seq=3),
        )
        dec = proto.response_action("bob", history)
        assert dec.is_cooperative
