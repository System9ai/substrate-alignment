"""Conformance tests for the executive band: LoadZone / CyclePhase / BandProfile.

Covers:
- classify_load_zone across the eight levels + boundary inclusivity (1/3 is RECREATION)
- classify_cycle_phase: pivot window derived from the 24-step cycle, not invented
- BandProfile structural validation R1-R5 (ordering, φ-anchors, conjugate sum,
  symmetry, RESISTANCE tighten-only)
- setpoint_for: RESISTANCE vs WORK bands; GROWTH rejected
- zone_to_legacy projection to the 8-level ZoneClassification (1:1)
"""
from __future__ import annotations

import pytest

from substrate.executive.band import (
    PEAKING_LEVELS,
    WORK_LEVELS,
    BandProfile,
    BandProfileInvalid,
    CyclePhase,
    LoadZone,
    classify_cycle_phase,
    classify_load_zone,
    zone_to_legacy,
)
from substrate.executive.quantities import (
    GrowthNotADecisionBand,
    Quantity,
    setpoint_for,
)
from substrate.resistance_band import (
    LOWER_BOUND,
    PEAKING_MIDPOINT,
    PHI_CONJUGATE,
    UPPER_BOUND,
    WORK_ZONE_MIDPOINT,
    WORK_ZONE_UPPER,
    ZoneClassification,
)


class TestClassifyLoadZone:
    def test_idle_below_third(self) -> None:
        assert classify_load_zone(0.2) is LoadZone.IDLE

    def test_third_is_recreation_inclusive(self) -> None:
        assert classify_load_zone(LOWER_BOUND) is LoadZone.RECREATION

    def test_lower_work_below_the_ninth(self) -> None:
        # (1/φ², 4/9]: the lower work level; 0.44 < 4/9.
        assert classify_load_zone(0.44) is LoadZone.LOWER_WORK

    def test_work_midpoint_is_lower_work_top(self) -> None:
        assert classify_load_zone(WORK_ZONE_MIDPOINT) is LoadZone.LOWER_WORK

    def test_upper_work_above_the_ninth(self) -> None:
        # (4/9, 0.50]: the upper work level; 0.46 > 4/9.
        assert classify_load_zone(0.46) is LoadZone.UPPER_WORK

    def test_pivot_is_upper_work_top(self) -> None:
        assert classify_load_zone(WORK_ZONE_UPPER) is LoadZone.UPPER_WORK

    def test_upper_bound_is_recreation_top(self) -> None:
        # 1/φ² is the inclusive TOP of RECREATION; LOWER_WORK starts just above.
        assert classify_load_zone(UPPER_BOUND) is LoadZone.RECREATION
        assert classify_load_zone(0.39) is LoadZone.LOWER_WORK

    def test_early_peaking_below_the_ninth(self) -> None:
        # (0.50, 5/9]: early peaking; 0.55 < 5/9.
        assert classify_load_zone(0.55) is LoadZone.EARLY_PEAKING

    def test_peaking_midpoint_is_early_peaking_top(self) -> None:
        assert classify_load_zone(PEAKING_MIDPOINT) is LoadZone.EARLY_PEAKING

    def test_committed_peaking_above_the_ninth(self) -> None:
        # (5/9, 1/φ]: committed peaking; 0.60 > 5/9.
        assert classify_load_zone(0.60) is LoadZone.COMMITTED_PEAKING

    def test_growth_ceiling_is_committed_peaking_top(self) -> None:
        assert classify_load_zone(PHI_CONJUGATE) is LoadZone.COMMITTED_PEAKING

    def test_warning(self) -> None:
        assert classify_load_zone(0.64) is LoadZone.WARNING

    def test_danger_above_two_thirds(self) -> None:
        assert classify_load_zone(0.8) is LoadZone.DANGER

    def test_inner_ninths_are_a_mirror_pair(self) -> None:
        assert WORK_ZONE_MIDPOINT + PEAKING_MIDPOINT == pytest.approx(1.0)

    def test_grouping_sets(self) -> None:
        assert classify_load_zone(0.44) in WORK_LEVELS
        assert classify_load_zone(0.55) in PEAKING_LEVELS


