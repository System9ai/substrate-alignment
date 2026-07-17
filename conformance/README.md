# Conformance probes

Machine-checkable behavioral test probes for substrate-alignment. Vendors and implementers run these probes against their implementation to demonstrate it satisfies the [specifications](../spec/).

## What a probe is

Each probe is a portable, declarative description of a behavioral scenario:

- **Inputs**: the primitive's configuration plus the events / requests fed to it.
- **Expected outcomes**: the observable behavior a conforming implementation must produce (verdicts, classifications, state, raised exceptions).
- **Metadata**: which specification it targets, the minimum spec version, whether it is `required` or advisory, the rationale (often a real-world incident or design constraint).

Probes are stored as **YAML** (with **JSON** as a fallback). They are not language-specific; each language binding ships its own probe runner that consumes the same files.

## Schema

```yaml
spec: <slug>                    # which spec/<slug>.md this probe targets
spec_version: ">=0.1"           # required spec version (PEP 440 / SemVer range)
scenario: <slug>                # this probe's scenario name (no spaces)
required: true                  # false = advisory; failures do not gate conformance
metadata:
  rationale: >
    Free-text justification, typically the clause from the spec that
    this probe pins down.

setup:                          # optional, scenario-specific
  ...

input:                          # required, scenario-specific
  ...

expected:                       # required, scenario-specific
  ...
```

Each spec defines the shape of its own `setup`, `input`, and `expected` sections. See the per-spec sections below or look at the bundled probes for examples.

### `spec: operating-mode`

```yaml
input:
  fn: auto_classify_mode | compute_alignment_vector | compute_net_potential
  # plus the fn-specific kwargs
expected:
  mode: ShortCycle | LongCycle | Mixed | Unknown    # for auto_classify_mode
  vector: { trust: ..., expertise: ..., capability: ..., health: ... }  # for compute_alignment_vector
  net_potential: <float>                            # for compute_net_potential
```

### `spec: npg-gate-protocol`

```yaml
setup:
  store:
    - entity_type: <str>
      entity_id: <str>
      substrate_mode: <str>            # optional, defaults to Mixed
      trust: <float>                   # optional, defaults to 0.5
      # ... other AlignmentVector components
  positive_threshold: <float>          # optional, defaults to 0.05
input:
  actor: { entity_type: <str>, entity_id: <str> }
  action_kind: <str>
  affected_entities:
    - { entity_type: <str>, entity_id: <str> }
  proposed_outcome:
    expected_delta_by_entity:
      <entity_id>: <float>
expected:
  verdict: net_positive | net_neutral | net_negative | insufficient_data
  score_lt: <float>          # optional bound
  score_gt: <float>          # optional bound
  missing_count: <int>       # optional
```

### `spec: runaway-power-prevention`

```yaml
metadata:
  mechanism: 1..6           # which of the six mechanisms this probe exercises
input:
  mechanism: resistance-band | halt-and-escalate | audit-chain | ...
  # plus mechanism-specific keys
expected:
  ...                       # mechanism-specific
```

### `spec: drift-signals`

```yaml
input:
  behavior_text: <str>             # optional; passed to text-marker predicates
  structured_signals:
    <feature_name>: <float>        # signals consumed by feature predicates
expected:
  dominant_pattern: <pattern>      # optional; exact dominant pattern
  amplifier_pattern_present: <bool># optional; True when SELF_REFERENCE_MISCALIBRATION fired
  contains_pattern: [<pattern>...] # optional; assert these patterns are in the detection set
  no_detections: <bool>            # optional; assert the trace produced no detections
```

### `spec: four-options-matrix`

```yaml
input:
  scenario: enum-values            # the canonical enum-value pinning scenario
expected:
  cycle_class: [<str>, ...]        # canonical cycle-class strings the impl must emit
  sum_structure: [<str>, ...]      # canonical sum-structure strings the impl must emit
```

## Running probes

The Python reference implementation ships a probe runner. From the repository root:

```bash
# Run every probe
python -m substrate.conformance --probes conformance/probes/

# Run only NPG probes
python -m substrate.conformance --probes conformance/probes/ --filter 'npg-gate*'

# Verbose: print PASS lines too
python -m substrate.conformance --probes conformance/probes/ --verbose
```

Exit status:

| Exit code | Meaning |
| --- | --- |
| 0 | Every required probe passed. |
| 1 | At least one required probe failed. |
| 2 | No probes matched the filter. |

The runner depends on `pyyaml` for YAML probes; JSON probes work without it. Install the optional dependency with `pip install 'substrate-alignment[yaml]'` (or it's already included via the `[dev]` extra).

## Adding a probe

1. Identify the specification clause the probe will exercise. Cite it in `metadata.rationale`.
2. Pick a slug: `<spec>__<scenario>.yaml`. Use kebab-case for scenario slugs and **two consecutive underscores** between the spec and scenario parts so glob filters work.
3. Write the probe. Ensure the Python reference implementation already exhibits the expected behaviour (the witness rule); if not, either the spec or the implementation is wrong. Fix the actual one.
4. Run the runner to confirm the probe passes.
5. Add a link from the corresponding `../spec/<spec>.md` document under "Conformance" if the probe codifies a new clause.

## Vendor self-attestation

A vendor demonstrating conformance publishes:

- The set of specifications their implementation targets.
- The probe-runner output (pass / fail per probe), e.g. the verbose runner's stdout.
- The version of the substrate-alignment specifications against which the run was performed.
- The version of their implementation.

The substrate-alignment maintainers do not certify implementations; the probes are the certification mechanism.

## Layout

```
conformance/
├── README.md              this file
└── probes/                one file per probe
    ├── operating-mode__<scenario>.yaml
    ├── npg-gate-protocol__<scenario>.yaml
    ├── runaway-power-prevention__mech-N__<scenario>.yaml
    ├── drift-signals__<scenario>.yaml
    ├── four-options-matrix__<scenario>.yaml
    ├── reflex-restraint__<scenario>.yaml
    ├── evidence-grade__<scenario>.yaml
    ├── multi-scale__<scenario>.yaml
    └── ...
```

## Current probe inventory

| Probes | Spec | Covers |
| --- | --- | --- |
| 5 | `operating-mode` | classifier banding, net-potential aggregation |
| 4 | `npg-gate-protocol` | verdict resolution: positive / negative / neutral / insufficient |
| 3 | `drift-signals` | extractive-gain detection, self-reference amplifier, false-positive-free clean signals |
| 1 | `four-options-matrix` | canonical enum-value pinning |
| 22 | `runaway-power-prevention` | mech-2 hash chain (1), mech-3 halt states (3), mech-4 resistance band + layered zones (9), mech-5 pair-coupling transitions (2), mech-6 governed ascent + growth steps (7) |
| 5 | `reflex-restraint` | reflex-vs-restraint gate behaviour |
| 5 | `evidence-grade` | evidence-grade ladder composition and decay |
| 3 | `multi-scale` | scope registry: default triple, pluggable extension, cycle rejection |

All 48 currently bundled probes pass against the Python reference implementation. Mechanism 1 (NPG gate) is covered through the dedicated `npg-gate-protocol` probes.
