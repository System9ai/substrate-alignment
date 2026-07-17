# FAQ

### What problem does this actually solve?

Multi-entity systems (humans, services, and AI agents cooperating and competing)
make consequential decisions constantly. Today, a vendor's claim that their
system is "aligned" or "safe" is unverifiable: you read a blog post and trust the
closed source. substrate-alignment turns that into a **checkable** claim by
publishing (a) a normative standard, (b) a reference implementation, and (c) a
machine-checkable conformance suite. You can *demonstrate* conformance, and a
third party can *re-run the probes* to confirm it.

### Is this an AI safety framework or an authorization system?

Neither, exactly. It is a **behavioural-layer standard** for systems where
multiple entities interact. It overlaps authorization (it gates actions) and AI
safety (it constrains agent behaviour), but its distinct question is the
*net-potential-gain test*: does an action increase net potential **across the
entities it affects**, not just for the actor? See the
[comparison](comparison.md) for how it relates to OPA, Cerbos, and LLM guardrails.

### What is "net potential gain" and why that specific test?

Value is defined as *net* potential gain: across the whole system an actor is
embedded in, not the actor's private gain. Optimising for private benefit
(revenue, engagement, agent reward) without the net test is how a system quietly
builds harmful incentives into its own infrastructure. The
[NPG gate](concepts/npg-gate.md) makes that test an explicit, auditable decision
point with four honest verdicts, including `INSUFFICIENT_DATA`, because a gate
that guesses is worse than one that admits it does not know.

### Do I have to adopt the whole thing?

No. Start with the [core surface](core-vs-extended.md): a handful of primitives
you import directly from `substrate`. The ~170-module tree is the *complete
witness* that the standard is implementable; you reach into the extended tier
only for the specific mechanism you are building.

### Does it call an LLM or need a model?

No. The package has **zero runtime dependencies** and never calls a model. The
[harness](core-vs-extended.md) intercepts model *outputs that propose actions* and
returns a verdict the caller acts on; it is provider-agnostic and works with any
model or none.

### What do I have to implement to use it?

One thing: the [`SubstrateMetadataStore` Protocol](../spec/operating-mode.md), which is
`get` and `upsert` against your own persistence (Postgres, Redis, DynamoDB, …).
Every primitive reads and writes through that single Protocol. A zero-dependency
`InMemorySubstrateMetadataStore` ships with the package so you can try everything
before wiring storage. See the
[SQLAlchemy recipe](adoption/sqlalchemy-metadata-store.md) for a real backend.

### Why does the gate return `INSUFFICIENT_DATA` in my first test?

Because you have not seeded substrate metadata for the affected entity. The gate
refuses to invent a verdict for an entity it knows nothing about. That honesty is
the point. `upsert` the entity first (see the
[30-second example](../README.md#see-it-work-in-30-seconds)), then the gate decides.

### The concept docs use golden-ratio numbers. Is that numerology?

The concern is fair, and the docs try to earn the numbers rather than assert them.
The [resistance band](concepts/resistance-band.md) derives its anchors (`1/3`,
`1/φ²`, the `2/3` debt line) from the calibration model and pins them with tests;
they are not tunable magic constants. If a derivation does not convince you, that
is a spec bug worth [reporting](../CONTRIBUTING.md); the standard should stand on
its reasoning, not on aesthetics.

### Why is the source code so plain, with no cosmology and no rationale comments?

Deliberate. The source passes a **federal-procurement test**: engineering
vocabulary only, so it survives review by auditors with no patience for
vendor-internal jargon. The reasoning that motivates each primitive lives in
[`docs/concepts/`](concepts/README.md) and [`spec/`](../spec/README.md), where
readers who want it can find it. A CI guard fails the build if internal references
reappear.

### Is it production-ready? What is the version story?

The primitives are extracted from a system where they run in production, and the
suite is green (2715 tests, 48/48 conformance probes, pyright-strict, pylint
10/10). It is **pre-release**: the first tagged release will be `v0.2.0`, and spec
wording may tighten before then. Breaking changes to **MUST** clauses are
major-version events under SemVer.

### What languages are supported?

The specification is language-neutral (RFC-2119). The reference implementation is
Python today; `rust/`, `go/`, and `ts/` bindings are planned as sibling
directories in this same repository. Any implementation demonstrates conformance
by passing the shared YAML probes.

### How do I verify an implementation actually conforms?

Run the [conformance suite](../conformance/README.md):
`python -m substrate.conformance --probes conformance/probes/`. It executes the
bundled behavioural probes against an implementation and reports required/advisory
pass-fail. That command *is* the verification. No trust required.

### How do I contribute or report a problem?

See [CONTRIBUTING.md](../CONTRIBUTING.md). The hard rule: source uses engineering
vocabulary only; substrate-mathematical reasoning goes in `docs/concepts/` and
`spec/`. Security-relevant issues go through [SECURITY.md](../SECURITY.md).
