# How substrate-alignment relates to policy engines and LLM guardrails

A reasonable first question is *"don't we already have this?"* OPA, Cerbos,
Guardrails AI, NeMo Guardrails all sit near decision points and say yes or no.
substrate-alignment overlaps with them at the surface (something evaluates an
action before it commits) but answers a different question. This page is honest
about where it does **not** compete and where it adds something those tools do
not.

## The one-line distinction

- **Policy engines** (OPA, Cerbos) enforce *rules an author wrote*: "role X may
  do Y on Z." The policy is the source of truth; the engine is a fast, auditable
  evaluator of it.
- **LLM guardrails** (Guardrails AI, NeMo Guardrails) constrain *a model's
  output*: schema validity, toxicity, topic, jailbreak resistance, conversational
  flow.
- **substrate-alignment** tests *the effect of an action on the other entities in
  the system* (the net-potential-gain test) and does it against a **published,
  machine-checkable standard** so the claim is verifiable by a third party rather
  than trusted.

They are complementary layers, not substitutes. A production system can run OPA
for RBAC, Guardrails for output schemas, **and** the NPG gate for the "is this
net-positive across the affected entities?" question none of the others ask.

## Side by side

| | OPA / Rego | Cerbos | Guardrails AI | NeMo Guardrails | **substrate-alignment** |
| --- | --- | --- | --- | --- | --- |
| Primary question | Does this request satisfy the written policy? | Is this principal permitted this action on this resource? | Is this model output valid/safe? | Does this conversation stay on the rails? | Is this action net-positive across the affected entities? |
| Unit of evaluation | Arbitrary JSON input vs Rego | Principal × resource × action | A single model output | A dialogue turn | An action + its per-entity effect |
| Source of truth | Author-written Rego | Author-written policy | Author-written validators | Author-written rails (Colang) | A **published normative spec** + the entity's substrate metadata |
| Multi-entity reasoning | No (one request at a time) | No (one principal at a time) | No | No | **Yes** (aggregates effect across all affected entities) |
| Cryptographic identity & audit | External | External | No | No | **First-class** (hash-chained audit, peer-witness signing) |
| Third-party verifiable? | Policy is readable, behaviour is not standardised | Same | No | No | **Yes** (a conformance suite any implementation runs) |
| Drift / self-awareness | No | No | No | Partial (rails only) | **Yes** (drift signals, self-awareness metrics) |
| Language-neutral standard | Rego is the standard | Proprietary schema | Library | Library | **RFC-2119 spec, any language** |

## When to reach for which

- **Use a policy engine** when the rule is known and author-written: RBAC/ABAC,
  data-residency, tenancy isolation. Do not rebuild that in this library; wire the
  [FastAPI](adoption/fastapi-permission-gate.md) or
  [Django](adoption/django-permission-gate.md) recipe *alongside* your policy
  engine.
- **Use an LLM guardrail** when you need output-schema validity, toxicity
  filtering, or jailbreak resistance on a single model response. substrate-alignment's
  [harness](core-vs-extended.md) intercepts model *outputs that propose actions*,
  which is a different cut. Run both.
- **Use substrate-alignment** when the question is about *effect on others over
  time*: should this agent take an action that benefits it but harms a peer?
  Is this entity drifting from long-cycle to short-cycle behaviour? Can you
  **prove** to an auditor that your alignment claims hold, rather than asking them
  to trust your code?

## What it deliberately is not

- It is **not** a policy language. There is no rule DSL; the gate consumes a
  caller-supplied or heuristic per-entity delta and the entity's substrate
  metadata.
- It is **not** a model-serving guardrail. It never calls a model; it evaluates
  proposed actions and outputs.
- It is **not** a finished product you deploy. It is a **standard plus a reference
  implementation**: the value is that conformance is *checkable*, so alignment
  claims survive procurement and audit review.

## The load-bearing difference: verifiability

Every tool above asks you to trust that its rules/validators are correct and
correctly wired. substrate-alignment ships a [conformance suite](../conformance/README.md)
of machine-checkable behavioural probes: an implementation *demonstrates* it
satisfies the standard, and a reviewer *re-runs the probes* rather than reading
the code and hoping. That shift (from "trust our closed-source alignment" to
"here is a verifiable claim against a published standard") is the reason the
project exists.
