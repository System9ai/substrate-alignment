"""Tests for EncapsulatingContextStateTracker (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.encapsulating_context.state_tracker import (
    DEFAULT_CONTEXT_STATE_TRACKER_CONFIG,
    ContextObservation,
    ContextScale,
    ContextStateTrackerConfig,
    EncapsulatingContextStateTracker,
    InsufficientContextDataError,
)

def _obs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    context: str = "node-1",
    scale: ContextScale = ContextScale.NODE,
    state: float = 0.7,
    drift: float = 0.05,
    audit: float = 0.1,
    cycle: int = 0,
) -> ContextObservation:
    return ContextObservation(
        context_id=context,
        scale=scale,
        substrate_state=state,
        drift_rate=drift,
        audit_failure_rate=audit,
        cycle_index=cycle,
    )

class TestObservationValidation:
    def test_round_trip(self) -> None:
        o = _obs()
        assert o.substrate_state == 0.7

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("context", "", "context_id"),
            ("state", 1.5, "substrate_state"),
            ("drift", 1.5, "drift_rate"),
            ("audit", -0.1, "audit_failure_rate"),
            ("cycle", -1, "cycle_index"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        c = ContextStateTrackerConfig()
        assert c.window_size == 50

    def test_window_minimum(self) -> None:
        with pytest.raises(ValueError, match="window_size"):
            ContextStateTrackerConfig(window_size=1)

    def test_min_obs_cannot_exceed_window(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            ContextStateTrackerConfig(
                window_size=5, min_observations=10,
            )

class TestTracker:
    def setup_method(self) -> None:
        self.t = EncapsulatingContextStateTracker(
            context_id="node-1", scale=ContextScale.NODE,
        )

    def test_initial_insufficient(self) -> None:
        with pytest.raises(InsufficientContextDataError):
            self.t.aggregate()

    def test_observe_and_aggregate(self) -> None:
        for i in range(5):
            self.t.observe(_obs(state=0.8, cycle=i))
        agg = self.t.aggregate()
        assert agg.observation_count == 5
        assert abs(agg.mean_substrate_state - 0.8) < 1e-9

    def test_context_id_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            self.t.observe(_obs(context="other-node"))

    def test_scale_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="scale"):
            self.t.observe(_obs(scale=ContextScale.ORG))

    def test_window_truncation(self) -> None:
        cfg = ContextStateTrackerConfig(
            window_size=5, min_observations=2,
        )
        t = EncapsulatingContextStateTracker(
            context_id="node-1", scale=ContextScale.NODE, config=cfg,
        )
        for i in range(10):
            t.observe(_obs(state=float(i) / 10.0, cycle=i))
        assert t.observation_count == 5

    def test_latest_reflects_most_recent(self) -> None:
        for i in range(3):
            self.t.observe(_obs(state=0.5, cycle=i))
        self.t.observe(_obs(state=0.9, cycle=3))
        agg = self.t.aggregate()
        assert agg.latest_substrate_state == 0.9

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_CONTEXT_STATE_TRACKER_CONFIG.window_size == 50
        )

    def test_tracker_requires_context_id(self) -> None:
        with pytest.raises(ValueError, match="context_id"):
            EncapsulatingContextStateTracker(
                context_id="", scale=ContextScale.NODE,
            )
