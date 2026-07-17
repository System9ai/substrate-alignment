"""Guard relaxation curve: Companion #2

Pure-logic curve defining how accumulated peer-trust unlocks guard
relaxation over sustained substrate-aligned operation. The companion
plan insight is that guards must not abruptly unlock on a single
high-trust signal; relaxation requires sustained trust across a
minimum number of cycles, gated also by evidence-trust quality from
the SubstrateStateEvidenceTrustScorer.

The curve maps ``(sustained_trust_cycles, peer_trust, evidence_trust)
→ guard_relaxation_factor`` in [0, 1].

* 0.0 → guards at full strength (every action gated).
* 1.0 → guards fully relaxed (action proceeds without additional
  substrate-mode-reasoning).

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the inputs.
* Honest uncertainty: insufficient cycles surfaces as
  ``RELAXATION_INSUFFICIENT_DATA``; the relaxation factor is forced
  to 0.0 (full guards).
* The curve never exceeds the operator-set ``max_relaxation_factor``
  ceiling: relaxation is bounded by design.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Final

class GuardRelaxationVerdict(str, Enum):
    """Guard-relaxation verdict."""

    RELAXED = "relaxed"
    PARTIAL = "partial"
    NOT_RELAXED = "not_relaxed"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class GuardRelaxationInput:
    """Caller-supplied inputs to the guard-relaxation curve."""

    entity_id: str
    sustained_trust_cycles: int
    peer_trust_score: float
    evidence_trust_score: float

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if self.sustained_trust_cycles < 0:
            raise ValueError(
                "sustained_trust_cycles must be >= 0"
            )
        if not 0.0 <= self.peer_trust_score <= 1.0:
            raise ValueError(
                "peer_trust_score must be in [0, 1]"
            )
        if not 0.0 <= self.evidence_trust_score <= 1.0:
            raise ValueError(
                "evidence_trust_score must be in [0, 1]"
            )

@dataclass(frozen=True, slots=True)
class GuardRelaxationConfig:
    """Operator-tunable curve parameters."""

    min_cycles_for_relaxation: int = 5
    cycles_saturation: int = 30
    min_peer_trust: float = 0.5
    min_evidence_trust: float = 0.5
    max_relaxation_factor: float = 0.7
    """Ceiling: guards never fully relax."""

    partial_threshold: float = 0.3
    relaxed_threshold: float = 0.6

    def __post_init__(self) -> None:
        if self.min_cycles_for_relaxation < 1:
            raise ValueError("min_cycles_for_relaxation must be >= 1")
        if self.cycles_saturation <= self.min_cycles_for_relaxation:
            raise ValueError(
                "cycles_saturation must exceed min_cycles_for_relaxation"
            )
        if not 0.0 <= self.min_peer_trust <= 1.0:
            raise ValueError("min_peer_trust must be in [0, 1]")
        if not 0.0 <= self.min_evidence_trust <= 1.0:
            raise ValueError("min_evidence_trust must be in [0, 1]")
        if not 0.0 < self.max_relaxation_factor < 1.0:
            raise ValueError(
                "max_relaxation_factor must be in (0, 1): "
                "full relaxation is disallowed by design"
            )
        if not 0.0 < self.partial_threshold < self.relaxed_threshold:
            raise ValueError(
                "must satisfy 0 < partial_threshold < relaxed_threshold"
            )
        if self.relaxed_threshold > self.max_relaxation_factor:
            raise ValueError(
                "relaxed_threshold cannot exceed max_relaxation_factor"
            )

DEFAULT_GUARD_RELAXATION_CONFIG: Final[GuardRelaxationConfig] = (
    GuardRelaxationConfig()
)

@dataclass(frozen=True, slots=True)
class GuardRelaxationOutput:  # pylint: disable=too-many-instance-attributes
    """Guard-relaxation curve output."""

    entity_id: str
    verdict: GuardRelaxationVerdict
    relaxation_factor: float
    sustained_trust_cycles: int
    peer_trust_score: float
    evidence_trust_score: float
    rationale: str

    @property
    def relaxed(self) -> bool:
        """True iff guards have meaningfully relaxed."""
        return self.verdict in (
            GuardRelaxationVerdict.PARTIAL,
            GuardRelaxationVerdict.RELAXED,
        )

class GuardRelaxationCurve:  # pylint: disable=too-few-public-methods
    """Pure-logic guard-relaxation curve (Companion #2)."""

    def __init__(
        self,
        *,
        config: GuardRelaxationConfig = DEFAULT_GUARD_RELAXATION_CONFIG,
    ) -> None:
        self._config = config

    def evaluate(
        self, input_: GuardRelaxationInput,
    ) -> GuardRelaxationOutput:
        """Evaluate the curve."""
        cfg = self._config
        if input_.sustained_trust_cycles < cfg.min_cycles_for_relaxation:
            return GuardRelaxationOutput(
                entity_id=input_.entity_id,
                verdict=GuardRelaxationVerdict.INSUFFICIENT_DATA,
                relaxation_factor=0.0,
                sustained_trust_cycles=input_.sustained_trust_cycles,
                peer_trust_score=input_.peer_trust_score,
                evidence_trust_score=input_.evidence_trust_score,
                rationale=(
                    f"cycles={input_.sustained_trust_cycles} below "
                    f"min {cfg.min_cycles_for_relaxation}"
                ),
            )
        if (
            input_.peer_trust_score < cfg.min_peer_trust
            or input_.evidence_trust_score < cfg.min_evidence_trust
        ):
            return GuardRelaxationOutput(
                entity_id=input_.entity_id,
                verdict=GuardRelaxationVerdict.NOT_RELAXED,
                relaxation_factor=0.0,
                sustained_trust_cycles=input_.sustained_trust_cycles,
                peer_trust_score=input_.peer_trust_score,
                evidence_trust_score=input_.evidence_trust_score,
                rationale=(
                    f"peer_trust={input_.peer_trust_score:.3f} or "
                    f"evidence_trust={input_.evidence_trust_score:.3f} "
                    f"below floor"
                ),
            )
        cycles_factor = min(
            1.0,
            math.log1p(
                input_.sustained_trust_cycles
                - cfg.min_cycles_for_relaxation
            )
            / math.log1p(
                cfg.cycles_saturation - cfg.min_cycles_for_relaxation
            ),
        )
        composite = (
            input_.peer_trust_score
            * input_.evidence_trust_score
            * cycles_factor
            * cfg.max_relaxation_factor
        )
        if composite >= cfg.relaxed_threshold:
            verdict = GuardRelaxationVerdict.RELAXED
        elif composite >= cfg.partial_threshold:
            verdict = GuardRelaxationVerdict.PARTIAL
        else:
            verdict = GuardRelaxationVerdict.NOT_RELAXED
        return GuardRelaxationOutput(
            entity_id=input_.entity_id,
            verdict=verdict,
            relaxation_factor=composite,
            sustained_trust_cycles=input_.sustained_trust_cycles,
            peer_trust_score=input_.peer_trust_score,
            evidence_trust_score=input_.evidence_trust_score,
            rationale=(
                f"cycles_factor={cycles_factor:.3f} * "
                f"peer={input_.peer_trust_score:.3f} * "
                f"evidence={input_.evidence_trust_score:.3f} * "
                f"ceiling={cfg.max_relaxation_factor:.3f} "
                f"= {composite:.3f}"
            ),
        )

__all__ = [
    "DEFAULT_GUARD_RELAXATION_CONFIG",
    "GuardRelaxationConfig",
    "GuardRelaxationCurve",
    "GuardRelaxationInput",
    "GuardRelaxationOutput",
    "GuardRelaxationVerdict",
]
