"""Tests for BehavioralTellDetector."""
from __future__ import annotations

import pytest

from substrate.tells.behavioral_tell_detector import (
    DEFAULT_BEHAVIORAL_TELL_CONFIG,
    BehavioralTellConfig,
    BehavioralTellDetector,
    TellCategory,
    TellStrength,
    TextObservation,
)

def _obs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    seq: int = 0,
    *,
    speaker: str = "alice",
    latency: float = 0.0,
    hesitation: int = 0,
    evasion: int = 0,
    defensiveness: int = 0,
    modal: int = 0,
    inconsistency: float = 0.0,
    mismatch: float | None = None,
) -> TextObservation:
    return TextObservation(
        speaker_id=speaker,
        sequence=seq,
        response_latency_ms=latency,
        hesitation_marker_count=hesitation,
        evasion_marker_count=evasion,
        defensiveness_marker_count=defensiveness,
        modal_contradiction_count=modal,
        narrative_inconsistency_score=inconsistency,
        verbal_nonverbal_mismatch_score=mismatch,
    )

class TestTextObservationValidation:
    def test_round_trip(self) -> None:
        o = _obs()
        assert o.speaker_id == "alice"

    def test_empty_speaker_rejected(self) -> None:
        with pytest.raises(ValueError, match="speaker_id"):
            _obs(speaker="")

    def test_negative_seq_rejected(self) -> None:
        with pytest.raises(ValueError, match="sequence"):
            _obs(seq=-1)

    def test_negative_latency_rejected(self) -> None:
        with pytest.raises(ValueError, match="response_latency_ms"):
            _obs(latency=-1.0)

    @pytest.mark.parametrize(
        "kwargs,match",
        [
            ({"hesitation": -1}, "hesitation_marker_count"),
            ({"evasion": -1}, "evasion_marker_count"),
            ({"defensiveness": -1}, "defensiveness_marker_count"),
            ({"modal": -1}, "modal_contradiction_count"),
        ],
    )
    def test_negative_counts_rejected(
        self, kwargs: dict, match: str,
    ) -> None:
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)

    def test_bad_inconsistency_score(self) -> None:
        with pytest.raises(ValueError, match="narrative_inconsistency_score"):
            _obs(inconsistency=1.5)

    def test_bad_mismatch_score(self) -> None:
        with pytest.raises(ValueError, match="verbal_nonverbal_mismatch_score"):
            _obs(mismatch=1.5)

