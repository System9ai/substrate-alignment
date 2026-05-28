"""Unit tests for the evidence-grade composer (spec v0.2.0).

Pins each clause of ``spec/evidence-grade.md`` § 3 with at least one
test. Pure-logic only — no DAO, no LLM, no network.
"""
from __future__ import annotations

import math

import pytest

from substrate.evidence_grade.composer import (
    DEFAULT_CONFIG,
    EVIDENCE_GRADES,
    EvidenceAttestation,
    EvidenceComposition,
    EvidenceGrade,
    EvidenceGradeConfig,
    SubstrateStateClaim,
    compose_evidence_grade,
)


_NOW = 1_700_000_000.0  # arbitrary epoch reference for tests
_HALF_LIFE = DEFAULT_CONFIG.decay_half_life_seconds
_DECAY_THRESHOLD = _HALF_LIFE * DEFAULT_CONFIG.decay_multiplier


def _att(
    source: str,
    *,
    age_seconds: float = 0.0,
    provenance_verified: bool = False,
) -> EvidenceAttestation:
    return EvidenceAttestation(
        source_id=source,
        observed_at_epoch_seconds=_NOW - age_seconds,
        provenance_verified=provenance_verified,
    )


# ── EvidenceGrade ordering (spec § 2.1) ──────────────────────────


class TestGradeOrdering:

    def test_ordering_constants_correct(self) -> None:
        assert EVIDENCE_GRADES == (
            EvidenceGrade.UNVERIFIED_HEARSAY,
            EvidenceGrade.CORROBORATED,
            EvidenceGrade.ATTESTED,
            EvidenceGrade.DOCUMENTED_CRYSTALLIZED,
        )

    def test_ranks_are_monotone(self) -> None:
        ranks = [g.rank for g in EVIDENCE_GRADES]
        assert ranks == sorted(ranks)
        assert ranks == [0, 1, 2, 3]

    def test_serialised_form_matches_spec(self) -> None:
        # Spec § 2.1 requires exact strings.
        assert EvidenceGrade.UNVERIFIED_HEARSAY.value == "unverified_hearsay"
        assert EvidenceGrade.CORROBORATED.value == "corroborated"
        assert EvidenceGrade.ATTESTED.value == "attested"
        assert (
            EvidenceGrade.DOCUMENTED_CRYSTALLIZED.value
            == "documented_crystallized"
        )


# ── EvidenceAttestation validation (spec § 2.2) ──────────────────


class TestAttestationValidation:

    def test_empty_source_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="source_id"):
            EvidenceAttestation(
                source_id="",
                observed_at_epoch_seconds=_NOW,
                provenance_verified=False,
            )

    def test_nan_observed_at_rejected(self) -> None:
        with pytest.raises(ValueError, match="NaN"):
            EvidenceAttestation(
                source_id="src",
                observed_at_epoch_seconds=float("nan"),
                provenance_verified=False,
            )

    def test_attestation_is_frozen(self) -> None:
        a = _att("src")
        with pytest.raises(Exception):  # FrozenInstanceError subclasses AttributeError/TypeError  # pylint: disable=broad-exception-caught,broad-except
            a.source_id = "other"


# ── EvidenceComposition validation (spec § 2.3) ──────────────────


class TestCompositionValidation:

    def test_attestation_count_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError, match="attestation_count"):
            EvidenceComposition(
                grade=EvidenceGrade.UNVERIFIED_HEARSAY,
                attestation_count=-1,
                unique_source_count=0,
                provenance_verified_count=0,
                youngest_age_seconds=math.inf,
                oldest_age_seconds=math.inf,
                rationale="x",
            )

    def test_unique_sources_cannot_exceed_attestations(self) -> None:
        with pytest.raises(ValueError, match="unique_source_count"):
            EvidenceComposition(
                grade=EvidenceGrade.CORROBORATED,
                attestation_count=1,
                unique_source_count=2,
                provenance_verified_count=0,
                youngest_age_seconds=0.0,
                oldest_age_seconds=0.0,
                rationale="x",
            )

    def test_empty_rationale_rejected(self) -> None:
        with pytest.raises(ValueError, match="rationale"):
            EvidenceComposition(
                grade=EvidenceGrade.UNVERIFIED_HEARSAY,
                attestation_count=0,
                unique_source_count=0,
                provenance_verified_count=0,
                youngest_age_seconds=math.inf,
                oldest_age_seconds=math.inf,
                rationale="",
            )

    def test_negative_finite_age_rejected(self) -> None:
        with pytest.raises(ValueError, match="youngest_age"):
            EvidenceComposition(
                grade=EvidenceGrade.UNVERIFIED_HEARSAY,
                attestation_count=1,
                unique_source_count=1,
                provenance_verified_count=0,
                youngest_age_seconds=-1.0,
                oldest_age_seconds=0.0,
                rationale="x",
            )


