import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from x_consensus import db, disclosure, handoff, tickers, timelines, traders


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / 'test.db'
        self.answer = self.root / 'answers.json'
        self.cfg = {'category_priors': {'politician': .7}, 'overrides': {},
                    'shrinkage_alpha': 5, 'forward_days': 30}
        c = db.connect(self.path)
        c.execute("INSERT INTO accounts(handle,account_type) VALUES('source','trade_disclosure')")
        c.execute("INSERT INTO raw_posts(post_id,author_handle,created_at_utc,text,kind,source,fetched_at_utc) VALUES('1','source','2026-10-03T01:00:00+00:00','Jane Doe bought AMD.','original','test','2026-10-03')")
        c.execute("INSERT INTO traders VALUES('doe-jane','Jane Doe','politician',.95,'user_directive','preserve me','2026-09-11')")
        c.execute("INSERT INTO disclosure_events(event_id,post_id,trader_key,ticker_key,direction,disclosed_at,confidence,extractor_version,extracted_at) VALUES('old-event','1','doe-jane','US:AMD','buy','2026-10-03T01:00:00+00:00',.8,'claude-code-session/disc-v1','2026-09-11')")
        c.execute("INSERT INTO post_classifications VALUES('1','claude-code-session/disc-v1','2026-09-11',1)")
        c.commit(); c.close()
        self.event = {'trader_name': 'Jane Doe', 'category': 'politician',
                      'symbol_as_written': 'AMD', 'company_name': 'Advanced Micro Devices',
                      'market_guess': 'US', 'direction': 'buy', 'amount_text': '$123',
                      'confidence': .9, 'trade_date': '2026-09-01', 'trade_date_text': 'Sep 1'}

    def tearDown(self):
        self.tmp.cleanup()

    def test_coverage_counts_references_separately_and_excludes_other_scopes(self):
        c = db.connect(self.path)
        self.assertEqual(db.backlog_status(c), [])
        c.executescript('''CREATE TABLE analysis_scopes(scope_key,kind,total_posts,manifest_sha256,window_start,window_end);
            CREATE TABLE analysis_batches(batch_key,scope_key);
            CREATE TABLE analysis_reviews(post_id,kind,batch_key,unresolved_json);''')
        c.execute("INSERT INTO analysis_scopes VALUES('frozen','opinion',3,'hash','start','end')")
        c.executemany('INSERT INTO analysis_batches VALUES(?,?)',[('ours','frozen'),('later','other')])
        c.executemany('INSERT INTO analysis_reviews VALUES(?,?,?,?)',
                      [('1','opinion','ours','[{"symbol_as_written":"A"},{"symbol_as_written":"B"}]'),
                       ('2','opinion','ours','[]'),('3','opinion','later','[]')])
        status = db.backlog_status(c)[0]
        self.assertEqual((status['reviewed'],status['remaining'],status['unresolved_posts'],status['unresolved_references']),
                         (2,1,1,2))
        c.close()

    def test_append_only_same_rubric_revision_replaces_one_active_post(self):
        c = db.connect(self.path)
        for version,ticker,stamp in [('codex-session/v1','US:HP','2026-10-03'),
                                     ('codex-session/v1-r1','US:HPQ','2026-10-04'),
                                     ('codex-session/v1-r2','US:HPQ','2026-10-04T01:00:00')]:
            c.execute('INSERT INTO post_classifications VALUES(?,?,?,1)',('1',version,stamp))
            c.execute("INSERT INTO signals VALUES(?,?,'unclear','neutral',.9,'HP company news','HP',?,?)",('1',ticker,version,stamp))
        self.assertEqual(c.execute('SELECT count(*) FROM signals').fetchone()[0],3)
        self.assertEqual([r[0] for r in c.execute('SELECT ticker_key FROM session_v1_signals')],['US:HPQ'])
        self.assertIn('codex-session/v1-r1',db.compatible_versions('codex-session/v1'))
        self.assertIn('codex-session/v1-r2',db.compatible_versions('codex-session/v1'))
        self.assertEqual(c.execute('SELECT classifier_version FROM session_v1_classifications').fetchone()[0],
                         'codex-session/v1-r2')
        c.close()

    def test_foreign_codes_require_explicit_supported_market(self):
        self.assertEqual(tickers.resolve('8299','Phison','TPEX'),'TPEX:8299')
        self.assertEqual(tickers.resolve('285A','Kioxia','TSE'),'TSE:285A')
        self.assertEqual(tickers.resolve('6600',None,'HKEX'),'HKEX:6600')
        for symbol in ['8299','285A','6600']:
            self.assertIsNone(tickers.resolve(symbol,None,None))

    def test_identity_override_changes_only_reviewed_instrument_and_keeps_source(self):
        c=db.connect(self.path)
        for pid in ['1','2']:
            c.execute('INSERT INTO post_classifications VALUES(?,?,?,1)',(pid,'claude-code-session/v1','2026-10-03'))
            c.execute("INSERT INTO signals VALUES(?,'US:ESMT','bullish','positive',.9,'thesis','ESMT','claude-code-session/v1','2026-10-03')",(pid,))
        original={tuple(x) for x in c.execute('SELECT * FROM signals')}
        c.execute("INSERT INTO signal_identity_overrides VALUES('1','claude-code-session/v1','US:ESMT','TWSE:3006','verified','ESMT','official','hash')")
        c.execute("INSERT INTO signal_identity_overrides VALUES('2','claude-code-session/v1','US:ESMT',NULL,'unresolved','ESMT',NULL,'hash')")
        for source in ['identity_checked_signals','session_v1_signals']:
            row=c.execute('SELECT * FROM '+source).fetchall()
            self.assertEqual(len(row),1)
            self.assertEqual((row[0]['ticker_key'],row[0]['stance'],row[0]['tone']),('TWSE:3006','bullish','positive'))
        self.assertEqual({tuple(x) for x in c.execute('SELECT * FROM signals')},original)
        c.commit();c.close();c=db.connect(self.path)
        self.assertEqual(c.execute('SELECT ticker_key FROM session_v1_signals').fetchone()[0],'TWSE:3006')
        c.close()

    def snapshot(self):
        c = db.connect(self.path)
        rows = {name: sorted(tuple(r) for r in c.execute('SELECT * FROM ' + name))
                for name in ['raw_posts', 'traders', 'disclosure_events', 'post_classifications']}
        c.close()
        return rows

    def apply(self, events):
        self.answer.write_text(json.dumps([{'post_id': '1', 'events': events}]))
        with patch.object(disclosure, 'connect', side_effect=lambda: db.connect(self.path)), \
             patch.object(disclosure, 'load_config', return_value=self.cfg):
            disclosure.apply(str(self.answer), 'codex-session/disc-v2')

    def test_new_version_preserves_old_rows_and_existing_prior(self):
        before = self.snapshot()
        self.apply([self.event])
        after = self.snapshot()
        for table, rows in before.items():
            self.assertTrue(set(rows) <= set(after[table]), table)
        self.assertEqual(after['traders'], before['traders'])
        self.assertEqual(len(after['disclosure_events']), 2)
        c = db.connect(self.path)
        active = c.execute('SELECT * FROM active_disclosure_events').fetchall()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]['extractor_version'], 'codex-session/disc-v2')
        c.close()

    def test_exact_replay_keeps_all_values_and_timestamps(self):
        self.apply([self.event])
        once = self.snapshot()
        self.apply([self.event])
        self.assertEqual(self.snapshot(), once)

    def test_conflicting_same_version_is_rejected_without_mutation(self):
        self.apply([self.event])
        once = self.snapshot()
        with self.assertRaises(ValueError):
            self.apply([{**self.event, 'direction': 'sell'}])
        self.assertEqual(self.snapshot(), once)

    def test_empty_new_result_preserves_old_event_but_excludes_it_from_outputs(self):
        old = self.snapshot()['disclosure_events']
        self.apply([])
        self.assertEqual(self.snapshot()['disclosure_events'], old)
        c = db.connect(self.path)
        self.assertEqual(timelines.load_trades(c), [])
        with patch.object(traders, 'load_config', return_value=self.cfg):
            score = traders.recompute_scores(c)
        self.assertEqual(score[0]['n_events'], 0)
        c.close()

    def test_different_trade_dates_in_one_post_remain_distinct_and_replayable(self):
        second = {**self.event, 'trade_date': '2026-09-02', 'trade_date_text': 'Sep 2'}
        self.apply([self.event, second])
        once = self.snapshot()
        c = db.connect(self.path)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM active_disclosure_events').fetchone()[0], 2)
        c.close()
        self.apply([self.event, second])
        self.assertEqual(self.snapshot(), once)

    def test_distinct_unknown_source_periods_are_kept_without_guessed_dates(self):
        first = {**self.event, 'trade_date': None, 'trade_date_text': 'in two days'}
        second = {**first, 'trade_date_text': 'back in mid-May', 'amount_text': 'another chunk'}
        self.apply([first, second])
        once = self.snapshot()
        c = db.connect(self.path)
        rows = c.execute('SELECT trade_date,trade_date_text FROM active_disclosure_events').fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['trade_date'] is None for r in rows))
        self.assertEqual({r['trade_date_text'] for r in rows}, {'in two days', 'back in mid-May'})
        c.close()
        self.apply([first, second])
        self.assertEqual(self.snapshot(), once)

    def test_duplicate_unknown_period_is_still_rejected_atomically(self):
        first = {**self.event, 'trade_date': None, 'trade_date_text': 'in two days'}
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.apply([first, {**first, 'amount_text': 'different amount'}])
        self.assertEqual(self.snapshot(), before)

    def test_stock_and_explicit_options_share_an_underlying_without_collapsing(self):
        stock = {**self.event, 'trade_date': None, 'trade_date_text': 'just disclosed',
                 'amount_text': '15,000 shares'}
        call = {**stock, 'amount_text': 'calls worth up to $5 million'}
        put = {**stock, 'amount_text': 'put options worth up to $500,000'}
        before = self.snapshot()
        self.apply([stock, call, put])
        once = self.snapshot()
        for table, rows in before.items():
            self.assertTrue(set(rows) <= set(once[table]), table)
        c = db.connect(self.path)
        active = c.execute('SELECT * FROM active_disclosure_events').fetchall()
        self.assertEqual(len(active), 3)
        self.assertTrue(all(r['trade_date'] is None for r in active))
        self.assertEqual({r['amount_text'] for r in active}, {e['amount_text'] for e in [stock, call, put]})
        c.close()
        self.apply([stock, call, put])
        self.assertEqual(self.snapshot(), once)
        with self.assertRaises(ValueError):
            self.apply([stock, call, {**call, 'amount_text': 'call contracts worth $1 million'}])
        self.assertEqual(self.snapshot(), once)

    def test_sive_quarantine_preserves_raw_signals_and_filters_both_read_paths(self):
        c = db.connect(self.path)
        for pid, version in [('1', 'claude-code-session/v1'), ('2', 'codex-session/v1')]:
            c.execute('INSERT INTO post_classifications VALUES(?,?,?,1)', (pid, version, '2026-10-04'))
            c.execute("INSERT INTO signals VALUES(?,'US:SIVE','bullish','positive',.9,'reason','SIVE',?,'2026-10-04')", (pid, version))
        original = [tuple(r) for r in c.execute('SELECT * FROM signals')]
        for version in ['session/v1', 'claude-code-session/v1']:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ' + db.signal_source(version)).fetchone()[0], 0)
        self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM signals')], original)
        self.assertIsNone(tickers.resolve('SIVE', None, 'US'))
        self.assertEqual(tickers.resolve('SIVE', 'Sivers Semiconductors', 'STO'), 'STO:SIVE')
        self.assertEqual(tickers.yfinance_symbol('STO:SIVE'), 'SIVE.ST')
        c.close()

    def test_numeric_market_requires_explicit_identity_context(self):
        self.assertIsNone(tickers.resolve('000660', None, None))
        self.assertIsNone(tickers.resolve('688017', None, None))
        self.assertEqual(tickers.resolve('000660', 'SK hynix', 'KRX'), 'KRX:000660')

    def test_explicit_skhy_ads_keeps_its_listing_despite_issuer_alias(self):
        self.assertEqual(tickers.resolve('$SKHY', 'SK hynix', 'US'), 'US:SKHY')
        self.assertEqual(tickers.resolve('SKHY', 'SK hynix', None), 'US:SKHY')
        self.assertIsNone(tickers.resolve('SKHY', 'SK hynix', 'KRX'))
        self.assertEqual(tickers.resolve('000660', 'SK hynix', 'KRX'), 'KRX:000660')

    def test_opinion_replay_keeps_values_and_conflict_rolls_back(self):
        item = {'post_id':'1','is_list_or_market_wide':False,'signals':[
            {'symbol_as_written':'AMD','company_name':'Advanced Micro Devices','market_guess':'US',
             'stance':'bullish','tone':'positive','confidence':.9,'reason_zh':'reason','evidence_quote':'AMD'}]}
        self.answer.write_text(json.dumps([item]))
        with patch.object(handoff,'connect',side_effect=lambda: db.connect(self.path)):
            handoff.apply('codex-session/v1',str(self.answer))
            c=db.connect(self.path)
            original=[tuple(r) for r in c.execute('SELECT * FROM signals')];c.close()
            first=self.snapshot()
            handoff.apply('codex-session/v1',str(self.answer))
            self.assertEqual(self.snapshot(),first)
            c=db.connect(self.path);self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM signals')],original);c.close()
            item['signals'][0]['stance']='bearish'
            self.answer.write_text(json.dumps([item]))
            with self.assertRaises(ValueError):
                handoff.apply('codex-session/v1',str(self.answer))
            self.assertEqual(self.snapshot(),first)


if __name__ == '__main__':
    unittest.main()
