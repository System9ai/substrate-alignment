"""substrate-alignment — reference Python implementation.

substrate-alignment is an open standard, reference implementation, and
machine-checkable conformance suite for primitives used in multi-entity
agent systems. This package is one conforming implementation; the
language-neutral specifications live alongside it, in the ``spec/``
directory of the source repository.

Currently a bootstrap stub: the primitive surface (gates, classifiers,
audit-chain types, drift signals, halt-and-escalate protocol) is being
ported in subsequent releases. See the project ``CHANGELOG.md`` for
progress.

Project home: https://github.com/System9ai/substrate-alignment
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0.dev0"
