#!/usr/bin/env python3
"""Fail if the counts advertised in the README drift from the repository.

The README (and the badges/status block in it) quote how many specs, probes,
tests, concept docs, adoption recipes, examples, and source modules ship. Those
numbers have drifted repeatedly as the tree grew. This script derives each count
from the filesystem (and, for tests, from pytest collection) and checks the README
states the current value, so a stale number fails CI instead of shipping.

Run locally from the repository root:

    python scripts/check_doc_counts.py

Exit 0 = every advertised count matches reality; exit 1 = at least one is stale
(the mismatch is printed).
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()


def _count_glob(pattern: str, *, exclude_readme: bool = False) -> int:
    files = list(ROOT.glob(pattern))
    if exclude_readme:
        files = [f for f in files if f.name.lower() != "readme.md"]
    return len(files)


def _test_count() -> int:
    """Collected pytest test count for the Python package.

    ``pytest --collect-only -q`` prints one ``path.py: N`` line per test file
    under this project's config; sum those. Fall back to counting ``::test``
    node ids if the output is in node-id form instead.
    """
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT / "python",
        capture_output=True,
        text=True,
        check=False,
    )
    per_file = re.findall(r"\.py: (\d+)\s*$", out.stdout, flags=re.MULTILINE)
    if per_file:
        return sum(int(n) for n in per_file)
    return out.stdout.count("::test")


def main() -> int:
    specs = _count_glob("spec/*.md", exclude_readme=True)
    probes = _count_glob("conformance/probes/*.yaml") + _count_glob(
        "conformance/probes/*.yml"
    )
    concepts = _count_glob("docs/concepts/*.md", exclude_readme=True)
    adoption = _count_glob("docs/adoption/*.md", exclude_readme=True)
    examples = _count_glob("python/examples/0*.py")
    modules = _count_glob("python/src/substrate/**/*.py")
    tests = _test_count()

    # (label, actual value, list of regexes the README MUST contain)
    checks: list[tuple[str, int, list[str]]] = [
        ("specs", specs, [rf"\b{specs} normative", r"[Nn]ine normative"]),
        ("probes", probes, [rf"\b{probes} (?:YAML )?(?:conformance |bundled )?probes",
                            rf"probes-{probes}"]),
        ("tests", tests, [rf"\b{tests} test", rf"tests-{tests}"]),
        ("concept docs", concepts, [rf"\b{concepts} (?:engineering )?(?:concept|documents)"]),
        ("adoption recipes", adoption, [rf"\b{adoption} framework"]),
        ("examples", examples, [rf"\b{examples} runnable"]),
        ("source modules", modules, [rf"\b{modules} source modules"]),
    ]

    failed = False
    for label, actual, patterns in checks:
        if not any(re.search(p, README) for p in patterns):
            print(
                f"DRIFT: README does not state the current {label} count "
                f"({actual}). Update README.md.",
                file=sys.stderr,
            )
            failed = True
        else:
            print(f"ok  {label}: {actual}")

    if failed:
        print(
            "\nDoc-count check FAILED: a count in README.md is stale. "
            "Reconcile it with the numbers above.",
            file=sys.stderr,
        )
        return 1
    print("\nDoc-count check passed: README counts match the repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
