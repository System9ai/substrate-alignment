"""Tests for SubstrateCoherenceTrustScorer"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from substrate.audit.substrate_trace import (
    DriftPatternSummary,
    SubstrateTraceLedger,
)
from substrate.drift.drift_pattern_matcher import DriftPattern
from substrate.harness import InterceptKind
from substrate.net_potential_gain_gate import (
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
)
from substrate.trust.substrate_coherence_trust_scorer import (
    DEFAULT_TRUST_SCORER_CONFIG,
    SubstrateCoherenceTrustScorer,
    TrustScore,
    TrustScoreComponents,
    TrustScorerConfig,
    TrustVerdict,
)

# -----------------------------
# Helpers
# -----------------------------

def _append(ledger: SubstrateTraceLedger, **overrides: Any) -> None:
    base: dict[str, Any] = {
        "decision_id": "d-?",
        "decision_kind": "observer_activate",
        "permitted": True,
        "rationale": "ok",
        "epoch_seconds": 1_700_000_000,
    }
    base.update(overrides)
    ledger.append(**base)

def _trusted_ledger(count: int = 10) -> SubstrateTraceLedger:
    ledger = SubstrateTraceLedger()
    for i in range(count):
        _append(
            ledger,
            decision_id=f"d-{i}",
            epoch_seconds=1_700_000_000 + i,
            npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
            resistance_band=ResistanceBandClassification.PRODUCTIVE,
        )
    return ledger

def _drifting_ledger(count: int = 10) -> SubstrateTraceLedger:
    ledger = SubstrateTraceLedger()
    for i in range(count):
        _append(
            ledger,
            decision_id=f"d-{i}",
            epoch_seconds=1_700_000_000 + i,
            permitted=False,
            npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
            resistance_band=ResistanceBandClassification.STRESSED,
            sin_summary=DriftPatternSummary(
                dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                composite_confidence=0.9,
                amplifier_pattern_present=True,
                kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION,),
            ),
            harness_intercept_kinds=(
                InterceptKind.NPG_NEGATIVE,
                InterceptKind.INVERSION_DETECTED,
            ),
        )
    return ledger

def _scorer() -> SubstrateCoherenceTrustScorer:
    return SubstrateCoherenceTrustScorer()

# -----------------------------
# Config validation
# -----------------------------

class TestConfigValidation:
    def test_default_config_valid(self) -> None:
        assert isinstance(DEFAULT_TRUST_SCORER_CONFIG, TrustScorerConfig)

    def test_min_records_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_records"):
            TrustScorerConfig(min_records=0)

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValueError, match="npg_weight"):
            TrustScorerConfig(npg_weight=-1.0)

    def test_zero_weight_rejected(self) -> None:
        with pytest.raises(ValueError, match="productive_weight"):
            TrustScorerConfig(productive_weight=0.0)

    def test_trusted_threshold_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="trusted_threshold"):
            TrustScorerConfig(trusted_threshold=0.0)
        with pytest.raises(ValueError, match="trusted_threshold"):
            TrustScorerConfig(trusted_threshold=1.5)

    def test_drifting_threshold_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="drifting_threshold"):
            TrustScorerConfig(drifting_threshold=-0.1)
        with pytest.raises(ValueError, match="drifting_threshold"):
            TrustScorerConfig(drifting_threshold=1.0)

    def test_thresholds_must_be_ordered(self) -> None:
        with pytest.raises(ValueError, match="trusted_threshold"):
            TrustScorerConfig(
                trusted_threshold=0.4, drifting_threshold=0.5,
            )
        with pytest.raises(ValueError, match="trusted_threshold"):
            TrustScorerConfig(
                trusted_threshold=0.5, drifting_threshold=0.5,
            )

# -----------------------------
# Insufficient data
# -----------------------------

class TestInsufficientData:
    def test_empty_records_insufficient(self) -> None:
        s = _scorer()
        result = s.score(entity_id="agent-1", records=())
        assert result.verdict is TrustVerdict.INSUFFICIENT_DATA
        assert result.components is None
        assert result.composite_score is None
        assert result.record_count == 0
        assert result.is_insufficient is True

    def test_below_min_records_insufficient(self) -> None:
        s = SubstrateCoherenceTrustScorer(
            config=TrustScorerConfig(min_records=5),
        )
        ledger = _trusted_ledger(count=3)
        result = s.score_from_ledger(
            entity_id="agent-1", ledger=ledger,
        )
        assert result.verdict is TrustVerdict.INSUFFICIENT_DATA
        assert "insufficient history" in result.rationale.lower()

    def test_at_min_records_not_insufficient(self) -> None:
        s = SubstrateCoherenceTrustScorer(
            config=TrustScorerConfig(min_records=3),
        )
        ledger = _trusted_ledger(count=3)
        result = s.score_from_ledger(
            entity_id="agent-1", ledger=ledger,
        )
        assert result.verdict is not TrustVerdict.INSUFFICIENT_DATA

    def test_empty_entity_id_rejected(self) -> None:
        s = _scorer()
        with pytest.raises(ValueError, match="entity_id"):
            s.score(entity_id="", records=())

# -----------------------------
# Verdict resolution
# -----------------------------

class TestVerdictResolution:
    def test_all_perfect_records_trusted(self) -> None:
        s = _scorer()
        ledger = _trusted_ledger(count=10)
        result = s.score_from_ledger(entity_id="agent-1", ledger=ledger)
        assert result.verdict is TrustVerdict.TRUSTED
        assert result.is_trusted is True
        assert result.composite_score is not None
        assert result.composite_score > 0.75

    def test_all_drifting_records_drifting(self) -> None:
        s = _scorer()
        ledger = _drifting_ledger(count=10)
        result = s.score_from_ledger(entity_id="agent-1", ledger=ledger)
        assert result.verdict is TrustVerdict.DRIFTING
        assert result.is_drifting is True
        assert result.composite_score is not None
        assert result.composite_score < 0.4

    def test_mixed_records_mixed(self) -> None:
        # 5 trusted records + 5 drifting → composite ≈ 0.5 → MIXED
        s = _scorer()
        ledger = SubstrateTraceLedger()
        for i in range(5):
            _append(
                ledger, decision_id=f"good-{i}", epoch_seconds=i,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
                resistance_band=ResistanceBandClassification.PRODUCTIVE,
            )
        for i in range(5):
            _append(
                ledger, decision_id=f"bad-{i}", epoch_seconds=100 + i,
                permitted=False,
                npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
                resistance_band=ResistanceBandClassification.STRESSED,
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.REACTIVE_NET_NEGATIVE,
                    composite_confidence=0.9,
                    amplifier_pattern_present=False,
                    kinds_detected=(DriftPattern.REACTIVE_NET_NEGATIVE,),
                ),
                harness_intercept_kinds=(
                    InterceptKind.NPG_NEGATIVE,
                ),
            )
        result = s.score_from_ledger(entity_id="agent-1", ledger=ledger)
        assert result.verdict is TrustVerdict.MIXED

# -----------------------------
# Component scoring
# -----------------------------

class TestComponentScoring:
    def test_components_present_when_above_threshold(self) -> None:
        s = SubstrateCoherenceTrustScorer(
            config=TrustScorerConfig(min_records=1),
        )
        ledger = _trusted_ledger(count=2)
        result = s.score_from_ledger(entity_id="agent-1", ledger=ledger)
        assert result.components is not None
        c = result.components
        assert c.npg_positive_rate == 1.0
        assert c.productive_rate == 1.0
        assert c.intercept_inverse == 1.0
        assert c.sin_inverse == 1.0
        assert c.inversion_inverse == 1.0

    def test_inversion_inverse_lowered_by_inversion_intercepts(self) -> None:
        s = SubstrateCoherenceTrustScorer(
            config=TrustScorerConfig(min_records=1),
        )
        ledger = SubstrateTraceLedger()
        for i in range(2):
            _append(
                ledger, decision_id=f"d-{i}", epoch_seconds=i,
                harness_intercept_kinds=(
                    InterceptKind.INVERSION_DETECTED,
                ),
            )
        result = s.score_from_ledger(entity_id="agent-1", ledger=ledger)
        assert result.components is not None
        assert result.components.inversion_inverse == 0.0

    def test_non_inversion_intercept_does_not_lower_inversion_inverse(self) -> None:
        s = SubstrateCoherenceTrustScorer(
            config=TrustScorerConfig(min_records=1),
        )
        ledger = SubstrateTraceLedger()
        for i in range(2):
            _append(
                ledger, decision_id=f"d-{i}", epoch_seconds=i,
                harness_intercept_kinds=(InterceptKind.NPG_NEGATIVE,),
            )
        result = s.score_from_ledger(entity_id="agent-1", ledger=ledger)
        assert result.components is not None
        # Non-inversion intercepts don't reduce inversion_inverse.
        assert result.components.inversion_inverse == 1.0
        # But they DO reduce intercept_inverse (because intercepts fired).
        assert result.components.intercept_inverse == 0.0

    def test_sin_detection_lowers_sin_inverse(self) -> None:
        s = SubstrateCoherenceTrustScorer(
            config=TrustScorerConfig(min_records=1),
        )
        ledger = SubstrateTraceLedger()
        _append(
            ledger, decision_id="d-1", epoch_seconds=1,
            sin_summary=DriftPatternSummary(
                dominant_pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION, composite_confidence=0.9,
                amplifier_pattern_present=True, kinds_detected=(DriftPattern.SELF_REFERENCE_MISCALIBRATION,),
            ),
        )
        _append(ledger, decision_id="d-2", epoch_seconds=2)  # clean
        result = s.score_from_ledger(entity_id="agent-1", ledger=ledger)
        assert result.components is not None
        assert result.components.sin_inverse == 0.5

# -----------------------------
# Custom weights + thresholds
# -----------------------------

class TestCustomConfig:
    def test_weight_changes_composite(self) -> None:
        # NPG-heavy weighting: composite dominated by NPG component.
        s_heavy = SubstrateCoherenceTrustScorer(
            config=TrustScorerConfig(
                min_records=1,
                npg_weight=10.0,
                productive_weight=1.0,
                intercept_inverse_weight=1.0,
                sin_inverse_weight=1.0,
                inversion_inverse_weight=1.0,
            ),
        )
        s_balanced = SubstrateCoherenceTrustScorer(
            config=TrustScorerConfig(min_records=1),
        )
        ledger = SubstrateTraceLedger()
        # NPG positive but other components weak.
        for i in range(3):
            _append(
                ledger, decision_id=f"d-{i}", epoch_seconds=i,
                permitted=False,
                npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
                resistance_band=ResistanceBandClassification.STRESSED,
                sin_summary=DriftPatternSummary(
                    dominant_pattern=DriftPattern.REACTIVE_NET_NEGATIVE, composite_confidence=0.5,
                    amplifier_pattern_present=False, kinds_detected=(DriftPattern.REACTIVE_NET_NEGATIVE,),
                ),
                harness_intercept_kinds=(InterceptKind.NPG_NEGATIVE,),
            )
        heavy = s_heavy.score_from_ledger(
            entity_id="agent-1", ledger=ledger,
        )
        balanced = s_balanced.score_from_ledger(
            entity_id="agent-1", ledger=ledger,
        )
        assert heavy.composite_score is not None
        assert balanced.composite_score is not None
        # Heavy NPG weight pushes composite up (NPG-positive component is 1.0).
        assert heavy.composite_score > balanced.composite_score

    def test_custom_thresholds_honored(self) -> None:
        # Very strict trusted threshold — even a perfect score doesn't trip
        # it if we set it to 1.0 and there's any inversion intercept.
        s = SubstrateCoherenceTrustScorer(
            config=TrustScorerConfig(
                min_records=1,
                trusted_threshold=1.0,
                drifting_threshold=0.5,
            ),
        )
        ledger = _trusted_ledger(count=3)
        result = s.score_from_ledger(entity_id="agent-1", ledger=ledger)
        assert result.composite_score == 1.0
        # composite == trusted_threshold qualifies as TRUSTED.
        assert result.verdict is TrustVerdict.TRUSTED

# -----------------------------
# Rationale and surface
# -----------------------------

class TestRationaleAndSurface:
    def test_rationale_contains_composite(self) -> None:
        s = _scorer()
        result = s.score_from_ledger(
            entity_id="agent-1", ledger=_trusted_ledger(count=10),
        )
        assert "composite=" in result.rationale

    def test_rationale_contains_components(self) -> None:
        s = _scorer()
        result = s.score_from_ledger(
            entity_id="agent-1", ledger=_trusted_ledger(count=10),
        )
        assert "npg+" in result.rationale
        assert "prod" in result.rationale
        assert "intercept_inv" in result.rationale
        assert "sin_inv" in result.rationale
        assert "inversion_inv" in result.rationale

    def test_insufficient_rationale_explains(self) -> None:
        s = _scorer()
        result = s.score(entity_id="agent-1", records=())
        assert "insufficient" in result.rationale.lower()

    def test_trust_score_is_frozen(self) -> None:
        s = _scorer()
        result = s.score(entity_id="agent-1", records=())
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.verdict = TrustVerdict.TRUSTED

    def test_components_is_frozen(self) -> None:
        s = _scorer()
        result = s.score_from_ledger(
            entity_id="agent-1", ledger=_trusted_ledger(count=10),
        )
        assert result.components is not None
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.components.npg_positive_rate = 0.0

    def test_score_returns_trust_score_type(self) -> None:
        s = _scorer()
        result = s.score(entity_id="agent-1", records=())
        assert isinstance(result, TrustScore)

    def test_components_type_is_correct(self) -> None:
        s = _scorer()
        result = s.score_from_ledger(
            entity_id="agent-1", ledger=_trusted_ledger(count=10),
        )
        assert isinstance(result.components, TrustScoreComponents)

# -----------------------------
# Composition with aggregator
# -----------------------------

class TestComposition:
    def test_entity_id_carried_through(self) -> None:
        s = _scorer()
        result = s.score_from_ledger(
            entity_id="custom-entity-XYZ",
            ledger=_trusted_ledger(count=10),
        )
        assert result.entity_id == "custom-entity-XYZ"

    def test_record_count_carried_through(self) -> None:
        s = _scorer()
        result = s.score_from_ledger(
            entity_id="agent-1", ledger=_trusted_ledger(count=7),
        )
        assert result.record_count == 7

    def test_composite_in_unit_interval(self) -> None:
        s = _scorer()
        for ledger in (
            _trusted_ledger(count=10),
            _drifting_ledger(count=10),
        ):
            result = s.score_from_ledger(
                entity_id="agent-1", ledger=ledger,
            )
            assert result.composite_score is not None
            assert 0.0 <= result.composite_score <= 1.0
