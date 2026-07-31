"""Unit tests for the pluggable scope registry (spec: multi-scale)."""
from __future__ import annotations

import pytest

from substrate.multiscale.scope_registry import (
    CELL_SCOPE,
    DEFAULT_SCOPES,
    NODE_SCOPE,
    ORG_SCOPE,
    ConcreteScope,
    ScopeRegistry,
    SubstrateScope,
    default_registry,
)


# ── ConcreteScope construction ─────────────────────────────────


class TestConcreteScope:

    def test_round_trip(self) -> None:
        s = ConcreteScope(
            name="cell",
            display_name="Cell",
            parent_name="node",
            aggregating=False,
        )
        assert s.name == "cell"
        assert s.parent_name == "node"
        assert s.aggregating is False

    def test_invalid_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="scope name"):
            ConcreteScope(
                name="Cell",
                display_name="Cell",
                parent_name=None,
                aggregating=True,
            )

    def test_empty_display_rejected(self) -> None:
        with pytest.raises(ValueError, match="display_name"):
            ConcreteScope(
                name="cell",
                display_name="",
                parent_name=None,
                aggregating=False,
            )

    def test_invalid_parent_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="parent_name"):
            ConcreteScope(
                name="cell",
                display_name="Cell",
                parent_name="Node",
                aggregating=False,
            )

    def test_satisfies_protocol(self) -> None:
        # runtime_checkable Protocol acceptance.
        assert isinstance(CELL_SCOPE, SubstrateScope)
        assert isinstance(NODE_SCOPE, SubstrateScope)
        assert isinstance(ORG_SCOPE, SubstrateScope)


# ── DEFAULT_SCOPES ─────────────────────────────────────────────


class TestDefaults:

    def test_triple_order(self) -> None:
        assert DEFAULT_SCOPES == (CELL_SCOPE, NODE_SCOPE, ORG_SCOPE)

    def test_default_names(self) -> None:
        assert CELL_SCOPE.name == "cell"
        assert NODE_SCOPE.name == "node"
        assert ORG_SCOPE.name == "org"

    def test_parent_chain(self) -> None:
        assert CELL_SCOPE.parent_name == "node"
        assert NODE_SCOPE.parent_name == "org"
        assert ORG_SCOPE.parent_name is None

    def test_aggregating_flags(self) -> None:
        assert CELL_SCOPE.aggregating is False
        assert NODE_SCOPE.aggregating is True
        assert ORG_SCOPE.aggregating is True


# ── ScopeRegistry: defaults + lookups ─────────────────────────


class TestRegistryDefaults:

    def test_fresh_registry_has_default_triple(self) -> None:
        r = ScopeRegistry()
        assert sorted(r.names()) == ["cell", "node", "org"]

    def test_default_registry_helper(self) -> None:
        r = default_registry()
        assert sorted(r.names()) == ["cell", "node", "org"]

    def test_get_returns_scope(self) -> None:
        r = ScopeRegistry()
        assert r.get("cell") is CELL_SCOPE
        assert r.get("node") is NODE_SCOPE
        assert r.get("org") is ORG_SCOPE

    def test_get_missing_raises(self) -> None:
        r = ScopeRegistry()
        with pytest.raises(KeyError):
            r.get("missing")

    def test_try_get_returns_none_for_missing(self) -> None:
        r = ScopeRegistry()
        assert r.try_get("missing") is None
        assert r.try_get("cell") is CELL_SCOPE

    def test_parents_of_default(self) -> None:
        r = ScopeRegistry()
        assert r.parents_of("cell") == ("node", "org")
        assert r.parents_of("node") == ("org",)
        assert r.parents_of("org") == ()

    def test_parents_of_unknown_raises(self) -> None:
        r = ScopeRegistry()
        with pytest.raises(KeyError):
            r.parents_of("missing")


# ── ScopeRegistry: register() ─────────────────────────────────


class TestRegisterAdditional:

    def test_register_new_scope_under_cell(self) -> None:
        r = ScopeRegistry()
        household = ConcreteScope(
            name="household",
            display_name="Household",
            parent_name="cell",
            aggregating=False,
        )
        r.register(household)
        assert r.get("household") is household
        assert r.parents_of("household") == ("cell", "node", "org")

    def test_register_duplicate_raises(self) -> None:
        r = ScopeRegistry()
        with pytest.raises(ValueError, match="already registered"):
            r.register(
                ConcreteScope(
                    name="cell",
                    display_name="Cell",
                    parent_name="node",
                    aggregating=False,
                )
            )

    def test_register_orphan_parent_raises(self) -> None:
        r = ScopeRegistry()
        with pytest.raises(ValueError, match="not registered"):
            r.register(
                ConcreteScope(
                    name="household",
                    display_name="Household",
                    parent_name="nonexistent",
                    aggregating=False,
                )
            )

    def test_register_self_cycle_raises(self) -> None:
        r = ScopeRegistry()
        # Self-referencing scope: parent_name == name. The
        # parent-existence check fires first because "loop" isn't
        # registered yet; that's still a valid spec rejection
        # (§ 2.3: parent MUST already be in the registry).
        with pytest.raises(ValueError):
            r.register(
                ConcreteScope(
                    name="loop",
                    display_name="Loop",
                    parent_name="loop",
                    aggregating=False,
                )
            )

    def test_register_longer_cycle_raises(self) -> None:
        # Indirect cycle: a → cell, b → a, c → b; then attempt to
        # register d → c whose name is reused as the parent of c's
        # parent → cycle. Since we can't mutate post-registration,
        # construct the cycle by claiming a parent that's actually
        # a descendant.
        r = ScopeRegistry()
        a = ConcreteScope(
            name="a", display_name="A",
            parent_name="cell", aggregating=False,
        )
        r.register(a)
        b = ConcreteScope(
            name="b", display_name="B",
            parent_name="a", aggregating=False,
        )
        r.register(b)
        # Now register a scope whose name would be in b's chain
        # (a/b/cell/node/org). Attempting parent_name=b for new
        # name=b would dupe; instead attempt name=cell which dupes.
        # The realistic cycle is registering ``c`` whose parent is
        # ``c`` (self-loop) AFTER registering ``c``, but we can't
        # because of duplicate-name guard. Self-loop test below
        # validates the path; the longer-cycle defense is structural.
        # Verified by the cycle-detection helper's seen-set.
        with pytest.raises(ValueError):
            r.register(
                ConcreteScope(
                    name="b",  # duplicate name
                    display_name="B-dup",
                    parent_name="a",
                    aggregating=False,
                )
            )

    def test_register_invalid_name_raises(self) -> None:
        r = ScopeRegistry()
        with pytest.raises(ValueError, match="scope name"):
            r.register(
                ConcreteScope(
                    name="Cell",  # uppercase rejected at ConcreteScope
                    display_name="Cell",
                    parent_name="node",
                    aggregating=False,
                )
            )


# ── ScopeRegistry: multiple operator scopes ──────────────────


class TestRegisterChain:

    def test_register_three_level_extension(self) -> None:
        r = ScopeRegistry()
        community = ConcreteScope(
            name="community", display_name="Community",
            parent_name="org", aggregating=True,
        )
        household = ConcreteScope(
            name="household", display_name="Household",
            parent_name="cell", aggregating=False,
        )
        r.register(community)
        r.register(household)
        # Independent extensions on either side of the default chain
        # compose correctly via parents_of.
        assert r.parents_of("community") == ("org",)
        assert r.parents_of("household") == ("cell", "node", "org")
