# Examples

Runnable end-to-end snippets demonstrating substrate-alignment primitives. Each example is self-contained — depends only on `substrate` plus the Python standard library — and runnable as `python NN_<name>.py`.

| Script | Primitive | What it shows |
| --- | --- | --- |
| [`01_npg_gate.py`](01_npg_gate.py) | `NetPotentialGainGate` | Positive / negative / insufficient verdicts; `RaiseOnNegativeGate` adapter |
| [`02_resistance_band.py`](02_resistance_band.py) | `ResistanceBand` + threshold helpers | Classification, derived limits, tighter-band overrides |
| [`03_alignment_refresher.py`](03_alignment_refresher.py) | `AlignmentRefresher` | Folding signal-source updates into stored alignment |
| [`04_metadata_store.py`](04_metadata_store.py) | `SubstrateMetadataStore` Protocol | In-memory default + Protocol implementation pattern |

Future examples (tracked separately):

- `05_halt_and_escalate.py` — full halt-and-escalate flow with the audit ledger
- `06_full_governor_loop.py` — end-to-end `SubstrateGovernor` composing every gate
- Adoption recipes (FastAPI, Celery, Temporal, Redis-backed limiter) live in [`../../docs/adoption/`](../../docs/adoption/) rather than under `examples/`.

## Running

From a checkout with the package installed (`pip install -e python/`):

```bash
cd python/examples
python 01_npg_gate.py
python 02_resistance_band.py
python 03_alignment_refresher.py
python 04_metadata_store.py
```

Each script prints its own narration; no flags required.
