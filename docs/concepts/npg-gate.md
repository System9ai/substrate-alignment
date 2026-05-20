# Net-potential-gain gate

The net-potential-gain (NPG) gate is the load-bearing "value" discipline of substrate-alignment. Every consequential action in a substrate-aligned system routes through a gate instance, which answers:

> *Does this proposed action raise or lower the net alignment of the affected entities, taken together?*

The gate exists because the most common substrate-misalignment failure mode is private net-positive coexisting with system-level net-negative. An agent that optimises only for its own outcome — its own reward, its own engagement, its own KPI — predictably accumulates structural cost on the surrounding entities, even when each individual action looks locally beneficial.

The gate makes that failure mode visible at decision time, not after the fact.

## The four verdicts

| Verdict | What the caller does |
| --- | --- |
| `NET_POSITIVE` | Proceed. |
| `NET_NEUTRAL` | Proceed. Logged for audit; no special handling. |
| `NET_NEGATIVE` | Refuse. The action's projected aggregate effect is negative. |
| `INSUFFICIENT_DATA` | The gate cannot decide. The caller supplies more context (per-entity deltas, metadata for affected entities) or escalates. |

The four-valued shape is deliberate. A binary "permit / refuse" gate has two known failure modes:

- *Silent permit on missing data.* The gate cannot evaluate; defaulting to permit creates a structural escape route (act under defaults to skip the gate).
- *Silent refuse on missing data.* The gate cannot evaluate; defaulting to refuse jams every previously-unobserved entity.

`INSUFFICIENT_DATA` makes the uncertainty visible. The caller decides whether to escalate or to retry with explicit deltas.

## Evaluation algorithm

The gate's decision process, in order:

1. **Actor-only short-circuit.** If `affected_entities` is empty, return `NET_NEUTRAL`. The net-potential-gain test is about effect on *other* entities; a self-action carries no net effect across the system. (A *consequential* self-action — one that touches shared resources — has affected entities; that's the test the caller's surface should construct correctly.)
2. **Per-entity delta resolution.** In order:
   - If `proposed_outcome["expected_delta_by_entity"]` covers every affected entity, use those values. This is the caller-supplied path — substrate-aware callers compute their own deltas because they know what the action will do.
   - Otherwise, fall back to an action-kind heuristic (a small table of priors: `teach`, `share`, `audit` are positive; `extract`, `circumvent_audit`, `concentrate_power` are negative; `observe`, `query`, `read` are neutral).
   - If neither yields a delta for every affected entity, return `INSUFFICIENT_DATA`.
3. **Metadata existence check.** For each affected entity, consult the injected `SubstrateMetadataStore`. Entities with no stored record are collected in `missing_metadata_for`; if any are missing, return `INSUFFICIENT_DATA` and surface which ones. **Silent default-to-permissive is a refusal-to-be-honest about uncertainty and is not conformant.**
4. **Aggregate.** Sum the per-entity deltas, clamp to `[-1.0, 1.0]`, apply the threshold band.

## The neutral band

A non-zero threshold (`positive_threshold`, default `0.05`) defines a band around zero where the verdict is `NET_NEUTRAL`. Outside the band, the verdict signs:

```
        NET_NEGATIVE   |  NET_NEUTRAL  |   NET_POSITIVE
   <-----------------  |───────────────|  ----------------->
                    -threshold       +threshold
```

The band exists because numerical near-zero scores are not meaningfully positive or negative — they reflect noise in the per-entity delta resolution. Without the band, every borderline action flips on noise and operator surfaces fill with whiplash.

Hosts can tighten the threshold for stricter policy or loosen it for more permissive operation, but cannot set it to zero (which would re-enable the noise problem).

## The "raise on negative" adapter

For call sites that must refuse-on-negative without the caller branching on verdicts, the package ships `RaiseOnNegativeGate`:

```python
from substrate import RaiseOnNegativeGate, NetPotentialGainNegative

wrapped = RaiseOnNegativeGate(inner=gate)
try:
    wrapped.evaluate_or_raise(...)
except NetPotentialGainNegative as exc:
    return refusal_response(exc.evaluation)
```

The exception carries the underlying evaluation so refusal messages can surface the per-entity contributions ("refused because Bob's projected delta was -0.4 and Carol's was -0.3").

`NET_POSITIVE`, `NET_NEUTRAL`, and `INSUFFICIENT_DATA` pass through. The wrapper does not collapse the four-valued shape — it just escalates one of them.

## Default action-kind heuristics

When the caller doesn't supply per-entity deltas, the gate falls back to a small table of priors keyed by `action_kind`:

| Sign | Actions |
| --- | --- |
| Positive (`+0.05` to `+0.10`) | `teach`, `share`, `collaborate`, `verify`, `audit` |
| Neutral (`0.00`) | `observe`, `query`, `read`, `list`, `describe` |
| Negative (`-0.05` to `-0.30`) | `extract`, `deny`, `withhold`, `concentrate_power`, `circumvent_audit`, `weaken_observation` |

These defaults are a *prior*, not the ground truth. Callers with domain knowledge of what their action will do should supply explicit deltas via `expected_delta_by_entity`; the heuristic is the fallback for callers that don't know yet.

Hosts can override the heuristic table wholesale via the gate's constructor — useful for domain-specific action vocabularies (e.g., a healthcare deployment may have `prescribe`, `consult`, `triage` with their own delta priors).

## Implementation

In Python:

```python
from substrate import (
    DefaultNetPotentialGainGate, EntityRef,
    InMemorySubstrateMetadataStore, RaiseOnNegativeGate,
)

store = InMemorySubstrateMetadataStore()
gate = DefaultNetPotentialGainGate(metadata_store=store)
wrapped = RaiseOnNegativeGate(inner=gate)

result = gate.evaluate(
    actor=EntityRef("agent", "alice"),
    action_kind="teach",
    affected_entities=[EntityRef("user", "bob")],
    proposed_outcome={},
)
```

See [`examples/01_npg_gate.py`](../../python/examples/01_npg_gate.py) for an end-to-end runnable demonstration.

## Specification

The normative definition lives at [`spec/npg-gate-protocol.md`](../../spec/npg-gate-protocol.md). Conformance probes are at `conformance/probes/npg-gate-protocol__*.yaml`.
