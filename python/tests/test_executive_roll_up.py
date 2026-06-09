"""Tests for the scale roll-up aggregator (physical / grouping axes)."""
from __future__ import annotations

import pytest

from substrate.executive.band import LoadZone
from substrate.executive.roll_up import (
    MemberLoad,
    RollUpError,
    ScaleAggregate,
    roll_up,
)
from substrate.executive.scale import (
    ExecutiveScale,
    ScaleAxis,
)


def _cells(*us: float) -> list[MemberLoad]:
    return [MemberLoad(f"c{i}", u, ExecutiveScale.CELL) for i, u in enumerate(us)]


class TestMemberLoadValidation:
    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="member_id"):
            MemberLoad("", 0.4, ExecutiveScale.CELL)

    def test_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="utilization"):
            MemberLoad("c", 1.5, ExecutiveScale.CELL)


class TestRollUp:
    def test_empty_returns_none(self) -> None:
        assert roll_up([], to_scale=ExecutiveScale.RACK) is None

    def test_aggregates_a_rack_of_cells(self) -> None:
        agg = roll_up(_cells(0.44, 0.46, 0.82, 0.2), to_scale=ExecutiveScale.RACK)
        assert isinstance(agg, ScaleAggregate)
        assert agg.scale is ExecutiveScale.RACK
        assert agg.axis is ScaleAxis.PHYSICAL
        assert agg.member_count == 4
        assert agg.mean_utilization == pytest.approx((0.44 + 0.46 + 0.82 + 0.2) / 4)

    def test_worst_zone_is_most_severe_member(self) -> None:
        agg = roll_up(_cells(0.44, 0.46, 0.82, 0.2), to_scale=ExecutiveScale.RACK)
        assert agg is not None
        assert agg.worst_zone is LoadZone.DANGER

    def test_dominant_zone_is_modal(self) -> None:
        agg = roll_up(_cells(0.44, 0.46, 0.82, 0.2), to_scale=ExecutiveScale.RACK)
        assert agg is not None
        assert agg.dominant_zone is LoadZone.WORK  # two cells in the work zone

    def test_failure_tell_fractions(self) -> None:
        agg = roll_up(_cells(0.44, 0.46, 0.82, 0.2), to_scale=ExecutiveScale.RACK)
        assert agg is not None
        assert agg.fraction_in_danger == pytest.approx(0.25)
        assert agg.fraction_idle == pytest.approx(0.25)

    def test_zone_distribution_in_severity_order(self) -> None:
        agg = roll_up(_cells(0.44, 0.46, 0.82, 0.2), to_scale=ExecutiveScale.RACK)
        assert agg is not None
        zones = [z for z, _ in agg.zone_distribution]
        assert zones == [LoadZone.IDLE, LoadZone.WORK, LoadZone.DANGER]

    def test_cross_axis_member_rejected(self) -> None:
        with pytest.raises(RollUpError, match="axis"):
            roll_up(
                [MemberLoad("a", 0.4, ExecutiveScale.AGENT)],
                to_scale=ExecutiveScale.RACK,
            )

    def test_member_not_below_parent_rejected(self) -> None:
        with pytest.raises(RollUpError, match="not below"):
            roll_up(
                [MemberLoad("z", 0.4, ExecutiveScale.ZONE)],
                to_scale=ExecutiveScale.RACK,
            )

    def test_cells_roll_up_to_region(self) -> None:
        # CELL is strictly below REGION on the physical axis.
        agg = roll_up(_cells(0.4, 0.5), to_scale=ExecutiveScale.REGION)
        assert agg is not None
        assert agg.scale is ExecutiveScale.REGION

    def test_grouping_axis_rolls_up(self) -> None:
        # Grouping axis: members aggregate into their group (no strict-below check).
        members = [
            MemberLoad("m0", 0.44, ExecutiveScale.SERVICE_GROUP),
            MemberLoad("m1", 0.5, ExecutiveScale.SERVICE_GROUP),
        ]
        agg = roll_up(members, to_scale=ExecutiveScale.SERVICE_GROUP)
        assert agg is not None
        assert agg.axis is ScaleAxis.GROUPING
