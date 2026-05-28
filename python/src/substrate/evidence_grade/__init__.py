"""Evidence-grade ladder for substrate-state claims (spec v0.2.0).

A pure-logic primitive that assigns a four-step grade —
``UNVERIFIED_HEARSAY`` < ``CORROBORATED`` < ``ATTESTED`` <
``DOCUMENTED_CRYSTALLIZED`` — to a substrate-state claim from the
sequence of attestations supporting it.

Existing specs (``operating-mode``, ``npg-gate-protocol``, …) define
how an entity's substrate state is computed and acted on. They are
silent on **how confidently a claim about that state may be relied
on**. The evidence-grade ladder gives downstream consumers a stable
ordinal they can weight, gate, or reject against — so a claim from a
single anonymous heuristic and a claim from three cryptographically
signed peer attestations no longer look alike.

The composer is host-agnostic. Host applications (MNEMOSYNE, ARGUS,
project-specific stores) declare conformance by implementing the
:class:`SubstrateStateClaim` Protocol on their canonical-state
records.

See ``spec/evidence-grade.md`` for the normative behaviour and
``conformance/probes/evidence-grade__*.yaml`` for the conformance
probes.
"""
