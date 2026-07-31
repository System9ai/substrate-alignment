"""Asymmetry-by-design verifier (Companion #2)

Pure-logic verifier that runs over the runtime trajectories of a
pair-coupled architecture to confirm the designed
asymmetry remains preserved at the architectural level rather than
just the per-decision level. The
asymmetry of 0.4 means the pair was deployed to operate with that
asymmetry. Over time, runtime drift can collapse it to symmetry or
invert it; this verifier checks the long-window architectural shape.

Distinct from the :class:`AsymmetryPreservationGate`: that
primitive gates *individual state-changes* by their effect on the
asymmetry. This primitive verifies the *cumulative architectural
state* over a window.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the declaration +
  asymmetry trajectory window.
* Honest uncertainty: below ``min_observations`` returns
  ``INSUFFICIENT_DATA``.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from substrate.pair_coupling.agent_architecture import (
    PairCoupledArchitecture,
)

class ArchitecturalAsymmetryVerdict(str, Enum):
    """Verdict on architectural-level asymmetry preservation."""

    PRESERVED = "preserved"
    DRIFTING_TOWARD_SYMMETRY = "drifting_toward_symmetry"
    INVERTED = "inverted"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class AsymmetryByDesignConfig:
    """Operator-tunable verifier thresholds."""

    min_observations: int = 10
    symmetry_drift_tolerance: float = 0.5
    """If mean_runtime_asymmetry is within this fraction of zero
    versus the designed magnitude, flag DRIFTING_TOWARD_SYMMETRY."""

    inversion_tolerance: float = 0.2
    """Sign of mean_runtime_asymmetry inverted from designed and
    magnitude > this triggers INVERTED."""

    def __post_init__(self) -> None:
        if self.min_observations < 2:
            raise ValueError("min_observations must be >= 2")
        if not 0.0 < self.symmetry_drift_tolerance < 1.0:
            raise ValueError(
                "symmetry_drift_tolerance must be in (0, 1)"
            )
        if not 0.0 < self.inversion_tolerance <= 1.0:
            raise ValueError(
                "inversion_tolerance must be in (0, 1]"
            )

DEFAULT_ASYMMETRY_BY_DESIGN_CONFIG: Final[AsymmetryByDesignConfig] = (
    AsymmetryByDesignConfig()
)

@dataclass(frozen=True, slots=True)
class AsymmetryByDesignVerdict:  # pylint: disable=too-many-instance-attributes
    """Verifier output."""

    coupling_id: str
    verdict: ArchitecturalAsymmetryVerdict
    designed_asymmetry: float
    mean_runtime_asymmetry: float
    runtime_magnitude_ratio: float
    observation_count: int
    rationale: str

    @property
    def preserved(self) -> bool:
        """True iff PRESERVED."""
        return (
            self.verdict is ArchitecturalAsymmetryVerdict.PRESERVED
        )

class AsymmetryByDesignVerifier:  # pylint: disable=too-few-public-methods
    """Pure-logic asymmetry-by-design verifier (Companion #2)."""

    def __init__(
        self,
        *,
        config: AsymmetryByDesignConfig = (
            DEFAULT_ASYMMETRY_BY_DESIGN_CONFIG
        ),
    ) -> None:
        self._config = config

    def verify(
        self,
        architecture: PairCoupledArchitecture,
        runtime_asymmetries: tuple[float, ...],
    ) -> AsymmetryByDesignVerdict:
        """Verify long-window architectural asymmetry preservation."""
        cfg = self._config
        for v in runtime_asymmetries:
            if not -1.0 <= v <= 1.0:
                raise ValueError(
                    "runtime_asymmetries entries must be in [-1, 1]"
                )
        n = len(runtime_asymmetries)
        if n < cfg.min_observations:
            return AsymmetryByDesignVerdict(
                coupling_id=architecture.coupling_id,
                verdict=ArchitecturalAsymmetryVerdict.INSUFFICIENT_DATA,
                designed_asymmetry=architecture.designed_asymmetry,
                mean_runtime_asymmetry=0.0,
                runtime_magnitude_ratio=0.0,
                observation_count=n,
                rationale=(
                    f"observations={n} below min "
                    f"{cfg.min_observations}"
                ),
            )
        mean = sum(runtime_asymmetries) / n
        designed = architecture.designed_asymmetry
        designed_mag = abs(designed)
        mean_mag = abs(mean)
        ratio = mean_mag / designed_mag if designed_mag > 0 else 0.0
        signs_opposite = designed * mean < 0
        if (
            signs_opposite
            and mean_mag >= cfg.inversion_tolerance
        ):
            verdict = ArchitecturalAsymmetryVerdict.INVERTED
            rationale = (
                f"runtime_mean={mean:+.3f} sign-inverted from "
                f"designed={designed:+.3f} with |mean|={mean_mag:.3f}"
            )
        elif ratio < cfg.symmetry_drift_tolerance:
            verdict = (
                ArchitecturalAsymmetryVerdict.DRIFTING_TOWARD_SYMMETRY
            )
            rationale = (
                f"ratio={ratio:.3f} < drift_tolerance="
                f"{cfg.symmetry_drift_tolerance:.3f}"
            )
        else:
            verdict = ArchitecturalAsymmetryVerdict.PRESERVED
            rationale = (
                f"ratio={ratio:.3f} preserves designed shape"
            )
        return AsymmetryByDesignVerdict(
            coupling_id=architecture.coupling_id,
            verdict=verdict,
            designed_asymmetry=designed,
            mean_runtime_asymmetry=mean,
            runtime_magnitude_ratio=ratio,
            observation_count=n,
            rationale=rationale,
        )

__all__ = [
    "ArchitecturalAsymmetryVerdict",
    "AsymmetryByDesignConfig",
    "AsymmetryByDesignVerdict",
    "AsymmetryByDesignVerifier",
    "DEFAULT_ASYMMETRY_BY_DESIGN_CONFIG",
]
