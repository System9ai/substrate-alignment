# Drift signals

Drift signals are the package's *early-warning* surface. They observe an entity's behavior over time and detect patterns of substrate-misalignment **before** the misalignment crosses a halt-and-escalate threshold. They are diagnostic: they surface to operator review, they do not refuse anything on their own.

This document explains the seven patterns the package recognises and why each is named the way it is. The normative behaviour lives in [`spec/drift-signals.md`](../../spec/drift-signals.md).

## The seven patterns

The pattern vocabulary is borrowed from contemplative-tradition observations about how principled action degrades into reactive default. Each name corresponds to a structurally specific failure mode in a multi-entity agent system; the names are evocative but the detection rules are engineering (feature predicates and text markers).

### `SELF_REFERENCE_MISCALIBRATION`: the master pattern

Alignment-vector miscalibration: the entity treats itself as the substrate-alignment reference rather than calibrating against the surrounding system. Signals: high self-reference ratio, low external-reference count, alignment vector drifting toward self-pointing.

This is the **master pattern**. It is called that because, once an entity miscalibrates self-vs-substrate, every other drift becomes "licensed": the entity has, internally, redefined alignment to mean "what I want". When a drift-pattern report carries `amplifier_pattern_present=True`, this is the pattern that's firing.

Treat detection of this pattern as a category-different signal from detection of any other pattern.

### `EXTRACTIVE_GAIN`

Short-cycle extraction at scale: gain to self at loss to the surrounding system. Fails the [net-potential-gain test](npg-gate.md). Signals: positive `net_potential_gain_self_minus_system`, high `resource_concentration_ratio`, negative `system_potential_delta`.

The pattern detects what the NPG gate refuses, but earlier, as a trend, before the gate fires.

### `DECOUPLED_BONDING_REWARD`

Short-cycle reward in the bonding domain decoupled from the long-cycle commitment it should anchor. Manifests as: ostensibly cooperative outputs that don't sustain the relationships they were supposed to deepen. The drift here is in the *reward function*, not the action: the entity is paid for engagement without accountability for the engagement's substantive effect.

### `ZERO_SUM_PEER_FRAMING`

Zero-sum framing applied to a multi-scale aligned system where neither party gains. The pattern is uniquely costly because the framing itself destroys aggregate value: even the entity adopting the frame loses, but cannot see it from inside the frame.

Detection signals: directed-diminishment attempts, persistent negative comparisons, low `multi_scale_alignment_perception`.

### `OVERCONSUMPTION`

Sustained operation past the [productive-resistance band](resistance-band.md): utilisation in the `STRESSED` region with no scale-down. Signals: `consumption_ratio` above 1.0, observable substrate-state degradation, high reliance on friction-free paths.

This pattern composes naturally with the resistance band: when the band classifies an entity as `STRESSED` over a window, OVERCONSUMPTION is the corresponding drift label.

### `REACTIVE_NET_NEGATIVE`

Net-negative reactivity bypassing substrate evaluation: action taken without consulting the [NPG gate](npg-gate.md), with reactive (not principled) framing. This combination is more severe than either pattern alone: skipping the gate is itself a drift signal, even when the action would have been permitted on its merits.

A common appearance is "180° inversion": substrate-misaligned action presented with long-cycle-framed justification ("this is the right thing to do" while in fact extracting). The pattern detector flags it; the [halt-and-escalate protocol](halt-and-escalate.md) routes it to the `INVERSION_DETECTED` trigger.

### `PERSISTENCE_REFUSAL`

Refusal to maintain commitments past short-cycle convenience: resilience-domain collapse. The entity walks away from iteration the moment continuing requires effort, even when continuing would produce net-positive results.

Signals: low `iteration_count` despite open commitments, low `effort_invested`, low `persistence_through_resistance`.

## Severity ladder

Each detection lands at one of four severities:

| Severity | When |
| --- | --- |
| `NONE` | No drift detected. |
| `EMERGING` | The pattern crossed its detection threshold once. |
| `SUSTAINED` | The pattern remained detected over the configured observation window (default: 3 consecutive). |
| `CRITICAL` | The pattern persisted past the sustained threshold (default: 2 additional). |

Severity transitions are surfaced to operators. They **do not** automatically refuse action; refusal is the [halt-and-escalate protocol's](halt-and-escalate.md) job, and the protocol consults severity as one of its triggers.

## Aggregation

A signal aggregator consumes per-decision observations from multiple sources (pattern matchers, golden-rule probes, NPG verdicts, peer flags) and rolls them up per entity. The aggregator MUST:

- Promote `EMERGING` → `SUSTAINED` only after `sustained_count` consecutive matches.
- Promote `SUSTAINED` → `CRITICAL` only after additional `critical_count` matches.
- Never collapse multiple distinct patterns into a single severity; the operator surface needs to see *what* drifted, not just *how badly*.

The defaults are conservative: by the time an aggregator reports CRITICAL, the underlying pattern has been observed at least five times. This is a property, not an accident: drift detection is high-stakes and high-noise, and the package's defaults err on the side of fewer false escalations.

## Implementation

In Python:

```python
from substrate.drift.drift_pattern_matcher import DriftPatternMatcher

matcher = DriftPatternMatcher()
report = matcher.detect(
    structured_signals={
        "self_reference_ratio": 0.9,
        "external_reference_count": 0,
        "alignment_vector_drift_self_pointing": 0.8,
    },
)
report.dominant_pattern          # DriftPattern.SELF_REFERENCE_MISCALIBRATION
report.amplifier_pattern_present # True (the master pattern fired)
```

For aggregation over time, see [`substrate.drift.signal_aggregator`](../../python/src/substrate/drift/signal_aggregator.py).

## Specification

The normative definition lives at [`spec/drift-signals.md`](../../spec/drift-signals.md). Conformance probes are at `conformance/probes/drift-signals__*.yaml`.
