"""Tests for GuardRelaxationCurve (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.trust.guard_relaxation_curve import (
    DEFAULT_GUARD_RELAXATION_CONFIG,
    GuardRelaxationConfig,
    GuardRelaxationCurve,
    GuardRelaxationInput,
    GuardRelaxationVerdict,
)

def _input(
    *,
    entity: str = "agent-1",
    cycles: int = 10,
    peer: float = 0.8,
    evidence: float = 0.8,
) -> GuardRelaxationInput:
    return GuardRelaxationInput(
        entity_id=entity,
        sustained_trust_cycles=cycles,
        peer_trust_score=peer,
        evidence_trust_score=evidence,
    )

class TestInputValidation:
    def test_round_trip(self) -> None:
        i = _input()
        assert i.sustained_trust_cycles == 10

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("entity", "", "entity_id"),
            ("cycles", -1, "sustained_trust_cycles"),
            ("peer", 1.5, "peer_trust_score"),
            ("evidence", -0.1, "evidence_trust_score"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _input(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        c = GuardRelaxationConfig()
        assert c.max_relaxation_factor == 0.7

    def test_max_relaxation_must_be_below_one(self) -> None:
        with pytest.raises(
            ValueError, match="max_relaxation_factor",
        ):
            GuardRelaxationConfig(max_relaxation_factor=1.0)

    def test_saturation_must_exceed_min_cycles(self) -> None:
        with pytest.raises(
            ValueError, match="cycles_saturation",
        ):
            GuardRelaxationConfig(
                min_cycles_for_relaxation=10, cycles_saturation=5,
            )

    def test_partial_below_relaxed(self) -> None:
        with pytest.raises(
            ValueError, match="partial_threshold",
        ):
            GuardRelaxationConfig(
                partial_threshold=0.6, relaxed_threshold=0.4,
            )

    def test_relaxed_below_ceiling(self) -> None:
        with pytest.raises(
            ValueError, match="relaxed_threshold cannot exceed",
        ):
            GuardRelaxationConfig(
                partial_threshold=0.5, relaxed_threshold=0.9,
                max_relaxation_factor=0.7,
            )

class TestCurve:
    def setup_method(self) -> None:
        self.c = GuardRelaxationCurve()

    def test_insufficient_cycles(self) -> None:
        out = self.c.evaluate(_input(cycles=2))
        assert out.verdict is GuardRelaxationVerdict.INSUFFICIENT_DATA
        assert out.relaxation_factor == 0.0

    def test_low_peer_trust_not_relaxed(self) -> None:
        out = self.c.evaluate(_input(peer=0.3, evidence=0.9))
        assert out.verdict is GuardRelaxationVerdict.NOT_RELAXED
        assert out.relaxation_factor == 0.0

    def test_low_evidence_trust_not_relaxed(self) -> None:
        out = self.c.evaluate(_input(peer=0.9, evidence=0.2))
        assert out.verdict is GuardRelaxationVerdict.NOT_RELAXED

    def test_partial_relaxation(self) -> None:
        out = self.c.evaluate(_input(
            cycles=8, peer=0.7, evidence=0.7,
        ))
        assert out.verdict in (
            GuardRelaxationVerdict.PARTIAL,
            GuardRelaxationVerdict.NOT_RELAXED,
        )

    def test_max_relaxation_bounded(self) -> None:
        out = self.c.evaluate(_input(
            cycles=1000, peer=1.0, evidence=1.0,
        ))
        assert out.relaxation_factor <= 0.7

    def test_no_full_relaxation_ever(self) -> None:
        out = self.c.evaluate(_input(
            cycles=10000, peer=1.0, evidence=1.0,
        ))
        assert out.relaxation_factor < 1.0

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_GUARD_RELAXATION_CONFIG.max_relaxation_factor == 0.7
        )
