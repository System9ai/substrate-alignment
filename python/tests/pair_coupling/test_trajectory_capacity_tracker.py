"""Tests for TrajectoryGenerationCapacityTracker (Companion #2b)."""
from __future__ import annotations

import pytest

from substrate.pair_coupling.trajectory_capacity_tracker import (
    CapacityObservation,
    CapacityTrackerConfig,
    CapacityVerdict,
    DEFAULT_CAPACITY_TRACKER_CONFIG,
    TrajectoryGenerationCapacityTracker,
)

def _obs(
    *,
    entity: str = "agent-1",
    cycle: int,
    generated: int,
    novel: int,
) -> CapacityObservation:
    return CapacityObservation(
        entity_id=entity,
        cycle_index=cycle,
        trajectories_generated=generated,
        novel_trajectories_count=novel,
    )

class TestObservationValidation:
    def test_round_trip(self) -> None:
        o = _obs(cycle=0, generated=5, novel=3)
        assert o.novelty_ratio == 0.6

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("entity", "", "entity_id"),
            ("cycle", -1, "cycle_index"),
            ("generated", -1, "trajectories_generated"),
            ("novel", -1, "novel_trajectories_count"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {
            "entity": "agent-1",
            "cycle": 0,
            "generated": 1,
            "novel": 0,
            field: value,
        }
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)

    def test_novel_cannot_exceed_generated(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            _obs(cycle=0, generated=2, novel=5)

class TestConfig:
    def test_defaults(self) -> None:
        c = CapacityTrackerConfig()
        assert c.window_size == 20

    def test_min_obs_cannot_exceed_window(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            CapacityTrackerConfig(
                window_size=5, min_observations=10,
            )

    def test_declining_slope_negative(self) -> None:
        with pytest.raises(
            ValueError, match="declining_slope_threshold",
        ):
            CapacityTrackerConfig(declining_slope_threshold=0.0)

    def test_minimum_novelty_bounds(self) -> None:
        with pytest.raises(
            ValueError, match="minimum_novelty_ratio",
        ):
            CapacityTrackerConfig(minimum_novelty_ratio=0.0)

class TestTracker:
    def setup_method(self) -> None:
        self.t = TrajectoryGenerationCapacityTracker(
            entity_id="agent-1",
        )

    def test_insufficient_data(self) -> None:
        self.t.observe(_obs(cycle=0, generated=5, novel=3))
        out = self.t.verdict()
        assert out.verdict is CapacityVerdict.INSUFFICIENT_DATA

    def test_sustained(self) -> None:
        for i in range(10):
            self.t.observe(_obs(cycle=i, generated=8, novel=5))
        out = self.t.verdict()
        assert out.verdict is CapacityVerdict.SUSTAINED

    def test_declining_via_slope(self) -> None:
        # generated declining 10 → 1
        for i, g in enumerate([10, 8, 6, 4, 2, 1, 1, 1]):
            self.t.observe(_obs(cycle=i, generated=g, novel=g // 2))
        out = self.t.verdict()
        assert out.declining

    def test_declining_via_low_novelty(self) -> None:
        # high count but zero novelty
        for i in range(10):
            self.t.observe(_obs(cycle=i, generated=10, novel=0))
        out = self.t.verdict()
        assert out.verdict is CapacityVerdict.DECLINING

    def test_collapsed(self) -> None:
        for i in range(10):
            self.t.observe(_obs(cycle=i, generated=0, novel=0))
        out = self.t.verdict()
        assert out.verdict is CapacityVerdict.COLLAPSED

    def test_entity_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            self.t.observe(_obs(
                entity="other", cycle=0, generated=1, novel=0,
            ))

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_CAPACITY_TRACKER_CONFIG.window_size == 20
        )

    def test_tracker_requires_entity_id(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            TrajectoryGenerationCapacityTracker(entity_id="")
