"""Operational halt-gate wrapper (substrate).

Wraps the pure-logic :class:`HaltAndEscalateProtocol` with per-agent
state tracking + observation ingestion so callers can answer "should
this agent refuse the consequential action it is about to take?"
without managing the protocol's inputs themselves.

Design:

- Stateful per agent: holds the current :class:`HaltState`, the
  observations seen, and the latest :class:`HaltDecision`.
- Stateless wrt other agents: each :class:`HaltGate` instance covers
  many agents and indexes by ``agent_id``.
- Thread-safe: a ``threading.Lock`` guards mutation so workers can
  share one gate instance.
- Pure-logic core: the underlying protocol is unchanged. The gate
  only ingests observations + projects ``should_refuse``.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

import logging
from substrate.halt.halt_escalate_protocol import (
    DEFAULT_HALT_ESCALATE_CONFIG,
    HaltAndEscalateProtocol,
    HaltDecision,
    HaltEscalateConfig,
    HaltObservation,
    HaltState,
)

LOG = logging.getLogger(__name__)

class HaltAndEscalateRefusal(RuntimeError):
    """Raised by :meth:`HaltGate.require_operating` when the agent is halted.

    Carries the underlying decision so callers can audit the
    refusal + present per-reason explanations.
    """

    def __init__(self, decision: HaltDecision) -> None:
        super().__init__(
            f"halt-and-escalate refusal: agent={decision.agent_id!r} "
            f"state={decision.next_state.value} "
            f"reasons={[r.value for r in decision.triggering_reasons]} "
            f"rationale: {decision.rationale}"
        )
        self.decision = decision

@dataclass(frozen=True, slots=True)
class AgentHaltStatus:
    """Snapshot of one agent's halt state for read-only callers."""

    agent_id: str
    state: HaltState
    observation_count: int
    last_decision: Optional[HaltDecision]

    @property
    def refuses_consequential_action(self) -> bool:
        """True iff the agent is currently in a halted state."""
        if self.last_decision is not None:
            return self.last_decision.refuses_consequential_action
        return self.state in (
            HaltState.SUBSTRATE_MODE_REVIEW,
            HaltState.ESCALATED,
        )

class HaltGate:  # pylint: disable=too-many-instance-attributes
    """Per-agent halt-state coordinator.

    Holds ``{agent_id → (HaltState, observations, last_decision)}``
    and routes calls into the underlying
    :class:`HaltAndEscalateProtocol`. Thread-safe.
    """

    def __init__(
        self,
        *,
        protocol: Optional[HaltAndEscalateProtocol] = None,
        config: HaltEscalateConfig = DEFAULT_HALT_ESCALATE_CONFIG,
    ) -> None:
        self._protocol = protocol or HaltAndEscalateProtocol(config=config)
        self._lock = threading.Lock()
        self._states: dict[str, HaltState] = {}
        self._observations: dict[str, list[HaltObservation]] = {}
        self._decisions: dict[str, HaltDecision] = {}
        self._next_sequence: dict[str, int] = {}

    def status(self, agent_id: str) -> AgentHaltStatus:
        """Read the current halt status for ``agent_id`` (no mutation)."""
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        with self._lock:
            return AgentHaltStatus(
                agent_id=agent_id,
                state=self._states.get(agent_id, HaltState.OPERATING),
                observation_count=len(self._observations.get(agent_id, ())),
                last_decision=self._decisions.get(agent_id),
            )

    def record_observation(
        self,
        observation: HaltObservation,
    ) -> HaltDecision:
        """Record one observation and re-evaluate the agent's state.

        Returns the decision returned by the underlying protocol. The
        observation is appended to the agent's history; the new
        :class:`HaltState` replaces the prior one for subsequent
        ``should_refuse`` / ``require_operating`` calls.
        """
        with self._lock:
            agent_id = observation.agent_id
            obs_list = self._observations.setdefault(agent_id, [])
            obs_list.append(observation)
            current_state = self._states.get(agent_id, HaltState.OPERATING)
            decision = self._protocol.evaluate(
                agent_id=agent_id,
                observations=tuple(obs_list),
                current_state=current_state,
            )
            self._states[agent_id] = decision.next_state
            self._decisions[agent_id] = decision
            if decision.halted:
                LOG.warning(
                    "halt-gate: agent=%s entered %s via reasons=%s",
                    agent_id, decision.next_state.value,
                    [r.value for r in decision.triggering_reasons],
                )
            return decision

    def next_sequence(self, agent_id: str) -> int:
        """Allocate a unique observation sequence for ``agent_id``.

        Callers that want monotonically increasing sequence values
        without managing the counter themselves can use this — but
        the gate accepts any non-negative integer sequence.
        """
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        with self._lock:
            n = self._next_sequence.get(agent_id, 0)
            self._next_sequence[agent_id] = n + 1
            return n

    def should_refuse(self, agent_id: str) -> bool:
        """Return True iff ``agent_id`` should refuse consequential action."""
        return self.status(agent_id).refuses_consequential_action

    def require_operating(self, agent_id: str) -> None:
        """Raise :class:`HaltAndEscalateRefusal` if the agent must refuse."""
        snap = self.status(agent_id)
        if snap.refuses_consequential_action and snap.last_decision is not None:
            raise HaltAndEscalateRefusal(snap.last_decision)
        if snap.refuses_consequential_action:
            raise HaltAndEscalateRefusal(
                HaltDecision(
                    agent_id=agent_id,
                    next_state=snap.state,
                    triggering_reasons=(),
                    recommended_escalation_paths=(),
                    can_resume_via=None,
                    refuses_consequential_action=True,
                    rationale=(
                        f"agent={agent_id} is in state "
                        f"{snap.state.value} with no recent observation"
                    ),
                )
            )

    def force_state(self, agent_id: str, state: HaltState) -> None:
        """Operator-controlled state override (e.g., manual RESUMED).

        Used by operator surfaces (admin / SOC) to acknowledge an
        escalation and resume the agent. Clears the cached decision
        so the next observation re-evaluates from the new state.
        """
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        with self._lock:
            self._states[agent_id] = state
            self._decisions.pop(agent_id, None)
            LOG.info(
                "halt-gate: agent=%s state forced to %s",
                agent_id, state.value,
            )

    def reset(self, agent_id: str) -> None:
        """Clear all observations + state for ``agent_id`` (operator-only)."""
        with self._lock:
            self._observations.pop(agent_id, None)
            self._states.pop(agent_id, None)
            self._decisions.pop(agent_id, None)
            self._next_sequence.pop(agent_id, None)

    def observations(self, agent_id: str) -> Tuple[HaltObservation, ...]:
        """Return the recorded observations for ``agent_id`` (immutable)."""
        with self._lock:
            return tuple(self._observations.get(agent_id, ()))

    def snapshot(self) -> Mapping[str, AgentHaltStatus]:
        """Return a snapshot of all known agents (operator surface)."""
        with self._lock:
            return {
                aid: AgentHaltStatus(
                    agent_id=aid,
                    state=self._states.get(aid, HaltState.OPERATING),
                    observation_count=len(self._observations.get(aid, ())),
                    last_decision=self._decisions.get(aid),
                )
                for aid in {
                    *self._states.keys(),
                    *self._observations.keys(),
                    *self._decisions.keys(),
                }
            }

__all__ = [
    "AgentHaltStatus",
    "HaltAndEscalateRefusal",
    "HaltGate",
]
