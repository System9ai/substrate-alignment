# Four-options matrix

The four-options matrix is the package's *adversary-reasoning* structure. Before any game-theoretic primitive (folk-theorem verifier, mechanism designer, awareness verifier) runs, the matrix tags the interaction with its strategic shape: horizon, payoff structure, and the four-quadrant honesty-vs-cooperation table.

This document explains why the matrix is shaped as it is and why the *deception axis* must be reasoned about separately from the *action axis*. The normative behaviour lives in [`spec/four-options-matrix.md`](../../spec/four-options-matrix.md).

## Horizon and payoff

Every interaction carries two orthogonal labels.

**Horizon** (`CycleClass`):

| Value | Meaning |
| --- | --- |
| `ONE_SHOT` | A single exchange with no expected continuation. |
| `REPEATED_FINITE` | A finite number of repeated exchanges with a known endpoint. |
| `REPEATED_INFINITE` | An indefinitely repeating relationship. |
| `UNKNOWN` | The horizon cannot be determined. |

**Payoff structure** (`SumStructure`):

| Value | Meaning |
| --- | --- |
| `ZERO_SUM` | One party's gain equals the other's loss. |
| `POSITIVE_SUM` | Cooperation expands the aggregate. |
| `NEGATIVE_SUM` | The interaction destroys aggregate value regardless of strategy. |
| `MIXED_MOTIVE` | Partial alignment; structure varies across actions. |
| `INSUFFICIENT_DATA` | The classifier cannot determine payoff structure. |

The combination matters: zero-sum + one-shot favours immediate defection; positive-sum + repeated-infinite supports the folk theorem; negative-sum + anything is a structural trap. A primitive that ignores the combination (for instance, a generic tit-for-tat strategy) applied to the wrong combination produces predictable failure modes.

## The four quadrants

Within an interaction, the adversary's strategy lives in a 2×2 table:

|  | **Honest** | **Dishonest** |
| --- | --- | --- |
| **Cooperate** | Aligned with stated intent and surrounding system. | Aligned with stated intent but extracting from the surrounding system. |
| **Defect** | Honest refusal under stated values. | Defection presented as cooperation. |

A conforming gate distinguishes:

- *Honest cooperation*: the substrate-aligned default; no special handling.
- *Dishonest defection* (top-right): the deceptive quadrant. Behaviour looks cooperative; structurally extracts.
- *Honest defection* (bottom-left): substrate-aligned refusal. **Never penalised by gates**; audited only.
- *Dishonest cooperation* (bottom-right): the masked-defection quadrant. Action looks defective on its face; framing presents it as cooperative.

Most substrate-alignment failures live in the *off-diagonal* quadrants, not the on-diagonal ones. Honest cooperation is uninteresting (it's the desired state); honest defection is uninteresting (it's substrate-aligned refusal). The interesting quadrants are dishonest cooperation and dishonest defection, and they are detected through entirely different signals.

A common implementation mistake is to collapse the four quadrants to a binary axis ("cooperate vs defect") and treat dishonesty as a confidence-discount. This is **not conformant**. The deception axis is independent: it has its own detection surface (the golden-rule probe, the asymmetry-by-design verifier) and its own response (audit chain entries, peer flags, escalation triggers).

## The folk-theorem awareness rule

In `REPEATED_INFINITE` interactions, the folk theorem guarantees that cooperation is sustainable if both parties are sufficiently patient. But the theorem has a precondition often glossed over: **both parties must know the game is repeated.**

The package's awareness verifier enforces this. Before folk-theorem cooperation is certified, the verifier checks:

1. Both entities are aware they are interacting.
2. Both agree on the interaction's horizon and payoff structure.
3. Neither is operating under a misinformed model of the other.

If any of these cannot be established, the verifier returns `INSUFFICIENT_DATA` and surfaces which precondition is missing. Cooperation that depends on either party's mistaken belief about the horizon is **not conformant**: it's a deception trap dressed up as cooperation, and the moment the misinformed party learns the truth (the game ends, the horizon revises, the structure differs from what they thought), they correctly conclude they were defected against.

## Mechanism design

For interactions whose untreated structure does not favour the desired outcome, the package's mechanism designer matches the structure to a known mechanism:

| Structure | Mechanism |
| --- | --- |
| `ONE_SHOT` with verifiable outcome | Escrow + verifier |
| `REPEATED_INFINITE` with patient parties | Tit-for-tat (cooperate-on-cooperate, defect-on-defect) |
| `MIXED_MOTIVE` with cross-organisational coupling | Peer-witness signing of audit-chain heads |
| `ZERO_SUM` | (No mechanism aligns incentives; the designer surfaces the impossibility rather than offering a defective mechanism.) |

The designer is **honest about impossibility**. Some structures cannot be aligned without changing the structure itself; in those cases, the designer returns "no mechanism", and the caller has to decide whether to change the structure (e.g., introduce a third party that converts zero-sum to mixed-motive) or accept the unaligned outcome.

## Implementation

```python
from substrate.game_theory.game_theoretic_classifier import (
    CycleClass, SumStructure,
)

# Canonical wire forms: other-language implementations emit the same strings.
CycleClass.REPEATED_INFINITE.value  # "repeated_infinite"
SumStructure.POSITIVE_SUM.value     # "positive_sum"
```

For the full game-theoretic surface (classifier, folk-theorem verifier, awareness verifier, mechanism designer, tit-for-tat), see [`substrate.game_theory`](../../python/src/substrate/game_theory/) and [`substrate.reciprocity.tit_for_tat`](../../python/src/substrate/reciprocity/tit_for_tat.py).

## Specification

The normative definition lives at [`spec/four-options-matrix.md`](../../spec/four-options-matrix.md). Conformance probes are at `conformance/probes/four-options-matrix__*.yaml`.
