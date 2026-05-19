# Examples

Runnable end-to-end snippets demonstrating substrate-alignment primitives.

The examples land alongside the primitives they exercise. Planned for `v0.1.0`:

| Script                              | Primitive                                      |
| ----------------------------------- | ---------------------------------------------- |
| `01_npg_gate.py`                    | `NetPotentialGainGate` — net-potential-gain test |
| `02_resistance_band.py`             | `ResistanceBand` — calibrated-resistance band  |
| `03_cancer_pattern_detector.py`     | Cancer-pattern / drift detection               |
| `04_halt_and_escalate.py`           | `HaltAndEscalateProtocol`                      |
| `05_progression_tier_engine.py`     | Tiered progression model                       |
| `06_full_governor_loop.py`          | End-to-end `SubstrateGovernor` loop            |

Each example is self-contained, runnable as `python NN_<name>.py`, and depends only on `substrate` plus the Python standard library.
