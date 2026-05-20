"""Pair-coupling primitives.

A pair coupling is a sustained two-entity relationship (peer pair,
agent pair, service pair) that develops shared substrate state across
many interaction cycles. Substrate-aligned pair couplings are those in
which both poles' substrate-state trajectories rise together;
extractive couplings raise one pole at the other's expense; degrading
couplings raise neither.

The primitives in this sub-package — the state machine, the
asymmetry-preservation gate, the alignment-audit verifier, the
extraction monitor, the trajectory-capacity tracker — together let a
host application surface extraction patterns *before* they become
sustained drift.

See ``docs/concepts/pair-coupling.md`` for the engineering rationale
and ``spec/runaway-power-prevention.md`` (mechanism 5) for the
normative behaviour.
"""
