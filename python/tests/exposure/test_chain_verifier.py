"""Tests for ConsequenceExposureChain."""
from __future__ import annotations

import pytest

from substrate.exposure.chain_verifier import (
    DEFAULT_CONSEQUENCE_EXPOSURE_CONFIG,
    ChainVerdict,
    ConsequenceExposureChain,
    ConsequenceExposureConfig,
    ExposureMechanism,
    MechanismAssertion,
    MechanismStatus,
)

def _assert(
    mechanism: ExposureMechanism,
    *,
    available: bool = True,
    strength: float = 0.8,
) -> MechanismAssertion:
    return MechanismAssertion(
        mechanism=mechanism,
        available=available,
        strength=strength,
    )

def _all_available() -> tuple[MechanismAssertion, ...]:
    return tuple(_assert(m) for m in ExposureMechanism)

class TestAssertionValidation:
    def test_round_trip(self) -> None:
        a = _assert(ExposureMechanism.DETECTION)
        assert a.available

    def test_strength_range(self) -> None:
        with pytest.raises(ValueError, match="strength"):
            _assert(ExposureMechanism.DETECTION, strength=1.5)

    def test_unavailable_must_have_zero_strength(self) -> None:
        with pytest.raises(ValueError, match="strength must be 0"):
            _assert(
                ExposureMechanism.DETECTION,
                available=False,
                strength=0.5,
            )

class TestConfig:
    def test_defaults(self) -> None:
        cfg = ConsequenceExposureConfig()
        assert cfg.complete_min_available == 8

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("available_strength_min", 0.0, "available_strength_min"),
            ("degraded_strength_min", 0.9, "degraded_strength_min"),
            ("complete_min_available", 9, "complete_min_available"),
            ("partial_min_available", 0, "partial_min_available"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            ConsequenceExposureConfig(**{field: value})

class TestVerifierFlow:
    def setup_method(self) -> None:
        self.v = ConsequenceExposureChain()

    def test_empty_context_rejected(self) -> None:
        with pytest.raises(ValueError, match="deployment_context_id"):
            self.v.assess("", ())

    def test_no_assertions_insufficient(self) -> None:
        out = self.v.assess("ctx-1", ())
        assert out.verdict is ChainVerdict.INSUFFICIENT_DATA

    def test_duplicate_kinds_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            self.v.assess(
                "ctx-1",
                (
                    _assert(ExposureMechanism.DETECTION),
                    _assert(ExposureMechanism.DETECTION),
                ),
            )

class TestVerdictAggregation:
    def setup_method(self) -> None:
        self.v = ConsequenceExposureChain()

    def test_all_available_complete(self) -> None:
        out = self.v.assess("ctx-1", _all_available())
        assert out.is_complete
        assert out.available_count == 8

    def test_five_available_partial(self) -> None:
        # 5 available, 3 unavailable
        assertions = tuple(
            _assert(
                m,
                available=(i < 5),
                strength=0.8 if i < 5 else 0.0,
            )
            for i, m in enumerate(ExposureMechanism)
        )
        out = self.v.assess("ctx-1", assertions)
        assert out.verdict is ChainVerdict.PARTIAL

    def test_few_available_insufficient(self) -> None:
        # 2 available, 6 unavailable
        assertions = tuple(
            _assert(
                m,
                available=(i < 2),
                strength=0.8 if i < 2 else 0.0,
            )
            for i, m in enumerate(ExposureMechanism)
        )
        out = self.v.assess("ctx-1", assertions)
        assert out.is_insufficient

class TestMechanismEvaluation:
    def setup_method(self) -> None:
        self.v = ConsequenceExposureChain()

    def test_unavailable_when_not_supplied(self) -> None:
        out = self.v.assess(
            "ctx-1",
            (_assert(ExposureMechanism.DETECTION),),
        )
        # SANCTION not supplied → UNAVAILABLE
        finding = out.by_mechanism(ExposureMechanism.SANCTION)
        assert finding is not None
        assert finding.status is MechanismStatus.UNAVAILABLE

    def test_degraded_when_low_strength(self) -> None:
        out = self.v.assess(
            "ctx-1",
            (_assert(
                ExposureMechanism.DETECTION,
                available=True,
                strength=0.4,
            ),),
        )
        finding = out.by_mechanism(ExposureMechanism.DETECTION)
        assert finding is not None
        assert finding.status is MechanismStatus.DEGRADED

    def test_available_strength_threshold(self) -> None:
        out = self.v.assess(
            "ctx-1",
            (_assert(
                ExposureMechanism.DETECTION,
                available=True,
                strength=0.7,
            ),),
        )
        finding = out.by_mechanism(ExposureMechanism.DETECTION)
        assert finding is not None
        assert finding.status is MechanismStatus.AVAILABLE

class TestReportProperties:
    def test_missing_mechanisms_reported(self) -> None:
        v = ConsequenceExposureChain()
        assertions = tuple(
            _assert(m)
            for m in [
                ExposureMechanism.DETECTION,
                ExposureMechanism.RECORDING,
            ]
        )
        out = v.assess("ctx-1", assertions)
        missing = out.missing_mechanisms()
        assert len(missing) == 6  # the other 6 are unavailable

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_CONSEQUENCE_EXPOSURE_CONFIG.complete_min_available == 8
