"""Tests for cross-org substrate-mode classifier."""
from __future__ import annotations

import pytest

from substrate.cross_org_classifier import (
    OrgMember,
    OrgSubstrateModeResult,
    classify_org,
)
from substrate.types import SubstrateMode

def _m(eid: str, etype: str, mode: SubstrateMode) -> OrgMember:
    return OrgMember(entity_id=eid, entity_type=etype, substrate_mode=mode)

class TestEdgeCases:
    def test_empty_org(self) -> None:
        r = classify_org("org-1", [])
        assert r.member_count == 0
        assert r.aggregate_mode is SubstrateMode.UNKNOWN
        assert r.long_cycle_fraction == 0.0
        assert r.short_cycle_fraction == 0.0
        assert r.cohesion_score == 0.0
        assert not r.is_substrate_aligned
        assert not r.is_drifted

    def test_empty_org_id_raises(self) -> None:
        with pytest.raises(ValueError, match="org_id"):
            classify_org("", [])

    def test_empty_entity_id_raises(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            OrgMember(
                entity_id="", entity_type="agent",
                substrate_mode=SubstrateMode.LONG_CYCLE,
            )

    def test_empty_entity_type_raises(self) -> None:
        with pytest.raises(ValueError, match="entity_type"):
            OrgMember(
                entity_id="e-1", entity_type="",
                substrate_mode=SubstrateMode.LONG_CYCLE,
            )

class TestAggregateMode:
    def test_all_long_cycle(self) -> None:
        members = [_m(f"e{i}", "agent", SubstrateMode.LONG_CYCLE) for i in range(5)]
        r = classify_org("org-1", members)
        assert r.aggregate_mode is SubstrateMode.LONG_CYCLE
        assert r.long_cycle_fraction == 1.0
        assert r.cohesion_score == 1.0
        assert r.is_substrate_aligned
        assert not r.is_drifted

    def test_all_short_cycle(self) -> None:
        members = [_m(f"e{i}", "agent", SubstrateMode.SHORT_CYCLE) for i in range(5)]
        r = classify_org("org-1", members)
        assert r.aggregate_mode is SubstrateMode.SHORT_CYCLE
        assert r.short_cycle_fraction == 1.0
        assert r.is_drifted
        assert not r.is_substrate_aligned

    def test_strict_plurality_long_cycle(self) -> None:
        members = [
            _m("e1", "agent", SubstrateMode.LONG_CYCLE),
            _m("e2", "agent", SubstrateMode.LONG_CYCLE),
            _m("e3", "agent", SubstrateMode.LONG_CYCLE),
            _m("e4", "agent", SubstrateMode.SHORT_CYCLE),
            _m("e5", "agent", SubstrateMode.MIXED),
        ]
        r = classify_org("org-1", members)
        assert r.aggregate_mode is SubstrateMode.LONG_CYCLE
        assert r.cohesion_score == pytest.approx(3 / 5)

    def test_tie_resolves_to_mixed(self) -> None:
        members = [
            _m("e1", "agent", SubstrateMode.LONG_CYCLE),
            _m("e2", "agent", SubstrateMode.LONG_CYCLE),
            _m("e3", "agent", SubstrateMode.SHORT_CYCLE),
            _m("e4", "agent", SubstrateMode.SHORT_CYCLE),
        ]
        r = classify_org("org-1", members)
        assert r.aggregate_mode is SubstrateMode.MIXED

    def test_all_unknown(self) -> None:
        members = [_m(f"e{i}", "agent", SubstrateMode.UNKNOWN) for i in range(3)]
        r = classify_org("org-1", members)
        assert r.aggregate_mode is SubstrateMode.UNKNOWN
        assert r.unknown_fraction == 1.0

class TestDistribution:
    def test_fractions_sum_to_one(self) -> None:
        members = [
            _m("e1", "agent", SubstrateMode.LONG_CYCLE),
            _m("e2", "cell", SubstrateMode.SHORT_CYCLE),
            _m("e3", "user", SubstrateMode.MIXED),
            _m("e4", "agent", SubstrateMode.UNKNOWN),
        ]
        r = classify_org("org-1", members)
        total = (
            r.long_cycle_fraction
            + r.short_cycle_fraction
            + r.mixed_fraction
            + r.unknown_fraction
        )
        assert total == pytest.approx(1.0)

class TestDeduplication:
    def test_duplicate_entity_skipped(self) -> None:
        members = [
            _m("e1", "agent", SubstrateMode.LONG_CYCLE),
            _m("e1", "agent", SubstrateMode.SHORT_CYCLE),  # same key — skipped
            _m("e2", "agent", SubstrateMode.LONG_CYCLE),
        ]
        r = classify_org("org-1", members)
        assert r.member_count == 2
        assert r.long_cycle_fraction == 1.0

    def test_same_id_different_type_allowed(self) -> None:
        members = [
            _m("e1", "agent", SubstrateMode.LONG_CYCLE),
            _m("e1", "cell", SubstrateMode.SHORT_CYCLE),
        ]
        r = classify_org("org-1", members)
        assert r.member_count == 2
        assert r.aggregate_mode is SubstrateMode.MIXED  # tie

class TestCohesion:
    def test_unanimous_is_one(self) -> None:
        members = [_m(f"e{i}", "agent", SubstrateMode.LONG_CYCLE) for i in range(4)]
        assert classify_org("org-1", members).cohesion_score == 1.0

    def test_split_even_is_quarter(self) -> None:
        members = [
            _m("e1", "agent", SubstrateMode.LONG_CYCLE),
            _m("e2", "agent", SubstrateMode.SHORT_CYCLE),
            _m("e3", "agent", SubstrateMode.MIXED),
            _m("e4", "agent", SubstrateMode.UNKNOWN),
        ]
        assert classify_org("org-1", members).cohesion_score == 0.25

class TestReasoning:
    def test_includes_org_id(self) -> None:
        members = [_m("e1", "agent", SubstrateMode.LONG_CYCLE)]
        r = classify_org("org-7", members)
        assert "org=org-7" in r.reasoning

    def test_empty_reasoning(self) -> None:
        r = classify_org("org-7", [])
        assert "no members" in r.reasoning

class TestResultIsImmutable:
    def test_frozen(self) -> None:
        r = classify_org("org-1", [])
        with pytest.raises(Exception):
            r.org_id = "x"

    def test_dataclass_fields(self) -> None:
        r = OrgSubstrateModeResult(
            org_id="o",
            member_count=0,
            aggregate_mode=SubstrateMode.UNKNOWN,
            long_cycle_fraction=0.0,
            short_cycle_fraction=0.0,
            mixed_fraction=0.0,
            unknown_fraction=0.0,
            cohesion_score=0.0,
            reasoning="",
        )
        assert r.aggregate_mode is SubstrateMode.UNKNOWN
