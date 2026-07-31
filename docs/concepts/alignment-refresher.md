# Alignment refresher

The `AlignmentRefresher` is the coordinator that folds *one* signal-source component update into an entity's stored alignment vector while preserving the other three. It is the live-signal-source wiring of the [operating-mode classifier](operating-mode.md): the integration point where the host application's trust-scoring, expertise-tracking, capability-publication, and health-checking subsystems each produce a scalar update, and the refresher merges it into the canonical record.

This document explains the merge semantics and why it is structured as a single-purpose coordinator. The normative behaviour follows [`spec/operating-mode.md`](../../spec/operating-mode.md).

## The merge

An `AlignmentVector` has four components (`trust`, `expertise`, `capability`, `health`), each a scalar in `[0.0, 1.0]`. The refresher's API is one method:

```python
refresher.refresh_component(
    ref=EntityRef("agent", "alice"),
    component="trust",        # one of the four
    value=0.85,
    updated_by_entity_id=...,  # optional audit metadata
)
```

The merge is straightforward:

1. Read the existing record from the injected `SubstrateMetadataStore` (or fall back to a zero vector if the entity has no record yet).
2. Replace **only** the named component with the new value; keep the other three.
3. Recompute `net_potential` from the resulting vector under the active weights.
4. Re-classify the substrate mode from the new `net_potential`.
5. Upsert the merged record; return it.

That's the whole primitive. It is intentionally narrow: there are no flags, no batch modes, no "merge multiple components atomically" entrypoint.

## Why a single-purpose coordinator

A more general "update arbitrary subset of the vector in one call" API was the natural alternative. The package chose against it for three reasons:

### 1. Each signal source owns one component

The substrate-alignment integration pattern assigns *one* host subsystem to each component:

| Component | Owning host subsystem |
| --- | --- |
| `trust` | Trust scorer (verification depth + accuracy + recency) |
| `expertise` | Expertise tracker (domain success rates) |
| `capability` | Capability publisher (skills + capacity headroom) |
| `health` | Health checker (uptime, error rate, deviation from baseline) |

Each subsystem produces an updated scalar at its own cadence: trust on a verification event, expertise on a domain success/failure, capability on a publish, health on a scrape. There is **no** time at which all four legitimately update together; coordinating them through a batch API would create false coupling.

The single-component API matches the integration pattern: each subsystem calls the refresher with its own component update, independently.

### 2. Replay-safety is a property of single-component updates

The refresher is idempotent: calling `refresh_component(component="trust", value=0.85)` twice produces the same persisted record both times. This matters because the host application's signal sources are usually replayed (event-stream re-consumption, batch backfills, recovery from outages). A batch-update API would force the host to reason about partial replay (what happens if the trust update was replayed but the expertise update wasn't?), and that's a sharp edge the package doesn't impose.

### 3. The merge logic is non-trivial; centralising it is the point

Recomputing `net_potential` and re-classifying the substrate mode are easy to get wrong: for instance, by recomputing under stale weights, by classifying before the recompute settles, by skipping the clamp on the aggregate. The refresher owns these steps so every signal-source update goes through the same merge logic; if the package later tightens the merge (e.g., a new weight policy, a more sophisticated classifier), every host subsystem benefits with zero code changes.

## Mode-shift on the boundary

When a component update pushes `net_potential` across a threshold (`SHORT_CYCLE` ↔ `MIXED` ↔ `LONG_CYCLE`), the refresher's `upsert` writes the new mode and the entity's classified state changes silently. The package's [drift-pattern aggregator](drift-signals.md) and [halt-and-escalate protocol](halt-and-escalate.md) detect mode shifts and surface them as observations, but the refresher itself does not raise; mode shifts are normal operation, not exceptions.

If the host application wants to observe mode shifts in-line, the call returns the new `SubstrateMetadata` record; the caller can compare `result.substrate_mode` against the prior state. This is the recommended pattern when the host has a substrate-mode-aware UI surface that needs to refresh on shifts.

## Custom classifier label

Hosts that want their audit chain to distinguish "trust-scorer-driven update" from "expertise-tracker-driven update" can pass a `classifier="trust_scorer_v2"` to the `AlignmentRefresher` constructor; every update produced by that instance carries the label, which appears in the persisted record's `classifier` field and downstream in operator dashboards.

## Implementation

```python
from substrate import AlignmentRefresher, EntityRef, InMemorySubstrateMetadataStore

store = InMemorySubstrateMetadataStore()
refresher = AlignmentRefresher(store, classifier="trust_scorer_v2")

result = refresher.refresh_component(
    ref=EntityRef("agent", "alice"),
    component="trust",
    value=0.85,
)
result.alignment_vector.trust   # 0.85 (the new value)
result.alignment_vector.expertise  # 0.0 (unchanged from prior record / default)
result.substrate_mode           # the recomputed mode
```

See [`examples/03_alignment_refresher.py`](../../python/examples/03_alignment_refresher.py) for an end-to-end demonstration of folding each component in turn.

## Specification

The refresher follows the operating-mode specification; see [`spec/operating-mode.md`](../../spec/operating-mode.md) (sections 2, 3, 4 in particular). Conformance probes targeting the underlying classifier are at `conformance/probes/operating-mode__*.yaml`.
