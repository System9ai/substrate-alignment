"""Tests for progression model."""
from __future__ import annotations

import pytest

from substrate.progression.model import (
    ENTITY_LAYERS,
    AchievementRef,
    ConsolidationEvent,
    ConsolidationTier,
    EntityLayer,
    StreakState,
    SubstrateStateTrajectoryProgression,
)

def _tier(
    *, tid: str = "t-1", name: str = "Bronze", index: int = 0,
    threshold: float = 100.0, caps: tuple[str, ...] = (),
) -> ConsolidationTier:
    return ConsolidationTier(
        tier_id=tid, tier_name=name, tier_index=index,
        threshold_quantity=threshold, capabilities_unlocked=caps,
    )

def _event(
    *, eid: str = "e-1", frm: int = 0, to: int = 1, epoch: float = 1.0,
    progress: float = 100.0,
) -> ConsolidationEvent:
    return ConsolidationEvent(
        event_id=eid, from_tier_index=frm, to_tier_index=to,
        transitioned_at_epoch=epoch, progress_at_transition=progress,
    )

def _streak(
    *, kind: str = "daily-login", count: int = 0, at: float = 0.0,
) -> StreakState:
    return StreakState(
        streak_kind=kind, consecutive_count=count,
        last_increment_at_epoch=at,
    )

def _achievement(
    *, aid: str = "a-1", name: str = "First Tier", at: float = 0.0,
) -> AchievementRef:
    return AchievementRef(
        achievement_id=aid, achievement_name=name, earned_at_epoch=at,
    )

def _progression(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    entity: str = "agent-1",
    layer: EntityLayer = EntityLayer.NODE,
    tier: int = 0,
    progress: float = 0.0,
    remaining: float = 100.0,
    history: tuple[ConsolidationEvent, ...] = (),
    streak: StreakState | None = None,
    achievements: tuple[AchievementRef, ...] = (),
    momentum: float = 0.0,
) -> SubstrateStateTrajectoryProgression:
    return SubstrateStateTrajectoryProgression(
        entity_id=entity, entity_layer=layer,
        current_tier_index=tier,
        accumulated_progress_quantity=progress,
        progress_to_next_tier=remaining,
        consolidation_history=history,
        streak_state=streak or _streak(),
        achievements_earned=achievements,
        progression_momentum=momentum,
    )

class TestEnums:
    def test_entity_layer_set(self) -> None:
        assert ENTITY_LAYERS == {"cell", "node", "org"}

class TestConsolidationTier:
    def test_round_trip(self) -> None:
        t = _tier()
        assert t.tier_index == 0

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("tid", "", "tier_id"),
            ("name", "", "tier_name"),
            ("index", -1, "tier_index"),
            ("threshold", -1.0, "threshold_quantity"),
        ],
    )
    def test_bad(self, field: str, value: object, match: str) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _tier(**kwargs)

class TestConsolidationEvent:
    def test_round_trip(self) -> None:
        e = _event()
        assert e.to_tier_index == 1

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("eid", "", "event_id"),
            ("frm", -1, "from_tier_index"),
            ("epoch", -1.0, "transitioned_at_epoch"),
            ("progress", -1.0, "progress_at_transition"),
        ],
    )
    def test_bad(self, field: str, value: object, match: str) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _event(**kwargs)

    def test_to_must_exceed_from(self) -> None:
        with pytest.raises(ValueError, match="to_tier_index"):
            _event(frm=2, to=1)

class TestStreakState:
    def test_active_when_positive(self) -> None:
        s = _streak(count=3)
        assert s.active

    def test_inactive_when_zero(self) -> None:
        s = _streak(count=0)
        assert not s.active

    def test_bad_count(self) -> None:
        with pytest.raises(ValueError, match="consecutive_count"):
            _streak(count=-1)

class TestAchievementRef:
    def test_round_trip(self) -> None:
        a = _achievement()
        assert a.achievement_id == "a-1"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("aid", "", "achievement_id"),
            ("name", "", "achievement_name"),
            ("at", -1.0, "earned_at_epoch"),
        ],
    )
    def test_bad(self, field: str, value: object, match: str) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _achievement(**kwargs)

class TestProgression:
    def test_round_trip(self) -> None:
        p = _progression()
        assert not p.has_history
        assert not p.streak_active

    def test_with_history(self) -> None:
        p = _progression(history=(_event(epoch=1.0),))
        assert p.has_history

    def test_history_must_ascend_by_epoch(self) -> None:
        with pytest.raises(ValueError, match="ascending by epoch"):
            _progression(history=(
                _event(eid="e-1", frm=0, to=1, epoch=2.0),
                _event(eid="e-2", frm=1, to=2, epoch=1.0),
            ))

    def test_history_must_ascend_by_tier(self) -> None:
        with pytest.raises(ValueError, match="ascending by tier"):
            _progression(history=(
                _event(eid="e-1", frm=2, to=3, epoch=1.0),
                _event(eid="e-2", frm=0, to=1, epoch=2.0),
            ))

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("entity", "", "entity_id"),
            ("tier", -1, "current_tier_index"),
            ("progress", -1.0, "accumulated_progress_quantity"),
            ("remaining", -1.0, "progress_to_next_tier"),
            ("momentum", 1.5, "progression_momentum"),
            ("momentum", -1.5, "progression_momentum"),
        ],
    )
    def test_bad(self, field: str, value: object, match: str) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _progression(**kwargs)
