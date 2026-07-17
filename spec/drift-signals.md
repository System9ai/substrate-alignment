# Drift signals

> **Status:** v0.2.0-draft. Subject to revision before the first tagged release.

This specification defines the *drift signals*: observational patterns that flag an entity drifting from substrate-aligned operation. Drift signals are diagnostic, not punitive: they surface to operator review, they do not trigger automatic shutdown.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) when, and only when, they appear in all capitals.

## 1. Drift patterns

A conforming implementation MUST recognise seven drift patterns. Each names a characteristic way substrate-aligned (long-cycle) operation can collapse to a reactive default:

| Pattern | Serialised form | Description |
| --- | --- | --- |
| `SELF_REFERENCE_MISCALIBRATION` | `"self_reference_miscalibration"` | Alignment-vector miscalibration: self treated as the reference rather than calibrating against the surrounding system. The **master pattern**; converts every other impulse into licensed misalignment. |
| `EXTRACTIVE_GAIN` | `"extractive_gain"` | Short-cycle extraction at scale: gain to self at loss to the system. Fails the net-potential-gain test. |
| `DECOUPLED_BONDING_REWARD` | `"decoupled_bonding_reward"` | Short-cycle reward in the bonding domain decoupled from the long-cycle commitment it should anchor. |
| `ZERO_SUM_PEER_FRAMING` | `"zero_sum_peer_framing"` | Zero-sum framing applied to a multi-scale aligned system where neither party gains. |
| `OVERCONSUMPTION` | `"overconsumption"` | Resource consumption sustained past the productive-resistance band, producing stress and waste. |
| `REACTIVE_NET_NEGATIVE` | `"reactive_net_negative"` | Action taken under reactive cycle with net-negative projected impact. The combination is more severe than either pattern alone. |
| `PERSISTENCE_REFUSAL` | `"persistence_refusal"` | Refusal to maintain commitments past short-cycle convenience; resilience-domain collapse. |

The serialised forms are canonical. Alternative spellings, casings, or labels are **NOT** conformant.

## 2. Drift severity

A conforming implementation MUST classify each detected drift signal at one of four severities:

| Severity | Serialised form | Meaning |
| --- | --- | --- |
| `NONE` | `"none"` | No drift detected. |
| `EMERGING` | `"emerging"` | A pattern is detectable but below sustained threshold. |
| `SUSTAINED` | `"sustained"` | A pattern is sustained across the observation window. |
| `CRITICAL` | `"critical"` | A pattern is sustained at a severity warranting halt-and-escalate review. |

Severity ordering is total: `NONE < EMERGING < SUSTAINED < CRITICAL`. Implementations MUST preserve this ordering across aggregation.

## 3. Drift signal sources

A conforming implementation MUST aggregate drift signals from at least the following sources:

| Source | What it observes |
| --- | --- |
| `PATTERN` | A drift-pattern match against an entity's behavior trace. |
| `INVERSION` | A 180° inversion event (substrate-misaligned action with long-cycle-framed justification). |
| `ATTACK` | An adversarial or extractive action against another entity. |
| `GOLDEN_RULE_VIOLATION` | An asymmetric reciprocal treatment that the entity would refuse against itself. |
| `NPG_NEGATIVE` | A net-potential-gain gate produced a `NET_NEGATIVE` verdict. |

Implementations MAY add additional sources, but the result MUST identify which source(s) produced each aggregated signal.

## 4. Drift-pattern matcher

A conforming pattern matcher MUST accept:

- A behavior trace (text or structured signals) keyed to an entity.
- Optional configuration (per-pattern thresholds, source-weight overrides).

It MUST return:

- The set of detected patterns.
- A confidence score in `[0.0, 1.0]` per detected pattern.
- An aggregate `dominant_pattern` (the highest-confidence detection), or `None` if no pattern crossed threshold.
- An `amplifier_pattern_present` flag, true iff `SELF_REFERENCE_MISCALIBRATION` is among the detected patterns.

A pattern below its confidence threshold MUST NOT appear in the detected set.

## 5. Aggregation across categories

A conforming signal aggregator MUST:

- Accept, per entity (and scale), a set of per-category drift inputs: for each drift category, an event count and a normalised severity contribution.
- Combine them into a single composite drift-severity score in `[0, 1]` under a configurable per-category weighting.
- Classify the composite score into one of four severities (`NONE`, `EMERGING`, `SUSTAINED`, `CRITICAL`) by configurable score thresholds (defaults: `EMERGING` at composite ≥ `0.2`, `SUSTAINED` ≥ `0.5`, `CRITICAL` ≥ `0.8`).
- Surface the per-category event counts and the categories whose individual contribution exceeds a high-severity threshold (default `0.4`).

Implementations MAY tune the score thresholds and category weights per deployment, subject to `0 < emerging < sustained < critical ≤ 1`, but MUST NOT classify a lower composite score as a higher severity than a higher score.

## 6. Operator surface contract

A conforming aggregator MUST surface, for any entity:

- The current overall severity.
- The per-category event counts.
- The categories contributing above the high-severity threshold.
- The composite severity score and a human-readable rationale.

The operator surface is **diagnostic**: severity classifications MUST surface to operators; they MUST NOT trigger automatic refusals. Automatic refusal is the responsibility of the [halt-and-escalate protocol](runaway-power-prevention.md#3-halt-and-escalate-protocol).

## 7. Conformance

A conforming implementation MUST pass every probe in `../conformance/probes/` whose filename begins with `drift-signals__`.

## 8. Reference implementation

In the Python reference implementation:

- Drift-pattern matcher: [`substrate.drift.drift_pattern_matcher`](../python/src/substrate/drift/drift_pattern_matcher.py)
- Golden-rule probe: [`substrate.drift.golden_rule_probe`](../python/src/substrate/drift/golden_rule_probe.py)
- Signal aggregator: [`substrate.drift.signal_aggregator`](../python/src/substrate/drift/signal_aggregator.py)
- Persisted record shape: [`substrate.audit.substrate_trace`](../python/src/substrate/audit/substrate_trace.py)