# ── EvidenceGradeConfig validation (spec § 3.1) ─────────────────


class TestConfigValidation:

    def test_default_config_matches_spec(self) -> None:
        assert DEFAULT_CONFIG.decay_half_life_seconds == 7 * 24 * 3600
        assert DEFAULT_CONFIG.decay_multiplier == 2.0

    def test_zero_half_life_rejected(self) -> None:
        with pytest.raises(ValueError, match="decay_half_life"):
            EvidenceGradeConfig(
                decay_half_life_seconds=0.0,
                decay_multiplier=2.0,
            )

    def test_multiplier_below_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="decay_multiplier"):
            EvidenceGradeConfig(
                decay_half_life_seconds=100.0,
                decay_multiplier=0.5,
            )


# ── compose_evidence_grade algorithm (spec § 3) ──────────────────


class TestComposerAlgorithm:

    # Step 4: zero attestations → UNVERIFIED_HEARSAY with +inf ages.
    def test_empty_attestations(self) -> None:
        result = compose_evidence_grade([], now_epoch_seconds=_NOW)
        assert result.grade is EvidenceGrade.UNVERIFIED_HEARSAY
        assert result.attestation_count == 0
        assert math.isinf(result.youngest_age_seconds)
        assert math.isinf(result.oldest_age_seconds)
        assert "no attestations" in result.rationale

    # Step 5: ages computed and clamped.
    def test_ages_clamped_negative(self) -> None:
        # Attestation timestamped in the future relative to now.
        future = EvidenceAttestation(
            source_id="src",
            observed_at_epoch_seconds=_NOW + 10.0,
            provenance_verified=False,
        )
        result = compose_evidence_grade([future], now_epoch_seconds=_NOW)
        assert result.youngest_age_seconds == 0.0
        assert result.oldest_age_seconds == 0.0

    # Step 6 rule (a): UNVERIFIED_HEARSAY.
    def test_single_source_no_provenance(self) -> None:
        result = compose_evidence_grade(
            [_att("src")], now_epoch_seconds=_NOW
        )
        assert result.grade is EvidenceGrade.UNVERIFIED_HEARSAY
        assert result.attestation_count == 1
        assert result.unique_source_count == 1
        assert result.provenance_verified_count == 0

    def test_two_attestations_same_source_no_provenance(self) -> None:
        # Same-source attestations don't bump unique_source_count.
        result = compose_evidence_grade(
            [_att("src"), _att("src")], now_epoch_seconds=_NOW
        )
        assert result.grade is EvidenceGrade.UNVERIFIED_HEARSAY
        assert result.attestation_count == 2
        assert result.unique_source_count == 1

    # Step 6 rule (b): CORROBORATED.
    def test_two_unique_sources_no_provenance(self) -> None:
        result = compose_evidence_grade(
            [_att("src1"), _att("src2")], now_epoch_seconds=_NOW
        )
        assert result.grade is EvidenceGrade.CORROBORATED
        assert result.unique_source_count == 2

    # Step 6 rule (c): ATTESTED.
    def test_single_source_with_provenance(self) -> None:
        result = compose_evidence_grade(
            [_att("src", provenance_verified=True)],
            now_epoch_seconds=_NOW,
        )
        assert result.grade is EvidenceGrade.ATTESTED
        assert result.provenance_verified_count == 1

    def test_two_sources_with_provenance(self) -> None:
        result = compose_evidence_grade(
            [
                _att("src1", provenance_verified=True),
                _att("src2"),
            ],
            now_epoch_seconds=_NOW,
        )
        # Only 2 unique sources → not DOCUMENTED_CRYSTALLIZED yet.
        assert result.grade is EvidenceGrade.ATTESTED

    # Step 6 rule (d): DOCUMENTED_CRYSTALLIZED.
    def test_three_unique_sources_with_one_provenance(self) -> None:
        result = compose_evidence_grade(
            [
                _att("src1", provenance_verified=True),
                _att("src2"),
                _att("src3"),
            ],
            now_epoch_seconds=_NOW,
        )
        assert result.grade is EvidenceGrade.DOCUMENTED_CRYSTALLIZED
        assert result.unique_source_count == 3
        assert result.provenance_verified_count == 1

    def test_three_unique_sources_no_provenance_stays_corroborated(
        self,
    ) -> None:
        # Three sources without ANY verified provenance is NOT enough
        # for DOCUMENTED_CRYSTALLIZED (rule order matters).
        result = compose_evidence_grade(
            [_att("src1"), _att("src2"), _att("src3")],
            now_epoch_seconds=_NOW,
        )
        assert result.grade is EvidenceGrade.CORROBORATED

    # Step 7: decay downgrade.
    def test_decay_downgrades_when_youngest_too_old(self) -> None:
        old_age = _DECAY_THRESHOLD + 1.0
        result = compose_evidence_grade(
            [
                _att("src1", age_seconds=old_age, provenance_verified=True),
                _att("src2", age_seconds=old_age),
                _att("src3", age_seconds=old_age),
            ],
            now_epoch_seconds=_NOW,
        )
        # Base would be DOCUMENTED_CRYSTALLIZED; decay downgrades to ATTESTED.
        assert result.grade is EvidenceGrade.ATTESTED
        assert "downgraded" in result.rationale

    def test_decay_floor_at_unverified_hearsay(self) -> None:
        # Single source, ancient → already UNVERIFIED_HEARSAY; decay
        # rule is skipped (base grade has rank 0).
        result = compose_evidence_grade(
            [_att("src", age_seconds=_DECAY_THRESHOLD + 1.0)],
            now_epoch_seconds=_NOW,
        )
        assert result.grade is EvidenceGrade.UNVERIFIED_HEARSAY
        assert "downgraded" not in result.rationale

    def test_no_decay_when_youngest_recent(self) -> None:
        # Mixed-age attestations: youngest is fresh, oldest is ancient.
        # Algorithm uses YOUNGEST age, so no decay.
        result = compose_evidence_grade(
            [
                _att(
                    "src1",
                    age_seconds=_DECAY_THRESHOLD + 1.0,
                    provenance_verified=True,
                ),
                _att("src2", age_seconds=0.0),
                _att("src3", age_seconds=10.0),
            ],
            now_epoch_seconds=_NOW,
        )
        assert result.grade is EvidenceGrade.DOCUMENTED_CRYSTALLIZED
        assert "downgraded" not in result.rationale

    # Step 8: composition shape.
    def test_composition_records_full_counts(self) -> None:
        result = compose_evidence_grade(
            [
                _att("src1", provenance_verified=True),
                _att("src1", provenance_verified=True),
                _att("src2"),
            ],
            now_epoch_seconds=_NOW,
        )
        assert result.attestation_count == 3
        assert result.unique_source_count == 2
        assert result.provenance_verified_count == 2


