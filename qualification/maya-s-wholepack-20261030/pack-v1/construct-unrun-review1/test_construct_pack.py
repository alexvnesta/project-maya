"""Prospective metadata caller only: all host/acquisition/construct actions mocked."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import construct_pack as c


class ConstructTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.e = Path(self.tmp.name); self.acq = self.e / 'acq'; self.acq.mkdir()
        self.patchers = [patch.object(c, 'E', self.e), patch.object(c, 'ACQ', self.acq)]
        for p in self.patchers: p.start(); self.addCleanup(p.stop)

    def test_source_pin_checks_content(self):
        path = self.e / 'source'; path.write_text('fixed')
        c.checked_files({str(path): c.g.sha(path)})
        path.write_text('changed')
        with self.assertRaises(ValueError): c.checked_files({str(path): '0' * 64})

    def test_foreign_source_path_rejected(self):
        with self.assertRaises(ValueError): c.checked_files({'/outside/file': '0' * 64})

    def test_empty_source_map_rejected(self):
        with self.assertRaises(ValueError): c.checked_files({})

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
        proofs = {}
        for label in ('darwin', 'linux'):
            rp = self.e / (label + '-receipt.json'); cp = self.e / (label + '-child.json')
            rec = copy.deepcopy(receipt); rec['Linux_AS_bytes'] = [512 * 2**20] * 2 if label == 'linux' else None
            rp.write_text(json.dumps(rec)); cp.write_text(json.dumps(child)); proofs[label] = {'receipt': str(rp), 'child': str(cp)}
        group = {'proofs': proofs, 'test_ids': ['new.test'], 'source_sha256': {'s': 'x'}, 'input_sha256': {'i': 'y'}}
        q = {'root_manual_review': True, 'astra_manual_review': True, 'pack_guard_both_physical_hosts_passed': True,
             'construct_controller_both_physical_hosts_passed': True, 'files': {'s': 'x'}, 'CPU_groups': [group, copy.deepcopy(group)]}
        return q, proofs

    def check_q(self, q):
        path = self.e / 'q.json'; path.write_text(json.dumps(q))
        with patch.object(c, 'checked_files'):
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


if __name__ == '__main__': unittest.main()
