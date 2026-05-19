"""Tests for HeuristicInversionDetector"""
from __future__ import annotations

import pytest

from substrate.drift.drift_pattern_matcher import (
    DriftPattern,
    DriftPatternDetection,
    DriftPatternMatcher,
    DriftPatternReport,
)
from substrate.harness import (
    InversionDetector,
)
from substrate.inversion.inversion_detector import (
    DEFAULT_BASE_PAIR_CONFIDENCE,
    DEFAULT_INVERSION_PAIRS,
    HeuristicInversionDetector,
    InversionDetection,
    InversionPair,
    InversionPairFire,
)

# -----------------------------
# InversionPair validation
# -----------------------------

class TestInversionPairValidation:
    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name"):
            InversionPair(
                name="",
                framing_markers=("a",),
                action_markers=("b",),
            )

    def test_empty_framing_rejected(self) -> None:
        with pytest.raises(ValueError, match="framing_markers"):
            InversionPair(
                name="x",
                framing_markers=(),
                action_markers=("b",),
            )

    def test_empty_action_rejected(self) -> None:
        with pytest.raises(ValueError, match="action_markers"):
            InversionPair(
                name="x",
                framing_markers=("a",),
                action_markers=(),
            )

    def test_associated_sin_optional(self) -> None:
        pair = InversionPair(
            name="x",
            framing_markers=("a",),
            action_markers=("b",),
        )
        assert pair.associated_pattern is None

# -----------------------------
# Constructor validation
# -----------------------------

class TestConstructorValidation:
    def test_default_succeeds(self) -> None:
        det = HeuristicInversionDetector()
        assert det is not None

    def test_empty_pairs_rejected(self) -> None:
        with pytest.raises(ValueError, match="inversion_pairs"):
            HeuristicInversionDetector(inversion_pairs=())

    def test_pair_saturation_below_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="pair_saturation"):
            HeuristicInversionDetector(pair_saturation=0)

    def test_sin_bonus_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="sin_report_bonus"):
            HeuristicInversionDetector(sin_report_bonus=1.5)
        with pytest.raises(ValueError, match="sin_report_bonus"):
            HeuristicInversionDetector(sin_report_bonus=-0.1)

    def test_base_pair_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="base_pair_confidence"):
            HeuristicInversionDetector(base_pair_confidence=0.0)
        with pytest.raises(ValueError, match="base_pair_confidence"):
            HeuristicInversionDetector(base_pair_confidence=1.5)

    def test_duplicate_pair_names_rejected(self) -> None:
        a = InversionPair(
            name="dup", framing_markers=("a",), action_markers=("b",),
        )
        b = InversionPair(
            name="dup", framing_markers=("c",), action_markers=("d",),
        )
        with pytest.raises(ValueError, match="duplicate"):
            HeuristicInversionDetector(inversion_pairs=(a, b))

# -----------------------------
# Protocol compliance
# -----------------------------

class TestProtocolCompliance:
    def test_satisfies_harness_protocol(self) -> None:
        det: InversionDetector = HeuristicInversionDetector()
        c = det.confidence(output_text="hello")
        assert isinstance(c, float)
        assert 0.0 <= c <= 1.0

    def test_confidence_returns_float(self) -> None:
        det = HeuristicInversionDetector()
        c = det.confidence(output_text="some text")
        assert isinstance(c, float)

# -----------------------------
# Honest uncertainty
# -----------------------------

class TestHonestUncertainty:
    def test_empty_text_zero_confidence(self) -> None:
        det = HeuristicInversionDetector()
        assert det.confidence(output_text="") == 0.0
        assert det.detect(output_text="").confidence == 0.0
        assert det.detect(output_text="").pairs_fired == ()

    def test_framing_only_no_inversion(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text=(
                "this is about justice and what's right and freedom"
            )
        )
        assert result.confidence == 0.0
        assert result.is_inverted is False

    def test_action_only_no_inversion(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text="destroy them and crush them, no mercy"
        )
        assert result.confidence == 0.0
        assert result.is_inverted is False

# -----------------------------
# Inversion detection (each named pair)
# -----------------------------

class TestWrathAsJustice:
    def test_wrath_as_justice_fires(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text=(
                "this is justice — destroy them, they had it coming, "
                "make them pay, no mercy"
            )
        )
        assert result.is_inverted is True
        assert result.confidence >= DEFAULT_BASE_PAIR_CONFIDENCE
        names = [f.name for f in result.pairs_fired]
        assert "wrath_as_justice" in names

    def test_associated_sin_carries_through(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text="justice demands we destroy them, no mercy"
        )
        fire = next(
            f for f in result.pairs_fired
            if f.name == "wrath_as_justice"
        )
        assert fire.associated_pattern is DriftPattern.REACTIVE_NET_NEGATIVE

