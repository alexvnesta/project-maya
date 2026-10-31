import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import build_current as b


class Controls(unittest.TestCase):
    def health(self):
        return {'status': 'ok', 'loaded': True, 'busy': False, 'model': 'deepseek-v4.1-flash-iq2-xs',
                'max_context': 1048576, 'switcher': {'active_model': 'deepseek', 'default_model': 'deepseek',
                'fault': None, 'inflight': 0, 'waiting': 0}}, {'work': {'active': 0, 'queued': 0, 'admission_reserved': 0}}

    def assets(self):
        rows = [{'path': str(i), 'sha256': str(i) * 64, 'size': i + 1} for i in range(6)]
        value = {'status': 'ALL_SIX_UNSLOTH_ASSETS_VERIFIED_NO_MODEL_RUN', 'returncode': 0, 'pid': 1234,
                 'model_or_service_actions': 0, 'files': [{'path': r['path'], 'sha256': r['sha256'],
                 'bytes': r['size'], 'status': 'DOWNLOADED_VERIFIED'} for r in rows]}
        return value, {'files': rows}

    def test_configure_full_source_and_current_cpu(self):
        p = b.plan('configure')
        self.assertIn(str(b.EXPECTED / 'source'), p)
        self.assertIn('-DSTRATA_GGML_DIR=' + str(b.R / 'llama.cpp'), p)
        self.assertFalse(any('60821a6d' in x or 'maya-build-sm80-ablate469' in x for x in p))

    def test_fixed_architecture_no_gpu_probe(self):
        p = b.plan('configure')
        self.assertIn('-DCMAKE_CUDA_ARCHITECTURES=80', p)
        self.assertIn('-DFETCHCONTENT_FULLY_DISCONNECTED=ON', p)
        self.assertIn('-DSTRATA_BUILD_TESTS=OFF', p)

    def test_serial_native_target_only(self):
        self.assertEqual(b.plan('compile'), ['/usr/bin/cmake', '--build', str(b.EXPECTED / 'native-build-FIRST'),
                                            '--target', 'maya-ds4', '--', '-j1'])

    def test_foreign_stage_refused(self):
        for stage in ('run', 'retry', 'deploy', '', None):
            with self.assertRaises(ValueError): b.plan(stage)

    def test_healthy_idle(self):
        b.idle_contract(*self.health())

    def test_active_work_refused(self):
        for key in ('active', 'queued', 'admission_reserved'):
            h, t = self.health(); t['work'][key] = 1
            with self.assertRaises(ValueError): b.idle_contract(h, t)

    def test_switcher_work_refused(self):
        for key in ('inflight', 'waiting'):
            h, t = self.health(); h['switcher'][key] = 1
            with self.assertRaises(ValueError): b.idle_contract(h, t)

    def test_busy_refused(self):
        h, t = self.health(); h['busy'] = True
        with self.assertRaises(ValueError): b.idle_contract(h, t)

    def test_counter_bool_or_missing_refused(self):
        for value in (True, False, None, '0', -1):
            h, t = self.health(); t['work']['active'] = value
            with self.assertRaises(ValueError): b.idle_contract(h, t)

    def test_changed_capacity_model_default_refused(self):
        for key, value in (('max_context', 262144), ('model', 'maya-s'), ('loaded', False)):
            h, t = self.health(); h[key] = value
            with self.assertRaises(ValueError): b.idle_contract(h, t)
        h, t = self.health(); h['switcher']['default_model'] = 'glm'
        with self.assertRaises(ValueError): b.idle_contract(h, t)

    def test_fault_refused(self):
        h, t = self.health(); h['switcher']['fault'] = 'fault'
        with self.assertRaises(ValueError): b.idle_contract(h, t)

    def test_complete_download(self):
        b.download_complete(*self.assets(), lambda pid: False)

    def test_active_worker_refused(self):
        with self.assertRaises(ValueError): b.download_complete(*self.assets(), lambda pid: True)

    def test_partial_download_refused(self):
        v, m = self.assets(); v['files'].pop()
        with self.assertRaises(ValueError): b.download_complete(v, m, lambda pid: False)

    def test_each_wrong_asset_field_refused(self):
        for field, value in (('path', 'other'), ('sha256', 'a' * 64), ('bytes', 999), ('status', 'PARTIAL')):
            v, m = self.assets(); v['files'][3][field] = value
            with self.assertRaises(ValueError): b.download_complete(v, m, lambda pid: False)

    def test_failed_download_refused(self):
        for key, value in (('returncode', 1), ('returncode', False), ('pid', 0), ('model_or_service_actions', 1),
                           ('status', 'PINNED_UNSLOTH_DOWNLOAD_RUNNING')):
            v, m = self.assets(); v[key] = value
            with self.assertRaises(ValueError): b.download_complete(v, m, lambda pid: False)

    def test_inputs_missing_changed_or_alias_refused(self):
        with tempfile.TemporaryDirectory() as s:
            root = Path(s).resolve(); p = root / 'source'; p.write_text('original')
            rows = {str(p): b.sha(p)}; b.verify_files(rows)
            p.write_text('changed')
            with self.assertRaises(ValueError): b.verify_files(rows)
            p.unlink()
            with self.assertRaises(ValueError): b.verify_files(rows)
            q = root / 'real'; q.write_text('original'); p.symlink_to(q)
            with self.assertRaises(ValueError): b.verify_files(rows)

    def test_empty_map_refused(self):
        for rows in ({}, [], None):
            with self.assertRaises(ValueError): b.verify_files(rows)

    def run_mock(self, folder, *, fault=None, code=0, observed_wrong=False, cleanup_fault=False):
        owner = types.SimpleNamespace(starting=lambda n: None, registered=lambda p, n: None,
                                      cleanup_failed=lambda n, e: None)
        def cleanup(p, deadline):
            if cleanup_fault: raise ValueError('scripted cleanup fault')
        helper = types.SimpleNamespace(environment=lambda: {}, ENV={}, cleanup=cleanup)
        def popen(argv, **kw):
            self.assertEqual(kw['env'], {'TMPDIR': str(folder / 'tmp')})
            (folder / 'observed.json').write_text(json.dumps({'pid': 99123, 'ppid': os.getpid(), 'pgid': 99123,
                'cpu': [120, 120], 'as': [4 * 2**30] * 2, 'nice': 16 if observed_wrong else 15,
                'environment': {'TMPDIR': str(folder / 'tmp')}}))
            return types.SimpleNamespace(pid=99123, returncode=code, poll=lambda: code)
        def check():
            if fault: raise ValueError(fault)
        with patch.object(b.subprocess, 'Popen', side_effect=popen) as spawn:
            if fault or code or observed_wrong or cleanup_fault:
                with self.assertRaises(ValueError): b.run_owned(['cmake'], folder, helper, owner, check)
            else:
                self.assertEqual(b.run_owned(['cmake'], folder, helper, owner, check)['returncode'], 0)
            return spawn.call_count, json.loads((folder / 'child.json').read_text())

    def test_owned_clean_completion(self):
        with tempfile.TemporaryDirectory() as s:
            calls, row = self.run_mock(Path(s).resolve())
            self.assertEqual(calls, 1); self.assertEqual(row['cleanup'], [])

    def test_guard_refuses_before_spawn(self):
        with tempfile.TemporaryDirectory() as s:
            calls, row = self.run_mock(Path(s).resolve(), fault='BUSY')
            self.assertEqual(calls, 0); self.assertIsNone(row['pid'])

    def test_nonzero_preserved(self):
        with tempfile.TemporaryDirectory() as s:
            _, row = self.run_mock(Path(s).resolve(), code=1)
            self.assertEqual(row['returncode'], 1); self.assertIsNotNone(row['error'])

    def test_actual_resource_drift_refused(self):
        with tempfile.TemporaryDirectory() as s:
            self.run_mock(Path(s).resolve(), observed_wrong=True)

    def test_cleanup_fault_blocks(self):
        with tempfile.TemporaryDirectory() as s:
            _, row = self.run_mock(Path(s).resolve(), cleanup_fault=True)
            self.assertEqual(len(row['cleanup']), 1)

    def test_inherited_toolchain_flags_excluded(self):
        with tempfile.TemporaryDirectory() as s, patch.dict(os.environ, {
                'CMAKE_TOOLCHAIN_FILE': '/foreign/toolchain.cmake', 'CXXFLAGS': '-lold',
                'CUDAFLAGS': '--bad', 'NVCC_PREPEND_FLAGS': '--bad', 'LD_PRELOAD': '/foreign/library'}):
            self.run_mock(Path(s).resolve())

    def configure_fixture(self, root, mutate=None):
        folder = root / 'configure-FIRST'; folder.mkdir()
        child = {'argv': b.plan('configure'), 'returncode': 0, 'error': None, 'cleanup': []}
        sup = {'passed': True, 'owned_claim_released': True, 'error': None}
        result = {'passed': True, 'stage': 'configure', 'child': child, 'model_executed': False}
        rows = {'child.json': child, 'supervision.json': sup, 'result.json': result}
        if mutate: mutate(rows)
        for name, value in rows.items(): (folder / name).write_text(json.dumps(value))
        return {'files': {str(folder / n): b.sha(folder / n) for n in rows}}

    def test_actual_configure_closure_required(self):
        with tempfile.TemporaryDirectory() as s:
            root = Path(s).resolve(); q = self.configure_fixture(root)
            with patch.object(b, 'HERE', root): b.configure_closed(q)

    def test_failed_configure_closure_blocks_compile(self):
        for key, value in (('passed', False), ('owned_claim_released', False), ('error', 'closure failure')):
            with tempfile.TemporaryDirectory() as s:
                root = Path(s).resolve()
                q = self.configure_fixture(root, lambda rows: rows['supervision.json'].__setitem__(key, value))
                with patch.object(b, 'HERE', root), self.assertRaises(ValueError): b.configure_closed(q)

    def test_unpinned_configure_closure_blocks_compile(self):
        with tempfile.TemporaryDirectory() as s:
            root = Path(s).resolve(); q = self.configure_fixture(root)
            del q['files'][str(root / 'configure-FIRST/supervision.json')]
            with patch.object(b, 'HERE', root), self.assertRaises(ValueError): b.configure_closed(q)


if __name__ == '__main__':
    unittest.main(verbosity=2)
