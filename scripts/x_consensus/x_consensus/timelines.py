"""個股與交易者的全歷史時間線：資料組裝 + 不依賴 JavaScript 的 HTML 呈現。

為什麼不用 JS 彈窗：儀表板會在 Obsidian、Claude App 的檔案預覽等環境打開，
這些環境會擋掉 <script>。第一版用 <dialog> + JS 在本機瀏覽器測試正常，
使用者那邊卻完全點不開。改用原生 <details>/<summary>——展開收合是瀏覽器內建
行為，不需要任何腳本，在會擋 JS 的環境也能用。

時間的定義：
- 意見帳號的立場：用貼文時間。觀點就是在發文那一刻表達的。
- 交易者的揭露事件：用**交易日**（trade_date）排序與顯示，揭露日另外標註。
  「川普 2 月 2 日買進」這篇貼文 9 月 7 日才發，時間線應該畫在 2 月。
  沒有交易日（來源沒寫）時才退回揭露日，並標示「交易日未知」。
"""
from __future__ import annotations

import html
import sqlite3
from collections import defaultdict

STANCE_ZH = {"bullish": "看多", "bearish": "看空", "unclear": "僅提及"}
DIRECTION_ZH = {"buy": "買進", "sell": "賣出", "short": "放空", "cover": "回補"}
BULLISH_DIRECTIONS = {"buy", "cover"}


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


# ── 資料組裝 ──────────────────────────────────────────────────────────


def _dedupe_trades(rows: list[dict]) -> list[dict]:
    """同一筆交易常被好幾個帳號、好幾篇貼文重複報導。

    以 (交易者, 標的, 方向, 交易日或揭露日) 合併成一筆，保留最早的揭露日、
    累計報導次數、留下最多 3 個原文連結。不合併的話，Pelosi 一筆 Bloom Energy
    被三個帳號轉述，時間線上就會出現三次，看起來像她買了三次。
    """
    merged: dict[tuple, dict] = {}
    for r in rows:
        day = (r["trade_date"] or r["disclosed_at"] or "")[:10]
        key = (r["trader_key"], r["ticker"], r["direction"], day)
        if key not in merged:
            merged[key] = {**r, "reports": 1, "urls": [r["url"]] if r["url"] else []}
            continue
        m = merged[key]
        m["reports"] += 1
        if r["url"] and r["url"] not in m["urls"] and len(m["urls"]) < 3:
            m["urls"].append(r["url"])
        if r["disclosed_at"] and r["disclosed_at"] < (m["disclosed_at"] or "9999"):
            m["disclosed_at"] = r["disclosed_at"]
        if not m["amount"] and r["amount"]:
            m["amount"] = r["amount"]
        if not m["trade_date_text"] and r["trade_date_text"]:
            m["trade_date_text"] = r["trade_date_text"]
    return list(merged.values())


def load_trades(conn: sqlite3.Connection) -> list[dict]:
    rows = [
        {
            "trader_key": r["trader_key"], "who": r["display_name"], "category": r["category"],
            "ticker": r["ticker_key"], "direction": r["direction"],
            "trade_date": r["trade_date"], "trade_date_text": r["trade_date_text"],
            "disclosed_at": r["disclosed_at"], "amount": r["amount_text"], "url": r["url"],
        }
        for r in conn.execute(
            """SELECT e.trader_key, t.display_name, t.category, e.ticker_key, e.direction,
                      e.trade_date, e.trade_date_text, e.disclosed_at, e.amount_text, p.url
               FROM active_disclosure_events e
               JOIN traders t ON t.trader_key = e.trader_key
               JOIN raw_posts p ON p.post_id = e.post_id
               JOIN accounts a ON a.handle=p.author_handle WHERE a.enabled=1"""
        )
    ]
    trades = _dedupe_trades(rows)
    for t in trades:
        t["kind"] = "trade"
        t["t"] = t["trade_date"] or t["disclosed_at"]
        t["dir"] = "bullish" if t["direction"] in BULLISH_DIRECTIONS else "bearish"
    return trades


