"""從揭露型貼文抽出「誰買賣了什麼」，餵給交易者權重模型。

沿用 handoff 那一套：export 出待抽取檔 → session 讀完寫 JSON → apply 入庫。
與立場分類分開，因為問的問題不同：立場問「作者怎麼看」，
揭露問「貼文報導了誰的哪一筆交易」。作者本人的意見在這裡無關。

    python3 -m x_consensus.disclosure export
    python3 -m x_consensus.disclosure apply
    python3 -m x_consensus.disclosure score
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .db import DATA_DIR, connect, window_cutoff, compatible_versions
from .tickers import resolve
from .traders import leaderboard, load_config, recompute_scores, upsert_trader

WORK_DIR = DATA_DIR / "disclosure"
PENDING = WORK_DIR / "pending.md"
# v2（2026-09-13）：新增 trade_date。v1 只記揭露日，「2 月 2 日買進」這種交易
# 會被畫在 9 月的時間線上。換版本會讓所有揭露型貼文重新抽取一次。
VERSION = "claude-code-session/disc-v2"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DIRECTIONS = ("buy", "sell", "short", "cover")
CATEGORIES = ("politician", "institution", "insider", "executive")


def slugify(name: str) -> str:
    """'Nancy Pelosi' → 'pelosi-nancy'。姓在前，讓同姓的人排在一起。"""
    clean = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", clean) if p]
    if len(parts) >= 2:
        parts = [parts[-1]] + parts[:-1]
    return "-".join(p.lower() for p in parts) or "unknown"


def export(hours: int, limit: int | None = None, require_candidates: bool = False,
           max_chars: int | None = None, version: str = VERSION) -> int:
    conn = connect()
    versions = compatible_versions(version)
    placeholders = ",".join("?" for _ in versions)
    rows = conn.execute(
        f"""SELECT p.post_id, p.author_handle, p.created_at_utc, p.text
           FROM raw_posts p JOIN accounts a ON a.handle = p.author_handle
           WHERE a.account_type IN ('trade_disclosure', 'options_flow') AND a.enabled=1
             AND p.is_pinned = 0 AND p.created_at_utc > ?
             AND NOT EXISTS (SELECT 1 FROM post_classifications c
                             WHERE c.post_id = p.post_id AND c.classifier_version IN ({placeholders}))
           ORDER BY p.created_at_utc DESC""",
        (window_cutoff(hours), *versions),
    ).fetchall()
    if require_candidates:
        from .handoff import NAME_HINTS
        from .tickers import extract_candidates
        rows = [r for r in rows if extract_candidates(r["text"], []) or NAME_HINTS.search(r["text"])]
    if limit:
        rows = rows[:limit]
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
    conn.close()

    lines = [
        f"# 待抽取揭露事件：{len(rows)} 篇（窗口 {hours} 小時）",
        "",
        "抽出「這篇報導了誰的哪一筆交易」。作者本人的意見無關，這裡只要事實。",
        "",
        "- 沒有具體交易事件的貼文（純新聞、總經、宣傳）→ events 給空陣列。",
        f"- direction 只能是 {' / '.join(DIRECTIONS)}。",
        f"- category 只能是 {' / '.join(CATEGORIES)}。",
        "- 機構（ARK、Berkshire）用機構名當 trader；個別基金經理人若有具名則用人名。",
        "- symbol_as_written 填**股票代碼**。原文只寫公司名沒寫 $代碼時（例：「Kura Sushi」），",
        "  填你確定的上市代碼（KRUS）並把公司名寫進 company_name；",
        "  不確定是否上市、或不確定代碼，就不要建事件，寧缺勿猜。",
        "",
        "**交易日（trade_date）最重要，也最容易錯：**",
        "",
        "- 每篇標題的時間是「貼文日」，不是交易日。「Trump bought Kura Sushi on Feb 2」",
        "  這篇 9 月才發，交易日是 2 月 2 日。",
        "- trade_date 填實際成交日，格式 `YYYY-MM-DD`。原文沒寫年份時，用貼文日推回",
        "  最近一次、且不晚於貼文日的那個日期（9 月的貼文寫 Feb 2 → 同年 2 月 2 日；",
        "  1 月的貼文寫 Dec 15 → 前一年 12 月 15 日）。",
        "- 原文是區間（「Jan–Jun」「last quarter」）→ trade_date 填區間起點，",
        "  trade_date_text 照抄原文寫法。只寫月份（「in July」）→ 填該月 1 日。",
        "- 原文只寫申報日（「filed on」「just filed」）沒寫成交日 → trade_date 給 null，",
        "  把申報資訊寫進 trade_date_text（例：「filed Sep 9」）。",
        "- 完全沒提到任何日期 → trade_date 與 trade_date_text 都給 null。**不要拿貼文日充數。**",
        "- trade_date 絕對不能晚於貼文日。",
        "",
        "答案寫成 `.data/disclosure/events_*.json`：",
        "```json",
        '[{"post_id":"...","events":[{"trader_name":"Maria Salazar","category":"politician",',
        '  "symbol_as_written":"SPCX","company_name":"SpaceX","market_guess":"US",',
        '  "direction":"buy","amount_text":"two purchases","trade_date":"2026-02-02",',
        '  "trade_date_text":"Feb 2","confidence":0.9}]}]',
        "```",
        "",
        "---",
        "",
    ]
    current = None
    for row in rows:
        if row["author_handle"] != current:
            current = row["author_handle"]
            lines += ["", f"## @{current}", ""]
        text = row["text"].replace("\n", " ⏎ ")
        lines += [f"### {row['post_id']} · {row['created_at_utc'][:16]}", text, ""]

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text("\n".join(lines), encoding="utf-8")
    print(f"匯出 {len(rows)} 篇 → {PENDING}")
    return len(rows)


def _valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate(only: str | None = None) -> int:
    """檢查揭露答案檔是否可以安全套用。回傳 0 代表通過。

    與 handoff.validate 同一個理由：自動化管線會把模型輸出直接寫進資料庫，
    幻覺出來的 post_id、不合法的 direction/category 一旦寫進去，
    交易者權重就悄悄錯了。寧可停下來等人處理。
    """
    problems: list[str] = []
    pending_ids: set[str] = set()
    if not PENDING.exists():
        print(f"待抽取檔不存在，無法驗證：{PENDING}")
        return 1
    if PENDING.exists():
        pending_ids = set(re.findall(r"^### (\d+) ", PENDING.read_text(encoding="utf-8"), re.M))

    files = [Path(only)] if only else sorted(WORK_DIR.glob("events_*.json"))
    files = [f for f in files if f.exists()]
    if not files:
        print("沒有答案檔可驗證")
        return 1

    conn = connect()
    post_dates = {r["post_id"]: r["created_at_utc"][:10]
                  for r in conn.execute("SELECT post_id, created_at_utc FROM raw_posts")}
    conn.close()

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
            if not isinstance(item.get("events"), list):
                problems.append(f"{where}: events 必須是陣列")
                continue
            for ev in item.get("events") or []:
                if not isinstance(ev, dict):
                    problems.append(f"{where}: 事件必須是物件")
                    continue
                for field in ("trader_name", "category", "symbol_as_written", "direction"):
                    if not ev.get(field):
                        problems.append(f"{where} {post_id}: 事件缺少 {field}")
                if ev.get("direction") not in DIRECTIONS:
                    problems.append(f"{where} {post_id}: direction 非法值 {ev.get('direction')!r}")
                if ev.get("category") not in CATEGORIES:
                    problems.append(f"{where} {post_id}: category 非法值 {ev.get('category')!r}")
                conf = ev.get("confidence", 0.7)
                if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
                    problems.append(f"{where} {post_id}: confidence 超出 0-1：{conf!r}")
                td = ev.get("trade_date")
                if td is not None:
                    if not isinstance(td, str) or not DATE_RE.match(td):
                        problems.append(f"{where} {post_id}: trade_date 格式錯誤 {td!r}")
                    elif not _valid_date(td):
                        problems.append(f"{where} {post_id}: trade_date 日期不存在 {td!r}")
                    elif post_id in post_dates and td > post_dates[post_id]:
                        # 交易不可能晚於報導它的貼文——這是模型把年份推錯的典型症狀
                        problems.append(f"{where} {post_id}: trade_date {td} 晚於貼文日 "
                                        f"{post_dates[post_id]}")
                    elif td < "2000-01-01":
                        problems.append(f"{where} {post_id}: trade_date 不合理 {td}")

    if PENDING.exists():
        missing = sorted(pending_ids - seen)
        if missing:
            problems.append(f"有 {len(missing)} 篇待辦沒有出現在答案裡：{missing[:5]}")
        ghost = sorted(seen - pending_ids)
        if ghost:
            problems.append(f"答案含 {len(ghost)} 個待辦清單裡沒有的 post_id：{ghost[:5]}")

    if problems:
        print(f"驗證未通過，{len(problems)} 個問題：")
        for msg in problems[:20]:
            print(f"  - {msg}")
        return 1
    print(f"驗證通過：{len(files)} 個檔案、{len(seen)} 篇貼文")
    return 0


def apply(only: str | None = None, version: str = VERSION) -> None:
    files = [Path(only)] if only else sorted(WORK_DIR.glob("events_*.json"))
    files = [f for f in files if f.exists()]
    if not files:
        raise SystemExit(f"找不到 {WORK_DIR}/events_*.json")

    items: list[dict] = []
    for path in files:
        items.extend(json.loads(path.read_text(encoding="utf-8")))

    conn = connect()
    cfg = load_config()
    now = datetime.now(timezone.utc).isoformat()
    times = {r["post_id"]: r["created_at_utc"]
             for r in conn.execute("SELECT post_id, created_at_utc FROM raw_posts")}

    stored, skipped, unresolved, replayed = 0, [], [], 0
    scanned: dict[str, int] = {}
    seen: set[str] = set()
    columns = 'trader_key,ticker_key,direction,disclosed_at,amount_text,confidence,trade_date,trade_date_text'
    try:
        with conn:
            for item in items:
                post_id = str(item["post_id"])
                if post_id in seen:
                    raise ValueError(f'Duplicate post_id: {post_id}')
                seen.add(post_id)
                if post_id not in times:
                    raise ValueError(f'Unknown post_id: {post_id}')
                prepared = []
                identities: set[tuple] = set()
                for ev in item.get('events', []):
                    if ev['direction'] not in DIRECTIONS or ev['category'] not in CATEGORIES:
                        raise ValueError(f'Invalid event: {post_id}')
                    ticker = resolve(ev['symbol_as_written'], ev.get('company_name'), ev.get('market_guess'))
                    if not ticker:
                        raise ValueError(f'Unresolved ticker: {post_id}/{ev["symbol_as_written"]}')
                    trader_key = slugify(ev['trader_name'])
                    # An unknown exact date can still have a distinct source
                    # period ("in two days" versus "back in mid-May"). Keep
                    # the literal period, without inventing a calendar date.
                    period = ev.get('trade_date') or 'unknown'
                    if period == 'unknown' and ev.get('trade_date_text'):
                        import hashlib
                        literal = ' '.join(ev['trade_date_text'].split())
                        period += '-' + hashlib.sha256(literal.encode()).hexdigest()[:16]
                    identity = (trader_key, ticker, ev['direction'], period)
                    if identity in identities:
                        raise ValueError(f'Duplicate event identity: {post_id}/{identity}')
                    identities.add(identity)
                    fields = (trader_key, ticker, ev['direction'], times[post_id], ev.get('amount_text'),
                              float(ev.get('confidence', .7)), ev.get('trade_date'), ev.get('trade_date_text'))
                    prepared.append((ev, fields, period))
                previous = conn.execute('SELECT signal_count FROM post_classifications WHERE post_id=? AND classifier_version=?',
                                        (post_id, version)).fetchone()
                if previous:
                    existing = [tuple(r) for r in conn.execute(f'SELECT {columns} FROM disclosure_events WHERE post_id=? AND extractor_version=?',
                                                               (post_id, version))]
                    if sorted(existing, key=repr) != sorted([fields for _, fields, _ in prepared], key=repr):
                        raise ValueError(f'Conflicting answer for existing version: {post_id}/{version}')
                    replayed += 1
                    continue
                for ev, fields, period in prepared:
                    trader_key, ticker, direction = fields[:3]
                    if not conn.execute('SELECT 1 FROM traders WHERE trader_key=?', (trader_key,)).fetchone():
                        upsert_trader(conn, trader_key, ev['trader_name'], ev['category'], cfg)
                    # Version and transaction date prevent overwriting another extraction.
                    event_id = f'{post_id}:{trader_key}:{ticker}:{direction}:{version}:{period}'
                    conn.execute('''INSERT INTO disclosure_events
                        (event_id,post_id,trader_key,ticker_key,direction,disclosed_at,amount_text,confidence,
                         extractor_version,extracted_at,trade_date,trade_date_text)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (event_id,post_id,*fields[:6],version,now,*fields[6:]))
                    stored += 1
                scanned[post_id] = len(prepared)
                conn.execute('INSERT INTO post_classifications VALUES(?,?,?,?)',
                             (post_id,version,now,len(prepared)))
    finally:
        conn.close()
    print(f"讀入 {len(files)} 個答案檔 → 新揭露事件 {stored} 筆、原樣重跑 {replayed} 篇")
    if unresolved:
        print(f"! 代碼解不出來：{sorted(set(unresolved))}")
    if skipped:
        print(f"! 跳過 {len(skipped)} 筆（post_id 不存在或欄位值不合法）")


def score() -> None:
    conn = connect()
    with conn:
        results = recompute_scores(conn)
    cfg = load_config()
    print(f"重算 {len(results)} 位交易者的權重"
          f"（收縮強度 α={cfg['shrinkage_alpha']}，前瞻 {cfg['forward_days']} 天）\n")
    print(f"  {'交易者':<22} {'類別':<12} {'先驗':>5} {'事件':>4} {'計分':>4} {'權重':>6}  來源")
    for row in leaderboard(conn):
        print(f"  {row['display_name'][:20]:<22} {row['category']:<12} "
              f"{row['prior_weight']:>5.2f} {row['n_events'] or 0:>4} {row['n_scored'] or 0:>4} "
              f"{(row['weight'] or row['prior_weight']):>6.3f}  {row['weight_source']}")
    scored = sum((r["n_scored"] or 0) for r in leaderboard(conn))
    if scored == 0:
        print("\n注意：還沒有任何事件滿 30 天且有價格資料，")
        print("      所以目前所有權重都等於先驗值，不含任何實績成分。")
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="揭露事件抽取與交易者權重")
    sub = parser.add_subparsers(dest="cmd", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--version", default=VERSION)
    exp.add_argument("--hours", type=int, default=72)
    exp.add_argument("--limit", type=int, default=None, help="每批最多匯出幾篇（回填用）")
    exp.add_argument("--require-candidates", action="store_true", help="只匯出含股票代碼或公司名的貼文")
    exp.add_argument("--max-chars", type=int, default=None, help="每批最多幾個字元（回填用）")
    app = sub.add_parser("apply")
    app.add_argument("--version", default=VERSION)
    app.add_argument("--file", default=None, help="只套用指定的答案檔")
    val = sub.add_parser("validate")
    val.add_argument("--file", default=None, help="只驗證指定的答案檔")
    sub.add_parser("score")
    args = parser.parse_args()
    if args.cmd == "export":
        export(args.hours, args.limit, args.require_candidates, args.max_chars, args.version)
    elif args.cmd == "apply":
        apply(args.file, args.version)
    elif args.cmd == "validate":
        raise SystemExit(validate(args.file))
    else:
        score()


if __name__ == "__main__":
    main()
