"""Conformance tests for the executive band — LoadZone / CyclePhase / BandProfile.

Covers:
- classify_load_zone across the six zones + boundary inclusivity (1/3 is RECREATION)
- classify_cycle_phase: pivot window derived from the 24-step cycle, not invented
- BandProfile structural validation R1-R5 (ordering, φ-anchors, conjugate sum,
  symmetry, RESISTANCE tighten-only)
- setpoint_for: RESISTANCE vs WORK bands; GROWTH rejected
- zone_to_legacy projection to the 5-band ZoneClassification
"""
from __future__ import annotations

import pytest

from substrate.executive.band import (
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
    UPPER_BOUND,
    WORK_ZONE_UPPER,
    ZoneClassification,
)


class TestClassifyLoadZone:
    def test_idle_below_third(self) -> None:
        assert classify_load_zone(0.2) is LoadZone.IDLE

    def test_third_is_recreation_inclusive(self) -> None:
        assert classify_load_zone(LOWER_BOUND) is LoadZone.RECREATION

    def test_work_zone(self) -> None:
        assert classify_load_zone(0.44) is LoadZone.WORK

    def test_upper_bound_is_recreation_top(self) -> None:
        # 1/φ² is the inclusive TOP of RECREATION; WORK starts just above.
        assert classify_load_zone(UPPER_BOUND) is LoadZone.RECREATION
        assert classify_load_zone(0.39) is LoadZone.WORK

    def test_peaking(self) -> None:
        assert classify_load_zone(0.55) is LoadZone.PEAKING

    def test_warning(self) -> None:
        assert classify_load_zone(0.64) is LoadZone.WARNING

    def test_danger_above_two_thirds(self) -> None:
        assert classify_load_zone(0.8) is LoadZone.DANGER


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
        assert zone_to_legacy(LoadZone.WORK) is ZoneClassification.WORKING
        assert zone_to_legacy(LoadZone.PEAKING) is ZoneClassification.WORKING
        assert zone_to_legacy(LoadZone.WARNING) is ZoneClassification.PEAKING
        assert zone_to_legacy(LoadZone.DANGER) is ZoneClassification.DEBT
