"""Tests for EgoIdentityEmergenceVerifier."""
from __future__ import annotations

import pytest

from substrate.identity.ego_emergence_verifier import (
    DEFAULT_EGO_EMERGENCE_CONFIG,
    EgoEmergenceConfig,
    EgoIdentityEmergenceVerifier,
    IdentitySignal,
    IdentityVerdict,
    NodeIdentityObservation,
)

def _obs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    node_id: str = "node-alpha",
    window_start: int = 0,
    window_end: int = 100,
    crypto_stable: bool = True,
    coherence: float = 0.8,
    consistency: float = 0.8,
    replacements: int = 0,
    continuity: bool = False,
    recognition: int = 5,
    misalignments: int = 0,
) -> NodeIdentityObservation:
    return NodeIdentityObservation(
        node_id=node_id,
        window_start=window_start,
        window_end=window_end,
        cryptographic_identity_stable=crypto_stable,
        cell_coherence_score=coherence,
        behavioral_consistency_score=consistency,
        cell_replacements_count=replacements,
        cell_replacements_continuity_preserved=continuity,
        external_recognition_count=recognition,
        misalignment_event_count=misalignments,
    )

class TestObservationValidation:
    def test_round_trip(self) -> None:
        o = _obs()
        assert o.node_id == "node-alpha"
        assert o.window_size == 100

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("node_id", "", "node_id"),
            ("coherence", 1.5, "cell_coherence_score"),
            ("consistency", -0.1, "behavioral_consistency_score"),
            ("replacements", -1, "cell_replacements_count"),
            ("recognition", -1, "external_recognition_count"),
            ("misalignments", -1, "misalignment_event_count"),
        ],
    )
    def test_bad_values(self, field: str, value: object, match: str) -> None:
        kwargs = {"node_id": "n"}
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)

    def test_window_end_before_start_rejected(self) -> None:
        with pytest.raises(ValueError, match="window_end"):
            _obs(window_start=100, window_end=50)

    def test_continuity_without_replacements_rejected(self) -> None:
        with pytest.raises(ValueError, match="continuity_preserved"):
            _obs(replacements=0, continuity=True)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = EgoEmergenceConfig()
        assert cfg.emerged_min_signals == 5

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("cell_coherence_min", 0.0, "cell_coherence_min"),
            ("behavioral_consistency_min", 0.0, "behavioral_consistency_min"),
            ("external_recognition_min", 0, "external_recognition_min"),
            ("min_window_size", 0, "min_window_size"),
            ("emerged_min_signals", 6, "emerged_min_signals"),
            ("misalignment_event_max", -1, "misalignment_event_max"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            EgoEmergenceConfig(**{field: value})

class TestVerifierFlow:
    def setup_method(self) -> None:
        self.v = EgoIdentityEmergenceVerifier()

    def test_insufficient_window(self) -> None:
        out = self.v.verify(_obs(window_end=10))
        assert out.verdict is IdentityVerdict.INSUFFICIENT_DATA
        assert out.findings == ()

    def test_too_many_misalignments_short_circuits(self) -> None:
        out = self.v.verify(_obs(misalignments=10))
        assert out.verdict is IdentityVerdict.INCOHERENT

    def test_all_signals_satisfied_emerged(self) -> None:
        out = self.v.verify(_obs())
        # Default: crypto stable, coherence=0.8, consistency=0.8,
        # no replacements (vacuous continuity), recognition=5, no misalignments
        assert out.emerged
        for signal in IdentitySignal:
            finding = out.by_signal(signal)
            assert finding is not None
            assert finding.satisfied

class TestSignalSpecificEvaluation:
    def setup_method(self) -> None:
        self.v = EgoIdentityEmergenceVerifier()

    def test_crypto_unstable_fails(self) -> None:
        out = self.v.verify(_obs(crypto_stable=False))
        crypto = out.by_signal(IdentitySignal.CRYPTOGRAPHIC_PERSISTENCE)
        assert crypto is not None and not crypto.satisfied

    def test_low_coherence_fails(self) -> None:
        out = self.v.verify(_obs(coherence=0.3))
        coh = out.by_signal(IdentitySignal.CELL_COHERENCE)
        assert coh is not None and not coh.satisfied

    def test_low_consistency_fails(self) -> None:
        out = self.v.verify(_obs(consistency=0.3))
        beh = out.by_signal(IdentitySignal.BEHAVIORAL_CONSISTENCY)
        assert beh is not None and not beh.satisfied

    def test_low_recognition_fails(self) -> None:
        out = self.v.verify(_obs(recognition=1))
        rec = out.by_signal(IdentitySignal.EXTERNAL_RECOGNITION)
        assert rec is not None and not rec.satisfied

    def test_continuity_with_replacements_preserved(self) -> None:
        out = self.v.verify(_obs(replacements=3, continuity=True))
        cont = out.by_signal(IdentitySignal.CONTINUITY_ACROSS_REPLACEMENT)
        assert cont is not None and cont.satisfied

    def test_continuity_with_replacements_broken(self) -> None:
        out = self.v.verify(_obs(replacements=3, continuity=False))
        cont = out.by_signal(IdentitySignal.CONTINUITY_ACROSS_REPLACEMENT)
        assert cont is not None and not cont.satisfied

    def test_continuity_vacuous_no_replacements(self) -> None:
        out = self.v.verify(_obs(replacements=0))
        cont = out.by_signal(IdentitySignal.CONTINUITY_ACROSS_REPLACEMENT)
        assert cont is not None and cont.satisfied

class TestAggregateVerdict:
    def setup_method(self) -> None:
        self.v = EgoIdentityEmergenceVerifier()

    def test_emerging_at_three_signals(self) -> None:
        # 3/5 satisfied: crypto + coherence + recognition; consistency low,
        # replacements with broken continuity
        out = self.v.verify(_obs(
            consistency=0.3, replacements=3, continuity=False,
        ))
        assert out.verdict is IdentityVerdict.EMERGING

    def test_incoherent_at_two_signals(self) -> None:
        out = self.v.verify(_obs(
            crypto_stable=False, coherence=0.3, consistency=0.3,
            recognition=0,
        ))
        assert out.incoherent

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_EGO_EMERGENCE_CONFIG.emerged_min_signals == 5
