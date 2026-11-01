"""Small source/receipt/ownership controls only; never touch model assets or hosts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

import bulk as b


class Bulk(unittest.TestCase):
    def parts(self, root, count=3):
        records, data = [], []
        for i in range(count):
            raw = bytes([i + 1]) * 7; data.append(raw)
            record = {'target_offset': i * 7, 'target_bytes': 7, 'layer': i}
            records.append(record)
            (root / ('%04d.iq3s' % i)).write_bytes(raw)
            b.emit(root / ('%04d.json' % i), {'record': record, 'bytes': 7,
                'sha256': hashlib.sha256(raw).hexdigest(), 'codec_returncode': 0, 'encoder_returncode': 0})
            b.emit(root / ('%04d.child.json' % i), {'returncode': 0, 'error': None,
                'timed_out': False, 'cleanup_errors': [], 'descendants_remaining': False})
        return records, b''.join(data)

    def test_ordered_join_actual_hash_and_exclusive_publish(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); records, data = self.parts(root)
            out = root / 'overlay.iq3s'
            receipt = b.join_parts(root, records, out, matrix_bytes=7)
            self.assertEqual(out.read_bytes(), data)
            self.assertEqual(receipt['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(receipt['parts'], 3)
            with self.assertRaises(ValueError): b.join_parts(root, records, out, matrix_bytes=7)
            self.assertEqual(out.read_bytes(), data)

    def test_wrong_record_hash_size_or_child_refused_before_publish(self):
        for mode in ('record', 'hash', 'size', 'exit', 'timeout', 'cleanup', 'descendants'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as t:
                root = Path(t).resolve(); records, _ = self.parts(root)
                proof_path = root / '0001.json'; proof = json.loads(proof_path.read_text())
                child_path = root / '0001.child.json'; child = json.loads(child_path.read_text())
                if mode == 'record': proof['record']['layer'] = 99
                elif mode == 'hash': proof['sha256'] = '0' * 64
                elif mode == 'size': (root / '0001.iq3s').write_bytes(b'short')
                elif mode == 'exit': child['returncode'] = 1
                elif mode == 'timeout': child['timed_out'] = True
                elif mode == 'cleanup': child['cleanup_errors'] = ['failure']
                else: child['descendants_remaining'] = True
                proof_path.write_text(json.dumps(proof)); child_path.write_text(json.dumps(child))
                out = root / 'overlay.iq3s'
                with self.assertRaises(ValueError): b.join_parts(root, records, out, matrix_bytes=7)
                self.assertFalse(out.exists()); self.assertTrue(out.with_suffix('.partial').exists())

    def test_join_missing_part_and_noncontiguous_plan_refused(self):
        for missing in (True, False):
            with tempfile.TemporaryDirectory() as t:
                root = Path(t).resolve(); records, _ = self.parts(root)
                if missing: (root / '0001.iq3s').unlink()
                else: records[1]['target_offset'] = 1
                with self.assertRaises((ValueError, FileNotFoundError)):
                    b.join_parts(root, records, root / 'overlay.iq3s', matrix_bytes=7)
                self.assertFalse((root / 'overlay.iq3s').exists())

    def test_full_source_sha_once_and_fingerprint_receipt(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); data = b'original source' * 11
            source = root / 'one'; source.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            result = b.verify_sources(root, 'plan', {'one': digest}, root / 'verified.json')
            self.assertEqual(result['root'], str(root)); self.assertEqual(result['plan_sha256'], 'plan')
            self.assertEqual(result['files']['one']['fingerprint'], b.regular(source))
            self.assertTrue(result['files']['one']['full_sha_verified'])
            self.assertEqual(result['files']['one']['sha256'], digest)

    def test_full_source_wrong_sha_preserves_failure_without_receipt(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); (root / 'one').write_bytes(b'wrong')
            with self.assertRaises(ValueError):
                b.verify_sources(root, 'plan', {'one': '0' * 64}, root / 'verified.json')
            self.assertFalse((root / 'verified.json').exists())

    def test_source_alias_and_traversal_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); (root / 'one').write_bytes(b'x'); (root / 'alias').symlink_to(root / 'one')
            with self.assertRaises(ValueError): b.regular(root / 'alias')
            with self.assertRaises(ValueError): b.verify_sources(root, 'p', {'../one': 'x'}, root / 'v.json')

    def base(self):
        specs = [{'path': 'assets/%d' % i, 'size': i + 1, 'sha256': str(i) * 64} for i in range(8)]
        receipt = {'status': 'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN', 'returncode': 0,
            'manifest_sha256': b.MANIFEST_SHA, 'asset_root': '/base', 'model_or_service_actions': 0,
            'files': [{'path': s['path'], 'bytes': s['size'], 'sha256': s['sha256'],
                       'status': 'DOWNLOADED_VERIFIED'} for s in specs]}
        inspect = lambda path: [1, 2, int(path.name) + 1, 3, 4]
        return receipt, {'files': specs}, inspect

    def test_exact_all8_terminal_base_gate(self):
        receipt, manifest, inspect = self.base()
        b.acquisition_contract(receipt, manifest, Path('/base'), inspect)
        for field, value in (('status', 'PASSIVE_DOWNLOAD_RUNNING'), ('returncode', 1),
                             ('asset_root', '/wrong'), ('manifest_sha256', 'wrong')):
            wrong = copy.deepcopy(receipt); wrong[field] = value
            with self.assertRaises(ValueError): b.acquisition_contract(wrong, manifest, Path('/base'), inspect)

    def test_missing_duplicate_changed_or_partial_base_asset_refused(self):
        for mode in ('missing', 'duplicate', 'hash', 'partial', 'size'):
            receipt, manifest, inspect = self.base()
            if mode == 'missing': receipt['files'].pop()
            elif mode == 'duplicate': receipt['files'][1] = receipt['files'][0]
            elif mode == 'hash': receipt['files'][0]['sha256'] = 'bad'
            elif mode == 'partial': receipt['files'][0]['status'] = 'PARTIAL'
            else: inspect = lambda p: [1, 2, 0, 3, 4]
            with self.assertRaises(ValueError): b.acquisition_contract(receipt, manifest, Path('/base'), inspect)

    def test_qualification_requires_matching_physical_manual_cpu_proofs(self):
        sources = {'bulk.py': 'x'}
        q = {'entire_source_tests_driver_manually_read': True, 'CPU_both_hosts_passed': True,
             'source_sha256': sources, 'test_ids': ['test']}
        proofs = {p: {'passed': True, 'source_sha256': sources, 'test_ids': ['test'],
                      'physical_platform': p, 'controls': 1, 'returncode': 0, 'failures': 0, 'errors': 0,
                      'observed': {'pid': 10001, 'pgid': 10001, 'cpu': [30, 30], 'nice': 15,
                                   'as': [512 * 2**20] * 2 if p == 'linux' else None,
                                   'platform': p, 'dont_write_bytecode': True,
                                   'environment': b.CLEAN_ENV}} for p in ('darwin', 'linux')}
        b.cpu_contract(q, sources, proofs)
        for key in ('entire_source_tests_driver_manually_read', 'CPU_both_hosts_passed'):
            wrong = dict(q, **{key: False})
            with self.assertRaises(ValueError): b.cpu_contract(wrong, sources, proofs)
        for key, value in (('passed', False), ('test_ids', ['other']), ('source_sha256', {}),
                           ('physical_platform', 'darwin'), ('controls', 0), ('returncode', 1), ('errors', 1)):
            wrong = copy.deepcopy(proofs); wrong['linux'][key] = value
            with self.assertRaises(ValueError): b.cpu_contract(q, sources, wrong)
        wrong = copy.deepcopy(proofs); wrong['linux']['observed']['cpu'] = [120, 120]
        with self.assertRaises(ValueError): b.cpu_contract(q, sources, wrong)

    def test_foreign_claim_or_unresolved_children_never_release(self):
        with tempfile.TemporaryDirectory() as t:
            state = Path(t) / 'state.json'; state.write_text(json.dumps({'active_cpu_build': {'other': 1}}))
            cas = types.SimpleNamespace(cas_state=Mock())
            with self.assertRaises(ValueError): b.release_claim(cas, state, {'ours': 1}, {'passed': True})
            with self.assertRaises(ValueError): b.release_claim(cas, state, {'ours': 1}, {'passed': False})
            cas.cas_state.assert_not_called()

    def test_exact_own_claim_release_is_cas_and_preserves_other_state(self):
        with tempfile.TemporaryDirectory() as t:
            state = Path(t) / 'state.json'; record = {'ours': 1}
            state.write_text(json.dumps({'active_cpu_build': record, 'other': 'keep'})); raw = state.read_bytes()
            cas = types.SimpleNamespace(cas_state=Mock())
            b.release_claim(cas, state, record, {'passed': True})
            cas.cas_state.assert_called_once_with(state, raw, {'active_cpu_build': False, 'other': 'keep'})

    def test_handle_capture_precedes_return_and_cleanup_uses_only_owned_handles(self):
        events = []; process = types.SimpleNamespace(pid=12345)
        owner = types.SimpleNamespace(children=[], starting=lambda n: events.append('starting'),
            cleanup_failed=Mock())
        def register(p, name):
            owner.children.append((name, p, p.pid)); events.append('registered')
        owner.registered = register
        children = b.Children(owner)
        with patch.object(b.subprocess, 'Popen', return_value=process):
            self.assertIs(children.popen(['python']), process)
        cleanup = types.SimpleNamespace(cleanup=Mock())
        children.cleanup_all(cleanup, 99)
        cleanup.cleanup.assert_called_once_with(process, 99)
        self.assertEqual(events, ['starting', 'registered'])

    def test_failed_owned_cleanup_is_retained(self):
        process = types.SimpleNamespace(pid=12345)
        owner = types.SimpleNamespace(children=[('one', process, process.pid)], cleanup_failed=Mock())
        children = b.Children(owner)
        children.cleanup_all(types.SimpleNamespace(cleanup=Mock(side_effect=ValueError('failed'))), 9)
        self.assertEqual(owner.cleanup_failed.call_count, 1)

    def test_actual_data_limits_require_exact_identity_and_bounds(self):
        row = {'pid': 10001, 'ppid': 10000, 'pgid': 10001, 'cpu': [30, 30],
               'as': [512 * 2**20] * 2, 'nice': 15, 'environment': b.CLEAN_ENV,
               'isolated': True, 'dont_write_bytecode': True}
        b.actual_limits(row, 10001, 10000)
        for key, value in (('pgid', 999), ('cpu', [120, 120]), ('nice', 30),
                           ('environment', {}), ('isolated', False)):
            with self.assertRaises(ValueError): b.actual_limits(dict(row, **{key: value}), 10001, 10000)

    def test_streaming_stage_requires_actual_limits_done_exit_and_cleanup(self):
        for wrong in (None, 'bounds', 'done', 'exit', 'cleanup'):
            with self.subTest(wrong=wrong), tempfile.TemporaryDirectory() as t:
                folder = Path(t).resolve() / 'stage'
                process = types.SimpleNamespace(pid=12345, returncode=1 if wrong == 'exit' else 0)
                process.poll = lambda: process.returncode
                def popen(*args, **kwargs):
                    observed = {'pid': process.pid, 'ppid': b.os.getpid(), 'pgid': process.pid,
                        'cpu': [120, 120] if wrong == 'bounds' else [30, 30],
                        'as': [512 * 2**20] * 2, 'nice': 15, 'environment': b.CLEAN_ENV,
                        'isolated': True, 'dont_write_bytecode': True}
                    b.emit(folder / 'observed.json', observed)
                    b.emit(folder / 'DONE.json', {'mode': 'verify-0', 'complete': wrong != 'done'})
                    return process
                cleanup_failed = Mock()
                children = types.SimpleNamespace(popen=popen, owner=types.SimpleNamespace(cleanup_failed=cleanup_failed))
                owner = types.SimpleNamespace(cleanup=Mock(side_effect=ValueError('cleanup') if wrong == 'cleanup' else None))
                call = lambda: b.owned_stage('verify-0', folder, children, owner, lambda: None,
                                            deadline=time.monotonic() + 90, spawned=lambda: None)
                if wrong:
                    with self.assertRaises(ValueError): call()
                else: call()
                row = json.loads((folder / 'child.json').read_text())
                self.assertEqual(row['returncode'], process.returncode)
                self.assertEqual(owner.cleanup.call_count, 1)
                if wrong == 'cleanup': self.assertEqual(cleanup_failed.call_count, 1)

    def test_matrix_registration_routes_only_exact_qualified_worker_command(self):
        process = types.SimpleNamespace(pid=12345)
        owner = types.SimpleNamespace(children=[], starting=Mock(), registered=Mock())
        children = b.Children(owner)
        argv = [b.sys.executable, '-I', '-B', str(b.CONVERTER), 'worker', '7', str(b.ROOT),
                str(b.OUT / 'parts'), str(b.OUT / 'verified-sources.json'), 'pin']
        with patch.object(b.subprocess, 'Popen', return_value=process) as popen:
            children.popen(argv, env=b.CLEAN_ENV)
        self.assertEqual(popen.call_args.args[0], [str(Path(b.sys.executable).resolve()), '-I', '-B', str(b.HERE / 'bulk.py'),
                                                'child', 'matrix-7', 'pin'])
        wrong = list(argv); wrong[6] = '/foreign/root'
        with patch.object(b.subprocess, 'Popen') as popen, self.assertRaises(ValueError):
            children.popen(wrong, env=b.CLEAN_ENV)
        popen.assert_not_called()

    def test_reused_queue_fault_stops_new_work_and_joins_started_work(self):
        # Import only the pinned reviewed module. Inject task callbacks; no
        # native process, original source or large output is touched.
        c = b.conversion(); seen = []
        def task(index):
            seen.append(index); raise ValueError('intentional')
        with self.assertRaises(ValueError):
            c.convert_queue(list(range(12)), task, lambda: None, workers=1)
        self.assertEqual(seen, [0])

    def test_clean_environment_and_native_unit_reuse_source_contract(self):
        self.assertFalse(any(n.startswith(('LD_', 'DYLD_', 'PYTHONPATH')) for n in b.CLEAN_ENV))
        source = Path(b.__file__).read_text()
        self.assertIn('c.bounded_unit(index, ROOT, parts, verified, verified_sha)', source)
        self.assertIn('workers=4', source); self.assertIn('owner.CPULease', source)
        self.assertIn('base_closed(q[\'base_terminal_sha256\'])', source)
        self.assertIn('children.cleanup_all(owner, deadline)', source)


if __name__ == '__main__': unittest.main(verbosity=2)
