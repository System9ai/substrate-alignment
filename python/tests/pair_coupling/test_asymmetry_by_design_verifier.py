"""Tests for AsymmetryByDesignVerifier (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.pair_coupling.agent_architecture import (
    ArchitectureStatus,
    PairCoupledArchitecture,
    PolePrincipal,
)
from substrate.pair_coupling.alignment_audit import (
    PairScale,
)
from substrate.pair_coupling.asymmetry_by_design_verifier import (
    ArchitecturalAsymmetryVerdict,
    AsymmetryByDesignConfig,
    AsymmetryByDesignVerifier,
    DEFAULT_ASYMMETRY_BY_DESIGN_CONFIG,
)

def _arch(asymmetry: float = 0.4) -> PairCoupledArchitecture:
    return PairCoupledArchitecture(
        coupling_id="pair-1",
        scale=PairScale.NODE_PAIR,
        pole_a=PolePrincipal(
            entity_id="alice", role_label="lead",
            attestation_chain_id="chain-a",
            designed_authority_scope="primary",
        ),
        pole_b=PolePrincipal(
            entity_id="bob", role_label="support",
            attestation_chain_id="chain-b",
            designed_authority_scope="advisory",
        ),
        designed_asymmetry=asymmetry,
        declared_cycle_index=0,
        status=ArchitectureStatus.ACTIVE,
    )

class TestConfig:
    def test_defaults(self) -> None:
        c = AsymmetryByDesignConfig()
        assert c.min_observations == 10

    def test_min_observations_floor(self) -> None:
        with pytest.raises(ValueError, match="min_observations"):
            AsymmetryByDesignConfig(min_observations=1)

    def test_drift_tolerance_bounds(self) -> None:
        with pytest.raises(
            ValueError, match="symmetry_drift_tolerance",
        ):
            AsymmetryByDesignConfig(symmetry_drift_tolerance=1.0)

    def test_inversion_tolerance_bounds(self) -> None:
        with pytest.raises(
            ValueError, match="inversion_tolerance",
        ):
            AsymmetryByDesignConfig(inversion_tolerance=0.0)

class TestVerifier:
    def setup_method(self) -> None:
        self.v = AsymmetryByDesignVerifier()

    def test_insufficient_data(self) -> None:
        out = self.v.verify(_arch(), (0.4,) * 5)
        assert (
            out.verdict is ArchitecturalAsymmetryVerdict.INSUFFICIENT_DATA
        )

    def test_preserved(self) -> None:
        out = self.v.verify(_arch(), (0.4,) * 12)
        assert out.verdict is ArchitecturalAsymmetryVerdict.PRESERVED
        assert out.preserved

    def test_drifting_toward_symmetry(self) -> None:
        # designed=0.4, runtime mean ~0.05 → ratio ~0.125 < 0.5
        out = self.v.verify(_arch(), (0.05,) * 12)
        assert (
            out.verdict
            is ArchitecturalAsymmetryVerdict.DRIFTING_TOWARD_SYMMETRY
        )

    def test_inverted(self) -> None:
        # designed=+0.4, runtime mean=-0.4 → opposite sign, mag 0.4
        out = self.v.verify(_arch(), (-0.4,) * 12)
        assert out.verdict is ArchitecturalAsymmetryVerdict.INVERTED

    def test_bad_runtime_values_rejected(self) -> None:
        with pytest.raises(ValueError, match="runtime_asymmetries"):
            self.v.verify(_arch(), (1.5,) * 12)

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_ASYMMETRY_BY_DESIGN_CONFIG.min_observations == 10
        )
