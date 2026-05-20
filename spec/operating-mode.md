# Operating-mode classification

> **Status:** v0.1.0-draft. Subject to revision before the first tagged release.

This specification defines how a conforming implementation classifies an entity's *substrate-alignment operating mode* — the four-valued summary of whether the entity is operating reactively, principledly, or somewhere in between.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) when, and only when, they appear in all capitals.

## 1. Vocabulary

### 1.1 Operating modes

A conforming implementation MUST expose four substrate-mode values:

| Value | Serialised form | Meaning |
| --- | --- | --- |
| `SHORT_CYCLE` | `"ShortCycle"` | Rapid, transactional, low-context operation. |
| `LONG_CYCLE` | `"LongCycle"` | Sustained, contextual, principled operation. |
| `MIXED` | `"Mixed"` | The classifier could not commit to one of the above. |
| `UNKNOWN` | `"Unknown"` | The classifier has not yet observed the entity. |

The serialised form is the canonical wire and storage form. Implementations MUST emit and accept exactly these strings; alternative casings or abbreviations are **NOT** conformant.

### 1.2 Alignment vector

A conforming implementation MUST represent each entity's alignment as a four-component vector, with each component a real number in the closed interval `[0.0, 1.0]`:

| Component | Conventional meaning |
| --- | --- |
| `trust` | The entity's reliability for declared intent. |
| `expertise` | The entity's competence in the relevant domain. |
| `capability` | The entity's headroom to act effectively. |
| `health` | The entity's freedom from operational degradation. |

Out-of-range components MUST be rejected at construction with a typed validation error.

The package does not specify how the host application computes each component; implementations integrate against the host's existing trust-scoring, expertise-tracking, capability-publication, and health-checking subsystems via injection.

### 1.3 Alignment weights

A conforming implementation MUST provide a four-component weight vector `(w_trust, w_expertise, w_capability, w_health)` such that:

- Each weight is in `[0.0, 1.0]`.
- The weights sum to `1.0 ± 0.01`.

Out-of-range or non-summing weight vectors MUST be rejected at construction.

The package defaults are `(0.35, 0.30, 0.20, 0.15)`. Implementations MAY ship different defaults but MUST allow callers to override.

## 2. Net-potential aggregation

A conforming implementation MUST provide a function `compute_net_potential(vector, *, weights)` that:

1. Computes `raw = Σᵢ wᵢ · componentᵢ`.
2. Returns `clamp(raw, 0.0, 1.0)`.

The clamp is defensive — valid inputs cannot produce out-of-range outputs, but implementations MUST still clamp to insulate downstream consumers from numerical drift.

## 3. Auto-classification

A conforming implementation MUST provide a function `auto_classify_mode(net_potential, *, long_cycle_threshold, mixed_threshold)` that returns a substrate mode according to:

```
if net_potential >= long_cycle_threshold:     return LONG_CYCLE
if net_potential >= mixed_threshold:          return MIXED
if net_potential >  0.0:                      return SHORT_CYCLE
                                              return UNKNOWN
```

The default thresholds are `long_cycle_threshold = 0.70` and `mixed_threshold = 0.40`. Implementations MAY ship different defaults but MUST:

- Validate `0.0 ≤ mixed_threshold ≤ long_cycle_threshold ≤ 1.0` at call time.
- Allow per-call override.

The distinction between `UNKNOWN` (no signal yet) and `SHORT_CYCLE` (signal but low) is load-bearing: callers SHOULD treat `UNKNOWN` as "needs classification" and `SHORT_CYCLE` as "actively reactive". Conflating the two is **NOT** conformant.

## 4. Persistence shape

A conforming implementation MUST expose a `SubstrateMetadata` record type with at minimum these fields:

- `entity_type: str` (non-empty)
- `entity_id: str` (non-empty)
- `substrate_mode: SubstrateMode`
- `classifier: str` — names the classifier that produced the mode
- `classifier_rationale: str` — human-readable justification
- `alignment_vector: AlignmentVector`
- `net_potential: float` (in `[0.0, 1.0]`)

The record MUST be frozen (immutable) after construction. The `(entity_type, entity_id)` pair is the composite identity; implementations MUST NOT collapse the pair to a single id.

## 5. Conformance

A conforming implementation MUST pass every probe in `../conformance/probes/` whose filename begins with `operating-mode__`.

## 6. Reference implementation

In the Python reference implementation:

- Types: [`substrate.types`](../python/src/substrate/types.py)
- Aggregation and classification: [`substrate.alignment_computer`](../python/src/substrate/alignment_computer.py)
- Component-refresh coordinator: [`substrate.alignment_refresher`](../python/src/substrate/alignment_refresher.py)
- Storage Protocol: [`SubstrateMetadataStore`](../python/src/substrate/types.py) — with `InMemorySubstrateMetadataStore` as the zero-dependency default.

## 7. Versioning

This document follows [Semantic Versioning](https://semver.org/). Changes that strengthen or add a **MUST** clause are major-version events. Each conformance probe declares the minimum specification version it requires.
