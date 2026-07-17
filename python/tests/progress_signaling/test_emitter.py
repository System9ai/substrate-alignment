"""Tests for ProgressSignalEmitter."""
from __future__ import annotations

import pytest

from substrate.progress_signaling.emitter import (
    DEFAULT_PROGRESS_EMITTER_CONFIG,
    EmissionVerdict,
    ProgressEmitterConfig,
    ProgressSignalEmitter,
)
from substrate.progress_signaling.signal import (
    SubstrateEvidence,
    SubstrateSignalType,
)
from substrate.resistance_band import (
    DEFAULT_CONFIG,
    ResistanceBandAssessment,
    ResistanceBandClassification,
    assess,
)

def _evidence(weight: float = 0.6) -> SubstrateEvidence:
    return SubstrateEvidence(
        evidence_id="e-1", evidence_kind="audit_pass",
        weight=weight, rationale="ok",
    )

def _assessment(utilization: float) -> ResistanceBandAssessment:
    return assess(
        utilization=utilization, config=DEFAULT_CONFIG,
    )

class TestConfig:
    def test_defaults(self) -> None:
        c = ProgressEmitterConfig()
        assert c.min_evidence_count == 1

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("min_evidence_weight", 0.0, "min_evidence_weight"),
            ("min_evidence_weight", 1.5, "min_evidence_weight"),
            ("min_evidence_count", 0, "min_evidence_count"),
        ],
    )
    def test_bad(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            ProgressEmitterConfig(**{field: value})

class TestEmissionLogic:
    def setup_method(self) -> None:
        self.e = ProgressSignalEmitter()

    def test_emit_when_in_band_with_evidence(self) -> None:
        d = self.e.evaluate(
            signal_id="s-1", target_entity_id="agent-1",
            trajectory_id="t-1",
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            progress_quantity=1.0,
            evidence=(_evidence(),),
            resistance=_assessment(0.35),
            emitted_at_epoch=100.0,
        )
        assert d.verdict is EmissionVerdict.EMIT
        assert d.emitted
        assert d.signal is not None
        assert d.signal.target_entity_id == "agent-1"

    def test_skip_no_evidence(self) -> None:
        d = self.e.evaluate(
            signal_id="s-1", target_entity_id="agent-1",
            trajectory_id="t-1",
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            progress_quantity=1.0,
            evidence=(),
            resistance=_assessment(0.35),
            emitted_at_epoch=100.0,
        )
        assert d.verdict is EmissionVerdict.SKIP_INSUFFICIENT_EVIDENCE
        assert not d.emitted

    def test_skip_low_weight(self) -> None:
        d = self.e.evaluate(
            signal_id="s-1", target_entity_id="agent-1",
            trajectory_id="t-1",
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            progress_quantity=1.0,
            evidence=(_evidence(weight=0.05),),
            resistance=_assessment(0.35),
            emitted_at_epoch=100.0,
        )
        assert d.verdict is EmissionVerdict.SKIP_INSUFFICIENT_EVIDENCE

    def test_skip_when_stressed(self) -> None:
        d = self.e.evaluate(
            signal_id="s-1", target_entity_id="agent-1",
            trajectory_id="t-1",
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            progress_quantity=1.0,
            evidence=(_evidence(),),
            resistance=_assessment(0.9),
            emitted_at_epoch=100.0,
        )
        assert d.verdict is EmissionVerdict.SKIP_OUTSIDE_BAND

    def test_resistance_at_stressed_class(self) -> None:
        a = _assessment(0.9)
        assert a.classification is ResistanceBandClassification.STRESSED

    def test_suppress_when_stressed_can_disable(self) -> None:
        e = ProgressSignalEmitter(
            config=ProgressEmitterConfig(suppress_when_stressed=False),
        )
        d = e.evaluate(
            signal_id="s-1", target_entity_id="agent-1",
            trajectory_id="t-1",
            signal_type=SubstrateSignalType.PROGRESS_MARKER,
            progress_quantity=1.0,
            evidence=(_evidence(),),
            resistance=_assessment(0.9),
            emitted_at_epoch=100.0,
        )
        assert d.verdict is EmissionVerdict.EMIT

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert DEFAULT_PROGRESS_EMITTER_CONFIG.min_evidence_count == 1
