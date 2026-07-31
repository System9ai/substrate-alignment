"""Smoke tests for the substrate-alignment bootstrap package.

These exist so CI has a passing test target before primitives are ported.
They verify only that the package is importable and exposes a non-empty
version string.
"""

from __future__ import annotations

import re

import substrate


def test_package_imports() -> None:
    """The top-level ``substrate`` module is importable."""
    assert substrate is not None


def test_version_is_pep440_release() -> None:
    """``substrate.__version__`` is a non-empty PEP 440 release identifier."""
    version = substrate.__version__
    assert isinstance(version, str)
    assert version
    # Loose PEP 440 check: starts with N.N.N, optionally followed by
    # pre/post/dev/local segments. Sufficient for the bootstrap stub.
    assert re.match(r"^\d+\.\d+\.\d+", version), version
