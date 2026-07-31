#!/usr/bin/env bash
#
# Federal-procurement guard.
#
# The reference source code uses engineering vocabulary only. Internal-document
# references, development-plan phase numbers, personal-author attributions, and
# vendor-internal subsystem codenames must NOT appear anywhere in the Python
# source or test tree. The substrate-mathematical reasoning that motivates the
# design lives in docs/concepts/ and spec/ instead. This is what lets the source
# survive review by auditors with no patience for vendor-internal jargon.
#
# This script is the enforcement the CHANGELOG and preprint claim: it fails the
# build if any forbidden pattern is re-introduced. Run it locally before a PR:
#
#     scripts/federal_procurement_check.sh
#
# Exit 0 = clean; exit 1 = one or more forbidden references found (printed).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Only the reference implementation surface is under the federal-procurement
# test. Prose under docs/ and spec/ is allowed to carry the reasoning.
SCAN_DIRS=(python/src python/tests)

# Extended-regex patterns that must never appear in the scanned surface.
PATTERNS=(
  # Internal document / workspace paths.
  '\.claude/'
  'infinity-code'
  # Internal host module paths (the reference package is `substrate.*`).
  'app[./](services|core|common)'
  # Development-plan phase / part numbering (incl. mangled scrub scars).
  'Phase [0-9]'
  'Phase [IVXLC]+-[0-9]'
  'Part [IVXLC]+-[0-9]'
  'Part [0-9]'
  'Plan [0-9]'
  'Plan 3art'
  # Internal plan-section labels, e.g. "(J.6)".
  '\([A-Z]\.[0-9]+\)'
  # Personal-author attributions.
  'Per Trevor'
  "Trevor's articulation"
  'Trevor Kagin'
  # Vendor-internal subsystem codenames (System9 platform).
  '\b(MNEMOSYNE|ARGUS|NEXUS|MINERVA|COGNATE|HELIOS|OUTPOST|QUARTERMASTER|OVERWATCH|WARDEN|SENTINEL|ATELIER|MYRIAD|CRUCIBLE|CONSTELLATION|CHORUS|AGORA|CASCADE|CATALYST|ANVIL|CHRONICLE|VANTAGE|JANUS|VESTA|DRAGNET|EMISSARY|MANDATE|BULWARK|BEACON|SIGIL|KEYSTONE|MERIDIAN|CONDUIT|MOSAIC|ZENITH|PLIMSOLL|LOADOUT|CONCORD|STARFIRE|PHANTOM|FLUXDB|DRIFTNET|FOUNDRY|MUSTER|ENVOY|LECTOR|PANOPLY|SENSORIUM|SCAP)\b'
  # SCAP-style internal wave labels.
  'Wave [A-Z]\.[0-9]'
)

found=0
for pat in "${PATTERNS[@]}"; do
  # -n line numbers, -E extended regex, -r recursive, -I skip binary.
  if hits="$(grep -rInE "$pat" "${SCAN_DIRS[@]}" 2>/dev/null)"; then
    echo "FORBIDDEN pattern /$pat/ found:"
    echo "$hits"
    echo
    found=1
  fi
done

if [ "$found" -ne 0 ]; then
  echo "Federal-procurement check FAILED: remove the references above." >&2
  echo "Reasoning that motivates the design belongs in docs/concepts/ or spec/." >&2
  exit 1
fi

echo "Federal-procurement check passed: no internal references in ${SCAN_DIRS[*]}."
