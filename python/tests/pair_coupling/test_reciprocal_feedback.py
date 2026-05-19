"""Tests for ReciprocalFeedbackProtocol (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.pair_coupling.reciprocal_feedback import (
    Attestation,
    DEFAULT_RECIPROCAL_FEEDBACK_CONFIG,
    FeedbackVerdict,
    ReciprocalFeedbackInput,
    ReciprocalFeedbackProtocol,
)

def _attest(
    *,
    attester: str = "alice",
    target: str = "bob",
    age: float = 60.0,
    evidence: float = 0.8,
) -> Attestation:
    return Attestation(
        attester_entity_id=attester,
        target_entity_id=target,
        submitted_age_seconds=age,
        evidence_trust_score=evidence,
    )

class TestAttestationValidation:
    def test_round_trip(self) -> None:
        a = _attest()
        assert a.evidence_trust_score == 0.8

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("attester", "", "attester_entity_id"),
            ("target", "", "target_entity_id"),
            ("age", -1.0, "submitted_age_seconds"),
            ("evidence", 1.5, "evidence_trust_score"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _attest(**kwargs)  # type: ignore[arg-type]

    def test_self_attestation_rejected(self) -> None:
        with pytest.raises(ValueError, match="differ"):
            _attest(attester="x", target="x")

class TestInputValidation:
    def test_a_attesting_must_be_from_a(self) -> None:
        with pytest.raises(
            ValueError, match="a_attesting_b",
        ):
            ReciprocalFeedbackInput(
                coupling_id="p", pole_a_id="alice", pole_b_id="bob",
                a_attesting_b=_attest(
                    attester="charlie", target="bob",
                ),
                b_attesting_a=None,
            )

    def test_b_attesting_must_be_from_b(self) -> None:
        with pytest.raises(
            ValueError, match="b_attesting_a",
        ):
            ReciprocalFeedbackInput(
                coupling_id="p", pole_a_id="alice", pole_b_id="bob",
                a_attesting_b=None,
                b_attesting_a=_attest(
                    attester="alice", target="bob",
                ),
            )

class TestProtocol:
    def setup_method(self) -> None:
        self.p = ReciprocalFeedbackProtocol()

    def _input(
        self,
        *,
        a: Attestation | None = None,
        b: Attestation | None = None,
    ) -> ReciprocalFeedbackInput:
        return ReciprocalFeedbackInput(
            coupling_id="p", pole_a_id="alice", pole_b_id="bob",
            a_attesting_b=a, b_attesting_a=b,
        )

    def test_no_feedback(self) -> None:
        out = self.p.evaluate(self._input())
        assert out.verdict is FeedbackVerdict.NO_FEEDBACK

    def test_asymmetric_missing(self) -> None:
        out = self.p.evaluate(self._input(
            a=_attest(attester="alice", target="bob"),
        ))
        assert (
            out.verdict is FeedbackVerdict.ASYMMETRIC_MISSING_POLE
        )

    def test_symmetric_healthy(self) -> None:
        out = self.p.evaluate(self._input(
            a=_attest(attester="alice", target="bob"),
            b=_attest(attester="bob", target="alice"),
        ))
        assert out.verdict is FeedbackVerdict.SYMMETRIC_HEALTHY
        assert out.healthy

    def test_stale_feedback(self) -> None:
        out = self.p.evaluate(self._input(
            a=_attest(attester="alice", target="bob", age=10000.0),
            b=_attest(attester="bob", target="alice", age=10000.0),
        ))
        assert out.verdict is FeedbackVerdict.STALE_FEEDBACK

    def test_low_evidence_feedback(self) -> None:
        out = self.p.evaluate(self._input(
            a=_attest(attester="alice", target="bob", evidence=0.1),
            b=_attest(attester="bob", target="alice", evidence=0.9),
        ))
        assert out.verdict is FeedbackVerdict.LOW_EVIDENCE_FEEDBACK

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_RECIPROCAL_FEEDBACK_CONFIG.max_attestation_age_seconds
            == 3600.0
        )
