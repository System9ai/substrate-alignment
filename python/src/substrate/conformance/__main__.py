"""CLI entry point: ``python -m substrate.conformance``."""
from __future__ import annotations

import sys

from substrate.conformance.probe_runner import main

if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main(sys.argv[1:]))
