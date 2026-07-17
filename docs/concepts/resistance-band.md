# Resistance band

The *productive-resistance band* is the package's primitive for deriving operational thresholds (rate limits, batch sizes, retry caps, queue depths, ring sizes) from a single, principled anchor. Instead of every subsystem picking its own multiplier (and drifting independently), all thresholds derive from the same band.

The three-state band classifies **imposed resistance**: the challenge deliberately applied to an entity (a fraction in `[0.0, 1.0]`). It is *not* the classifier for the work an entity carries. Carried work, and the load an entity is under, are governed by the finer layered model in [Advanced](#advanced-the-layered-capacity-model) below, where healthy work cruises all the way up to `0.50` and only sustained load past `2/3` is damage. Conflating the two, for example reading `1/φ²` as a utilisation ceiling, is the inversion the standard guards against.

| State | Meaning (resistance lens) |
| --- | --- |
| `UNDER_LOADED` | Below the band's lower edge. More challenge could be applied. |
| `PRODUCTIVE` | Inside the band. Imposed resistance is calibrated; hold or fine-tune. |
| `STRESSED` | Above the band's upper edge. Imposed resistance is miscalibrated. |

The package's default bounds are `1/3 ≈ 0.3333` (lower) and `1/φ² ≈ 0.3820` (upper). The midpoint is the closed-loop calibration setpoint for resistance.

## Why those specific numbers

The choice of `1/3` and `1/φ²` is not arbitrary, and explaining it is the point of this document. (The source code keeps engineering vocabulary only; the derivation lives here, where readers expecting a "concepts" document can find it.)

### The lower edge: `1/3`

The lower bound is the *partition anchor*. A system that observes itself in three roughly-equal classes (input / processing / output, or read / compute / write, or load / store / cleanup) runs healthily when each class consumes about one-third of the available cycle. Drop below that and you've stopped doing one of the three.

Three is the smallest number of classes a self-referential system needs to avoid collapsing into binary dichotomies (which generate the substrate-misalignment patterns `ZERO_SUM_PEER_FRAMING` and `SELF_REFERENCE_MISCALIBRATION` at scale). The `1/3` lower bound is the operational expression of that requirement.

### The upper edge: `1/φ² ≈ 0.382`

The upper bound is the *self-similarity anchor*. The golden ratio `φ = (1 + √5) / 2 ≈ 1.618` is the most compact ratio under which a system's parts have the same ratio to each other as the whole has to its largest part. Equivalently, it is the unique ratio under which the system can subdivide indefinitely without drift.

`1/φ² = 2 - φ ≈ 0.382` is the level at which *imposed resistance* reaches the limit of compact self-similar subdivision. Push resistance past it and the headroom needed for self-observation and audit (which itself consumes resources) gets squeezed. This is the resistance ceiling, not a limit on the work an entity may carry; carried work healthily runs well above it (see [Advanced](#advanced-the-layered-capacity-model)).

These two anchors aren't tied to any specific application: they're properties of the *shape* of any self-observing system that needs to maintain alignment under operation. The package ships them as defaults; hosts that have independent evidence their system tolerates a wider band can tighten further, but **cannot widen beyond the defaults** without exiting the productive band.

### Why tighter, not looser, override

A common ask is "can I set my upper bound to 0.5, since my subsystem can handle it?". The answer is **no**, and the rejection is a deliberate package-level discipline:

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

# Classification (the resistance lens: 0.50 is well over the resistance band).
classify(0.50)  # ResistanceBandClassification.STRESSED

# Full assessment with scaling factor.
a = assess(0.50)
a.recommended_scaling_factor  # 0.715: resistance over-calibrated, ease the challenge ~30%

# Threshold derivation.
soft, hard = derive_quota_pair(1000)        # (333, 381)
batch_size = derive_batch_size(1000)        # 357
```

`classify` and `assess` are the resistance lens. A reading of `0.50` for the **work** an entity carries is the top of the sustainable work zone (`UPPER_WORK`), not a stress signal; classify carried work with `classify_zone` (see [Advanced](#advanced-the-layered-capacity-model)). See [`examples/02_resistance_band.py`](../../python/examples/02_resistance_band.py) for an end-to-end runnable demonstration.

## Advanced: the layered capacity model

*Most integrations need only the three-state band above: classify utilisation,
derive thresholds, done. This section is for entities that additionally govern the
**work** they carry and the **growth** they undergo. These are distinct governed
quantities with their own zones; conflating them with resistance is a modelling
error. Read on only if you are building that.*

### The layered zone model

The three-state classifier above governs **resistance**: challenge imposed on an entity, productive at 33–38%. **Work** (load an entity carries) obeys a layered model anchored on the same constants plus the φ-conjugate and the thirds. The ladder is mirror-symmetric about the `0.50` pivot, and the **debt line is the uniform `2/3 ≈ 0.667`**, not `0.618`:

- **`< 1/3`: rest.** Legitimate recovery. Repeatedly approaching the work-entry threshold and retreating while work is pending is *avoidance* (a temporal pattern, see below).
- **`[1/3, 1/φ²]`: calibration.** The work-entry threshold; where imposed resistance calibrates.
- **`(1/φ², 0.5]`: the work zone.** Genuinely productive sustained effort: "in the zone but not rising too fast." A retracement into 38.2–50% continues the trend (the Fibonacci-retracement reading). The **inner ninth `4/9 ≈ 0.444`** (the work-zone midpoint) subdivides it into a **lower work zone** `(1/φ², 4/9]` (settling into cruise) and an **upper work zone** `(4/9, 0.5]` (climbing to the pivot).
- **`(0.5, 1/φ]`: peaking.** Growth: transient peaks build (intervals). Past the 50% line a turnaround is expected. Tolerable sporadically; never sustained. The **inner ninth `5/9 ≈ 0.556`** (the mirror of `4/9`; `4/9 + 5/9 = 1`) subdivides it into **early peaking** `(0.5, 5/9]` (the burst beginning, headroom still there) and **committed peaking** `(5/9, 1/φ]` (deep in the burst, nearing the peak; resolve, don't settle).
- **`(1/φ, 2/3]`: warning.** Winded: the approach to burnout; the mirror of calibration. Still not yet debt.
- **`> 2/3 ≈ 0.667`: debt.** Sustained operation past the uniform `2/3` debt line accrues **compensation debt**.

The inner ninths `4/9` and `5/9` are the **mod-9 refinement** of the thirds (`3/9 = 1/3` and `6/9 = 2/3` are the outer thirds; `4/9`/`5/9` the inner ninths straddling the `4.5/9 = 0.50` pivot). They are **first-class levels**, not markers: `LoadZone` and its wire twin `ZoneClassification` are eight-valued, and `classify_zone` / `classify_load_zone` return the eight-way classification directly. The outer φ-conjugate/thirds boundaries, the `2/3` debt line, the temporal contract, and the mirror symmetry are all unchanged. The only coarse projection is the three-state `ResistanceBandClassification` (all four work/peaking levels + warning + debt → `STRESSED`); consumers that want the coarse work/peaking band use the grouping sets `WORK_LEVELS`/`PEAKING_LEVELS` (`LoadZone`) or `WORK_ZONES`/`PEAKING_ZONES` (`ZoneClassification`): grouping, not folding the model.

### The φ-conjugate: maintained capacity and the failover ceiling

`1/φ = φ − 1 ≈ 0.618` is the upper bound's complement structure: the fraction of capacity an entity maintains for itself. It is load-bearing in **three** roles: the **top of the PEAKING / growth band**, the **WARNING-band floor**, and the **failover-spike ceiling** (a survivor may transiently spike toward it after a peer fails, then rebalance). But it is **never the debt line**. The debt line is `2/3`. An entity above the calibration band is spending out of the ~62% it maintains; spending it sporadically absorbs spikes, and only sustained operation past `2/3` is burnout the system owes compensation for.

### Burnout, debt, and compensation

Debt is a **transferable obligation**: the work zone is sized so peers carry pickup headroom (the same arithmetic as N+1 failover: `maintain_target(N) = min(0.5, (1/φ)·(N−1)/N)` keeps every survivor's transient failover spike at or under the φ-conjugate ceiling after one peer fails). The compensation order is peer pickup → recovery window → capacity grant (φ-stepped) → human escalation; pickup that pushes a carrier past the φ-conjugate failover ceiling is contagion, not compensation, and a refusal to compensate is itself a drift signal. Reciprocity is recorded over time: chronic debtors signal structural under-capacity (grow, don't endlessly carry); free riders signal a net-potential-gain inversion.

### Sporadic vs sustained

The zone model is instantaneous; the contract is temporal. `SustainedLoadTracker` distinguishes a *spike* (single excursion past 0.5 that decays) from *sustained strain* (consecutive observations past 0.5) from *debt accrual* (sustained past the `2/3` debt line; units = breach magnitude × duration), and detects *avoidance* (approach→retreat bounces off the work-entry threshold with work pending). Growth has its own temporal discipline: at most φ (≈1.618×) per step, consolidation between steps; consecutive growth without consolidation is *runaway growth* (mechanism 6).

## Specification

The normative behaviour (band classification, override discipline, threshold helpers) is in [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md) as mechanism 4. Conformance probes are at `conformance/probes/runaway-power-prevention__mech-4__*.yaml`.
