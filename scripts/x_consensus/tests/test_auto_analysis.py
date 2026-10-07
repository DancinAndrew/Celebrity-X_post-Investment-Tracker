import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from x_consensus import auto_analysis as auto


class AutoAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xc-auto-test-')
        self.root = Path(self.temp.name)
        self.pending = self.root / 'pending.md'
        self.pending.write_text('### 123 · 2026-10-05T00:00\nNo stocks here.\n')
        self.data_patch = patch.object(auto, 'DATA_DIR', self.root)
        self.data_patch.start()

    def tearDown(self):
        self.data_patch.stop()
        self.temp.cleanup()

    def status(self, kind='handoff'):
        return json.loads((self.root / kind / 'codex_last_status.json').read_text())

    def response(self, payload, exit_code=0, changed=False):
        def infer(command, prompt, log, timeout):
            response = Path(command[command.index('--output-last-message') + 1])
            response.write_text(json.dumps(payload))
            if changed:
                self.pending.write_text('### 456 · different queue\n')
            return exit_code
        return infer

    def test_zero_pending_never_starts_worker(self):
        self.pending.write_text('# zero posts\n')
        with patch.object(auto, 'bounded_inference') as worker:
            self.assertEqual(auto.run('stance', self.pending), 0)
            worker.assert_not_called()
        self.assertEqual(self.status()['state'], 'no_pending')

    def test_failed_worker_does_not_apply_even_if_it_wrote_a_response(self):
        before = self.pending.read_bytes()
        with patch.object(auto, 'codex_binary', return_value='fake'), \
             patch.object(auto, 'bounded_inference', side_effect=self.response({'items': [{'post_id': '123', 'signals': []}]}, 1)), \
             patch.object(auto.handoff, 'apply') as apply:
            self.assertEqual(auto.run('stance', self.pending), 1)
            apply.assert_not_called()
        self.assertEqual(before, self.pending.read_bytes())
        self.assertEqual(self.status()['state'], 'failed')

    def test_missing_or_duplicate_ids_cannot_reach_apply(self):
        for items in ([], [{'post_id': '999', 'signals': []}],
                      [{'post_id': '123', 'signals': []}] * 2):
            with self.subTest(items=items), patch.object(auto, 'codex_binary', return_value='fake'), \
                 patch.object(auto, 'bounded_inference', side_effect=self.response({'items': items})), \
                 patch.object(auto.handoff, 'apply') as apply:
                self.assertEqual(auto.run('stance', self.pending), 1)
                apply.assert_not_called()

    def test_replaced_queue_cannot_be_applied(self):
        with patch.object(auto, 'codex_binary', return_value='fake'), \
             patch.object(auto, 'bounded_inference', side_effect=self.response({'items': [{'post_id': '123', 'signals': []}]}, changed=True)), \
             patch.object(auto.handoff, 'apply') as apply:
            self.assertEqual(auto.run('stance', self.pending), 1)
            apply.assert_not_called()

    def test_invalid_stance_is_rejected_by_existing_validator(self):
        payload = {'items': [{'post_id': '123', 'signals': [
            {'symbol_as_written': 'AMD', 'stance': 'neutral', 'reason_zh': 'invalid'}]}]}
        with patch.object(auto, 'codex_binary', return_value='fake'), \
             patch.object(auto, 'bounded_inference', side_effect=self.response(payload)), \
             patch.object(auto.handoff, 'apply') as apply:
            self.assertEqual(auto.run('stance', self.pending), 1)
            apply.assert_not_called()

    def test_validated_stance_uses_codex_version_and_archives_full_input(self):
        before = self.pending.read_text()
        payload = {'items': [{'post_id': '123', 'is_list_or_market_wide': False, 'signals': []}]}
        with patch.object(auto, 'codex_binary', return_value='fake'), \
             patch.object(auto, 'bounded_inference', side_effect=self.response(payload)), \
             patch.object(auto.handoff, 'apply') as apply:
            self.assertEqual(auto.run('stance', self.pending), 0)
            self.assertEqual(apply.call_args.args[0], 'codex-session/v1')
        status = self.status()
        self.assertEqual(status['state'], 'applied')
        archive = Path(status['archive'])
        self.assertEqual((archive / 'pending.md').read_text(), before)
        self.assertEqual(json.loads((archive / 'answers.json').read_text()), payload['items'])

    def test_disclosure_validation_failure_never_applies(self):
        original = auto.disclosure.PENDING
        with patch.object(auto, 'codex_binary', return_value='fake'), \
             patch.object(auto, 'bounded_inference', side_effect=self.response({'items': [{'post_id': '123', 'events': []}]})), \
             patch.object(auto.disclosure, 'validate', return_value=1), \
             patch.object(auto.disclosure, 'apply') as apply:
            self.assertEqual(auto.run('disclosure', self.pending), 1)
            apply.assert_not_called()
        self.assertEqual(auto.disclosure.PENDING, original)

    def test_disclosure_has_its_own_codex_version(self):
        with patch.object(auto, 'codex_binary', return_value='fake'), \
             patch.object(auto, 'bounded_inference', side_effect=self.response({'items': [{'post_id': '123', 'events': []}]})), \
             patch.object(auto.disclosure, 'validate', return_value=0), \
             patch.object(auto.disclosure, 'apply') as apply:
            self.assertEqual(auto.run('disclosure', self.pending), 0)
            self.assertEqual(apply.call_args.args[1], 'codex-session/disc-v2')

    def test_oversized_and_truncated_input_never_start_worker(self):
        for text, env in [('### 123 · time\n（截斷）', {}),
                          ('### 123 · time\n### 456 · time\n', {'XC_CODEX_MAX_POSTS': '1'})]:
            with self.subTest(text=text), patch.dict(os.environ, env), \
                 patch.object(auto, 'bounded_inference') as worker:
                self.pending.write_text(text)
                self.assertEqual(auto.run('stance', self.pending), 1)
                worker.assert_not_called()

    def test_shell_pipeline_reports_model_failure_after_rendering(self):
        app = self.root / 'app'; app.mkdir()
        bindir = self.root / 'bin'; bindir.mkdir()
        for name in ('run.sh', 'lock.sh', 'classify_auto.sh', 'disclosure_auto.sh'):
            shutil.copy2(auto.APP / name, app / name)
        (app / 'fetch.sh').write_text('#!/bin/bash\nexit 0\n')
        for name in ('curl', 'uv'):
            (bindir / name).write_text('#!/bin/bash\nexit 0\n')
            (bindir / name).chmod(0o755)
        (bindir / 'python3').write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$CAPTURE"\ncase "$2" in x_consensus.auto_analysis) exit 1;; esac\nexit 0\n')
        (bindir / 'python3').chmod(0o755)
        data = self.root / 'data with spaces'
        capture = self.root / 'calls.txt'
        env = {**os.environ, 'PATH': str(bindir) + os.pathsep + os.environ['PATH'],
               'XC_DATA_DIR': str(data), 'XC_AUTO_CLASSIFY': '1', 'MODE': 'auto', 'CAPTURE': str(capture)}
        result = subprocess.run(['bash', str(app / 'run.sh')], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        calls = capture.read_text()
        self.assertIn('x_consensus.auto_analysis stance', calls)
        self.assertIn('x_consensus.auto_analysis disclosure', calls)
        self.assertIn('x_consensus.aggregate', calls)
        self.assertNotIn('x_consensus.classify', calls)
        self.assertTrue((data / 'run.log').is_file())

    def test_fetch_lock_protects_browser_and_releases_after_failure(self):
        app = self.root / 'app'; app.mkdir()
        bindir = self.root / 'bin'; bindir.mkdir()
        for name in ('fetch.sh', 'lock.sh'):
            shutil.copy2(auto.APP / name, app / name)
        capture = self.root / 'browser-calls.txt'
        ego = bindir / 'ego-browser'
        ego.write_text('#!/bin/bash\ncat >/dev/null\nprintf "called\\n" >> "$CAPTURE"\nexit "${EGO_EXIT:-0}"\n')
        ego.chmod(0o755)
        data = self.root / 'data with spaces'
        lock = data / 'locks/fetch'; lock.mkdir(parents=True)
        env = {**os.environ, 'PATH': str(bindir) + os.pathsep + os.environ['PATH'],
               'XC_DATA_DIR': str(data), 'CAPTURE': str(capture)}
        (lock / 'pid').write_text(str(os.getpid()))
        blocked = subprocess.run(['bash', str(app / 'fetch.sh')], env=env, capture_output=True, text=True)
        self.assertEqual(blocked.returncode, 1)
        self.assertFalse(capture.exists(), 'A competing collector must never enter the browser')
        self.assertEqual((lock / 'pid').read_text(), str(os.getpid()))
        (lock / 'pid').write_text('2147483647')  # A stale owner can be recovered.
        finished = subprocess.run(['bash', str(app / 'fetch.sh')], env=env, capture_output=True, text=True)
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertFalse(lock.exists())
        failed = subprocess.run(['bash', str(app / 'fetch.sh')], env={**env, 'EGO_EXIT': '7'}, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 7)
        self.assertFalse(lock.exists(), 'Failed browser transport must release its own fetch lock')
        self.assertEqual(capture.read_text().splitlines(), ['called', 'called'])


if __name__ == '__main__':
    unittest.main()
