#!/bin/bash
# X 觀點共識追蹤器 —— 每日抓取器（路線 D：ego-browser 沿用使用者登入態）
#
# 做法：注入 fetch/XHR 攔截器，捕捉 x.com 自己發出的 GraphQL 時間軸回應，
# 而不是解析畫面 DOM。這樣可以拿到長文全文（note_tweet）、轉貼原文、
# 精確時間戳與 tweet id，且不受虛擬捲動（畫面外節點被移除）影響。
#
# 用法：
#   bash scripts/x_consensus/fetch.sh                     # 抓最近 26 小時
#   HOURS=48 bash scripts/x_consensus/fetch.sh            # 補漏
#   ONLY=unusual_whales bash scripts/x_consensus/fetch.sh # 只抓單一帳號
#
# 輸出：.data/raw/<UTC日期>/<handle>__<n>.json 與 .data/runs/<run_id>.json
#
# 注意：ego-browser 的 Node 執行環境不繼承本 shell 的環境變數，cwd 也是 /，
# 所以參數用「產生一段 const 前綴 + 靜態 JS 主體」的方式從 stdin 餵進去。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOURS="${HOURS:-26}"
ONLY="${ONLY:-}"
# 歷史回填：BACKFILL_DAYS=365 會一路往回捲到一年前（或時間軸到底／被限流為止）。
# 平常排程不設，只抓最近 HOURS 小時。
BACKFILL_DAYS="${BACKFILL_DAYS:-0}"
TYPES="${TYPES:-}"          # 只抓這些帳號型別，逗號分隔，例：opinion,trade_disclosure
if [ "$BACKFILL_DAYS" != "0" ]; then
  MAX_SCROLLS="${MAX_SCROLLS:-250}"
else
  MAX_SCROLLS="${MAX_SCROLLS:-12}"
fi

DATA="${XC_DATA_DIR:-$HERE/.data}"
mkdir -p "$DATA/raw" "$DATA/runs"
export XC_LOCK_DIR="$DATA/locks"
source "$HERE/lock.sh"
if ! acquire_lock fetch; then
  echo "X 收集正由另一輪執行，本輪未抓取；既有資料與分頁保留。" >&2
  exit 1
fi
trap 'release_lock fetch' EXIT

