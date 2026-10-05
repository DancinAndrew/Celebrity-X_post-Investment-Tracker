"""產生單一自帶樣式的 HTML 儀表板，每次跑管線就重新產生。

不依賴網路、不依賴伺服器、不引用外部 CSS 或字型——直接用瀏覽器開檔案就能看。
排程是無人值守的本機工作，沒辦法每次自動發布到雲端，所以本機檔案才是
真正能做到「每天更新」的形式。

個股與交易者的全歷史時間線用原生 <details> 展開收合，完全不用 JavaScript——
Obsidian 與 App 預覽會擋腳本，第一版的 JS 彈窗在使用者那邊點不開。見 timelines.py。
"""
from __future__ import annotations

import html
import sqlite3
from datetime import datetime, timezone
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .aggregate import EASTERN, consensus, fetch_health, tone_signals
from .db import connect, window_cutoff, select_stance_version, backlog_status
from .prices import window_return
from .traders import leaderboard
from . import timelines as tl

OUT_ROOT = Path(os.environ.get("XC_OUT_ROOT")
                or Path(__file__).resolve().parents[3] / "01_Projects" / "X觀點共識追蹤")
OUT_PATH = OUT_ROOT / "dashboard.html"

CSS = """
:root{--bg:#faf9f5;--fg:#1a1a19;--muted:#6b6a63;--line:#e3e1d8;--card:#fff;
--bull:#1a6b3c;--bull-bg:#eaf5ee;--bear:#a32d2d;--bear-bg:#fbecec;--accent:#3b5bdb}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#161614;--fg:#eceae2;
--muted:#9c9a90;--line:#2e2e2a;--card:#1e1e1b;--bull:#5fbf85;--bull-bg:#16281d;
--bear:#e07b7b;--bear-bg:#2a1818;--accent:#8fa4f5}}
:root[data-theme=dark]{--bg:#161614;--fg:#eceae2;--muted:#9c9a90;--line:#2e2e2a;
--card:#1e1e1b;--bull:#5fbf85;--bull-bg:#16281d;--bear:#e07b7b;--bear-bg:#2a1818;--accent:#8fa4f5}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,BlinkMacSystemFont,
"Segoe UI","Noto Sans TC","PingFang TC",sans-serif;margin:0;padding:28px 20px 60px}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:30px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:19px;margin:36px 0 6px;padding-bottom:6px;border-bottom:2px solid var(--fg)}
.sub{color:var(--muted);font-size:13px;margin:0 0 4px}
.note{color:var(--muted);font-size:13px;margin:0 0 12px;font-style:italic}
.warn{background:var(--bear-bg);border-left:3px solid var(--bear);padding:10px 14px;
border-radius:4px;font-size:13px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px}
.card.bull{border-left:4px solid var(--bull)}.card.bear{border-left:4px solid var(--bear)}
.card.split{border-left:4px solid var(--accent)}
.tk{font-size:17px;font-weight:700;letter-spacing:-.01em}
.ret{float:right;font-variant-numeric:tabular-nums;font-weight:600}
.up{color:var(--bull)}.down{color:var(--bear)}
.who{font-size:13px;color:var(--muted);margin-top:6px}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;margin-right:4px}
.t-bull{background:var(--bull-bg);color:var(--bull)}.t-bear{background:var(--bear-bg);color:var(--bear)}
.t-mute{background:var(--line);color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-weight:600;color:var(--muted);border-bottom:1px solid var(--line);
padding:7px 8px;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
.num{text-align:right;font-variant-numeric:tabular-nums}
.bar{height:6px;border-radius:3px;background:var(--line);overflow:hidden;min-width:70px}
.bar>i{display:block;height:100%;background:var(--accent)}
.scroll{overflow-x:auto}
"""+tl.DETAILS_CSS+"""footer{margin-top:44px;padding-top:14px;border-top:1px solid var(--line);
color:var(--muted);font-size:12px}
"""


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _ret_html(value: float | None) -> str:
    if value is None:
        return '<span class="ret" style="color:var(--muted)">無價格</span>'
    cls = "up" if value >= 0 else "down"
    return f'<span class="ret {cls}">{value * 100:+.1f}%</span>'


STANCE_TAG = {"bullish_only": ("t-bull", "看多"), "bearish_only": ("t-bear", "看空"),
              "mixed": ("t-mute", "多空並存"), "unclear": ("t-mute", "僅提及")}


def _accounts_html(entry: dict, names: dict[str, str]) -> str:
    out = []
    for handle, bucket in sorted(entry["all_accounts"].items()):
        cls, label = STANCE_TAG[bucket]
        out.append(f'<span class="tag {cls}">{_esc(names.get(handle, handle))} · {label}</span>')
    return "".join(out)


def _cards(conn, entries: list[dict], names: dict[str, str], kind: str) -> str:
    if not entries:
        return '<p class="note">今天沒有</p>'
    cards = []
    for e in entries:
        cards.append(
            f'<div class="card {kind}"><div class="tk">{_esc(e["ticker"])}'
            f'{_ret_html(window_return(conn, e["ticker"], 7))}</div>'
            f'<div class="who">{_accounts_html(e, names)}</div></div>'
        )
    return f'<div class="grid">{"".join(cards)}</div>'


