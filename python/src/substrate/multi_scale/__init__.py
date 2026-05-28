"""SCAP Wave G.2 / spec v0.3.0 — pluggable substrate-scope registry.

Companion to the shipped ``substrate.multiscale.aggregator`` (single-
word ``multiscale`` package — the cell→node→org aggregator). This
hyphenated ``multi_scale`` package provides the *pluggable* scope
registry per ``spec/multi-scale.md``:

* :class:`SubstrateScope` — runtime-checkable Protocol that
  concrete scope classes implement.
* :class:`ScopeRegistry` — operator-extensible registry of
  scopes, pre-populated with the default ``cell`` / ``node`` /
  ``org`` triple.
* :data:`DEFAULT_SCOPES` — canonical default scope triple.

Operators register additional scopes (``household``, ``community``,
``squad``, …) for deployment-specific multi-scale aggregation.

Pure logic; no DAO, no LLM, no network.
"""
from substrate.multi_scale.scope_registry import (
    CELL_SCOPE,
    DEFAULT_SCOPES,
    NODE_SCOPE,
    ORG_SCOPE,
    ConcreteScope,
    ScopeRegistry,
    SubstrateScope,
    default_registry,
)

__all__ = [
    "CELL_SCOPE",
    "ConcreteScope",
    "DEFAULT_SCOPES",
    "NODE_SCOPE",
    "ORG_SCOPE",
    "ScopeRegistry",
    "SubstrateScope",
    "default_registry",
]