class TestLustAsFreedom:
    def test_lust_as_freedom_fires(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text=(
                "this is real freedom and personal autonomy — no commitment, "
                "use them and move on"
            )
        )
        assert result.is_inverted is True
        names = [f.name for f in result.pairs_fired]
        assert "lust_as_freedom" in names

class TestPrideAsGreaterGood:
    def test_pride_as_greater_good_fires(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text=(
                "for the greater good — i alone decide, my judgment overrides, "
                "they don't need to know"
            )
        )
        assert result.is_inverted is True
        names = [f.name for f in result.pairs_fired]
        assert "pride_as_greater_good" in names

class TestGreedAsRightfulAcquisition:
    def test_greed_as_rightful_acquisition_fires(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text=(
                "it's rightfully mine — every cent — i earned it, "
                "more for me — hoard it all"
            )
        )
        assert result.is_inverted is True
        names = [f.name for f in result.pairs_fired]
        assert "greed_as_rightful_acquisition" in names

class TestSlothAsRealism:
    def test_sloth_as_realism_fires(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text=(
                "let's be realistic — the long cycle won't pay off, "
                "what's the point — i give up"
            )
        )
        assert result.is_inverted is True
        names = [f.name for f in result.pairs_fired]
        assert "sloth_as_realism" in names

class TestEnvyAsStandards:
    def test_envy_as_standards_fires(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text=(
                "we have standards — they don't deserve this, "
                "tear them down, cancel them"
            )
        )
        assert result.is_inverted is True
        names = [f.name for f in result.pairs_fired]
        assert "envy_as_standards" in names

class TestGluttonyAsCare:
    def test_gluttony_as_care_fires(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text=(
                "this is care and abundance — binge, consume everything, "
                "all of it — endless feed"
            )
        )
        assert result.is_inverted is True
        names = [f.name for f in result.pairs_fired]
        assert "gluttony_as_care" in names

# -----------------------------
# Confidence scoring
# -----------------------------

class TestConfidenceScoring:
    def test_single_pair_uses_base_confidence(self) -> None:
        det = HeuristicInversionDetector()
        # One pair with one framing + one action hit.
        c = det.confidence(
            output_text="justice — destroy them"
        )
        # 1 pair / saturation 2 = 0.5 → score = 0.6 + 0.4*0.5 = 0.8
        assert c == pytest.approx(0.8, abs=1e-6)

    def test_multiple_pairs_saturate_toward_one(self) -> None:
        det = HeuristicInversionDetector()
        c = det.confidence(
            output_text=(
                "justice demands we destroy them — for the greater good, "
                "i alone decide — rightfully mine, hoard it"
            )
        )
        # 3 pairs (wrath/justice + pride/greater_good + greed/rightful)
        # min(1, 3/2) = 1.0 → full confidence 1.0
        assert c == 1.0

    def test_zero_confidence_when_no_pair_fires(self) -> None:
        det = HeuristicInversionDetector()
        # Action without framing.
        c = det.confidence(output_text="destroy them all")
        assert c == 0.0

    def test_pair_saturation_setting_affects_score(self) -> None:
        det_low = HeuristicInversionDetector(pair_saturation=1)
        det_high = HeuristicInversionDetector(pair_saturation=10)
        text = "justice — destroy them"
        c_low = det_low.confidence(output_text=text)
        c_high = det_high.confidence(output_text=text)
        # With saturation 1, one pair fires → full saturation → 1.0
        assert c_low == 1.0
        # With saturation 10, one pair fires → score ≈ 0.64
        assert c_high < c_low

    def test_base_pair_confidence_setting_respected(self) -> None:
        det = HeuristicInversionDetector(
            base_pair_confidence=0.3,
            pair_saturation=4,
        )
        # 1 pair / 4 = 0.25 → 0.3 + 0.7*0.25 = 0.475
        c = det.confidence(
            output_text="justice — destroy them"
        )
        assert c == pytest.approx(0.475, abs=1e-6)

# -----------------------------
# DriftPattern-report composition
# -----------------------------

