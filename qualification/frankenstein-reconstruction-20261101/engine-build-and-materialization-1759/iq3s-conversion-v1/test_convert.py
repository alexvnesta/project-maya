"""Essential source, unit-fault, concurrency and real-matrix composition checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

import convert as c


class Conversion(unittest.TestCase):
    def test_exact_frozen_plan_and_artifact_map(self):
        self.assertEqual(c.sha(c.HERE / 'SOURCE_PLAN.json'), c.PLAN_SHA)
        self.assertEqual(c.sha(c.HERE / 'PLATFORM_ARTIFACTS.json'), c.ARTIFACTS_SHA)
        p = json.loads((c.HERE / 'SOURCE_PLAN.json').read_text())
        self.assertEqual(len(p['records']), 3840)
        self.assertEqual({r['layer'] for r in p['records']}, set(range(24, 29)))
        self.assertEqual({r['role'] for r in p['records']}, {'w1', 'w3'})
        self.assertEqual(sum(r['target_bytes'] for r in p['records']), 19464192000)

    def test_complete_original_matrix_matches_previous_independent_component(self):
        fixture = c.Q / 'iq3s-real-matrix-v1'
        w, s = (fixture / 'original-weight.bin').read_bytes(), (fixture / 'original-scale.bin').read_bytes()
        self.assertEqual(hashlib.sha256(w).hexdigest(), 'baf5ebb0c98ef3d38b03f62ac1702dc4658bde4bfcb6f1268deeefa8dd176319')
        self.assertEqual(hashlib.sha256(s).hexdigest(), '2cd9b4c35666281251c0218ec7bbe998f0d351436fa375cd7020cef43a8c385b')
        codec = c.Q / ('native-codec-v2/mxpack-FIRST-' + sys.platform)
        encoder = c.Q / ('iq3s-encoder-v2/compile-FIRST-' + sys.platform + '/encode-iq3s')
        pins = json.loads((c.HERE / 'PLATFORM_ARTIFACTS.json').read_text())[sys.platform]
        self.assertEqual(c.sha(codec), pins['codec_sha256'])
        self.assertEqual(c.sha(encoder), pins['encoder_sha256'])
        result = c.encode(w, s, codec, encoder)
        self.assertEqual(hashlib.sha256(result).hexdigest(), 'bf0f9f966922a9d0f12ac1156c85e0155acac15a1e574b959ad18a5864c9aee3')

    def test_codec_failure_prevents_encoder_without_retry(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 4, b'', b''))
        with self.assertRaisesRegex(ValueError, 'codec failed'):
            c.encode(bytes(5898240), bytes(368640), 'codec', 'encoder', runner)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.kwargs['env'], c.CLEAN_ENV)

    def test_encoder_partial_is_failure(self):
        runner = Mock(side_effect=[subprocess.CompletedProcess([], 0, bytes(6266880), b''),
                                   subprocess.CompletedProcess([], 0, bytes(10), b'')])
        with self.assertRaisesRegex(ValueError, 'encoder failed'):
            c.encode(bytes(5898240), bytes(368640), 'codec', 'encoder', runner)
        self.assertEqual(runner.call_count, 2)

    def test_short_original_plane_rejected_before_process(self):
        runner = Mock()
        with self.assertRaises(ValueError): c.encode(b'', bytes(368640), 'a', 'b', runner)
        runner.assert_not_called()

    def test_range_read_uses_same_pinned_inode(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); f = root / 'source'; f.write_bytes(bytes(range(64)))
            pins = {'source': {'fingerprint': c.fingerprint(f)}}
            self.assertEqual(c.read_plane(root, {'file': 'source', 'offset': 8, 'bytes': 12}, pins), bytes(range(8, 20)))
            f.write_bytes(bytes(64))
            with self.assertRaises(ValueError): c.read_plane(root, {'file': 'source', 'offset': 8, 'bytes': 12}, pins)

    def test_symlink_and_oversized_range_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); f = root / 'source'; f.write_bytes(bytes(64))
            pins = {'source': {'fingerprint': c.fingerprint(f)}}
            with self.assertRaises(ValueError): c.read_plane(root, {'file': 'source', 'offset': 60, 'bytes': 12}, pins)
            (root / 'link').symlink_to(f)
            with self.assertRaises(ValueError): c.fingerprint(root / 'link')

    def test_completed_part_is_exclusive_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / '0000.iq3s'; data = bytes(c.MATRIX_BYTES)
            p = c.write_part(f, data, {'index': 0}, {'weight': 'w', 'scale': 's'})
            self.assertEqual(c.sha(f), p['sha256'])
            with self.assertRaises(ValueError): c.write_part(f, data, {}, {})
            self.assertEqual(f.stat().st_size, c.MATRIX_BYTES)

    def test_four_workers_unique_tasks_and_complete_join(self):
        lock = threading.Lock(); live = 0; maximum = 0; seen = []
        def task(i):
            nonlocal live, maximum
            with lock: live += 1; maximum = max(maximum, live); seen.append(i)
            time.sleep(.005)
            with lock: live -= 1
            return i
        self.assertEqual(c.convert_queue(list(range(16)), task, lambda: None), list(range(16)))
        self.assertEqual(sorted(seen), list(range(16))); self.assertEqual(live, 0)
        self.assertLessEqual(maximum, 4); self.assertGreater(maximum, 1)

    def test_immediate_fault_latches_before_any_later_task_start(self):
        seen, failed = [], threading.Event()
        def task(i):
            if failed.is_set(): self.fail('A task began after the failure latch')
            seen.append(i)
            if i == 0:
                failed.set(); raise ValueError('intentional fault')
            return i
        calls = 0
        def guard():
            nonlocal calls
            calls += 1
            if calls > 1:
                self.assertTrue(failed.wait(1))
                time.sleep(.01)  # First task has raised before initial fill continues.
        with self.assertRaises(ValueError): c.convert_queue(list(range(32)), task, guard, workers=4)
        self.assertEqual(seen, [0])

    def test_guard_deferral_joins_running_work_without_starting_remaining(self):
        seen, live, calls = [], [], 0
        started = [threading.Event(), threading.Event()]
        def task(i):
            live.append(i); started[i].set(); time.sleep(.05); seen.append(i); live.remove(i); return i
        def guard():
            nonlocal calls
            calls += 1
            if calls == 3:
                self.assertTrue(all(event.wait(1) for event in started))
                raise RuntimeError('busy deferral')
        with self.assertRaisesRegex(RuntimeError, 'busy deferral'):
            c.convert_queue(list(range(20)), task, guard)
        self.assertEqual(sorted(seen), [0, 1]); self.assertEqual(live, [])

    def test_duplicate_task_wrong_completion_and_deadline_refused(self):
        for ids, task, wall in [([0, 0], lambda i: i, 5), ([0], lambda i: 9, 5), ([0], lambda i: i, -1)]:
            with self.subTest(ids=ids, wall=wall), self.assertRaises(ValueError):
                c.convert_queue(ids, task, lambda: None, wall=wall)

    def test_environment_excludes_dynamic_loaders_and_python_paths(self):
        self.assertEqual(set(c.CLEAN_ENV), set(c.ENV) | {'PATH', 'LANG', 'LC_ALL'})
        self.assertFalse(any(k.startswith(('LD_', 'DYLD_', 'PYTHONPATH')) for k in c.CLEAN_ENV))


if __name__ == '__main__': unittest.main()
