"""Example 03: AlignmentRefresher.

Demonstrates the live-signal-source wiring: when one of the four
alignment-vector components (trust, expertise, capability, health)
produces a new score, the refresher folds it into the stored
:class:`SubstrateMetadata` while preserving the other three components.

Run with::

    python 03_alignment_refresher.py
"""
from __future__ import annotations

from substrate import (
    ALIGNMENT_COMPONENTS,
    AlignmentRefresher,
    EntityRef,
    InMemorySubstrateMetadataStore,
)


def show(store: InMemorySubstrateMetadataStore, ref: EntityRef, label: str) -> None:
    record = store.get(ref)
    if record is None:
        print(f"  {label}: <no record>")
        return
    v = record.alignment_vector
    print(
        f"  {label}: trust={v.trust:.2f} expertise={v.expertise:.2f} "
        f"capability={v.capability:.2f} health={v.health:.2f}  "
        f"net={record.net_potential:.3f}  mode={record.substrate_mode.value}"
    )


def main() -> None:
    store = InMemorySubstrateMetadataStore()
    refresher = AlignmentRefresher(store)
    alice = EntityRef("agent", "alice")

    print("Folding signal-source updates one component at a time:")
    show(store, alice, "before")
    for component in sorted(ALIGNMENT_COMPONENTS):
        refresher.refresh_component(
            ref=alice, component=component, value=0.8,
        )
        show(store, alice, f"after {component}=0.80")

    # The component refresh recomputes net_potential and reclassifies
    # the substrate mode under the default thresholds.
    print("\nFinal record after every component reached 0.80:")
    show(store, alice, "final")


if __name__ == "__main__":
    main()
