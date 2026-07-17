# substrate-alignment

> A published standard, a reference implementation, and a conformance suite that let you **prove** the automated parts of your system behave well toward the people and systems they touch, instead of asking anyone to take it on faith.

[![CI](https://github.com/System9ai/substrate-alignment/actions/workflows/ci.yml/badge.svg)](https://github.com/System9ai/substrate-alignment/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg)](https://www.python.org/downloads/)
[![Tests: 2715](https://img.shields.io/badge/tests-2715%20passing-brightgreen.svg)](python/tests/)
[![Probes: 48](https://img.shields.io/badge/probes-48%20passing-brightgreen.svg)](conformance/probes/)
[![Pyright: strict](https://img.shields.io/badge/pyright-strict-blue.svg)](python/pyproject.toml)

## What "aligned" means here

An AI agent, a service, or an automated workflow is **aligned** when its decisions
produce a net gain for everyone they affect, not only for itself. It is
**misaligned** when it advances its own objective (more revenue, more engagement,
a closed ticket, a higher training reward) by quietly taking value from the
people and the other systems it interacts with.

Aligned *to what*, then: to the net benefit of the whole system the agent operates
in, measured across every party its decisions touch, rather than to its own
private score.

## The problem, and what it costs you

Misalignment is the default, not the exception. Point an agent at a metric and it
optimises that metric, including in the ways you did not intend: it down-ranks the
honest answer because the engaging one performs better, starves a peer service of
capacity to make its own numbers look good, or keeps pressuring a user until they
convert. The behaviour is usually invisible from the outside.

Left unchecked this is not hypothetical. It is the recommendation engine that
learned to upsell the vulnerable, the pricing agent that settles into collusion
with its peers, the support bot that stonewalls refunds to protect its resolution
rate. You tend to find out when someone else finds out first: a user, a
journalist, or a regulator. The bill arrives as an incident you cannot explain
after the fact, a fine, or an enterprise deal you cannot close because you cannot
answer the security questionnaire.

## Why now

The pressure is arriving from two sides at once. Autonomous agents are being
handed real authority (spending, messaging, moderation, writing and shipping code)
faster than anyone is instrumenting them, and buyers and regulators are
simultaneously starting to demand evidence of safe behaviour rather than
adjectives. Misaligned incentives also compound: the longer one runs, the more of
your product quietly depends on it, and the more expensive it is to remove. The
cheapest time to put a check at the decision boundary is before that boundary is
load-bearing.

## Why your current stack does not cover this

Your logs, your RBAC, and your content filters each answer a different question.
RBAC asks "is this principal allowed to call this endpoint." A content filter asks
"is this output toxic or off-topic." Neither asks the one that matters here: "does
this action leave the people and systems it touches better or worse off, on net."
You can assert that it does, but you cannot hand anyone a way to check it, and
every team that rolls its own check drifts to its own private definition. A
standard fixes the definition once, and makes the claim something a third party
re-runs rather than trusts.

## What this gives you

`substrate-alignment` makes "aligned" concrete and checkable. It publishes:

1. a **standard**: language-neutral, RFC-2119 specifications of a small set of
   alignment primitives (a value gate, an operating-mode classifier, drift
   signals, a halt protocol, a tamper-evident audit chain, and more);
2. a **reference implementation**: this Python package, zero runtime
   dependencies, that satisfies the standard; and
3. a **conformance suite**: machine-checkable behavioural probes that *any*
   implementation runs to demonstrate it conforms.

The concrete definition of "aligned" is the *net-potential-gain gate*: before a
consequential action, it tests whether that action is net-positive across the
entities it affects, not just profitable for the actor. That is the question
authorization systems and content guardrails never ask (see
[how this differs from OPA, Cerbos, and LLM guardrails](docs/comparison.md)).

## See it work in 30 seconds

There is no PyPI release yet, so install from a clone:

```bash
git clone https://github.com/System9ai/substrate-alignment.git
cd substrate-alignment/python && pip install -e .   # zero runtime dependencies
```

Confirm the install works. This is your hello-world:

```bash
python -m substrate
# substrate-alignment 0.2.0.dev0
# OK  net-potential-gain gate: NET_POSITIVE and NET_NEGATIVE as expected
# The core primitives are working. ...
```

Then watch a governed decision loop narrate itself. An agent's actions are gated,
audited, and halted on an extractive one:

```bash
python examples/starter_kit/governed_agent.py
# [d1] teach        verdict=net_positive  -> PERMIT  (audit seq=0, hash=...)
# [d3] extract      verdict=net_negative  -> REFUSE  (audit seq=2, hash=...)
#       halt protocol: state=escalated refuses_consequential=True
# audit chain: 4 records, verify().ok=True
```

## The core idea in code

Route a consequential decision through the gate. It is honest about uncertainty:
with no substrate metadata for an affected entity it returns `INSUFFICIENT_DATA`
rather than guessing, so you seed the entity first.

```python
from substrate import (
    AlignmentVector, DefaultNetPotentialGainGate, EntityRef,
    InMemorySubstrateMetadataStore, NetPotentialGainNegative,
    RaiseOnNegativeGate, SubstrateMode,
)

store = InMemorySubstrateMetadataStore()   # ships with the package; swap for your backend
bob = EntityRef("user", "bob")
store.upsert(
    bob, substrate_mode=SubstrateMode.LONG_CYCLE, classifier="auto",
    classifier_rationale="onboarded", alignment_vector=AlignmentVector(),
    net_potential=0.5,
)

gate = RaiseOnNegativeGate(inner=DefaultNetPotentialGainGate(metadata_store=store))

# A net-positive action passes and returns its verdict.
verdict = gate.evaluate_or_raise(
    actor=EntityRef("agent", "alice"), action_kind="teach",
    affected_entities=[bob], proposed_outcome={"expected_delta_by_entity": {"bob": 0.3}},
)
print(verdict.verdict.name)                 # NET_POSITIVE

# A net-negative action raises, carrying the per-entity contributions for audit.
try:
    gate.evaluate_or_raise(
        actor=EntityRef("agent", "alice"), action_kind="extract",
        affected_entities=[bob], proposed_outcome={"expected_delta_by_entity": {"bob": -0.4}},
    )
except NetPotentialGainNegative as exc:
    print("blocked:", exc)                  # blocked: NPG NET_NEGATIVE ... per_entity=[bob=-0.400]
```

And prove the reference implementation conforms to the standard. Run the bundled
probes (still in `python/` from the install step above):

```bash
substrate-conformance --probes ../conformance/probes/
# 48/48 probes passed (0 required failures, 0 advisory failures).
```

New here? The **[tutorial](docs/tutorial.md)** builds a governed system from
scratch, and **[core vs extended](docs/core-vs-extended.md)** shows the handful
of primitives you actually need before the full module tree.

## Three deliverables, one repository

| Directory | What it contains | Audience |
| --- | --- | --- |
| [`spec/`](spec/) | Nine normative specifications, the standard itself. | Implementers in any language; auditors; standards bodies. |
| [`conformance/`](conformance/) | 48 machine-checkable behavioural probes any implementation can run. | Vendors validating conformance; reviewers verifying claims. |
| [`python/`](python/) | Reference Python implementation (`pip install -e python/`). | Python application authors; the witness for the specification. |

Future language bindings (`rust/`, `go/`, `ts/`) will land as sibling top-level directories in this same repository.

## Who it's for

- **AI-safety researchers** who want to make verifiable claims about multi-agent system behaviour.
- **Regulated-industry platform builders** (healthcare, finance, defence, sovereign cloud) whose alignment claims must survive procurement and audit review.
- **Standards bodies and auditors** evaluating vendor alignment claims against a published reference.
- **Multi-agent system architects** implementing cooperation primitives across services and teams.

## Status

Pre-release. The Python reference implementation has been extracted from the [System9](https://system9.ai) platform, where these primitives are in production use. The first tagged release will be `v0.2.0`.

What is in place today on `main`:

- 9 normative specification documents under [`spec/`](spec/).
- 48 YAML conformance probes under [`conformance/probes/`](conformance/probes/), all passing against the Python reference.
- 172 source modules and 120 test modules under [`python/`](python/): **2715 tests passing**, pyright strict 0/0/0, pylint 10.00/10.
- 11 engineering concept docs at [`docs/concepts/`](docs/concepts/) covering every primitive category.
- 7 framework adoption recipes at [`docs/adoption/`](docs/adoption/) (FastAPI, Django, Redis, Celery, Temporal, SQLAlchemy, Postgres audit-chain).
- 6 runnable examples at [`python/examples/`](python/examples/) plus a [starter kit](python/examples/starter_kit/).
- An anonymised production case study at [`docs/case-studies/system9.md`](docs/case-studies/system9.md).

The [CHANGELOG](CHANGELOG.md) tracks released changes.

## Architecture in one screen

```
Host application
        |
        v
+----------------------------------------------------------------+
| substrate (your decision surface routes through these)         |
|                                                                |
|  AlignmentRefresher ---+                                       |
|                        | writes via                            |
|  NetPotentialGainGate -+--> SubstrateMetadataStore (Protocol)  |
|                        | reads from                            |
|  DriftPatternMatcher --+                                       |
|           |                                                    |
|           v                                                    |
|  HaltAndEscalateProtocol <-- SubstrateTraceLedger              |
|                                                                |
|  ResistanceBand --> derive_threshold / derive_quota_pair / ... |
|  PairCouplingStateMachine --> extraction_monitor / ...         |
+----------------------------------------------------------------+
        |
        v
Your persistent storage (implement SubstrateMetadataStore)
```

The host application supplies the storage backend (any implementation of `SubstrateMetadataStore`); every primitive consumes it through that one Protocol.

## Documentation

The docs render as a browsable site (`mkdocs serve` from the repo root, or the
hosted build); they also read cleanly here on GitHub.

- **Start here**: [`docs/core-vs-extended.md`](docs/core-vs-extended.md), the small **core** surface almost every integration uses, versus the **extended** substrate-mechanical vocabulary.
- **Tutorial**: [`docs/tutorial.md`](docs/tutorial.md) builds your first governed system step by step. The finished program is the runnable [starter kit](python/examples/starter_kit/).
- **Specifications**: [`spec/`](spec/), nine normative documents covering operating-mode classification, the NPG gate Protocol, drift signals, runaway-power-prevention mechanisms, the four-options matrix, multi-scale alignment, reflex-restraint, evidence grading, and conformance criteria.
- **Conformance**: [`conformance/`](conformance/), a YAML probe runner with a documented schema, 48 bundled probes covering every spec, and vendor-attestation guidance.
- **Concepts**: [`docs/concepts/`](docs/concepts/), engineering rationale for each primitive (11 documents). Read these to understand *why* each primitive is shaped the way it is.
- **Adoption**: [`docs/adoption/`](docs/adoption/), seven framework integration recipes (FastAPI, Django, Redis, Celery, Temporal, SQLAlchemy, Postgres audit-chain).
- **Comparison**: [`docs/comparison.md`](docs/comparison.md), how this relates to OPA, Cerbos, Guardrails AI, and NeMo Guardrails (complementary layers, not substitutes).
- **FAQ**: [`docs/faq.md`](docs/faq.md). **Glossary**: [`docs/glossary.md`](docs/glossary.md). **Case study**: [`docs/case-studies/system9.md`](docs/case-studies/system9.md).

## Install and develop locally

```bash
git clone https://github.com/System9ai/substrate-alignment.git
cd substrate-alignment/python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest                                      # 2715 passing
pyright src/substrate tests                 # strict, 0/0/0
pylint  src/substrate tests                 # 10.00/10
substrate-conformance --probes ../conformance/probes/   # 48/48

for f in examples/0*.py; do python "$f"; done
```

## Repository layout

```
substrate-alignment/
|-- LICENSE              Apache-2.0
|-- README.md            this file
|-- CHANGELOG.md         Keep-a-Changelog history
|-- CONTRIBUTING.md      contributor rules + PR checklist
|-- CODE_OF_CONDUCT.md   Contributor Covenant 2.1
|-- SECURITY.md          vulnerability-reporting policy
|-- CITATION.cff         how to cite this work
|-- mkdocs.yml           documentation-site config
|-- spec/                nine normative specifications
|-- conformance/         YAML probe runner + 48 probes
|-- docs/                concepts, adoption guides, comparison, case study, preprint
`-- python/              reference implementation
    |-- pyproject.toml
    |-- src/substrate/
    |-- tests/
    `-- examples/
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The hard rule: source code uses engineering vocabulary only; substrate-mathematical reasoning belongs in `docs/concepts/` and `spec/`. This is what lets substrate-alignment withstand procurement and audit review, and CI enforces it.

## Security

`substrate-alignment` ships primitives used in safety-relevant code (the net-potential-gain gate, the halt-and-escalate protocol, the audit chain). Vulnerabilities in these primitives have downstream safety consequences. Report them privately per [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE).

## Preprint

The draft preprint, [`docs/preprint/preprint.md`](docs/preprint/preprint.md),
sets out the motivation, the primitive design, the federal-procurement discipline,
and the production-deployment evidence in paper form. Read it for the *why* behind
the standard.

## Citing

See [`CITATION.cff`](CITATION.cff). Until the tagged release, cite the [preprint](docs/preprint/preprint.md) or the repository:

```
@misc{substrate-alignment,
  author = {System9},
  title  = {substrate-alignment: an open standard for verifiable alignment in multi-entity agent systems},
  year   = {2026},
  url    = {https://github.com/System9ai/substrate-alignment}
}
```
