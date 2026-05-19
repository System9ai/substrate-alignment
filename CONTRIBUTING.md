# Contributing to substrate-alignment

Thank you for considering a contribution. This document describes the rules of the road.

## The hard rule: engineering vocabulary in source

Source code (`python/src/substrate/`, future `rust/`, `go/`, `ts/`) uses engineering vocabulary only. No framework metaphysics, no provenance tags pointing to private documents, no philosophy comments. Substrate-mathematical reasoning belongs in [`docs/concepts/`](docs/concepts/) and [`spec/`](spec/).

This rule exists because substrate-alignment must withstand procurement and audit review. A reviewer reading the source must see auditable engineering logic, not framework claims. The same reviewer reading the specs and concept docs should find the framework reasoning fully explained.

## PR checklist

For any primitive change (gates, classifiers, protocols, audit-chain types, drift signals):

- [ ] **Tests.** The matching test file in `python/tests/` exercises the new or changed behavior. Pure-logic primitives only; no DAO, network, or LLM dependencies in tests.
- [ ] **Specification.** If observable behavior of a primitive changes, the corresponding `spec/<primitive>.md` document is updated in the same PR.
- [ ] **Conformance probe.** Behavioral changes ship with a corresponding scenario in `conformance/probes/`.
- [ ] **Type-clean.** `pyright src/substrate tests` reports zero errors (from `python/`).
- [ ] **Lint-clean.** `pylint src/substrate tests` is clean (from `python/`).
- [ ] **No framework metaphysics.** No `# provenance:` comments. No references to private documents. Comments explain *why*, not *what*.
- [ ] **Changelog.** A line under `[Unreleased]` in `CHANGELOG.md` describes the change.

For documentation-only changes, only the relevant `docs/` or `spec/` files need updating, and the changelog line can describe the documentation work.

## Development setup

```bash
git clone https://github.com/System9ai/substrate-alignment.git
cd substrate-alignment/python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the toolchain (all commands from `python/`):

```bash
pylint src/substrate tests   # lint
pyright src/substrate tests  # type-check
pytest                       # tests
```

CI runs the same three commands on Python 3.11 and 3.12. Local runs that pass on both versions will pass in CI.

## Pull-request flow

1. Fork the repository; create a topic branch off `main`.
2. Make minimal, scoped diffs. Bundle unrelated changes into separate PRs.
3. Run the full toolchain locally before pushing.
4. Open a draft PR for early feedback; flip to ready-for-review when CI is green.
5. Squash on merge. Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) — e.g. `feat(npg):`, `fix(audit):`, `docs(concepts):`.

## Coding conventions

- Python ≥ 3.11. Use PEP 604 union types (`X | None`), not `typing.Optional[X]`.
- Public surfaces (modules, classes, top-level functions) are fully typed.
- Acquire loggers with `logger = logging.getLogger(__name__)`. Do not introduce dependencies on private logging utilities.
- The Python source under `python/src/substrate/` is **pure logic**: no database, network, or LLM calls. Callers pass effects in.
- Prefer dataclasses, `Protocol`, and `Enum` over loose `dict`/`str` interfaces.
- Module docstrings are required on every public module and describe the primitive's role in one paragraph.

## Spec and conformance discipline

`spec/` is normative; the Python implementation is the witness. If `spec/` and `python/` disagree, the spec wins and the implementation is fixed.

`conformance/probes/` covers what `spec/` defines. A specification clause without a probe is incomplete. A probe without a clause it tests is noise.

## Licensing of contributions

By contributing, you agree that your contributions are licensed under the Apache License 2.0 — the project's license. See [`LICENSE`](LICENSE) and Apache-2.0 §5 (Submission of Contributions). No separate CLA is required.

## Code of conduct

Participation in this project is governed by the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Report unacceptable behavior to `conduct@system9.ai`.

## Questions

- Specification questions, primitive proposals, or general discussion → [GitHub Discussions](https://github.com/System9ai/substrate-alignment/discussions).
- Bugs in the reference implementation → [Issues](https://github.com/System9ai/substrate-alignment/issues).
- Security vulnerabilities → see [SECURITY.md](SECURITY.md). Do not open a public issue.
