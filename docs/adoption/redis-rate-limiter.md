# Using ResistanceBand to derive limits in a Redis-backed rate limiter

This recipe shows how to derive the soft and hard limits of a Redis-backed token-bucket rate limiter from the [resistance band](../concepts/resistance-band.md). Every limiter in the host application ends up commensurable: when one subsystem's band tightens (operator action), every limiter that draws from the band tightens with it.

The pattern is small but pins down a discipline that's often re-invented per limiter: **anchor every threshold to the same band, not to ad-hoc multipliers**.

## What you need

- A Redis instance.
- A token-bucket rate limiter library (this recipe uses `redis-py` directly for clarity).
- A measurement of *capacity* per limiter (requests-per-second the upstream can sustain, bytes-per-second the bandwidth budget allows, etc.).

## The derivation

```python
# app/rate_limit.py
from __future__ import annotations

from typing import Optional
import redis
from substrate import ResistanceBandConfig
from substrate.threshold_derivation import (
    BandPosition,
    derive_soft_limit,
    derive_threshold_float,
    derive_work_target_float,
)


class BandLimiter:
    """A Redis token-bucket limiter whose limits derive from the resistance band.

    The ``capacity`` constructor argument is what the upstream can sustain
    in the unit of your limiter (req/s, bytes/s, work-units/s). The limiter
    derives:

    - ``soft_limit`` (resistance lower edge, ``1/3 × capacity``): where the
      limiter starts applying gentle backpressure.
    - sustained ``refill`` rate (work-zone target, ``~4/9 × capacity``): the
      throughput the limiter sustains is a WORK (carried-load) quantity, so it
      targets the work zone, not the resistance setpoint.
    - ``hard_limit`` (work-zone ceiling, ``1/2 × capacity``): the top of the
      sustainable work zone, above which requests are rejected. This sits
      *above* the sustained refill rate, as a reject ceiling must.

    Limit *override* policy follows the band: tighter is permitted, looser
    is rejected at construction.
    """

    def __init__(
        self,
        *,
        key_prefix: str,
        capacity: float,
        redis_client: redis.Redis,
        band: Optional[ResistanceBandConfig] = None,
    ) -> None:
        self._redis = redis_client
        self._prefix = key_prefix
        self._soft = float(derive_soft_limit(int(capacity), config=band))
        # The sustained refill and the reject ceiling are WORK quantities
        # (throughput carried), so both come from the work zone: the target
        # (~4/9) for the sustained rate, the ceiling (0.5) for hard reject.
        self._refill_per_sec = derive_work_target_float(capacity, config=band)
        self._hard = derive_threshold_float(
            capacity, position=BandPosition.WORK_CEILING, config=band,
        )

    @property
    def soft_limit(self) -> float:
        return self._soft

    @property
    def hard_limit(self) -> float:
        return self._hard

    def consume(self, key: str, *, cost: float = 1.0) -> bool:
        """Attempt to consume ``cost`` tokens from the limiter for ``key``.

        Returns ``True`` if the request is permitted, ``False`` otherwise.

        Implementation: simple token bucket via Redis ``SET`` + ``EXPIRE``;
        production deployments use a Lua script for atomicity. Algorithm
        details are out of scope; the point is how the limits are derived.
        """
        bucket_key = f"{self._prefix}:bucket:{key}"
        timestamp_key = f"{self._prefix}:ts:{key}"
        # ... token-bucket bookkeeping with self._refill_per_sec and self._hard ...
        # (See your favourite redis-py rate-limiter tutorial for the
        # Lua-script form.)
        return True  # placeholder
```

## What the band buys

- **Commensurability across limiters.** A `BandLimiter(capacity=1000)` for one upstream and a `BandLimiter(capacity=10_000)` for another have the same *shape*; both sustain throughput in the work zone (`~38–50%` of capacity, the carried-load band) with the same burst/reject edges. Operators reasoning about either limiter use the same mental model.
- **Single-knob tightening.** When operations needs to shed load globally (e.g., a degraded downstream), tightening the band config propagates to every limiter that derives from it. No per-limiter migration.
- **Refusal of unsafe widening.** A subsystem that proposes a `lower_bound=0.20, upper_bound=0.50` configuration is *refused at construction* (the package rejects loosening past defaults). The operator surface gets the error early, not when the limiter is in production.

## Per-deployment tighter band

A deployment with independent evidence that a tighter band is warranted (e.g., a regulated environment where utilisation past `35%` shows latency tail risk) can construct a tighter `ResistanceBandConfig` and pass it to every limiter:

```python
# app/configs.py
from substrate import ResistanceBandConfig

TIGHT_BAND = ResistanceBandConfig(lower_bound=0.34, upper_bound=0.36)

# app/main.py
limiter = BandLimiter(
    key_prefix="api:read",
    capacity=10_000,
    redis_client=redis_client,
    band=TIGHT_BAND,
)
```

Every limiter in the deployment that takes the same `TIGHT_BAND` is now tightened together. Subsystems can also adopt the tighter band independently; the package permits tightening locally without requiring it deployment-wide.

## What this wiring deliberately does not do

- It does not abstract away the token-bucket algorithm. Token-bucket vs. leaky-bucket vs. GCRA is a deployment choice; the band derives the *limits*, not the algorithm.
- It does not auto-tune `capacity` from observed load. That's a closed-loop controller's job; the band gives it a target (`recommend_scaling_factor`) but doesn't run the loop.
- It does not enforce that every limiter in the application uses `BandLimiter`. The discipline is a recommendation; ad-hoc limiters still work, but lose commensurability.

## Closed-loop controller variant

For limiters whose capacity changes over time (e.g., upstream auto-scaling), the band exposes `recommend_scaling_factor`:

```python
from substrate import recommend_scaling_factor

def autotune_capacity(current_qps: float, capacity_qps: float) -> float:
    utilisation = min(1.0, current_qps / capacity_qps)
    factor = recommend_scaling_factor(utilisation)
    # factor > 1.0 → grow capacity; factor < 1.0 → shrink
    return capacity_qps * factor
```

This is the *control* version of the derivation: instead of pinning limits, it walks the capacity toward the band's midpoint.

## Testing

```python
# tests/test_rate_limit.py
from substrate import ResistanceBandConfig
from app.rate_limit import BandLimiter

def test_limits_derive_from_default_band(fake_redis) -> None:
    limiter = BandLimiter(
        key_prefix="t", capacity=1000.0, redis_client=fake_redis,
    )
    assert limiter.soft_limit == 333    # 1000 * 1/3 (resistance lower edge)
    assert limiter.hard_limit == 500.0  # 1000 * 1/2 (work-zone ceiling)

def test_looser_band_override_rejected(fake_redis) -> None:
    import pytest
    with pytest.raises(ValueError):
        BandLimiter(
            key_prefix="t",
            capacity=1000.0,
            redis_client=fake_redis,
            band=ResistanceBandConfig(lower_bound=0.20, upper_bound=0.50),
        )
```

## See also

- [Resistance band concept](../concepts/resistance-band.md). Derivation of the default bounds, the `1/φ²` upper anchor, the tighter-not-looser discipline.
- [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md) mechanism 4. The normative definition.
- [`examples/02_resistance_band.py`](../../python/examples/02_resistance_band.py). Runnable demonstration.
