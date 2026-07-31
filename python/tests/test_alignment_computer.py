"""Unit tests for alignment_computer pure functions"""
from __future__ import annotations

import pytest

from substrate.alignment_computer import (
    DEFAULT_ALIGNMENT_WEIGHTS,
    DEFAULT_LONG_CYCLE_THRESHOLD,
    DEFAULT_MIXED_THRESHOLD,
    AlignmentWeights,
    auto_classify_mode,
    compute_alignment_vector,
    compute_net_potential,
)
from substrate.types import AlignmentVector, SubstrateMode

# ── compute_alignment_vector ──────────────────────────────────────

def test_compute_alignment_vector_round_trip() -> None:
    av = compute_alignment_vector(
        trust=0.6, expertise=0.7, capability=0.5, health=0.8,
    )
    assert av == AlignmentVector(
        trust=0.6, expertise=0.7, capability=0.5, health=0.8,
    )

def test_compute_alignment_vector_validates_range() -> None:
    with pytest.raises(ValueError):
        compute_alignment_vector(
            trust=1.5, expertise=0.0, capability=0.0, health=0.0,
        )

# ── AlignmentWeights ──────────────────────────────────────────────

def test_alignment_weights_defaults_sum_to_one() -> None:
    w = DEFAULT_ALIGNMENT_WEIGHTS
    total = w.trust + w.expertise + w.capability + w.health
    assert 0.99 <= total <= 1.01

def test_alignment_weights_rejects_imbalance() -> None:
    with pytest.raises(ValueError):
        AlignmentWeights(trust=0.5, expertise=0.5, capability=0.5, health=0.5)

def test_alignment_weights_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        # Components individually exceed [0, 1], even though the sum
        # could be 1.0.
        AlignmentWeights(trust=1.5, expertise=-0.5, capability=0.0, health=0.0)

# ── compute_net_potential ─────────────────────────────────────────

def test_compute_net_potential_uses_default_weights() -> None:
    av = AlignmentVector(trust=1.0, expertise=1.0, capability=1.0, health=1.0)
    np = compute_net_potential(av)
    # With weights summing to 1.0 and all components at 1.0, score = 1.0.
    assert np == pytest.approx(1.0)

def test_compute_net_potential_zero_when_empty() -> None:
    np = compute_net_potential(AlignmentVector())
    assert np == 0.0

def test_compute_net_potential_weighted() -> None:
    av = AlignmentVector(trust=1.0, expertise=0.0, capability=0.0, health=0.0)
    np = compute_net_potential(av)
    # Only trust contributes; net = default trust weight.
    assert np == pytest.approx(DEFAULT_ALIGNMENT_WEIGHTS.trust)

def test_compute_net_potential_custom_weights() -> None:
    av = AlignmentVector(trust=1.0, expertise=0.0, capability=0.0, health=0.0)
    weights = AlignmentWeights(trust=1.0, expertise=0.0, capability=0.0, health=0.0)
    np = compute_net_potential(av, weights=weights)
    assert np == pytest.approx(1.0)

# ── auto_classify_mode ────────────────────────────────────────────

def test_auto_classify_unknown_at_zero() -> None:
    assert auto_classify_mode(0.0) == SubstrateMode.UNKNOWN

def test_auto_classify_short_cycle_below_mixed_threshold() -> None:
    assert auto_classify_mode(0.1) == SubstrateMode.SHORT_CYCLE
    assert (
        auto_classify_mode(DEFAULT_MIXED_THRESHOLD - 0.01)
        == SubstrateMode.SHORT_CYCLE
    )

def test_auto_classify_mixed_band() -> None:
    assert auto_classify_mode(DEFAULT_MIXED_THRESHOLD) == SubstrateMode.MIXED
    assert (
        auto_classify_mode(DEFAULT_LONG_CYCLE_THRESHOLD - 0.01)
        == SubstrateMode.MIXED
    )

def test_auto_classify_long_cycle_at_threshold() -> None:
    assert (
        auto_classify_mode(DEFAULT_LONG_CYCLE_THRESHOLD) == SubstrateMode.LONG_CYCLE
    )
    assert auto_classify_mode(1.0) == SubstrateMode.LONG_CYCLE

def test_auto_classify_custom_thresholds() -> None:
    # DoD-style: tighten thresholds.
    mode = auto_classify_mode(
        0.75, long_cycle_threshold=0.85, mixed_threshold=0.50,
    )
    assert mode == SubstrateMode.MIXED

def test_auto_classify_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        auto_classify_mode(1.5)
    with pytest.raises(ValueError):
        auto_classify_mode(-0.1)

def test_auto_classify_rejects_bad_thresholds() -> None:
    with pytest.raises(ValueError):
        # Mixed > long-cycle invalid.
        auto_classify_mode(0.5, long_cycle_threshold=0.4, mixed_threshold=0.6)
