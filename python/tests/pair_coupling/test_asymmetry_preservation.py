"""Tests for AsymmetryPreservationGate (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.pair_coupling.alignment_audit import (
    PairScale,
)
from substrate.pair_coupling.asymmetry_preservation import (
    DEFAULT_ASYMMETRY_PRESERVATION_CONFIG,
    AsymmetryPreservationConfig,
    AsymmetryPreservationGate,
    AsymmetryPreservationInput,
    AsymmetryVerdict,
)

def _input(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    pair: str = "pair-1",
    pole_a: str = "lead",
    pole_b: str = "support",
    scale: PairScale = PairScale.NODE_PAIR,
    designed: float = 0.4,
    current: float = 0.4,
    proposed: float = 0.4,
) -> AsymmetryPreservationInput:
    return AsymmetryPreservationInput(
        pair_id=pair,
        pole_a_id=pole_a,
        pole_b_id=pole_b,
        scale=scale,
        designed_asymmetry=designed,
        current_asymmetry=current,
        proposed_asymmetry=proposed,
    )

class TestInputValidation:
    def test_round_trip(self) -> None:
        i = _input()
        assert i.designed_asymmetry == 0.4

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("pair", "", "pair_id"),
            ("pole_a", "", "pole_a_id"),
            ("pole_b", "", "pole_b_id"),
            ("designed", 1.5, "designed_asymmetry"),
            ("current", -1.5, "current_asymmetry"),
            ("proposed", 1.5, "proposed_asymmetry"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _input(**kwargs)

    def test_same_pole_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            _input(pole_a="x", pole_b="x")

class TestConfig:
    def test_defaults(self) -> None:
        cfg = AsymmetryPreservationConfig()
        assert cfg.designed_asymmetry_floor == 0.05
        assert cfg.collapse_tolerance == 0.1

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("designed_asymmetry_floor", 0.0, "designed_asymmetry_floor"),
            ("designed_asymmetry_floor", 1.5, "designed_asymmetry_floor"),
            ("collapse_tolerance", 0.0, "collapse_tolerance"),
            ("collapse_tolerance", 1.5, "collapse_tolerance"),
        ],
    )
    def test_bad_values(
        self, field: str, value: float, match: str,
    ) -> None:
        with pytest.raises(ValueError, match=match):
            AsymmetryPreservationConfig(**{field: value})

class TestGateLogic:
    def setup_method(self) -> None:
        self.g = AsymmetryPreservationGate()

    def test_preserved(self) -> None:
        out = self.g.evaluate(_input(designed=0.4, proposed=0.4))
        assert out.verdict is AsymmetryVerdict.PRESERVED
        assert out.preserved
        assert not out.inversion

    def test_preserved_negative_design(self) -> None:
        out = self.g.evaluate(_input(designed=-0.4, proposed=-0.35))
        assert out.verdict is AsymmetryVerdict.PRESERVED

    def test_collapse_to_symmetry(self) -> None:
        out = self.g.evaluate(_input(designed=0.4, proposed=0.05))
        assert out.verdict is AsymmetryVerdict.COLLAPSING_TO_SYMMETRY
        assert not out.preserved

    def test_inversion_detected(self) -> None:
        out = self.g.evaluate(_input(designed=0.4, proposed=-0.4))
        assert out.verdict is AsymmetryVerdict.INVERTING_DESIGN
        assert out.inversion

    def test_insufficient_data_below_floor(self) -> None:
        out = self.g.evaluate(_input(designed=0.02, proposed=0.02))
        assert out.verdict is AsymmetryVerdict.INSUFFICIENT_DATA

class TestScaleAwareness:
    def test_cell_pair(self) -> None:
        g = AsymmetryPreservationGate()
        out = g.evaluate(_input(scale=PairScale.CELL_PAIR))
        assert out.scale is PairScale.CELL_PAIR

    def test_org_pair(self) -> None:
        g = AsymmetryPreservationGate()
        out = g.evaluate(_input(scale=PairScale.ORG_PAIR))
        assert out.scale is PairScale.ORG_PAIR

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_ASYMMETRY_PRESERVATION_CONFIG.designed_asymmetry_floor
            == 0.05
        )
