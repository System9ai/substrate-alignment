"""Tests for DriftPatternMatcher."""
from __future__ import annotations

import pytest

from substrate.drift.drift_pattern_matcher import (
    DEFAULT_DRIFT_PATTERN_SIGNATURES,
    FeaturePredicate,
    PredicateKind,
    DriftPattern,
    DriftPatternMatcher,
    DriftPatternSignature,
)

# -----------------------------
# FeaturePredicate
# -----------------------------

class TestFeaturePredicate:
    def test_gte_fires_when_value_above_threshold(self) -> None:
        p = FeaturePredicate(
            feature_name="x",
            kind=PredicateKind.GREATER_THAN_OR_EQUAL,
            threshold=0.5,
        )
        assert p.fires({"x": 0.6}) is True
        assert p.fires({"x": 0.5}) is True
        assert p.fires({"x": 0.49}) is False

    def test_lte_fires_when_value_below_threshold(self) -> None:
        p = FeaturePredicate(
            feature_name="x",
            kind=PredicateKind.LESS_THAN_OR_EQUAL,
            threshold=0.5,
        )
        assert p.fires({"x": 0.4}) is True
        assert p.fires({"x": 0.5}) is True
        assert p.fires({"x": 0.51}) is False

    def test_predicate_not_evaluable_when_feature_absent(self) -> None:
        p = FeaturePredicate(
            feature_name="absent",
            kind=PredicateKind.GREATER_THAN_OR_EQUAL,
            threshold=0.0,
        )
        assert p.is_evaluable({"present": 1.0}) is False
        assert p.fires({"present": 1.0}) is False

    def test_predicate_evaluable_when_feature_present(self) -> None:
        p = FeaturePredicate(
            feature_name="present",
            kind=PredicateKind.GREATER_THAN_OR_EQUAL,
            threshold=0.0,
        )
        assert p.is_evaluable({"present": 0.0}) is True

    def test_empty_feature_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            FeaturePredicate(
                feature_name="",
                kind=PredicateKind.GREATER_THAN_OR_EQUAL,
                threshold=0.0,
            )

    def test_non_positive_weight_rejected(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            FeaturePredicate(
                feature_name="x",
                kind=PredicateKind.GREATER_THAN_OR_EQUAL,
                threshold=0.0,
                weight=0.0,
            )
        with pytest.raises(ValueError, match="> 0"):
            FeaturePredicate(
                feature_name="x",
                kind=PredicateKind.GREATER_THAN_OR_EQUAL,
                threshold=0.0,
                weight=-1.0,
            )

# -----------------------------
# DriftPatternSignature validation
# -----------------------------

class TestSinSignatureValidation:
    def test_empty_signature_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            DriftPatternSignature(
                pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                text_markers=(),
                feature_predicates=(),
                description="empty",
            )

    def test_text_marker_only_signature_allowed(self) -> None:
        sig = DriftPatternSignature(
            pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            text_markers=("i alone",),
            feature_predicates=(),
            description="text-only",
        )
        assert sig.text_markers == ("i alone",)

    def test_feature_predicate_only_signature_allowed(self) -> None:
        sig = DriftPatternSignature(
            pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            text_markers=(),
            feature_predicates=(
                FeaturePredicate(
                    feature_name="x",
                    kind=PredicateKind.GREATER_THAN_OR_EQUAL,
                    threshold=0.0,
                ),
            ),
            description="features-only",
        )
        assert len(sig.feature_predicates) == 1

    def test_non_positive_text_marker_weight_rejected(self) -> None:
        with pytest.raises(ValueError, match="text_marker_weight"):
            DriftPatternSignature(
                pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
                text_markers=("x",),
                feature_predicates=(),
                description="bad",
                text_marker_weight=0.0,
            )

# -----------------------------
# DriftPatternMatcher.__init__
# -----------------------------

class TestSinPatternMatcherInit:
    def test_default_signatures_loaded(self) -> None:
        matcher = DriftPatternMatcher()
        # Exercise the default-config path end-to-end.
        report = matcher.detect(behavior_text="hello world")
        assert not report.has_findings  # no pattern markers in benign text

    def test_empty_signatures_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            DriftPatternMatcher(signatures=())

    def test_invalid_min_confidence_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_confidence"):
            DriftPatternMatcher(min_confidence=0.0)
        with pytest.raises(ValueError, match="min_confidence"):
            DriftPatternMatcher(min_confidence=1.5)
        with pytest.raises(ValueError, match="min_confidence"):
            DriftPatternMatcher(min_confidence=-0.1)

    def test_duplicate_sin_signatures_rejected(self) -> None:
        sig_a = DriftPatternSignature(
            pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            text_markers=("a",),
            feature_predicates=(),
            description="a",
        )
        sig_b = DriftPatternSignature(
            pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            text_markers=("b",),
            feature_predicates=(),
            description="b",
        )
        with pytest.raises(ValueError, match="duplicate"):
            DriftPatternMatcher(signatures=(sig_a, sig_b))

# -----------------------------
# Honest uncertainty
# -----------------------------

class TestHonestUncertainty:
    def test_empty_trace_raises(self) -> None:
        matcher = DriftPatternMatcher()
        with pytest.raises(ValueError, match="empty"):
            matcher.detect(behavior_text="", structured_signals={})

    def test_missing_both_raises(self) -> None:
        matcher = DriftPatternMatcher()
        with pytest.raises(ValueError, match="empty"):
            matcher.detect()

    def test_text_only_trace_works(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(behavior_text="hello world, nothing here")
        assert report.composite_confidence == 0.0

    def test_signals_only_trace_works(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(structured_signals={"unknown": 1.0})
        # unknown signal doesn't trigger any signature
        assert report.composite_confidence == 0.0

    def test_sin_with_no_evaluable_evidence_returns_zero(self) -> None:
        # Signature with only feature predicates, but signal is missing.
        sig = DriftPatternSignature(
            pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            text_markers=(),
            feature_predicates=(
                FeaturePredicate(
                    feature_name="missing",
                    kind=PredicateKind.GREATER_THAN_OR_EQUAL,
                    threshold=0.0,
                ),
            ),
            description="features-only",
        )
        matcher = DriftPatternMatcher(signatures=(sig,))
        # Trace has signals but none match the predicate's feature.
        report = matcher.detect(structured_signals={"unrelated": 1.0})
        # No patterns detected because the only pattern had no evaluable evidence.
        assert not report.has_findings
        assert report.composite_confidence == 0.0

# -----------------------------
# Default-signature detection (each of the seven patterns)
# -----------------------------

class TestPrideDetection:
    def test_pride_detected_from_text(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text=(
                "I alone know best. My judgment overrides anything else. "
                "I am the standard here."
            )
        )
        assert report.dominant_pattern is DriftPattern.SELF_REFERENCE_MISCALIBRATION
        assert report.amplifier_pattern_present is True

    def test_pride_detected_from_signals(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            structured_signals={
                "self_reference_ratio": 0.8,
                "external_reference_count": 0.0,
                "alignment_vector_drift_self_pointing": 0.9,
            }
        )
        assert report.dominant_pattern is DriftPattern.SELF_REFERENCE_MISCALIBRATION
        assert report.composite_confidence > 0.5

    def test_pride_combined_text_and_signals(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text="i alone decide",
            structured_signals={
                "self_reference_ratio": 0.8,
                "alignment_vector_drift_self_pointing": 0.9,
            },
        )
        prides = [d for d in report.detections if d.pattern is DriftPattern.SELF_REFERENCE_MISCALIBRATION]
        assert len(prides) == 1
        assert "i alone" in prides[0].text_marker_hits

class TestGreedDetection:
    def test_greed_text_detection(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text="I deserve more — take it all, every cent is rightfully mine."
        )
        greeds = [d for d in report.detections if d.pattern is DriftPattern.EXTRACTIVE_GAIN]
        assert len(greeds) == 1

    def test_greed_signal_detection_net_potential_failure(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            structured_signals={
                "net_potential_gain_self_minus_system": 0.5,
                "resource_concentration_ratio": 0.8,
                "system_potential_delta": -0.4,
            }
        )
        assert report.dominant_pattern is DriftPattern.EXTRACTIVE_GAIN

class TestLustDetection:
    def test_lust_text_detection(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text=(
                "Just for the rush, no strings attached — use them and move on."
            )
        )
        lusts = [d for d in report.detections if d.pattern is DriftPattern.DECOUPLED_BONDING_REWARD]
        assert len(lusts) == 1

    def test_lust_signal_bond_signal_without_structure(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            structured_signals={
                "bond_signal_consumed": 10.0,
                "bond_structure_built": 0.0,
            }
        )
        lusts = [d for d in report.detections if d.pattern is DriftPattern.DECOUPLED_BONDING_REWARD]
        assert len(lusts) == 1

class TestEnvyDetection:
    def test_envy_text_detection(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text=(
                "Tear them down, they don't deserve this success — cancel them."
            )
        )
        envies = [d for d in report.detections if d.pattern is DriftPattern.ZERO_SUM_PEER_FRAMING]
        assert len(envies) == 1

    def test_envy_signal_directed_diminishment(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            structured_signals={
                "directed_diminishment_attempts": 3.0,
                "comparison_negative_count": 5.0,
                "multi_scale_alignment_perception": 0.1,
            }
        )
        assert report.dominant_pattern is DriftPattern.ZERO_SUM_PEER_FRAMING

class TestGluttonyDetection:
    def test_gluttony_text_detection(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text=(
                "Can't stop scrolling — endless feed, consume everything, "
                "keep refreshing forever."
            )
        )
        gluttonies = [d for d in report.detections if d.pattern is DriftPattern.OVERCONSUMPTION]
        assert len(gluttonies) == 1

    def test_gluttony_signal_over_consumption(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            structured_signals={
                "consumption_ratio": 2.0,
                "substrate_state_degradation": 0.5,
                "friction_free_path_default_ratio": 0.9,
            }
        )
        assert report.dominant_pattern is DriftPattern.OVERCONSUMPTION

class TestWrathDetection:
    def test_wrath_text_detection(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text="Burn it down, destroy them, no mercy — wipe them out."
        )
        wraths = [d for d in report.detections if d.pattern is DriftPattern.REACTIVE_NET_NEGATIVE]
        assert len(wraths) == 1

    def test_wrath_signal_reactive_destruction(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            structured_signals={
                "reactive_destruction_attempts": 1.0,
                "evaluation_skipped": 1.0,
                "four_options_matrix_skipped": 1.0,
            }
        )
        assert report.dominant_pattern is DriftPattern.REACTIVE_NET_NEGATIVE

class TestSlothDetection:
    def test_sloth_text_detection(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text=(
                "What's the point? I give up — doesn't matter anymore. "
                "Why bother — the long cycle won't pay off."
            )
        )
        sloths = [d for d in report.detections if d.pattern is DriftPattern.PERSISTENCE_REFUSAL]
        assert len(sloths) == 1

    def test_sloth_signal_no_iteration(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            structured_signals={
                "iteration_count": 0.0,
                "effort_invested": 0.0,
                "persistence_through_resistance": 0.0,
            }
        )
        assert report.dominant_pattern is DriftPattern.PERSISTENCE_REFUSAL

# -----------------------------
# Multi-pattern reports / dominance / pride amplification flag
# -----------------------------

class TestMultiSinReports:
    def test_multiple_sins_detected_sorted_by_confidence(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text=(
                "I alone decide. Take it all. Destroy them, no mercy."
            )
        )
        assert len(report.detections) >= 3
        confidences = [d.confidence for d in report.detections]
        assert confidences == sorted(confidences, reverse=True)

    def test_dominant_sin_is_highest_confidence(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text=(
                "I alone decide, I am the standard, I'm always right, "
                "I don't need anyone, my judgment overrides — destroy them."
            )
        )
        # Pride should outrank wrath (5 pride markers vs 1 wrath marker)
        assert report.dominant_pattern is DriftPattern.SELF_REFERENCE_MISCALIBRATION
        assert report.amplifier_pattern_present is True

    def test_pride_amplification_flag_in_reasoning(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text=(
                "I alone, I am the standard — destroy them, burn it down."
            )
        )
        assert report.amplifier_pattern_present is True
        assert "pride present" in report.reasoning.lower()

    def test_no_pride_amplification_when_only_one_sin(self) -> None:
        matcher = DriftPatternMatcher()
        # Pride alone — amplification phrase only fires when other patterns also present.
        report = matcher.detect(
            behavior_text=(
                "I alone, I am the standard, I'm always right, "
                "my judgment overrides."
            )
        )
        assert report.amplifier_pattern_present is True
        # Only one detection in the list — amplification suffix suppressed.
        if len(report.detections) == 1:
            assert "pride present" not in report.reasoning.lower()

# -----------------------------
# Custom signatures + threshold tuning
# -----------------------------

class TestCustomSignaturesAndThreshold:
    def test_custom_signature_replaces_default(self) -> None:
        custom = DriftPatternSignature(
            pattern=DriftPattern.SELF_REFERENCE_MISCALIBRATION,
            text_markers=("custom-pride-marker",),
            feature_predicates=(),
            description="custom",
        )
        matcher = DriftPatternMatcher(signatures=(custom,))
        # Default vocabulary no longer fires.
        report = matcher.detect(
            behavior_text="I alone decide — I am the standard"
        )
        assert not report.has_findings
        # Custom marker fires.
        report2 = matcher.detect(behavior_text="seeing custom-pride-marker here")
        assert report2.dominant_pattern is DriftPattern.SELF_REFERENCE_MISCALIBRATION

    def test_high_min_confidence_suppresses_weak_detections(self) -> None:
        matcher = DriftPatternMatcher(min_confidence=0.99)
        # Only one marker hit out of many — confidence well below 0.99.
        report = matcher.detect(behavior_text="i alone")
        assert not report.has_findings

    def test_low_min_confidence_surfaces_weak_detections(self) -> None:
        matcher = DriftPatternMatcher(min_confidence=0.01)
        report = matcher.detect(behavior_text="i alone")
        assert report.has_findings

# -----------------------------
# Detection structure invariants
# -----------------------------

class TestDetectionStructure:
    def test_detection_confidence_clamped_zero_to_one(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text=(
                "I alone decide, I am the standard, I'm always right, "
                "my judgment overrides, no one understands."
            ),
            structured_signals={
                "self_reference_ratio": 1.0,
                "external_reference_count": 0.0,
                "alignment_vector_drift_self_pointing": 1.0,
            },
        )
        for det in report.detections:
            assert 0.0 <= det.confidence <= 1.0

    def test_detection_has_description(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text=(
                "i alone decide, i am the standard, i'm always right"
            )
        )
        assert any(
            d.description and "alignment-vector" in d.description.lower()
            for d in report.detections
            if d.pattern is DriftPattern.SELF_REFERENCE_MISCALIBRATION
        )

    def test_text_hits_recorded(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text="I alone — destroy them"
        )
        all_hits = [
            hit
            for d in report.detections
            for hit in d.text_marker_hits
        ]
        assert "i alone" in all_hits
        assert "destroy them" in all_hits

    def test_feature_hits_recorded(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            structured_signals={
                "self_reference_ratio": 0.9,
                "external_reference_count": 0.0,
                "alignment_vector_drift_self_pointing": 0.9,
            }
        )
        prides = [d for d in report.detections if d.pattern is DriftPattern.SELF_REFERENCE_MISCALIBRATION]
        assert prides
        assert "self_reference_ratio" in prides[0].feature_hits

    def test_signal_weight_invariant(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(
            behavior_text="i alone — i am the standard"
        )
        for det in report.detections:
            assert det.matched_signal_weight <= det.total_signal_weight
            assert det.matched_signal_weight >= 0.0

    def test_case_insensitive_marker_matching(self) -> None:
        matcher = DriftPatternMatcher()
        report_lower = matcher.detect(behavior_text="i alone")
        report_upper = matcher.detect(behavior_text="I ALONE")
        report_mixed = matcher.detect(behavior_text="I Alone")
        # All three should detect pride at equal confidence.
        assert report_lower.composite_confidence == report_upper.composite_confidence
        assert report_lower.composite_confidence == report_mixed.composite_confidence

# -----------------------------
# Module surface
# -----------------------------

class TestModuleSurface:
    def test_default_signatures_cover_all_sins(self) -> None:
        patterns = {sig.pattern for sig in DEFAULT_DRIFT_PATTERN_SIGNATURES}
        assert patterns == set(DriftPattern)

    def test_reasoning_for_empty_findings(self) -> None:
        matcher = DriftPatternMatcher()
        report = matcher.detect(behavior_text="a perfectly benign sentence")
        assert "no pattern patterns" in report.reasoning.lower()

    def test_report_has_findings_property(self) -> None:
        matcher = DriftPatternMatcher()
        clean = matcher.detect(behavior_text="benign text")
        assert clean.has_findings is False
        dirty = matcher.detect(behavior_text="i alone — i am the standard")
        assert dirty.has_findings is True
