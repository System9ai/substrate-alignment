"""Potential-trajectory class: the perspective-taking input.

An entity's potential-trajectory determines how the same raw impact reweights on
the long horizon (a benefit to a high-future-potential DEVELOPING entity compounds;
a harm to an accumulated-and-at-risk VULNERABLE one bites harder). A minimal,
self-contained enum for the deliberation engine.
"""
from __future__ import annotations

from enum import Enum


class TrajectoryClass(str, Enum):
    """The potential-trajectory class of an entity."""

    DEVELOPING = "developing"      # high future potential (a child / seed)
    ESTABLISHED = "established"    # at capacity
    VULNERABLE = "vulnerable"      # accumulated + at risk (an elder / dependent)
    STATIC = "static"             # spent / low remaining potential
    UNKNOWN = "unknown"


__all__ = ["TrajectoryClass"]
