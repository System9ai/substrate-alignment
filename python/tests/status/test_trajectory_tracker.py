"""Tests for SubstrateStateTrajectoryStatusTracker."""
from __future__ import annotations

import pytest

from substrate.status.trajectory_tracker import (
    DEFAULT_TRAJECTORY_STATUS_CONFIG,
    StatusScale,
    SubstrateStateTrajectoryStatusTracker,
    TrajectoryDataPoint,
    TrajectoryDirection,
    TrajectoryStatusConfig,
)

def _point(
    seq: int,
    *,
    alignment: float = 0.7,
    health: float = 0.8,
    npg: float = 0.7,
    timestamp: int | None = None,
) -> TrajectoryDataPoint:
    return TrajectoryDataPoint(
        sequence=seq,
        timestamp=timestamp if timestamp is not None else seq,
        alignment_score=alignment,
        health_score=health,
        npg_positive_rate=npg,
    )

class TestPointValidation:
    def test_round_trip(self) -> None:
        p = _point(0)
        assert p.sequence == 0

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("seq", -1, "sequence"),
            ("alignment", 1.5, "alignment_score"),
            ("health", -0.1, "health_score"),
            ("npg", 1.5, "npg_positive_rate"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        kwargs = {"seq": 0}
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            _point(**kwargs)  # type: ignore[arg-type]

class TestConfig:
    def test_defaults(self) -> None:
        cfg = TrajectoryStatusConfig()
        assert cfg.min_data_points == 3

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("min_data_points", 1, "min_data_points"),
            ("improving_slope_min", 0.0, "improving_slope_min"),
            ("declining_slope_max", 0.1, "declining_slope_max"),
            ("persistence_threshold", 0.0, "persistence_threshold"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            TrajectoryStatusConfig(**{field: value})

class TestTrackingFlow:
    def setup_method(self) -> None:
        self.t = SubstrateStateTrajectoryStatusTracker()

    def test_empty_entity_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            self.t.track("", StatusScale.CELL, ())

    def test_insufficient_data(self) -> None:
        out = self.t.track(
            "alice", StatusScale.CELL,
            (_point(0), _point(1)),
        )
        assert out.direction is TrajectoryDirection.INSUFFICIENT_DATA

    def test_empty_data(self) -> None:
        out = self.t.track("alice", StatusScale.CELL, ())
        assert out.direction is TrajectoryDirection.INSUFFICIENT_DATA
        assert out.data_point_count == 0

class TestTrajectoryDirection:
    def setup_method(self) -> None:
        self.t = SubstrateStateTrajectoryStatusTracker()

    def test_improving(self) -> None:
        points = tuple(
            _point(i, alignment=0.4 + i * 0.05) for i in range(10)
        )
        out = self.t.track("alice", StatusScale.CELL, points)
        assert out.is_improving
        assert out.alignment_slope > 0

    def test_declining(self) -> None:
        points = tuple(
            _point(i, alignment=0.9 - i * 0.05) for i in range(10)
        )
        out = self.t.track("alice", StatusScale.CELL, points)
        assert out.is_declining
        assert out.alignment_slope < 0

    def test_stable(self) -> None:
        points = tuple(
            _point(i, alignment=0.7) for i in range(10)
        )
        out = self.t.track("alice", StatusScale.CELL, points)
        assert out.is_stable
        assert abs(out.alignment_slope) < 1e-9

class TestPersistenceScore:
    def test_high_persistence(self) -> None:
        t = SubstrateStateTrajectoryStatusTracker()
        points = tuple(_point(i, alignment=0.8) for i in range(10))
        out = t.track("alice", StatusScale.CELL, points)
        assert out.persistence_score == 1.0

    def test_low_persistence(self) -> None:
        t = SubstrateStateTrajectoryStatusTracker()
        points = tuple(_point(i, alignment=0.4) for i in range(10))
        out = t.track("alice", StatusScale.CELL, points)
        assert out.persistence_score == 0.0

    def test_mixed_persistence(self) -> None:
        t = SubstrateStateTrajectoryStatusTracker()
        # 5/10 above threshold (0.6 default)
        points = tuple(
            _point(i, alignment=0.7 if i < 5 else 0.4) for i in range(10)
        )
        out = t.track("alice", StatusScale.CELL, points)
        assert out.persistence_score == 0.5

class TestAccumulatedAlignment:
    def test_average_alignment(self) -> None:
        t = SubstrateStateTrajectoryStatusTracker()
        points = (
            _point(0, alignment=0.2),
            _point(1, alignment=0.5),
            _point(2, alignment=0.8),
        )
        out = t.track("alice", StatusScale.CELL, points)
        assert abs(out.accumulated_alignment_score - 0.5) < 1e-9

class TestScaleAwareness:
    def test_cell_scale(self) -> None:
        t = SubstrateStateTrajectoryStatusTracker()
        points = tuple(_point(i) for i in range(5))
        out = t.track("alice", StatusScale.CELL, points)
        assert out.scale is StatusScale.CELL

    def test_node_scale(self) -> None:
        t = SubstrateStateTrajectoryStatusTracker()
        points = tuple(_point(i) for i in range(5))
        out = t.track("node-alpha", StatusScale.NODE, points)
        assert out.scale is StatusScale.NODE

class TestUnsortedInput:
    def test_unsorted_handled(self) -> None:
        t = SubstrateStateTrajectoryStatusTracker()
        points = (
            _point(3, alignment=0.6),
            _point(1, alignment=0.4),
            _point(2, alignment=0.5),
            _point(0, alignment=0.3),
        )
        out = t.track("alice", StatusScale.CELL, points)
        assert out.is_improving  # actual order 0,1,2,3 has positive slope

class TestModuleSurface:
    def test_default_config_singleton(self) -> None:
        assert DEFAULT_TRAJECTORY_STATUS_CONFIG.min_data_points == 3
