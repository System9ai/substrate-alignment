"""Example 02 — ResistanceBand and band-derived thresholds.

Demonstrates the productive-resistance band classifier and the
helpers that derive operational thresholds from it. The band's default
bounds are 1/3 (lower) and 1/φ² (upper); see
``docs/concepts/resistance-band.md`` for the derivation.

Run with::

    python 02_resistance_band.py
"""
from __future__ import annotations

from substrate import (
    ResistanceBandConfig,
    assess,
    classify,
    recommend_scaling_factor,
)
from substrate.threshold_derivation import (
    derive_batch_size,
    derive_quota_pair,
    derive_retry_cap,
    derive_target,
)


def main() -> None:
    # 1. Classify utilisation across the band.
    print("Classification at different utilisations:")
    for u in (0.10, 0.30, 0.35, 0.38, 0.50, 0.90):
        c = classify(u)
        print(f"  util={u:.2f}  ->  {c.value}")

    # 2. Full assessment — band classification + scaling factor.
    print("\nFull assessment at 0.50 utilisation (stressed):")
    a = assess(0.50)
    print(f"  classification     = {a.classification.value}")
    print(f"  distance_to_band   = {a.distance_to_band:+.3f}")
    print(f"  scaling_factor     = {a.recommended_scaling_factor:.3f}   "
          f"(< 1.0 → shed load)")
    print(f"  reasoning          = {a.reasoning}")

    # 3. Derive thresholds for a host application from the band.
    capacity = 1000  # whatever your capacity unit is
    soft, hard = derive_quota_pair(capacity)
    print(f"\nDerived thresholds for capacity={capacity}:")
    print(f"  soft_limit (band lower)    = {soft}")
    print(f"  target     (band midpoint) = {derive_target(capacity)}")
    print(f"  hard_limit (band upper)    = {hard}")
    print(f"  batch_size (band midpoint) = {derive_batch_size(capacity)}")
    print(f"  retry_cap  (band upper)    = {derive_retry_cap(10)}")

    # 4. Tighter band override — package permits tighter, rejects looser.
    print("\nTighter band override:")
    tight = ResistanceBandConfig(lower_bound=0.34, upper_bound=0.37)
    print(f"  recommend_scaling_factor(0.35, tight band) = "
          f"{recommend_scaling_factor(0.35, config=tight):.3f}")

    # 5. Looser band is rejected.
    print("\nLooser-than-default band is rejected:")
    try:
        ResistanceBandConfig(lower_bound=0.20, upper_bound=0.50)
    except ValueError as exc:
        print(f"  ValueError: {exc}")


if __name__ == "__main__":
    main()
