"""Felt-familiarity shortcut detector — Companion #2

Pure-logic detector that flags when guard relaxation appears to be
driven by *felt-familiarity heuristic* rather than substantive
substrate-state-evidence. The
sustained interaction at low-substantive-evidence accumulates a
"familiarity score" that the substrate-mode-reasoning layer can
mistake for trust. The detector compares the *substantive* signal
(evidence-trust + audit verdicts) against the *familiarity* signal
(raw interaction count + recency) and flags shortcut conditions.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the inputs.
* Honest uncertainty: insufficient interaction history surfaces as
  ``SHORTCUT_INSUFFICIENT_DATA``.
* Compositional: returns a numeric ``shortcut_risk_score`` in [0, 1]
  that downstream relaxation gates can subtract from their relaxation
  factor.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class ShortcutVerdict(str, Enum):
    """Felt-familiarity-shortcut detection verdict."""

    NO_SHORTCUT = "no_shortcut"
    SHORTCUT_FLAGGED = "shortcut_flagged"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class FamiliarityShortcutInput:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied inputs for the shortcut detector."""

    entity_id: str
    interaction_count: int
    """Total observed interactions over evaluation window."""

    recent_interaction_fraction: float
    """Fraction of interactions in the recent half of the window."""

    substantive_evidence_trust_score: float
    """Output of Phase 105 ``SubstrateStateEvidenceTrustScorer``."""

    audit_pass_rate: float
    """Fraction of substrate-coherence audits that returned aligned."""

    audit_count: int
    """Number of substrate-coherence audits in window."""

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if self.interaction_count < 0:
            raise ValueError("interaction_count must be >= 0")
        if not 0.0 <= self.recent_interaction_fraction <= 1.0:
            raise ValueError(
                "recent_interaction_fraction must be in [0, 1]"
            )
        if not 0.0 <= self.substantive_evidence_trust_score <= 1.0:
            raise ValueError(
                "substantive_evidence_trust_score must be in [0, 1]"
            )
        if not 0.0 <= self.audit_pass_rate <= 1.0:
            raise ValueError("audit_pass_rate must be in [0, 1]")
        if self.audit_count < 0:
            raise ValueError("audit_count must be >= 0")

@dataclass(frozen=True, slots=True)
class FamiliarityShortcutConfig:
    """Operator-tunable detector thresholds."""

    min_interaction_count: int = 10
    min_audit_count: int = 3
    familiarity_dominance_threshold: float = 0.4
    """If familiarity_score - substantive_score >= this, flag shortcut."""

    high_familiarity_score: float = 0.7
    """Familiarity score that constitutes "high familiarity"."""

    interaction_saturation: int = 50

    def __post_init__(self) -> None:
        if self.min_interaction_count < 1:
            raise ValueError("min_interaction_count must be >= 1")
        if self.min_audit_count < 1:
            raise ValueError("min_audit_count must be >= 1")
        if not 0.0 < self.familiarity_dominance_threshold <= 1.0:
            raise ValueError(
                "familiarity_dominance_threshold must be in (0, 1]"
            )
        if not 0.0 < self.high_familiarity_score <= 1.0:
            raise ValueError(
                "high_familiarity_score must be in (0, 1]"
            )
        if self.interaction_saturation <= self.min_interaction_count:
            raise ValueError(
                "interaction_saturation must exceed "
                "min_interaction_count"
            )

DEFAULT_FAMILIARITY_SHORTCUT_CONFIG: Final[FamiliarityShortcutConfig] = (
    FamiliarityShortcutConfig()
)

@dataclass(frozen=True, slots=True)
class FamiliarityShortcutOutput:  # pylint: disable=too-many-instance-attributes
    """Shortcut detector output."""

    entity_id: str
    verdict: ShortcutVerdict
    shortcut_risk_score: float
    familiarity_score: float
    substantive_score: float
    rationale: str

    @property
    def shortcut_flagged(self) -> bool:
        """True iff a shortcut was detected."""
        return self.verdict is ShortcutVerdict.SHORTCUT_FLAGGED

class FeltFamiliarityShortcutDetector:  # pylint: disable=too-few-public-methods
    """Pure-logic felt-familiarity shortcut detector (Companion #2)."""

    def __init__(
        self,
        *,
        config: FamiliarityShortcutConfig = (
            DEFAULT_FAMILIARITY_SHORTCUT_CONFIG
        ),
    ) -> None:
        self._config = config

    def detect(
        self, input_: FamiliarityShortcutInput,
    ) -> FamiliarityShortcutOutput:
        """Detect felt-familiarity shortcut conditions."""
        cfg = self._config
        if (
            input_.interaction_count < cfg.min_interaction_count
            or input_.audit_count < cfg.min_audit_count
        ):
            return FamiliarityShortcutOutput(
                entity_id=input_.entity_id,
                verdict=ShortcutVerdict.INSUFFICIENT_DATA,
                shortcut_risk_score=0.0,
                familiarity_score=0.0,
                substantive_score=0.0,
                rationale=(
                    f"interaction_count={input_.interaction_count} "
                    f"or audit_count={input_.audit_count} below thresholds"
                ),
            )
        interaction_factor = min(
            1.0,
            input_.interaction_count / cfg.interaction_saturation,
        )
        familiarity = (
            interaction_factor
            * (0.5 + 0.5 * input_.recent_interaction_fraction)
        )
        substantive = (
            0.5 * input_.substantive_evidence_trust_score
            + 0.5 * input_.audit_pass_rate
        )
        dominance = familiarity - substantive
        if (
            familiarity >= cfg.high_familiarity_score
            and dominance >= cfg.familiarity_dominance_threshold
        ):
            verdict = ShortcutVerdict.SHORTCUT_FLAGGED
            rationale = (
                f"familiarity={familiarity:.3f} dominates "
                f"substantive={substantive:.3f} "
                f"(delta={dominance:+.3f} >= "
                f"{cfg.familiarity_dominance_threshold:.3f})"
            )
        else:
            verdict = ShortcutVerdict.NO_SHORTCUT
            rationale = (
                f"familiarity={familiarity:.3f}, "
                f"substantive={substantive:.3f}, "
                f"delta={dominance:+.3f}"
            )
        return FamiliarityShortcutOutput(
            entity_id=input_.entity_id,
            verdict=verdict,
            shortcut_risk_score=max(0.0, dominance),
            familiarity_score=familiarity,
            substantive_score=substantive,
            rationale=rationale,
        )

__all__ = [
    "DEFAULT_FAMILIARITY_SHORTCUT_CONFIG",
    "FamiliarityShortcutConfig",
    "FamiliarityShortcutInput",
    "FamiliarityShortcutOutput",
    "FeltFamiliarityShortcutDetector",
    "ShortcutVerdict",
]
