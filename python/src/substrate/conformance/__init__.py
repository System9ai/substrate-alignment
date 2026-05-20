"""Machine-checkable conformance probes.

Two surfaces live in this package:

- :mod:`substrate.conformance.assessment_service` — a pure-logic primitive
  for computing a conformance-assessment summary against a host
  application's substrate metadata.
- :mod:`substrate.conformance.probe_runner` — a runner that consumes the
  YAML probes under ``conformance/probes/`` (at the repository root) and
  validates the primitives in this package against them. Other language
  bindings of substrate-alignment ship their own runners that consume the
  same probe files.

Run the bundled probes from the repository root:

.. code-block:: shell

   python -m substrate.conformance --probes conformance/probes
"""
from substrate.conformance.probe_runner import (
    ProbeFailure,
    ProbeResult,
    ProbeRunner,
    run_probes,
)

__all__ = [
    "ProbeFailure",
    "ProbeResult",
    "ProbeRunner",
    "run_probes",
]
