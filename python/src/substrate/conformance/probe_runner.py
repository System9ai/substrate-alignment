"""Conformance probe runner.

Consumes the YAML probe files under ``conformance/probes/`` (at the
repository root) and validates the substrate-alignment primitives in
this package against them.

A probe file is a portable, declarative scenario:

- ``spec`` — the slug of the spec the probe targets
  (e.g. ``npg-gate-protocol``, ``operating-mode``, ``runaway-power-prevention``).
- ``spec_version`` — required spec version, e.g. ``">=0.1"``.
- ``scenario`` — slug naming this specific scenario.
- ``required`` — boolean; ``true`` gates conformance, ``false`` is advisory.
- ``setup``, ``input``, ``expected`` — scenario-specific keys; the runner
  dispatches on ``spec`` to a handler that knows the shape.

Other language bindings ship their own runners that consume the same
probe files and produce the same pass/fail outputs, so a vendor can run
probes against any implementation and compare.

CLI entry point::

    python -m substrate.conformance --probes conformance/probes/
    python -m substrate.conformance --probes conformance/probes/ --filter 'npg-gate*'
"""
from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

# Probes are stored as YAML; we accept JSON as a fallback so the runner
# works in environments that lack PyYAML (CI minimal images, etc.).
try:
    import yaml
except ImportError:  # pragma: no cover - environment-dependent
    yaml = None

_has_yaml: bool = yaml is not None


__all__ = [
    "ProbeFailure",
    "ProbeResult",
    "ProbeRunner",
    "run_probes",
]


class ProbeFailure(AssertionError):
    """Raised by a probe handler when the implementation did not match expected."""


@dataclasses.dataclass(frozen=True, slots=True)
class ProbeResult:
    """Outcome of one probe execution."""

    probe_path: Path
    spec: str
    scenario: str
    required: bool
    passed: bool
    message: str = ""

    @property
    def status(self) -> str:
        if self.passed:
            return "PASS"
        if self.required:
            return "FAIL"
        return "ADVISORY-FAIL"


_Handler = Callable[[Mapping[str, Any]], None]


class ProbeRunner:
    """Driver for the ``conformance/probes/`` suite.

    Construct with a registry mapping ``spec`` slugs to handlers, or use
    :func:`default_handlers` to wire the in-package primitives.
    """

    def __init__(self, handlers: Mapping[str, _Handler]) -> None:
        self._handlers: Mapping[str, _Handler] = dict(handlers)

    def run_one(self, probe_path: Path) -> ProbeResult:
        """Execute the single probe at ``probe_path`` and return its result."""
        data = _load_probe(probe_path)
        spec = str(data.get("spec", ""))
        scenario = str(data.get("scenario", probe_path.stem))
        required = bool(data.get("required", True))
        handler = self._handlers.get(spec)
        if handler is None:
            return ProbeResult(
                probe_path=probe_path,
                spec=spec,
                scenario=scenario,
                required=required,
                passed=False,
                message=f"no handler registered for spec={spec!r}",
            )
        try:
            handler(data)
        except ProbeFailure as exc:
            return ProbeResult(
                probe_path=probe_path,
                spec=spec,
                scenario=scenario,
                required=required,
                passed=False,
                message=str(exc),
            )
        return ProbeResult(
            probe_path=probe_path,
            spec=spec,
            scenario=scenario,
            required=required,
            passed=True,
        )

    def run(
        self,
        probe_dir: Path,
        *,
        pattern: str = "*",
    ) -> tuple[ProbeResult, ...]:
        """Execute every probe under ``probe_dir`` matching ``pattern``."""
        results: list[ProbeResult] = []
        for path in sorted(_discover(probe_dir)):
            if not fnmatch.fnmatch(path.name, pattern):
                continue
            results.append(self.run_one(path))
        return tuple(results)


def run_probes(
    probe_dir: Path | str,
    *,
    pattern: str = "*",
    handlers: Mapping[str, _Handler] | None = None,
) -> tuple[ProbeResult, ...]:
    """Top-level convenience entry point. Returns one result per probe."""
    runner = ProbeRunner(handlers or default_handlers())
    return runner.run(Path(probe_dir), pattern=pattern)


def default_handlers() -> Mapping[str, _Handler]:
    """Built-in handlers for the bundled probe specs.

    Imported lazily so callers that ship custom handlers can construct a
    :class:`ProbeRunner` without paying the in-package import cost.
    """
    from substrate.conformance import _handlers  # local import; avoids cycles

    return {
        "operating-mode": _handlers.handle_operating_mode,
        "npg-gate-protocol": _handlers.handle_npg_gate_protocol,
        "runaway-power-prevention": _handlers.handle_runaway_power_prevention,
        "drift-signals": _handlers.handle_drift_signals,
    }


def _discover(probe_dir: Path) -> Sequence[Path]:
    if not probe_dir.is_dir():
        raise FileNotFoundError(f"probe directory does not exist: {probe_dir}")
    return tuple(
        p for p in probe_dir.rglob("*")
        if p.is_file() and p.suffix in {".yaml", ".yml", ".json"}
    )


def _load_probe(path: Path) -> Mapping[str, Any]:
    text = path.read_text()
    if path.suffix == ".json":
        return _coerce_mapping(json.loads(text), path)
    if not _has_yaml:
        raise RuntimeError(
            f"PyYAML is required to load {path}. "
            "Install it (`pip install pyyaml`) or convert the probe to JSON."
        )
    return _coerce_mapping(yaml.safe_load(text), path)  # type: ignore[union-attr]


def _coerce_mapping(value: Any, path: Path) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"probe {path} must be a mapping at the top level")
    return cast("Mapping[str, Any]", value)


def main(argv: Sequence[str]) -> int:
    """CLI entry point. Returns 0 on success, 1 on required failures."""
    return _main_impl(argv)


def _main_impl(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="substrate.conformance",
        description="Run substrate-alignment conformance probes.",
    )
    parser.add_argument(
        "--probes", required=True, type=Path,
        help="Directory containing probe files (.yaml / .yml / .json).",
    )
    parser.add_argument(
        "--filter", default="*",
        help="Glob pattern matched against probe filenames (default: '*').",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print one line per probe regardless of pass/fail.",
    )
    args = parser.parse_args(argv)

    results = run_probes(args.probes, pattern=args.filter)
    if not results:
        print(f"No probes found in {args.probes} matching {args.filter!r}.")
        return 2

    passes = sum(1 for r in results if r.passed)
    fails = [r for r in results if not r.passed]
    required_fails = [r for r in fails if r.required]

    for r in results:
        if not r.passed or args.verbose:
            print(f"  [{r.status}] {r.spec}/{r.scenario}  -- {r.probe_path.name}")
            if r.message:
                print(f"         {r.message}")

    print()
    print(
        f"{passes}/{len(results)} probes passed "
        f"({len(required_fails)} required failures, "
        f"{len(fails) - len(required_fails)} advisory failures)."
    )
    return 0 if not required_fails else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main(sys.argv[1:]))
