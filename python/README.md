# substrate-alignment (Python reference implementation)

Reference Python implementation of [substrate-alignment](https://github.com/System9ai/substrate-alignment), an open standard, with a conformance suite, for making **verifiable** alignment claims in multi-entity agent systems (rather than asking people to trust closed-source assertions). Zero runtime dependencies.

## Install

Pre-release: install from a clone until the first tagged release publishes to PyPI.

```bash
git clone https://github.com/System9ai/substrate-alignment.git
cd substrate-alignment/python && pip install -e .
```

The installed top-level module is `substrate`; confirm it works:

```bash
python -m substrate
# substrate-alignment 0.2.0.dev0
# OK  net-potential-gain gate: NET_POSITIVE and NET_NEGATIVE as expected
```

## Status

Pre-release (`0.2.0.dev0`). The primitive surface (net-potential-gain gate, resistance band, drift signals, halt-and-escalate protocol, audit-chain types, classifiers, and more) has been extracted from the System9 production implementation, where these primitives are in production use. The suite is green: 2715 tests, 48/48 conformance probes, pyright-strict, pylint 10/10. The first tagged release will be `v0.2.0`.

Track changes in the repository's [CHANGELOG](https://github.com/System9ai/substrate-alignment/blob/main/CHANGELOG.md).

## What's in this package

- `substrate`: pure-logic primitives. No database, network, or LLM calls; callers pass effects in.
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
