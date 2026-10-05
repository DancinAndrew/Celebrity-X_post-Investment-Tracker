"""regex-only 提及模式：不呼叫模型也能跑出「今天誰提到哪些股票」。

用途有二：
1. 沒有 API 金鑰時，管線仍可端到端驗證。
2. 當成分類器的下限對照 —— 如果模型抓到的個股比 regex 還少，那是 bug。

立場一律 unclear：regex 判不出看多看空，硬猜只會製造假訊號。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from .db import connect
from .tickers import resolve

VERSION = "regex-mentions/v1"

# 指數、ETF 與商品不是個股，不進共識。模型層由提示詞規則 1 處理，
# regex 層沒有語意判斷，只能用排除表。
NOT_SINGLE_STOCKS = {
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "VIX", "SPX", "NDX", "RUT", "ES", "NQ",
    "TLT", "HYG", "GLD", "SLV", "USO", "UNG", "XLF", "XLE", "XLK", "SMH", "SOXX",
    "ARKK", "TQQQ", "SQQQ", "UVXY", "BTC", "ETH", "SOL", "DXY", "GBTC", "IBIT",
}

# 純大寫短字母在沒有 $ 前綴時誤判率極高，這裡只採用 X 自己標好的 entities.symbols
# 與明確帶 $ 的 cashtag，不做公司名比對。
def run(hours: int = 26) -> int:
    conn = connect()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        "SELECT post_id, text, symbols_json FROM raw_posts WHERE created_at_utc > ? AND is_pinned = 0",
        (cutoff,),
    ).fetchall()

    now = datetime.now(timezone.utc).isoformat()
    out: list[tuple] = []
    for row in rows:
        symbols = json.loads(row["symbols_json"])
        # 一篇貼文列出超過 6 檔多半是清單型內容（例如「所有單字母代碼」），不是觀點
        if len(symbols) > 6:
            continue
        for sym in symbols:
            if sym.upper() in NOT_SINGLE_STOCKS:
                continue
            key = resolve(sym, None, None)
            if key:
                out.append((row["post_id"], key, "unclear", "neutral", 0.0,
                            "regex 提及，未判立場", None, VERSION, now))
    with conn:
        conn.executemany(
            """INSERT OR REPLACE INTO signals
               (post_id, ticker_key, stance, tone, confidence, reason_zh, evidence_quote,
                classifier_version, classified_at_utc) VALUES (?,?,?,?,?,?,?,?,?)""",
            out,
        )
    conn.close()
    return len(out)


if __name__ == "__main__":
    print(f"寫入提及訊號：{run()}")
