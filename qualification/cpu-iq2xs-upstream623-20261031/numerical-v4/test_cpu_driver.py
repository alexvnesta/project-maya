"""Source/parent/supervisor controls; two real bounded CPU child witnesses."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import cpu_driver as d


def dump(path, value):
    path.write_text(json.dumps(value, sort_keys=True))


def actual(pid, parent):
    return {'pid': pid, 'ppid': parent, 'pgid': pid, 'cpu': [30, 30],
            'as': [d.AS_BYTES, d.AS_BYTES] if sys.platform == 'linux' else None,
            'nice': 15, 'environment': dict(d.ENV), 'platform': sys.platform,
            'dont_write_bytecode': True}


class Qualification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.here = self.root / 'new'; self.here.mkdir()
        self.input = self.root / 'input.json'; self.input.write_text('{}')
        self.source = self.here / 'test_fixture.py'
        self.source.write_text('class A:\n def test_one(self): pass\n')
        self.inputs = {str(d.REMOTE / 'input.json'): d.digest(self.input)}
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for name, value in {'HERE': self.here, 'R': self.root, 'SOURCES': ('test_fixture.py',),
                            'TEST_MODULES': ('test_fixture',), 'INPUTS': self.inputs}.items():
            self.stack.enter_context(patch.object(d, name, value))
        self.review = {'source_sha256': {'test_fixture.py': d.digest(self.source)},
                       'input_sha256': dict(self.inputs), 'test_ids': ['test_fixture.A.test_one'],
                       'root_entire_new_source_tests_and_candidate_delta_read': True,
                       'astra_entire_new_source_tests_and_candidate_delta_read': True}

    def pin(self):
        path = self.here / 'SOURCE_ROOT_REVIEW.json'; dump(path, self.review)
        return d.digest(path)

    def test_full_positive_no_project_import(self):
        with patch.object(d.importlib, 'import_module') as imp:
            result = d.checked(self.pin())
        self.assertEqual(result[2], ['test_fixture.A.test_one']); imp.assert_not_called()

    def test_bad_review_digest_refused(self):
        self.pin()
        with self.assertRaisesRegex(ValueError, 'review bytes'):
            d.checked('0' * 64)

    def test_missing_manual_review_refused(self):
        self.review['astra_entire_new_source_tests_and_candidate_delta_read'] = False
        with self.assertRaisesRegex(ValueError, 'manual reads'):
            d.checked(self.pin())

    def test_source_change_before_import_refused(self):
        pin = self.pin(); self.source.write_text('changed')
        with patch.object(d.importlib, 'import_module') as imp:
            with self.assertRaisesRegex(ValueError, 'source map'):
                d.checked(pin)
        imp.assert_not_called()

    def test_input_change_before_import_refused(self):
        pin = self.pin(); self.input.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Input bytes'):
            d.checked(pin)

    def test_missing_input_membership_refused(self):
        self.review['input_sha256'] = {}
        with self.assertRaisesRegex(ValueError, 'literal input'):
            d.checked(self.pin())

    def test_wrong_control_order_refused(self):
        self.review['test_ids'] = []
        with self.assertRaisesRegex(ValueError, 'ordered controls'):
            d.checked(self.pin())

    def test_canonical_path_escape_refused(self):
        for path in ('relative', '/tmp/input.json', str(d.REMOTE / '..' / 'input.json')):
            with self.assertRaisesRegex(ValueError, 'Canonical'):
                d.local(path)

    def test_alias_and_hardlink_refused(self):
        alias = self.root / 'alias'; alias.symlink_to(self.input)
        with self.assertRaisesRegex(ValueError, 'regular'):
            d.digest(alias)
        alias.unlink(); os.link(self.input, alias)
        with self.assertRaisesRegex(ValueError, 'regular'):
            d.digest(self.input)


class Supervisor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()

    def test_real_child_observes_exact_bounds_and_environment(self):
        code = ('import json,os,resource,sys; '
                'print(json.dumps(dict(pid=os.getpid(),ppid=os.getppid(),pgid=os.getpgid(0),'
                'cpu=list(resource.getrlimit(resource.RLIMIT_CPU)),'
                'as_value=list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform=="linux" else None,'
                'nice=os.getpriority(os.PRIO_PROCESS,0),platform=sys.platform,'
                'dont_write_bytecode=sys.dont_write_bytecode,'
                'environment={k:os.environ.get(k) for k in ' + repr(tuple(d.ENV)) + '})))')
        result = d.supervise([sys.executable, '-I', '-B', '-c', code], self.folder,
                             run_seconds=5, wall_seconds=7)
        self.assertEqual((result['returncode'], result['error'], result['cleanup']), (0, None, []))
        obs = json.loads((self.folder / 'child.log').read_text()); obs['as'] = obs.pop('as_value')
        d.bounds(obs, result['pid'], os.getpid())
        self.assertFalse(d.group_alive(result['pid']))

    def test_real_timeout_terminates_owned_group(self):
        result = d.supervise([sys.executable, '-I', '-B', '-c', 'import time; time.sleep(5)'],
                             self.folder, run_seconds=0.1, wall_seconds=2)
        self.assertIn('TimeoutExpired', result['error'])
        self.assertNotEqual(result['returncode'], 0); self.assertEqual(result['cleanup'], [])
        self.assertFalse(d.group_alive(result['pid']))
        self.assertLess(result['elapsed_seconds'], 2)

    def test_nonzero_and_cleanup_error_both_retained(self):
        process = Mock(pid=54321); process.wait.return_value = 7; process.poll.return_value = 7
        with patch.object(d.subprocess, 'Popen', return_value=process), \
             patch.object(d, 'cleanup', side_effect=RuntimeError('cleanup fault')):
            result = d.supervise(['owned'], self.folder)
        self.assertIn('Child nonzero', result['error']); self.assertIn('cleanup fault', result['cleanup'][0])
        self.assertEqual(result['returncode'], 7)

    def test_start_refusal_has_no_cleanup_target(self):
        with patch.object(d.subprocess, 'Popen', side_effect=OSError('start refused')), \
             patch.object(d, 'cleanup') as clean:
            result = d.supervise(['owned'], self.folder)
        self.assertIn('start refused', result['error']); self.assertIsNone(result['pid'])
        clean.assert_not_called()

    def test_existing_log_refuses_before_start(self):
        (self.folder / 'child.log').write_text('preserve')
        with patch.object(d.subprocess, 'Popen') as popen:
            result = d.supervise(['owned'], self.folder)
        popen.assert_not_called(); self.assertIn('FileExistsError', result['error'])
        self.assertEqual((self.folder / 'child.log').read_text(), 'preserve')

    def test_foreign_group_refused_without_signal(self):
        process = Mock(pid=54321)
        with patch.object(d.os, 'killpg') as kill:
            with self.assertRaisesRegex(ValueError, 'identity'):
                d.cleanup(process, 54322, time.monotonic() + 1)
        kill.assert_not_called()

    def test_changed_live_group_refused_without_signal(self):
        process = Mock(pid=54321); process.poll.return_value = None
        with patch.object(d.os, 'getpgid', return_value=54322), patch.object(d.os, 'killpg') as kill:
            with self.assertRaisesRegex(ValueError, 'changed group'):
                d.cleanup(process, 54321, time.monotonic() + 1)
        kill.assert_not_called()

    def test_exited_parent_still_checks_and_kills_descendants(self):
        process = Mock(pid=54321); process.poll.return_value = 0
        with patch.object(d, 'group_alive', side_effect=[True, True, False, False]), \
             patch.object(d.os, 'killpg') as kill:
            d.cleanup(process, 54321, time.monotonic() + 1)
        self.assertEqual([c.args[1] for c in kill.call_args_list], [d.signal.SIGTERM, d.signal.SIGKILL])

    def test_surviving_group_is_error(self):
        process = Mock(pid=54321); process.poll.return_value = 0
        with patch.object(d, 'group_alive', return_value=True), patch.object(d.os, 'killpg'):
            with self.assertRaisesRegex(ValueError, 'survive'):
                d.cleanup(process, 54321, time.monotonic() - 1)

    def test_declared_budget_refuses_unbounded(self):
        with self.assertRaisesRegex(ValueError, 'budget'):
            d.supervise(['owned'], self.folder, run_seconds=90, wall_seconds=90)


class Parent(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.here = Path(self.temp.name).resolve()
        self.before = ({'source': 'a' * 64}, {'input': 'b' * 64}, ['test.literal'])
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(d, 'HERE', self.here))
        self.checked = self.stack.enter_context(patch.object(d, 'checked', return_value=self.before))

    def output(self, argv, folder):
        self.argv = argv
        obs = actual(54321, os.getpid())
        receipt = {'status': 'PASS', 'pid': 54321, 'review_sha256': 'c' * 64,
                   'observed': obs, 'post_observed': obs, 'failures': 0, 'errors': 0,
                   'tests_run': 1, 'test_ids': self.before[2], 'source_sha256': self.before[0],
                   'source_after_sha256': self.before[0], 'input_sha256': self.before[1],
                   'input_after_sha256': self.before[1]}
        dump(folder / 'observed.json', obs); dump(folder / 'receipt.json', receipt)
        dump(folder / 'child.json', {'pid': 54321}); (folder / 'child.log').write_text('synthetic')
        return {'pid': 54321, 'returncode': 0, 'error': None, 'cleanup': [], 'elapsed_seconds': 1}

    def test_full_parent_consumes_exact_child_and_command(self):
        with patch.object(d, 'supervise', side_effect=self.output):
            self.assertEqual(d.parent('c' * 64), 0)
        self.assertEqual(self.argv, [sys.executable, '-I', '-B', str(self.here / 'cpu_driver.py'), '--child',
                                    '--review-pin', 'c' * 64, '--parent-pid', str(os.getpid())])
        self.assertEqual(json.loads((self.here / ('CPU-FIRST-' + sys.platform) / 'parent.json').read_text())['pid'], 54321)

    def test_existing_attempt_refuses_without_child(self):
        (self.here / ('CPU-FIRST-' + sys.platform)).mkdir()
        with patch.object(d, 'supervise') as child:
            with self.assertRaises(FileExistsError):
                d.parent('c' * 64)
        child.assert_not_called()

    def test_precheck_refusal_creates_no_attempt(self):
        self.checked.side_effect = ValueError('source change')
        with patch.object(d, 'supervise') as child:
            with self.assertRaisesRegex(ValueError, 'source change'):
                d.parent('c' * 64)
        child.assert_not_called(); self.assertFalse(list(self.here.iterdir()))

    def test_missing_success_receipt_refused(self):
        def run(argv, folder):
            result = self.output(argv, folder); (folder / 'receipt.json').unlink(); return result
        with patch.object(d, 'supervise', side_effect=run):
            with self.assertRaises(FileNotFoundError):
                d.parent('c' * 64)

    def test_forged_observed_pid_refused(self):
        def run(argv, folder):
            result = self.output(argv, folder); dump(folder / 'observed.json', actual(54322, os.getpid())); return result
        with patch.object(d, 'supervise', side_effect=run):
            with self.assertRaisesRegex(ValueError, 'identity'):
                d.parent('c' * 64)

    def test_missing_actual_as_bound_refused(self):
        obs = actual(54321, os.getpid()); obs['as'] = [0, 0]
        with self.assertRaisesRegex(ValueError, 'address-space'):
            d.bounds(obs, 54321, os.getpid())

    def test_ignored_environment_bytecode_flag_refused(self):
        obs = actual(54321, os.getpid()); obs['dont_write_bytecode'] = False
        with self.assertRaisesRegex(ValueError, 'bounds/environment'):
            d.bounds(obs, 54321, os.getpid())

    def test_wrong_receipt_ids_refused(self):
        def run(argv, folder):
            result = self.output(argv, folder)
            receipt = json.loads((folder / 'receipt.json').read_text()); receipt['test_ids'] = []
            dump(folder / 'receipt.json', receipt); return result
        with patch.object(d, 'supervise', side_effect=run):
            with self.assertRaisesRegex(ValueError, 'child receipt'):
                d.parent('c' * 64)

    def test_source_changed_after_child_refused(self):
        self.checked.side_effect = [self.before, ({}, {}, [])]
        with patch.object(d, 'supervise', side_effect=self.output):
            with self.assertRaisesRegex(ValueError, 'Post-child'):
                d.parent('c' * 64)
        self.assertFalse((self.here / ('CPU-FIRST-' + sys.platform) / 'parent.json').exists())

    def test_child_attempt_requires_exact_parent_and_maps(self):
        value = {'review_sha256': 'c' * 64, 'parent_pid': os.getpid(),
                 'source_sha256': self.before[0], 'input_sha256': self.before[1], 'test_ids': self.before[2]}
        d.attempt_contract(value, 'c' * 64, os.getpid(), self.before)
        value['parent_pid'] += 1
        with self.assertRaisesRegex(ValueError, 'attempt custody'):
            d.attempt_contract(value, 'c' * 64, os.getpid(), self.before)

    def test_child_attempt_missing_input_membership_refused(self):
        value = {'review_sha256': 'c' * 64, 'parent_pid': os.getpid(),
                 'source_sha256': self.before[0], 'input_sha256': {}, 'test_ids': self.before[2]}
        with self.assertRaisesRegex(ValueError, 'attempt custody'):
            d.attempt_contract(value, 'c' * 64, os.getpid(), self.before)


if __name__ == '__main__':
    unittest.main()
