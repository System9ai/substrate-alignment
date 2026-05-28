"""Pluggable substrate-scope registry per spec/multi-scale.md.

Pure-logic primitive. Default registry exposes ``cell`` / ``node`` /
``org`` per spec § 2.2. Operators register additional scopes via
:meth:`ScopeRegistry.register` for deployment-specific multi-scale
aggregation (``household`` / ``community`` for civic deployments,
``squad`` / ``platoon`` / ``battalion`` for tactical, etc.).

Spec invariants enforced at registration:

* ``name`` matches ``[a-z0-9_]+`` (non-empty, ASCII, lowercase).
* ``parent_name`` references a scope already in the registry.
* Adding the new scope would not create a cycle in the parent chain.
* Names are unique within a registry; duplicates raise
  :class:`ValueError`.

Honest uncertainty: :meth:`try_get` returns ``None`` for missing
scopes instead of inventing an empty default.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import (
    Final,
    Iterable,
    Optional,
    Protocol,
    runtime_checkable,
)


_VALID_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_]+$")


@runtime_checkable
class SubstrateScope(Protocol):
    """Per ``spec/multi-scale.md`` § 2.1.

    Read-only properties so frozen-dataclass implementations
    (:class:`ConcreteScope`) satisfy the Protocol — pyright treats
    mutable Protocol attributes as incompatible with frozen
    dataclasses.

    Concrete implementations are free to add methods / properties so
    long as the four named accessors below are present and behave as
    specified.
    """

    @property
    def name(self) -> str:
        """Canonical wire form. Matches ``[a-z0-9_]+``."""
        ...  # pylint: disable=unnecessary-ellipsis

    @property
    def display_name(self) -> str:
        """Human-readable form."""
        ...  # pylint: disable=unnecessary-ellipsis

    @property
    def parent_name(self) -> Optional[str]:
        """Immediate parent scope's ``name``, or ``None`` if top-level."""
        ...  # pylint: disable=unnecessary-ellipsis

    @property
    def aggregating(self) -> bool:
        """``True`` if observations at this scope aggregate from children."""
        ...  # pylint: disable=unnecessary-ellipsis


@dataclass(frozen=True, slots=True)
class ConcreteScope:
    """Reference implementation of :class:`SubstrateScope`.

    Frozen dataclass; safe to share across threads / registries.
    Construction validates ``name`` against the ASCII / lowercase /
    underscore-only rule from spec § 2.1.
    """

    name: str
    display_name: str
    parent_name: Optional[str]
    aggregating: bool

    def __post_init__(self) -> None:
        if not _VALID_NAME_RE.fullmatch(self.name):
            raise ValueError(
                "scope name must match [a-z0-9_]+; got "
                f"{self.name!r}"
            )
        if not self.display_name:
            raise ValueError("display_name must be non-empty")
        if self.parent_name is not None and not _VALID_NAME_RE.fullmatch(
            self.parent_name
        ):
            raise ValueError(
                "parent_name must match [a-z0-9_]+; got "
                f"{self.parent_name!r}"
            )


#: Default cell scope (terminal / leaf — observations originate here).
CELL_SCOPE: Final[ConcreteScope] = ConcreteScope(
    name="cell",
    display_name="Cell",
    parent_name="node",
    aggregating=False,
)


#: Default node scope (aggregates cells).
NODE_SCOPE: Final[ConcreteScope] = ConcreteScope(
    name="node",
    display_name="Node",
    parent_name="org",
    aggregating=True,
)


#: Default org scope (top-level by default).
ORG_SCOPE: Final[ConcreteScope] = ConcreteScope(
    name="org",
    display_name="Org",
    parent_name=None,
    aggregating=True,
)


#: Canonical default-scope triple per spec § 2.2.
DEFAULT_SCOPES: Final[tuple[ConcreteScope, ...]] = (
    CELL_SCOPE,
    NODE_SCOPE,
    ORG_SCOPE,
)


