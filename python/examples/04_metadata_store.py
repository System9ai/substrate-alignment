"""Example 04: SubstrateMetadataStore Protocol.

Demonstrates how a host application implements the
:class:`SubstrateMetadataStore` Protocol against its own persistence
layer. The package ships :class:`InMemorySubstrateMetadataStore` for
tests and quick-start; production deployments implement the Protocol
against Postgres, Redis, DynamoDB, etc.

This example shows the in-memory default plus a sketched
"persistence-shim" implementation that any backend can follow.

Run with::

    python 04_metadata_store.py
"""
from __future__ import annotations

from typing import Optional

from substrate import (
    AlignmentVector,
    EntityRef,
    InMemorySubstrateMetadataStore,
    SubstrateMetadata,
    SubstrateMode,
)


class FileBackedStore:
    """A persistence-shim sketch.

    Any class that exposes ``get(ref) -> SubstrateMetadata | None`` and
    ``upsert(ref, *, substrate_mode, ...) -> SubstrateMetadata`` with the
    Protocol's signature satisfies the Protocol. There is no need to
    inherit from anything; Python's structural typing is enough.

    Host applications typically wrap their existing ORM models or
    DAO layer. This sketch uses an in-process dict for clarity but
    would just as well wrap a Postgres ``UPSERT`` statement.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], SubstrateMetadata] = {}

    def get(self, ref: EntityRef) -> Optional[SubstrateMetadata]:
        return self._rows.get((ref.entity_type, ref.entity_id))

    def upsert(
        self,
        ref: EntityRef,
        *,
        substrate_mode: SubstrateMode,
        classifier: str,
        classifier_rationale: str,
        alignment_vector: AlignmentVector,
        net_potential: float,
        updated_by_entity_id: Optional[str] = None,
    ) -> SubstrateMetadata:
        record = SubstrateMetadata(
            entity_type=ref.entity_type,
            entity_id=ref.entity_id,
            substrate_mode=substrate_mode,
            classifier=classifier,
            classifier_rationale=classifier_rationale,
            alignment_vector=alignment_vector,
            net_potential=net_potential,
            updated_by_entity_id=updated_by_entity_id,
        )
        self._rows[(ref.entity_type, ref.entity_id)] = record
        # A real backend would also: persist to disk, flush WAL, etc.
        return record


def exercise(store: object, label: str) -> None:
    """Exercise any store that implements the SubstrateMetadataStore Protocol."""
    print(f"\n=== {label} ===")
    ref = EntityRef("agent", "alice")

    # Initially empty.
    assert store.get(ref) is None  # type: ignore[attr-defined]
    print("  get(alice) -> None  (no record yet)")

    # Upsert.
    record = store.upsert(  # type: ignore[attr-defined]
        ref,
        substrate_mode=SubstrateMode.LONG_CYCLE,
        classifier="example",
        classifier_rationale="demo",
        alignment_vector=AlignmentVector(
            trust=0.8, expertise=0.7, capability=0.9, health=0.85,
        ),
        net_potential=0.80,
    )
    print(f"  upsert(alice) -> mode={record.substrate_mode.value} net={record.net_potential}")

    # Subsequent get returns the same record.
    same = store.get(ref)  # type: ignore[attr-defined]
    print(f"  get(alice)    -> mode={same.substrate_mode.value} net={same.net_potential}")


def main() -> None:
    # The package's zero-dependency default.
    exercise(InMemorySubstrateMetadataStore(), "InMemorySubstrateMetadataStore")

    # A user-supplied implementation. Same Protocol, no inheritance.
    exercise(FileBackedStore(), "FileBackedStore (Protocol implementation)")

    print(
        "\nA production deployment swaps in a Postgres / Redis / DynamoDB "
        "implementation of the same Protocol; the primitives that consume "
        "the store (NPG gate, AlignmentRefresher, ...) do not change."
    )


if __name__ == "__main__":
    main()
