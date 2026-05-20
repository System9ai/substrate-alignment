# NetPotentialGainGate protocol

> **Status:** v0.1.0-draft. Subject to revision before the first tagged release.

This specification defines the *net-potential-gain gate* — the decision gate that consequential actions in a substrate-aligned system must route through. The gate answers a single question: *does this proposed action raise or lower the net alignment of the affected entities, taken together?*

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) when, and only when, they appear in all capitals.

## 1. Verdict

A conforming implementation MUST expose four verdict values:

| Value | Serialised form | Meaning |
| --- | --- | --- |
| `NET_POSITIVE` | `"net_positive"` | Aggregate projected delta is positive above the positive threshold. |
| `NET_NEUTRAL` | `"net_neutral"` | Aggregate projected delta is within the neutral band. |
| `NET_NEGATIVE` | `"net_negative"` | Aggregate projected delta is negative below the negative threshold. |
| `INSUFFICIENT_DATA` | `"insufficient_data"` | The gate cannot decide; the caller must supply more context. |

The serialised forms are canonical. Alternative casings or labels are **NOT** conformant.

## 2. Gate inputs

A conforming gate's `evaluate` method MUST accept:

| Parameter | Type | Description |
| --- | --- | --- |
| `actor` | typed entity reference, or bare entity-id string | The entity proposing the action. |
| `action_kind` | non-empty string | A discriminator that selects a scoring heuristic. |
| `affected_entities` | sequence of entity references | Entities whose alignment may shift as a result. |
| `proposed_outcome` | mapping with string keys | Opaque to the Protocol; specific evaluators look for keys they understand. |

Implementations MUST reject an empty `action_kind` with a typed validation error.

Implementations SHOULD accept both the typed entity-reference form and a legacy entity-id-string form for `actor` and `affected_entities`. When a string is provided, the implementation MUST coerce it to a typed reference using a documented default entity-type (the reference implementation uses `"entity"`).

## 3. Evaluation algorithm

A conforming gate MUST produce a verdict by the following algorithm:

1. **Actor-only short-circuit.** If `affected_entities` is empty, return `NET_NEUTRAL` with an explanatory reasoning string. The substrate-alignment value test is about effect on *other* entities; a self-action carries no net effect.

2. **Resolve per-entity deltas.** In order:
   1. If `proposed_outcome["expected_delta_by_entity"]` is a `Mapping[str, float]` covering every entity-id in `affected_entities`, use that mapping directly. This is the caller-supplied-projection path.
   2. Otherwise, look up `action_kind` in the implementation's action-kind heuristic table. If a heuristic exists, apply it uniformly across the affected entities.
   3. If neither path yields a delta for every affected entity, return `INSUFFICIENT_DATA`.

3. **Existence check.** For each affected entity, the gate MUST consult its injected metadata store. If the store has no record for an affected entity, the gate MUST return `INSUFFICIENT_DATA` and surface the missing entities in the evaluation's `missing_metadata_for` field. Silent default-to-permissive is **NOT** conformant.

4. **Aggregate.** Sum the per-entity deltas. Clamp the sum to `[-1.0, 1.0]`. Apply the threshold:
   - `score > +positive_threshold`  → `NET_POSITIVE`
   - `score < -positive_threshold`  → `NET_NEGATIVE`
   - otherwise                      → `NET_NEUTRAL`

## 4. Constructor validation

A conforming gate's constructor MUST reject any `positive_threshold` outside the open interval `(0.0, 1.0]` with a typed validation error. The default is `0.05`.

## 5. Result shape

A conforming evaluation result MUST be immutable and MUST carry at minimum:

- The verdict.
- The actor and affected entities (typed references).
- The aggregate score (in `[-1.0, 1.0]`).
- The per-entity deltas (parallel to `affected_entities`).
- A human-readable reasoning string.
- A wall-clock timestamp at evaluation time.
- The list of entities whose metadata was missing (empty unless verdict is `INSUFFICIENT_DATA`).

The reasoning string MUST contain the verdict label, the score, the actor identifier, and the per-entity contributions. Operator surfaces depend on this format.

## 6. The "raise on negative" adapter

A conforming implementation SHOULD provide a wrapper that escalates `NET_NEGATIVE` verdicts to a typed exception while passing `NET_POSITIVE`, `NET_NEUTRAL`, and `INSUFFICIENT_DATA` through unchanged. The exception MUST carry the underlying evaluation so callers can audit and surface per-entity contributions in refusal messages.

Callers that must refuse-on-negative wrap the gate in this adapter.

## 7. Conformance

A conforming implementation MUST pass every probe in `../conformance/probes/` whose filename begins with `npg-gate-protocol__`.

## 8. Reference implementation

In the Python reference implementation:

- Gate Protocol and default: [`substrate.net_potential_gain_gate`](../python/src/substrate/net_potential_gain_gate.py)
- Storage adapter: [`SubstrateMetadataStore` and `InMemorySubstrateMetadataStore`](../python/src/substrate/types.py)
- Result type: `NetPotentialGainEvaluation`
- Refusal exception: `NetPotentialGainNegative`
- Default action-kind heuristics: `ACTION_KIND_HEURISTICS`
