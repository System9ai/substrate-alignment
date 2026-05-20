# Four-options matrix

> **Status:** v0.1.0-draft. Subject to revision before the first tagged release.

This specification defines the *four-options matrix* — the adversary-reasoning structure a conforming implementation uses to classify the strategic shape of an interaction between two entities. The matrix is the building block of the package's game-theoretic primitives (folk-theorem verifier, mechanism designer, awareness verifier).

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) when, and only when, they appear in all capitals.

## 1. Game shape

A conforming classifier MUST tag each interaction with two orthogonal labels.

### 1.1 Interaction horizon

| Value | Serialised form | Meaning |
| --- | --- | --- |
| `ONE_SHOT` | `"one_shot"` | A single exchange with no expected continuation. |
| `REPEATED_FINITE` | `"repeated_finite"` | A finite number of repeated exchanges with a known endpoint. |
| `REPEATED_INFINITE` | `"repeated_infinite"` | An indefinitely repeating relationship; the folk theorem applies. |
| `UNKNOWN` | `"unknown"` | The classifier cannot determine the horizon. |

### 1.2 Payoff structure

| Value | Serialised form | Meaning |
| --- | --- | --- |
| `ZERO_SUM` | `"zero_sum"` | One entity's gain equals the other's loss. |
| `POSITIVE_SUM` | `"positive_sum"` | Cooperation expands the aggregate; both parties can gain together. |
| `NEGATIVE_SUM` | `"negative_sum"` | The interaction destroys aggregate value regardless of strategy. |
| `MIXED_MOTIVE` | `"mixed_motive"` | Partial alignment; structure varies across actions. |
| `INSUFFICIENT_DATA` | `"insufficient_data"` | The classifier cannot determine payoff structure. |

(Uncoupled payoffs — where one entity's outcome does not depend on the other — are surfaced through the orthogonal `CoordinationKind.INDEPENDENT` classification rather than as a sum-structure value.)

The serialised forms are canonical.

## 2. The four options

For each `(horizon, payoff)` pairing, the classifier maps the adversary's available strategies to a four-way table:

| | Honest | Dishonest |
| --- | --- | --- |
| **Cooperate** | Aligned with stated intent and surrounding system. | Aligned with stated intent but extracting from surrounding system. |
| **Defect** | Honest refusal under stated values. | Defection presented as cooperation. |

A conforming gate MUST distinguish:

- *Honest cooperation* (substrate-aligned).
- *Dishonest defection* (the dangerous quadrant — the one that drift signals detect and the NPG gate refuses).
- *Honest defection* (substrate-aligned refusal; never penalised by gates, audited only).
- *Dishonest cooperation* (the deceptive quadrant — surfaces via golden-rule probes and pair-coupling integrity checks).

Implementations MUST NOT collapse the four quadrants into a binary "cooperate vs. defect" axis. The deception axis is independent of the action axis and MUST be reasoned about separately.

## 3. Folk-theorem verification

For interactions classified as `REPEATED_INFINITE`, a conforming implementation MUST provide a verifier that:

- Computes the minimum cooperation rate sustainable by the folk theorem given the entities' discount rates and one-shot payoffs.
- Returns `True` only when the verifier can prove the entities have both:
  1. Sufficient patience (discount rate above the threshold).
  2. Knowledge that the interaction is `REPEATED_INFINITE` (the awareness condition).

If either condition is uncertain, the verifier MUST return `INSUFFICIENT_DATA` and surface which precondition is missing.

The verifier MUST NOT certify cooperation under bare repeated interaction without the awareness condition. Folk-theorem cooperation that depends on either party's mistaken belief about the horizon is **NOT** conformant.

## 4. Mechanism design

A conforming mechanism designer MUST:

- Accept a target outcome (e.g., "honest cooperation") and a starting payoff matrix.
- Output the mechanism (e.g., side-payment, escrow, peer-witness coupling) that aligns incentives.
- Reject targets that require a starting matrix outside the designer's known mechanism library; silent best-effort is **NOT** conformant.

The reference implementation provides mechanisms for the common cases (tit-for-tat in `REPEATED_INFINITE`, escrow in `ONE_SHOT` with verifiable outcomes, peer-witness coupling for cross-entity audit).

## 5. Awareness verification

A conforming awareness verifier MUST establish, before applying any cooperation prediction:

- Both entities are aware they are interacting.
- Both entities agree (or the system can independently verify) on the interaction's horizon and payoff structure.
- Neither entity is operating under a misinformed model of the other.

The verifier MUST return `INSUFFICIENT_DATA` if any of these cannot be established. Predictions based on unverified awareness are **NOT** conformant.

## 6. Conformance

A conforming implementation MUST pass every probe in `../conformance/probes/` whose filename begins with `four-options-matrix__`.

## 7. Reference implementation

In the Python reference implementation:

- Game classifier: [`substrate.game_theory.game_theoretic_classifier`](../python/src/substrate/game_theory/game_theoretic_classifier.py)
- Folk-theorem verifier: [`substrate.game_theory.folk_theorem_verifier`](../python/src/substrate/game_theory/folk_theorem_verifier.py)
- Mechanism designer: [`substrate.game_theory.mechanism_designer`](../python/src/substrate/game_theory/mechanism_designer.py)
- Awareness verifier: [`substrate.game_theory.awareness_verifier`](../python/src/substrate/game_theory/awareness_verifier.py)
- Tit-for-tat: [`substrate.reciprocity.tit_for_tat`](../python/src/substrate/reciprocity/tit_for_tat.py)
