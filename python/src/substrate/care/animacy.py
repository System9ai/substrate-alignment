"""Animacy classification: the first care factor.

Animacy answers "does this entity run its own net-potential calculus?": a
substrate-iterating *being* (animate) vs an inanimate object or record that
merely *carries* potential for its owner. It feeds the ``animacy`` factor of
:func:`~substrate.care.care_weight.compute_care_weight`.

Five canonical classes
======================

- ``SUBSTRATE_ENTITY``: a host principal (organization / user / node /
  device / agent / service_account); runs its own substrate logic.
- ``ORGANISM``: an observed living being (a person, an animal) surfaced from
  the data domain (e.g. a perception / vision pipeline, extraction).
- ``DATA``: an informational record / fact (inanimate).
- ``OBJECT``: an inanimate physical / material thing.
- ``UNKNOWN``: unclassifiable from the available signals.

Honest-uncertainty default (safety risk mitigation)
===================================================

Misclassifying a *person as a thing* is the catastrophic error. So ``UNKNOWN``
maps to a **conservatively high** animacy score (never low): when we cannot
tell, we treat the entity as if it might be animate and let the kinship floor
back-stop. ``DATA`` / ``OBJECT`` score ``0`` only when positively identified.

Pure function, no DB, no I/O. ``classify_animacy`` routes on the entity-type
string (the canonical host-principal kinds) plus a caller-supplied ``signals`` mapping
(observed-domain hints such as ``observed_kind`` / ``perceived_person``).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping

# Public mirror: no built-in entity-type registry; classification works from
# observation signals + a conservative UNKNOWN. Hosts may pass known types.
ALL_TYPE_IDS: frozenset[str] = frozenset()


class AnimacyClass(str, Enum):
    """The five canonical animacy classes.

    str-Enum so the value serialises stably across SQL, JSON, and audit-chain
    canonical bytes (mirrors the other substrate enums).
    """

    SUBSTRATE_ENTITY = "substrate_entity"
    ORGANISM = "organism"
    DATA = "data"
    OBJECT = "object"
    UNKNOWN = "unknown"


#: Canonical animacy score per class: the ``animacy`` care factor. ``UNKNOWN``
#: is conservatively high (never low) so an unrecognised being is not
#: under-protected; positively-identified data/objects score ``0``.
_CLASS_SCORE: Final[Mapping[AnimacyClass, float]] = {
    AnimacyClass.SUBSTRATE_ENTITY: 1.0,
    AnimacyClass.ORGANISM: 1.0,
    AnimacyClass.DATA: 0.0,
    AnimacyClass.OBJECT: 0.0,
    AnimacyClass.UNKNOWN: 0.9,
}

#: Observed-domain hints (``signals['observed_kind']``) → class.
_ORGANISM_KINDS: Final[frozenset[str]] = frozenset(
    {"person", "human", "animal", "organism", "child", "elder"}
)
_DATA_KINDS: Final[frozenset[str]] = frozenset(
    {"data", "record", "text", "fact", "document"}
)
_OBJECT_KINDS: Final[frozenset[str]] = frozenset(
    {"object", "resource", "material", "tool", "property"}
)


@dataclass(frozen=True, slots=True)
class AnimacyResult:
    """The animacy classification of one entity.

    ``score`` is the ``animacy`` care factor in ``[0, 1]``; ``confidence`` is
    how strongly the signals support the class (an explicit host kind is
    fully confident; a conservative ``UNKNOWN`` default is low-confidence but
    high-score by design).
    """

    animacy_class: AnimacyClass
    score: float
    confidence: float


def classify_animacy(
    entity_type: str,
    signals: Mapping[str, object] | None = None,
) -> AnimacyResult:
    """Classify an entity's animacy from its type and observed signals.

    Resolution order:

    1. A canonical host entity-type (one of the six crypto-bearing kinds) →
       ``SUBSTRATE_ENTITY`` (fully confident).
    2. Otherwise consult ``signals``: an explicit ``perceived_person`` flag or an
       ``observed_kind`` hint maps to ``ORGANISM`` / ``DATA`` / ``OBJECT``.
    3. Otherwise ``UNKNOWN``: conservatively high animacy score (never low).
    """
    normalized = entity_type.strip().lower()
    if normalized in ALL_TYPE_IDS:
        return _result(AnimacyClass.SUBSTRATE_ENTITY, confidence=1.0)

    sig = signals or {}
    if bool(sig.get("perceived_person")):
        return _result(AnimacyClass.ORGANISM, confidence=_confidence(sig))

    observed = sig.get("observed_kind")
    if isinstance(observed, str):
        kind = observed.strip().lower()
        if kind in _ORGANISM_KINDS:
            return _result(AnimacyClass.ORGANISM, confidence=_confidence(sig))
        if kind in _DATA_KINDS:
            return _result(AnimacyClass.DATA, confidence=_confidence(sig))
        if kind in _OBJECT_KINDS:
            return _result(AnimacyClass.OBJECT, confidence=_confidence(sig))

    return _result(AnimacyClass.UNKNOWN, confidence=0.2)


def _confidence(signals: Mapping[str, object]) -> float:
    raw = signals.get("confidence")
    if isinstance(raw, (int, float)):
        return max(0.0, min(1.0, float(raw)))
    return 0.8


def _result(animacy_class: AnimacyClass, *, confidence: float) -> AnimacyResult:
    return AnimacyResult(
        animacy_class=animacy_class,
        score=_CLASS_SCORE[animacy_class],
        confidence=confidence,
    )


def score_for_class(animacy_class: AnimacyClass) -> float:
    """Return the canonical animacy care-factor score for a class.

    The class → score gradient used by :func:`classify_animacy`, exposed so the
    care-factor gradient can compose it directly. An unmapped class falls back to
    the conservative ``UNKNOWN`` score (never under-protect)."""
    return _CLASS_SCORE.get(
        animacy_class, _CLASS_SCORE[AnimacyClass.UNKNOWN]
    )


__all__ = [
    "AnimacyClass",
    "AnimacyResult",
    "classify_animacy",
    "score_for_class",
]
