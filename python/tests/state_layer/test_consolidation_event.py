"""Tests for ConsolidationEvent (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.state_layer.consolidation_event import (
    REQUIRED_INVARIANT_KEYS,
    ConsolidationEvent,
    ConsolidationKind,
    required_invariants_present,
)

def _event(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    eid: str = "e-1",
    actor: str = "alice",
    compartment: str = "compartment-default",
    kind: ConsolidationKind = ConsolidationKind.CHECKPOINT,
    first: int = 0,
    last: int = 10,
    rep_hash: str = "h-abc",
    invariants: tuple[str, ...] = (
        "identity-preserved",
        "cryptographic-chain-intact",
        "compartment-label-preserved",
    ),
) -> ConsolidationEvent:
    return ConsolidationEvent(
        event_id=eid,
        actor_entity_id=actor,
        compartment_label_id=compartment,
        kind=kind,
        source_first_cycle=first,
        source_last_cycle=last,
        compressed_representation_hash=rep_hash,
        declared_invariants=invariants,
    )

class TestEventValidation:
    def test_round_trip(self) -> None:
        e = _event()
        assert e.source_cycle_count == 11

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("eid", "", "event_id"),
            ("actor", "", "actor_entity_id"),
            ("compartment", "", "compartment_label_id"),
            ("rep_hash", "", "compressed_representation_hash"),
            ("first", -1, "source_first_cycle"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _event(**kwargs)  # type: ignore[arg-type]

    def test_last_before_first(self) -> None:
        with pytest.raises(ValueError, match="source_last_cycle"):
            _event(first=10, last=5)

    def test_empty_invariant_entry(self) -> None:
        with pytest.raises(ValueError, match="declared_invariants"):
            _event(invariants=("identity-preserved", ""))

class TestRequiredInvariants:
    def test_all_present(self) -> None:
        e = _event()
        assert required_invariants_present(e)

    def test_missing_one(self) -> None:
        e = _event(invariants=(
            "identity-preserved",
            "cryptographic-chain-intact",
        ))
        assert not required_invariants_present(e)

    def test_constant(self) -> None:
        assert len(REQUIRED_INVARIANT_KEYS) == 3

class TestKinds:
    def test_compression(self) -> None:
        e = _event(kind=ConsolidationKind.COMPRESSION)
        assert e.kind is ConsolidationKind.COMPRESSION

    def test_promotion(self) -> None:
        e = _event(kind=ConsolidationKind.PROMOTION)
        assert e.kind is ConsolidationKind.PROMOTION
