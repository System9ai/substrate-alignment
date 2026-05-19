"""Tests for AlignmentRefresher against the Protocol-based store API."""
from __future__ import annotations

import pytest

from substrate.alignment_computer import compute_net_potential
from substrate.alignment_refresher import (
    ALIGNMENT_COMPONENTS,
    AlignmentRefresher,
)
from substrate.types import (
    AlignmentVector,
    EntityRef,
    InMemorySubstrateMetadataStore,
    SubstrateMode,
)


def _ref() -> EntityRef:
    return EntityRef(entity_type="agent", entity_id="alice")


def _store_with_seed() -> InMemorySubstrateMetadataStore:
    store = InMemorySubstrateMetadataStore()
    store.upsert(
        _ref(),
        substrate_mode=SubstrateMode.MIXED,
        classifier="seed",
        classifier_rationale="initial",
        alignment_vector=AlignmentVector(
            trust=0.2, expertise=0.3, capability=0.4, health=0.5,
        ),
        net_potential=0.34,
    )
    return store


class TestInputValidation:
    def test_unknown_component_rejected(self) -> None:
        r = AlignmentRefresher(InMemorySubstrateMetadataStore())
        with pytest.raises(ValueError, match="component"):
            r.refresh_component(
                ref=_ref(), component="bogus", value=0.5,
            )

    def test_out_of_range_value_rejected(self) -> None:
        r = AlignmentRefresher(InMemorySubstrateMetadataStore())
        with pytest.raises(ValueError, match="value"):
            r.refresh_component(
                ref=_ref(), component="trust", value=1.5,
            )

    def test_negative_value_rejected(self) -> None:
        r = AlignmentRefresher(InMemorySubstrateMetadataStore())
        with pytest.raises(ValueError, match="value"):
            r.refresh_component(
                ref=_ref(), component="trust", value=-0.1,
            )


class TestComponentMerge:
    def test_refresh_replaces_one_component(self) -> None:
        store = _store_with_seed()
        r = AlignmentRefresher(store)
        result = r.refresh_component(
            ref=_ref(), component="trust", value=0.9,
        )
        assert result.alignment_vector.trust == pytest.approx(0.9)
        assert result.alignment_vector.expertise == pytest.approx(0.3)
        assert result.alignment_vector.capability == pytest.approx(0.4)
        assert result.alignment_vector.health == pytest.approx(0.5)

    def test_refresh_recomputes_net_potential(self) -> None:
        store = _store_with_seed()
        r = AlignmentRefresher(store)
        result = r.refresh_component(
            ref=_ref(), component="trust", value=0.9,
        )
        expected_np = compute_net_potential(
            AlignmentVector(trust=0.9, expertise=0.3, capability=0.4, health=0.5)
        )
        assert result.net_potential == pytest.approx(expected_np)

    def test_refresh_reclassifies_mode(self) -> None:
        store = _store_with_seed()
        r = AlignmentRefresher(store)
        for comp in ALIGNMENT_COMPONENTS:
            result = r.refresh_component(
                ref=_ref(), component=comp, value=1.0,
            )
        assert result.substrate_mode is SubstrateMode.LONG_CYCLE

    def test_refresh_persists_via_store(self) -> None:
        store = _store_with_seed()
        r = AlignmentRefresher(store)
        r.refresh_component(ref=_ref(), component="trust", value=0.9)
        persisted = store.get(_ref())
        assert persisted is not None
        assert persisted.alignment_vector.trust == pytest.approx(0.9)

    def test_refresh_first_time_for_unseen_entity(self) -> None:
        store = InMemorySubstrateMetadataStore()
        r = AlignmentRefresher(store)
        result = r.refresh_component(
            ref=_ref(), component="trust", value=0.5,
        )
        assert result.alignment_vector.trust == pytest.approx(0.5)
        assert result.alignment_vector.expertise == 0.0
        assert result.alignment_vector.capability == 0.0
        assert result.alignment_vector.health == 0.0

    def test_idempotent_under_replay(self) -> None:
        store = _store_with_seed()
        r = AlignmentRefresher(store)
        first = r.refresh_component(ref=_ref(), component="trust", value=0.9)
        second = r.refresh_component(ref=_ref(), component="trust", value=0.9)
        assert first.alignment_vector == second.alignment_vector
        assert first.net_potential == pytest.approx(second.net_potential)
        assert first.substrate_mode is second.substrate_mode


class TestClassifierMetadata:
    def test_default_classifier_label(self) -> None:
        store = InMemorySubstrateMetadataStore()
        r = AlignmentRefresher(store)
        result = r.refresh_component(
            ref=_ref(), component="trust", value=0.5,
        )
        assert result.classifier == "alignment_refresher"

    def test_custom_classifier_label(self) -> None:
        store = InMemorySubstrateMetadataStore()
        r = AlignmentRefresher(store, classifier="signal-source-v2")
        result = r.refresh_component(
            ref=_ref(), component="trust", value=0.5,
        )
        assert result.classifier == "signal-source-v2"

    def test_rationale_names_the_component_and_value(self) -> None:
        store = InMemorySubstrateMetadataStore()
        r = AlignmentRefresher(store)
        result = r.refresh_component(
            ref=_ref(), component="trust", value=0.345,
        )
        assert "trust" in result.classifier_rationale
        assert "0.345" in result.classifier_rationale


def test_alignment_components_set() -> None:
    assert ALIGNMENT_COMPONENTS == frozenset(
        {"trust", "expertise", "capability", "health"}
    )
