# Starter kit: a governed agent action loop

A small but complete governed system you can clone, run, and adapt. Where the
`examples/0*.py` snippets each show one primitive, this wires the core primitives
into one believable loop.

## Run it

From the `python/` directory, with the package installed (`pip install -e .`):

```bash
python examples/starter_kit/governed_agent.py
```

Expected output:

```
seeded 3 entities; processing 4 proposed actions

[d1] teach        verdict=net_positive     score=+0.30 → PERMIT  (audit seq=0, hash=…)
[d2] mentor       verdict=net_positive     score=+0.50 → PERMIT  (audit seq=1, hash=…)
[d3] extract      verdict=net_negative     score=-0.40 → REFUSE  (audit seq=2, hash=…)
      ↳ halt protocol: state=escalated refuses_consequential=True
[d4] collaborate  verdict=net_positive     score=+0.40 → PERMIT  (audit seq=3, hash=…)

audit chain: 4 records, verify().ok=True
final halt state: escalated
```

## What it demonstrates

An agent `atlas` works through a queue of proposed actions. For each one the loop:

1. **Gates** the action with the [net-potential-gain gate](../../../docs/concepts/npg-gate.md),
   using a projected per-entity delta; the extractive `extract` action scores
   negative and is refused.
2. **Audits** every decision (permitted *and* refused) into a hash-chained
   [substrate-trace ledger](../../../docs/concepts/audit-chain.md).
3. **Escalates** on a net-negative action via the
   [halt-and-escalate protocol](../../../docs/concepts/halt-and-escalate.md),
   which moves the agent into a state that refuses further consequential actions.

At the end it verifies the whole decision chain: an auditor re-runs `verify()`
and re-derives every verdict; nothing is taken on trust.

## Make it yours

Open `governed_agent.py` and edit `ACTION_QUEUE`:

- Add an action and give it a per-entity delta.
- Flip a delta negative and watch the verdict become `REFUSE` and the halt state escalate.
- Remove the seeding for an entity and watch the gate return `INSUFFICIENT_DATA`
  instead of guessing.

The full walkthrough (building this loop from scratch and understanding each
decision) is the [tutorial](../../../docs/tutorial.md).
