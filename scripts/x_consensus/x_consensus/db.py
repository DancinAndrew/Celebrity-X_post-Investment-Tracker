"""SQLite schema 與連線。

Markdown 與 raw JSON 是 source of truth；這個資料庫是 derived state，
砍掉可以從 .data/raw/ 完全重建。
"""
from __future__ import annotations

import os
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

# launchd 代理讀不到 ~/Documents（macOS 檔案保護），所以執行副本會放在
# ~/Library/Application Support/xconsensus。路徑用環境變數覆寫，
# 同一份程式碼才能在兩個位置都跑。
DATA_DIR = Path(os.environ.get("XC_DATA_DIR")
                or Path(__file__).resolve().parent.parent / ".data")
DB_PATH = DATA_DIR / "x_consensus.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  handle                  TEXT PRIMARY KEY,
  display_name            TEXT,
  account_type            TEXT NOT NULL,
  focus                   TEXT,
  enabled                 INTEGER NOT NULL DEFAULT 1,
  disabled_reason         TEXT,
  counts_toward_consensus INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS raw_posts (
  post_id          TEXT PRIMARY KEY,
  author_handle    TEXT NOT NULL,
  created_at_utc   TEXT NOT NULL,
  text             TEXT NOT NULL,
  lang             TEXT,
  kind             TEXT NOT NULL,          -- original | retweet | quote | reply
  original_post_id TEXT,
  original_author  TEXT,
  conversation_id  TEXT,
  is_pinned        INTEGER NOT NULL DEFAULT 0,
  symbols_json     TEXT NOT NULL DEFAULT '[]',
  url              TEXT,
  source           TEXT NOT NULL,
  fetched_at_utc   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_author_time ON raw_posts(author_handle, created_at_utc);
CREATE INDEX IF NOT EXISTS idx_raw_time ON raw_posts(created_at_utc);

CREATE TABLE IF NOT EXISTS signals (
  post_id            TEXT NOT NULL,
  ticker_key         TEXT NOT NULL,
  stance             TEXT NOT NULL,        -- bullish | bearish | unclear（只有這個進共識計算）
  tone               TEXT,                 -- positive | negative | neutral（只顯示，不投票）
  confidence         REAL NOT NULL,
  reason_zh          TEXT NOT NULL,
  evidence_quote     TEXT,
  classifier_version TEXT NOT NULL,
  classified_at_utc  TEXT NOT NULL,
  PRIMARY KEY (post_id, ticker_key, classifier_version)
);
CREATE INDEX IF NOT EXISTS idx_sig_ticker ON signals(ticker_key);

-- Preserve source rows while excluding an identifier whose market is wrong.
CREATE TABLE IF NOT EXISTS ticker_identity_exclusions (
  ticker_key TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  evidence_url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signal_identity_overrides (
  post_id TEXT NOT NULL,
  classifier_version TEXT NOT NULL,
  original_ticker_key TEXT NOT NULL,
  canonical_ticker_key TEXT,
  reason TEXT NOT NULL,
  evidence_quote TEXT NOT NULL,
  evidence_url TEXT,
  review_sha256 TEXT NOT NULL,
  PRIMARY KEY(post_id,classifier_version,original_ticker_key)
);
INSERT OR IGNORE INTO ticker_identity_exclusions VALUES (
  'US:SIVE', 'Sivers is listed in Stockholm; this US key is unverified.',
  'https://www.nasdaq.com/european-market-activity/shares/sive?id=TX2540138'
);
CREATE VIEW IF NOT EXISTS identity_checked_signals AS
SELECT s.post_id, COALESCE(o.canonical_ticker_key,s.ticker_key) AS ticker_key,
       s.stance,s.tone,s.confidence,s.reason_zh,s.evidence_quote,
       s.classifier_version,s.classified_at_utc
FROM signals s LEFT JOIN signal_identity_overrides o
ON o.post_id=s.post_id AND o.classifier_version=s.classifier_version
   AND o.original_ticker_key=s.ticker_key
WHERE (o.post_id IS NULL OR o.canonical_ticker_key IS NOT NULL) AND NOT EXISTS (
  SELECT 1 FROM ticker_identity_exclusions x WHERE x.ticker_key=s.ticker_key
);

-- 記錄「這篇已經用這個版本分類過」，與「這篇有幾個訊號」分開。
-- 沒有這張表的話，真的沒提到任何個股的貼文會因為 signals 查不到而
-- 每天被重送給模型，安靜地重複計費。
CREATE TABLE IF NOT EXISTS post_classifications (
  post_id            TEXT NOT NULL,
  classifier_version TEXT NOT NULL,
  classified_at_utc  TEXT NOT NULL,
  signal_count       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (post_id, classifier_version)
);

CREATE TABLE IF NOT EXISTS tickers (
  ticker_key      TEXT PRIMARY KEY,        -- 'NASDAQ:AMD' | 'KRX:005930'
  symbol          TEXT NOT NULL,
  name            TEXT,
  market          TEXT NOT NULL,
  yfinance_symbol TEXT,
  aliases_json    TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS prices (
  ticker_key TEXT NOT NULL,
  date       TEXT NOT NULL,
  close      REAL NOT NULL,
  PRIMARY KEY (ticker_key, date)
);

-- ── 交易者權重模型 ─────────────────────────────────────────────
-- 被追蹤的「交易者」本人（政治人物、機構、內部人），不是 X 帳號。
CREATE TABLE IF NOT EXISTS traders (
  trader_key    TEXT PRIMARY KEY,        -- 'trump-donald'
  display_name  TEXT NOT NULL,
  category      TEXT NOT NULL,           -- politician | institution | insider | executive
  prior_weight  REAL NOT NULL,
  weight_source TEXT NOT NULL,           -- user_directive | category_default
  notes         TEXT,
  first_seen    TEXT
);

-- 從揭露型貼文抽出的單筆交易事件。
CREATE TABLE IF NOT EXISTS disclosure_events (
  event_id     TEXT PRIMARY KEY,         -- post_id:trader_key:ticker_key:direction
  post_id      TEXT NOT NULL,
  trader_key   TEXT NOT NULL,
  ticker_key   TEXT NOT NULL,
  direction    TEXT NOT NULL,            -- buy | sell | short | cover
  disclosed_at TEXT NOT NULL,            -- 貼文時間＝我們得知的時間，不是成交時間
  amount_text  TEXT,
  confidence   REAL NOT NULL,
  extractor_version TEXT NOT NULL,
  extracted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_disc_trader ON disclosure_events(trader_key);
CREATE INDEX IF NOT EXISTS idx_disc_ticker ON disclosure_events(ticker_key);

CREATE VIEW IF NOT EXISTS session_disclosure_classifications AS
SELECT post_id, classifier_version FROM (
  SELECT c.*, ROW_NUMBER() OVER (
    PARTITION BY post_id ORDER BY
      CASE WHEN classifier_version LIKE '%/disc-v2' THEN 2 ELSE 1 END DESC,
      classified_at_utc DESC, classifier_version DESC
  ) AS position
  FROM post_classifications c WHERE classifier_version IN (
    'claude-code-session/disc-v1', 'claude-code-session/disc-v2', 'codex-session/disc-v2'
  )
) WHERE position=1;
CREATE VIEW IF NOT EXISTS active_disclosure_events AS
SELECT e.* FROM disclosure_events e
LEFT JOIN session_disclosure_classifications c ON c.post_id=e.post_id
WHERE (c.post_id IS NULL OR c.classifier_version=e.extractor_version)
AND NOT EXISTS (SELECT 1 FROM ticker_identity_exclusions x WHERE x.ticker_key=e.ticker_key);

-- 由 disclosure_events + prices 算出的實績與權重。可整表重算。
CREATE TABLE IF NOT EXISTS trader_scores (
  trader_key      TEXT PRIMARY KEY,
  n_events        INTEGER NOT NULL,
  n_scored        INTEGER NOT NULL,      -- 已滿 30 天、能算報酬的事件數
  n_hits          INTEGER NOT NULL,
  shrunk_hit_rate REAL NOT NULL,
  credibility     REAL NOT NULL,
  weight          REAL NOT NULL,
  computed_at     TEXT NOT NULL
);

-- 每次抓取的結果。儀表板要讀它，才能把「今天沒發文」跟「抓取失敗」分開。
CREATE TABLE IF NOT EXISTS fetch_runs (
  run_id      TEXT NOT NULL,
  handle      TEXT NOT NULL,
  started_at_utc TEXT NOT NULL,
  status      TEXT NOT NULL,               -- ok | partial | failed
  tweets      INTEGER NOT NULL DEFAULT 0,
  oldest_utc  TEXT,
  newest_utc  TEXT,
  note        TEXT,
  PRIMARY KEY (run_id, handle)
);

-- Both sessions use the unchanged v1 rubric. Keep provenance and choose one
-- classification per post; disclosure extraction never enters this view.
CREATE VIEW IF NOT EXISTS session_v1_classifications AS
SELECT post_id, classifier_version, classified_at_utc, signal_count FROM (
  SELECT c.*, ROW_NUMBER() OVER (
    PARTITION BY post_id ORDER BY classified_at_utc DESC, classifier_version DESC
  ) AS position
  FROM post_classifications c
  WHERE classifier_version IN ('claude-code-session/v1', 'codex-session/v1', 'codex-session/v1-r1', 'codex-session/v1-r2')
) WHERE position = 1;
CREATE VIEW IF NOT EXISTS session_v1_signals AS
SELECT s.* FROM identity_checked_signals s JOIN session_v1_classifications c
ON c.post_id = s.post_id AND c.classifier_version = s.classifier_version;
"""


def compatible_versions(version: str) -> tuple[str, ...]:
    if version in {"claude-code-session/v1", "codex-session/v1", "codex-session/v1-r1", "codex-session/v1-r2"}:
        return ("claude-code-session/v1", "codex-session/v1", "codex-session/v1-r1", "codex-session/v1-r2")
    if version in {"claude-code-session/disc-v2", "codex-session/disc-v2"}:
        return ("claude-code-session/disc-v2", "codex-session/disc-v2")
    return (version,)


def signal_source(version: str) -> str:
    return "session_v1_signals" if version == "session/v1" else "identity_checked_signals"


def backlog_status(conn: sqlite3.Connection) -> list[dict]:
    """Report frozen candidate coverage separately from unresolved identities."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='analysis_scopes'").fetchone():
        return []
    status = []
    for scope in conn.execute('SELECT * FROM analysis_scopes ORDER BY scope_key,kind'):
        rows = conn.execute('''SELECT r.post_id,r.unresolved_json FROM analysis_reviews r
            JOIN analysis_batches b ON b.batch_key=r.batch_key
            WHERE b.scope_key=? AND r.kind=?''',(scope['scope_key'],scope['kind'])).fetchall()
        resolved = set()
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='analysis_identity_resolutions'").fetchone():
            resolved = {(r[0],r[1]) for r in conn.execute(
                'SELECT post_id,original_symbol FROM analysis_identity_resolutions WHERE kind=?',(scope['kind'],))}
        gaps = [[u for u in json.loads(row[1]) if (row[0],u['symbol_as_written']) not in resolved] for row in rows]
        status.append({**dict(scope),'reviewed':len(rows),'remaining':scope['total_posts']-len(rows),
                       'unresolved_references':sum(len(g) for g in gaps),
                       'unresolved_posts':sum(bool(g) for g in gaps)})
    return status


def select_stance_version(conn: sqlite3.Connection) -> str:
    if conn.execute("SELECT 1 FROM post_classifications WHERE "
                    "classifier_version='codex-session/v1' LIMIT 1").fetchone():
        return "session/v1"
    row = conn.execute("SELECT classifier_version v, COUNT(*) n FROM signals "
                       "GROUP BY 1 ORDER BY n DESC LIMIT 1").fetchone()
    return row["v"] if row else "regex-mentions/v1"


def window_cutoff(hours: int) -> str:
    """時間窗口的起點，格式與 raw_posts.created_at_utc 一致。

    必須用這個，不要在 SQL 裡寫 datetime('now', '-N hours')——
    SQLite 產生的是空格分隔（'2026-09-09 22:48:00'），資料庫存的是
    ISO 含 T（'2026-09-09T14:00:00+00:00'）。字串比較時 'T' 大於空格，
    同一天較舊的貼文會被誤判成落在窗口內，讓所有計數靜默偏大。
    """
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _migrate(conn: sqlite3.Connection) -> None:
    """既有資料庫補上後來才加的欄位。CREATE TABLE IF NOT EXISTS 不會改既有表。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(signals)")}
    if "tone" not in cols:
        conn.execute("ALTER TABLE signals ADD COLUMN tone TEXT")

    account_cols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)")}
    if "enabled" not in account_cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
    if "disabled_reason" not in account_cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN disabled_reason TEXT")

    # 交易日與揭露日是兩件事：「川普 2 月 2 日買進」這篇貼文 9 月 7 日才發。
    # disclosed_at 只記得後者，時間線會把 2 月的交易畫在 9 月。
    dcols = {r[1] for r in conn.execute("PRAGMA table_info(disclosure_events)")}
    if "trade_date" not in dcols:
        conn.execute("ALTER TABLE disclosure_events ADD COLUMN trade_date TEXT")      # YYYY-MM-DD，最佳估計
    if "trade_date_text" not in dcols:
        conn.execute("ALTER TABLE disclosure_events ADD COLUMN trade_date_text TEXT") # 原文寫法：「Feb 2」「Jan–Jun」

    identity = conn.execute("SELECT sql FROM sqlite_master WHERE name='identity_checked_signals'").fetchone()
    if identity and ('signal_identity_overrides' not in identity['sql'] or 's.reason,' in identity['sql']):
        conn.execute('DROP VIEW identity_checked_signals')
        begin=SCHEMA.index('CREATE VIEW IF NOT EXISTS identity_checked_signals')
        end=SCHEMA.index('-- 記錄',begin)
        conn.executescript(SCHEMA[begin:end])
    view = conn.execute("SELECT sql FROM sqlite_master WHERE name='session_v1_signals'").fetchone()
    if view and 'identity_checked_signals' not in view['sql']:
        conn.execute('DROP VIEW session_v1_signals')
        conn.execute('''CREATE VIEW session_v1_signals AS
            SELECT s.* FROM identity_checked_signals s JOIN session_v1_classifications c
            ON c.post_id=s.post_id AND c.classifier_version=s.classifier_version''')
    classes = conn.execute("SELECT sql FROM sqlite_master WHERE name='session_v1_classifications'").fetchone()
    if classes and 'codex-session/v1-r2' not in classes['sql']:
        conn.execute('DROP VIEW session_v1_signals')
        conn.execute('DROP VIEW session_v1_classifications')
        conn.executescript(SCHEMA[SCHEMA.index('CREATE VIEW IF NOT EXISTS session_v1_classifications'):])
    conn.commit()


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn
