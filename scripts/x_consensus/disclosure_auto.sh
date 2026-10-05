#!/bin/bash
# Codex disclosure extraction; validated separately from stock stance.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
DATA="${XC_DATA_DIR:-$HERE/.data}"
export XC_DATA_DIR="$DATA"
mkdir -p "$DATA"
python3 -m x_consensus.auto_analysis disclosure --pending "$DATA/disclosure/pending.md" 2>&1 | tee -a "$DATA/disclosure_auto.log"
