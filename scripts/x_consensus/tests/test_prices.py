import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
from x_consensus import prices


class Series:
    def __init__(self, values):
        self.values = values
    def dropna(self):
        return self
    def items(self):
        return self.values


class PriceRepairTests(unittest.TestCase):
    def test_unfinished_us_session_is_not_a_close(self):
        rows = Series([(datetime(2026,10,6),100),(datetime(2026,10,7),110)])
        meta = {'exchangeTimezoneName':'America/New_York','currentTradingPeriod':{'regular':{'end':int(datetime(2026,10,7,20,tzinfo=timezone.utc).timestamp())}}}
        self.assertEqual(prices.complete_rows(rows,meta,datetime(2026,10,7,13,tzinfo=timezone.utc)),[('2026-10-06',100)])
        self.assertEqual(prices.complete_rows(rows,meta,datetime(2026,10,7,20,16,tzinfo=timezone.utc)),[('2026-10-06',100),('2026-10-07',110)])

    def test_asian_market_has_its_own_session_date(self):
        rows = Series([(datetime(2026,10,7),10),(datetime(2026,10,8),12)])
        meta = {'exchangeTimezoneName':'Asia/Tokyo','currentTradingPeriod':{'regular':{'end':int(datetime(2026,10,7,6,30,tzinfo=timezone.utc).timestamp())}}}
        self.assertEqual(prices.complete_rows(rows,meta,datetime(2026,10,7,13,tzinfo=timezone.utc)),[('2026-10-07',10)])

    def test_processed_datetime_session_metadata(self):
        rows=Series([(datetime(2026,10,6),100),(datetime(2026,10,7),110)])
        meta={'exchangeTimezoneName':'America/New_York','currentTradingPeriod':{'regular':{'end':datetime(2026,10,7,20,tzinfo=timezone.utc)}}}
        self.assertEqual(prices.complete_rows(rows,meta,datetime(2026,10,7,13,tzinfo=timezone.utc)),[('2026-10-06',100)])

    def test_unknown_timezone_and_bad_prices_are_rejected(self):
        rows = Series([(datetime(2026,10,6),-5),(datetime(2026,10,5),float('inf'))])
        self.assertEqual(prices.complete_rows(rows,{'exchangeTimezoneName':'UTC'},datetime(2026,10,7,tzinfo=timezone.utc)),[])
        with self.assertRaises(ValueError):prices.complete_rows(rows,{},datetime.now(timezone.utc))

    def test_spcx_cannot_receive_the_old_spac_etf(self):
        with self.assertRaises(ValueError):
            prices.check_identity('US:SPCX','SPCX',{'symbol':'SPCX','longName':'The SPAC and New Issue ETF','currency':'USD'})
        prices.check_identity('US:SPCX','SPCX',{'symbol':'SPCX','longName':'Space Exploration Technologies Corp.','currency':'USD'})
        with self.assertRaises(ValueError):prices.check_identity('US:SIVE','SIVE',{})

    def test_revisions_preserve_old_values_and_replay_is_idempotent(self):
        db = sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE prices(ticker_key TEXT,date TEXT,close REAL,PRIMARY KEY(ticker_key,date))')
        db.execute("INSERT INTO prices VALUES('US:META','2026-10-05',95)")
        prices.ensure_price_audit(db)
        args=(db,'US:META','META',[('2026-10-05',100),('2026-10-06',105)],{'exchangeTimezoneName':'America/New_York'},'batch','2026-10-07T13:00:00Z')
        self.assertEqual(prices.persist_rows(*args),(1,1,0))
        self.assertEqual(prices.persist_rows(*args),(0,0,2))
        self.assertEqual(db.execute('SELECT previous_close FROM price_revisions').fetchone()[0],95)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM price_observations').fetchone()[0],2)
        db.close()

    def test_rate_limit_stops_all_remaining_tickers(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE prices(ticker_key TEXT,date TEXT,close REAL,PRIMARY KEY(ticker_key,date))')
        yf=MagicMock();yf.Ticker.return_value.history.side_effect=RuntimeError('Too Many Requests. Rate limited.')
        with tempfile.TemporaryDirectory() as tmp, patch.object(prices,'DATA_DIR',Path(tmp)),patch.object(prices,'connect',return_value=db),patch.dict('sys.modules',{'yfinance':yf}):
            n,missing=prices.fetch(keys=['US:META','US:AMD'])
            self.assertEqual(n,0);self.assertEqual(missing,['US:META','US:AMD']);self.assertEqual(yf.Ticker.call_count,1)


if __name__=='__main__':unittest.main()
