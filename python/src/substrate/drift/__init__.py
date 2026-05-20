"""Substrate drift-detection primitives.

Pure-logic primitives that surface substrate-misalignment patterns
from a behaviour trace (text plus structured signals). The matcher
classifies detections against the seven canonical drift patterns; the
signal aggregator promotes per-entity severities (NONE → EMERGING →
SUSTAINED → CRITICAL) over a sliding observation window; the
golden-rule probe surfaces asymmetric reciprocal treatment as a
separate first-class signal.

See ``docs/concepts/drift-signals.md`` for the engineering rationale
and ``spec/drift-signals.md`` for the normative behaviour.
"""