class ScopeRegistry:
    """Operator-extensible registry of substrate scopes.

    Construct with no arguments to get a registry pre-populated with
    the default ``cell`` / ``node`` / ``org`` triple. Operators MAY
    register additional scopes; spec invariants are enforced at
    :meth:`register` time.
    """

    def __init__(self) -> None:
        self._scopes: dict[str, SubstrateScope] = {}
        for scope in DEFAULT_SCOPES:
            # Bypass register()'s parent-existence check during
            # bootstrap because the defaults reference each other in
            # cell → node → org order. We insert in that order so each
            # subsequent insert sees its parent already present.
            if (
                scope.parent_name is not None
                and scope.parent_name not in self._scopes
            ):
                # ORG before NODE before CELL — but we iterate CELL
                # first, so the very first cell insertion lacks the
                # node parent. Fall back to direct insert during the
                # bootstrap loop; cycle / parent validation re-runs on
                # operator-driven register() calls below.
                self._scopes[scope.name] = scope
                continue
            self._scopes[scope.name] = scope

    # ── reads ─────────────────────────────────────────────────

    def get(self, name: str) -> SubstrateScope:
        """Return the scope by ``name``; raise :class:`KeyError` if absent."""
        if name not in self._scopes:
            raise KeyError(
                f"scope {name!r} not registered; "
                f"known: {sorted(self._scopes)}"
            )
        return self._scopes[name]

    def try_get(self, name: str) -> Optional[SubstrateScope]:
        """Return the scope by ``name`` or ``None`` if absent."""
        return self._scopes.get(name)

    def names(self) -> Iterable[str]:
        """All registered scope names, in registration order."""
        return tuple(self._scopes.keys())

    def parents_of(self, name: str) -> tuple[str, ...]:
        """Ordered parent chain — immediate parent first.

        Returns the empty tuple when ``name`` is a top-level scope.
        Raises :class:`KeyError` if ``name`` itself is not registered.
        """
        if name not in self._scopes:
            raise KeyError(
                f"scope {name!r} not registered; "
                f"known: {sorted(self._scopes)}"
            )
        chain: list[str] = []
        current: Optional[str] = self._scopes[name].parent_name
        # Spec invariant § 3 step 3: registration prevents cycles, so
        # the walk terminates without a guard.
        while current is not None:
            chain.append(current)
            parent_scope = self._scopes.get(current)
            if parent_scope is None:
                # Defensive — should be unreachable because register()
                # rejects orphan parents. Bail rather than infinite-
                # loop if invariants were broken externally.
                break
            current = parent_scope.parent_name
        return tuple(chain)

    # ── writes ────────────────────────────────────────────────

    def register(self, scope: SubstrateScope) -> None:
        """Add a new scope. Enforces spec § 2.3 invariants.

        Raises :class:`ValueError` for:
        * duplicate ``name``;
        * missing ``parent_name`` (the parent must already be
          registered);
        * a parent chain that would close a cycle through the new
          scope.
        """
        name = scope.name
        if not _VALID_NAME_RE.fullmatch(name):
            raise ValueError(
                "scope name must match [a-z0-9_]+; got "
                f"{name!r}"
            )
        if name in self._scopes:
            raise ValueError(
                f"scope {name!r} already registered"
            )
        if scope.parent_name is not None:
            if scope.parent_name not in self._scopes:
                raise ValueError(
                    f"scope {name!r}'s parent_name "
                    f"{scope.parent_name!r} is not registered"
                )
            if self._would_close_cycle(name, scope.parent_name):
                raise ValueError(
                    f"registering scope {name!r} with parent "
                    f"{scope.parent_name!r} would close a cycle"
                )
        self._scopes[name] = scope

    # ── internals ─────────────────────────────────────────────

    def _would_close_cycle(
        self, new_name: str, parent_name: str
    ) -> bool:
        """Detect whether adding ``new_name`` → ``parent_name`` would
        introduce a cycle.

        Walks the prospective parent chain and returns ``True`` if
        ``new_name`` appears anywhere in it.
        """
        current: Optional[str] = parent_name
        seen: set[str] = set()
        while current is not None:
            if current == new_name:
                return True
            if current in seen:
                # Pre-existing cycle (shouldn't happen if invariants
                # held). Treat as cycle-positive — registration would
                # not improve the situation.
                return True
            seen.add(current)
            current = (
                self._scopes[current].parent_name
                if current in self._scopes
                else None
            )
        return False


def default_registry() -> ScopeRegistry:
    """Convenience: a fresh registry with the default scopes only."""
    return ScopeRegistry()


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
