# Multi-scale observation

> **Status:** v0.2.0-draft. Subject to revision before the first tagged release.

This specification defines the **multi-scale observation** Protocol: how a conforming implementation describes the *scope* at which a substrate-state observation is taken, and how scopes compose into parent/child hierarchies so observations can be aggregated upward (cell → node → org) or extended downward into deployment-specific scales (community → household → individual, for civic deployments; squad → platoon → battalion, for tactical).

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) when, and only when, they appear in all capitals.

## 1. Motivation

Substrate condition #3 (multi-scale alignment architecture) requires that an implementation reason about cells / nodes / orgs (and analogues) as first-class scales, *not* as ad-hoc string tags on observations. Without a Protocol, every implementation chooses its own scope vocabulary; aggregating observations across two implementations means writing pairwise glue.

The `substrate.multiscale.aggregator` reference impl hard-codes the cell/node/org enum. The pluggable scope registry generalises this so:

- the default cell/node/org scopes remain the canonical baseline;
- operators MAY extend the registry with deployment-specific scopes (HOUSEHOLD / COMMUNITY / SQUAD / etc.);
- aggregation up the parent chain works uniformly across both default and operator-registered scopes.

## 2. Vocabulary

### 2.1 Scope

A conforming implementation MUST expose a `SubstrateScope` runtime-checkable Protocol with at minimum:

- `name: str` (non-empty, lowercase, ASCII; `[a-z0-9_]+`): the canonical wire form.
- `display_name: str` (non-empty): human-readable form.
- `parent_name: Optional[str]`: `None` for top-level scopes; otherwise the `name` of the immediate parent scope (which MUST itself be a registered scope).
- `aggregating: bool`: `True` if observations at this scope aggregate from children; `False` for terminal/leaf scopes (the canonical CELL scope is a leaf; observations originate here).

The Protocol MUST be `runtime_checkable` so host applications can verify their concrete scope classes conform.

### 2.2 Default scopes

A conforming implementation MUST ship three default scopes:

| `name` | `display_name` | `parent_name` | `aggregating` |
| --- | --- | --- | --- |
| `cell` | `Cell` | `node` | `False` |
| `node` | `Node` | `org` | `True` |
| `org` | `Org` | `None` | `True` |

The serialised `name` values are canonical wire / storage form. Implementations MUST emit and accept exactly these strings; alternative casings or abbreviations are **NOT** conformant.

### 2.3 Scope registry

A conforming implementation MUST expose a `ScopeRegistry` (or equivalent) with:

- `register(scope)`: adds a new scope. MUST raise `ValueError` if `scope.name` is already registered, or if `scope.parent_name` is not in the registry.
- `get(name) → SubstrateScope`: returns the scope by name. MUST raise `KeyError` if absent.
- `try_get(name) → Optional[SubstrateScope]`: non-raising variant.
- `names() → Iterable[str]`: all registered scope names.
- `parents_of(name) → tuple[str, ...]`: the ordered parent chain (immediate parent first, top-level scope last; empty tuple if `name` is itself top-level).

Implementations MUST construct each fresh registry pre-populated with the three default scopes (§ 2.2).

### 2.4 Extension API

A conforming implementation MUST permit operators to register additional scopes at runtime, subject to the constraints in § 2.3. The registry MUST detect cycles in the parent chain at `register()` time and raise `ValueError` if registration would create one.

Implementations MUST forbid mutating a previously-registered scope's `parent_name` after registration. Scope identity is immutable once registered. Replacing a registered scope requires a fresh registry instance.

## 3. Parent-chain semantics

A conforming implementation MUST guarantee:

1. `parents_of(name)` returns the chain in *upward* order: immediate parent first.
2. `parents_of(top_level_name)` returns the empty tuple.
3. `parents_of(name)` terminates (no infinite loop) for every registered name, by virtue of cycle prevention at registration.
4. For every registered scope `s` with `s.parent_name is not None`, `s.parent_name` is itself a registered scope at `parents_of(s.name)[0]`.

## 4. Conformance

A conforming implementation MUST pass every probe in `../conformance/probes/` whose filename begins with `multi-scale__`.

## 5. Reference implementation

In the Python reference implementation:

- Registry, types, and Protocol: [`substrate.multiscale.scope_registry`](../python/src/substrate/multiscale/scope_registry.py)
- Conformance handler: registered in [`substrate.conformance.probe_runner.default_handlers`](../python/src/substrate/conformance/probe_runner.py)

Both multi-scale primitives live in the `substrate.multiscale` package: `substrate.multiscale.aggregator` is the cell→node→org aggregator, and `substrate.multiscale.scope_registry` is the pluggable scope registry. The two compose: the aggregator's CELL/NODE/ORG names align with the registry's defaults.

## 6. Cross-references

- `operating-mode.md` § 4 (`SubstrateMetadata` records carry an entity-scope; the scope name MUST come from a registered scope).
- `runaway-power-prevention.md` (Mechanism 5's substrate-scoped transitions assume a stable scope vocabulary).

## 7. Non-goals

- The spec does NOT define a per-scope substrate-mode threshold: thresholds are operator-tunable per `operating-mode.md` § 3.
- The spec does NOT prescribe a JSON or proto serialisation; the canonical `name` field IS the wire form.
- The spec does NOT define cross-implementation interoperability of operator-registered scopes: two implementations can each register a "household" scope but the spec makes no claim that they mean the same thing.