# ── Spec §4 symmetry obligation note ─────────────────────────────


class TestSpecSymmetryObligation:

    def test_protocol_is_runtime_checkable(self) -> None:
        # Protocol § 2.4 must be runtime_checkable so host applications
        # can verify their records conform.
        class _Claim:
            claim_id = "c1"
            subject_entity_type = "user"
            subject_entity_id = "u1"

            @property
            def attestations(self) -> tuple[EvidenceAttestation, ...]:
                return ()

            @property
            def evidence_composition(self) -> EvidenceComposition:
                return EvidenceComposition(
                    grade=EvidenceGrade.UNVERIFIED_HEARSAY,
                    attestation_count=0,
                    unique_source_count=0,
                    provenance_verified_count=0,
                    youngest_age_seconds=math.inf,
                    oldest_age_seconds=math.inf,
                    rationale="empty",
                )

        assert isinstance(_Claim(), SubstrateStateClaim)


# ── Pure-logic property ──────────────────────────────────────────


class TestPureLogic:

    def test_deterministic_under_repeat(self) -> None:
        atts = [
            _att("src1", provenance_verified=True),
            _att("src2"),
            _att("src3"),
        ]
        a = compose_evidence_grade(atts, now_epoch_seconds=_NOW)
        b = compose_evidence_grade(atts, now_epoch_seconds=_NOW)
        assert a == b
