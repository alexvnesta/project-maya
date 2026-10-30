"""New parallel acquisition controls. Fake HTTP, never serving/model operations."""
import copy
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import shutil
import resource
import types
import unittest
from unittest.mock import Mock, patch

import acquire_unsloth as u
import run_cpu as driver


class Pure(unittest.TestCase):
    def test_exact_current_six_shards(self):
        m = u.manifest(); self.assertEqual(len(m['files']), 6); self.assertEqual(m['total_bytes'], 300475464795)

    def test_both_downloads_and_comparison_space_reserved(self):
        free = u.FLOOR + u.CUSHION + u.TOTAL + u.MAYA_TOTAL
        self.assertEqual(u.combined_space(free, 0, 0)['required_bytes'], free)
        with self.assertRaises(ValueError): u.combined_space(free - 1, 0, 0)

    def test_download_progress_preserves_space_equation(self):
        free = u.FLOOR + u.CUSHION + u.TOTAL + u.MAYA_TOTAL
        a = u.combined_space(free, 0, 0); b = u.combined_space(free - 300, 100, 200)
        self.assertEqual(a['free_bytes'] - a['required_bytes'], b['free_bytes'] - b['required_bytes'])

    def test_comparison_reserve_survives_download_completion(self):
        out = u.combined_space(u.FLOOR + u.CUSHION, u.TOTAL, u.MAYA_TOTAL)
        self.assertEqual(out['required_bytes'], 144 * 2**30 + 256 * 2**20)

    def test_bad_counter_types_sizes(self):
        for args in [(True, 0, 0), (10**15, -1, 0), (10**15, u.TOTAL + 1, 0), (10**15, 0, u.MAYA_TOTAL + 1)]:
            with self.assertRaises(ValueError): u.combined_space(*args)

    def test_changed_manifest_pin_before_parse(self):
        with patch.object(u, 'sha', return_value='bad'):
            with self.assertRaises(ValueError): u.manifest()

    def test_changed_owner_source_before_import(self):
        with patch.object(u, 'sha', return_value='bad'), patch.object(u.importlib.util, 'spec_from_file_location') as loader:
            with self.assertRaises(ValueError): u.primitive()
        loader.assert_not_called()

    def test_new_qualification_pin_required(self):
        with patch.object(u, 'sha', return_value='bad'):
            with self.assertRaises(ValueError): u.qualified('expected')

    def test_rate_and_socket_deadline_not_model_timeouts(self):
        self.assertEqual(u.RATE, 16 * 2**20); self.assertEqual(u.WALL, 21600)
        self.assertEqual(u.ENV['CUDA_VISIBLE_DEVICES'], '')


class Snapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.spec = {'path': 'Maya-S/a.gguf', 'size': 10}
        (self.root / 'Maya-S').mkdir(); self.final = self.root / self.spec['path']

    def test_partial_budget(self):
        self.final.with_name('a.gguf.partial').write_bytes(b'1234')
        self.assertEqual(u.concurrent_maya_retained(self.root, [self.spec]), 4)

    def test_final_budget(self):
        self.final.write_bytes(b'1234567890'); self.assertEqual(u.concurrent_maya_retained(self.root, [self.spec]), 10)

    def test_atomic_link_unlink_publication_not_double_counted(self):
        p = self.final.with_name('a.gguf.partial'); p.write_bytes(b'1234567890'); self.final.hardlink_to(p)
        self.assertEqual(u.concurrent_maya_retained(self.root, [self.spec]), 10)

    def test_ambiguous_different_inodes_rejected(self):
        self.final.write_bytes(b'1234'); self.final.with_name('a.gguf.partial').write_bytes(b'1234')
        with self.assertRaises(ValueError): u.concurrent_maya_retained(self.root, [self.spec])

    def test_symlink_rejected(self):
        self.final.symlink_to('/nonexistent')
        with self.assertRaises(ValueError): u.concurrent_maya_retained(self.root, [self.spec])

    def test_oversize_rejected(self):
        self.final.write_bytes(b'x' * 11)
        with self.assertRaises(ValueError): u.concurrent_maya_retained(self.root, [self.spec])

    def test_missing_leaf_over_reserves(self): self.assertEqual(u.concurrent_maya_retained(self.root, [self.spec]), 0)


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.maya = self.root / 'maya'; self.maya.mkdir()
        self.original_manifest = (u.MAYA / 'ASSET_MANIFEST.json').read_bytes()
        (self.maya / 'ASSET_MANIFEST.json').write_bytes(self.original_manifest)
        self.a = types.SimpleNamespace(SelectedGate=Mock(return_value=Mock()), retained_inventory=Mock(return_value=0), Deferred=RuntimeError,
                                      safe_file=Mock())
        for p in [patch.object(u, 'HERE', self.root), patch.object(u, 'MAYA', self.maya),
                  patch.object(u, 'concurrent_maya_retained', return_value=0),
                  patch.object(u.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=10**15))]:
            p.start(); self.addCleanup(p.stop)

    def test_current_selected_gate_rechecked(self):
        gate = u.Gate(self.a, {'files': []}); gate()
        self.assertEqual(gate.selected.call_count, 2); self.assertIsNotNone(gate.last_budget)

    def test_foreign_or_private_owner_before_asset_mutation(self):
        self.a.SelectedGate.side_effect = RuntimeError('phase active')
        with self.assertRaisesRegex(RuntimeError, 'phase active'): u.Gate(self.a, {'files': []})
        self.assertFalse((self.root / 'assets').exists())

    def test_explicit_pause_cooperatively_defers(self):
        gate = u.Gate(self.a, {'files': []})
        (self.root / 'pause-for-comparison.json').write_text(json.dumps({'authorization_sha256': u.AUTH_SHA, 'pause_before_private_phase': True}))
        with self.assertRaisesRegex(RuntimeError, 'Paused before'): gate()

    def test_foreign_pause_policy_rejected(self):
        gate = u.Gate(self.a, {'files': []}); (self.root / 'pause-for-comparison.json').write_text('{}')
        with self.assertRaises(ValueError): gate()

    def test_pause_alias_checked_before_read(self):
        gate = u.Gate(self.a, {'files': []}); self.a.safe_file.side_effect = ValueError('alias')
        with self.assertRaisesRegex(ValueError, 'alias'): gate()

    def test_combined_disk_shortfall_before_writes(self):
        with patch.object(u.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=u.FLOOR)):
            with self.assertRaises(ValueError): u.Gate(self.a, {'files': []})
        self.assertFalse((self.root / 'assets').exists())


class Transfer(unittest.TestCase):
    def setUp(self):
        path = u.ACQ / 'acquire.py'; self.assertEqual(u.sha(path), u.PRIMITIVE_SHA)
        spec = importlib.util.spec_from_file_location('_new_target_transfer_test_only', path)
        self.a = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.a)
        self.a.REPO, self.a.REVISION, self.a.RATE = u.REPO, u.REVISION, u.RATE
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name).resolve()
        self.payload = b'new target bytes'; self.asset = {'path': 'UD-IQ2_XXS/fixture.gguf', 'size': len(self.payload),
                         'sha256': hashlib.sha256(self.payload).hexdigest()}; self.calls = []

    def opener(self, request, timeout):
        self.calls.append((request.full_url, request.headers, timeout))
        class Response(io.BytesIO):
            status = 206
        response = Response(self.payload); response.headers = {'Content-Length': str(len(self.payload)),
             'Content-Range': 'bytes 0-%d/%d' % (len(self.payload) - 1, len(self.payload))}
        return response

    def test_new_repo_revision_and_every_byte_checksum(self):
        r = self.a.acquire_file(self.asset, self.root, lambda: None, opener=self.opener, free=lambda: 10**15)
        self.assertEqual(r['sha256'], self.asset['sha256']); self.assertEqual(r['status'], 'DOWNLOADED_VERIFIED')
        self.assertEqual(len(self.calls), 1); self.assertIn('/' + u.REPO + '/resolve/' + u.REVISION + '/', self.calls[0][0])
        self.assertEqual(self.calls[0][2], 5); self.assertEqual((self.root / self.asset['path']).read_bytes(), self.payload)

    def test_wrong_hash_retains_partial_no_publish(self):
        asset = dict(self.asset, sha256='0' * 64)
        with self.assertRaises(ValueError): self.a.acquire_file(asset, self.root, lambda: None, opener=self.opener, free=lambda: 10**15)
        self.assertFalse((self.root / asset['path']).exists()); self.assertTrue((self.root / (asset['path'] + '.partial')).exists())
        self.assertEqual(len(self.calls), 1)

    def test_transport_fault_not_retried(self):
        opener = Mock(side_effect=TimeoutError('synthetic'))
        with self.assertRaises(TimeoutError): self.a.acquire_file(self.asset, self.root, lambda: None, opener=opener, free=lambda: 10**15)
        self.assertEqual(opener.call_count, 1)

    def test_original_running_module_source_unchanged(self):
        self.assertEqual(u.sha(u.ACQ / 'acquire.py'), u.PRIMITIVE_SHA)
        self.assertEqual(self.a.REPO, u.REPO); self.assertEqual(self.a.REVISION, u.REVISION)


