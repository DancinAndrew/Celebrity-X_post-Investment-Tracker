#!/bin/bash
# X 觀點共識追蹤器 —— 每日一鍵執行：抓取 → 正規化 → 分類 → 產出報告
#
#   bash scripts/x_consensus/run.sh
#
# 每個階段都是冪等的，中途失敗可以直接重跑整條。
set -uo pipefail
FAILED=0

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
# 24 小時排程：08 點那班用 26 小時窗口對帳補漏，其餘班次用 10 小時做增量。
# 全部階段冪等，重疊抓取只會被 post_id 去重。
if [ -z "${HOURS:-}" ]; then
  if [ "$(date +%H)" = "08" ]; then HOURS=26; else HOURS=10; fi
fi
export XC_DATA_DIR="${XC_DATA_DIR:-$HERE/.data}"
LOG="$XC_DATA_DIR/run.log"
mkdir -p "$XC_DATA_DIR"
export XC_LOCK_DIR="${XC_DATA_DIR:-$HERE/.data}/locks"
source "$HERE/lock.sh"
# uv 預設每次都會連 PyPI 檢查建置依賴；Mac 剛睡醒沒網路時整段就失敗，
# 連不需要網路的儀表板都產不出來。產出階段一律離線跑。
UVRUN=(uv run --project "$HERE" --offline)
ONLINE=1
curl -s -o /dev/null --max-time 10 https://x.com/ || ONLINE=0

say() { printf '\n=== %s === %s\n' "$1" "$(date '+%H:%M:%S')" | tee -a "$LOG"; }

say "1/6 抓取（ego-browser，需要 ego lite 已登入 X）"
if [ "$ONLINE" = "0" ]; then
  echo "沒有網路（連不上 x.com），略過抓取；後續階段用既有資料執行。" | tee -a "$LOG"
  FAILED=1
elif ! HOURS="$HOURS" bash "$HERE/fetch.sh" 2>&1 | tee -a "$LOG"; then
  echo "抓取失敗；後續階段仍會用既有資料執行。" | tee -a "$LOG"
  FAILED=1
fi

say "2/6 正規化進 SQLite"
python3 -m x_consensus.ingest 2>&1 | tee -a "$LOG" || { echo "正規化失敗，停止本輪。" | tee -a "$LOG"; exit 1; }

say "3/6 立場分類"
# MODE=mentions 保留提及統計；其他模式均使用 Codex，不呼叫 Claude/API。
MODE="${MODE:-auto}"
if [ "$MODE" = "mentions" ]; then
  python3 -m x_consensus.mentions 2>&1 | tee -a "$LOG" || FAILED=1
elif acquire_lock handoff; then
  if python3 -m x_consensus.handoff export --version codex-session/v1 --hours "$HOURS" 2>&1 | tee -a "$LOG"; then
    if [ "${XC_AUTO_CLASSIFY:-1}" = "1" ] && [ "$ONLINE" = "1" ]; then
      bash "$HERE/classify_auto.sh" 2>&1 | tee -a "$LOG" || FAILED=1
    else
      echo "待分類檔已備妥；本輪未完成分類（離線或自動分類關閉）。" | tee -a "$LOG"
      FAILED=1
    fi
  else
    FAILED=1
  fi
  release_lock handoff
else
  echo "分類佇列正被使用，本輪未完成分類。" | tee -a "$LOG"
  FAILED=1
fi

say "4/6 抽取揭露事件"
if acquire_lock disclosure; then
  if python3 -m x_consensus.disclosure export --version codex-session/disc-v2 --hours 72 2>&1 | tee -a "$LOG"; then
    if [ "${XC_AUTO_CLASSIFY:-1}" = "1" ] && [ "$ONLINE" = "1" ]; then
      bash "$HERE/disclosure_auto.sh" 2>&1 | tee -a "$LOG" || FAILED=1
    else
      echo "揭露待辦已備妥；本輪未完成抽取。" | tee -a "$LOG"
      FAILED=1
    fi
  else
    FAILED=1
  fi
  release_lock disclosure
else
  echo "揭露佇列正被使用，本輪未完成抽取。" | tee -a "$LOG"
  FAILED=1
fi

say "5/6 抓價格並重算交易者權重"
if command -v uv >/dev/null 2>&1; then
  if [ "$ONLINE" = "1" ]; then
    "${UVRUN[@]}" python -m x_consensus.prices 2>&1 | grep -v '^\[' | tee -a "$LOG" || FAILED=1
  else
    echo "沒有網路，略過抓價格；權重用既有價格重算。" | tee -a "$LOG"
  fi
  "${UVRUN[@]}" python -m x_consensus.disclosure score 2>&1 | tee -a "$LOG" || FAILED=1
else
  echo "沒有 uv，跳過價格與權重（需要 yfinance）" | tee -a "$LOG"
fi

say "6/6 產出報告與儀表板"
python3 -m x_consensus.aggregate 2>&1 | tee -a "$LOG" || FAILED=1
if command -v uv >/dev/null 2>&1; then
  "${UVRUN[@]}" python -m x_consensus.dashboard 2>&1 | tee -a "$LOG" || FAILED=1
fi

if [ "$FAILED" -ne 0 ]; then
  echo "本輪部分階段未完成；詳見 run.log 與 Codex 狀態檔。" | tee -a "$LOG"
fi
exit "$FAILED"
