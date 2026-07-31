"""Tests for CulturalInfrastructureGapDetector (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.cultural_infrastructure.gap_detector import (
    DEFAULT_GAP_DETECTOR_CONFIG,
    ActivityProfile,
    CulturalInfrastructureGapDetector,
    GapDetectorConfig,
    GapVerdict,
)
from substrate.cultural_infrastructure.inventory import (
    CulturalInfrastructureInventory,
    CulturalMechanism,
    InventoryInput,
    MechanismPresence,
)

def _activity(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    voting: float = 0.0,
    cross_cell: float = 0.0,
    pair_coupling: float = 0.0,
    escalation: float = 0.0,
    reputation: float = 0.0,
    reciprocal: float = 0.0,
) -> ActivityProfile:
    return ActivityProfile(
        voting_activity_score=voting,
        cross_cell_activity_score=cross_cell,
        pair_coupling_activity_score=pair_coupling,
        escalation_activity_score=escalation,
        reputation_activity_score=reputation,
        reciprocal_activity_score=reciprocal,
    )

def _inventory_with(
    present: tuple[CulturalMechanism, ...],
) -> "InventoryReport":  # type: ignore[name-defined]
    return CulturalInfrastructureInventory.compile(
        InventoryInput(
            org_or_node_id="org-1",
            mechanisms=tuple(
                MechanismPresence(
                    mechanism=m, present=True, coverage_ratio=1.0,
                )
                for m in present
            ),
        ),
    )

class TestActivityValidation:
    def test_round_trip(self) -> None:
        a = _activity(voting=0.5)
        assert a.voting_activity_score == 0.5

    def test_out_of_bounds_rejected(self) -> None:
        with pytest.raises(ValueError, match="voting_activity_score"):
            _activity(voting=1.5)

class TestConfig:
    def test_defaults(self) -> None:
        c = GapDetectorConfig()
        assert c.critical_priority_threshold == 0.7

    def test_high_below_critical(self) -> None:
        with pytest.raises(ValueError, match="critical"):
            GapDetectorConfig(
                high_priority_threshold=0.8,
                critical_priority_threshold=0.5,
            )

class TestDetector:
    def setup_method(self) -> None:
        self.d = CulturalInfrastructureGapDetector()

    def test_no_gaps_complete_inventory(self) -> None:
        report = self.d.detect(
            _inventory_with(tuple(CulturalMechanism)),
            _activity(voting=1.0),
        )
        assert report.verdict is GapVerdict.NO_GAPS
        assert report.gap_count == 0

    def test_critical_gap_high_activity(self) -> None:
        report = self.d.detect(
            _inventory_with(()),  # all missing
            _activity(voting=0.9),
        )
        assert report.verdict is GapVerdict.CRITICAL_GAPS
        assert (
            report.gaps[0].mechanism
            is CulturalMechanism.SUBSTRATE_AWARE_VOTING
        )

    def test_high_priority_gap(self) -> None:
        report = self.d.detect(
            _inventory_with(()),
            _activity(cross_cell=0.5),
        )
        assert report.verdict is GapVerdict.HIGH_PRIORITY_GAPS

    def test_low_priority_gap(self) -> None:
        report = self.d.detect(
            _inventory_with(()),
            _activity(reputation=0.1),
        )
        assert report.verdict is GapVerdict.LOW_PRIORITY_GAPS

    def test_gaps_sorted_by_priority(self) -> None:
        report = self.d.detect(
            _inventory_with(()),
            _activity(voting=0.9, cross_cell=0.3, reputation=0.1),
        )
        priorities = [g.priority_score for g in report.gaps]
        assert priorities == sorted(priorities, reverse=True)

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_GAP_DETECTOR_CONFIG.critical_priority_threshold == 0.7
        )
