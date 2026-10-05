"""立場分類器：判斷每篇貼文對哪些股票看多／看空／只提及。

分兩層：
1. regex（tickers.extract_candidates）先找出可能的代碼 —— 零成本、可解釋。
2. 模型判立場並補漏 —— 用結構化輸出（structured output，API 強制回傳符合
   指定 JSON schema 的內容，不必自己解析文字）。

模型只負責「這句話對這檔是看多還看空」，不負責「這是哪一檔」；
代碼對應交給 tickers.resolve 這一層確定性邏輯，解不出來就進 unresolved，不猜。

每筆訊號都記 classifier_version。換模型或改提示詞就要換版本，
否則新舊標準混在一起算共識，數字會沒有意義。
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import connect
from .tickers import extract_candidates, resolve

MODEL = "claude-opus-5"
PROMPT_VERSION = "v2"
CLASSIFIER_VERSION = f"{MODEL}/{PROMPT_VERSION}"
BATCH_SIZE = 10
MAX_TOKENS = 16000

SYSTEM_PROMPT = """你是金融社群貼文的立場標註器。輸入是 X（Twitter）上財經帳號的貼文，
輸出是每篇貼文對「具體個股」的立場。

每個訊號要分開標兩件事：**立場（stance）** 與 **語氣（tone）**。

立場——只有這個會進共識計算，標準要嚴：
- bullish：作者認為這檔會漲、基本面轉好、或明確表達持有／買進傾向。
- bearish：作者認為這檔會跌、基本面轉壞、或明確表達賣出／看空傾向。
- unclear：有提到這檔，但看不出對股價的方向判斷。

語氣——只顯示，不投票，標準可以寬：
- positive / negative / neutral：這則提及讀起來對這家公司是正面、負面還是中性。

**嘲諷產品不等於看空股票。** 「這支手機好醜」的立場是 unclear、語氣是 negative。
理由：如果去問那位作者「你看空這檔嗎」，他多半會說我只是在酸產品。
把它算成看空會製造出不存在的共識，而製造假共識正是這個工具最致命的失效模式。
但整天四個人嘲諷同一家公司卻在報告上完全消失，也是資訊損失——
所以用語氣欄把它留下來，放在共識分母外面。

必須遵守的規則：

1. 只標「具體個股」。大盤、指數、總經、加密貨幣、商品不算，跳過。
2. 反諷與雙重否定要照語意判斷，不要看字面。
   例：「not time to put down the semis」是看多，不是看空。
3. 沒有 $ 前綴的短字母串，只有在你能指出公司名時才算個股。
   PM、IT、ALL、NOW、BB、A、ON 這類極容易誤判：看不出是公司就不要標。
4. 一篇貼文列出大量代碼（例如「所有單字母代碼一覽」）屬於清單型內容，
   不是觀點。這種情況回空的 signals，並把 is_list_or_market_wide 設為 true。
5. 帳號類型會改變判讀：
   - opinion：正常判立場。
   - options_flow：選擇權流向。大量 call 流入偏 bullish、put 流入偏 bearish，
     但只有在作者有表達傾向時才給方向，純數據播報給 unclear。
   - market_news：新聞轉述。除非作者加了自己的判斷，否則給 unclear。
   - trade_disclosure：揭露別人的交易。一律 unclear，那不是作者的觀點。
6. quote（引用）型貼文的文字裡會有「[引用 @某人]:」。立場以「引用者自己寫的那段」
   為準；被引用的原文只是脈絡。作者若只是轉貼沒加評論，給 unclear。
7. confidence 是你對這個立場判斷的把握，0 到 1。語氣模糊、反諷、脈絡不足就壓低。
8. reason_zh 用繁體中文寫一句話，說明你為什麼判這個立場，要具體引到貼文內容，
   不要寫「作者看多」這種空話。
9. evidence_quote 直接從貼文原文抄一小段（原文語言，不要翻譯），
   讓人可以回頭核對。