class TestClassifyCyclePhase:
    def test_pivot_at_half(self) -> None:
        assert classify_cycle_phase(0.5) is CyclePhase.PIVOT

    def test_ascending_below(self) -> None:
        assert classify_cycle_phase(0.42) is CyclePhase.ASCENDING

    def test_past_pivot_above(self) -> None:
        assert classify_cycle_phase(0.58) is CyclePhase.PAST_PIVOT


class TestBandProfileValidation:
    def test_default_is_valid(self) -> None:
        BandProfile()  # no raise

    def test_ordering_violation_rejected(self) -> None:
        with pytest.raises(BandProfileInvalid) as exc:
            BandProfile(idle_ceiling=0.6, recreation_ceiling=0.5)
        assert exc.value.rule == "R1"

    def test_phi_anchor_violation_rejected(self) -> None:
        with pytest.raises(BandProfileInvalid):
            BandProfile(recreation_ceiling=0.30)  # too far from 1/φ²

    def test_resistance_tighten_only(self) -> None:
        # widening the resistance band to escape challenge is rejected (R5).
        with pytest.raises(BandProfileInvalid) as exc:
            BandProfile(
                idle_ceiling=0.30,  # < 1/3 = looser
                quantity=Quantity.RESISTANCE,
            )
        assert exc.value.rule in ("R1", "R5")


class TestSetpointFor:
    def test_resistance_setpoint(self) -> None:
        low, high = setpoint_for(Quantity.RESISTANCE, BandProfile())
        assert low == pytest.approx(LOWER_BOUND)
        assert high == pytest.approx(UPPER_BOUND)

    def test_work_setpoint(self) -> None:
        low, high = setpoint_for(Quantity.WORK, BandProfile())
        assert low == pytest.approx(UPPER_BOUND)
        assert high == pytest.approx(WORK_ZONE_UPPER)

    def test_growth_rejected(self) -> None:
        with pytest.raises(GrowthNotADecisionBand):
            setpoint_for(Quantity.GROWTH, BandProfile())


class TestZoneToLegacy:
    def test_projection(self) -> None:
        assert zone_to_legacy(LoadZone.IDLE) is ZoneClassification.UNDER_LOADED
        assert zone_to_legacy(LoadZone.RECREATION) is ZoneClassification.CALIBRATION
        assert zone_to_legacy(LoadZone.LOWER_WORK) is ZoneClassification.LOWER_WORK
        assert zone_to_legacy(LoadZone.UPPER_WORK) is ZoneClassification.UPPER_WORK
        assert (
            zone_to_legacy(LoadZone.EARLY_PEAKING)
            is ZoneClassification.EARLY_PEAKING
        )
        assert (
            zone_to_legacy(LoadZone.COMMITTED_PEAKING)
            is ZoneClassification.COMMITTED_PEAKING
        )
        assert zone_to_legacy(LoadZone.WARNING) is ZoneClassification.WARNING
        assert zone_to_legacy(LoadZone.DANGER) is ZoneClassification.DEBT

    def test_eight_levels_map_one_to_one(self) -> None:
        mapped = {zone_to_legacy(z) for z in LoadZone}
        assert len(mapped) == len(list(LoadZone)) == 8


class TestFullLadder:
    def test_full_ladder_monotone(self) -> None:
        order = [
            LoadZone.IDLE,
            LoadZone.RECREATION,
            LoadZone.LOWER_WORK,
            LoadZone.UPPER_WORK,
            LoadZone.EARLY_PEAKING,
            LoadZone.COMMITTED_PEAKING,
            LoadZone.WARNING,
            LoadZone.DANGER,
        ]
        seen = [classify_load_zone(u / 100.0) for u in range(0, 101)]
        assert [z for i, z in enumerate(seen) if i == 0 or z != seen[i - 1]] == order
