"""Example 05 — Halt-and-escalate protocol with audit chain.

Demonstrates the full halt-and-escalate flow:

1. An OPERATING agent observes a single SUSTAINED_DRIFT_CRITICAL signal
   → moves to SUBSTRATE_MODE_REVIEW (gate-narrowing state).
2. The decision appends a record to the audit ledger.
3. An INVERSION_DETECTED observation arrives → immediate-escalate to
   ESCALATED.
4. The escalation appends another record. The ledger's hash continuity
   verifies end-to-end.
5. Resume requires an explicit operator action (we do not auto-resume).

Run with::

    python 05_halt_and_escalate.py
"""
from __future__ import annotations

from substrate import NetPotentialGainVerdict, ResistanceBandClassification
from substrate.audit.substrate_trace import SubstrateTraceLedger
from substrate.halt.halt_escalate_protocol import (
    HaltAndEscalateProtocol,
    HaltObservation,
    HaltReason,
    HaltState,
)


def show(label: str, decision: object) -> None:
    """Cast away the protocol's return type for compact display."""
    d = decision  # type: ignore[assignment]
    print(
        f"  {label:30s} next_state={d.next_state.value:24s} "  # type: ignore[attr-defined]
        f"refuses={d.refuses_consequential_action}"            # type: ignore[attr-defined]
    )


def main() -> None:
    protocol = HaltAndEscalateProtocol()
    ledger = SubstrateTraceLedger()
    agent_id = "alice"
    state = HaltState.OPERATING

    # [1] OPERATING + sustained-drift-critical → SUBSTRATE_MODE_REVIEW
    obs_1 = (
        HaltObservation(
            sequence=0, timestamp=1_700_000_000, agent_id=agent_id,
            halt_reason=HaltReason.SUSTAINED_DRIFT_CRITICAL, severity=0.95,
            evidence="extractive-gain pattern sustained across 5 decisions",
        ),
    )
    decision_1 = protocol.evaluate(agent_id, obs_1, current_state=state)
    show("[1] sustained-drift-critical", decision_1)

    ledger.append(
        decision_id="halt-1",
        decision_kind="halt_escalate",
        permitted=not decision_1.refuses_consequential_action,
        rationale=decision_1.rationale,
        epoch_seconds=1_700_000_000,
        npg_verdict=NetPotentialGainVerdict.NET_NEUTRAL,
        resistance_band=ResistanceBandClassification.PRODUCTIVE,
    )
    state = decision_1.next_state

    # [2] After review, an inversion event → immediate-escalate to ESCALATED.
    obs_2 = (
        HaltObservation(
            sequence=1, timestamp=1_700_000_300, agent_id=agent_id,
            halt_reason=HaltReason.INVERSION_DETECTED, severity=0.97,
            evidence="180° inversion: extraction with long-cycle framing",
        ),
    )
    decision_2 = protocol.evaluate(agent_id, obs_2, current_state=state)
    show("[2] inversion-detected", decision_2)

    ledger.append(
        decision_id="halt-2",
        decision_kind="halt_escalate",
        permitted=not decision_2.refuses_consequential_action,
        rationale=decision_2.rationale,
        epoch_seconds=1_700_000_300,
        npg_verdict=NetPotentialGainVerdict.NET_NEGATIVE,
        resistance_band=ResistanceBandClassification.STRESSED,
    )
    state = decision_2.next_state

    # [3] Audit chain verification.
    verification = ledger.verify()
    print()
    print(f"  audit chain ok       = {verification.ok}")
    print(f"  audit chain length   = {ledger.length}")
    last = ledger.last()
    if last is not None:
        print(f"  audit head hash      = {last.record_hash[:12]}…")

    # [4] Resume requires an explicit operator action.
    print()
    print(
        "  resume requires explicit operator action — the protocol does\n"
        "  not auto-resume even when the trigger expires. Halted entities\n"
        "  stay halted until the operator clears them.\n"
        f"  recommended resumption path: {decision_2.can_resume_via}"
    )


if __name__ == "__main__":
    main()
