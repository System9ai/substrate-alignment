# Resistance band

The *productive-resistance band* is the package's primitive for deriving operational thresholds — rate limits, batch sizes, retry caps, queue depths, ring sizes — from a single, principled anchor. Instead of every subsystem picking its own multiplier (and drifting independently), all thresholds derive from the same band.

The band classifies utilisation (the fraction of capacity in use, in `[0.0, 1.0]`) into three states:

| State | Meaning |
| --- | --- |
| `UNDER_LOADED` | Below the band's lower edge. Useful work could be added. |
| `PRODUCTIVE` | Inside the band. Hold or fine-tune. |
| `STRESSED` | Above the band's upper edge. Drift risk grows; shed load. |

The package's default bounds are `1/3 ≈ 0.3333` (lower) and `1/φ² ≈ 0.3820` (upper). The midpoint is the closed-loop target.

## Why those specific numbers

The choice of `1/3` and `1/φ²` is not arbitrary, and explaining it is the point of this document. (The source code keeps engineering vocabulary only; the derivation lives here, where readers expecting a "concepts" document can find it.)

### The lower edge: `1/3`

The lower bound is the *partition anchor*. A system that observes itself in three roughly-equal classes — input / processing / output, or read / compute / write, or load / store / cleanup — runs healthily when each class consumes about one-third of the available cycle. Drop below that and you've stopped doing one of the three.

Three is the smallest number of classes a self-referential system needs to avoid collapsing into binary dichotomies (which generate the substrate-misalignment patterns `ZERO_SUM_PEER_FRAMING` and `SELF_REFERENCE_MISCALIBRATION` at scale). The `1/3` lower bound is the operational expression of that requirement.

### The upper edge: `1/φ² ≈ 0.382`

The upper bound is the *self-similarity anchor*. The golden ratio `φ = (1 + √5) / 2 ≈ 1.618` is the most compact ratio under which a system's parts have the same ratio to each other as the whole has to its largest part. Equivalently, it is the unique ratio under which the system can subdivide indefinitely without drift.

`1/φ² = 2 - φ ≈ 0.382` is the fraction at which utilisation reaches the limit of compact self-similar subdivision. Above it, the system can still operate, but the headroom needed for self-observation and audit (which itself consumes resources) gets squeezed.

These two anchors aren't tied to any specific application — they're properties of the *shape* of any self-observing system that needs to maintain alignment under operation. The package ships them as defaults; hosts that have independent evidence their system tolerates a wider band can tighten further, but **cannot widen beyond the defaults** without exiting the productive band.

### Why tighter, not looser, override

A common ask is "can I set my upper bound to 0.5 — my subsystem can handle it?". The answer is **no**, and the rejection is a deliberate package-level discipline:

- The band is the substrate-alignment-discipline anchor. Once each subsystem picks its own anchor, the system loses the property that thresholds across subsystems are commensurable.
- A subsystem that can "handle" 0.5 utilisation can also handle the productive band; widening past it doesn't add value, only risk.

Tightening, on the other hand, is welcome: a subsystem with independent evidence of a narrower safe envelope can run inside that envelope without losing commensurability.

## How thresholds derive

Given any *capacity* `C`, the package derives operational thresholds as `C × band_position`:

| Threshold | Position |
| --- | --- |
| Soft limit | Lower (`~1/3`) |
| Target | Midpoint (`~0.358`) |
| Hard limit | Upper (`~1/φ²`) |
| Batch size | Midpoint |
| Retry cap | Upper |

The helpers (`derive_soft_limit`, `derive_target`, `derive_hard_limit`, `derive_batch_size`, `derive_retry_cap`, `derive_quota_pair`, `derive_threshold_float`) round down to integers where appropriate and floor trivial cases at 1.

For closed-loop control (where a controller adjusts the current load toward the target), the band exposes `recommend_scaling_factor(utilisation) = target / utilisation`. A scaling factor `> 1` says scale up; `< 1` says scale down; `1.0` says hold.

## Implementation

In Python:

```python
from substrate import classify, assess, recommend_scaling_factor
from substrate.threshold_derivation import derive_quota_pair, derive_batch_size

# Classification.
classify(0.50)  # ResistanceBandClassification.STRESSED

# Full assessment with scaling factor.
a = assess(0.50)
a.recommended_scaling_factor  # 0.715 — shed about 30% of load

# Threshold derivation.
soft, hard = derive_quota_pair(1000)        # (333, 381)
batch_size = derive_batch_size(1000)        # 357
```

See [`examples/02_resistance_band.py`](../../python/examples/02_resistance_band.py) for an end-to-end runnable demonstration.

## Specification

The normative behaviour (band classification, override discipline, threshold helpers) is in [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md) as mechanism 4. Conformance probes are at `conformance/probes/runaway-power-prevention__mech-4__*.yaml`.