market_guess 填該股主要掛牌市場：NASDAQ、NYSE、AMEX、KRX、KOSDAQ、SSE、SZSE、
TWSE、TSE、HKEX 其中之一。六碼數字代碼特別容易搞混：005930 與 000660 是韓國（KRX），
688xxx 與 6xxxxx 是上海（SSE），000001／002xxx／300xxx 是深圳（SZSE）。不確定就填最可能的。
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "post_id": {"type": "string"},
                    "is_list_or_market_wide": {"type": "boolean"},
                    "signals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "symbol_as_written": {"type": "string"},
                                "company_name": {"type": "string"},
                                "market_guess": {"type": "string"},
                                "stance": {"type": "string", "enum": ["bullish", "bearish", "unclear"]},
                                "tone": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                                "confidence": {"type": "number"},
                                "reason_zh": {"type": "string"},
                                "evidence_quote": {"type": "string"},
                            },
                            "required": [
                                "symbol_as_written", "company_name", "market_guess",
                                "stance", "tone", "confidence", "reason_zh", "evidence_quote",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["post_id", "is_list_or_market_wide", "signals"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def pending_posts(conn: sqlite3.Connection, hours: int) -> list[sqlite3.Row]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return conn.execute(
        """SELECT p.post_id, p.author_handle, p.created_at_utc, p.text, p.kind,
                  p.symbols_json, a.account_type, a.focus
           FROM raw_posts p
           JOIN accounts a ON a.handle = p.author_handle
           WHERE p.created_at_utc > ?
             AND p.is_pinned = 0
             AND NOT EXISTS (
               SELECT 1 FROM post_classifications c
               WHERE c.post_id = p.post_id AND c.classifier_version = ?
             )
           ORDER BY p.created_at_utc DESC""",
        (cutoff, CLASSIFIER_VERSION),
    ).fetchall()


def build_batch_prompt(rows: list[sqlite3.Row]) -> str:
    parts = []
    for row in rows:
        candidates = extract_candidates(row["text"], json.loads(row["symbols_json"]))
        parts.append(
            f"<post id=\"{row['post_id']}\" account=\"@{row['author_handle']}\" "
            f"account_type=\"{row['account_type']}\" kind=\"{row['kind']}\" "
            f"time=\"{row['created_at_utc']}\">\n"
            f"帳號關注領域：{row['focus']}\n"
            f"regex 候選代碼：{', '.join(candidates) if candidates else '（無）'}\n"
            f"內文：\n{row['text']}\n"
            f"</post>"
        )
    return (
        "為下列每一篇貼文標註立場。每篇都要在 results 出現一次，"
        "即使它沒有任何個股訊號（那就給空的 signals）。\n\n" + "\n\n".join(parts)
    )


def classify_batch(client: Any, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            # 系統提示每批都一樣，快取起來只算一次錢
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": build_batch_prompt(rows)}],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"模型拒答，跳過這批：{getattr(response, 'stop_details', None)}")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["results"]


def store(conn: sqlite3.Connection, results: list[dict[str, Any]]) -> tuple[int, list[str]]:
    now = datetime.now(timezone.utc).isoformat()
    unresolved: list[str] = []
    rows = []
    done: dict[str, int] = {}
    for item in results:
        done.setdefault(item["post_id"], 0)
        if item.get("is_list_or_market_wide"):
            continue
        for sig in item.get("signals", []):
            key = resolve(sig["symbol_as_written"], sig.get("company_name"), sig.get("market_guess"))
            if not key:
                unresolved.append(f"{sig['symbol_as_written']} / {sig.get('company_name')}")
                continue
            rows.append((
                item["post_id"], key, sig["stance"], sig.get("tone", "neutral"),
                float(sig["confidence"]), sig["reason_zh"], sig.get("evidence_quote"),
                CLASSIFIER_VERSION, now,
            ))
            done[item["post_id"]] = done.get(item["post_id"], 0) + 1
    conn.executemany(
        """INSERT OR REPLACE INTO signals
           (post_id, ticker_key, stance, tone, confidence, reason_zh, evidence_quote,
            classifier_version, classified_at_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    # 即使一個訊號都沒有也要記，否則這篇明天會再被送一次
    conn.executemany(
        """INSERT OR REPLACE INTO post_classifications
           (post_id, classifier_version, classified_at_utc, signal_count)
           VALUES (?, ?, ?, ?)""",
        [(pid, CLASSIFIER_VERSION, now, count) for pid, count in done.items()],
    )
    return len(rows), unresolved


def main(hours: int = 26) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "缺少 ANTHROPIC_API_KEY。分類器需要 Anthropic API 金鑰才能執行；\n"
            "抓取與正規化（fetch.sh、ingest）不需要。"
        )
    import anthropic

    client = anthropic.Anthropic()
    conn = connect()
    pending = pending_posts(conn, hours)
    print(f"待分類貼文：{len(pending)}  版本：{CLASSIFIER_VERSION}")

    total, all_unresolved = 0, []
    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i:i + BATCH_SIZE]
        try:
            results = classify_batch(client, batch)
        except Exception as exc:                      # noqa: BLE001 - 單批失敗不該中斷整天
            print(f"  ! 第 {i // BATCH_SIZE + 1} 批失敗：{exc}")
            continue
        with conn:
            stored, unresolved = store(conn, results)
        total += stored
        all_unresolved.extend(unresolved)
        print(f"  批次 {i // BATCH_SIZE + 1}: {len(batch)} 篇 → {stored} 個訊號")

    print(f"\n寫入訊號：{total}")
    if all_unresolved:
        print(f"無法解析的代碼（需要補 ticker_aliases.json）：{sorted(set(all_unresolved))}")
    conn.close()


if __name__ == "__main__":
    main()
