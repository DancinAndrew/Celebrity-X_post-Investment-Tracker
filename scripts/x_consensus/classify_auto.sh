#!/bin/bash
# Codex inference returns JSON; the parent validates before writing SQLite.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
DATA="${XC_DATA_DIR:-$HERE/.data}"
export XC_DATA_DIR="$DATA"
SLOT="${XC_SLOT:-}"
PENDING="${XC_PENDING:-$DATA/handoff/pending${SLOT:+_$SLOT}.md}"
mkdir -p "$DATA"
python3 -m x_consensus.auto_analysis stance --pending "$PENDING" 2>&1 | tee -a "$DATA/classify_auto${SLOT:+_$SLOT}.log"
