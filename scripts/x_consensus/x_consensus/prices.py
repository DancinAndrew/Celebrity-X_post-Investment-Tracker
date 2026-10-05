"""抓收盤價，供報酬計算與交易者實績評分使用。

只抓真的被提到過的標的（signals 或 disclosure_events 裡出現過的），
不維護一份全市場清單。抓不到就留空——寧可在報告上顯示「無價格資料」，
也不要用猜的數字去算報酬。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .db import connect
from .tickers import yfinance_symbol

LOOKBACK_DAYS = 420          # 一年報酬需要約 365 天，多留緩衝給停牌與假日


def wanted_tickers(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT ticker_key FROM (
             SELECT ticker_key FROM signals
             UNION SELECT ticker_key FROM disclosure_events
           ) ORDER BY ticker_key"""
    ).fetchall()
    return [r["ticker_key"] for r in rows]


def fetch(limit: int | None = None) -> tuple[int, list[str]]:
    import yfinance as yf

    conn = connect()
    tickers = wanted_tickers(conn)
    if limit:
        tickers = tickers[:limit]

    pairs = [(k, yfinance_symbol(k)) for k in tickers]
    pairs = [(k, s) for k, s in pairs if s]
    symbols = [s for _, s in pairs]
    if not symbols:
        conn.close()
        return (0, [])

    data = yf.download(symbols, period=f"{LOOKBACK_DAYS}d", interval="1d",
                       auto_adjust=True, progress=False, threads=True)
    written, missing = 0, []
    with conn:
        for key, symbol in pairs:
            try:
                series = data["Close"][symbol] if len(symbols) > 1 else data["Close"]
            except (KeyError, TypeError):
                missing.append(key)
                continue
            series = series.dropna()
            if series.empty:
                missing.append(key)
                continue
            rows = [(key, idx.strftime("%Y-%m-%d"), float(val)) for idx, val in series.items()]
            conn.executemany(
                "INSERT OR REPLACE INTO prices (ticker_key, date, close) VALUES (?, ?, ?)", rows
            )
            written += len(rows)
    conn.close()
    return (written, missing)


def window_return(conn: sqlite3.Connection, ticker_key: str, days: int) -> float | None:
    """最近 days 天的報酬。資料不足回 None。"""
    rows = conn.execute(
        """SELECT close FROM prices WHERE ticker_key = ?
           AND date >= date('now', ?) ORDER BY date""",
        (ticker_key, f"-{days} days"),
    ).fetchall()
    if len(rows) < 2 or not rows[0]["close"]:
        return None
    return (rows[-1]["close"] - rows[0]["close"]) / rows[0]["close"]


def main() -> None:
    written, missing = fetch()
    print(f"寫入價格列：{written}")
    if missing:
        print(f"抓不到價格（{len(missing)}）：{missing[:15]}")
        print("這些標的在報告上會顯示『無價格資料』，不會用猜的數字補。")
    conn = connect()
    n = conn.execute("SELECT COUNT(DISTINCT ticker_key) FROM prices").fetchone()[0]
    print(f"已有價格的標的：{n}")
    conn.close()


if __name__ == "__main__":
    main()
