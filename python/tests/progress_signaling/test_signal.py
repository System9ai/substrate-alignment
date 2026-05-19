"""Tests for SubstrateProgressSignal + SubstrateEvidence (Plan 3art 30)."""
from __future__ import annotations

import pytest

from substrate.progress_signaling.signal import (
    SUBSTRATE_SIGNAL_TYPES,
    SubstrateEvidence,
    SubstrateProgressSignal,
    SubstrateSignalType,
)

def _evidence(
    *,
    eid: str = "e-1",
    kind: str = "audit_pass",
    weight: float = 0.5,
    rationale: str = "ok",
) -> SubstrateEvidence:
    return SubstrateEvidence(
        evidence_id=eid, evidence_kind=kind,
        weight=weight, rationale=rationale,
    )

def _signal(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    sid: str = "s-1",
    target: str = "agent-1",
    trajectory: str = "t-1",
    kind: SubstrateSignalType = SubstrateSignalType.PROGRESS_MARKER,
    quantity: float = 1.0,
    evidence: tuple[SubstrateEvidence, ...] = (),
    position: float = 0.5,
    epoch: float = 0.0,
) -> SubstrateProgressSignal:
    return SubstrateProgressSignal(
        signal_id=sid, target_entity_id=target, trajectory_id=trajectory,
        signal_type=kind, progress_quantity=quantity,
        evidence=evidence,
        resistance_band_position=position,
        emitted_at_epoch=epoch, metadata={},
    )

class TestEvidence:
    def test_round_trip(self) -> None:
        e = _evidence()
        assert e.weight == 0.5

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("eid", "", "evidence_id"),
            ("kind", "", "evidence_kind"),
            ("weight", -0.1, "weight"),
            ("weight", 1.5, "weight"),
        ],
    )
    def test_bad(self, field: str, value: object, match: str) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _evidence(**kwargs)  # type: ignore[arg-type]

class TestSignal:
    def test_round_trip(self) -> None:
        s = _signal(evidence=(_evidence(),))
        assert s.has_evidence
        assert s.total_evidence_weight == 0.5

    def test_empty_evidence_allowed(self) -> None:
        s = _signal()
        assert not s.has_evidence
        assert s.total_evidence_weight == 0.0

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("sid", "", "signal_id"),
            ("target", "", "target_entity_id"),
            ("trajectory", "", "trajectory_id"),
            ("quantity", -1.0, "progress_quantity"),
            ("position", 1.5, "resistance_band_position"),
            ("epoch", -1.0, "emitted_at_epoch"),
        ],
    )
    def test_bad(self, field: str, value: object, match: str) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _signal(**kwargs)  # type: ignore[arg-type]

class TestEnumSurface:
    def test_signal_types_constant(self) -> None:
        assert len(SUBSTRATE_SIGNAL_TYPES) == 5

    def test_signal_types_match_enum(self) -> None:
        assert SUBSTRATE_SIGNAL_TYPES == {
            t.value for t in SubstrateSignalType
        }
