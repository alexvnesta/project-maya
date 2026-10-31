"""Prospective metadata caller only: all host/acquisition/construct actions mocked."""
import copy
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import construct_pack as c


class ConstructTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.e = Path(self.tmp.name).resolve(); self.acq = self.e / 'acq'; self.acq.mkdir()
        self.patchers = [patch.object(c, 'E', self.e), patch.object(c, 'ACQ', self.acq)]
        for p in self.patchers: p.start(); self.addCleanup(p.stop)

    def test_new_source_namespace_and_unchanged_exact_target(self):
        self.assertEqual(c.HERE.name,'pack-v2')
        self.assertEqual(c.TARGET,c.Q/'pack-v1/pack-FIRST')
        self.assertNotEqual(c.TARGET.parent,c.HERE)

    def test_contract_keeps_exact_target(self):
        receipt=self.acq/'acquisition-attempt-complete.json';receipt.write_text('{}')
        with patch.object(c,'completed_receipt'),patch.object(c.g,'path_inventory',return_value={}), \
             patch.object(c.g,'regular',return_value=(1,2,3,4,5)):
            value=c.contract(receipt)
        self.assertEqual(value['output'],str(c.TARGET))

    def test_old_child_attempt_paths_rejected_before_qualification(self):
        old=c.Q/'pack-v1'
        with patch.object(c,'qualified') as qualified:
            with self.assertRaises(ValueError):
                c.child(old/'construct-contract-FIRST.json',Path('/q'),'x',old/'construct-CPU-FIRST')
        qualified.assert_not_called()

    def test_source_pin_checks_content(self):
        path = self.e / 'source'; path.write_text('fixed')
        c.checked_files({str(path): c.g.sha(path)})
        path.write_text('changed')
        with self.assertRaises(ValueError): c.checked_files({str(path): '0' * 64})

    def test_foreign_source_path_rejected(self):
        with self.assertRaises(ValueError): c.checked_files({'/outside/file': '0' * 64})

    def test_empty_source_map_rejected(self):
        with self.assertRaises(ValueError): c.checked_files({})

    def test_only_exact_inherited_external_pin_allowed(self):
        p = self.e / 'external'; p.write_text('selected'); pin = c.g.sha(p)
        inside = self.e / 'inside'; inside.mkdir()
        with patch.object(c, 'E', inside):
            c.checked_files({str(p): pin}, allowed_external={str(p): pin})
            with self.assertRaises(ValueError): c.checked_files({str(p): pin}, allowed_external={str(p): '0' * 64})

    def test_symlink_source_rejected(self):
        path = self.e / 'source'; path.write_text('fixed'); alias = self.e / 'alias'; alias.symlink_to(path)
        with self.assertRaises(ValueError): c.checked_files({str(alias): c.g.sha(path)})

    def test_first_receipt_preserved(self):
        p = self.e / 'receipt.json'; c.emit(p, {'status': 'failed'})
        with self.assertRaises(ValueError): c.emit(p, {'status': 'pass'})
        self.assertEqual(json.loads(p.read_text()), {'status': 'failed'})

    def test_terminal_attempt_path_not_mutable_state(self):
        with self.assertRaises(ValueError): c.completed_receipt(self.acq / 'acquisition-state.json')

    def test_terminal_attempt_requires_complete_eight(self):
        p = self.acq / 'acquisition-attempt-test.json'; p.write_text('{"status":"PASSIVE_DOWNLOAD_RUNNING"}')
        with patch.object(c.g, 'manifest', return_value={'files': []}):
            with self.assertRaises(ValueError): c.completed_receipt(p)

    def test_changed_acquisition_source_before_import(self):
        with patch.object(c.g, 'sha', return_value='bad'), patch.object(c.importlib.util, 'spec_from_file_location') as loader:
            with self.assertRaises(ValueError): c.acquisition_module()
        loader.assert_not_called()

    def test_exact_child_paths_before_actions(self):
        with patch.object(c, 'qualified') as qualification:
            with self.assertRaises(ValueError): c.child(Path('/wrong'), Path('/q'), '0' * 64, Path('/out'))
        qualification.assert_not_called()

    def test_environment_literal_no_global_change(self):
        self.assertEqual(c.CHILD_ENV, {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1',
            'OPENBLAS_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1'})

    def test_changed_explicit_qualification_pin_before_inputs(self):
        p = self.e / 'q.json'; p.write_text('{}')
        with patch.object(c, 'checked_files') as checked:
            with self.assertRaises(ValueError): c.qualified(p, '0' * 64)
        checked.assert_not_called()

    def proof(self):
        receipt = {'passed': True, 'controls': 1, 'test_ids': ['new.test'], 'source_sha256': {'s': 'x'},
                   'input_sha256': {'i': 'y'}, 'CPU_seconds': [30, 30], 'nice': 15,
                   'environment': c.CHILD_ENV, 'Linux_AS_bytes': None}
        child = {'returncode': 0, 'error': None, 'cleanup_errors': [], 'CPU_limit_seconds': 30,
                 'wall_limit_seconds': 90, 'nice_increment': 15, 'environment': c.CHILD_ENV}
        groups = []; files = {}; first_proofs = None
        for role, module, sources in [('pack_guard', 'test_pack_guard', ('pack_guard.py', 'test_pack_guard.py', 'run_cpu.py')),
                                      ('construct_controller', 'test_construct_pack', ('pack_guard.py', 'construct_pack.py', 'test_construct_pack.py', 'construct_cpu.py'))]:
            sm = {n: c.g.sha(c.HERE / n) for n in sources}; tree = ast.parse((c.HERE / (module + '.py')).read_text())
            ids = sorted(module + '.' + cls.name + '.' + f.name for cls in tree.body if isinstance(cls, ast.ClassDef)
                         for f in cls.body if isinstance(f, ast.FunctionDef) and f.name.startswith('test_'))
            proofs = {}
            for label in ('darwin', 'linux'):
                rp = self.e / (role + label + '-receipt.json'); cp = self.e / (role + label + '-child.json'); lp = self.e / (role + label + '-child.log')
                rec = copy.deepcopy(receipt); rec.update(controls=len(ids), test_ids=ids, source_sha256=sm)
                rec['Linux_AS_bytes'] = [512 * 2**20] * 2 if label == 'linux' else None
                rp.write_text(json.dumps(rec)); cp.write_text(json.dumps(child)); lp.write_text('synthetic test-only proof')
                proofs[label] = {'receipt': str(rp), 'child': str(cp), 'log': str(lp)}
                files.update({str(p): c.g.sha(p) for p in (rp, cp, lp)})
            files.update({str(c.HERE / n): pin for n, pin in sm.items()}); files[str(self.e / 'i')] = 'y'
            groups.append({'name': role, 'proofs': proofs, 'test_ids': ids, 'source_sha256': sm, 'input_sha256': {'i': 'y'}})
            if first_proofs is None: first_proofs = proofs
        q = {'root_manual_review': True, 'astra_manual_review': True, 'pack_guard_both_physical_hosts_passed': True,
             'construct_controller_both_physical_hosts_passed': True, 'files': files, 'CPU_groups': groups}
        return q, first_proofs

    def check_q(self, q):
        path = self.e / 'q.json'; path.write_text(json.dumps(q))
        with patch.object(c, 'checked_files'), patch.object(c, 'acquisition_inventory', return_value={}):
            return c.qualified(path, c.g.sha(path))

    def test_both_exact_physical_proofs(self):
        q, _ = self.proof(); self.assertTrue(self.check_q(q)['root_manual_review'])

    def test_missing_other_host(self):
        q, _ = self.proof(); del q['CPU_groups'][0]['proofs']['linux']
        with self.assertRaises(ValueError): self.check_q(q)

    def test_changed_test_ids(self):
        q, _ = self.proof(); q['CPU_groups'][0]['test_ids'] = ['different']
        with self.assertRaises(ValueError): self.check_q(q)

    def test_changed_input_map(self):
        q, _ = self.proof(); q['CPU_groups'][0]['input_sha256'] = {'i': 'changed'}
        with self.assertRaises(ValueError): self.check_q(q)

    def test_failed_child_kept(self):
        q, proofs = self.proof(); p = Path(proofs['linux']['child']); s = json.loads(p.read_text()); s['returncode'] = 1; p.write_text(json.dumps(s))
        with self.assertRaises(ValueError): self.check_q(q)

    def test_missing_AS_observation(self):
        q, proofs = self.proof(); p = Path(proofs['linux']['receipt']); s = json.loads(p.read_text()); s['Linux_AS_bytes'] = None; p.write_text(json.dumps(s))
        with self.assertRaises(ValueError): self.check_q(q)

    def test_no_manual_source_review(self):
        q, _ = self.proof(); q['astra_manual_review'] = False
        with self.assertRaises(ValueError): self.check_q(q)

    def test_duplicate_CPU_group_rejected(self):
        q, _ = self.proof(); q['CPU_groups'][1] = copy.deepcopy(q['CPU_groups'][0])
        with self.assertRaises(ValueError): self.check_q(q)

    def test_source_omitted_from_qualification(self):
        q, _ = self.proof(); del q['files'][str(c.HERE / 'construct_pack.py')]
        with self.assertRaises(ValueError): self.check_q(q)

    def test_raw_log_pin_omitted(self):
        q, proofs = self.proof(); del q['files'][proofs['linux']['log']]
        with self.assertRaises(ValueError): self.check_q(q)

    def test_current_source_hash_must_match_group(self):
        q, _ = self.proof(); q['CPU_groups'][1]['source_sha256']['construct_pack.py'] = '0' * 64
        with self.assertRaises(ValueError): self.check_q(q)

    def test_successful_supervision_one_child_cleanup_even_after_exit(self):
        proc = Mock(pid=777); proc.wait.return_value = 0; proc.poll.return_value = 0
        with patch.object(c.subprocess, 'Popen', return_value=proc) as popen, patch.object(c, 'cleanup', return_value=[]) as cleanup:
            result = c.supervise(['synthetic-only'], self.e, c.CHILD_ENV)
        self.assertEqual(result['returncode'], 0); self.assertIsNone(result['error'])
        self.assertEqual(popen.call_count, 1); cleanup.assert_called_once_with(proc)
        self.assertTrue(popen.call_args.kwargs['start_new_session']); self.assertEqual(proc.wait.call_args.kwargs['timeout'], 90)

    def test_timeout_kept_no_second_child(self):
        proc = Mock(pid=777); proc.wait.side_effect = c.subprocess.TimeoutExpired('synthetic', 90); proc.poll.return_value = -15
        with patch.object(c.subprocess, 'Popen', return_value=proc) as popen, patch.object(c, 'cleanup', return_value=[]):
            result = c.supervise(['synthetic-only'], self.e, c.CHILD_ENV)
        self.assertIn('TimeoutExpired', result['error']); self.assertEqual(result['returncode'], -15); self.assertEqual(popen.call_count, 1)

    def test_first_child_fault_kept_no_second_child(self):
        proc = Mock(pid=777); proc.wait.return_value = 1; proc.poll.return_value = 1
        with patch.object(c.subprocess, 'Popen', return_value=proc) as popen, patch.object(c, 'cleanup', return_value=[]):
            result = c.supervise(['synthetic-only'], self.e, c.CHILD_ENV)
        self.assertEqual(result['returncode'], 1); self.assertEqual(popen.call_count, 1)

    def test_exited_parent_descendants_still_cleaned(self):
        proc = Mock(pid=777); proc.poll.return_value = 0
        with patch.object(c, 'gone', side_effect=[False, True, True, True]), patch.object(c.os, 'killpg') as kill:
            self.assertEqual(c.cleanup(proc), [])
        kill.assert_called_once_with(777, c.signal.SIGTERM)

    def test_active_private_phase_guard_before_pack_output_write(self):
        gate = Mock(side_effect=RuntimeError('private phase active'))
        fake = Mock(); fake.SelectedGate.return_value = gate
        with patch.object(c, 'HERE', self.e), patch.object(c, 'qualified', return_value={}), patch.object(c, 'acquisition_module', return_value=fake), \
             patch.object(c, 'completed_receipt'), patch.object(c.g, 'sha', return_value='x'):
            # Constructor of the gate is the real fresh-health/phase boundary.
            fake.SelectedGate.side_effect = RuntimeError('private phase active')
            with self.assertRaisesRegex(RuntimeError, 'private phase active'): c.run(self.e / 'q', 'x')
        self.assertFalse((c.HERE / 'construct-CPU-FIRST').exists())


if __name__ == '__main__': unittest.main()
