"""Fold a single-component signal update into stored substrate metadata.

Each signal source — trust, expertise, capability, health — owns one
component of the four-axis :class:`AlignmentVector`. When a source
produces a new score, it calls :meth:`AlignmentRefresher.refresh_component`
to fold the new value into the existing vector while preserving the
other three components.

The refresher reads the current record via the injected
:class:`SubstrateMetadataStore`, merges the one component, recomputes
:func:`compute_net_potential`, re-classifies the :class:`SubstrateMode`
via :func:`auto_classify_mode`, and upserts the merged result.

Single-purpose coordinator: the storage Protocol owns persistence
(insert / update / lookup); the refresher owns the merge.
"""
from __future__ import annotations

import logging
from typing import Final, Optional, final

from substrate.alignment_computer import (
    DEFAULT_ALIGNMENT_WEIGHTS,
    AlignmentWeights,
    auto_classify_mode,
    compute_alignment_vector,
    compute_net_potential,
)
from substrate.types import (
    AlignmentVector,
    EntityRef,
    SubstrateMetadata,
    SubstrateMetadataStore,
)

LOG = logging.getLogger(__name__)

#: Component names that a signal source may refresh.
ALIGNMENT_COMPONENTS: Final[frozenset[str]] = frozenset(
    {"trust", "expertise", "capability", "health"}
)


@final
class AlignmentRefresher:
    """Coordinator: fold one signal-source component into the merged vector.

    Reads the existing :class:`SubstrateMetadata` (if any) via the
    injected store, replaces one component, recomputes net potential
    and substrate mode, then upserts. Idempotent under repeated
    identical inputs — the store's upsert is INSERT-or-UPDATE so
    replays land deterministically.
    """

    def __init__(
        self,
        store: SubstrateMetadataStore,
        *,
        weights: Optional[AlignmentWeights] = None,
        classifier: str = "alignment_refresher",
    ) -> None:
        self._store = store
        self._weights = weights or DEFAULT_ALIGNMENT_WEIGHTS
        self._classifier = classifier

    def refresh_component(
        self,
        *,
        ref: EntityRef,
        component: str,
        value: float,
        updated_by_entity_id: Optional[str] = None,
    ) -> SubstrateMetadata:
        """Fold ``value`` into the ``component`` axis of the vector.

        Reads the existing record (if any), keeps the other three
        components, recomputes net potential and substrate mode, and
        upserts the merged result. Returns the persisted record.

        Raises :class:`ValueError` on unknown component or out-of-range
        value — same boundary contract as :class:`AlignmentVector`.
        """
        if component not in ALIGNMENT_COMPONENTS:
            raise ValueError(
                f"component must be one of {sorted(ALIGNMENT_COMPONENTS)}; "
                f"got {component!r}"
            )
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"value must be in [0.0, 1.0]; got {value}"
            )

        existing = self._store.get(ref)
        if existing is not None:
            base = {
                "trust": existing.alignment_vector.trust,
                "expertise": existing.alignment_vector.expertise,
                "capability": existing.alignment_vector.capability,
                "health": existing.alignment_vector.health,
            }
        else:
            base = {
                "trust": 0.0,
                "expertise": 0.0,
                "capability": 0.0,
                "health": 0.0,
            }
        base[component] = value
        new_vector: AlignmentVector = compute_alignment_vector(**base)
        new_net = compute_net_potential(new_vector, weights=self._weights)
        new_mode = auto_classify_mode(new_net)

        return self._store.upsert(
            ref,
            substrate_mode=new_mode,
            classifier=self._classifier,
            classifier_rationale=(
                f"refresh_component({component}={value:.3f})"
            ),
            alignment_vector=new_vector,
            net_potential=new_net,
            updated_by_entity_id=updated_by_entity_id,
        )


__all__ = [
    "ALIGNMENT_COMPONENTS",
    "AlignmentRefresher",
]