class Qualification(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.e = Path(self.tmp.name).resolve(); self.here = self.e / 'decode-optimization-20261028/unsloth-v31-iq2xxs-download-v1'
        self.here.mkdir(parents=True); original_e, original_here = u.E, u.HERE
        for n in u.SOURCES: shutil.copy2(original_here / n, self.here / n)
        for n in u.INPUTS:
            target = self.e / n; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(original_e / n, target)
        self.sources = {n: u.sha(self.here / n) for n in u.SOURCES}; self.inputs = {n: u.sha(self.e / n) for n in u.INPUTS}
        tree = ast.parse((self.here / 'test_acquire_unsloth.py').read_text())
        self.ids = sorted('test_acquire_unsloth.' + c.name + '.' + f.name for c in tree.body if isinstance(c, ast.ClassDef)
                          for f in c.body if isinstance(f, ast.FunctionDef) and f.name.startswith('test_'))
        self.review = {'root_entire_source_and_tests_read': True, 'astra_entire_source_and_tests_read': True,
                       'source_sha256': self.sources, 'input_sha256': self.inputs, 'test_ids': self.ids}
        self.put(self.here / 'CPU_SOURCE_ROOT_REVIEW.json', self.review)
        self.files = {str(self.here / n): h for n, h in self.sources.items()}
        self.files.update({str(self.e / n): h for n, h in self.inputs.items()})
        self.files[str(self.here / 'CPU_SOURCE_ROOT_REVIEW.json')] = u.sha(self.here / 'CPU_SOURCE_ROOT_REVIEW.json')
        env = dict(u.ENV, PYTHONDONTWRITEBYTECODE='1')
        for label in ('darwin', 'linux'):
            d = self.here / ('CPU-FIRST-' + label); d.mkdir()
            r = {'passed': True, 'test_ids': self.ids, 'controls': len(self.ids), 'source_sha256': self.sources,
                 'input_sha256': self.inputs, 'CPU_seconds': [30, 30], 'nice': 15, 'environment': env,
                 'Linux_AS_bytes': [512 * 2**20] * 2 if label == 'linux' else None}
            c = {'returncode': 0, 'error': None, 'cleanup_errors': [], 'CPU_limit_seconds': 30, 'wall_limit_seconds': 90,
                 'nice_increment': 15, 'Linux_AS_bytes': 512 * 2**20 if label == 'linux' else None, 'environment': env}
            self.put(d / 'receipt.json', r); self.put(d / 'child.json', c); (d / 'child.log').write_text('synthetic test-only proof')
            self.files.update({str(d / n): u.sha(d / n) for n in ('receipt.json', 'child.json', 'child.log')})
        self.q = {**self.review, 'files': self.files, 'selected_binding': {'native_pid': 7}}
        self.patchers = [patch.object(u, 'HERE', self.here), patch.object(u, 'E', self.e)]
        for p in self.patchers: p.start(); self.addCleanup(p.stop)

    def put(self, path, value): path.write_text(json.dumps(value))
    def check(self):
        p = self.here / 'qualification.json'; self.put(p, self.q); return u.qualified(u.sha(p))

    def test_actual_current_qualification_positive(self): self.assertEqual(self.check()['source_sha256'], self.sources)

    def test_executing_source_cannot_be_omitted(self):
        self.q['source_sha256'] = {n: h for n, h in self.sources.items() if n != 'acquire_unsloth.py'}
        with self.assertRaises(ValueError): self.check()

    def test_empty_test_ids_rejected(self):
        self.q['test_ids'] = []
        with self.assertRaises(ValueError): self.check()

    def test_required_input_omission_rejected(self):
        self.q['input_sha256'] = {n: h for n, h in self.inputs.items() if not n.endswith('maya-s-comparison-v1/ASSET_MANIFEST.json')}
        with self.assertRaises(ValueError): self.check()

    def test_raw_log_cannot_be_omitted(self):
        del self.q['files'][str(self.here / 'CPU-FIRST-linux/child.log')]
        with self.assertRaises(ValueError): self.check()

    def test_unbounded_child_rejected(self):
        p = self.here / 'CPU-FIRST-linux/child.json'; s = json.loads(p.read_text()); s['Linux_AS_bytes'] = None
        self.put(p, s); self.files[str(p)] = u.sha(p)
        with self.assertRaises(ValueError): self.check()

    def test_manual_source_review_required(self):
        self.q['astra_entire_source_and_tests_read'] = False
        with self.assertRaises(ValueError): self.check()


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.here = Path(self.tmp.name).resolve()
        path = u.ACQ / 'acquire.py'; spec = importlib.util.spec_from_file_location('_main_fake_http_test_only', path)
        self.a = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.a)
        self.binding = {'native_pid': 7}; self.gate = Mock(); self.gate.selected.host.start_binding = self.binding; self.gate.last_budget = {'free_bytes': 10**15}
        self.m = {'files': [{'path': str(i), 'size': 1, 'sha256': '0' * 64} for i in range(2)]}
        self.a.acquire_file = Mock(return_value={'bytes': 1, 'sha256': '0' * 64, 'status': 'DOWNLOADED_VERIFIED'})
        for p in [patch.object(u, 'HERE', self.here), patch.object(u, 'qualified', return_value={'selected_binding': self.binding}),
                  patch.object(u, 'manifest', return_value=self.m), patch.object(u, 'primitive', return_value=self.a),
                  patch.object(u, 'Gate', return_value=self.gate), patch.object(u, 'physical_namespace', return_value=True)]:
            p.start(); self.addCleanup(p.stop)

    def test_actual_main_success_receipt_no_service_actions(self):
        self.assertEqual(u.main('test-only'), 0); s = json.loads((self.here / 'STATE.json').read_text())
        self.assertEqual(s['status'], 'ALL_SIX_UNSLOTH_ASSETS_VERIFIED_NO_MODEL_RUN'); self.assertEqual(s['model_or_service_actions'], 0)
        self.assertEqual(self.a.acquire_file.call_count, 2)

    def test_first_transport_failure_no_second_transfer(self):
        self.a.acquire_file.side_effect = TimeoutError('synthetic')
        self.assertEqual(u.main('test-only'), 1); self.assertEqual(self.a.acquire_file.call_count, 1)
        self.assertEqual(json.loads((self.here / 'STATE.json').read_text())['status'], 'ACQUISITION_HOLD_PARTIALS_RETAINED')

    def test_changed_selected_binding_no_lock_or_assets_write(self):
        self.gate.selected.host.start_binding = {'native_pid': 8}
        with self.assertRaises(ValueError): u.main('test-only')
        self.assertFalse((self.here / 'download.lock').exists()); self.a.acquire_file.assert_not_called()

    def test_lock_alias_rejected_before_open(self):
        (self.here / 'download.lock').symlink_to(self.here / 'foreign')
        with self.assertRaises(ValueError): u.main('test-only')
        self.assertFalse((self.here / 'foreign').exists()); self.a.acquire_file.assert_not_called()


class Driver(unittest.TestCase):
    def test_source_review_checked_before_test_import(self):
        with patch.object(driver, 'sha', return_value='wrong'):
            with self.assertRaises(ValueError): driver.checked('expected')

    def test_child_only_cpu_nice_AS_bounds(self):
        with patch.object(driver.os, 'nice') as nice, patch.object(driver.resource, 'setrlimit') as limit, patch.object(driver.sys, 'platform', 'linux'):
            driver.limits()
        nice.assert_called_once_with(15)
        self.assertEqual([c.args for c in limit.call_args_list], [(resource.RLIMIT_CPU, (30, 30)), (resource.RLIMIT_AS, (512 * 2**20,) * 2)])

    def test_only_owned_test_group_cleanup(self):
        proc = Mock(pid=123)
        with patch.object(driver, 'gone', side_effect=[False, True, True, True]), patch.object(driver.os, 'killpg') as kill:
            self.assertEqual(driver.cleanup(proc), [])
        kill.assert_called_once_with(123, driver.signal.SIGTERM)


if __name__ == '__main__': unittest.main()
