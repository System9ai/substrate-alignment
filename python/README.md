# substrate-alignment (Python reference implementation)

Reference Python implementation of [substrate-alignment](https://github.com/System9ai/substrate-alignment) — the open standard for substrate-alignment primitives in multi-entity agent systems.

## Install

```bash
pip install substrate-alignment
```

The PyPI distribution is `substrate-alignment`; the installed top-level module is `substrate`.

```python
import substrate

print(substrate.__version__)
```

## Status

Pre-release (`0.1.0.dev0`). The full primitive surface — net-potential-gain gate, ResistanceBand, drift signals, halt-and-escalate protocol, audit-chain types, classifiers — is being ported from the System9 production implementation.

Track progress in the repository's [CHANGELOG](https://github.com/System9ai/substrate-alignment/blob/main/CHANGELOG.md).

## What's in this package

- `substrate` — pure-logic primitives. No database, network, or LLM calls; callers pass effects in.
- Test suite under `tests/` mirroring the source tree.
- Runnable examples under `examples/`.

## Where the standard lives

This package is **one conforming implementation**. The language-neutral specifications and conformance probes live alongside it, in the same repository:

- Specifications: <https://github.com/System9ai/substrate-alignment/tree/main/spec>
- Conformance probes: <https://github.com/System9ai/substrate-alignment/tree/main/conformance>
- Concepts and adoption guides: <https://github.com/System9ai/substrate-alignment/tree/main/docs>

## Development

From a checkout of the repository:

```bash
cd python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pylint src/substrate tests
pyright src/substrate tests
pytest
```

## License

[Apache-2.0](https://github.com/System9ai/substrate-alignment/blob/main/LICENSE).
