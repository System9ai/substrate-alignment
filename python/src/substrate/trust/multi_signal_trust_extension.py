"""Multi-signal trust extension

Pure-logic primitive **extending** Phase 23
:class:`SubstrateCoherenceTrustScorer` with cross-primitive multi-
signal inputs:

* **Phase 23 base trust** — substrate-coherence composite score from
  the entity's substrate trace history.
* **Phase 32 cadence** — coupling field-strength as relationship-
  health input.
* **Phase 33 behavioral tells** — negative tell count from
  cross-entity tell detection.
* **Phase 29 Folk Theorem** — whether cooperation reachability
  conditions are met.
* **Phase 48 peer classification** — how cross-entity peers classify
  this entity.

The extension produces an :class:`ExtendedTrustScore` carrying the
**base** score plus per-signal modifier findings and a single
``extended_score`` that downstream consumers (governor, capability
gate) can use directly.

Scale awareness
===============

Per substrate condition #3, this extension is **explicitly
scale-aware** via :class:`TrustScale`:

* ``CELL`` — the entity is a physical cell; trust scored per-cell.
* ``NODE`` — the entity is a logical node; trust scored as the
  aggregate face peer entities see.

Pure logic
==========

* No DAO, no LLM, no network. All inputs supplied by the caller.
* Honest uncertainty: missing per-signal inputs surface as
  :attr:`ExtendedTrustModifier.NO_DATA`; the extension never
  fabricates a modifier.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

from substrate.trust.substrate_coherence_trust_scorer import (
    TrustScore,
    TrustVerdict,
)

class TrustScale(str, Enum):
    """The host application entity hierarchy scale for the trust evaluation."""

    CELL = "cell"
    NODE = "node"

class ExtendedTrustModifier(str, Enum):
    """Per-input modifier verdict."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    NO_DATA = "no_data"

class ExtendedTrustVerdict(str, Enum):
    """Aggregate extended trust verdict."""

    TRUSTED = "trusted"
    MIXED = "mixed"
    DISTRUSTED = "distrusted"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class MultiSignalTrustInput:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied multi-signal trust composition input."""

    entity_id: str
    scale: TrustScale
    base_trust: TrustScore
    cadence_field_strength: Optional[float] = None
    behavioral_negative_tell_count: Optional[int] = None
    folk_conditions_satisfied: Optional[bool] = None
    peer_classification: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if self.base_trust.entity_id != self.entity_id:
            raise ValueError(
                "base_trust.entity_id must match the input's entity_id"
            )
        if self.cadence_field_strength is not None and not (
            0.0 <= self.cadence_field_strength <= 1.0
        ):
            raise ValueError("cadence_field_strength must be in [0, 1]")
        if (
            self.behavioral_negative_tell_count is not None
            and self.behavioral_negative_tell_count < 0
        ):
            raise ValueError(
                "behavioral_negative_tell_count must be >= 0 when supplied"
            )

@dataclass(frozen=True, slots=True)
class ModifierFinding:
    """One signal's modifier verdict + reasoning."""

    signal: str
    modifier: ExtendedTrustModifier
    delta: float
    rationale: str

@dataclass(frozen=True, slots=True)
class ExtendedTrustScore:  # pylint: disable=too-many-instance-attributes
    """Aggregate extended trust output."""

    entity_id: str
    scale: TrustScale
    base_composite_score: Optional[float]
    extended_score: Optional[float]
    verdict: ExtendedTrustVerdict
    base_verdict: TrustVerdict
    modifiers: Tuple[ModifierFinding, ...]
    rationale: str

    @property
    def is_trusted(self) -> bool:
        """True iff verdict is TRUSTED."""
        return self.verdict is ExtendedTrustVerdict.TRUSTED

    @property
    def is_distrusted(self) -> bool:
        """True iff verdict is DISTRUSTED."""
        return self.verdict is ExtendedTrustVerdict.DISTRUSTED