{
  # Serialize shell inputs as JSON: spaces, quotes, and backslashes remain data.
  python3 - "$HERE" "$DATA" "$HOURS" "$ONLY" "$MAX_SCROLLS" "$BACKFILL_DAYS" "$TYPES" "${XC_CUTOFF_UTC:-}" "${XC_BEFORE:-}" <<'PYCONFIG'
import json, sys
names = ['HOME','DATA','HOURS','ONLY','MAX_SCROLLS','BACKFILL_DAYS','TYPES','CUTOFF_UTC','BEFORE']
for name, value in zip(names, sys.argv[1:]):
    if name in {'HOURS','MAX_SCROLLS','BACKFILL_DAYS'}:
        value = int(value)
        if value < 0:
            raise SystemExit(f'{name} must not be negative')
    print(f'const XC_{name} = {json.dumps(value)}')
PYCONFIG
  cat <<'___EGO_END___'
import fs from 'node:fs'
import path from 'node:path'

await useOrCreateTaskSpace('x consensus daily fetch')

const cfg = JSON.parse(fs.readFileSync(path.join(XC_HOME, 'accounts.json'), 'utf8'))
const wantTypes = XC_TYPES ? XC_TYPES.split(',').map(x => x.trim()) : null
const accounts = cfg.accounts
  .filter(a => a.enabled !== false)
  .filter(a => !XC_ONLY || a.handle.toLowerCase() === XC_ONLY.toLowerCase())
  .filter(a => !wantTypes || wantTypes.includes(a.account_type))

const runStarted = new Date()
const runId = runStarted.toISOString().replace(/[:.]/g, '-')
const dayDir = path.join(XC_DATA, 'raw', runStarted.toISOString().slice(0, 10))
fs.mkdirSync(dayDir, { recursive: true })
const cutoffMs = XC_CUTOFF_UTC ? Date.parse(XC_CUTOFF_UTC) : XC_BACKFILL_DAYS > 0
  ? runStarted.getTime() - XC_BACKFILL_DAYS * 86400 * 1000
  : runStarted.getTime() - XC_HOURS * 3600 * 1000
if (!Number.isFinite(cutoffMs)) throw new Error('XC_CUTOFF_UTC is invalid')
if (XC_BEFORE && !/^\d{4}-\d{2}-\d{2}$/.test(XC_BEFORE)) throw new Error('XC_BEFORE must be YYYY-MM-DD')
// 回填時時間軸載入較慢，連續幾頁沒新資料才判定到底
const STAGNANT_LIMIT = XC_BACKFILL_DAYS > 0 ? 6 : 3
// 檔名帶上本次執行時間，同一天跑四次不會互相覆蓋（原本同名檔案會被後一次蓋掉，
// 違反「原始 JSON 永久保留」）
const runStamp = runStarted.toISOString().slice(11, 19).replace(/:/g, '')

// ── 攔截器：在每個新 document 的頁面腳本之前執行 ──────────────────────────
const hookSource = `
(() => {
  if (window.__xcap) return;
  window.__xcap = { hits: [] };
  const want = (u) => typeof u === 'string' && u.includes('/i/api/graphql/');
  const push = (url, text, status) => { try { window.__xcap.hits.push({ url, text, status }); } catch (e) {} };
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await origFetch.apply(this, args);
    try {
      const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url);
      if (want(url)) { res.clone().text().then(t => push(url, t, res.status)).catch(() => {}); }
    } catch (e) {}
    return res;
  };
  const oOpen = XMLHttpRequest.prototype.open, oSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u, ...r) { this.__u = u; return oOpen.call(this, m, u, ...r); };
  XMLHttpRequest.prototype.send = function (...a) {
    this.addEventListener('load', () => { try { if (want(this.__u)) push(this.__u, this.responseText, this.status); } catch (e) {} });
    return oSend.apply(this, a);
  };
})();
`

// 取出「上次之後新進來的」時間軸回應：回傳原文與統計後清空緩衝。
// 舊版每捲一次就把全部回應重新解析一遍，平常只捲幾頁無感，
// 回填捲兩百頁時會變成平方級的重複解析，也會把整包回應堆在頁面記憶體裡。
// 置頂貼文要排除：它可能是幾個月前的，不排除的話第一頁就會誤判「已經夠舊」。
const drainSource = String.raw`((expectedHandle) => {
  const all = window.__xcap ? window.__xcap.hits : [];
  const hits = all.filter(h => /Timeline|UserTweets/.test(h.url));
  if (window.__xcap) window.__xcap.hits = [];
  let oldest = null, newest = null;
  const errors = [], ids = [];
  for (const h of hits) {
    if (h.status === 429) errors.push('HTTP 429 rate limit');
    let d; try { d = JSON.parse(h.text); } catch (e) { errors.push(h.text.trim() ? 'non-JSON timeline response' : 'empty timeline response'); continue; }
    if (d.errors) { for (const e of d.errors) errors.push(e.message || String(e.code || 'unknown')); }
    const stack = [d];
    while (stack.length) {
      const cur = stack.pop();
      if (!cur || typeof cur !== 'object') continue;
      if (Array.isArray(cur)) { for (const v of cur) stack.push(v); continue; }
      if (Array.isArray(cur.instructions)) {
        for (const ins of cur.instructions) {
          const isPin = ins.type === 'TimelinePinEntry';
          const ents = ins.entries || (ins.entry ? [ins.entry] : []);
          for (const e of ents) {
            if (!e || isPin) continue;
            // Conversation entries contain nested items. Only count the requested
            // author's top-level tweets, never quoted tweets or recommendations.
            const items = [e.content || {}];
            while (items.length) {
              const item = items.pop();
              if (!item || typeof item !== 'object') continue;
              if (item.tweet_results && item.tweet_results.result) {
                let tr = item.tweet_results.result;
                if (tr.__typename === 'TweetWithVisibilityResults') tr = tr.tweet || {};
                const user = (((tr.core || {}).user_results || {}).result || {});
                const handle = (user.core || {}).screen_name || (user.legacy || {}).screen_name || '';
                const leg = tr.legacy;
                if (!leg || !leg.created_at || handle.toLowerCase() !== expectedHandle.toLowerCase()) continue;
                const t = Date.parse(leg.created_at);
                if (!Number.isFinite(t)) continue;
                ids.push(leg.id_str);
                if (oldest === null || t < oldest) oldest = t;
                if (newest === null || t > newest) newest = t;
                continue;
              }
              for (const value of Object.values(item)) {
                if (value && typeof value === 'object') items.push(value);
              }
            }
          }
        }
      }
      for (const k in cur) { const v = cur[k]; if (v && typeof v === 'object') stack.push(v); }
    }
  }
  return { texts: hits.map(h => h.text), ids, oldest, newest, errors: errors.slice(0, 3) };
})`

const jitter = (a, b) => a + Math.random() * (b - a)

// 回填用獨立的 task space，跟排程的每日抓取互不搶控制權
await useOrCreateTaskSpace(XC_BACKFILL_DAYS > 0 ? 'x consensus backfill' : 'x consensus daily fetch')
await openOrReuseTab('https://x.com/home', { wait: true, timeout: 40 })
const hook = await cdp('Page.addScriptToEvaluateOnNewDocument', { source: hookSource })

const report = { run_id: runId, started_at_utc: runStarted.toISOString(), hours: XC_HOURS,
                 backfill_days: XC_BACKFILL_DAYS, cutoff_utc: new Date(cutoffMs).toISOString(), before: XC_BEFORE || null, accounts: [] }

for (const acct of accounts) {
  const rec = { handle: acct.handle, status: 'failed', payloads: 0, tweets: 0, scrolls: 0,
                oldest: null, newest: null, note: null, stop_reason: null }
  try {
    const query = `from:${acct.handle} since:${new Date(cutoffMs).toISOString().slice(0, 10)} until:${XC_BEFORE}`
    const url = XC_BEFORE ? 'https://x.com/search?q=' + encodeURIComponent(query) + '&f=live' : 'https://x.com/' + acct.handle
    await gotoAndWait(url, { timeout: 45, settle: 3 })
    await wait(jitter(3, 5))

    const seenIds = new Set()
    const errs = []
    let stagnant = 0, fileNo = 0, oldest = null, newest = null
    for (let i = 0; i <= XC_MAX_SCROLLS; i++) {
      const got = await js(`${drainSource}(${JSON.stringify(acct.handle)})`)
      rec.scrolls = i
      for (const text of got.texts) {
        fs.writeFileSync(path.join(dayDir,
          `${acct.handle}__${runStamp}__${String(fileNo++).padStart(3, '0')}.json`), text)
      }
      const before = seenIds.size
      for (const id of got.ids) seenIds.add(id)
      if (got.oldest !== null && (oldest === null || got.oldest < oldest)) oldest = got.oldest
      if (got.newest !== null && (newest === null || got.newest > newest)) newest = got.newest
      for (const e of got.errors) if (!errs.includes(e)) errs.push(e)

      if (errs.some(e => /rate.?limit|too many requests/i.test(e))) { rec.stop_reason = 'rate_limit'; break }
      if (errs.some(e => /empty timeline response|non-JSON timeline response/i.test(e))) { rec.stop_reason = 'invalid_response'; break }
      if (oldest !== null && oldest < cutoffMs) { rec.stop_reason = 'cutoff'; break }
      if (seenIds.size === before) { if (++stagnant >= STAGNANT_LIMIT) { rec.stop_reason = 'stagnant'; break } }  // 時間軸到底
      else { stagnant = 0 }
      if (i === XC_MAX_SCROLLS) { rec.stop_reason = 'max_scrolls'; break }
      if (XC_BACKFILL_DAYS > 0 && i > 0 && i % 25 === 0) {
        cliLog(`  … ${acct.handle} scroll ${i} tweets=${seenIds.size} oldest=${oldest ? new Date(oldest).toISOString().slice(0, 10) : '-'}`)
      }
      await scrollBy(4000)
      // 等待分頁請求真的回來，比固定 sleep 可靠；逾時就退回固定等待
      try { await waitForNetworkIdle({ timeout: 6 }) } catch (e) {}
      await wait(jitter(2, 3.5))
    }

    rec.payloads = fileNo
    rec.tweets = seenIds.size
    rec.oldest = oldest ? new Date(oldest).toISOString() : null
    rec.newest = newest ? new Date(newest).toISOString() : null
    rec.note = [errs.join(' | '), rec.stop_reason ? 'stop=' + rec.stop_reason : ''].filter(Boolean).join(' | ') || null

    // 狀態三分：抓不到任何貼文 = failed（帳號代號錯、被限流、或版面改版）；
    // 抓到但沒回溯到 cutoff = partial。partial 必須跟 ok 分開，否則
    // 「管線壞掉」在報告上會長得跟「今天沒發文」一模一樣。
    if (rec.tweets === 0) rec.status = 'failed'
    else if (['rate_limit', 'invalid_response', 'error'].includes(rec.stop_reason) || oldest === null || oldest >= cutoffMs) rec.status = 'partial'
    else rec.status = 'ok'
  } catch (err) {
    rec.stop_reason = 'error'
    rec.note = String(err && err.message ? err.message : err)
  }
  report.accounts.push(rec)
  cliLog([rec.status.padEnd(7), acct.handle.padEnd(16), 'tweets=' + String(rec.tweets).padStart(3),
          'pages=' + rec.payloads, 'scrolls=' + rec.scrolls,
          rec.oldest ? 'oldest=' + rec.oldest.slice(5, 16) : '',
          rec.note ? '| ' + rec.note : ''].join(' '))
  if (rec.stop_reason === 'rate_limit') break  // Stop the entire run; do not rotate accounts to evade limits.
  await wait(jitter(4, 8))   // 帳號之間放慢，降低觸發限流的機率
}

await cdp('Page.removeScriptToEvaluateOnNewDocument', { identifier: hook.identifier })
report.finished_at_utc = new Date().toISOString()
report.raw_dir = dayDir
fs.writeFileSync(path.join(XC_DATA, 'runs', runId + '.json'), JSON.stringify(report, null, 2))

const tally = (s) => report.accounts.filter(a => a.status === s).length
cliLog('')
cliLog('run ' + runId + '  ok=' + tally('ok') + ' partial=' + tally('partial') + ' failed=' + tally('failed'))
cliLog('raw -> ' + dayDir)
___EGO_END___
} | ego-browser nodejs
