"""Prospective new quality owner tests. No process, service, or model action."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import ms_quality as q


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.output = self.root / 'output'
        self.old = types.SimpleNamespace(q8_phase=types.SimpleNamespace(admission=Mock(return_value='window')))
        self.helpers = patch.object(q, 'helpers', return_value=(object(), self.old, object(), object(), object(), object(), object()))
        self.helpers.start(); self.addCleanup(self.helpers.stop)
        self.patches = [patch.object(q, 'read_proof', return_value={'qualification_sha256': 'a'*64}),
                        patch.object(q.runtime, 'qualified', return_value={}), patch.object(q, 'window_contract'),
                        patch.object(q, 'manifest', return_value={'cases': []})]
        for p in self.patches: p.start(); self.addCleanup(p.stop)

    def test_fence_installed_before_body_and_receipt_after_restoration(self):
        events = []; owner = self
        class Fence:
            def __enter__(self):
                owner.assertTrue(owner.output.is_dir()); owner.assertTrue((owner.output/'native').is_dir())
                events.append('install'); return {}, []
            def __exit__(self, *args): events.append('restore')
        def body(*args): events.append('body'); return {'passed': True}
        original = q.runtime.emit
        def emit(path, value): events.append('receipt'); return original(path, value)
        with patch.object(q.controls, 'fenced_phase', side_effect=lambda output: Fence()), \
             patch.object(q, 'phase_body', side_effect=body), patch.object(q.runtime, 'emit', side_effect=emit):
            self.assertEqual(q.phase(self.output, 'quality', 'QS0', 'unused'), 0)
        self.assertEqual(events, ['install', 'body', 'restore', 'receipt'])

    def test_cleanup_failure_never_publishes_success(self):
        class Fence:
            def __enter__(self): return {}, []
            def __exit__(self, *args): raise RuntimeError('restore did not complete')
        with patch.object(q.controls, 'fenced_phase', return_value=Fence()), patch.object(q, 'phase_body', return_value={}):
            with self.assertRaisesRegex(RuntimeError, 'restore did not complete'):
                q.phase(self.output, 'quality', 'QS0', 'unused')
        self.assertFalse((self.output/'receipt.json').exists())

    def test_fence_install_failure_never_starts_API(self):
        with patch.object(q.controls, 'fenced_phase', side_effect=RuntimeError('fence')), patch.object(q, 'phase_body') as body:
            with self.assertRaises(RuntimeError): q.phase(self.output, 'quality', 'QS0', 'unused')
        body.assert_not_called()

    def test_quality_only_refuses_timing_before_support_import(self):
        with self.assertRaises(ValueError): q.phase(self.output, 'prose', 'A1', 'unused')
        q.helpers.assert_not_called()

    def test_existing_output_never_replayed(self):
        self.output.mkdir()
        with patch.object(q.controls, 'fenced_phase') as fence:
            with self.assertRaises(FileExistsError): q.phase(self.output, 'quality', 'QS0', 'unused')
        fence.assert_not_called()


class FileLimitTests(unittest.TestCase):
    def test_exact_native_only_preexec_composition(self):
        original = Mock(return_value=types.SimpleNamespace(pid=71)); server = types.SimpleNamespace(popen=original)
        storage = types.SimpleNamespace(HARD_FILE_BYTES=512*2**20, native_fsize_preexec=Mock(return_value=Mock()))
        cfg = {'exe':'selected','args':['x']}; before = Mock(); emitted = []
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'pack-state-A.json').write_text(json.dumps({'storage_geometry':{'ratios':[0], 'kv_sources':[2], 'index_sources':[2]}, 'engine_version':'0.1.27','pack_files':['p']}))
            with patch.object(q, 'P', p), patch.object(q.config, 'expected_native_argv', return_value=['selected','--serve','']), \
                 patch.object(q.runtime, 'emit', side_effect=lambda path, value: emitted.append(value)):
                q.install_dump_limit(server,cfg,p,'quality','QS0',storage)
                proc = server.popen('the Strata engine',['selected','--serve'],preexec_fn=before)
                self.assertEqual(proc.pid,71)
                original.call_args.kwargs['preexec_fn']()
                self.assertEqual(before.call_count,1); self.assertEqual(storage.native_fsize_preexec.return_value.call_count,1)
                self.assertFalse(emitted[0]['API_limits_changed'])
                with self.assertRaises(ValueError): server.popen('the Strata engine',['selected','--serve'])
        self.assertEqual(original.call_count,1)
        self.assertEqual(storage.native_fsize_preexec.call_args.args[0]['ratios'],(0,))

    def test_dump_bound_forbidden_on_timing(self):
        with self.assertRaises(ValueError): q.install_dump_limit(object(),{},Path('/unused'),'prose','A1',object())

    def test_receipt_failure_terminates_captured_native(self):
        proc=types.SimpleNamespace(pid=71,poll=lambda:None,terminate=Mock(),wait=Mock(),kill=Mock())
        server=types.SimpleNamespace(popen=Mock(return_value=proc))
        storage=types.SimpleNamespace(HARD_FILE_BYTES=512*2**20,native_fsize_preexec=Mock(return_value=Mock()))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'pack-state-A.json').write_text(json.dumps({'storage_geometry':{'ratios':[], 'kv_sources':[], 'index_sources':[]}, 'engine_version':'0.1.27','pack_files':[]}))
            with patch.object(q,'P',p),patch.object(q.config,'expected_native_argv',return_value=['n','']),patch.object(q.runtime,'emit',side_effect=RuntimeError('receipt write')):
                q.install_dump_limit(server,{},p,'quality','QS0',storage)
                with self.assertRaisesRegex(RuntimeError,'receipt write'):server.popen('the Strata engine',['n'])
        proc.terminate.assert_called_once();proc.wait.assert_called_once_with(timeout=10)


    def test_receipt_cleanup_fault_keeps_primary(self):
        proc=types.SimpleNamespace(pid=71,poll=lambda:None,terminate=Mock(side_effect=RuntimeError('terminate failed')))
        server=types.SimpleNamespace(popen=Mock(return_value=proc))
        storage=types.SimpleNamespace(HARD_FILE_BYTES=512*2**20,native_fsize_preexec=Mock(return_value=Mock()))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'pack-state-A.json').write_text(json.dumps({'storage_geometry':{'ratios':[], 'kv_sources':[], 'index_sources':[]}, 'engine_version':'0.1.27','pack_files':[]}))
            with patch.object(q,'P',p),patch.object(q.config,'expected_native_argv',return_value=['n','']),patch.object(q.runtime,'emit',side_effect=RuntimeError('receipt first')):
                q.install_dump_limit(server,{},p,'quality','QS0',storage)
                with self.assertRaisesRegex(RuntimeError,'receipt first') as caught:server.popen('the Strata engine',['n'])
                self.assertIn('terminate failed',str(caught.exception.__notes__))


class RegistryTests(unittest.TestCase):
    def test_reservation_is_durable_single_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'quality-arms.json').write_text('{}')
            with patch.object(q,'P',p):
                q.reserve('quality','QS0','out','proof')
                value=json.loads((p/'quality-arms.json').read_text())['QS0']
                self.assertTrue(value['attempted']);self.assertFalse(value['fully_reviewed']);self.assertFalse(value['accepted'])
                with self.assertRaises(ValueError):q.reserve('quality','QS0','other','proof')

    def test_second_arm_not_reserved_without_clean_review(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'quality-arms.json').write_text('{"QS0":{"attempted":true,"fully_reviewed":false}}')
            with patch.object(q,'P',p):
                with self.assertRaises(ValueError):q.reserve('quality','QS1','out','proof')
            self.assertNotIn('QS1',json.loads((p/'quality-arms.json').read_text()))


if __name__=='__main__':unittest.main()
