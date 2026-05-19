# Conformance probes

Machine-checkable behavioral test probes for substrate-alignment. Vendors and implementers run these probes against their implementation to demonstrate it satisfies the [specifications](../spec/).

> **Status:** skeleton. The probe schema and initial probe set are added alongside each primitive specification during the spec/conformance phase of the project roadmap.

## What a probe is

Each probe is a portable, declarative description of a behavioral scenario:

- **Inputs** — the primitive's configuration plus the events / requests fed to it.
- **Expected outcomes** — the observable behavior a conforming implementation must produce (return values, state transitions, audit-chain entries, raised exceptions).
- **Metadata** — which specification it targets, the minimum spec version, whether it is `required` or advisory, the rationale (often a real-world incident or design constraint).

Probes are stored as data (JSON or YAML), not as language-specific tests. The Python reference implementation ships a probe runner under `../python/src/substrate/conformance/`; other language bindings will ship their own runners.

## Layout

```
conformance/
├── README.md              this file
└── probes/                one file per probe; named <spec>__<scenario>.{json,yaml}
```

Probe files use the naming convention `<spec-slug>__<scenario-slug>.<ext>`, for example:

```
npg-gate-protocol__rejects-negative-net-gain.yaml
drift-signals__pattern-match-on-aggregation-window.yaml
```

## Running probes

*The probe runner is added in the spec/conformance phase. The interface will be:*

```bash
substrate-conformance run probes/             # run every probe
substrate-conformance run probes/npg-gate-protocol__*.yaml   # run a subset
```

The runner reports per-probe pass/fail and exits non-zero on any required probe failure.

## Adding a probe

1. Identify the specification clause the probe will exercise.
2. Create `probes/<spec-slug>__<scenario-slug>.yaml`. Use the schema documented in the runner.
3. Link the probe from the corresponding `../spec/<spec-slug>.md` document under "Conformance".
4. Ensure the Python reference implementation passes the probe; if it does not, either the spec is wrong, the implementation is wrong, or the probe is wrong — fix the actual one.

## Vendor self-attestation

A vendor demonstrating conformance publishes:

- The set of specifications their implementation targets.
- The probe-runner output (pass/fail per probe).
- The version of the substrate-alignment specifications against which the run was performed.

The substrate-alignment maintainers do not certify implementations; the probes are the certification mechanism.
