# Operating mode

The *substrate-alignment operating mode* is a four-valued summary of how an entity is currently behaving in a multi-entity agent system. It is the foundation every other primitive in the package builds on: gates filter by mode, drift detectors compare against mode, audit records carry mode at the time of decision.

The mode is **diagnostic**, not punitive. A `SHORT_CYCLE` classification surfaces an entity to operator review; it does not trigger an automatic refusal. Refusals are the responsibility of the [net-potential-gain gate](npg-gate.md) and the [halt-and-escalate protocol](runaway-power-prevention.md).

## The four modes

| Mode | When it applies |
| --- | --- |
| `LONG_CYCLE` | Sustained, contextual, principled operation. The substrate-aligned default for production agents. |
| `MIXED` | A blend of cycles; the classifier could not commit to one of the others. |
| `SHORT_CYCLE` | Rapid, transactional, low-context operation. Suitable for cache fills and throw-away inferences; **not** suitable for consequential decisions affecting other entities. |
| `UNKNOWN` | The classifier has never observed the entity. Distinct from `SHORT_CYCLE` (which means "actively low") because the operator surface needs to distinguish "needs classification" from "needs review". |

The distinction between `UNKNOWN` and `SHORT_CYCLE` is load-bearing. Consider an entity that has never produced any signal. What should the system assume?

- If we collapse it to `SHORT_CYCLE` ("low alignment by default"), we permanently de-rate every newly-created entity and create perverse incentives to avoid scrutiny.
- If we collapse it to `LONG_CYCLE` ("high alignment by default"), the gate's existence check (mechanism 1) collapses to permissive: anyone can act under defaults.

`UNKNOWN` resolves the dilemma honestly: the system *does not know*, and the operator decides what to do with that.

## The alignment vector

Each entity carries four scalar components in `[0.0, 1.0]`:

| Component | What it measures | Typical host source |
| --- | --- | --- |
| `trust` | Reliability for declared intent | Trust scorer (verification depth + accuracy + recency) |
| `expertise` | Competence in the relevant domain | Expertise tracker (domain success rates) |
| `capability` | Headroom to act effectively | Capability publisher (skills + capacity) |
| `health` | Freedom from operational degradation | Health checker (uptime, error rate) |

The package takes **no opinion** on how each component is computed. Host applications integrate against their own subsystems; the package only specifies the shape (`[0.0, 1.0]`) and the aggregation.

## Aggregation: from vector to mode

The four components roll up into a single `net_potential` score via weighted sum:

```
net_potential = w_trust·trust + w_expertise·expertise + w_capability·capability + w_health·health
```

The default weights `(0.35, 0.30, 0.20, 0.15)` favour trust and expertise (the "reliably doing the right thing" axis) over capability and health (the "able to act" axis). The rationale: an entity with high capability but low trust is more dangerous than one with low capability but high trust.

Hosts can override weights per call (or wholesale via a custom `AlignmentWeights`); the package validates that the override sums to `1.0 ± 0.01` and rejects out-of-range components.

`net_potential` then bands into a mode under the default thresholds:

| `net_potential` range | Mode |
| --- | --- |
| `[0.70, 1.00]` | `LONG_CYCLE` |
| `[0.40, 0.70)` | `MIXED` |
| `(0.00, 0.40)` | `SHORT_CYCLE` |
| `0.00` exactly | `UNKNOWN` |

The default `LONG_CYCLE` threshold is tuned conservatively: only entities with strong signals across all four components reach it by auto-classification. This is the conservative side: under-classifying surfaces the entity to operator review; over-classifying permits action under defaults.

## Implementation

In Python:

```python
from substrate import (
    AlignmentVector, AlignmentWeights,
    auto_classify_mode, compute_alignment_vector, compute_net_potential,
)

vec = compute_alignment_vector(trust=0.8, expertise=0.7, capability=0.6, health=0.7)
np = compute_net_potential(vec)                      # 0.7150
mode = auto_classify_mode(np)                        # SubstrateMode.LONG_CYCLE
```

For folding live signal-source updates into stored metadata, see [`AlignmentRefresher`](alignment-refresher.md).

## Specification

The normative definition lives at [`spec/operating-mode.md`](../../spec/operating-mode.md). Conformance probes that pin down each clause are at `conformance/probes/operating-mode__*.yaml`.
