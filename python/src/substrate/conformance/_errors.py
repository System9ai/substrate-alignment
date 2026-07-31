"""Exception types raised inside the conformance package.

Lives in its own module so handlers and the runner can both import the
exception without forming an import cycle.
"""
from __future__ import annotations


class ProbeFailure(AssertionError):
    """Raised by a probe handler when the implementation did not match expected."""


__all__ = ["ProbeFailure"]
