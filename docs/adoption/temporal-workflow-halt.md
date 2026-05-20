# Wiring halt-and-escalate into a Temporal workflow

This recipe shows how to consult the [halt-and-escalate protocol](../concepts/halt-and-escalate.md) at activity boundaries in a long-running Temporal workflow. The pattern fits Temporal's signal/activity model exactly: drift observations arrive as signals, the workflow re-evaluates state between activities, and a halted workflow waits for an explicit operator signal to resume.

## What you need

- A Temporal cluster and the Python SDK (`temporalio`).
- A `SubstrateMetadataStore` instance (this recipe assumes you already have one — see [`sqlalchemy-metadata-store.md`](sqlalchemy-metadata-store.md) for the Protocol implementation against a real database).
- An audit ledger (in-process `SubstrateTraceLedger` for this recipe; see [`audit-chain-postgres.md`](audit-chain-postgres.md) for the persistent backend).

## Module layout

```
app/
├── workflows/
│   ├── halted_workflow.py    # the workflow itself
│   └── activities.py         # the activity bodies
└── substrate_deps.py         # the protocol + store; constructed once per worker
```

## The wiring

```python
# app/workflows/halted_workflow.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow

from substrate.halt.halt_escalate_protocol import (
    HaltAndEscalateProtocol,
    HaltObservation,
    HaltReason,
    HaltState,
)


@dataclass
class HaltSignal:
    """Drift observation arriving as a Temporal signal."""
    halt_reason: str
    severity: float
    evidence: str = ""


@workflow.defn
class HaltedWorkflow:
    """Long-running workflow that consults the halt protocol per activity.

    The workflow:

    1. Accepts ``HaltSignal`` updates over the workflow's lifetime
       (drift detectors send signals when they observe a triggering
       condition).
    2. Re-evaluates the halt protocol before each consequential activity.
    3. When in ``SUBSTRATE_MODE_REVIEW`` or ``ESCALATED``, awaits an
       explicit ``resume`` signal from an operator. **No auto-resume.**
    4. Otherwise dispatches the activity as normal.
    """

    def __init__(self) -> None:
        self._observations: list[HaltObservation] = []
        self._state: HaltState = HaltState.OPERATING
        self._resume_requested: bool = False

    @workflow.signal
    def report_halt_condition(self, signal: HaltSignal) -> None:
        # Temporal workflow code is deterministic; ``HaltObservation``
        # uses :func:`workflow.now` for the timestamp so it stays
        # reproducible under workflow replay.
        seq = len(self._observations)
        timestamp = int(workflow.now().timestamp())
        self._observations.append(
            HaltObservation(
                sequence=seq,
                timestamp=timestamp,
                agent_id=workflow.info().workflow_id,
                halt_reason=HaltReason(signal.halt_reason),
                severity=signal.severity,
                evidence=signal.evidence,
            )
        )

    @workflow.signal
    def resume(self) -> None:
        """Operator-driven resume; clears the resume_requested gate."""
        self._resume_requested = True

    async def _gate(self) -> bool:
        """Evaluate the halt protocol and gate consequential activities.

        Returns ``True`` if the workflow may proceed with the next
        activity; awaits the operator ``resume`` signal otherwise.
        """
        protocol = HaltAndEscalateProtocol()
        decision = protocol.evaluate(
            workflow.info().workflow_id,
            tuple(self._observations),
            current_state=self._state,
        )
        self._state = decision.next_state
        if not decision.refuses_consequential_action:
            return True
        # Halted. Park until the operator signals resume.
        workflow.logger.info(
            "halted by reason(s)=%s; waiting for resume signal. "
            "recommended path=%s",
            [r.value for r in decision.triggering_reasons],
            decision.can_resume_via,
        )
        await workflow.wait_condition(lambda: self._resume_requested)
        # Reset the gate; future halt conditions will re-trip it.
        self._resume_requested = False
        self._state = HaltState.RESUMED
        return True

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        for activity_name in payload["activities"]:
            await self._gate()
            await workflow.execute_activity(
                activity_name,
                payload,
                start_to_close_timeout=timedelta(minutes=5),
            )
        return {"status": "complete"}
```