def render(conn: sqlite3.Connection, hours: int, version: str) -> str:
    names = {r["handle"]: r["display_name"]
             for r in conn.execute("SELECT handle, display_name FROM accounts")}
    data = consensus(conn, hours, version)
    tones = tone_signals(conn, hours, version)
    now_et = datetime.now(timezone.utc).astimezone(EASTERN)
    posts = conn.execute(
        "SELECT COUNT(*) n FROM raw_posts p JOIN accounts a ON a.handle=p.author_handle WHERE created_at_utc > ? AND is_pinned=0 AND a.enabled=1",
        (window_cutoff(hours),),
    ).fetchone()["n"]
    n_acct = conn.execute("SELECT COUNT(*) n FROM accounts").fetchone()["n"]
    # 待分類篇數必須顯示出來。否則「還沒判讀」在畫面上會長得跟「沒有訊號」一樣，
    # 讀報告的人會把管線的缺口誤讀成市場的安靜。
    classification_table = "session_v1_classifications" if version == "session/v1" else "post_classifications"
    pending = conn.execute(
        f"""SELECT COUNT(*) n FROM raw_posts p JOIN accounts a ON a.handle=p.author_handle
           WHERE a.enabled=1 AND a.account_type='opinion' AND p.created_at_utc > ? AND p.is_pinned = 0
             AND NOT EXISTS (SELECT 1 FROM {classification_table} c
                             WHERE c.post_id = p.post_id AND (?='session/v1' OR c.classifier_version = ?))""",
        (window_cutoff(hours), version, version),
    ).fetchone()["n"]

    latest = conn.execute("SELECT MAX(created_at_utc) FROM raw_posts p JOIN accounts a ON a.handle=p.author_handle WHERE a.enabled=1").fetchone()[0]
    coverage = backlog_status(conn)
    coverage_html = ''.join(
        f'<p class="note">固定候選全文回填 · {"觀點" if s["kind"]=="opinion" else "揭露/選擇權"}：'
        f'{s["reviewed"]:,}／{s["total_posts"]:,} 篇已判讀，{s["remaining"]:,} 篇待判讀；'
        f'{s["unresolved_posts"]:,} 篇含 {s["unresolved_references"]:,} 個待確認股票參照。'
        '候選完成不代表全部歷史已取得或分類，待確認身分不進個股投票。</p>' for s in coverage)
    parts = [
        f"<title>X 觀點共識 {now_et:%Y-%m-%d}</title><style>{CSS}</style>",
        '<div class="wrap">',
        f"<h1>X 觀點共識儀表板</h1>",
        f'<p class="sub">產出時間 {now_et:%Y-%m-%d %H:%M} 美東時間 · 窗口 {hours} 小時 · '
        f'{n_acct} 個帳號 · {posts} 篇貼文 · 分類器 <code>{_esc(version)}</code></p>',
        (f'<div class="warn"><b>{pending} 篇尚未判讀立場。</b>'
         '下面的共識結論不包含這些貼文——這是管線的缺口，不是市場沒有訊號。'
         '在 Claude Code 說「分類 x_consensus 的待辦貼文」即可補上。</div>'
         if pending else ''),
        f'<p class="note">最新入庫貼文（UTC）：{_esc(latest)}。歷史回補尚未完成，分類器尚未通過人工評測。</p>',
        coverage_html,
        '<div class="warn">這是公開資訊彙整，不是投資建議。所有立場標籤都是模型推斷，會錯。'
        '報酬數字為最近 7 日收盤價變化，僅供對照，不代表任何人的實際損益。</div>',
        "<h2>明確共同看多</h2>",
        '<p class="note">至少 2 個意見帳號明確看多，且無人看空</p>',
        _cards(conn, data["shared_bullish"], names, "bull"),
        "<h2>明確共同看空</h2>",
        '<p class="note">至少 2 個意見帳號明確看空，且無人看多</p>',
        _cards(conn, data["shared_bearish"], names, "bear"),
        "<h2>多空分歧</h2>",
        '<p class="note">同一檔同時有帳號看多與看空</p>',
        _cards(conn, data["split"], names, "split"),
    ]

    parts.append("<h2>語氣訊號</h2>")
    parts.append('<p class="note">多個意見帳號用同一種語氣談同一檔，但都沒有明確表態。'
                 '嘲諷產品不等於看空股票，所以不計入共識；但整天沒人提到它也是資訊損失。</p>')
    if tones:
        rows = "".join(
            f'<tr><td><b>{_esc(e["ticker"])}</b></td>'
            f'<td>{"偏負面" if e["tone"] == "negative" else "偏正面"}</td>'
            f'<td class="num">{len(e["accounts"])}</td>'
            f'<td>{_esc("、".join(names.get(h, h) for h in sorted(e["accounts"])))}</td></tr>'
            for e in tones
        )
        parts.append('<div class="scroll"><table><tr><th>標的</th><th>語氣</th>'
                     f'<th class="num">帳號數</th><th>誰</th></tr>{rows}</table></div>')
    else:
        parts.append('<p class="note">今天沒有</p>')

    # ── 個股總覽（全歷史，<details> 展開，不需要 JS）────────────────
    signals_all = tl.load_signals(conn, version)
    trades_all = tl.load_trades(conn)
    by_ticker = tl.ticker_timelines(signals_all, trades_all)
    by_trader = tl.trader_timelines(trades_all)
    parts.append("<h2>個股總覽</h2>")
    parts.append('<p class="note">全歷史，不限於本次窗口。點任一檔展開：上方是每個人的立場軌跡'
                 '（有反轉會標出來），下方是由新到舊的完整時間線。交易者的揭露事件以<b>交易日</b>排序，'
                 '揭露日另外標註。</p>')
    parts.append(tl.render_ticker_index(by_ticker, lambda k: _ret_html(window_return(conn, k, 7))))

    # ── 交易者權重與揭露事件 ──────────────────────────────────────
    board = leaderboard(conn)
    scored_total = sum((r["n_scored"] or 0) for r in board)
    parts.append("<h2>交易風向：交易者權重</h2>")
    parts.append('<p class="note">權重 = 先驗值 × 實績乘數。先驗值依身分類別給，'
                 '實績乘數由本專案自己抓到的揭露事件加價格資料算出，樣本不足時退回 1.0。'
                 '點任一位展開他的全歷史交易時間線。</p>')
    parts.append('<p class="note">權重結合先驗值與揭露事件的價格計分。有成交日用成交日，未知時用揭露日，混合兩種起點；尚未驗證預測能力，不能當成實際交易績效，未納入完整持倉。</p>')
    if scored_total == 0:
        parts.append('<div class="warn">目前所有權重都等於先驗值，<b>不含任何實績成分</b>——'
                     '還沒有任何揭露事件滿 30 天。實績要累積數月才會讓權重脫離先驗值。</div>')
    parts.append(tl.render_trader_index(board, by_trader))

    weights = {r["trader_key"]: (r["weight"] or r["prior_weight"]) for r in board}
    recent = sorted(trades_all, key=lambda t: t["t"] or "", reverse=True)[:60]
    parts.append("<h2>揭露事件（依交易日，新到舊）</h2>")
    parts.append('<p class="note">交易日是實際成交日（來源有寫才有），揭露日是我們得知的日期。'
                 '國會申報最長可延遲 45 天，內部人 Form 4 為兩個工作日。'
                 '同一筆交易被多則貼文重複報導時已合併。</p>')
    rows = "".join(
        f'<tr><td>{_esc(t["trade_date"] or "未知")}</td>'
        f'<td>{_esc((t["disclosed_at"] or "")[:10])}</td>'
        f'<td><b>{_esc(t["who"])}</b></td><td>{_esc(t["ticker"])}</td>'
        f'<td><span class="tag {"t-bull" if t["dir"] == "bullish" else "t-bear"}">'
        f'{_esc(tl.DIRECTION_ZH.get(t["direction"], t["direction"]))}</span></td>'
        f'<td>{_esc(t["amount"])}</td><td class="num">{t["reports"]}</td>'
        f'<td class="num">{weights.get(t["trader_key"], 0):.2f}</td></tr>'
        for t in recent
    )
    parts.append('<div class="scroll"><table><tr><th>交易日</th><th>揭露日</th><th>交易者</th>'
                 '<th>標的</th><th>方向</th><th>金額</th><th class="num">報導數</th>'
                 f'<th class="num">權重</th></tr>{rows}</table></div>')

    parts.append("<h2>抓取健康度</h2>")
    parts.append('<p class="note">失敗的帳號代表資料缺失，不代表該帳號今天沒發文。</p>')
    icons = {"ok": "✅", "partial": "⚠️", "failed": "❌", "excluded": "⛔"}
    rows = "".join(
        f'<tr><td>{_esc(names.get(r["handle"], r["handle"]))}</td>'
        f'<td>{icons.get(r["status"], "?")} {_esc(r["status"])}</td>'
        f'<td class="num">{r["tweets"]}</td>'
        f'<td>{_esc((r["newest_utc"] or "—")[:16].replace("T", " "))}</td>'
        f'<td>{_esc(r["note"])}</td></tr>'
        for r in fetch_health(conn)
    )
    parts.append('<div class="scroll"><table><tr><th>帳號</th><th>狀態</th>'
                 f'<th class="num">貼文</th><th>最新一篇</th><th>備註</th></tr>{rows}</table></div>')

    parts.append(f'<footer>由 scripts/x_consensus 產生於 '
                 f'{datetime.now(timezone.utc).astimezone(EASTERN):%Y-%m-%d %H:%M} 美東時間。'
                 f'判準見 01_Projects/X觀點共識追蹤/判準.md。</footer></div>')

    return "\n".join(parts)


def main(hours: int = 26, version: str | None = None) -> None:
    conn = connect()
    if version is None:
        version = select_stance_version(conn)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        + render(conn, hours, version) + "</body></html>",
        encoding="utf-8",
    )
    print(f"儀表板已寫入：{OUT_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
