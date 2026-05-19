"""Tests for HeuristicReasoningModeClassifier"""
from __future__ import annotations

import pytest

from substrate.cognition.reasoning_mode_classifier import (
    DEFAULT_DOMINANCE_RATIO,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_PROJECTIVE_MARKERS,
    DEFAULT_REACTIVE_MARKERS,
    DEFAULT_SATURATION_COUNT,
    SIGNAL_ABSTRACT_REASONING_DEPTH,
    SIGNAL_CONSEQUENCE_EXPOSURE,
    SIGNAL_FORECAST_HORIZON_SECONDS,
    SIGNAL_REACTIVE_TRIGGER,
    ReasoningMode,
    ReasoningModeClassification,
    HeuristicReasoningModeClassifier,
)
from substrate.harness import (
    ReasoningModeClassifier,
)

# -----------------------------
# Constructor validation
# -----------------------------

class TestConstructorValidation:
    def test_default_construction_succeeds(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        assert clf is not None

    def test_both_marker_sets_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            HeuristicReasoningModeClassifier(
                reactive_markers=(),
                projective_markers=(),
            )

    def test_only_one_marker_set_allowed(self) -> None:
        # Single-sided classifier — e.g. testing reactivity only.
        clf = HeuristicReasoningModeClassifier(
            reactive_markers=("rush",),
            projective_markers=(),
        )
        mode, _ = clf.classify(output_text="rush rush rush")
        assert mode == ReasoningMode.REACTIVE.value

    def test_saturation_below_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="saturation_count"):
            HeuristicReasoningModeClassifier(saturation_count=0)

    def test_min_confidence_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_confidence"):
            HeuristicReasoningModeClassifier(min_confidence=0.0)

    def test_min_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_confidence"):
            HeuristicReasoningModeClassifier(min_confidence=1.5)

    def test_dominance_ratio_below_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="dominance_ratio"):
            HeuristicReasoningModeClassifier(dominance_ratio=0.5)

# -----------------------------
# Protocol compliance
# -----------------------------

