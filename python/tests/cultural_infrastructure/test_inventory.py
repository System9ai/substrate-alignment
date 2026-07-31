"""Tests for CulturalInfrastructureInventory (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.cultural_infrastructure.inventory import (
    ALL_MECHANISMS,
    CulturalInfrastructureInventory,
    CulturalMechanism,
    InventoryInput,
    MechanismPresence,
)

def _full(coverage: float = 1.0) -> tuple[MechanismPresence, ...]:
    return tuple(
        MechanismPresence(
            mechanism=m, present=True, coverage_ratio=coverage,
        )
        for m in CulturalMechanism
    )

class TestMechanismPresence:
    def test_round_trip(self) -> None:
        p = MechanismPresence(
            mechanism=CulturalMechanism.SYMMETRIC_AUDIT,
            present=True, coverage_ratio=0.8,
        )
        assert p.coverage_ratio == 0.8

    def test_coverage_out_of_bounds(self) -> None:
        with pytest.raises(ValueError, match="coverage_ratio"):
            MechanismPresence(
                mechanism=CulturalMechanism.SYMMETRIC_AUDIT,
                present=True, coverage_ratio=1.5,
            )

class TestInventoryInput:
    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="org_or_node_id"):
            InventoryInput(org_or_node_id="", mechanisms=())

    def test_duplicate_mechanism_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            InventoryInput(
                org_or_node_id="org-1",
                mechanisms=(
                    MechanismPresence(
                        mechanism=CulturalMechanism.SYMMETRIC_AUDIT,
                        present=True, coverage_ratio=1.0,
                    ),
                    MechanismPresence(
                        mechanism=CulturalMechanism.SYMMETRIC_AUDIT,
                        present=False, coverage_ratio=0.0,
                    ),
                ),
            )

class TestInventory:
    def test_all_present_complete(self) -> None:
        report = CulturalInfrastructureInventory.compile(
            InventoryInput(
                org_or_node_id="org-1", mechanisms=_full(coverage=1.0),
            ),
        )
        assert report.present_count == 6
        assert report.missing_count == 0
        assert report.is_complete
        assert report.mean_coverage_ratio == 1.0

    def test_none_present(self) -> None:
        report = CulturalInfrastructureInventory.compile(
            InventoryInput(org_or_node_id="org-1", mechanisms=()),
        )
        assert report.present_count == 0
        assert report.missing_count == 6
        assert not report.is_complete
        assert report.mean_coverage_ratio == 0.0

    def test_partial(self) -> None:
        report = CulturalInfrastructureInventory.compile(
            InventoryInput(
                org_or_node_id="org-1",
                mechanisms=(
                    MechanismPresence(
                        mechanism=CulturalMechanism.SYMMETRIC_AUDIT,
                        present=True, coverage_ratio=0.5,
                    ),
                    MechanismPresence(
                        mechanism=CulturalMechanism.HALT_AND_ESCALATE,
                        present=True, coverage_ratio=1.0,
                    ),
                ),
            ),
        )
        assert report.present_count == 2
        assert report.missing_count == 4
        assert (
            CulturalMechanism.SYMMETRIC_AUDIT in report.present_mechanisms
        )
        assert (
            CulturalMechanism.PAIR_COUPLED_ARCHITECTURE
            in report.missing_mechanisms
        )

    def test_explicit_absent(self) -> None:
        report = CulturalInfrastructureInventory.compile(
            InventoryInput(
                org_or_node_id="org-1",
                mechanisms=(
                    MechanismPresence(
                        mechanism=CulturalMechanism.SYMMETRIC_AUDIT,
                        present=False, coverage_ratio=0.0,
                    ),
                ),
            ),
        )
        assert report.missing_count == 6

class TestModuleSurface:
    def test_all_mechanisms_constant(self) -> None:
        assert len(ALL_MECHANISMS) == 6
