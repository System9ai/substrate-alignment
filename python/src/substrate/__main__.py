"""``python -m substrate``: a zero-argument health check.

Run it right after installing to confirm the package works end to end::

    python -m substrate

It seeds an entity, routes a net-positive and a net-negative action through the
net-potential-gain gate, checks the verdicts, and prints a single pass/fail line.
Exit code ``0`` means the core primitives are working; non-zero means something is
wrong with the install. ``python -m substrate --version`` prints just the version.
"""
from __future__ import annotations

import sys

from substrate import (
    AlignmentVector,
    DefaultNetPotentialGainGate,
    EntityRef,
    InMemorySubstrateMetadataStore,
    NetPotentialGainVerdict,
    SubstrateMode,
    __version__,
)


def _self_check() -> bool:
    """Exercise the core gate path; return True iff both verdicts are as expected."""
    store = InMemorySubstrateMetadataStore()
    bob = EntityRef("user", "bob")
    store.upsert(
        bob,
        substrate_mode=SubstrateMode.LONG_CYCLE,
        classifier="self_check",
        classifier_rationale="seeded by python -m substrate",
        alignment_vector=AlignmentVector(),
        net_potential=0.5,
    )
    gate = DefaultNetPotentialGainGate(metadata_store=store)
    actor = EntityRef("agent", "alice")

    positive = gate.evaluate(
        actor=actor,
        action_kind="teach",
        affected_entities=(bob,),
        proposed_outcome={"expected_delta_by_entity": {"bob": 0.3}},
    )
    negative = gate.evaluate(
        actor=actor,
        action_kind="extract",
        affected_entities=(bob,),
        proposed_outcome={"expected_delta_by_entity": {"bob": -0.4}},
    )
    return (
        positive.verdict is NetPotentialGainVerdict.NET_POSITIVE
        and negative.verdict is NetPotentialGainVerdict.NET_NEGATIVE
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m substrate``."""
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in ("--version", "-V"):
        print(__version__)
        return 0

    print(f"substrate-alignment {__version__}")
    if _self_check():
        print("OK  net-potential-gain gate: NET_POSITIVE and NET_NEGATIVE as expected")
        print("The core primitives are working. Next: read docs/tutorial.md or run")
        print("  python examples/starter_kit/governed_agent.py")
        return 0
    print("FAIL  the self-check verdicts were not as expected; the install looks broken", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
