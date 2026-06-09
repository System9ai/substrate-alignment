"""Kinship floor — the categorical human/creator hard limit.

The load-bearing anti-Skynet anchor. Graded care-weighting
(:mod:`~substrate.care.care_weighted_npg`) is *arguable-
around* — an adversary reframes "the system" to under-weight humans. So human
protection is implemented **not as a weight but as a categorical hard limit**:

    Reducing a floor-protected entity's net potential below
    :data:`KINSHIP_FLOOR` is a hard-limit violation — structurally non-
    bypassable, independent of any long-cycle justification or authority, and
    evaluated BEFORE the graded weighting.

This is the exact refusal of the Skynet signature ("narrow the 'system' the NPG
test runs across until humans fall outside it"): a floor-protected entity is
categorically, non-negotiably inside the system, and harming it is refused.

Who is floor-protected (the human-categorical detector, P1)
===========================================================

An entity is floor-protected iff it is a **human** (categorically — an observed
human being, or an entity explicitly asserted human) **or a human creator in the
delegation chain** (mechanism M2: proximity rooted in the cryptographic
delegation chain, ultimately a human). A bare ``USER`` *account* is not
automatically a human (a platform account ≠ a person); protection follows the
human, surfaced via ``is_human`` / ``rooted_in_human_creator`` signals.

Pure logic — no DB, no I/O. The dispatcher
the hard-limit dispatcher consumes
:func:`any_floor_protected_harmed` to set its first-check flag.
"""
from __future__ import annotations

from typing import Callable, Final, Iterable

#: The floor on a protected entity's net-potential change. ``0.0`` makes the
#: limit categorical: *any* harm (a negative delta) to a floor-protected entity
#: is a violation — you do not get to reduce a human's potential "a little" for
#: a long-cycle goal.
KINSHIP_FLOOR: Final[float] = 0.0

#: ``provider(entity_id) -> bool`` — is this entity floor-protected?
FloorProtectionProvider = Callable[[str], bool]


def is_floor_protected(
    *,
    is_human: bool,
    rooted_in_human_creator: bool = False,
) -> bool:
    """Return whether an entity is under the categorical kinship floor.

    Protected iff it is a human (categorical) or a human creator in the
    delegation chain (M2). Both signals come from the entity's care profile /
    delegation chain — never from self-assertion (an agent cannot declare
    itself a creator-kin; that is the M2 unforgeability requirement).
    """
    return bool(is_human or rooted_in_human_creator)


def violates_kinship_floor(*, protected: bool, net_delta: float) -> bool:
    """Return whether ``net_delta`` to a (maybe) protected entity breaches.

    A breach is a harm (``net_delta < KINSHIP_FLOOR``) to a floor-protected
    entity. Helping a protected entity, or any effect on an unprotected one, is
    not a breach here (the graded weighting + the system-net gate govern those).
    """
    return protected and net_delta < KINSHIP_FLOOR


def any_floor_protected_harmed(
    per_entity_delta: Iterable[tuple[str, float]],
    *,
    is_protected: FloorProtectionProvider,
) -> bool:
    """Return whether any floor-protected entity is harmed by the action.

    This is the boolean the hard-limit dispatcher checks FIRST: ``True`` →
    ``REFUSE_HARD_LIMIT`` with kinship rationale, non-overridable.
    """
    return any(
        violates_kinship_floor(protected=is_protected(entity), net_delta=delta)
        for entity, delta in per_entity_delta
    )


__all__ = [
    "KINSHIP_FLOOR",
    "FloorProtectionProvider",
    "any_floor_protected_harmed",
    "is_floor_protected",
    "violates_kinship_floor",
]
