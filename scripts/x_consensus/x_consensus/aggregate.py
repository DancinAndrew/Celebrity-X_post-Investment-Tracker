"""把 signals 聚合成共識視圖，輸出每日報告。

核心規則（對應 Capafy Alpha Consensus 的行為，並修掉它的兩個弱點）：
- 立場是「貼文層級」，同一帳號同一天可以同時對一檔看多與看空 → 記為 mixed。
- 「沒提到」不等於「中立」。從未提到的帳號單獨列為 not_mentioned，不進分母。
- 共識只算 counts_toward_consensus 的帳號（意見帳號）；
  選擇權流向、新聞轉述、交易揭露不投票，只出現在「提及」清單。
- 抓取失敗的帳號會被標出來。否則「管線壞掉」在報告上會長得跟「今天沒發文」一樣。
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .db import connect, signal_source, select_stance_version, backlog_status

EASTERN = ZoneInfo("US/Eastern")
OUT_ROOT = Path(os.environ.get("XC_OUT_ROOT")
                or Path(__file__).resolve().parents[3] / "01_Projects" / "X觀點共識追蹤")
REPORT_DIR = OUT_ROOT / "reports"

STANCE_LABEL = {
    "bullish_only": "看多",
    "bearish_only": "看空",
    "mixed": "多空並存",
    "unclear": "僅提及",
}


def _window_start(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def account_stances(conn: sqlite3.Connection, hours: int, version: str) -> dict[str, dict[str, str]]:
    """回傳 {ticker_key: {handle: stance_bucket}}。語氣不影響分桶。"""
    source = signal_source(version)
    rows = conn.execute(
        f"""SELECT s.ticker_key, p.author_handle, s.stance
           FROM {source} s JOIN raw_posts p ON p.post_id = s.post_id
           JOIN accounts a ON a.handle=p.author_handle
           WHERE (? = 'session/v1' OR s.classifier_version = ?) AND a.enabled = 1 AND p.created_at_utc > ? AND p.is_pinned = 0""",
        (version, version, _window_start(hours)),
    ).fetchall()

    seen: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in rows:
        seen[row["ticker_key"]][row["author_handle"]].add(row["stance"])

    out: dict[str, dict[str, str]] = {}
    for ticker, by_account in seen.items():
        buckets = {}
        for handle, stances in by_account.items():
            has_bull, has_bear = "bullish" in stances, "bearish" in stances
            if has_bull and has_bear:
                buckets[handle] = "mixed"
            elif has_bull:
                buckets[handle] = "bullish_only"
            elif has_bear:
                buckets[handle] = "bearish_only"
            else:
                buckets[handle] = "unclear"
        out[ticker] = buckets
    return out


def consensus(conn: sqlite3.Connection, hours: int, version: str) -> dict:
    voters = {
        r["handle"] for r in conn.execute(
            "SELECT handle FROM accounts WHERE counts_toward_consensus = 1 AND enabled = 1"
        )
    }
    stances = account_stances(conn, hours, version)

    shared_bull, shared_bear, split, mentioned = [], [], [], []
    for ticker, buckets in stances.items():
        voting = {h: b for h, b in buckets.items() if h in voters}
        bulls = [h for h, b in voting.items() if b == "bullish_only"]
        bears = [h for h, b in voting.items() if b == "bearish_only"]
        mixed = [h for h, b in voting.items() if b == "mixed"]

        entry = {"ticker": ticker, "bulls": bulls, "bears": bears, "mixed": mixed,
                 "all_accounts": buckets}
        if len(bulls) >= 2 and not bears and not mixed:
            shared_bull.append(entry)
        elif len(bears) >= 2 and not bulls and not mixed:
            shared_bear.append(entry)
        elif (bulls and bears) or mixed:
            split.append(entry)
        else:
            mentioned.append(entry)

    key = lambda e: (-len(e["all_accounts"]), e["ticker"])
    return {
        "shared_bullish": sorted(shared_bull, key=key),
        "shared_bearish": sorted(shared_bear, key=key),
        "split": sorted(split, key=key),
        "mentioned": sorted(mentioned, key=key),
    }


def tone_signals(conn: sqlite3.Connection, hours: int, version: str, min_accounts: int = 2) -> list[dict]:
    """語氣訊號：多個意見帳號用同一種語氣談同一檔，但**都沒有明確表態**。

    只取 stance='unclear' 的訊號。已經有明確立場的個股會出現在共識區塊，
    在這裡重印一次只是噪音——這一區的存在意義是補共識看不見的東西。

    存在的理由：把「四個人同一天嘲諷同一家公司的旗艦產品」這件事顯示出來，
    又不把它算成「四個人看空」。嘲諷產品不等於對股票的判斷——
    但整天都沒人提到它，也是資訊損失。所以分開放，不進共識分母。
    """
    source = signal_source(version)
    rows = conn.execute(
        f"""SELECT s.ticker_key, p.author_handle, s.tone, s.reason_zh
           FROM {source} s
           JOIN raw_posts p ON p.post_id = s.post_id
           JOIN accounts a ON a.handle = p.author_handle
           WHERE (? = 'session/v1' OR s.classifier_version = ?) AND a.enabled = 1 AND p.created_at_utc > ? AND p.is_pinned = 0
             AND a.counts_toward_consensus = 1
             AND s.tone IN ('positive', 'negative')
             AND s.stance = 'unclear'""",
        (version, version, _window_start(hours)),
    ).fetchall()

    grouped: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for row in rows:
        grouped[(row["ticker_key"], row["tone"])][row["author_handle"]] = row["reason_zh"]

    out = [
        {"ticker": ticker, "tone": tone, "accounts": accounts}
        for (ticker, tone), accounts in grouped.items()
        if len(accounts) >= min_accounts
    ]
    return sorted(out, key=lambda e: (-len(e["accounts"]), e["ticker"]))


def fetch_health(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    # INNER JOIN accounts：只顯示目前設定檔裡的帳號。
    # 否則被移除或打錯的舊 handle 會永遠留一列 ❌，看起來像每天都在失敗。
    return conn.execute(
        """SELECT r.handle, CASE WHEN a.enabled=0 THEN 'excluded' ELSE r.status END status, r.tweets, r.newest_utc,
                  CASE WHEN a.enabled=0 THEN a.disabled_reason ELSE r.note END note,
                  MAX(r.started_at_utc) started
           FROM fetch_runs r
           JOIN accounts a ON a.handle = r.handle
           GROUP BY r.handle ORDER BY
             CASE r.status WHEN 'failed' THEN 0 WHEN 'partial' THEN 1 ELSE 2 END, r.handle"""
    ).fetchall()


def _fmt_accounts(entry: dict, names: dict[str, str]) -> str:
    parts = []
    for handle, bucket in sorted(entry["all_accounts"].items()):
        parts.append(f"{names.get(handle, handle)}（{STANCE_LABEL[bucket]}）")
    return "、".join(parts)


def render(conn: sqlite3.Connection, hours: int, version: str) -> str:
    names = {r["handle"]: r["display_name"] for r in conn.execute("SELECT handle, display_name FROM accounts")}
    data = consensus(conn, hours, version)
    now_et = datetime.now(timezone.utc).astimezone(EASTERN)
    posts = conn.execute(
        "SELECT COUNT(*) n FROM raw_posts p JOIN accounts a ON a.handle=p.author_handle WHERE created_at_utc > ? AND is_pinned = 0 AND a.enabled=1",
        (_window_start(hours),),
    ).fetchone()["n"]

    latest = conn.execute("SELECT MAX(created_at_utc) FROM raw_posts p JOIN accounts a "
                          "ON a.handle=p.author_handle WHERE a.enabled=1").fetchone()[0]
    classification_table = "session_v1_classifications" if version == "session/v1" else "post_classifications"
    pending = conn.execute(
        f"""SELECT COUNT(*) FROM raw_posts p JOIN accounts a ON a.handle=p.author_handle
            WHERE a.enabled=1 AND a.account_type='opinion' AND p.is_pinned=0 AND p.created_at_utc > ?
            AND NOT EXISTS(SELECT 1 FROM {classification_table} c WHERE c.post_id=p.post_id
                           AND (?='session/v1' OR c.classifier_version=?))""",
        (_window_start(hours), version, version)).fetchone()[0]
    lines = [
        "---",
        f"title: X 觀點共識 {now_et:%Y-%m-%d}",
        f"created: {now_et:%Y-%m-%d}",
        "tags:",
        "  - project/finance",
        "  - type/report",
        "---",
        "",
        f"# X 觀點共識 · {now_et:%Y-%m-%d}",
        "",
        f"> 產出時間：{now_et:%Y-%m-%d %H:%M} 美東時間 · 窗口 {hours} 小時 · "
        f"{posts} 篇貼文 · 分類器 `{version}`",
        "",
        "> [!warning] 這是公開資訊彙整，不是投資建議。所有立場標籤都是模型推斷，會錯。",
        "",
    ]

    lines += [f"> 最新入庫貼文（UTC）：{latest or '無'}；窗口內尚未判讀觀點：{pending} 篇。",
              "> 歷史回補尚未完成，空白或未分類不可解讀為中立。分類器尚未通過人工評測。", ""]
    for s in backlog_status(conn):
        label = '觀點' if s['kind']=='opinion' else '揭露/選擇權'
        lines += [f"> 固定候選全文回填 · {label}：{s['reviewed']:,}／{s['total_posts']:,} 篇已判讀，"
                  f"{s['remaining']:,} 篇待判讀；{s['unresolved_posts']:,} 篇含 {s['unresolved_references']:,} 個待確認股票參照。",
                  "> 候選完成不代表全部歷史已取得或分類，待確認身分不進個股投票。", ""]

    if version.startswith("regex-mentions"):
        lines += [
            "> [!note] 目前是 regex 提及模式：只統計「誰提到哪些股票」，沒有判斷看多看空。",
            "> 設定 `ANTHROPIC_API_KEY` 後執行 `python -m x_consensus.classify` 才會有立場。",
            "",
        ]

    sections = [
        ("## 明確共同看多", "shared_bullish", "至少 2 個意見帳號明確看多，且無人看空"),
        ("## 明確共同看空", "shared_bearish", "至少 2 個意見帳號明確看空，且無人看多"),
        ("## 多空分歧", "split", "同一檔同時有帳號看多與看空"),
    ]
    for title, key, note in sections:
        lines += [title, "", f"_{note}_", ""]
        entries = data[key]
        if not entries:
            lines += ["（今天沒有）", ""]
            continue
        for entry in entries:
            lines.append(f"- **{entry['ticker']}** — {_fmt_accounts(entry, names)}")
        lines.append("")

    lines += ["## 今日提及（無明確共識）", ""]
    if data["mentioned"]:
        for entry in data["mentioned"][:40]:
            lines.append(f"- **{entry['ticker']}** — {_fmt_accounts(entry, names)}")
        if len(data["mentioned"]) > 40:
            lines.append(f"- …另有 {len(data['mentioned']) - 40} 檔")
    else:
        lines.append("（今天沒有）")
    lines.append("")

    tones = tone_signals(conn, hours, version)
    lines += ["## 語氣訊號（不計入共識）", "",
              "_多個意見帳號用同一種語氣談同一檔，但都沒有明確表態。"
              "嘲諷產品不等於看空股票，所以不投票；但整天沒人提到它也是資訊損失，所以列出來。_", ""]
    if tones:
        for entry in tones:
            mark = "偏負面" if entry["tone"] == "negative" else "偏正面"
            who = "、".join(
                f"{names.get(h, h)}（{why}）" for h, why in sorted(entry["accounts"].items())
            )
            lines.append(f"- **{entry['ticker']}** · {mark} · {len(entry['accounts'])} 個帳號 — {who}")
    else:
        lines.append("（今天沒有）")
    lines.append("")

    lines += ["## 抓取健康度", "",
              "_失敗的帳號代表資料缺失，不代表該帳號今天沒發文。_", "",
              "| 帳號 | 狀態 | 貼文 | 最新一篇 | 備註 |", "|---|---|---|---|---|"]
    for row in fetch_health(conn):
        icon = {"ok": "✅", "partial": "⚠️", "failed": "❌", "excluded": "⛔"}.get(row["status"], "?")
        newest = row["newest_utc"][:16].replace("T", " ") if row["newest_utc"] else "—"
        lines.append(
            f"| {names.get(row['handle'], row['handle'])} | {icon} {row['status']} | "
            f"{row['tweets']} | {newest} | {row['note'] or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(hours: int = 26, version: str | None = None) -> None:
    conn = connect()
    if version is None:
        version = select_stance_version(conn)

    text = render(conn, hours, version)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now_et = datetime.now(timezone.utc).astimezone(EASTERN)
    path = REPORT_DIR / f"{now_et:%Y-%m-%d}.md"
    path.write_text(text, encoding="utf-8")
    print(f"報告已寫入：{path}")
    conn.close()


if __name__ == "__main__":
    main()