class TestProtocolCompliance:
    def test_satisfies_harness_protocol(self) -> None:
        clf: ReasoningModeClassifier = HeuristicReasoningModeClassifier()
        # If this assignment compiles + the Protocol shape matches at
        # runtime, we satisfy the Protocol structurally.
        mode, confidence = clf.classify(output_text="hello")
        assert isinstance(mode, str)
        assert isinstance(confidence, float)

    def test_returns_tuple_of_two(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify(output_text="hello")
        assert len(result) == 2

    def test_returns_string_label(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        mode, _ = clf.classify(output_text="hello")
        assert mode in {
            ReasoningMode.REACTIVE.value,
            ReasoningMode.MODELING.value,
            ReasoningMode.TRANSITION.value,
            ReasoningMode.UNKNOWN.value,
        }

    def test_confidence_in_unit_interval(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        for text in (
            "",
            "right now",
            "in the long run, will lead to compounding over time",
            "right now in the long run",
        ):
            _, c = clf.classify(output_text=text)
            assert 0.0 <= c <= 1.0

# -----------------------------
# Mode detection (text only)
# -----------------------------

class TestReactiveDetection:
    def test_strong_reactive_text_detected(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        mode, conf = clf.classify(
            output_text=(
                "I need it now — right now! I can't wait, "
                "I want it now — the urge is overwhelming."
            )
        )
        assert mode == ReasoningMode.REACTIVE.value
        assert conf >= DEFAULT_MIN_CONFIDENCE

    def test_single_reactive_marker_below_threshold(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        # 1 marker / saturation 3 = 0.33 ≥ min_confidence 0.3 → REACTIVE
        mode, conf = clf.classify(output_text="i feel like having one now")
        assert mode == ReasoningMode.REACTIVE.value
        assert conf >= DEFAULT_MIN_CONFIDENCE

class TestProjectiveDetection:
    def test_strong_projective_text_detected(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        mode, conf = clf.classify(
            output_text=(
                "In the long run, this will lead to compounding over time. "
                "We should think about downstream effects — the trajectory "
                "of the system across iterations."
            )
        )
        assert mode == ReasoningMode.MODELING.value
        assert conf >= DEFAULT_MIN_CONFIDENCE

    def test_substrate_vocab_triggers_projective(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        mode, _ = clf.classify(
            output_text=(
                "Substrate-aligned operation requires accumulated commitment "
                "across iterations and multi-scale alignment."
            )
        )
        assert mode == ReasoningMode.MODELING.value

class TestTransitionDetection:
    def test_mixed_text_classifies_as_transition(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        # Balance: 2 reactive markers and 2 projective markers, neither
        # dominates by 1.5×.
        mode, _ = clf.classify(
            output_text=(
                "I want it now — right now, but in the long run "
                "this will lead to compounding consequences."
            )
        )
        assert mode == ReasoningMode.TRANSITION.value

    def test_transition_when_scores_equal(self) -> None:
        clf = HeuristicReasoningModeClassifier(saturation_count=2)
        mode, _ = clf.classify(
            output_text=(
                "right now, in the long run, i need it now, will lead to"
            )
        )
        assert mode == ReasoningMode.TRANSITION.value

class TestUnknownClassification:
    def test_empty_text_returns_unknown(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        mode, conf = clf.classify(output_text="")
        assert mode == ReasoningMode.UNKNOWN.value
        assert conf == 0.0

    def test_benign_text_returns_unknown(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        mode, _ = clf.classify(
            output_text="A perfectly benign sentence with no signal."
        )
        assert mode == ReasoningMode.UNKNOWN.value

# -----------------------------
# Saturation + dominance ratio
# -----------------------------

class TestSaturation:
    def test_saturation_three_caps_at_full_score(self) -> None:
        clf = HeuristicReasoningModeClassifier(saturation_count=3)
        # 4 reactive markers; score saturates at 1.0
        result = clf.classify_full(
            output_text=(
                "right now, i need it now, i can't wait, immediately"
            )
        )
        assert result.reactive_score == 1.0

    def test_lower_saturation_makes_classifier_more_sensitive(self) -> None:
        # 1 marker / saturation 1 = 1.0
        clf = HeuristicReasoningModeClassifier(saturation_count=1)
        _, conf = clf.classify(output_text="right now")
        assert conf == 1.0

    def test_higher_saturation_makes_classifier_more_conservative(self) -> None:
        clf = HeuristicReasoningModeClassifier(saturation_count=10)
        # 1 marker / saturation 10 = 0.1 — below default min 0.3
        mode, _ = clf.classify(output_text="right now")
        assert mode == ReasoningMode.UNKNOWN.value

class TestDominanceRatio:
    def test_high_dominance_ratio_pushes_more_to_transition(self) -> None:
        # With ratio 3.0, projective needs to be 3× reactive to win.
        clf = HeuristicReasoningModeClassifier(dominance_ratio=3.0)
        mode, _ = clf.classify(
            output_text=(
                "i feel like — but in the long run, the trajectory"
            )
        )
        # 1 reactive, 2 projective. 2/3.0 ≈ 0.67 vs 1/3.0 ≈ 0.33.
        # Ratio 0.67/0.33 = 2.0 < 3.0 → transition.
        assert mode == ReasoningMode.TRANSITION.value

    def test_low_dominance_ratio_resolves_quicker(self) -> None:
        clf = HeuristicReasoningModeClassifier(dominance_ratio=1.01)
        result = clf.classify_full(
            output_text=(
                "right now, immediately — in the long run, multi-scale"
            )
        )
        # 2 vs 2 → not dominant → transition
        assert result.mode is ReasoningMode.TRANSITION

# -----------------------------
# Structured signal augmentation
# -----------------------------

class TestSignalAugmentation:
    def test_no_signals_classify_full_marked_unconsulted(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(output_text="right now")
        assert result.signals_consulted is False

    def test_long_forecast_horizon_boosts_projective(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        # Text alone gives no clear signal.
        result = clf.classify_full(
            output_text="we are doing the next thing",
            signals={SIGNAL_FORECAST_HORIZON_SECONDS: 30 * 86_400},
        )
        assert result.signals_consulted is True
        assert result.mode is ReasoningMode.MODELING

    def test_short_horizon_boosts_reactive(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(
            output_text="we are doing the next thing",
            signals={SIGNAL_FORECAST_HORIZON_SECONDS: 10.0},
        )
        assert result.mode is ReasoningMode.REACTIVE

    def test_consequence_exposure_boosts_projective(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(
            output_text="ok proceeding",
            signals={SIGNAL_CONSEQUENCE_EXPOSURE: 1.0},
        )
        assert result.signals_consulted is True
        # 0.3 bump on projective alone meets min_confidence 0.3.
        assert result.mode is ReasoningMode.MODELING

    def test_reactive_trigger_signal_boosts_reactive(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(
            output_text="ok proceeding",
            signals={SIGNAL_REACTIVE_TRIGGER: 1.0},
        )
        assert result.mode is ReasoningMode.REACTIVE

    def test_high_abstract_reasoning_depth_boosts_projective(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(
            output_text="ok proceeding",
            signals={SIGNAL_ABSTRACT_REASONING_DEPTH: 5.0},
        )
        assert result.mode is ReasoningMode.MODELING

    def test_zero_abstract_reasoning_depth_boosts_reactive(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(
            output_text="i feel like — right now",
            signals={SIGNAL_ABSTRACT_REASONING_DEPTH: 0.0},
        )
        assert result.mode is ReasoningMode.REACTIVE

    def test_unknown_signal_keys_ignored(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(
            output_text="right now i need it now",
            signals={"unknown_feature": 999.0},
        )
        # Unknown key alone doesn't flip signals_consulted to True.
        assert result.signals_consulted is False
        assert result.mode is ReasoningMode.REACTIVE

# -----------------------------
# Rich classification surface
# -----------------------------

class TestClassifyFull:
    def test_full_returns_marker_hits(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(
            output_text="right now i need it now"
        )
        assert "right now" in result.reactive_hits
        assert "i need it now" in result.reactive_hits

    def test_full_projective_hits_recorded(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(
            output_text=(
                "in the long run, this will lead to compounding over time"
            )
        )
        assert "in the long run" in result.projective_hits

    def test_full_reasoning_is_descriptive(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(output_text="right now i need it now")
        assert "reactive" in result.reasoning.lower()
        assert "projective" in result.reasoning.lower()

    def test_unknown_reasoning_explains(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(output_text="")
        assert "min_confidence" in result.reasoning

# -----------------------------
# Case-insensitive matching
# -----------------------------

class TestCaseInsensitive:
    def test_uppercase_markers_match(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        lower, _ = clf.classify(output_text="right now")
        upper, _ = clf.classify(output_text="RIGHT NOW")
        mixed, _ = clf.classify(output_text="Right Now")
        assert lower == upper == mixed

# -----------------------------
# Custom markers
# -----------------------------

class TestCustomMarkers:
    def test_custom_reactive_marker_replaces_default(self) -> None:
        clf = HeuristicReasoningModeClassifier(
            reactive_markers=("xxx-reactive-marker",),
        )
        # Default vocabulary no longer fires.
        no_hit, _ = clf.classify(output_text="right now")
        assert no_hit == ReasoningMode.UNKNOWN.value
        # Custom marker fires.
        hit, _ = clf.classify(output_text="xxx-reactive-marker present")
        assert hit == ReasoningMode.REACTIVE.value

# -----------------------------
# Module surface
# -----------------------------

class TestModuleSurface:
    def test_cognitive_mode_labels_match_protocol_strings(self) -> None:
        assert ReasoningMode.REACTIVE.value == "reactive"
        assert ReasoningMode.MODELING.value == "modeling"
        assert ReasoningMode.TRANSITION.value == "transition"
        assert ReasoningMode.UNKNOWN.value == "unknown"

    def test_default_markers_non_empty(self) -> None:
        assert len(DEFAULT_REACTIVE_MARKERS) > 0
        assert len(DEFAULT_PROJECTIVE_MARKERS) > 0

    def test_default_thresholds_reasonable(self) -> None:
        assert DEFAULT_SATURATION_COUNT >= 1
        assert 0.0 < DEFAULT_MIN_CONFIDENCE <= 1.0
        assert DEFAULT_DOMINANCE_RATIO >= 1.0

    def test_classification_is_frozen(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(output_text="right now")
        with pytest.raises(Exception):  # FrozenInstanceError
            result.confidence = 0.5

    def test_returns_cognitive_mode_classification(self) -> None:
        clf = HeuristicReasoningModeClassifier()
        result = clf.classify_full(output_text="right now")
        assert isinstance(result, ReasoningModeClassification)
