"""Tests for TierProgressionEngine."""
from __future__ import annotations

import pytest

from substrate.progression.model import (
    EntityLayer,
    StreakState,
    SubstrateStateTrajectoryProgression,
)
from substrate.progression.tier_engine import (
    DEFAULT_TIER_ENGINE_CONFIG,
    TierEngineConfig,
    TierProgressionEngine,
    build_tier_table,
    multiplicative_tier_thresholds,
)

class TestConfig:
    def test_defaults(self) -> None:
        c = TierEngineConfig()
        assert c.ratio == 2.0

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("base_threshold", 0.0, "base_threshold"),
            ("ratio", 1.0, "ratio"),
            ("ratio", 0.5, "ratio"),
        ],
    )
    def test_bad(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            TierEngineConfig(**{field: value})

class TestThresholds:
    def test_default_ratio_2(self) -> None:
        out = multiplicative_tier_thresholds(4)
        assert out == (100.0, 200.0, 400.0, 800.0)

    def test_custom_ratio(self) -> None:
        out = multiplicative_tier_thresholds(
            3, config=TierEngineConfig(base_threshold=50.0, ratio=3.0),
        )
        assert out == (50.0, 150.0, 450.0)

    def test_count_floor(self) -> None:
        with pytest.raises(ValueError, match="count"):
            multiplicative_tier_thresholds(0)

class TestBuildTierTable:
    def test_basic(self) -> None:
        table = build_tier_table(tier_names=("Bronze", "Silver", "Gold"))
        assert len(table) == 3
        assert table[0].tier_name == "Bronze"
        # Tier 0 is starter (threshold 0); tiers 1+ use multiplicative thresholds.
        assert table[0].threshold_quantity == 0.0
        assert table[1].threshold_quantity == 100.0
        assert table[2].threshold_quantity == 200.0

    def test_capabilities(self) -> None:
        table = build_tier_table(
            tier_names=("Bronze", "Silver"),
            capabilities_by_tier=(("read",), ("read", "write")),
        )
        assert table[1].capabilities_unlocked == ("read", "write")

    def test_capabilities_length_mismatch(self) -> None:
        with pytest.raises(ValueError, match="align"):
            build_tier_table(
                tier_names=("Bronze", "Silver"),
                capabilities_by_tier=(("read",),),
            )

    def test_empty_names_rejected(self) -> None:
        with pytest.raises(ValueError, match="tier_names"):
            build_tier_table(tier_names=())

class TestEngine:
    def setup_method(self) -> None:
        self.table = build_tier_table(
            tier_names=("Tier 0", "Tier 1", "Tier 2", "Tier 3"),
        )
        self.engine = TierProgressionEngine(tier_table=self.table)

    def test_empty_table_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            TierProgressionEngine(tier_table=())

    def test_resolve_tier_floor(self) -> None:
        assert self.engine.resolve_tier_for_progress(0.0) == 0

    def test_resolve_tier_mid(self) -> None:
        assert self.engine.resolve_tier_for_progress(150.0) == 1

    def test_resolve_tier_top(self) -> None:
        # 4 tiers with thresholds (0, 100, 200, 400); 1M reaches top tier 3.
        assert self.engine.resolve_tier_for_progress(1_000_000.0) == 3

    def test_resolve_tier_single_transition(self) -> None:
        # progress=150 with thresholds (0, 100, 200, 400) → tier 1
        assert self.engine.resolve_tier_for_progress(150.0) == 1

    def test_resolve_bad_progress(self) -> None:
        with pytest.raises(ValueError, match="accumulated_progress"):
            self.engine.resolve_tier_for_progress(-1.0)

    def test_apply_progress_no_transition(self) -> None:
        snapshot = SubstrateStateTrajectoryProgression(
            entity_id="agent-1", entity_layer=EntityLayer.NODE,
            current_tier_index=0, accumulated_progress_quantity=50.0,
            progress_to_next_tier=50.0,
            consolidation_history=(),
            streak_state=StreakState(
                streak_kind="daily-login", consecutive_count=0,
                last_increment_at_epoch=0.0,
            ),
            achievements_earned=(),
            progression_momentum=0.0,
        )
        transition, updated = self.engine.apply_progress(
            snapshot=snapshot, new_event_id_prefix="evt", epoch=100.0,
        )
        assert not transition.is_transition
        assert updated.current_tier_index == 0
        assert updated.progress_to_next_tier == 50.0
        assert not updated.has_history

    def test_apply_progress_single_transition(self) -> None:
        snapshot = SubstrateStateTrajectoryProgression(
            entity_id="agent-1", entity_layer=EntityLayer.NODE,
            current_tier_index=0, accumulated_progress_quantity=150.0,
            progress_to_next_tier=0.0,
            consolidation_history=(),
            streak_state=StreakState(
                streak_kind="daily-login", consecutive_count=0,
                last_increment_at_epoch=0.0,
            ),
            achievements_earned=(),
            progression_momentum=0.0,
        )
        transition, updated = self.engine.apply_progress(
            snapshot=snapshot, new_event_id_prefix="evt", epoch=100.0,
        )
        assert transition.is_transition
        assert transition.to_tier_index == 1
        assert len(updated.consolidation_history) == 1
        assert updated.consolidation_history[0].to_tier_index == 1

    def test_apply_progress_multi_transition(self) -> None:
        # 4 tiers with thresholds (0, 100, 200, 400). Progress 250
        # crosses thresholds for tier 1 and tier 2.
        snapshot = SubstrateStateTrajectoryProgression(
            entity_id="agent-1", entity_layer=EntityLayer.NODE,
            current_tier_index=0, accumulated_progress_quantity=250.0,
            progress_to_next_tier=0.0,
            consolidation_history=(),
            streak_state=StreakState(
                streak_kind="daily-login", consecutive_count=0,
                last_increment_at_epoch=0.0,
            ),
            achievements_earned=(),
            progression_momentum=0.0,
        )
        transition, updated = self.engine.apply_progress(
            snapshot=snapshot, new_event_id_prefix="evt", epoch=100.0,
        )
        assert transition.from_tier_index == 0
        assert transition.to_tier_index == 2
        assert len(transition.crossed_thresholds) == 2
        assert updated.current_tier_index == 2

    def test_apply_progress_bad_prefix(self) -> None:
        snapshot = SubstrateStateTrajectoryProgression(
            entity_id="agent-1", entity_layer=EntityLayer.NODE,
            current_tier_index=0, accumulated_progress_quantity=50.0,
            progress_to_next_tier=50.0,
            consolidation_history=(),
            streak_state=StreakState(
                streak_kind="x", consecutive_count=0,
                last_increment_at_epoch=0.0,
            ),
            achievements_earned=(), progression_momentum=0.0,
        )
        with pytest.raises(ValueError, match="prefix"):
            self.engine.apply_progress(
                snapshot=snapshot, new_event_id_prefix="", epoch=100.0,
            )

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert DEFAULT_TIER_ENGINE_CONFIG.ratio == 2.0

    def test_tier_table_property(self) -> None:
        table = build_tier_table(tier_names=("A", "B"))
        engine = TierProgressionEngine(tier_table=table)
        assert engine.tier_table == table
