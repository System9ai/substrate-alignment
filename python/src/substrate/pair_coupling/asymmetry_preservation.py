"""Asymmetry-preservation gate (Companion #2)

Pure-logic gate that enforces a designed asymmetry inside a
pair-coupling. The
substrate-aligned shape of a pair-coupling is not "symmetric twins" but
two poles holding distinct, complementary roles. The substrate-aligned
hard-limit is therefore not "drive A and B to equal trajectories" but
"preserve the *designed* asymmetry while keeping both trajectories
rising".

This gate is consulted before a state-change is applied to a
pair-coupling (e.g. reassigning role, redistributing capability,
collapsing a workflow). It rejects state changes that would force the
pair toward zero designed-asymmetry.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the
  :class:`AsymmetryPreservationInput`.
* Honest uncertainty: a baseline asymmetry of zero with no declared
  designed-asymmetry produces ``INSUFFICIENT_DATA``.
* Scale-aware via :class:`~substrate.pair_coupling.alignment_audit.PairScale`.
* Frozen dataclasses with slots throughout.
# § "Asymmetry by design: the substrate-aligned shape of a pair-coupling"
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from substrate.pair_coupling.alignment_audit import (
    PairScale,
)

class AsymmetryVerdict(str, Enum):
    """Verdict from the asymmetry-preservation gate."""

    PRESERVED = "preserved"
    COLLAPSING_TO_SYMMETRY = "collapsing_to_symmetry"
    INVERTING_DESIGN = "inverting_design"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class AsymmetryPreservationInput:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied asymmetry-preservation gate input."""

    pair_id: str
    pole_a_id: str
    pole_b_id: str
    scale: PairScale
    designed_asymmetry: float
    """Signed designed asymmetry: positive favors pole A, negative pole B."""

    current_asymmetry: float
    """Signed observed asymmetry under current state."""

    proposed_asymmetry: float
    """Signed asymmetry that the proposed state-change would produce."""

    def __post_init__(self) -> None:
        if not self.pair_id:
            raise ValueError("pair_id must be non-empty")
        if not self.pole_a_id:
            raise ValueError("pole_a_id must be non-empty")
        if not self.pole_b_id:
            raise ValueError("pole_b_id must be non-empty")
        if self.pole_a_id == self.pole_b_id:
            raise ValueError("pole_a_id and pole_b_id must differ")
        for name, value in (
            ("designed_asymmetry", self.designed_asymmetry),
            ("current_asymmetry", self.current_asymmetry),
            ("proposed_asymmetry", self.proposed_asymmetry),
        ):
            if not -1.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [-1, 1]")

@dataclass(frozen=True, slots=True)
class AsymmetryPreservationDecision:  # pylint: disable=too-many-instance-attributes
    """Aggregate decision from the asymmetry-preservation gate."""

    pair_id: str
    scale: PairScale
    verdict: AsymmetryVerdict
    designed_asymmetry: float
    proposed_asymmetry: float
    collapse_distance: float
    inversion: bool
    rationale: str

    @property
    def preserved(self) -> bool:
        """True iff the proposed state-change preserves designed asymmetry."""
        return self.verdict is AsymmetryVerdict.PRESERVED

@dataclass(frozen=True, slots=True)
class AsymmetryPreservationConfig:
    """Tunable thresholds for the asymmetry-preservation gate."""

    designed_asymmetry_floor: float = 0.05
    """Below this designed-asymmetry magnitude, the pair has no
    declared design and the gate returns INSUFFICIENT_DATA."""

    collapse_tolerance: float = 0.1
    """If proposed_asymmetry would close the designed asymmetry to
    within this magnitude of zero, the gate flags
    COLLAPSING_TO_SYMMETRY."""

    def __post_init__(self) -> None:
        if not 0.0 < self.designed_asymmetry_floor <= 1.0:
            raise ValueError(
                "designed_asymmetry_floor must be in (0, 1]"
            )
        if not 0.0 < self.collapse_tolerance <= 1.0:
            raise ValueError(
                "collapse_tolerance must be in (0, 1]"
            )

DEFAULT_ASYMMETRY_PRESERVATION_CONFIG: Final[
    AsymmetryPreservationConfig
] = AsymmetryPreservationConfig()

class AsymmetryPreservationGate:  # pylint: disable=too-few-public-methods
    """Pure-logic asymmetry-preservation gate (Companion #2)."""

    def __init__(
        self,
        *,
        config: AsymmetryPreservationConfig = (
            DEFAULT_ASYMMETRY_PRESERVATION_CONFIG
        ),
    ) -> None:
        self._config = config

    def evaluate(
        self, input_: AsymmetryPreservationInput,
    ) -> AsymmetryPreservationDecision:
        """Evaluate whether a proposed state-change preserves designed asymmetry."""
        cfg = self._config
        designed_magnitude = abs(input_.designed_asymmetry)
        proposed_magnitude = abs(input_.proposed_asymmetry)
        collapse_distance = proposed_magnitude
        inversion = (
            designed_magnitude >= cfg.designed_asymmetry_floor
            and input_.designed_asymmetry * input_.proposed_asymmetry < 0
        )

        if designed_magnitude < cfg.designed_asymmetry_floor:
            verdict = AsymmetryVerdict.INSUFFICIENT_DATA
            rationale = (
                f"designed_asymmetry={input_.designed_asymmetry:+.3f} "
                f"below floor {cfg.designed_asymmetry_floor:.3f}; "
                f"no declared design to preserve"
            )
        elif inversion:
            verdict = AsymmetryVerdict.INVERTING_DESIGN
            rationale = (
                f"designed_asymmetry={input_.designed_asymmetry:+.3f} "
                f"inverts to proposed_asymmetry="
                f"{input_.proposed_asymmetry:+.3f}; sign flip"
            )
        elif proposed_magnitude < cfg.collapse_tolerance:
            verdict = AsymmetryVerdict.COLLAPSING_TO_SYMMETRY
            rationale = (
                f"proposed_asymmetry={input_.proposed_asymmetry:+.3f} "
                f"within collapse_tolerance "
                f"{cfg.collapse_tolerance:.3f} of zero; "
                f"designed asymmetry would be erased"
            )
        else:
            verdict = AsymmetryVerdict.PRESERVED
            rationale = (
                f"proposed_asymmetry={input_.proposed_asymmetry:+.3f} "
                f"preserves designed_asymmetry="
                f"{input_.designed_asymmetry:+.3f} sign and magnitude"
            )

        return AsymmetryPreservationDecision(
            pair_id=input_.pair_id,
            scale=input_.scale,
            verdict=verdict,
            designed_asymmetry=input_.designed_asymmetry,
            proposed_asymmetry=input_.proposed_asymmetry,
            collapse_distance=collapse_distance,
            inversion=inversion,
            rationale=rationale,
        )

__all__ = [
    "DEFAULT_ASYMMETRY_PRESERVATION_CONFIG",
    "AsymmetryPreservationConfig",
    "AsymmetryPreservationDecision",
    "AsymmetryPreservationGate",
    "AsymmetryPreservationInput",
    "AsymmetryVerdict",
]
