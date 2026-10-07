"""Fetch completed, split/dividend-adjusted daily bars with per-key evidence.

No guessed prices or instruments. Preserve old values in revisions, stop on
rate limits, and report missing or unsupported keys instead of exit-zero success.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from .db import DATA_DIR, connect
from .tickers import yfinance_symbol

LOOKBACK_DAYS = 420
SPECIAL_IDENTITIES = {
    'US:PENG': ('penguin', 'USD', None),
    'US:SPCX': ('space exploration', 'USD', '2026-06-12'),
    'STO:SIVE': ('sivers', 'SEK', None),
    'US:BITF': ('keel', 'USD', None),
    'US:SATS': ('echostar', 'USD', None),
    'US:BRR': ('silvia', 'USD', None),
    'US:VSCO': ('victoria', 'USD', None),
    # Keep only the verified post-combination BRUN sessions. Earlier WLAC
    # SPAC prices remain a separate historical gap, not invented continuity.
    'US:WLAC': ('boost run', 'USD', '2026-05-11'),
    'LSE:RPI': ('raspberry pi', 'GBp', None),
    'AMS:BESI': ('be semiconductor', 'EUR', None),
    'XETRA:IFX': ('infineon', 'EUR', None),
    'XETRA:BMW': ('bayerische', 'EUR', None),
    'XETRA:LPK': ('lpkf', 'EUR', None),
    'XETRA:MBG': ('mercedes', 'EUR', None),
    'XETRA:WAF': ('siltronic', 'EUR', None),
    'EPA:KER': ('kering', 'EUR', None),
    'EPA:MC': ('lvmh', 'EUR', None),
    'EPA:RMS': ('herm', 'EUR', None),
    'EPA:SOI': ('soitec', 'EUR', None),
    'VI:ATS': ('austria', 'EUR', None),
    'EPA:HO': ('thales', 'EUR', None),
    'TSXV:PNG': ('kraken', 'CAD', None),
    'SWX:NESN': ('nestl', 'CHF', None),
    'SWX:AMS': ('osram', 'CHF', None),
    'SWX:ABBN': ('abb', 'CHF', None),
    'SWX:KNIN': ('kuehne', 'CHF', None),
    'XETRA:P911': ('porsche ag', 'EUR', None),
}
PROVIDER_ALIASES = {
    'US:BITF': {'symbol': 'KEEL', 'effective_date': '2026-04-06',
                'exchange_ratio': '1:1', 'evidence_url': 'https://investor.bitfarms.com/news-releases/news-release-details/bitfarms-officially-rebrands-keel-infrastructure-completes-us'},
    'US:SATS': {'symbol': 'ECHO', 'effective_date': '2026-06-24',
                'exchange_ratio': 'unchanged share capital and CUSIP', 'evidence_url': 'https://ir.echostar.com/news-releases/news-release-details/echostar-changing-stocker-ticker-sats-echo-marking-companys-next'},
    'US:BRR': {'symbol': 'SVIA', 'effective_date': '2026-09-22',
                'exchange_ratio': 'unchanged rights; existing certificates remain valid', 'evidence_url': 'https://investors.cfosilvia.com/news-releases/news-release-details/silvia-inc-begins-trading-nasdaq-under-new-ticker-svia'},
    'US:VSCO': {'symbol': 'VSXY', 'effective_date': '2026-06-02',
                'exchange_ratio': 'unchanged common stock and CUSIP; no shareholder action',
                'evidence_url': 'https://victoriassecret.gcs-web.com/news-releases/news-release-details/victorias-secret-co-change-ticker-symbol-vsxy-marking-next'},
    'US:WLAC': {'symbol': 'BRUN', 'effective_date': '2026-05-11',
                'exchange_ratio': 'one WLAC Class A share converted into one Boost Run Class A share at May 8 closing',
                'evidence_url': 'https://investors.boostrun.com/news-releases/news-release-details/boost-run-brun-begins-trading-nasdaq-940-million-contracted',
                'continuity_evidence_url': 'https://www.sec.gov/Archives/edgar/data/2090646/000149315226031923/forms-1.htm',
                'history_limit': 'Only verified post-combination sessions from 2026-05-11 are cached; earlier SPAC prices are not supplied by this mapping'},
}


def wanted_tickers(conn: sqlite3.Connection) -> list[str]:
    return [r['ticker_key'] for r in conn.execute('''
        SELECT DISTINCT ticker_key FROM (
          SELECT ticker_key FROM identity_checked_signals
          UNION SELECT ticker_key FROM active_disclosure_events
        ) ORDER BY ticker_key''')]


def complete_rows(series, metadata: dict, now: datetime) -> list[tuple[str, float]]:
    """Keep exchange-local session dates; exclude future and unfinished bars."""
    zone_name = metadata.get('exchangeTimezoneName')
    if not zone_name:
        raise ValueError('missing_exchange_timezone')
    zone = ZoneInfo(zone_name)
    today = now.astimezone(zone).date()
    regular = metadata.get('currentTradingPeriod', {}).get('regular', {})
    close_epoch = regular.get('end')
    # yfinance 1.7 formats these values as timezone-aware pandas Timestamps;
    # older versions leave Unix seconds. Both describe the same actual session.
    if hasattr(close_epoch, 'timestamp'):
        close_epoch = close_epoch.timestamp()
    session_date = datetime.fromtimestamp(close_epoch, zone).date() if close_epoch else None
    # Fifteen-minute grace prevents treating an unfinished/delayed current bar
    # as a finalized daily close. No missing holiday is invented as a data hole.
    today_complete = bool(close_epoch and session_date == today and now.timestamp() >= close_epoch + 900)
    rows = []
    for index, value in series.dropna().items():
        bar_date = index.date()
        if bar_date > today or (bar_date == today and not today_complete):
            continue
        close = float(value)
        if not math.isfinite(close) or close <= 0:
            continue
        rows.append((bar_date.isoformat(), close))
    return rows


def check_identity(key: str, symbol: str, metadata: dict) -> None:
    if key == 'US:SIVE':
        raise ValueError('unverified_US_SIVE_excluded')
    actual = metadata.get('symbol')
    if actual and actual.upper() != symbol.upper():
        raise ValueError('provider_symbol_mismatch')
    if key in SPECIAL_IDENTITIES:
        name, currency, _ = SPECIAL_IDENTITIES[key]
        provider_name = (metadata.get('longName') or metadata.get('shortName') or '').lower()
        if name not in provider_name or metadata.get('currency') != currency:
            raise ValueError('verified_issuer_name_or_currency_mismatch')


def ensure_price_audit(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS price_revisions (
        batch_id TEXT NOT NULL, ticker_key TEXT NOT NULL, date TEXT NOT NULL,
        previous_close REAL NOT NULL, replacement_close REAL NOT NULL,
        observed_at_utc TEXT NOT NULL, PRIMARY KEY(batch_id,ticker_key,date)
      );
      CREATE TABLE IF NOT EXISTS price_observations (
        batch_id TEXT NOT NULL, ticker_key TEXT NOT NULL, date TEXT NOT NULL,
        adjusted_close REAL NOT NULL, provider_symbol TEXT NOT NULL,
        exchange_timezone TEXT NOT NULL, fetched_at_utc TEXT NOT NULL,
        adjustment TEXT NOT NULL, PRIMARY KEY(batch_id,ticker_key,date)
      );
    ''')


def persist_rows(conn, key, symbol, rows, metadata, batch_id, fetched_at):
    before = {r['date']: r['close'] for r in conn.execute('SELECT date,close FROM prices WHERE ticker_key=?', (key,))}
    inserted, revised, unchanged = 0, 0, 0
    with conn:
        for date, close in rows:
            old = before.get(date)
            if old == close:
                unchanged += 1
                continue
            if old is None:
                inserted += 1
            else:
                revised += 1
                conn.execute('INSERT OR IGNORE INTO price_revisions VALUES(?,?,?,?,?,?)',
                             (batch_id,key,date,old,close,fetched_at))
            conn.execute('INSERT OR REPLACE INTO prices VALUES(?,?,?)', (key,date,close))
            conn.execute('INSERT OR IGNORE INTO price_observations VALUES(?,?,?,?,?,?,?,?)',
                         (batch_id,key,date,close,symbol,metadata['exchangeTimezoneName'],fetched_at,'auto_adjust=True'))
    return inserted, revised, unchanged


def safe_error(error):
    value = str(error).replace('\n', ' ')[:400]
    return re.sub(r'(crumb|token|cookie|Authorization)=\S+', r'\1=[redacted]', value, flags=re.I)


def fetch(limit: int | None = None, keys: list[str] | None = None) -> tuple[int, list[str]]:
    import yfinance as yf
    history_options = {}
    if hasattr(yf, 'config') and hasattr(yf.config, 'debug'):
        yf.config.debug.hide_exceptions = False
    else:
        history_options['raise_errors'] = True

    conn = connect()
    conn.execute('PRAGMA busy_timeout=30000')
    ensure_price_audit(conn)
    tickers = keys if keys is not None else wanted_tickers(conn)
    tickers = list(dict.fromkeys(tickers))
    if limit:
        tickers = tickers[:limit]
    batch_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    archive = DATA_DIR / 'prices' / 'applied' / batch_id
    archive.mkdir(parents=True, exist_ok=True)
    status = {'batch_id': batch_id, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'provider': 'yfinance', 'adjustment': 'auto_adjust=True', 'wanted': len(tickers),
              'inserted': 0, 'revised': 0, 'unchanged': 0, 'results': [], 'state': 'running'}
    missing = []
    now = datetime.now(timezone.utc)
    start = (now.date() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    end = (now.date() + timedelta(days=1)).isoformat()
    rate_limited = False
    network_blocked = False
    consecutive_network_failures = 0
    for index, key in enumerate(tickers):
        result = {'ticker_key': key, 'state': 'missing', 'attempts': 0}
        symbol = PROVIDER_ALIASES.get(key, {}).get('symbol') or yfinance_symbol(key)
        result['provider_symbol'] = symbol
        if not symbol or key == 'US:SIVE':
            result.update(state='blocked_identity', reason='unverified_or_unsupported_market')
        elif rate_limited:
            result.update(state='not_attempted', reason='earlier_rate_limit_stopped_run')
        elif network_blocked:
            result.update(state='not_attempted', reason='network_circuit_open_after_three_failures')
        else:
            # Serial bounded requests avoid the previous hundreds-of-threads
            # burst. Retry only one transient connection failure; never 429,
            # missing/delisted data, identity mismatches, or invalid responses.
            for attempt in range(2):
                result['attempts'] = attempt + 1
                try:
                    instrument = yf.Ticker(symbol)
                    data = instrument.history(start=start, end=end, interval='1d',
                                              auto_adjust=True, prepost=False,
                                              repair=False, timeout=15, **history_options)
                    metadata = instrument.get_history_metadata()
                    check_identity(key, symbol, metadata)
                    rows = complete_rows(data['Close'], metadata, datetime.now(timezone.utc))
                    minimum = SPECIAL_IDENTITIES.get(key, ('', '', None))[2]
                    if minimum:
                        rows = [(date, close) for date, close in rows if date >= minimum]
                    if not rows:
                        raise ValueError('no_completed_daily_bars')
                    fetched = datetime.now(timezone.utc).isoformat()
                    meta = {k:metadata.get(k) for k in ('symbol','longName','shortName','currency','exchangeName','exchangeTimezoneName','instrumentType','firstTradeDate','regularMarketTime','currentTradingPeriod')}
                    evidence = {'ticker_key':key,'provider_symbol':symbol,'provider_alias':PROVIDER_ALIASES.get(key),'fetched_at_utc':fetched,'start':start,'end_exclusive':end,'adjustment':'auto_adjust=True','metadata':meta,'rows':rows}
                    (archive / (key.replace(':','_') + '.json')).write_text(json.dumps(evidence,ensure_ascii=False,indent=2,default=lambda value:value.isoformat())+'\n')
                    before = conn.execute('SELECT MAX(date) FROM prices WHERE ticker_key=?', (key,)).fetchone()[0]
                    inserted, revised, unchanged = persist_rows(conn,key,symbol,rows,metadata,batch_id,fetched)
                    status['inserted'] += inserted; status['revised'] += revised; status['unchanged'] += unchanged
                    result.update(state='filled', available_daily_bars=len(rows), before_latest=before,
                                  latest_completed_bar=rows[-1][0], inserted=inserted,
                                  revised=revised, unchanged=unchanged, exchange_timezone=metadata['exchangeTimezoneName'])
                    consecutive_network_failures = 0
                    break
                except Exception as error:
                    reason = safe_error(error)
                    result['reason'] = reason
                    if 'rate limit' in reason.lower() or '429' in reason or type(error).__name__ == 'YFRateLimitError':
                        rate_limited = True
                        result['state'] = 'blocked_rate_limit'
                        break
                    transient = any(t in reason.lower() for t in ('resolve host','timed out','timeout','connection','curl: (6)','curl: (28)'))
                    if transient and attempt:
                        consecutive_network_failures += 1
                        network_blocked = consecutive_network_failures >= 3
                    if not transient or attempt:
                        break
                    time.sleep(2)
        if result['state'] != 'filled':
            missing.append(key)
        status['results'].append(result)
        (archive/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
        if result['state'] == 'filled' and (keys is not None or (index+1)%25 == 0):
            print(f"{index+1}/{len(tickers)} {key}: {result['latest_completed_bar']} new={result['inserted']} revised={result['revised']}",flush=True)
        if not rate_limited and not network_blocked and symbol:
            time.sleep(0.35)
    status.update(finished_at_utc=datetime.now(timezone.utc).isoformat(),
                  state='partial' if missing else 'applied', missing=missing)
    encoded = json.dumps(status,ensure_ascii=False,indent=2)+'\n'
    (archive/'status.json').write_text(encoded)
    target = DATA_DIR/'prices/last_status.json'
    temporary = target.with_suffix('.tmp'); temporary.write_text(encoded); temporary.replace(target)
    conn.close()
    print(f"價格新增 {status['inserted']} 列；修訂 {status['revised']} 列（舊值保留）；相同 {status['unchanged']} 列；缺口 {len(missing)} 檔。",flush=True)
    return status['inserted'] + status['revised'], missing


def window_return(conn: sqlite3.Connection, ticker_key: str, days: int) -> float | None:
    rows = conn.execute('''SELECT date,close FROM prices WHERE ticker_key=?
                          AND date>=date('now',?) ORDER BY date''', (ticker_key,f'-{days} days')).fetchall()
    if len(rows) < 2 or not rows[0]['close']:
        return None
    # A stale cache must not silently generate a current-window return.
    if (datetime.now(timezone.utc).date() - datetime.fromisoformat(rows[-1]['date']).date()).days > 5:
        return None
    return (rows[-1]['close'] - rows[0]['close']) / rows[0]['close']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tickers', help='Comma-separated canonical market:symbol keys')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    keys = [key.strip() for key in args.tickers.split(',') if key.strip()] if args.tickers else None
    _, missing = fetch(args.limit,keys)
    if missing:
        print(f'未完成的價格標的：{missing[:20]}。完整逐檔原因見 data/prices/last_status.json。')
    raise SystemExit(1 if missing else 0)


if __name__ == '__main__':
    main()
