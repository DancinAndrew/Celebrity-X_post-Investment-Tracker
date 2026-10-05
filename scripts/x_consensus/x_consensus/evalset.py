"""分類器評測：由使用者裁決，不是由模型自己打分。

為什麼是「裁決」而不是「從零標註」：
Cohen's κ 衡量的是「模型」與「你」的一致程度。如果兩邊都由模型標，
κ 只是在量模型跟自己一致，沒有意義。所以這裡把模型的判斷與依據先列好，
你只需要逐項說同意或不同意——工作量從標 150 篇降到裁決數十列。

也不是全部訊號都值得裁決。只有**意見帳號**的訊號會影響共識結論
（新聞、選擇權流向、交易揭露帳號不投票），所以優先排它們；
再抽一部分「我判定沒有訊號」的貼文，用來抓漏標。

    python3 -m x_consensus.evalset export     # 產生 .data/eval/adjudication.md
    # 你填每個區塊的「裁決」欄
    python3 -m x_consensus.evalset score      # 算 κ、precision/recall、漏標

裁決怎麼填：
  A 區（我標了訊號）：空白＝同意；或寫 bullish / bearish / unclear / none
                      （none 表示這裡根本不該有訊號）
  B 區（我判定無訊號）：空白＝同意；或寫 `US:AMD=bullish` 這種格式補上漏標，
                      多筆用逗號分隔
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
import os
from pathlib import Path

from .db import DATA_DIR, connect, window_cutoff

EVAL_DIR = DATA_DIR / "eval"                      # 機器用的中繼資料
# 要人填的檔案放在 vault 裡看得見的地方。`.data/` 以點開頭，
# Obsidian 不會顯示，放在那裡等於叫使用者去終端機編輯。
OUT_ROOT = Path(os.environ.get("XC_OUT_ROOT")
                or Path(__file__).resolve().parents[3] / "01_Projects" / "X觀點共識追蹤")
REVIEW_DIR = OUT_ROOT / "評測"
ADJUDICATION = REVIEW_DIR / "adjudication.md"
STANCES = ("bullish", "bearish", "unclear", "none")
DEFAULT_VERSION = "claude-code-session/v1"
MISS_SAMPLE = 15


def _headline_tickers(conn, version: str) -> set[str]:
    """出現在共識結論（共同看多／看空／分歧）裡的個股，優先裁決。"""
    from .aggregate import consensus

    data = consensus(conn, 26, version)
    keys = set()
    for bucket in ("shared_bullish", "shared_bearish", "split"):
        keys.update(e["ticker"] for e in data[bucket])
    return keys


def export(version: str, hours: int, seed: int = 20260911) -> None:
    conn = connect()
    headline = _headline_tickers(conn, version)

    signals = conn.execute(
        """SELECT s.post_id, s.ticker_key, s.stance, s.tone, s.confidence, s.reason_zh,
                  s.evidence_quote, p.author_handle, p.url, p.text, a.account_type
           FROM signals s
           JOIN raw_posts p ON p.post_id = s.post_id
           JOIN accounts a ON a.handle = p.author_handle
           WHERE s.classifier_version = ? AND a.counts_toward_consensus = 1
             AND p.created_at_utc > ?
           ORDER BY p.author_handle, s.ticker_key""",
        (version, window_cutoff(hours)),
    ).fetchall()
    # 影響共識結論的排前面，其次是低信心的
    ranked = sorted(
        signals,
        key=lambda r: (r["ticker_key"] not in headline, r["confidence"]),
    )

    silent = conn.execute(
        """SELECT p.post_id, p.author_handle, p.url, p.text
           FROM raw_posts p JOIN accounts a ON a.handle = p.author_handle
           JOIN post_classifications c ON c.post_id = p.post_id
           WHERE c.classifier_version = ? AND c.signal_count = 0
             AND a.counts_toward_consensus = 1 AND p.is_pinned = 0
             AND p.created_at_utc > ?""",
        (version, window_cutoff(hours)),
    ).fetchall()
    rng = random.Random(seed)
    sample = rng.sample(list(silent), min(MISS_SAMPLE, len(silent)))
    conn.close()

    def clip(text: str, n: int = 300) -> str:
        flat = text.replace("\n", " ⏎ ")
        return flat[:n] + ("…" if len(flat) > n else "")

    lines = [
        f"# 分類裁決 · 版本 `{version}`",
        "",
        f"A 區 {len(ranked)} 列（意見帳號訊號，影響共識結論者排前面）、"
        f"B 區 {len(sample)} 列（抽查漏標）。",
        "",
        "> [!important] 只有**立場**進共識計算，語氣只顯示不投票。",
        "> 所以裁決時問的是「這個立場對不對」，不是「這個語氣對不對」。",
        "",
        "判準的完整說明與理由在 [[判準]]。**先看那份文件的第 1 條**——"
        "立場與語氣為什麼分開兩欄、嘲諷產品為什麼不算看空。",
        "如果你不同意那條判準本身，就不必逐列改：直接說，我改判準再全部重跑。",
        "",
        "**怎麼填**：",
        "- A 區：空白＝同意。不同意就寫 `bullish` / `bearish` / `unclear`，"
        "或寫 `none` 表示這裡根本不該有訊號。",
        "- B 區：空白＝同意（確實沒有個股訊號）。有漏標就寫 `US:AMD=bullish`，"
        "多筆用逗號分隔。",
        "- 填完執行 `python3 -m x_consensus.evalset score`。",
        "",
        "---",
        "",
    ]

    # 時間不夠時的最小可行裁決：我自己最沒把握的那幾列。
    shaky = [f"A{i}" for i, r in enumerate(ranked, 1) if r["confidence"] < 0.5]
    if shaky:
        lines += [
            "> [!tip] 時間不夠就只做這幾列",
            f"> 我信心低於 0.5 的判斷：{'、'.join(shaky)}。"
            "這些是最可能標錯、也最值得你花時間的。",
            "",
        ]

    lines += ["## A 區：我標了訊號，請裁決", ""]
    for i, row in enumerate(ranked, 1):
        flag = " ⭐ 影響共識結論" if row["ticker_key"] in headline else ""
        lines += [
            f"### A{i} · {row['ticker_key']} · @{row['author_handle']}{flag}",
            f"- 我判：立場 **{row['stance']}** ／ 語氣 **{row['tone'] or 'neutral'}**"
            f"（信心 {row['confidence']:.2f}）",
            f"- 依據：{row['reason_zh']}",
            f"- 引文：`{clip(row['evidence_quote'] or '', 160)}`",
            f"- 原文：{clip(row['text'])}",
            f"- 連結：{row['url']}",
            f"- **裁決**: ",
            "",
        ]

    lines += ["---", "", "## B 區：我判定這幾篇沒有個股訊號，請抽查", ""]
    for i, row in enumerate(sample, 1):
        lines += [
            f"### B{i} · @{row['author_handle']}",
            f"- 原文：{clip(row['text'], 400)}",
            f"- 連結：{row['url']}",
            f"- **裁決**: ",
            "",
        ]

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    ADJUDICATION.write_text("\n".join(lines), encoding="utf-8")
    (EVAL_DIR / "_meta.json").write_text(
        json.dumps(
            {
                "version": version,
                "a_rows": [
                    {"id": f"A{i}", "post_id": r["post_id"], "ticker_key": r["ticker_key"],
                     "model_stance": r["stance"]}
                    for i, r in enumerate(ranked, 1)
                ],
                "b_rows": [
                    {"id": f"B{i}", "post_id": r["post_id"]} for i, r in enumerate(sample, 1)
                ],
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"A 區 {len(ranked)} 列、B 區 {len(sample)} 列 → {ADJUDICATION}")


def _parse() -> tuple[dict[str, str], dict[str, str]]:
    if not ADJUDICATION.exists():
        raise SystemExit(f"找不到 {ADJUDICATION}，先跑 export。")
    text = ADJUDICATION.read_text(encoding="utf-8")
    verdicts: dict[str, str] = {}
    current = None
    for line in text.splitlines():
        header = re.match(r"^### ([AB]\d+) ", line)
        if header:
            current = header.group(1)
            continue
        got = re.match(r"^- \*\*裁決\*\*:\s*(.*)$", line)
        if got and current:
            verdicts[current] = got.group(1).strip()
            current = None
    a = {k: v for k, v in verdicts.items() if k.startswith("A")}
    b = {k: v for k, v in verdicts.items() if k.startswith("B")}
    return a, b


def _kappa(pairs: list[tuple[str, str]]) -> float:
    if not pairs:
        return 0.0
    n = len(pairs)
    observed = sum(1 for x, y in pairs if x == y) / n
    left, right = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    expected = sum((left[s] / n) * (right[s] / n) for s in STANCES)
    return 1.0 if expected >= 1 else (observed - expected) / (1 - expected)


def score() -> None:
    meta = json.loads((EVAL_DIR / "_meta.json").read_text(encoding="utf-8"))
    a_verdicts, b_verdicts = _parse()
    by_id = {r["id"]: r for r in meta["a_rows"]}

    pairs: list[tuple[str, str]] = []
    disagreements = []
    for row_id, model in ((r["id"], r["model_stance"]) for r in meta["a_rows"]):
        verdict = a_verdicts.get(row_id, "")
        if verdict == "":
            # 空白＝同意。但整份都空白代表根本沒填，下面會擋掉
            human = model
        elif verdict.split()[0] in STANCES:
            human = verdict.split()[0]
        else:
            print(f"  ! {row_id} 裁決欄看不懂：{verdict!r}，當作同意處理")
            human = model
        pairs.append((human, model))
        if human != model:
            info = by_id[row_id]
            disagreements.append((row_id, info["ticker_key"], model, human))

    filled = sum(1 for v in a_verdicts.values() if v != "")
    if filled == 0:
        raise SystemExit(
            "A 區裁決欄全是空白。空白代表『同意』，但整份沒填代表還沒裁決過——\n"
            "請先填完再計分，否則 κ 會是 1.0 而毫無意義。"
        )

    misses = [(k, v) for k, v in b_verdicts.items() if v]
    for _ in misses:
        pairs.append(("bullish", "none"))       # 漏標：人有、模型沒有

    print(f"分類器版本：{meta['version']}")
    print(f"A 區 {len(meta['a_rows'])} 列，其中 {filled} 列被明確改過")
    print(f"B 區抽查 {len(meta['b_rows'])} 列，回報漏標 {len(misses)} 列")
    print(f"\nCohen's κ：{_kappa(pairs):.3f}   （≥0.6 可用；<0.4 等於雜訊）")
    print(f"逐列一致率：{sum(1 for x, y in pairs if x == y) / len(pairs):.1%}\n")

    for stance in ("bullish", "bearish", "unclear"):
        tp = sum(1 for h, m in pairs if h == stance and m == stance)
        fp = sum(1 for h, m in pairs if h != stance and m == stance)
        fn = sum(1 for h, m in pairs if h == stance and m != stance)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        print(f"  {stance:<8} precision={p:.2f} recall={r:.2f} (tp={tp} fp={fp} fn={fn})")

    if disagreements:
        print(f"\n你不同意的 {len(disagreements)} 列：")
        for row_id, ticker, model, human in disagreements:
            print(f"    {row_id} {ticker:<14} 我判 {model:<8} → 你判 {human}")
    if misses:
        print(f"\n漏標回報：")
        for row_id, value in misses:
            print(f"    {row_id}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="分類器評測（使用者裁決）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--version", default=DEFAULT_VERSION)
    exp.add_argument("--hours", type=int, default=26)
    sub.add_parser("score")
    args = parser.parse_args()
    if args.cmd == "export":
        export(args.version, args.hours)
    else:
        score()


if __name__ == "__main__":
    main()
