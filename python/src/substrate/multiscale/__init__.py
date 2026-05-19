"""Multi-scale aggregation primitives.
condition #3 — **Multi-scale alignment architecture** (cells / nodes
/ orgs, mirroring cells / tissues / organs).

the host application entity hierarchy
========================

* **Cell** — physical, replicable instance. Identified by ``cell_id``
  (unique to the physical instance). Belongs to exactly one node via
  ``node_id``. Holds its own state (DBs, volumes). Replication,
  leasing, placement, and topology all operate at this scale.
* **Node** — logical, persistent construct. Identified by ``node_id``
  (cryptographic identity). Aggregates 1..N cells (which may span
  cloud / region / service-group). The substrate "face" peer entities
  see; the persistent identity that survives cell replacement.
* **Org** — optional multi-node aggregate. The organizational scale
  at which substrate-aligned-mode emerges as a civilizational
  property (per substrate condition #8).

Substrate-state intelligence exists at each scale: individual cells
have their own alignment; nodes have emergent aggregate alignment;
orgs have emergent civilizational alignment. The biology analogy:
cells → tissues → organism.
"""
