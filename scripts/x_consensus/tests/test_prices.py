import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
from x_consensus import prices, tickers


class Series:
    def __init__(self, values):
        self.values = values
    def dropna(self):
        return self
    def items(self):
        return self.values


class PriceRepairTests(unittest.TestCase):
    def test_merger_target_cannot_use_the_surviving_issuer_price(self):
        self.assertEqual(prices.PROVIDER_ALIASES['US:EQR']['symbol'], 'VMRK')
        self.assertEqual(prices.SPECIAL_IDENTITIES['US:EQR'][2], '2026-08-18')
        self.assertNotIn('US:AVB', prices.PROVIDER_ALIASES)
        prices.check_identity('US:EQR', 'VMRK', {'symbol': 'VMRK', 'longName': 'Vivmark Residential', 'currency': 'USD'})
        with self.assertRaises(ValueError):
            prices.check_identity('US:EQR', 'VMRK', {'symbol': 'VMRK', 'longName': 'AvalonBay Communities, Inc.', 'currency': 'USD'})

    def test_porsche_ag_preferred_reference_is_not_the_holding_company(self):
        self.assertEqual(tickers.resolve('P911', 'Porsche AG', None), 'XETRA:P911')
        self.assertEqual(tickers.yfinance_symbol('XETRA:P911'), 'P911.DE')
        self.assertIsNone(tickers.resolve('', 'Porsche Automobil Holding SE', None))
        prices.check_identity('XETRA:P911', 'P911.DE', {'symbol': 'P911.DE', 'longName': 'Dr. Ing. h.c. F. Porsche AG', 'currency': 'EUR'})
        with self.assertRaises(ValueError):
            prices.check_identity('XETRA:P911', 'P911.DE', {'symbol': 'P911.DE', 'longName': 'Porsche Automobil Holding SE', 'currency': 'EUR'})

    def test_verified_swiss_codes_keep_exchange_and_currency(self):
        for code, company, name in [('ABBN', 'ABB Ltd', 'ABB Ltd'),
                                     ('KNIN', 'Kuehne+Nagel', 'Kuehne + Nagel International AG')]:
            key = 'SWX:' + code
            self.assertEqual(tickers.resolve(code, company, None), key)
            self.assertEqual(tickers.yfinance_symbol(key), code + '.SW')
            prices.check_identity(key, code + '.SW', {'symbol': code + '.SW', 'longName': name, 'currency': 'CHF'})
            with self.assertRaises(ValueError):
                prices.check_identity(key, code + '.SW', {'symbol': code + '.SW', 'longName': name, 'currency': 'USD'})

    def test_wrong_numeric_market_shape_stays_unresolved(self):
        with patch.object(tickers, 'ALIASES', {}):
            for market in ['US', 'LSE', 'TWSE', 'TSE', 'TPEX', 'HKEX', 'UNKNOWN']:
                self.assertIsNone(tickers.resolve('005930', None, market))
            self.assertEqual(tickers.resolve('005930', None, 'KRX'), 'KRX:005930')
            self.assertEqual(tickers.resolve('688012', None, 'SSE'), 'SSE:688012')
            self.assertIsNone(tickers.resolve('6274', None, None))

    def test_company_abbreviations_cannot_be_numeric_market_tickers(self):
        with patch.object(tickers, 'ALIASES', {}):
            for token, market in [('TEL', 'TSE'), ('NAURA', 'SZSE'), ('AMEC', 'SSE'), ('NMR', 'TSE')]:
                self.assertIsNone(tickers.resolve(token, None, market))
                self.assertIsNone(tickers.yfinance_symbol(f'{market}:{token}'))
        self.assertEqual(tickers.resolve('285A', None, 'TSE'), 'TSE:285A')
        self.assertEqual(tickers.yfinance_symbol('TSE:285A'), '285A.T')
        self.assertEqual(tickers.resolve('RSW', None, 'LSE'), 'LSE:RSW')

    def test_verified_class_and_saudi_aliases_do_not_guess_numeric_market(self):
        self.assertEqual(tickers.resolve('BRK.B', 'Berkshire Hathaway', 'US'), 'US:BRK-B')
        self.assertIsNone(tickers.resolve('', 'Berkshire Hathaway', 'US'))
        self.assertEqual(tickers.resolve('2222', 'Saudi Aramco', None), 'TADAWUL:2222')
        self.assertIsNone(tickers.resolve('2222', None, None))
        self.assertEqual(tickers.yfinance_symbol('TADAWUL:2222'), '2222.SR')

    def test_verified_renamed_provider_preserves_key_and_rejects_wrong_issuer(self):
        self.assertEqual(prices.PROVIDER_ALIASES['US:BITF']['symbol'], 'KEEL')
        prices.check_identity('US:BITF', 'KEEL', {'symbol':'KEEL','longName':'Keel Infrastructure','currency':'USD'})
        prices.check_identity('US:SATS', 'ECHO', {'symbol':'ECHO','longName':'EchoStar Corporation','currency':'USD'})
        self.assertEqual(prices.PROVIDER_ALIASES['US:BRR']['symbol'], 'SVIA')
        prices.check_identity('US:BRR', 'SVIA', {'symbol':'SVIA','longName':'Silvia, Inc.','currency':'USD'})
        prices.check_identity('US:VSCO', 'VSXY', {'symbol':'VSXY','longName':"Victoria's Secret & Co.",'currency':'USD'})
        prices.check_identity('US:WLAC', 'BRUN', {'symbol':'BRUN','longName':'Boost Run Inc.','currency':'USD'})
        with self.assertRaises(ValueError):
            prices.check_identity('US:WLAC', 'BRUN', {'symbol':'BRUN','longName':'Unrelated issuer','currency':'USD'})
        with self.assertRaises(ValueError):
            prices.check_identity('US:SATS', 'ECHO', {'symbol':'ECHO','longName':'Unrelated Company','currency':'USD'})
        self.assertNotIn('US:USOU', prices.PROVIDER_ALIASES)

    def test_explicit_provider_suffix_keeps_market_and_rejects_conflict(self):
        self.assertEqual(tickers.resolve('6324.T', None, 'TSE'), 'TSE:6324')
        self.assertEqual(tickers.resolve('RSW.L', None, None), 'LSE:RSW')
        self.assertIsNone(tickers.resolve('6324.T', None, 'TWSE'))
        self.assertIsNone(tickers.resolve('6324', None, None))
        self.assertEqual(tickers.resolve('BESI.AS', None, None), 'AMS:BESI')
        self.assertEqual(tickers.yfinance_symbol('AMS:BESI'), 'BESI.AS')
        self.assertEqual(tickers.resolve('133.HK', None, 'HKEX'), 'HKEX:0133')
        self.assertIsNone(tickers.resolve('133', None, None))

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

    def test_spac_successor_does_not_supply_unverified_pre_merger_prices(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE prices(ticker_key TEXT,date TEXT,close REAL,PRIMARY KEY(ticker_key,date))')
        yf=MagicMock()
        yf.Ticker.return_value.history.return_value={'Close':Series([
            (datetime(2026,5,7),10), (datetime(2026,5,11),12)])}
        yf.Ticker.return_value.get_history_metadata.return_value={
            'symbol':'BRUN','longName':'Boost Run Inc.','currency':'USD',
            'exchangeTimezoneName':'America/New_York'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(prices,'DATA_DIR',Path(tmp)),patch.object(prices,'connect',return_value=db),patch.dict('sys.modules',{'yfinance':yf}),patch.object(prices,'time'):
            n,missing=prices.fetch(keys=['US:WLAC'])
            self.assertEqual(n,1);self.assertEqual(missing,[])
            status=json.loads((Path(tmp)/'prices/last_status.json').read_text())
            evidence=json.loads((Path(tmp)/'prices/applied'/status['batch_id']/'US_WLAC.json').read_text())
            self.assertEqual(evidence['rows'],[['2026-05-11',12.0]])
            self.assertEqual(evidence['ticker_key'],'US:WLAC')
            self.assertEqual(evidence['provider_symbol'],'BRUN')


if __name__=='__main__':unittest.main()
