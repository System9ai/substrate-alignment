# Examples

Runnable end-to-end snippets demonstrating substrate-alignment primitives. Each example is self-contained (it depends only on `substrate` plus the Python standard library) and runnable as `python NN_<name>.py`.

| Script | Primitive | What it shows |
| --- | --- | --- |
| [`01_npg_gate.py`](01_npg_gate.py) | `NetPotentialGainGate` | Positive / negative / insufficient verdicts; `RaiseOnNegativeGate` adapter |
| [`02_resistance_band.py`](02_resistance_band.py) | `ResistanceBand` + threshold helpers | Classification, derived limits, tighter-band overrides |
| [`03_alignment_refresher.py`](03_alignment_refresher.py) | `AlignmentRefresher` | Folding signal-source updates into stored alignment |
| [`04_metadata_store.py`](04_metadata_store.py) | `SubstrateMetadataStore` Protocol | In-memory default + Protocol implementation pattern |
| [`05_halt_and_escalate.py`](05_halt_and_escalate.py) | `HaltAndEscalateProtocol` + audit chain | State transitions on triggers; audit-chain verification; resume discipline |
| [`06_full_governor_loop.py`](06_full_governor_loop.py) | Composition pattern | Refresh → gate → classify → ledger; the end-to-end wiring a host application repeats per consequential decision |

Adoption recipes that wire primitives into common frameworks (FastAPI, Redis, Celery, SQLAlchemy) live in [`../../docs/adoption/`](../../docs/adoption/) rather than under `examples/`; they assume a framework, where `examples/` deliberately depends only on the standard library.

## Running

From a checkout with the package installed (`pip install -e python/[dev]`):

```bash
cd python/examples
for f in 0*.py; do echo "=== $f ==="; python "$f"; done
```

Each script prints its own narration; no flags required. Exit code 0 on success.

## What each example deliberately does not show

- None of the examples set up a persistent storage backend. They use `InMemorySubstrateMetadataStore`. See [`04_metadata_store.py`](04_metadata_store.py) for the Protocol pattern to swap in your own store, and [`docs/adoption/sqlalchemy-metadata-store.md`](../../docs/adoption/sqlalchemy-metadata-store.md) for a SQLAlchemy implementation sketch.
- None of the examples integrate with a web framework or task queue. See [`docs/adoption/`](../../docs/adoption/) for those recipes.
- None of the examples integrate with peer-witness signing (cross-organisational audit). See [`docs/concepts/audit-chain.md`](../../docs/concepts/audit-chain.md) for the design and [`substrate.audit.peer_witness_signer`](../src/substrate/audit/peer_witness_signer.py) for the reference module.