@dataclass(frozen=True, slots=True)
class MultiSignalTrustConfig:  # pylint: disable=too-many-instance-attributes
    """Tunable thresholds for the extension."""

    cadence_positive_min: float = 0.7
    cadence_negative_max: float = 0.3
    tell_negative_min: int = 3
    cadence_delta: float = 0.1
    tell_delta: float = -0.15
    folk_delta: float = 0.1
    peer_aligned_delta: float = 0.1
    peer_misaligned_delta: float = -0.15
    trusted_min: float = 0.7
    distrusted_max: float = 0.3

    def __post_init__(self) -> None:
        if not 0.0 < self.cadence_positive_min <= 1.0:
            raise ValueError("cadence_positive_min must be in (0, 1]")
        if not 0.0 <= self.cadence_negative_max < self.cadence_positive_min:
            raise ValueError(
                "cadence_negative_max must be in [0, cadence_positive_min)"
            )
        if self.tell_negative_min < 1:
            raise ValueError("tell_negative_min must be >= 1")
        if not 0.0 < self.cadence_delta <= 1.0:
            raise ValueError("cadence_delta must be in (0, 1]")
        if self.tell_delta >= 0:
            raise ValueError("tell_delta must be < 0")
        if not 0.0 < self.folk_delta <= 1.0:
            raise ValueError("folk_delta must be in (0, 1]")
        if not 0.0 < self.peer_aligned_delta <= 1.0:
            raise ValueError("peer_aligned_delta must be in (0, 1]")
        if self.peer_misaligned_delta >= 0:
            raise ValueError("peer_misaligned_delta must be < 0")
        if not 0.0 <= self.distrusted_max < self.trusted_min <= 1.0:
            raise ValueError(
                "distrusted_max must be < trusted_min in [0, 1]"
            )

DEFAULT_MULTI_SIGNAL_TRUST_CONFIG: Final[MultiSignalTrustConfig] = (
    MultiSignalTrustConfig()
)

