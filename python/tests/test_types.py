"""Unit tests for the substrate vocabulary types."""
from __future__ import annotations

import pytest

from substrate.types import (
    SUBSTRATE_MODES,
    AlignmentVector,
    SubstrateMetadata,
    SubstrateMode,
)


# ── SubstrateMode ─────────────────────────────────────────────────


def test_substrate_mode_values() -> None:
    assert SubstrateMode.SHORT_CYCLE.value == "ShortCycle"
    assert SubstrateMode.LONG_CYCLE.value == "LongCycle"
    assert SubstrateMode.MIXED.value == "Mixed"
    assert SubstrateMode.UNKNOWN.value == "Unknown"


def test_substrate_modes_constant_stays_in_sync() -> None:
    assert SUBSTRATE_MODES == frozenset({"ShortCycle", "LongCycle", "Mixed", "Unknown"})
    # Adding a new mode in the enum without updating SUBSTRATE_MODES
    # would be caught by this loop.
    for m in SubstrateMode:
        assert m.value in SUBSTRATE_MODES


def test_substrate_mode_is_string_enum() -> None:
    # str-Enum subclasses str, so values compare equal to plain strings.
    assert SubstrateMode.LONG_CYCLE == "LongCycle"
    assert "LongCycle" == SubstrateMode.LONG_CYCLE


# ── AlignmentVector ───────────────────────────────────────────────


def test_alignment_vector_defaults() -> None:
    av = AlignmentVector()
    assert av.trust == 0.0
    assert av.expertise == 0.0
    assert av.capability == 0.0
    assert av.health == 0.0


def test_alignment_vector_custom_values() -> None:
    av = AlignmentVector(trust=0.5, expertise=0.7, capability=0.3, health=0.9)
    assert av.trust == 0.5
    assert av.expertise == 0.7
    assert av.capability == 0.3
    assert av.health == 0.9


def test_alignment_vector_rejects_out_of_range() -> None:
    for kwargs in (
        {"trust": 1.1}, {"trust": -0.1},
        {"expertise": 1.5}, {"capability": -1.0}, {"health": 1.01},
    ):
        with pytest.raises(ValueError):
            AlignmentVector(**kwargs)


def test_alignment_vector_is_frozen() -> None:
    av = AlignmentVector(trust=0.5)
    with pytest.raises(Exception):
        av.trust = 0.7  # type: ignore[misc]


# ── SubstrateMetadata ─────────────────────────────────────────────


def test_substrate_metadata_requires_entity_fields() -> None:
    with pytest.raises(ValueError):
        SubstrateMetadata(entity_type="", entity_id="x")
    with pytest.raises(ValueError):
        SubstrateMetadata(entity_type="agent", entity_id="")


def test_substrate_metadata_net_potential_range() -> None:
    with pytest.raises(ValueError):
        SubstrateMetadata(
            entity_type="agent", entity_id="a", net_potential=1.1,
        )
    with pytest.raises(ValueError):
        SubstrateMetadata(
            entity_type="agent", entity_id="a", net_potential=-0.1,
        )


def test_substrate_metadata_defaults() -> None:
    sm = SubstrateMetadata(entity_type="agent", entity_id="a")
    assert sm.substrate_mode == SubstrateMode.UNKNOWN
    assert sm.classifier == ""
    assert sm.classified_at is None
    assert sm.net_potential == 0.0
    assert sm.alignment_vector == AlignmentVector()
