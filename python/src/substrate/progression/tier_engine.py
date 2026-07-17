"""Tier-progression engine.

Pure-logic engine that:

1. Produces multiplicatively-spaced tier thresholds.
2. Resolves which tier an entity belongs to given accumulated progress.
3. Computes a :class:`TierTransition` when accumulated progress would
   bridge one or more tier thresholds.

Multiplicatively-spaced thresholds match the substrate-efficient stacking
pattern documented across video games, martial arts belt systems, and
academic degree progressions: the threshold for tier ``k+1`` is
``base_threshold * (ratio ** k)``.

The engine is **stateless**; the caller threads the previous
:class:`SubstrateStateTrajectoryProgression` snapshot through.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional, Sequence

from substrate.progression.model import (
    ConsolidationEvent,
    ConsolidationTier,
    SubstrateStateTrajectoryProgression,
)

@dataclass(frozen=True, slots=True)
class TierEngineConfig:
    """Operator-tunable tier-engine parameters."""

    base_threshold: float = 100.0
    ratio: float = 2.0
    """Multiplicative ratio between consecutive tier thresholds."""

    def __post_init__(self) -> None:
        if self.base_threshold <= 0:
            raise ValueError("base_threshold must be > 0")
        if self.ratio <= 1.0:
            raise ValueError(
                "ratio must be > 1.0 (multiplicative spacing requires "
                "expansion, not contraction)"
            )

DEFAULT_TIER_ENGINE_CONFIG: Final[TierEngineConfig] = TierEngineConfig()

@dataclass(frozen=True, slots=True)
class TierTransition:
    """One transition decision."""

    from_tier_index: int
    to_tier_index: int
    crossed_thresholds: tuple[float, ...]
    progress_remaining_in_new_tier: float

    @property
    def is_transition(self) -> bool:
        """True iff the to-tier differs from the from-tier."""
        return self.to_tier_index != self.from_tier_index

def multiplicative_tier_thresholds(
    count: int,
    *,
    config: TierEngineConfig = DEFAULT_TIER_ENGINE_CONFIG,
) -> tuple[float, ...]:
    """Produce the first ``count`` tier thresholds multiplicatively."""
    if count < 1:
        raise ValueError("count must be >= 1")
    return tuple(
        config.base_threshold * (config.ratio ** k)
        for k in range(count)
    )

def build_tier_table(
    *,
    tier_names: Sequence[str],
    capabilities_by_tier: Optional[Sequence[Sequence[str]]] = None,
    config: TierEngineConfig = DEFAULT_TIER_ENGINE_CONFIG,
) -> tuple[ConsolidationTier, ...]:
    """Build a typed tier table from names + optional per-tier capabilities.

    Tier 0 is the starter tier (threshold 0). Tier ``k`` for ``k >= 1``
    has threshold ``base_threshold * ratio**(k-1)``. An entity is "in
    tier k" when ``accumulated_progress >= tier_table[k].threshold_quantity``
    and (for k < N-1) ``< tier_table[k+1].threshold_quantity``.
    """
    if not tier_names:
        raise ValueError("tier_names must be non-empty")
    n = len(tier_names)
    if n == 1:
        thresholds: tuple[float, ...] = (0.0,)
    else:
        thresholds = (0.0,) + multiplicative_tier_thresholds(
            n - 1, config=config,
        )
    caps: Sequence[Sequence[str]]
    if capabilities_by_tier is None:
        caps = [() for _ in tier_names]
    else:
        if len(capabilities_by_tier) != len(tier_names):
            raise ValueError(
                "capabilities_by_tier must align with tier_names"
            )
        caps = capabilities_by_tier
    return tuple(
        ConsolidationTier(
            tier_id=f"tier-{index}",
            tier_name=name,
            tier_index=index,
            threshold_quantity=thresholds[index],
            capabilities_unlocked=tuple(caps[index]),
        )
        for index, name in enumerate(tier_names)
    )

class TierProgressionEngine:  # pylint: disable=too-few-public-methods
    """Pure-logic engine: resolves tier transitions."""

    def __init__(
        self,
        *,
        tier_table: tuple[ConsolidationTier, ...],
        config: TierEngineConfig = DEFAULT_TIER_ENGINE_CONFIG,
    ) -> None:
        if not tier_table:
            raise ValueError("tier_table must be non-empty")
        if any(
            tier_table[i].threshold_quantity
            >= tier_table[i + 1].threshold_quantity
            for i in range(len(tier_table) - 1)
        ):
            raise ValueError(
                "tier_table thresholds must be strictly ascending"
            )
        self._tier_table = tier_table
        self._config = config

    @property
    def tier_table(self) -> tuple[ConsolidationTier, ...]:
        """Snapshot of the configured tier table."""
        return self._tier_table

    def resolve_tier_for_progress(
        self, accumulated_progress: float,
    ) -> int:
        """Return the tier index for ``accumulated_progress``.

        Tier 0 is the starter tier (threshold 0). The entity is in
        tier ``k`` when ``accumulated_progress >= tier_table[k].threshold_quantity``
        and (for k < N-1) less than ``tier_table[k+1].threshold_quantity``.
        """
        if accumulated_progress < 0:
            raise ValueError(
                "accumulated_progress must be >= 0"
            )
        result = 0
        for tier in self._tier_table:
            if accumulated_progress >= tier.threshold_quantity:
                result = tier.tier_index
            else:
                break
        return result

    def apply_progress(
        self,
        *,
        snapshot: SubstrateStateTrajectoryProgression,
        new_event_id_prefix: str,
        epoch: float,
    ) -> tuple[
        TierTransition,
        SubstrateStateTrajectoryProgression,
    ]:
        """Compute the new snapshot after ``accumulated_progress`` reaches new value.

        The caller provides a snapshot whose
        ``accumulated_progress_quantity`` is the *target* value (after this
        step's progress is folded in). The engine returns the
        :class:`TierTransition` plus the updated snapshot with refreshed
        ``current_tier_index``, ``progress_to_next_tier``, and
        ``consolidation_history``.
        """
        if not new_event_id_prefix:
            raise ValueError("new_event_id_prefix must be non-empty")
        if epoch < 0:
            raise ValueError("epoch must be >= 0")
        progress = snapshot.accumulated_progress_quantity
        from_index = snapshot.current_tier_index
        to_index = self.resolve_tier_for_progress(progress)
        next_threshold = self._next_threshold(to_index)
        progress_remaining = max(0.0, next_threshold - progress)
        crossed: list[float] = []
        new_events: list[ConsolidationEvent] = list(
            snapshot.consolidation_history,
        )
        if to_index > from_index:
            for tier_idx in range(from_index, to_index):
                # Threshold that was crossed to enter tier_idx + 1.
                crossed.append(
                    self._tier_table[tier_idx + 1].threshold_quantity,
                )
            new_events.append(ConsolidationEvent(
                event_id=f"{new_event_id_prefix}-{from_index}-to-{to_index}",
                from_tier_index=from_index,
                to_tier_index=to_index,
                transitioned_at_epoch=epoch,
                progress_at_transition=progress,
            ))
        transition = TierTransition(
            from_tier_index=from_index,
            to_tier_index=to_index,
            crossed_thresholds=tuple(crossed),
            progress_remaining_in_new_tier=progress_remaining,
        )
        updated = SubstrateStateTrajectoryProgression(
            entity_id=snapshot.entity_id,
            entity_layer=snapshot.entity_layer,
            current_tier_index=to_index,
            accumulated_progress_quantity=progress,
            progress_to_next_tier=progress_remaining,
            consolidation_history=tuple(new_events),
            streak_state=snapshot.streak_state,
            achievements_earned=snapshot.achievements_earned,
            progression_momentum=snapshot.progression_momentum,
        )
        return transition, updated

    def _next_threshold(self, current_tier_index: int) -> float:
        if current_tier_index + 1 < len(self._tier_table):
            return self._tier_table[
                current_tier_index + 1
            ].threshold_quantity
        # Already at top tier: return current threshold * ratio as
        # the stretch goal beyond the visible ladder.
        top_threshold = self._tier_table[-1].threshold_quantity
        if top_threshold <= 0:
            # Single-tier ladder degenerate case: there is no next.
            return 0.0
        return top_threshold * self._config.ratio

__all__ = [
    "DEFAULT_TIER_ENGINE_CONFIG",
    "TierEngineConfig",
    "TierProgressionEngine",
    "TierTransition",
    "build_tier_table",
    "multiplicative_tier_thresholds",
]
