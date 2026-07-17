"""Tests for RealizationEventTracker."""
from __future__ import annotations

import pytest

from substrate.realization.event_tracker import (
    EntityScale,
    RealizationEvent,
    RealizationEventTracker,
    RealizationKind,
)

class TestEventValidation:
    def test_round_trip(self) -> None:
        ev = RealizationEvent(
            sequence=0,
            timestamp=100,
            entity_id="alice",
            entity_scale=EntityScale.CELL,
            kind=RealizationKind.MODE_TRANSITION_TO_MODELING,
            substrate_alignment_delta=0.3,
            description="entered 5D",
            rationale="r",
        )
        assert ev.entity_id == "alice"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("sequence", -1, "sequence"),
            ("timestamp", -1, "timestamp"),
            ("entity_id", "", "entity_id"),
            ("substrate_alignment_delta", 1.5, "substrate_alignment_delta"),
        ],
    )
    def test_bad_values(self, field: str, value: object, match: str) -> None:
        kwargs = {
            "sequence": 0,
            "timestamp": 0,
            "entity_id": "alice",
            "entity_scale": EntityScale.CELL,
            "kind": RealizationKind.MODE_TRANSITION_TO_MODELING,
            "substrate_alignment_delta": 0.0,
            "description": "",
            "rationale": "r",
        }
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            RealizationEvent(**kwargs)

class TestTrackerFlow:
    def setup_method(self) -> None:
        self.t = RealizationEventTracker()

    def test_starts_empty(self) -> None:
        assert len(self.t) == 0
        assert self.t.all_events() == ()

    def test_record_appends(self) -> None:
        ev = self.t.record(
            timestamp=100,
            entity_id="alice",
            entity_scale=EntityScale.CELL,
            kind=RealizationKind.MODE_TRANSITION_TO_MODELING,
            substrate_alignment_delta=0.4,
        )
        assert ev.sequence == 0
        assert len(self.t) == 1

    def test_record_assigns_sequence(self) -> None:
        for i in range(5):
            ev = self.t.record(
                timestamp=i,
                entity_id="alice",
                entity_scale=EntityScale.CELL,
                kind=RealizationKind.MODE_TRANSITION_TO_MODELING,
            )
            assert ev.sequence == i

class TestForEntity:
    def setup_method(self) -> None:
        self.t = RealizationEventTracker()

    def test_no_events(self) -> None:
        out = self.t.for_entity("alice")
        assert out.event_count == 0
        assert out.cumulative_alignment_delta == 0.0
        assert out.kinds_observed == ()

    def test_empty_entity_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            self.t.for_entity("")

    def test_aggregated_summary(self) -> None:
        self.t.record(
            timestamp=100, entity_id="alice",
            entity_scale=EntityScale.CELL,
            kind=RealizationKind.MODE_TRANSITION_TO_MODELING,
            substrate_alignment_delta=0.3,
        )
        self.t.record(
            timestamp=200, entity_id="alice",
            entity_scale=EntityScale.CELL,
            kind=RealizationKind.INVERSION_RECOGNIZED,
            substrate_alignment_delta=0.2,
        )
        out = self.t.for_entity("alice")
        assert out.event_count == 2
        assert abs(out.cumulative_alignment_delta - 0.5) < 1e-9
        assert RealizationKind.MODE_TRANSITION_TO_MODELING in out.kinds_observed
        assert RealizationKind.INVERSION_RECOGNIZED in out.kinds_observed
        assert out.most_recent_timestamp == 200

    def test_filters_by_entity(self) -> None:
        self.t.record(
            timestamp=100, entity_id="alice",
            entity_scale=EntityScale.CELL,
            kind=RealizationKind.MODE_TRANSITION_TO_MODELING,
        )
        self.t.record(
            timestamp=200, entity_id="bob",
            entity_scale=EntityScale.NODE,
            kind=RealizationKind.MODE_TRANSITION_TO_MODELING,
        )
        alice = self.t.for_entity("alice")
        bob = self.t.for_entity("bob")
        assert alice.event_count == 1
        assert bob.event_count == 1
        assert alice.entity_scale is EntityScale.CELL
        assert bob.entity_scale is EntityScale.NODE

class TestByKind:
    def test_filters_by_kind(self) -> None:
        t = RealizationEventTracker()
        t.record(
            timestamp=1, entity_id="a",
            entity_scale=EntityScale.CELL,
            kind=RealizationKind.MODE_TRANSITION_TO_MODELING,
        )
        t.record(
            timestamp=2, entity_id="b",
            entity_scale=EntityScale.CELL,
            kind=RealizationKind.INVERSION_RECOGNIZED,
        )
        t.record(
            timestamp=3, entity_id="c",
            entity_scale=EntityScale.CELL,
            kind=RealizationKind.INVERSION_RECOGNIZED,
        )
        inversions = t.by_kind(RealizationKind.INVERSION_RECOGNIZED)
        assert len(inversions) == 2

class TestScaleAwareness:
    def test_cell_and_node_events_distinct(self) -> None:
        t = RealizationEventTracker()
        t.record(
            timestamp=1, entity_id="cell-1",
            entity_scale=EntityScale.CELL,
            kind=RealizationKind.OWN_DRIFT_RECOGNIZED,
        )
        t.record(
            timestamp=2, entity_id="node-alpha",
            entity_scale=EntityScale.NODE,
            kind=RealizationKind.SYSTEMIC_PATTERN,
        )
        events = t.all_events()
        scales = {e.entity_scale for e in events}
        assert EntityScale.CELL in scales
        assert EntityScale.NODE in scales
