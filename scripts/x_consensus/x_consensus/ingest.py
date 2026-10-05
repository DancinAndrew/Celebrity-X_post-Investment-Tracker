"""把 .data/raw/ 的 payload 與 .data/runs/ 的抓取狀態寫進 SQLite。

冪等：重跑同一天的資料不會產生重複列。
"""
from __future__ import annotations

import json
import argparse
import sqlite3
from pathlib import Path

from .db import DATA_DIR, connect
from .normalize import parse_file

HOME = Path(__file__).resolve().parent.parent


def load_accounts(conn: sqlite3.Connection) -> None:
    cfg = json.loads((HOME / "accounts.json").read_text(encoding="utf-8"))
    conn.executemany(
        """INSERT INTO accounts (handle, display_name, account_type, focus, counts_toward_consensus,
                                 enabled, disabled_reason)
           VALUES (:handle, :display_name, :account_type, :focus, :counts, :enabled, :disabled_reason)
           ON CONFLICT(handle) DO UPDATE SET
             display_name=excluded.display_name,
             account_type=excluded.account_type,
             focus=excluded.focus,
             counts_toward_consensus=excluded.counts_toward_consensus,
             enabled=excluded.enabled, disabled_reason=excluded.disabled_reason""",
        [
            {
                "handle": a["handle"],
                "display_name": a["display_name"],
                "account_type": a["account_type"],
                "focus": a["focus"],
                "counts": int(a["counts_toward_consensus"]),
                "enabled": int(a.get("enabled", True)),
                "disabled_reason": a.get("disabled_reason"),
            }
            for a in cfg["accounts"]
        ],
    )


def source_directories() -> list[Path]:
    """Recover the old fetch destination without moving or rewriting raw files."""
    return list(dict.fromkeys([DATA_DIR.resolve(), (HOME / ".data").resolve()]))


def ingest_runs(conn: sqlite3.Connection, source_dirs: list[Path] | None = None) -> int:
    count = 0
    paths = sorted({p for root in (source_dirs or source_directories())
                    for p in (root / "runs").glob("*.json")})
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        for acct in report.get("accounts", []):
            conn.execute(
                """INSERT OR REPLACE INTO fetch_runs
                   (run_id, handle, started_at_utc, status, tweets, oldest_utc, newest_utc, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report["run_id"],
                    acct["handle"],
                    report["started_at_utc"],
                    acct["status"],
                    acct.get("tweets", 0),
                    acct.get("oldest"),
                    acct.get("newest"),
                    acct.get("note"),
                ),
            )
            count += 1
    return count


def ingest_raw(conn: sqlite3.Connection, source_dirs: list[Path] | None = None) -> tuple[int, int]:
    """回傳 (解析到的貼文數, 新寫入的貼文數)。"""
    parsed = 0
    before = conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
    day_dirs = sorted({p for root in (source_dirs or source_directories())
                       for p in (root / "raw").glob("*") if p.is_dir()})
    for day_dir in day_dirs:
        if not day_dir.is_dir():
            continue
        for path in sorted(day_dir.glob("*.json")):
            handle = path.stem.split("__")[0]
            try:
                rows = parse_file(path, handle)
            except (json.JSONDecodeError, OSError) as exc:
                print(f"  ! 解析失敗 {path.name}: {exc}")
                continue
            parsed += len(rows)
            conn.executemany(
                """INSERT OR IGNORE INTO raw_posts
                   (post_id, author_handle, created_at_utc, text, lang, kind,
                    original_post_id, original_author, conversation_id, is_pinned,
                    symbols_json, url, source, fetched_at_utc)
                   VALUES (:post_id, :author_handle, :created_at_utc, :text, :lang, :kind,
                           :original_post_id, :original_author, :conversation_id, :is_pinned,
                           :symbols_json, :url, :source, :fetched_at_utc)""",
                rows,
            )
    after = conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
    return (parsed, after - before)


def main() -> None:
    parser = argparse.ArgumentParser(description="冪等補入抓取資料，保留原始檔")
    parser.add_argument("--source-dir", action="append", type=Path,
                        help="額外原始資料根目錄，可重複指定")
    args = parser.parse_args()
    sources = list(dict.fromkeys(source_directories() +
                                [p.resolve() for p in (args.source_dir or [])]))
    print("資料來源：" + ", ".join(str(p) for p in sources))
    conn = connect()
    with conn:
        load_accounts(conn)
        runs = ingest_runs(conn, sources)
        parsed, added = ingest_raw(conn, sources)
    print(f"fetch_runs 列: {runs}")
    print(f"解析貼文: {parsed}  新寫入: {added}")
    total = conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
    print(f"raw_posts 總計: {total}")
    conn.close()


if __name__ == "__main__":
    main()