## What this wiring buys

- **No auto-resume.** The package's halt-and-escalate discipline is "easy to enter halted states, hard to leave". Temporal's `wait_condition` enforces this naturally — the workflow literally cannot proceed until an operator signal lands.
- **Replay-safe.** Halt observations are stored on the workflow object and timestamped via `workflow.now()`; under replay, the protocol's verdict is identical to its original evaluation.
- **Signal-handler ergonomics.** Operator dashboards send a single `resume` signal to clear a halt; drift detectors send `report_halt_condition` signals with the structured payload. No bespoke RPC layer.
- **Per-activity gating.** The gate runs between activities, not inside them. An activity that has already started runs to completion; the next one is gated.

## What this wiring deliberately does not do

- **It does not cancel running activities on halt.** If you need that, attach a `cancel` signal handler that calls `workflow.execute_activity` with `cancellation_type=...` semantics — but the package's discipline is that halting prevents *new* consequential action; activities already in flight finish.
- **It does not auto-escalate to higher operator levels.** The protocol returns `recommended_escalation_paths`; this recipe logs them but does not page anyone. Wire your paging integration on the signal-handler side, not in the workflow body (paging is non-deterministic and would break replay).
- **It does not collapse `SUBSTRATE_MODE_REVIEW` and `ESCALATED` into one state.** The two-state distinction is load-bearing (see [the halt-and-escalate concept doc](../concepts/halt-and-escalate.md)); the gate refuses both, but operator tooling differentiates them via `decision.next_state`.

## Activity-side audit-chain hookup

The workflow body does not directly append to the audit ledger because Temporal workflow code is deterministic. Activities (which run outside the deterministic context) do:

```python
# app/workflows/activities.py
from __future__ import annotations

from temporalio import activity

from substrate import NetPotentialGainVerdict, ResistanceBandClassification
from substrate.audit.substrate_trace import SubstrateTraceLedger


@activity.defn
async def teach_lesson(payload: dict) -> dict:
    # Real work happens here ...
    result = {...}

    # Append a substrate-trace record. The ledger handle comes from
    # the activity's worker-local state, not the workflow's.
    ledger: SubstrateTraceLedger = activity.info().heartbeat_details[0]  # or your DI
    ledger.append(
        decision_id=f"teach-{activity.info().workflow_id}-{activity.info().activity_id}",
        decision_kind="teach",
        permitted=True,
        rationale="activity executed under non-halted workflow",
        epoch_seconds=int(activity.info().started_time.timestamp()),
        npg_verdict=NetPotentialGainVerdict.NET_POSITIVE,
        resistance_band=ResistanceBandClassification.PRODUCTIVE,
    )
    return result
```

For a persistent audit ledger across workflow restarts, see [`audit-chain-postgres.md`](audit-chain-postgres.md).

## Testing

```python
# tests/workflows/test_halted_workflow.py
import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.workflows.halted_workflow import HaltSignal, HaltedWorkflow


@pytest.mark.asyncio
async def test_workflow_halts_then_resumes(client) -> None:
    async with WorkflowEnvironment() as env:
        async with Worker(env.client, task_queue="t", workflows=[HaltedWorkflow]):
            handle = await env.client.start_workflow(
                HaltedWorkflow.run, {"activities": ["teach_lesson"]},
                id="wf-1", task_queue="t",
            )
            await handle.signal(
                HaltedWorkflow.report_halt_condition,
                HaltSignal(halt_reason="inversion_detected", severity=0.95),
            )
            # Workflow is parked awaiting resume; assert it has not completed.
            with pytest.raises(TimeoutError):
                await handle.result(rpc_timeout=1)
            await handle.signal(HaltedWorkflow.resume)
            assert (await handle.result())["status"] == "complete"
```

## See also

- [Concept: halt-and-escalate](../concepts/halt-and-escalate.md) — the four states, six trigger reasons, resume discipline.
- [Example 05](../../python/examples/05_halt_and_escalate.py) — synchronous in-process demonstration of the same flow.
- [`audit-chain-postgres.md`](audit-chain-postgres.md) — persistent backend for the ledger that activities append to.