class TestConfig:
    def test_defaults_ok(self) -> None:
        cfg = BehavioralTellConfig()
        assert cfg.hesitation_count_weak < cfg.hesitation_count_strong

    @pytest.mark.parametrize(
        "kwargs,match",
        [
            ({"hesitation_count_weak": 5, "hesitation_count_moderate": 4},
             "hesitation_count"),
            ({"inconsistency_strong": 0.4}, "inconsistency"),
            ({"latency_ms_strong": 100.0}, "latency_ms_moderate"),
        ],
    )
    def test_bad_thresholds(self, kwargs: dict, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            BehavioralTellConfig(**kwargs)

class TestNoTells:
    def test_clean_observation_no_tells(self) -> None:
        out = BehavioralTellDetector().detect(_obs())
        assert out.tells == ()
        assert out.max_strength is TellStrength.NONE
        assert "no tells" in out.rationale

class TestHesitation:
    def setup_method(self) -> None:
        self.d = BehavioralTellDetector()

    def test_one_marker_weak(self) -> None:
        out = self.d.detect(_obs(hesitation=1))
        tell = out.by_category(TellCategory.HESITATION)
        assert tell is not None
        assert tell.strength is TellStrength.WEAK

    def test_three_markers_moderate(self) -> None:
        out = self.d.detect(_obs(hesitation=3))
        tell = out.by_category(TellCategory.HESITATION)
        assert tell is not None
        assert tell.strength is TellStrength.MODERATE

    def test_six_markers_strong(self) -> None:
        out = self.d.detect(_obs(hesitation=10))
        tell = out.by_category(TellCategory.HESITATION)
        assert tell is not None
        assert tell.strength is TellStrength.STRONG

class TestNervousness:
    def setup_method(self) -> None:
        self.d = BehavioralTellDetector()

    def test_no_latency_no_hesitation_none(self) -> None:
        out = self.d.detect(_obs())
        assert out.by_category(TellCategory.NERVOUSNESS) is None

    def test_high_latency_alone(self) -> None:
        out = self.d.detect(_obs(latency=6000))
        tell = out.by_category(TellCategory.NERVOUSNESS)
        assert tell is not None

    def test_latency_plus_hesitation_combines(self) -> None:
        out = self.d.detect(_obs(latency=3000, hesitation=3))
        tell = out.by_category(TellCategory.NERVOUSNESS)
        assert tell is not None
        assert tell.strength is TellStrength.MODERATE

class TestEvasion:
    def setup_method(self) -> None:
        self.d = BehavioralTellDetector()

    def test_one_marker_weak(self) -> None:
        out = self.d.detect(_obs(evasion=1))
        tell = out.by_category(TellCategory.EVASION)
        assert tell is not None
        assert tell.strength is TellStrength.WEAK

    def test_strong(self) -> None:
        out = self.d.detect(_obs(evasion=10))
        tell = out.by_category(TellCategory.EVASION)
        assert tell is not None
        assert tell.strength is TellStrength.STRONG

class TestDefensiveness:
    def setup_method(self) -> None:
        self.d = BehavioralTellDetector()

    def test_moderate(self) -> None:
        out = self.d.detect(_obs(defensiveness=3))
        tell = out.by_category(TellCategory.DEFENSIVENESS)
        assert tell is not None
        assert tell.strength is TellStrength.MODERATE

class TestInconsistentNarrative:
    def setup_method(self) -> None:
        self.d = BehavioralTellDetector()

    def test_weak(self) -> None:
        out = self.d.detect(_obs(inconsistency=0.35))
        tell = out.by_category(TellCategory.INCONSISTENT_NARRATIVE)
        assert tell is not None
        assert tell.strength is TellStrength.WEAK

    def test_strong(self) -> None:
        out = self.d.detect(_obs(inconsistency=0.9))
        tell = out.by_category(TellCategory.INCONSISTENT_NARRATIVE)
        assert tell is not None
        assert tell.strength is TellStrength.STRONG

class TestIndecision:
    def setup_method(self) -> None:
        self.d = BehavioralTellDetector()

    def test_moderate(self) -> None:
        out = self.d.detect(_obs(modal=2))
        tell = out.by_category(TellCategory.INDECISION)
        assert tell is not None
        assert tell.strength is TellStrength.MODERATE

class TestVerbalNonverbalMismatch:
    def setup_method(self) -> None:
        self.d = BehavioralTellDetector()

    def test_none_when_score_absent(self) -> None:
        out = self.d.detect(_obs(mismatch=None))
        assert out.by_category(TellCategory.VERBAL_NONVERBAL_MISMATCH) is None

    def test_moderate(self) -> None:
        out = self.d.detect(_obs(mismatch=0.55))
        tell = out.by_category(TellCategory.VERBAL_NONVERBAL_MISMATCH)
        assert tell is not None
        assert tell.strength is TellStrength.MODERATE

class TestLying:
    def setup_method(self) -> None:
        self.d = BehavioralTellDetector()

    def test_no_lying_when_evasion_weak(self) -> None:
        out = self.d.detect(
            _obs(evasion=1, inconsistency=0.6, latency=3000),
        )
        assert out.by_category(TellCategory.LYING) is None

    def test_no_lying_when_narrative_weak(self) -> None:
        out = self.d.detect(
            _obs(evasion=3, inconsistency=0.3, latency=3000),
        )
        assert out.by_category(TellCategory.LYING) is None

    def test_no_lying_when_latency_low(self) -> None:
        out = self.d.detect(
            _obs(evasion=3, inconsistency=0.6, latency=500),
        )
        assert out.by_category(TellCategory.LYING) is None

    def test_lying_composite_strong(self) -> None:
        out = self.d.detect(
            _obs(evasion=5, inconsistency=0.9, latency=6000),
        )
        tell = out.by_category(TellCategory.LYING)
        assert tell is not None
        assert tell.strength is TellStrength.STRONG

class TestReportProperties:
    def test_multiple_tells_max_strength(self) -> None:
        out = BehavioralTellDetector().detect(
            _obs(hesitation=3, evasion=10, modal=2),
        )
        assert out.max_strength is TellStrength.STRONG

    def test_default_config_singleton(self) -> None:
        assert (
            DEFAULT_BEHAVIORAL_TELL_CONFIG.hesitation_count_weak == 1
        )
