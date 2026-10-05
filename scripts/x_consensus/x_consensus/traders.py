"""交易者權重：先驗值 × 實績乘數。

刻意不把「某某人的戰績」寫死在程式裡——那是幻覺風險最高的地方，而且無法查核。
權重拆成兩層：

1. prior（先驗）：依身分類別給的保守起始值，寫在 traders.json，可改。
2. credibility（實績乘數）：用**我們自己抓到的揭露事件加上價格資料**算出的
   前瞻報酬。樣本不足時自動退回 1.0，也就是完全採用先驗值。

    weight = prior × credibility
    credibility = 0.5 + shrunk_hit_rate
    shrunk_hit_rate = (命中數 + α×0.5) / (已計分事件數 + α)

α 是收縮強度（shrinkage）——樣本少時把命中率拉回 0.5，避免「兩筆全中就給滿分」。
事件數為 0 時 shrunk_hit_rate 正好是 0.5，credibility 正好是 1.0。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent
CONFIG_PATH = HOME / "traders.json"

# 方向對應「期待股價往哪走」。cover（回補空單）視為看多，因為那是在減少空方曝險。
BULLISH_DIRECTIONS = {"buy", "cover"}
BEARISH_DIRECTIONS = {"sell", "short"}


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def resolve_prior(trader_key: str, category: str, cfg: dict) -> tuple[float, str, str | None]:
    """回傳 (prior_weight, weight_source, notes)。覆寫優先於類別預設。"""
    override = cfg.get("overrides", {}).get(trader_key)
    if override:
        return (
            float(override["prior_weight"]),
            override.get("weight_source", "user_directive"),
            override.get("notes"),
        )
    prior = cfg["category_priors"].get(category)
    if prior is None:
        raise ValueError(f"未知的交易者類別：{category!r}")
    return (float(prior), "category_default", None)


def upsert_trader(conn: sqlite3.Connection, trader_key: str, display_name: str,
                  category: str, cfg: dict) -> None:
    prior, source, notes = resolve_prior(trader_key, category, cfg)
    conn.execute(
        """INSERT INTO traders (trader_key, display_name, category, prior_weight,
                                weight_source, notes, first_seen)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(trader_key) DO UPDATE SET
             display_name = excluded.display_name,
             category     = excluded.category,
             prior_weight = excluded.prior_weight,
             weight_source= excluded.weight_source,
             notes        = COALESCE(excluded.notes, traders.notes)""",
        (trader_key, display_name, category, prior, source, notes,
         datetime.now(timezone.utc).isoformat()),
    )


def _forward_return(conn: sqlite3.Connection, ticker_key: str,
                    start_date: str, days: int) -> float | None:
    """揭露日之後 days 天的報酬。沒有足夠價格資料就回 None，不猜。"""
    start = conn.execute(
        "SELECT close FROM prices WHERE ticker_key=? AND date<=? ORDER BY date DESC LIMIT 1",
        (ticker_key, start_date),
    ).fetchone()
    end = conn.execute(
        "SELECT close FROM prices WHERE ticker_key=? AND date>=date(?, ?) ORDER BY date LIMIT 1",
        (ticker_key, start_date, f"+{days} days"),
    ).fetchone()
    if not start or not end or not start["close"]:
        return None
    return (end["close"] - start["close"]) / start["close"]


def recompute_scores(conn: sqlite3.Connection) -> list[dict]:
    """整表重算。事件或價格更新後直接重跑，不做增量。"""
    cfg = load_config()
    alpha = float(cfg["shrinkage_alpha"])
    days = int(cfg["forward_days"])
    now = datetime.now(timezone.utc).isoformat()

    # 同一筆交易常被多個帳號重複報導。以 (交易者, 標的, 方向, 交易日或揭露日)
    # 合併成一筆，揭露日取最早那則——不合併的話，被轉述越多次的交易者
    # 事件數與命中數會被灌水，權重跟「誰比較常被報導」掛鉤，而不是跟實績掛鉤。
    rows = conn.execute(
        """SELECT t.trader_key, t.prior_weight, e.ticker_key, e.direction,
                  MIN(e.disclosed_at) AS disclosed_at,
                  -- 計分起點：有交易日就用交易日（衡量交易者本人的戰績），
                  -- 沒有才退回揭露日（衡量「看到揭露才跟單」的報酬）
                  COALESCE(MIN(e.trade_date), substr(MIN(e.disclosed_at), 1, 10)) AS start_date
           FROM traders t LEFT JOIN active_disclosure_events e ON e.trader_key = t.trader_key
           GROUP BY t.trader_key, e.ticker_key, e.direction,
                    COALESCE(e.trade_date, substr(e.disclosed_at, 1, 10))"""
    ).fetchall()

    tally: dict[str, dict] = {}
    for row in rows:
        rec = tally.setdefault(
            row["trader_key"],
            {"prior": row["prior_weight"], "n_events": 0, "n_scored": 0, "n_hits": 0},
        )
        if row["ticker_key"] is None:
            continue
        rec["n_events"] += 1
        ret = _forward_return(conn, row["ticker_key"], row["start_date"], days)
        if ret is None:
            continue                      # 未滿 days 天或缺價格 → 不計分，不灌水
        rec["n_scored"] += 1
        direction = row["direction"]
        if (direction in BULLISH_DIRECTIONS and ret > 0) or (
            direction in BEARISH_DIRECTIONS and ret < 0
        ):
            rec["n_hits"] += 1

    out = []
    for trader_key, rec in tally.items():
        shrunk = (rec["n_hits"] + alpha * 0.5) / (rec["n_scored"] + alpha)
        credibility = 0.5 + shrunk
        weight = rec["prior"] * credibility
        conn.execute(
            """INSERT OR REPLACE INTO trader_scores
               (trader_key, n_events, n_scored, n_hits, shrunk_hit_rate,
                credibility, weight, computed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (trader_key, rec["n_events"], rec["n_scored"], rec["n_hits"],
             shrunk, credibility, weight, now),
        )
        out.append({"trader_key": trader_key, **rec, "shrunk_hit_rate": shrunk,
                    "credibility": credibility, "weight": weight})
    return sorted(out, key=lambda r: -r["weight"])


def leaderboard(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT t.trader_key, t.display_name, t.category, t.prior_weight,
                  t.weight_source, s.n_events, s.n_scored, s.n_hits, s.weight
           FROM traders t LEFT JOIN trader_scores s ON s.trader_key = t.trader_key
           ORDER BY COALESCE(s.weight, t.prior_weight) DESC, t.display_name"""
    ).fetchall()
