import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from x_consensus import db, handoff, ingest, aggregate, disclosure

APP = Path(__file__).resolve().parents[1]

class ContinuationTests(unittest.TestCase):
    def test_fetch_uses_configured_data_and_quotes_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); app=root/'app';app.mkdir()
            shutil.copy2(APP/'fetch.sh',app/'fetch.sh')
            shutil.copy2(APP/'lock.sh',app/'lock.sh')
            target=root/'data with "quotes"'; bindir=root/'bin';bindir.mkdir()
            (bindir/'ego-browser').write_text('#!/bin/sh\ncat > "$CAPTURE"\n')
            (bindir/'ego-browser').chmod(0o755)
            capture=root/'fetch.js'
            env={**os.environ,'XC_DATA_DIR':str(target),'PATH':str(bindir)+os.pathsep+os.environ['PATH'],'CAPTURE':str(capture)}
            result=subprocess.run(['bash',str(app/'fetch.sh')],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue((target/'raw').is_dir())
            self.assertIn('const XC_DATA = '+json.dumps(str(target)),capture.read_text())
            self.assertNotIn("path.join(XC_HOME, '.data'",capture.read_text())

    def test_ingest_recovers_legacy_data_without_replacing_existing_posts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';legacy=root/'app/.data'
            for p in [data,legacy]:
                (p/'raw/2026-10-04').mkdir(parents=True);(p/'runs').mkdir()
            (data/'raw/2026-10-04/a__one.json').write_text('{}')
            (legacy/'raw/2026-10-04/a__two.json').write_text('{}')
            def record(path,handle):
                return [{'post_id': '1' if 'one' in path.name else '2', 'author_handle':'a','created_at_utc':'2026-10-04T01:00:00+00:00','text':path.name,'lang':'en','kind':'original','original_post_id':None,'original_author':None,'conversation_id':None,'is_pinned':0,'symbols_json':'[]','url':None,'source':'test','fetched_at_utc':'2026-10-04T02:00:00+00:00'}]
            c=db.connect(root/'test.db')
            with patch.object(ingest,'parse_file',side_effect=record):
                self.assertEqual(ingest.ingest_raw(c,source_dirs=[data,legacy]),(2,2))
                self.assertEqual(ingest.ingest_raw(c,source_dirs=[data,legacy]),(2,0))
            c.close()

    def test_session_versions_are_counted_once_and_disclosures_do_not_vote(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=db.connect(Path(tmp)/'test.db')
            now='2099-01-01T01:00:00+00:00'
            for handle,typ,vote in [('a','opinion',1),('b','opinion',1),('news','trade_disclosure',0),('silent','opinion',1)]:
                c.execute('insert into accounts(handle,account_type,counts_toward_consensus) values(?,?,?)',(handle,typ,vote))
            for pid,author in [('1','a'),('2','b'),('3','news')]:
                c.execute("insert into raw_posts(post_id,author_handle,created_at_utc,text,kind,source,fetched_at_utc) values(?,?,?,'text','original','test',?)",(pid,author,now,now))
            for pid,version,stance in [('1','claude-code-session/v1','bearish'),('1','codex-session/v1','bullish'),('2','claude-code-session/v1','bullish'),('3','codex-session/v1','bearish')]:
                stamp='2099-01-02' if version.startswith('codex') else '2099-01-01'
                c.execute('insert into post_classifications values(?,?,?,1)',(pid,version,stamp))
                c.execute("insert into signals(post_id,ticker_key,stance,tone,confidence,reason_zh,classifier_version,classified_at_utc) values(?,'US:AMD',?,'positive',.9,'reason',?,?)",(pid,stance,version,stamp))
            result=aggregate.consensus(c,100000,'session/v1')
            self.assertEqual(len(result['shared_bullish']),1)
            self.assertEqual(set(result['shared_bullish'][0]['bulls']),{'a','b'})
            self.assertNotIn('silent',result['shared_bullish'][0]['all_accounts'])
            c.close()

    def test_handoff_rejects_duplicate_ids_and_missing_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); pending=root/'pending.md';pending.write_text('### 1 · time\n')
            answer=root/'answers.json';answer.write_text(json.dumps([{'post_id':'1','signals':[]},{'post_id':'1','signals':[]}]))
            self.assertEqual(handoff.validate(only=str(answer),pending=str(pending)),1)
            answer.write_text(json.dumps([{'post_id':'1','signals':[]}]))
            self.assertEqual(handoff.validate(only=str(answer),pending=str(root/'missing.md')),1)

    def test_tone_does_not_create_directional_consensus(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=db.connect(Path(tmp)/'test.db')
            for i in range(2):
                c.execute("insert into accounts(handle,account_type) values(?,'opinion')",(str(i),))
                c.execute("insert into raw_posts(post_id,author_handle,created_at_utc,text,kind,source,fetched_at_utc) values(?,?,'2099-01-01','phone ugly','original','test','2099-01-01')",(str(i),str(i)))
                c.execute("insert into signals values(?,'US:AAPL','unclear','negative',.9,'產品嘲諷','ugly','claude-code-session/v1','2099-01-01')",(str(i),))
            r=aggregate.consensus(c,100000,'claude-code-session/v1')
            self.assertEqual(r['shared_bearish'],[])
            self.assertEqual(len(aggregate.tone_signals(c,100000,'claude-code-session/v1')),1)
            c.close()

    def test_graphql_progress_ignores_quotes_pins_and_other_authors(self):
        source=re.search(r"const drainSource = String.raw`(.*?)`\n", (APP/'fetch.sh').read_text(), re.S).group(1)
        def tweet(pid,author,date):
            return {'__typename':'Tweet','core':{'user_results':{'result':{'core':{'screen_name':author}}}},'legacy':{'id_str':pid,'created_at':date}}
        main=tweet('1','jukan05','Thu Oct 01 12:00:00 +0000 2026')
        main['quoted_status_result']={'result':tweet('old','jukan05','Thu Jan 01 12:00:00 +0000 2015')}
        entry=lambda t:{'entryId':'tweet-'+t['legacy']['id_str'],'content':{'itemContent':{'tweet_results':{'result':t}}}}
        module={'entryId':'profile-conversation-2','content':{'items':[{'item':{'itemContent':{'tweet_results':{'result':tweet('2','jukan05','Wed Sep 30 12:00:00 +0000 2026')}}}}]}}
        payload={'instructions':[{'type':'TimelinePinEntry','entry':entry(tweet('pin','jukan05','Thu Jan 01 12:00:00 +0000 2015'))},{'type':'TimelineAddEntries','entries':[entry(main),entry(tweet('other','someone_else','Thu Jan 01 12:00:00 +0000 2015')),module]}]}
        hit={'url':'https://x.com/i/api/graphql/id/UserTweets','text':json.dumps(payload),'status':200}
        script='const window={__xcap:{hits:'+json.dumps([hit])+'}}; const drain='+source+'; console.log(JSON.stringify(drain("jukan05"))); console.log(window.__xcap.hits.length);'
        r=subprocess.run(['node','-e',script],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        result=json.loads(r.stdout.splitlines()[0])
        self.assertEqual(set(result['ids']),{'1','2'})
        self.assertEqual(result['oldest'],1790769600000)
        self.assertEqual(r.stdout.splitlines()[1],'0')

    def test_disclosure_requires_all_ids_and_real_trade_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pending=root/'pending.md';pending.write_text('### 1 · time\n### 2 · time\n')
            answer=root/'events.json';answer.write_text(json.dumps([{'post_id':'1','events':[]}]))
            def connect():return db.connect(root/'test.db')
            with patch.object(disclosure,'PENDING',pending),patch.object(disclosure,'connect',connect):
                self.assertEqual(disclosure.validate(str(answer)),1)
            self.assertFalse(disclosure._valid_date('2026-02-30'))
            self.assertTrue(disclosure._valid_date('2026-02-28'))

    def test_disabled_account_is_excluded_even_if_old_signals_exist(self):
        from x_consensus import timelines
        with tempfile.TemporaryDirectory() as tmp:
            c=db.connect(Path(tmp)/'test.db')
            c.execute("insert into accounts(handle,account_type,enabled,disabled_reason) values('bad','opinion',0,'identity mismatch')")
            c.execute("insert into raw_posts(post_id,author_handle,created_at_utc,text,kind,source,fetched_at_utc) values('1','bad','2099-01-01','text','original','test','2099-01-01')")
            c.execute("insert into signals values('1','US:AMD','bullish','positive',.9,'reason','text','claude-code-session/v1','2099-01-01')")
            self.assertEqual(aggregate.account_stances(c,100000,'claude-code-session/v1'),{})
            self.assertEqual(timelines.load_signals(c,'claude-code-session/v1'),[])
            c.execute("insert into traders(trader_key,display_name,category,prior_weight,weight_source) values('trader','Trader','institution',.6,'category_default')")
            c.execute("insert into disclosure_events(event_id,post_id,trader_key,ticker_key,direction,disclosed_at,confidence,extractor_version,extracted_at) values('event','1','trader','US:AMD','buy','2099-01-01',.9,'test','2099-01-01')")
            self.assertEqual(timelines.load_trades(c),[])
            c.close()

if __name__=='__main__':unittest.main()
