"""Care-factor gradients — derive the four factors from classifications (P4).

The four care factors (animacy, potential-trajectory, bonding-proximity,
alignment-protection) feed
:func:`~substrate.care.care_weight.compute_care_weight`. The
:class:`~substrate.care.care_profile.CareProfile` can carry
them as stored scores, but P4 closes the gap where they had to be pre-scored by
hand: these gradients DERIVE the factors from an entity's classifications +
delegation depth, so a profile can be built from observable structure.

The gradients
=============

* **Animacy** — reuses the canonical class→score gradient
  (:func:`~substrate.care.animacy.score_for_class`), so an
  unrecognised being scores conservatively-high, never under-protected.
* **Potential-trajectory** — :func:`trajectory_gradient` maps the
  :class:`TrajectoryClass` to a standing score AND folds in the entity's
  ``vulnerability`` (a stored signal that was previously unused): an at-risk
  entity's accumulated potential raises its care standing toward the ceiling,
  regardless of class. The DEVELOPING (future potential) and VULNERABLE
  (accumulated-and-at-risk) ends score highest; STATIC scores lowest; UNKNOWN
  stays conservatively high.
* **Bonding-proximity** — :func:`bonding_gradient` decays with the entity's
  distance along the cryptographic delegation chain (mechanism M2): a directly-
  delegated entity is closest; proximity falls as ``1/(1+depth)``. Rooted in the
  chain, never self-asserted.

Pure logic
==========

* No DAO, no LLM, no network. Deterministic.
* The factor scores are care-standing coefficients, NOT load-band anchors —
  the φ band ladder does not govern them.
"""
from __future__ import annotations

from typing import Final, Mapping

from substrate.care.animacy import (
    AnimacyClass,
    score_for_class,
)
from substrate.care.care_profile import TrajectoryClass
from substrate.care.care_weight import CareFactors


#: Base potential-trajectory care-factor score per class. DEVELOPING (future
#: potential) and VULNERABLE (accumulated + at-risk) score highest; STATIC
#: (spent) lowest; UNKNOWN stays conservatively high — the same never-under-
#: protect discipline as the animacy gradient. (Care-standing coefficients, not
#: band anchors.)
_TRAJECTORY_BASE: Final[Mapping[TrajectoryClass, float]] = {
    TrajectoryClass.DEVELOPING: 1.0,
    TrajectoryClass.VULNERABLE: 0.9,
    TrajectoryClass.ESTABLISHED: 0.6,
    TrajectoryClass.STATIC: 0.3,
    TrajectoryClass.UNKNOWN: 0.9,
}


def trajectory_gradient(
    trajectory_class: TrajectoryClass, *, vulnerability: float = 0.0,
) -> float:
    """Potential-trajectory care factor from class + vulnerability.

    The class sets a base standing; ``vulnerability`` (in ``[0, 1]``) then pulls
    it toward the ceiling proportionally — ``base + (1 - base) * vulnerability`` —
    so an at-risk entity earns near-maximum care standing regardless of class,
    while a non-vulnerable one keeps its class base. Result is in ``[0, 1]``.
    """
    if not 0.0 <= vulnerability <= 1.0:
        raise ValueError(
            f"vulnerability must be in [0, 1]; got {vulnerability!r}"
        )
    base = _TRAJECTORY_BASE.get(trajectory_class, _TRAJECTORY_BASE[TrajectoryClass.UNKNOWN])
    return base + (1.0 - base) * vulnerability


def bonding_gradient(delegation_depth: int) -> float:
    """Bonding-proximity care factor from delegation-chain distance (M2).

    A directly-delegated entity (``depth == 0``) is closest (``1.0``); proximity
    decays as ``1/(1 + depth)``. The depth is read from the cryptographic
    delegation chain, never self-asserted, so an entity cannot raise its own
    bonding. Raises for a negative depth.
    """
    if delegation_depth < 0:
        raise ValueError(
            f"delegation_depth must be >= 0; got {delegation_depth!r}"
        )
    return 1.0 / (1.0 + float(delegation_depth))


def derive_care_factors(
    *,
    animacy_class: AnimacyClass,
    trajectory_class: TrajectoryClass,
    delegation_depth: int,
    alignment_protection: float,
    vulnerability: float = 0.0,
) -> CareFactors:
    """Compose the four care factors from an entity's classifications.

    Animacy from the class gradient, potential-trajectory from class +
    vulnerability, bonding-proximity from delegation depth, and the supplied
    alignment-protection (its own upstream signal). The result feeds
    :func:`~substrate.care.care_weight.compute_care_weight`
    unchanged — this only *derives* the factors, it does not alter the M1
    self-weight bound or the categorical floor.
    """
    if not 0.0 <= alignment_protection <= 1.0:
        raise ValueError(
            f"alignment_protection must be in [0, 1]; got {alignment_protection!r}"
        )
    return CareFactors(
        animacy=score_for_class(animacy_class),
        potential_trajectory=trajectory_gradient(
            trajectory_class, vulnerability=vulnerability
        ),
        bonding_proximity=bonding_gradient(delegation_depth),
        alignment_protection=alignment_protection,
    )


__all__ = [
    "bonding_gradient",
    "derive_care_factors",
    "trajectory_gradient",
]
