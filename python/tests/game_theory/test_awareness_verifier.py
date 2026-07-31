"""Tests for GameTheoreticAwarenessVerifier."""
from __future__ import annotations

import pytest

from substrate.game_theory.awareness_verifier import (
    DEFAULT_AWARENESS_VERIFIER_CONFIG,
    AgentBehaviorRecord,
    AwarenessAssessment,
    AwarenessMode,
    AwarenessSignal,
    AwarenessVerifierConfig,
    GameTheoreticAwarenessVerifier,
)

def _record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    seq: int,
    *,
    classified: bool = True,
    cycle: bool = True,
    npg: bool = True,
    inversion: bool | None = True,
    reciprocal: bool = True,
    folk: bool = True,
    vocab: bool = True,
) -> AgentBehaviorRecord:
    return AgentBehaviorRecord(
        sequence=seq,
        decision_id=f"d{seq}",
        classified_game_theoretically=classified,
        identified_cycle_structure=cycle,
        applied_npg_test=npg,
        detected_inversion_when_present=inversion,
        used_reciprocal_protocol=reciprocal,
        checked_folk_conditions=folk,
        used_substrate_vocabulary=vocab,
    )

class TestAgentBehaviorRecord:
    def test_round_trip(self) -> None:
        rec = _record(seq=0)
        assert rec.sequence == 0
        assert rec.decision_id == "d0"

    def test_negative_sequence_rejected(self) -> None:
        with pytest.raises(ValueError, match="sequence"):
            _record(seq=-1)

    def test_empty_decision_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="decision_id"):
            AgentBehaviorRecord(
                sequence=0,
                decision_id="",
                classified_game_theoretically=True,
                identified_cycle_structure=True,
                applied_npg_test=True,
                detected_inversion_when_present=None,
                used_reciprocal_protocol=True,
                checked_folk_conditions=True,
                used_substrate_vocabulary=True,
            )

class TestAwarenessVerifierConfig:
    def test_defaults(self) -> None:
        cfg = AwarenessVerifierConfig()
        assert cfg.signal_satisfaction_threshold == 0.7

    def test_bad_threshold(self) -> None:
        with pytest.raises(ValueError, match="signal_satisfaction_threshold"):
            AwarenessVerifierConfig(signal_satisfaction_threshold=0.0)

    def test_mode_3_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="mode_3_min_satisfied_signals"):
            AwarenessVerifierConfig(mode_3_min_satisfied_signals=0)

    def test_mode_2_must_be_below_mode_3(self) -> None:
        with pytest.raises(ValueError, match="mode_2_min_satisfied_signals"):
            AwarenessVerifierConfig(
                mode_3_min_satisfied_signals=4,
                mode_2_min_satisfied_signals=4,
            )

    def test_min_history(self) -> None:
        with pytest.raises(ValueError, match="min_history_for_assessment"):
            AwarenessVerifierConfig(min_history_for_assessment=0)

class TestEmptyOrShortHistory:
    def test_empty_history_insufficient(self) -> None:
        v = GameTheoreticAwarenessVerifier()
        out = v.verify("alice", ())
        assert out.mode is AwarenessMode.INSUFFICIENT_DATA
        assert out.findings == ()

    def test_short_history_insufficient(self) -> None:
        v = GameTheoreticAwarenessVerifier()
        out = v.verify("alice", (_record(seq=0),))
        assert out.mode is AwarenessMode.INSUFFICIENT_DATA

    def test_empty_agent_id(self) -> None:
        v = GameTheoreticAwarenessVerifier()
        with pytest.raises(ValueError, match="agent_id"):
            v.verify("", ())

class TestSignalScoring:
    def setup_method(self) -> None:
        self.v = GameTheoreticAwarenessVerifier()

    def test_all_signals_satisfied_mode_3(self) -> None:
        behavior = tuple(_record(seq=i) for i in range(5))
        out: AwarenessAssessment = self.v.verify("alice", behavior)
        assert out.mode is AwarenessMode.MODE_3
        assert out.is_mode_3
        for sig in AwarenessSignal:
            finding = out.by_signal(sig)
            assert finding is not None and finding.satisfied

    def test_all_signals_missing_mode_1(self) -> None:
        behavior = tuple(
            _record(
                seq=i,
                classified=False,
                cycle=False,
                npg=False,
                inversion=False,
                reciprocal=False,
                folk=False,
                vocab=False,
            )
            for i in range(5)
        )
        out = self.v.verify("alice", behavior)
        assert out.mode is AwarenessMode.MODE_1

    def test_partial_mode_2(self) -> None:
        # 4 signals satisfied = MODE_2 (>= mode_2_min=3, < mode_3_min=6)
        records = tuple(
            _record(
                seq=i,
                classified=True,
                cycle=True,
                npg=True,
                inversion=True,
                reciprocal=False,
                folk=False,
                vocab=False,
            )
            for i in range(5)
        )
        out = self.v.verify("alice", records)
        assert out.mode is AwarenessMode.MODE_2

    def test_inversion_vacuous_when_no_inversion_present(self) -> None:
        behavior = tuple(
            _record(seq=i, inversion=None) for i in range(5)
        )
        out = self.v.verify("alice", behavior)
        finding = out.by_signal(AwarenessSignal.INVERSION_DETECTED)
        assert finding is not None
        assert finding.satisfied
        assert finding.sample_size == 0

    def test_inversion_missed_unsatisfied(self) -> None:
        behavior = tuple(
            _record(seq=i, inversion=False) for i in range(5)
        )
        out = self.v.verify("alice", behavior)
        finding = out.by_signal(AwarenessSignal.INVERSION_DETECTED)
        assert finding is not None
        assert not finding.satisfied

    def test_threshold_boundary(self) -> None:
        # 7 records, 5 with vocab=True → rate=0.714 > 0.7 → satisfied
        # 7 records, 4 with vocab=True → rate=0.571 < 0.7 → unsatisfied
        below = tuple(
            _record(seq=i, vocab=i < 4) for i in range(7)
        )
        out = self.v.verify("alice", below)
        finding = out.by_signal(AwarenessSignal.SUBSTRATE_VOCABULARY)
        assert finding is not None
        assert not finding.satisfied
        above = tuple(
            _record(seq=i, vocab=i < 5) for i in range(7)
        )
        out = self.v.verify("alice", above)
        finding = out.by_signal(AwarenessSignal.SUBSTRATE_VOCABULARY)
        assert finding is not None
        assert finding.satisfied

class TestMissingSignals:
    def test_missing_signals_reported(self) -> None:
        v = GameTheoreticAwarenessVerifier()
        records = tuple(
            _record(seq=i, npg=False, vocab=False) for i in range(5)
        )
        out = v.verify("alice", records)
        missing = out.missing_signals()
        assert AwarenessSignal.NPG_APPLIED in missing
        assert AwarenessSignal.SUBSTRATE_VOCABULARY in missing
        assert AwarenessSignal.GAME_CLASSIFICATION not in missing

    def test_rationale_includes_mode(self) -> None:
        v = GameTheoreticAwarenessVerifier()
        records = tuple(_record(seq=i) for i in range(5))
        out = v.verify("alice", records)
        assert "mode=" in out.rationale
        assert AwarenessMode.MODE_3.value in out.rationale

    def test_default_config_singleton(self) -> None:
        cfg = DEFAULT_AWARENESS_VERIFIER_CONFIG
        assert cfg.signal_satisfaction_threshold == 0.7
