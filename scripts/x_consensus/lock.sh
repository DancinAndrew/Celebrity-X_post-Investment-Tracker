# 共用鎖：排程（run.sh）與回填（backfill.sh）共用同一份 pending.md 與答案檔，
# 同時跑會互相覆蓋——A 匯出的待辦被 B 蓋掉，A 的答案驗證就對不上。
# mkdir 是原子操作；持有者行程已不存在時視為殘留鎖，自動清掉。
acquire_lock() {   # $1=鎖名
  local d="$XC_LOCK_DIR/$1"
  mkdir -p "$XC_LOCK_DIR"
  if mkdir "$d" 2>/dev/null; then echo $$ > "$d/pid"; return 0; fi
  local pid; pid=$(cat "$d/pid" 2>/dev/null)
  if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
    rm -rf "$d"
    mkdir "$d" 2>/dev/null && echo $$ > "$d/pid" && return 0
  fi
  return 1
}
release_lock() { rm -rf "$XC_LOCK_DIR/$1"; }
wait_lock() {      # $1=鎖名 $2=最多等幾秒
  local waited=0
  until acquire_lock "$1"; do
    sleep 20; waited=$((waited + 20))
    [ "$waited" -ge "${2:-1800}" ] && return 1
  done
}
