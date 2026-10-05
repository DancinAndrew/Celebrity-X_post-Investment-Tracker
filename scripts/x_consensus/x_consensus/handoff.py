"""把分類工作交給「正在跟你對話的 Claude Code session」而不是 API。

為什麼有這條路：分類只有在**無人值守排程**時才非得走 API 金鑰不可。
你人在終端機前面的時候，session 本身就是分類器，不需要另外開帳單。

流程：
    python3 -m x_consensus.handoff export     # 匯出待分類貼文
    # → Claude 讀 .data/handoff/pending.md，寫出 .data/handoff/answers_*.json
    python3 -m x_consensus.handoff apply      # 匯入答案、解析代碼、寫入 signals

答案檔格式（每個檔一個陣列，可以拆成多個檔分批寫）：
    [{"post_id": "...", "is_list_or_market_wide": false,
      "signals": [{"symbol_as_written": "AMD", "company_name": "Advanced Micro Devices",
                   "market_guess": "US", "stance": "bullish", "tone": "positive",
                   "confidence": 0.85, "reason_zh": "...", "evidence_quote": "..."}]}]

stance 只有 bullish / bearish / unclear 三種，是唯一進共識計算的欄位，標準要嚴。
tone 是 positive / negative / neutral，只顯示不投票，標準可以寬。
判準見 `01_Projects/X觀點共識追蹤/判準.md`。

與 classify.py 共用同一套 ticker 解析、signals 結構與 post_classifications 紀錄，
所以兩條路徑產出的資料可以互換，只有 classifier_version 不同。
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import DATA_DIR, connect, compatible_versions
from .tickers import extract_candidates, resolve

HANDOFF_DIR = DATA_DIR / "handoff"
PENDING = HANDOFF_DIR / "pending.md"
VERSION = "claude-code-session/v1"


# 回填時用來預篩：沒有 $代碼、沒有六碼數字、也沒提到常見公司名的貼文，
# 不可能產生個股訊號，送給模型只是燒額度。平常排程不預篩，每篇都分類。
NAME_HINTS = re.compile(
    r"\b(nvidia|jensen|amd|intel|micron|hynix|samsung|tsmc|broadcom|marvell|qualcomm|apple|"
    r"google|alphabet|meta|microsoft|amazon|tesla|palantir|oracle|coreweave|nebius|sandisk|"
    r"lumentum|coherent|arm|asml|applied materials|lam research|kioxia|cambricon|huawei|"
    r"smic|softbank|sony|toyota|netflix|salesforce|adobe|shopify|robinhood|coinbase|"
    r"microstrategy|strategy inc|berkshire|jpmorgan|goldman)\b|三星|海力士|台積電|輝達|美光",
    re.I,
)


def export(hours: int, version: str, limit: int | None = None,
           types: list[str] | None = None, require_candidates: bool = False,
           max_chars: int | None = None, handles: list[str] | None = None,
           out_path: str | None = None, truncate: int | None = None) -> int:
    conn = connect()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    versions = compatible_versions(version)
    placeholders = ",".join("?" for _ in versions)
    rows = conn.execute(
        f"""SELECT p.post_id, p.author_handle, p.created_at_utc, p.text, p.kind,
                  p.symbols_json, a.account_type, a.focus
           FROM raw_posts p JOIN accounts a ON a.handle = p.author_handle
           WHERE p.created_at_utc > ? AND p.is_pinned = 0 AND a.enabled = 1
             AND NOT EXISTS (SELECT 1 FROM post_classifications c
                             WHERE c.post_id = p.post_id AND c.classifier_version IN ({placeholders}))
           ORDER BY p.created_at_utc DESC""",
        (cutoff, *versions),
    ).fetchall()
    conn.close()
    if types:
        rows = [r for r in rows if r["account_type"] in types]
    if handles:
        # 平行回填時每個 worker 負責互斥的帳號，保證不會兩個 session 分類同一篇
        wanted = {h.lower() for h in handles}
        rows = [r for r in rows if r["author_handle"].lower() in wanted]
    if require_candidates:
        rows = [r for r in rows
                if extract_candidates(r["text"], json.loads(r["symbols_json"]))
                or NAME_HINTS.search(r["text"])]
    if limit:
        rows = rows[:limit]          # 由新到舊取前 N 篇：回填時先補最近的歷史
    if max_chars:
        # 依字數切批：貼文長度從幾十字到四千字都有，用篇數切會讓長文批次逾時
        # （實測 80 篇約 9 萬字 15 分鐘沒跑完）
        kept, total = [], 0
        for r in rows:
            if kept and total + len(r["text"]) > max_chars:
                break
            kept.append(r); total += len(r["text"])
        rows = kept
    rows = sorted(rows, key=lambda r: (r["author_handle"], r["created_at_utc"]))

    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    out = [
        f"# 待分類貼文：{len(rows)} 篇（窗口 {hours} 小時，版本 {version}）",
        "",
        "每篇都要在答案裡出現一次，即使沒有任何個股訊號（signals 給空陣列）。",
        "",
        "每個訊號要分開標 stance（bullish/bearish/unclear，進共識計算，從嚴）"
        "與 tone（positive/negative/neutral，只顯示不投票，可從寬）。",
        "嘲諷產品的立場是 unclear、語氣是 negative。"
        "判準見 `01_Projects/X觀點共識追蹤/判準.md`。",
        "",
    ]
    current = None
    for row in rows:
        if row["author_handle"] != current:
            current = row["author_handle"]
            out += ["", f"## @{current}（{row['account_type']}）— {row['focus']}", ""]
        candidates = extract_candidates(row["text"], json.loads(row["symbols_json"]))
        text = row["text"].replace("\n", " ⏎ ")
        if truncate and len(text) > truncate:
            # 長文多半是引用整篇報導；作者自己的判斷通常在開頭。回填時截斷省時間與額度
            text = text[:truncate] + " …（截斷）"
        out += [
            f"### {row['post_id']} · {row['created_at_utc'][:16]} · {row['kind']}"
            + (f" · regex 候選: {', '.join(candidates)}" if candidates else ""),
            text,
            "",
        ]
    target = Path(out_path) if out_path else PENDING
    target.write_text("\n".join(out), encoding="utf-8")
    print(f"匯出 {len(rows)} 篇 → {target}")
    return len(rows)


STANCES = ("bullish", "bearish", "unclear")
TONES = ("positive", "negative", "neutral")


def validate(strict: bool = True, only: str | None = None, pending: str | None = None) -> int:
    """檢查答案檔是否可以安全套用。回傳 0 代表通過。

    自動化管線會把模型輸出直接寫進資料庫，所以這一關必須存在：
    格式壞掉、post_id 對不上、立場值不合法的答案一旦寫進去，
    共識數字就錯了而且不會報錯。寧可停下來等人處理。
    """
    problems: list[str] = []
    pending_ids: set[str] = set()
    pending_path = Path(pending) if pending else PENDING
    if not pending_path.exists():
        print(f"待分類檔不存在，無法驗證：{pending_path}")
        return 1
    pending_ids = set(re.findall(r"^### (\d+) ", pending_path.read_text(encoding="utf-8"), re.M))

    # 只驗指定檔案：自動化每輪只該為自己的產出負責。
    # 掃全部會把先前已套用的舊檔也算進來，它們的 post_id 本來就不在
    # 這一輪的待辦清單裡，會被誤判成幻覺。
    files = [Path(only)] if only else sorted(HANDOFF_DIR.glob("answers*.json"))
    files = [f for f in files if f.exists()]
    if not files:
        print("沒有答案檔可驗證")
        return 1

    seen: set[str] = set()
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: JSON 解析失敗 {exc}")
            continue
        if not isinstance(payload, list):
            problems.append(f"{path.name}: 最外層必須是陣列")
            continue
        for i, item in enumerate(payload):
            where = f"{path.name}[{i}]"
            if not isinstance(item, dict) or "post_id" not in item:
                problems.append(f"{where}: 缺少 post_id")
                continue
            post_id = str(item["post_id"])
            if post_id in seen:
                problems.append(f"{where}: 重複 post_id {post_id}")
            seen.add(post_id)
            if not isinstance(item.get("signals"), list):
                problems.append(f"{where}: signals 必須是陣列")
                continue
            for sig in item.get("signals") or []:
                if not isinstance(sig, dict):
                    problems.append(f"{where}: 訊號必須是物件")
                    continue
                for field in ("symbol_as_written", "stance", "reason_zh"):
                    if not sig.get(field):
                        problems.append(f"{where} {post_id}: 訊號缺少 {field}")
                if sig.get("stance") not in STANCES:
                    problems.append(f"{where} {post_id}: stance 非法值 {sig.get('stance')!r}")
                if sig.get("tone") and sig["tone"] not in TONES:
                    problems.append(f"{where} {post_id}: tone 非法值 {sig.get('tone')!r}")
                conf = sig.get("confidence", 0.7)
                if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
                    problems.append(f"{where} {post_id}: confidence 超出 0-1：{conf!r}")

    if pending_path.exists():
        # 幻覺出來的 post_id 是最危險的一種錯：它會安靜地對不到任何貼文
        ghost = sorted(seen - pending_ids)
        missing = sorted(pending_ids - seen)
        if ghost:
            problems.append(f"答案含 {len(ghost)} 個待辦清單裡沒有的 post_id：{ghost[:5]}")
        if strict and missing:
            problems.append(f"有 {len(missing)} 篇待辦沒有出現在答案裡：{missing[:5]}")

    if problems:
        print(f"驗證未通過，{len(problems)} 個問題：")
        for msg in problems[:20]:
            print(f"  - {msg}")
        return 1
    print(f"驗證通過：{len(files)} 個檔案、{len(seen)} 篇貼文")
    return 0


def apply(version: str, only: str | None = None) -> None:
    files = [Path(only)] if only else sorted(HANDOFF_DIR.glob("answers*.json"))
    if not files:
        raise SystemExit(f"找不到 {HANDOFF_DIR}/answers*.json")

    items: list[dict] = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items.extend(payload if isinstance(payload, list) else payload.get("results", []))

    conn = connect()
    now = datetime.now(timezone.utc).isoformat()
    known = {r["post_id"] for r in conn.execute("SELECT post_id FROM raw_posts")}

    rows, done, unresolved, unknown = [], {}, [], []
    seen: set[str] = set()
    for item in items:
        post_id = str(item["post_id"])
        if post_id in seen:
            conn.close()
            raise ValueError(f'Duplicate post_id: {post_id}')
        seen.add(post_id)
        if post_id not in known:
            unknown.append(post_id)          # 打錯 id 要吵出來，不要安靜吞掉
            continue
        done.setdefault(post_id, 0)
        if item.get("is_list_or_market_wide"):
            continue
        for sig in item.get("signals", []):
            key = resolve(sig["symbol_as_written"], sig.get("company_name"), sig.get("market_guess"))
            if not key:
                unresolved.append(f"{sig['symbol_as_written']} / {sig.get('company_name')}")
                continue
            rows.append((post_id, key, sig["stance"], sig.get("tone", "neutral"),
                         float(sig.get("confidence", 0.7)), sig["reason_zh"],
                         sig.get("evidence_quote"), version, now))
            done[post_id] = done[post_id] + 1

    if unknown or unresolved:
        conn.close()
        raise ValueError(f'Unknown posts or unresolved tickers: {unknown[:5]} / {unresolved[:5]}')
    try:
        with conn:
            new_ids: set[str] = set()
            for pid in done:
                previous = conn.execute('SELECT 1 FROM post_classifications WHERE post_id=? AND classifier_version=?', (pid, version)).fetchone()
                expected = [tuple(r[:-1]) for r in rows if r[0] == pid]
                if len({r[1] for r in expected}) != len(expected):
                    raise ValueError(f'Duplicate stock signal: {pid}')
                if previous:
                    existing = [tuple(r) for r in conn.execute('''SELECT post_id,ticker_key,stance,tone,confidence,
                        reason_zh,evidence_quote,classifier_version FROM signals WHERE post_id=? AND classifier_version=?''', (pid, version))]
                    if sorted(existing,key=repr) != sorted(expected,key=repr):
                        raise ValueError(f'Conflicting answer for existing version: {pid}/{version}')
                else:
                    new_ids.add(pid)
            conn.executemany(
                """INSERT INTO signals
                   (post_id, ticker_key, stance, tone, confidence, reason_zh, evidence_quote,
                    classifier_version, classified_at_utc) VALUES (?,?,?,?,?,?,?,?,?)""",
                [r for r in rows if r[0] in new_ids],
            )
            conn.executemany(
                """INSERT INTO post_classifications
                   (post_id, classifier_version, classified_at_utc, signal_count) VALUES (?,?,?,?)""",
                [(pid, version, now, n) for pid, n in done.items() if pid in new_ids],
            )
    finally:
        conn.close()

    print(f"讀入答案檔 {len(files)} 個，貼文 {len(done)} 篇 → 訊號 {len(rows)} 個")
    if unknown:
        print(f"! 找不到對應貼文的 post_id（{len(unknown)}）：{unknown[:5]}")
    if unresolved:
        print(f"! 無法解析的代碼（需補 ticker_aliases.json）：{sorted(set(unresolved))}")


def main() -> None:
    parser = argparse.ArgumentParser(description="把分類交給 Claude Code session")
    sub = parser.add_subparsers(dest="cmd", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--hours", type=int, default=26)
    exp.add_argument("--version", default=VERSION)
    exp.add_argument("--limit", type=int, default=None, help="每批最多幾篇（回填用，由新到舊）")
    exp.add_argument("--types", default=None, help="只匯出這些帳號型別，逗號分隔")
    exp.add_argument("--require-candidates", action="store_true",
                     help="只匯出含股票代碼或常見公司名的貼文（回填用）")
    exp.add_argument("--max-chars", type=int, default=None, help="每批最多幾個字元（回填用）")
    exp.add_argument("--handles", default=None, help="只匯出這些帳號，逗號分隔（平行回填用）")
    exp.add_argument("--out", default=None, help="待分類檔輸出路徑（平行回填用）")
    exp.add_argument("--truncate", type=int, default=None, help="每篇最多保留幾個字元")
    app = sub.add_parser("apply")
    app.add_argument("--version", default=VERSION)
    app.add_argument("--file", default=None, help="只套用指定的答案檔")
    val = sub.add_parser("validate")
    val.add_argument("--loose", action="store_true",
                     help="不要求每篇待辦都出現在答案裡")
    val.add_argument("--file", default=None, help="只驗證指定的答案檔")
    val.add_argument("--pending", default=None, help="對照的待分類檔路徑")
    args = parser.parse_args()
    if args.cmd == "export":
        export(args.hours, args.version, args.limit,
               args.types.split(",") if args.types else None, args.require_candidates,
               args.max_chars, args.handles.split(",") if args.handles else None,
               args.out, args.truncate)
    elif args.cmd == "validate":
        raise SystemExit(validate(strict=not args.loose, only=args.file, pending=args.pending))
    else:
        apply(args.version, args.file)


if __name__ == "__main__":
    main()