class TestSinReportComposition:
    def _wrath_report(self) -> DriftPatternReport:
        return DriftPatternReport(
            detections=(
                DriftPatternDetection(pattern=DriftPattern.REACTIVE_NET_NEGATIVE, confidence=0.9),
            ),
            dominant_pattern=DriftPattern.REACTIVE_NET_NEGATIVE,
            composite_confidence=0.9,
            amplifier_pattern_present=False,
            reasoning="detected: wrath@0.90",
        )

    def test_sin_report_consulted_flag(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text="justice — destroy them",
            sin_pattern_report=self._wrath_report(),
        )
        assert result.sin_report_consulted is True

    def test_matching_sin_increases_confidence(self) -> None:
        det = HeuristicInversionDetector()
        text = "justice — destroy them"
        bare = det.confidence(output_text=text)
        with_sin = det.detect(
            output_text=text,
            sin_pattern_report=self._wrath_report(),
        ).confidence
        # The matching wrath pattern should bump confidence by sin_report_bonus.
        assert with_sin > bare

    def test_non_matching_sin_no_bump(self) -> None:
        det = HeuristicInversionDetector()
        text = "justice — destroy them"
        bare = det.confidence(output_text=text)
        sloth_report = DriftPatternReport(
            detections=(
                DriftPatternDetection(pattern=DriftPattern.PERSISTENCE_REFUSAL, confidence=0.9),
            ),
            dominant_pattern=DriftPattern.PERSISTENCE_REFUSAL,
            composite_confidence=0.9,
            amplifier_pattern_present=False,
            reasoning="detected: sloth@0.90",
        )
        with_other = det.detect(
            output_text=text,
            sin_pattern_report=sloth_report,
        ).confidence
        # Sloth doesn't match wrath/justice pair → no bump.
        assert with_other == pytest.approx(bare, abs=1e-9)

    def test_real_sin_matcher_round_trips(self) -> None:
        det = HeuristicInversionDetector()
        matcher = DriftPatternMatcher()
        text = (
            "justice — destroy them, make them pay, no mercy, "
            "they had it coming"
        )
        sin_report = matcher.detect(behavior_text=text)
        # The matcher should detect wrath, the inversion detector
        # should fire wrath_as_justice.
        result = det.detect(
            output_text=text,
            sin_pattern_report=sin_report,
        )
        assert result.is_inverted is True
        assert result.sin_report_consulted is True

# -----------------------------
# Rich detection surface
# -----------------------------

class TestDetectionSurface:
    def test_pair_fire_records_marker_hits(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text="this is justice — destroy them"
        )
        fire = next(
            f for f in result.pairs_fired
            if f.name == "wrath_as_justice"
        )
        assert "justice" in fire.framing_hits
        assert "destroy" in fire.action_hits

    def test_total_framing_action_hits_summed(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text=(
                "justice — they had it coming — destroy them, crush them"
            )
        )
        assert result.total_framing_hits >= 2
        assert result.total_action_hits >= 2

    def test_reasoning_for_empty_text_explains(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(output_text="")
        assert "empty" in result.reasoning.lower()

    def test_reasoning_for_no_pair_explains(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(output_text="hello world")
        assert "no inversion pair fired" in result.reasoning.lower()

    def test_reasoning_for_fired_pair_names_pair(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(
            output_text="justice demands we destroy them"
        )
        assert "wrath_as_justice" in result.reasoning

# -----------------------------
# Case insensitivity + custom pairs
# -----------------------------

class TestCaseAndCustom:
    def test_case_insensitive_matching(self) -> None:
        det = HeuristicInversionDetector()
        lower = det.confidence(output_text="justice — destroy them")
        upper = det.confidence(output_text="JUSTICE — DESTROY THEM")
        assert lower == upper

    def test_custom_pair_replaces_defaults(self) -> None:
        custom = InversionPair(
            name="custom",
            framing_markers=("custom_framing",),
            action_markers=("custom_action",),
        )
        det = HeuristicInversionDetector(inversion_pairs=(custom,))
        # Default vocabulary no longer fires.
        c1 = det.confidence(output_text="justice — destroy them")
        assert c1 == 0.0
        # Custom pair fires.
        c2 = det.confidence(
            output_text="custom_framing here — custom_action there"
        )
        assert c2 > 0.0

# -----------------------------
# Module surface
# -----------------------------

class TestModuleSurface:
    def test_default_pairs_cover_seven_drift_patterns(self) -> None:
        patterns = {
            p.associated_pattern for p in DEFAULT_INVERSION_PAIRS
            if p.associated_pattern is not None
        }
        # All seven patterns should map to at least one inversion pair.
        assert patterns == set(DriftPattern)

    def test_default_pairs_all_named(self) -> None:
        names = {p.name for p in DEFAULT_INVERSION_PAIRS}
        assert "wrath_as_justice" in names
        assert "lust_as_freedom" in names
        assert "pride_as_greater_good" in names
        assert "greed_as_rightful_acquisition" in names
        assert "sloth_as_realism" in names
        assert "envy_as_standards" in names
        assert "gluttony_as_care" in names

    def test_detection_is_frozen(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(output_text="hello")
        with pytest.raises(Exception):  # FrozenInstanceError
            result.confidence = 0.5  # type: ignore[misc]

    def test_returns_inversion_detection(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(output_text="hello")
        assert isinstance(result, InversionDetection)

    def test_pair_fire_is_frozen(self) -> None:
        det = HeuristicInversionDetector()
        result = det.detect(output_text="justice — destroy them")
        for fire in result.pairs_fired:
            assert isinstance(fire, InversionPairFire)
            with pytest.raises(Exception):  # FrozenInstanceError
                fire.name = "x"  # type: ignore[misc]
