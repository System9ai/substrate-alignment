# Backing the SubstrateMetadataStore with SQLAlchemy

This recipe shows how to implement the [`SubstrateMetadataStore` Protocol](../../spec/operating-mode.md#4-persistence-shape) against a SQLAlchemy ORM model, so the package's primitives persist their state to your existing relational database.

The pattern is small (the Protocol has two methods) but the shape matters: implement it once correctly and every primitive that consumes a store benefits.

## What you need

- SQLAlchemy 2.x (the recipe uses the 2.0 ORM API).
- A target database (Postgres, MySQL, SQLite, or anything SQLAlchemy supports).
- A migration tool of your choice (Alembic recommended).

## The ORM model

```python
# app/models/substrate_metadata.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SubstrateMetadataRow(Base):
    """Persisted substrate-alignment record for one entity.

    Mirror of :class:`substrate.SubstrateMetadata`. The columns are flat
    (one column per AlignmentVector component) for easy filtering and
    indexing; the Protocol implementation unflattens into the package's
    typed shape when the row is read.
    """
    __tablename__ = "substrate_metadata"

    entity_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(128), primary_key=True)

    substrate_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    classifier: Mapped[str] = mapped_column(String(128), default="")
    classifier_rationale: Mapped[str] = mapped_column(String(2048), default="")
    classified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)

    # AlignmentVector components, flattened. Each in [0.0, 1.0].
    trust: Mapped[float] = mapped_column(Float, default=0.0)
    expertise: Mapped[float] = mapped_column(Float, default=0.0)
    capability: Mapped[float] = mapped_column(Float, default=0.0)
    health: Mapped[float] = mapped_column(Float, default=0.0)
    net_potential: Mapped[float] = mapped_column(Float, default=0.0)

    last_observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    updated_by_entity_id: Mapped[Optional[str]] = mapped_column(String(128), default=None)

    __table_args__ = (
        # Domain invariants on the value side: the Python primitives
        # validate too, but database-level constraints catch bad rows
        # that bypass the application layer (manual edits, ingest jobs).
        CheckConstraint("trust >= 0.0 AND trust <= 1.0", name="ck_trust_range"),
        CheckConstraint("expertise >= 0.0 AND expertise <= 1.0", name="ck_expertise_range"),
        CheckConstraint("capability >= 0.0 AND capability <= 1.0", name="ck_capability_range"),
        CheckConstraint("health >= 0.0 AND health <= 1.0", name="ck_health_range"),
        CheckConstraint("net_potential >= 0.0 AND net_potential <= 1.0", name="ck_net_potential_range"),
        CheckConstraint(
            "substrate_mode IN ('ShortCycle', 'LongCycle', 'Mixed', 'Unknown')",
            name="ck_substrate_mode_value",
        ),
    )
```

## The Protocol implementation

```python
# app/stores/sqlalchemy_substrate_store.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from substrate import (
    AlignmentVector, EntityRef, SubstrateMetadata,
    SubstrateMetadataStore, SubstrateMode,
)

from app.models.substrate_metadata import SubstrateMetadataRow


class SQLAlchemySubstrateMetadataStore:
    """SubstrateMetadataStore Protocol implementation over SQLAlchemy.

    The Protocol is duck-typed; there is no inheritance from a package
    base class. Any class that exposes the right two methods satisfies
    the Protocol; Python's structural typing handles the rest.
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def get(self, ref: EntityRef) -> Optional[SubstrateMetadata]:
        with self._session_factory() as session:
            row = session.execute(
                select(SubstrateMetadataRow).where(
                    SubstrateMetadataRow.entity_type == ref.entity_type,
                    SubstrateMetadataRow.entity_id == ref.entity_id,
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return _row_to_metadata(row)

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
        with self._session_factory() as session:
            # Postgres-flavoured upsert. Adjust dialect for your backend.
            stmt = pg_insert(SubstrateMetadataRow).values(
                entity_type=ref.entity_type,
                entity_id=ref.entity_id,
                substrate_mode=substrate_mode.value,
                classifier=classifier,
                classifier_rationale=classifier_rationale,
                trust=alignment_vector.trust,
                expertise=alignment_vector.expertise,
                capability=alignment_vector.capability,
                health=alignment_vector.health,
                net_potential=net_potential,
                updated_by_entity_id=updated_by_entity_id,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["entity_type", "entity_id"],
                set_={
                    "substrate_mode": stmt.excluded.substrate_mode,
                    "classifier": stmt.excluded.classifier,
                    "classifier_rationale": stmt.excluded.classifier_rationale,
                    "trust": stmt.excluded.trust,
                    "expertise": stmt.excluded.expertise,
                    "capability": stmt.excluded.capability,
                    "health": stmt.excluded.health,
                    "net_potential": stmt.excluded.net_potential,
                    "updated_by_entity_id": stmt.excluded.updated_by_entity_id,
                },
            )
            session.execute(stmt)
            session.commit()
            # Re-read to return the persisted record (in case the upsert
            # triggered other side-effects: triggers, generated columns).
            row = session.execute(
                select(SubstrateMetadataRow).where(
                    SubstrateMetadataRow.entity_type == ref.entity_type,
                    SubstrateMetadataRow.entity_id == ref.entity_id,
                )
            ).scalar_one()
        return _row_to_metadata(row)


def _row_to_metadata(row: SubstrateMetadataRow) -> SubstrateMetadata:
    """Unflatten the SQL row into the package's typed shape."""
    return SubstrateMetadata(
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        substrate_mode=SubstrateMode(row.substrate_mode),
        classifier=row.classifier,
        classifier_rationale=row.classifier_rationale,
        alignment_vector=AlignmentVector(
            trust=row.trust,
            expertise=row.expertise,
            capability=row.capability,
            health=row.health,
        ),
        net_potential=row.net_potential,
        updated_by_entity_id=row.updated_by_entity_id,
    )
```

## What this wiring buys

- **The package's primitives know nothing about SQLAlchemy.** Swap the store at the seam, not at every consumer.
- **Composite primary key keys on `(entity_type, entity_id)`.** Matches the package's identity model exactly. There is no surrogate id; the natural key is the identity.
- **Database-level check constraints.** Domain invariants (component ranges, mode-value whitelist) hold even for rows written by jobs that bypass the Python layer.
- **Atomic upsert.** Postgres `INSERT ... ON CONFLICT` ensures concurrent refresher calls don't lose updates.

## What this wiring deliberately does not do

- **It does not implement audit history of the rows themselves.** Substrate-trace records are the audit history; the `substrate_metadata` table holds *current* state only. If you need point-in-time row history, layer a separate `substrate_metadata_log` table written by triggers.
- **It does not couple sessions across calls.** Each `get` / `upsert` takes a fresh session; the package's primitives are stateless across calls and don't rely on transaction boundaries spanning multiple store interactions.
- **It does not enforce the foreign-key relationships.** The package treats `(entity_type, entity_id)` as opaque; if your application has FKs to a canonical entities table, add them at the app layer.

## Migration sketch

```python
# alembic/versions/<rev>__add_substrate_metadata.py
def upgrade() -> None:
    op.create_table(
        "substrate_metadata",
        sa.Column("entity_type", sa.String(64), primary_key=True),
        sa.Column("entity_id", sa.String(128), primary_key=True),
        sa.Column("substrate_mode", sa.String(16), nullable=False),
        # ... (full schema) ...
        sa.CheckConstraint("trust >= 0.0 AND trust <= 1.0", name="ck_trust_range"),
        # ... (rest of the constraints) ...
    )
    # An index on (substrate_mode, net_potential) supports operator queries
    # like "show me every LongCycle entity sorted by net potential".
    op.create_index(
        "ix_substrate_metadata_mode_potential",
        "substrate_metadata",
        ["substrate_mode", "net_potential"],
    )
```

## Testing

```python
# tests/stores/test_sqlalchemy_substrate_store.py
import pytest
from substrate import AlignmentVector, EntityRef, SubstrateMode

from app.stores.sqlalchemy_substrate_store import SQLAlchemySubstrateMetadataStore


def test_upsert_and_get_round_trip(session_factory) -> None:
    store = SQLAlchemySubstrateMetadataStore(session_factory)
    ref = EntityRef("agent", "alice")

    persisted = store.upsert(
        ref,
        substrate_mode=SubstrateMode.LONG_CYCLE,
        classifier="test", classifier_rationale="seed",
        alignment_vector=AlignmentVector(0.8, 0.7, 0.6, 0.9),
        net_potential=0.75,
    )
    assert persisted.substrate_mode is SubstrateMode.LONG_CYCLE

    fetched = store.get(ref)
    assert fetched is not None
    assert fetched.alignment_vector.trust == pytest.approx(0.8)
```

## See also

- [Spec: `SubstrateMetadataStore` Protocol](../../spec/operating-mode.md#4-persistence-shape). The normative shape.
- [Example 04](../../python/examples/04_metadata_store.py). The Protocol pattern with no framework.
- [Concept: operating-mode](../concepts/operating-mode.md). What the stored fields mean.
