#!/bin/bash
# 歷史回填後的分類與揭露抽取：分批、由新到舊、有上限、沒進度就停。
#
#   bash backfill.sh                 # 抓取已完成後執行
#   MAX_BATCHES=10 bash backfill.sh  # 限制這次最多跑幾批，控制額度
#
# 抓取（fetch.sh BACKFILL_DAYS=365）只花時間不花額度；這一步才花額度，
# 所以預設只送含股票代碼或常見公司名的貼文，並先補最近的歷史。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
DATA="${XC_DATA_DIR:-$HERE/.data}"
export XC_DATA_DIR="$DATA"
BATCH="${BATCH:-60}"
MAX_CHARS="${MAX_CHARS:-30000}"   # 每批字數上限，比篇數更能控制單批耗時
# 所有批次使用 Codex，保留原文，不截斷。
export XC_CODEX_MODEL="${XC_CODEX_MODEL:-gpt-6.1-sol}"
# 依帳號分成互斥的 worker 平行跑，保證不會兩個 session 分類同一篇
WORKERS=(${WORKERS:-"jukan05" "aleabitoreddit" "michaelsikand,zephyr_z9" "KawzInvests,ren_stocks,octopusycc"})
export XC_CODEX_TIMEOUT="${XC_CODEX_TIMEOUT:-1200}"
MAX_BATCHES="${MAX_BATCHES:-40}"
LOG="$DATA/backfill.log"
export XC_LOCK_DIR="$DATA/locks"
source "$HERE/lock.sh"
log() { printf '%s | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG"; }

count() { grep -o '匯出 [0-9]*' | tr -cd '0-9'; }

loop() {   # $1=名稱 $2=基本 export 指令（不含批次參數） $3=auto 腳本 $4=鎖名
  local name="$1" base="$2" runner="$3" lock="$4" prev=-1 stuck=0
  local batch_cmd="$base --limit $BATCH --max-chars $MAX_CHARS"
  for i in $(seq 1 "$MAX_BATCHES"); do
    # 每批才拿鎖、做完就放，讓每 6 小時的排程可以插隊處理最新貼文
    wait_lock "$lock" 3600 || { log "$name 等不到鎖（排程卡住？），停止"; return; }
    local n; n=$(eval "$batch_cmd" 2>&1 | count); n=${n:-0}
    if [ "$n" -eq 0 ]; then release_lock "$lock"; log "$name 完成"; return; fi
    log "$name 第 $i 批：$n 篇"
    bash "$HERE/$runner" >>"$LOG" 2>&1
    # 用不限批次的 export 算剩餘量（會重寫 pending.md，但這批已處理完，無妨）
    local left; left=$(eval "$base" 2>&1 | count); left=${left:-0}
    release_lock "$lock"
    log "$name 剩 $left 篇"
    if [ "$prev" -ge 0 ] && [ "$left" -ge "$prev" ]; then
      stuck=$((stuck + 1))
      log "$name 沒有進度，第 $stuck 次"
      [ "$stuck" -ge 2 ] && { log "$name 連續兩批沒進度，停止。檢查 ${runner%.sh}.log"; return; }
    else
      stuck=0
    fi
    prev=$left
  done
  log "$name 達到批次上限 $MAX_BATCHES，剩下的下次再跑"
}

log "=== 回填開始 ==="
python3 -m x_consensus.ingest >>"$LOG" 2>&1 && log "ingest 完成"

stance_worker() {   # $1=slot $2=帳號（逗號分隔）
  local slot="$1" handles="$2" prev=-1 stuck=0
  local pend="$DATA/handoff/pending_$slot.md"
  local base="python3 -m x_consensus.handoff export --version codex-session/v1 --hours 100000 --types opinion --require-candidates --handles $handles"
  for i in $(seq 1 "$MAX_BATCHES"); do
    local n; n=$($base --limit "$BATCH" --max-chars "$MAX_CHARS" --out "$pend" 2>&1 | count); n=${n:-0}
    if [ "$n" -eq 0 ]; then log "[$slot $handles] 完成"; return; fi
    XC_SLOT="$slot" bash "$HERE/classify_auto.sh" >/dev/null 2>&1
    # 算剩餘量寫到另一個檔，不覆蓋正在用的待分類檔
    local left; left=$($base --out "$pend.count" 2>&1 | count); left=${left:-0}
    log "[$slot $handles] 第 $i 批 $n 篇，剩 $left 篇"
    if [ "$prev" -ge 0 ] && [ "$left" -ge "$prev" ]; then
      stuck=$((stuck + 1))
      [ "$stuck" -ge 2 ] && { log "[$slot $handles] 連續兩批沒進度，停止。看 classify_auto_$slot.log"; return; }
    else
      stuck=0
    fi
    prev=$left
  done
  log "[$slot $handles] 達到批次上限"
}

log "立場分類：${#WORKERS[@]} 個 worker 平行，模型 $XC_CODEX_MODEL"
slot=0
for handles in "${WORKERS[@]}"; do
  slot=$((slot + 1))
  stance_worker "w$slot" "$handles" &
done
wait
log "立場分類全部 worker 結束"

# 揭露帳號的回填抓取可能比立場分類晚完成，這裡再 ingest 一次把新抓到的原始檔補進來
python3 -m x_consensus.ingest >>"$LOG" 2>&1 && log "ingest（揭露抽取前）完成"

loop "揭露抽取" \
  "python3 -m x_consensus.disclosure export --version codex-session/disc-v2 --hours 100000 --require-candidates" \
  "disclosure_auto.sh" disclosure

if command -v uv >/dev/null 2>&1; then
  uv run --project "$HERE" python -m x_consensus.prices >>"$LOG" 2>&1
  uv run --project "$HERE" --offline python -m x_consensus.disclosure score >>"$LOG" 2>&1
  python3 -m x_consensus.aggregate >>"$LOG" 2>&1
  uv run --project "$HERE" --offline python -m x_consensus.dashboard >>"$LOG" 2>&1
fi
log "=== 回填結束 ==="