def load_signals(conn: sqlite3.Connection, version: str) -> list[dict]:
    from .db import signal_source
    source = signal_source(version)
    return [
        {
            "kind": "signal", "t": r["created_at_utc"], "ticker": r["ticker_key"],
            "who": r["display_name"] or r["author_handle"], "dir": r["stance"],
            "tone": r["tone"], "reason": r["reason_zh"], "quote": r["evidence_quote"],
            "url": r["url"],
        }
        for r in conn.execute(
            f"""SELECT s.ticker_key, s.stance, s.tone, s.reason_zh, s.evidence_quote,
                      p.created_at_utc, p.url, p.author_handle, a.display_name
               FROM {source} s
               JOIN raw_posts p ON p.post_id = s.post_id
               JOIN accounts a ON a.handle = p.author_handle
               WHERE (?='session/v1' OR s.classifier_version = ?) AND p.is_pinned = 0 AND a.enabled=1
                 AND (s.stance != 'unclear' OR s.tone != 'neutral')""",
            (version, version),
        )
    ]


def ticker_timelines(signals: list[dict], trades: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for item in signals + trades:
        out[item["ticker"]].append(item)
    for items in out.values():
        items.sort(key=lambda x: x["t"] or "")
    return dict(out)


def trader_timelines(trades: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        out[t["trader_key"]].append(t)
    for items in out.values():
        items.sort(key=lambda x: x["t"] or "")
    return dict(out)


def stance_path(items: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """每個人在這一檔上的立場軌跡，連續同方向合併成一段。

    回傳 {人: [(起始年月, 方向), ...]}。兩段以上就是發生過反轉，
    例如 [("2026-07", "bullish"), ("2026-08", "bearish")] = 7 月看多、8 月轉空。
    只看有方向的紀錄；「僅提及」不算立場，不會打斷一段軌跡。
    """
    path: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for item in items:
        if item["dir"] not in ("bullish", "bearish"):
            continue
        segs = path[item["who"]]
        if not segs or segs[-1][1] != item["dir"]:
            segs.append(((item["t"] or "")[:7], item["dir"]))
    return dict(path)


# ── HTML 呈現（不用 JS）──────────────────────────────────────────────


def _tag(direction: str, label: str) -> str:
    cls = {"bullish": "t-bull", "bearish": "t-bear"}.get(direction, "t-mute")
    return f'<span class="tag {cls}">{_esc(label)}</span>'


def _links(urls: list[str]) -> str:
    return " ".join(
        f'<a href="{_esc(u)}" target="_blank" rel="noopener">原文{i + 1 if len(urls) > 1 else ""}</a>'
        for i, u in enumerate(urls)
    )


def _trade_when(t: dict) -> str:
    disclosed = (t["disclosed_at"] or "")[:10]
    if t["trade_date"]:
        raw = f"（原文：{_esc(t['trade_date_text'])}）" if t["trade_date_text"] else ""
        return f"交易日 {_esc(t['trade_date'])}{raw} · 揭露 {_esc(disclosed)}"
    return f"交易日未知 · 揭露 {_esc(disclosed)}"


def _timeline_row(item: dict, show_ticker: bool) -> str:
    date = _esc((item["t"] or "")[:10])
    if item["kind"] == "trade":
        head = _esc(item["ticker"]) if show_ticker else f"<b>{_esc(item['who'])}</b>"
        label = DIRECTION_ZH.get(item["direction"], item["direction"])
        extra = f"{item['reports']} 則報導" if item.get("reports", 1) > 1 else ""
        detail = " · ".join(x for x in [
            "揭露事件", _esc(item["amount"]) if item["amount"] else "", _trade_when(item), extra,
        ] if x)
        urls = item.get("urls") or []
    else:
        head = f"<b>{_esc(item['who'])}</b>"
        label = STANCE_ZH.get(item["dir"], item["dir"])
        quote = f"「{_esc(item['quote'])}」" if item.get("quote") else ""
        detail = f"{_esc(item.get('reason'))}{quote}"
        urls = [item["url"]] if item.get("url") else []
    return (f'<div class="tl-row"><div class="tl-t">{date}</div><div class="tl-body">'
            f'{head} {_tag(item["dir"], label)}'
            f'<div class="tl-detail">{detail} {_links(urls)}</div></div></div>')


def _path_html(items: list[dict]) -> str:
    rows = []
    for who, segs in sorted(stance_path(items).items()):
        steps = " → ".join(f"{_esc(m)} {_tag(d, STANCE_ZH[d])}" for m, d in segs)
        flip = ' <span class="flip">立場反轉</span>' if len(segs) > 1 else ""
        rows.append(f"<li><b>{_esc(who)}</b>：{steps}{flip}</li>")
    if not rows:
        return ""
    return f'<div class="paths"><div class="paths-h">每個人的立場軌跡</div><ul>{"".join(rows)}</ul></div>'


def render_ticker_index(timelines: dict[str, list[dict]], ret_html) -> str:
    """個股總覽：每檔一個 <details>，摘要列可直接點開。"""
    if not timelines:
        return '<p class="note">還沒有任何個股資料</p>'
    blocks = []
    for ticker in sorted(timelines, key=lambda k: (-len(timelines[k]), k)):
        items = timelines[ticker]
        latest = items[-1]
        latest_label = (DIRECTION_ZH.get(latest.get("direction"), "") if latest["kind"] == "trade"
                        else STANCE_ZH.get(latest["dir"], latest["dir"]))
        flips = sum(1 for segs in stance_path(items).values() if len(segs) > 1)
        flip_badge = f'<span class="flip">{flips} 人反轉</span>' if flips else ""
        first = (items[0]["t"] or "")[:10]
        blocks.append(
            f'<details class="dt"><summary>'
            f'<span class="s-tk">{_esc(ticker)}</span>'
            f'<span class="s-n">{len(items)} 筆</span>'
            f'<span class="s-range">{_esc(first)} → {_esc((latest["t"] or "")[:10])}</span>'
            f'<span class="s-dir">最新 {_tag(latest["dir"], latest_label)}</span>'
            f'{flip_badge}<span class="s-ret">{ret_html(ticker)}</span>'
            f'</summary><div class="dt-body">{_path_html(items)}'
            f'{"".join(_timeline_row(i, show_ticker=False) for i in reversed(items))}'
            f'</div></details>'
        )
    return "".join(blocks)


def render_trader_index(board: list, timelines: dict[str, list[dict]]) -> str:
    """交易者權重：每人一個 <details>，展開看他的全歷史揭露事件。"""
    if not board:
        return '<p class="note">還沒有交易者資料</p>'
    max_w = max((r["weight"] or r["prior_weight"]) for r in board) or 1
    blocks = []
    for r in board:
        w = r["weight"] or r["prior_weight"]
        items = timelines.get(r["trader_key"], [])
        src = "使用者指定" if r["weight_source"] == "user_directive" else "類別預設"
        tickers = sorted({i["ticker"] for i in items})
        body = "".join(_timeline_row(i, show_ticker=True) for i in reversed(items))
        blocks.append(
            f'<details class="dt"><summary>'
            f'<span class="s-tk">{_esc(r["display_name"])}</span>'
            f'<span class="s-n">{_esc(r["category"])}</span>'
            f'<span class="s-n">{len(items)} 筆交易</span>'
            f'<span class="s-w">權重 {w:.2f}</span>'
            f'<span class="bar s-bar"><i style="width:{w / max_w * 100:.0f}%"></i></span>'
            f'<span class="s-src">{src}</span>'
            f'</summary><div class="dt-body">'
            f'<p class="note">先驗 {r["prior_weight"]:.2f} · 已計分事件 {r["n_scored"] or 0} · '
            f'涉及標的：{_esc("、".join(tickers)) or "—"}</p>'
            f'{body or "<p class=note>沒有揭露事件</p>"}</div></details>'
        )
    return "".join(blocks)


DETAILS_CSS = """
details.dt{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:6px 0}
details.dt>summary{list-style:none;cursor:pointer;padding:10px 14px;display:flex;flex-wrap:wrap;
align-items:center;gap:6px 14px;font-size:13.5px}
details.dt>summary::-webkit-details-marker{display:none}
details.dt>summary::before{content:"▸";color:var(--muted);width:10px}
details.dt[open]>summary::before{content:"▾"}
details.dt[open]>summary{border-bottom:1px solid var(--line)}
details.dt>summary:hover{background:var(--bull-bg)}
.s-tk{font-weight:700;min-width:110px}.s-n,.s-range,.s-src{color:var(--muted);font-size:12.5px}
.s-w{font-variant-numeric:tabular-nums;font-weight:600}.s-bar{width:90px;display:inline-block}
.s-ret{margin-left:auto}.s-ret .ret{float:none}
.flip{font-size:11px;padding:1px 7px;border-radius:99px;background:var(--accent);color:#fff}
.dt-body{padding:6px 14px 12px}
.paths{background:var(--bg);border-radius:6px;padding:8px 12px;margin:6px 0 10px;font-size:13px}
.paths-h{color:var(--muted);font-size:12px;margin-bottom:2px}.paths ul{margin:0;padding-left:18px}
.tl-row{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--line)}
.tl-row:last-child{border-bottom:none}
.tl-t{flex:0 0 84px;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums;padding-top:2px}
.tl-body{flex:1;font-size:13.5px}
.tl-detail{color:var(--muted);margin-top:2px;font-size:12.5px;line-height:1.5}
.tl-detail a{color:var(--accent)}
"""