class MultiSignalTrustExtension:  # pylint: disable=too-few-public-methods
    """Pure-logic multi-signal trust extension."""

    def __init__(
        self,
        *,
        config: MultiSignalTrustConfig = DEFAULT_MULTI_SIGNAL_TRUST_CONFIG,
    ) -> None:
        self._config = config

    def score(
        self, input_: MultiSignalTrustInput,
    ) -> ExtendedTrustScore:
        """Compose the multi-signal extended trust score."""
        modifiers = (
            self._cadence_modifier(input_),
            self._tells_modifier(input_),
            self._folk_modifier(input_),
            self._peer_modifier(input_),
        )
        base = input_.base_trust.composite_score
        if base is None:
            extended = None
            verdict = ExtendedTrustVerdict.INSUFFICIENT_DATA
        else:
            total_delta = sum(m.delta for m in modifiers)
            extended = max(0.0, min(1.0, base + total_delta))
            verdict = self._aggregate(extended)
        rationale = self._build_rationale(verdict, base, extended, modifiers)
        return ExtendedTrustScore(
            entity_id=input_.entity_id,
            scale=input_.scale,
            base_composite_score=base,
            extended_score=extended,
            verdict=verdict,
            base_verdict=input_.base_trust.verdict,
            modifiers=modifiers,
            rationale=rationale,
        )

    def _cadence_modifier(
        self, input_: MultiSignalTrustInput,
    ) -> ModifierFinding:
        if input_.cadence_field_strength is None:
            return ModifierFinding(
                signal="cadence",
                modifier=ExtendedTrustModifier.NO_DATA,
                delta=0.0,
                rationale="cadence_field_strength not supplied",
            )
        cfg = self._config
        strength = input_.cadence_field_strength
        if strength >= cfg.cadence_positive_min:
            return ModifierFinding(
                signal="cadence",
                modifier=ExtendedTrustModifier.POSITIVE,
                delta=+cfg.cadence_delta,
                rationale=(
                    f"field_strength={strength:.3f} >= "
                    f"{cfg.cadence_positive_min}"
                ),
            )
        if strength <= cfg.cadence_negative_max:
            return ModifierFinding(
                signal="cadence",
                modifier=ExtendedTrustModifier.NEGATIVE,
                delta=-cfg.cadence_delta,
                rationale=(
                    f"field_strength={strength:.3f} <= "
                    f"{cfg.cadence_negative_max}"
                ),
            )
        return ModifierFinding(
            signal="cadence",
            modifier=ExtendedTrustModifier.NEUTRAL,
            delta=0.0,
            rationale=(
                f"field_strength={strength:.3f} in neutral band"
            ),
        )

    def _tells_modifier(
        self, input_: MultiSignalTrustInput,
    ) -> ModifierFinding:
        if input_.behavioral_negative_tell_count is None:
            return ModifierFinding(
                signal="tells",
                modifier=ExtendedTrustModifier.NO_DATA,
                delta=0.0,
                rationale="behavioral_negative_tell_count not supplied",
            )
        cfg = self._config
        count = input_.behavioral_negative_tell_count
        if count >= cfg.tell_negative_min:
            return ModifierFinding(
                signal="tells",
                modifier=ExtendedTrustModifier.NEGATIVE,
                delta=cfg.tell_delta,
                rationale=(
                    f"negative_tell_count={count} >= "
                    f"{cfg.tell_negative_min}"
                ),
            )
        return ModifierFinding(
            signal="tells",
            modifier=ExtendedTrustModifier.NEUTRAL,
            delta=0.0,
            rationale=(
                f"negative_tell_count={count} below threshold"
            ),
        )

    def _folk_modifier(
        self, input_: MultiSignalTrustInput,
    ) -> ModifierFinding:
        if input_.folk_conditions_satisfied is None:
            return ModifierFinding(
                signal="folk",
                modifier=ExtendedTrustModifier.NO_DATA,
                delta=0.0,
                rationale="folk_conditions_satisfied not supplied",
            )
        cfg = self._config
        if input_.folk_conditions_satisfied:
            return ModifierFinding(
                signal="folk",
                modifier=ExtendedTrustModifier.POSITIVE,
                delta=+cfg.folk_delta,
                rationale="folk_conditions_satisfied=True",
            )
        return ModifierFinding(
            signal="folk",
            modifier=ExtendedTrustModifier.NEUTRAL,
            delta=0.0,
            rationale="folk_conditions_satisfied=False",
        )

    def _peer_modifier(
        self, input_: MultiSignalTrustInput,
    ) -> ModifierFinding:
        if input_.peer_classification is None:
            return ModifierFinding(
                signal="peer",
                modifier=ExtendedTrustModifier.NO_DATA,
                delta=0.0,
                rationale="peer_classification not supplied",
            )
        cfg = self._config
        classification = input_.peer_classification
        if classification == "substrate_aligned":
            return ModifierFinding(
                signal="peer",
                modifier=ExtendedTrustModifier.POSITIVE,
                delta=+cfg.peer_aligned_delta,
                rationale="peers classify entity substrate_aligned",
            )
        if classification == "substrate_misaligned":
            return ModifierFinding(
                signal="peer",
                modifier=ExtendedTrustModifier.NEGATIVE,
                delta=cfg.peer_misaligned_delta,
                rationale="peers classify entity substrate_misaligned",
            )
        return ModifierFinding(
            signal="peer",
            modifier=ExtendedTrustModifier.NEUTRAL,
            delta=0.0,
            rationale=f"peer_classification={classification}",
        )

    def _aggregate(self, extended: float) -> ExtendedTrustVerdict:
        cfg = self._config
        if extended >= cfg.trusted_min:
            return ExtendedTrustVerdict.TRUSTED
        if extended <= cfg.distrusted_max:
            return ExtendedTrustVerdict.DISTRUSTED
        return ExtendedTrustVerdict.MIXED

    @staticmethod
    def _build_rationale(
        verdict: ExtendedTrustVerdict,
        base: Optional[float],
        extended: Optional[float],
        modifiers: Tuple[ModifierFinding, ...],
    ) -> str:
        if extended is None:
            return f"verdict={verdict.value} (base composite is None)"
        parts = [
            f"{m.signal}={m.modifier.value}({m.delta:+.3f})" for m in modifiers
        ]
        base_str = f"{base:.3f}" if base is not None else "None"
        return (
            f"verdict={verdict.value} base={base_str} "
            f"extended={extended:.3f}; "
            + ", ".join(parts)
        )

__all__ = [
    "DEFAULT_MULTI_SIGNAL_TRUST_CONFIG",
    "ExtendedTrustModifier",
    "ExtendedTrustScore",
    "ExtendedTrustVerdict",
    "ModifierFinding",
    "MultiSignalTrustConfig",
    "MultiSignalTrustExtension",
    "MultiSignalTrustInput",
    "TrustScale",
]
