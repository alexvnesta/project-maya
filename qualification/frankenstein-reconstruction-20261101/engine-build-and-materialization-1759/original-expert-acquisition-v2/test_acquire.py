"""New40-shard closure/coexistence controls only; no remote requests or weights."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import acquire as a


class Acquisition(unittest.TestCase):
    def binding(self): return {'main_pid': 5000, 'native_pid': 5001, 'native_start_ticks': 777}

    def state(self):
        return {'decode_optimization_current': {'selected_identity': {'start_binding': self.binding()}},
                **{key: False for key in a.PHASE_KEYS}}

    def record(self):
        return {'mode': 's2-iq3s-bulk-FIRST', 'qualification_sha256': 'a' * 64,
                'start_binding': self.binding(), 'controller_pid': 9999, 'controller_start_ticks': 12345}

    def view(self, state, admitted=True, verify=None):
        return a.phase_view(state, self.binding(), admitted=admitted, bulk_pin='a' * 64,
                            verify=a.bulk_contract if verify is None else verify)

    def test_exact_official_index_closure_is40_trunk_shards_and_correct_bytes(self):
        manifest = a.manifest()
        self.assertEqual(len(manifest['files']), 40)
        self.assertEqual(manifest['total_bytes'], 295672271408)
        self.assertEqual([r['path'] for r in manifest['files']],
                         ['original/model-%05d-of-00048.safetensors' % i for i in range(3, 43)])
        self.assertIn('actual1870 selection remains unfrozen until placement', manifest['scope'])

    def synthetic(self):
        names = ['model-00003-of-00048.safetensors', 'model-00004-of-00048.safetensors']
        index = {'weight_map': {}}
        for layer in range(2):
            for expert in range(2):
                for role in ('w1', 'w3', 'w2'):
                    for kind in ('weight', 'scale'):
                        index['weight_map']['layers.%d.ffn.experts.%d.%s.%s' % (layer, expert, role, kind)] = names[layer]
        meta = {'id': a.REPO, 'sha': a.REVISION, 'siblings': [
            {'rfilename': name, 'size': 12, 'lfs': {'size': 12, 'sha256': str(i) * 64}}
            for i, name in enumerate(names)]}
        return index, meta

    def test_all_three_roles_and_scales_are_required(self):
        index, meta = self.synthetic()
        self.assertEqual(len(a.derive_closure(index, meta, layers=2, experts=2)), 2)
        for suffix in ('w1.weight', 'w3.scale', 'w2.weight', 'w2.scale'):
            broken = copy.deepcopy(index)
            del broken['weight_map']['layers.1.ffn.experts.1.' + suffix]
            with self.assertRaises(ValueError): a.derive_closure(broken, meta, layers=2, experts=2)

    def test_foreign_revision_duplicate_metadata_and_nonlfs_refused(self):
        index, meta = self.synthetic()
        for mode in ('revision', 'duplicate', 'size', 'hash'):
            wrong = copy.deepcopy(meta)
            if mode == 'revision': wrong['sha'] = 'foreign'
            elif mode == 'duplicate': wrong['siblings'].append(wrong['siblings'][0])
            elif mode == 'size': wrong['siblings'][0]['lfs']['size'] = 13
            else: wrong['siblings'][0]['lfs']['sha256'] = 'bad'
            with self.assertRaises(ValueError): a.derive_closure(index, wrong, layers=2, experts=2)

    def test_full_remaining_disk_budget_includes_native_and_two_overlays_once(self):
        expected = 474531916504
        self.assertEqual(a.disk_admission(expected, a.TOTAL_BYTES, 36959958872), expected)
        with self.assertRaises(ValueError): a.disk_admission(expected - 1, a.TOTAL_BYTES, 36959958872)
        for retained in (-1, a.TOTAL_BYTES + 1, True):
            with self.assertRaises(ValueError): a.disk_admission(10**15, a.TOTAL_BYTES, retained)

    def test_CPU_receipt_requires_complete_controls_actual_bounds_and_clean_exit(self):
        sources, inputs, ids = {'source': 's'}, {'input': 'i'}, ['case']
        for label in ('mac', 'ubuntu'):
            proof = {'passed': True, 'physical_host': label, 'source_map': sources, 'input_map': inputs,
                'test_ids': ids, 'tests_run': 1, 'returncode': 0, 'failures': 0, 'errors': 0,
                'observed': {'platform': 'linux' if label == 'ubuntu' else 'darwin', 'cpu': [30, 30],
                    'nice': 15, 'as': [512 * 2**20] * 2 if label == 'ubuntu' else None,
                    'dont_write_bytecode': True, 'pid': 9999, 'pgid': 9999,
                    'environment': {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1',
                                    'OPENBLAS_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1'}}}
            a.cpu_proof_contract(proof, label, sources, inputs, ids)
            for key, value in [('tests_run', 0), ('returncode', 1), ('errors', 1), ('source_map', {})]:
                with self.assertRaises(ValueError):
                    a.cpu_proof_contract(dict(proof, **{key: value}), label, sources, inputs, ids)
            wrong = copy.deepcopy(proof); wrong['observed']['cpu'] = [120, 120]
            with self.assertRaises(ValueError): a.cpu_proof_contract(wrong, label, sources, inputs, ids)

    def test_initial_admission_never_allows_even_qualified_cpu_conversion(self):
        state = self.state(); state['active_cpu_build'] = self.record()
        verifier = Mock()
        with self.assertRaises(a.Deferred): self.view(state, admitted=False, verify=verifier)
        verifier.assert_not_called()

    def test_only_exact_qualified_conversion_is_normalized_after_admission(self):
        empty = self.state(); running = self.state(); running['active_cpu_build'] = self.record()
        self.assertEqual(self.view(empty), self.view(running))
        for key, value in (('mode', 's2-placement-native-compile'), ('qualification_sha256', 'b' * 64),
                           ('controller_pid', True), ('controller_start_ticks', 0), ('start_binding', {})):
            wrong = copy.deepcopy(running); wrong['active_cpu_build'][key] = value
            with self.assertRaises(a.Deferred): self.view(wrong)

    def test_every_private_or_restoration_phase_defers_before_bulk_identity(self):
        for key in a.PHASE_KEYS:
            if key == 'active_cpu_build': continue
            state = self.state(); state[key] = {'active': True}; verifier = Mock()
            with self.assertRaises(a.Deferred): self.view(state, verify=verifier)
            verifier.assert_not_called()

    def test_meaningful_snapshot_ignores_unrelated_state_progress(self):
        first = self.state(); second = copy.deepcopy(first); second['progress'] = {'bytes': 9000}
        self.assertEqual(self.view(first), self.view(second))
        second['decode_optimization_current']['selected_identity']['start_binding']['native_pid'] += 1
        with self.assertRaises(ValueError): self.view(second)

    def test_dead_identity_or_foreign_cpu_lock_stops_before_endpoint(self):
        for failure in ('pid', 'lock'):
            state = self.state(); state['active_cpu_build'] = self.record()
            verifier = Mock(side_effect=ValueError(failure))
            with self.assertRaises(a.Deferred): self.view(state, verify=verifier)

    def live_bulk_fixture(self, root):
        folder = root / 'iq3s-bulk-v1'; folder.mkdir()
        q = folder / 'qualification.json'
        q.write_text(json.dumps({'selected_binding': self.binding(), 'CPU_both_hosts_passed': True,
                                'entire_source_tests_driver_manually_read': True}))
        (root / 'cpu-build.lock').write_bytes(b'')
        record = self.record(); record['qualification_sha256'] = a.sha(q)
        owner = types.SimpleNamespace(process_ticks=Mock(return_value=record['controller_start_ticks']),
            lock_identity=Mock(return_value={'device_major': 1, 'device_minor': 2, 'inode': 3}),
            gpu_lock_row=Mock(return_value='exact CPU flock'))
        return record, owner

    def test_actual_live_cpu_controller_ticks_and_exact_flock_identity_are_checked(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); record, owner = self.live_bulk_fixture(root)
            read = Path.read_text
            def text(path, *args, **kwargs):
                return 'cpu lock rows' if str(path) == '/proc/locks' else read(path, *args, **kwargs)
            with patch.object(a, 'Q', root), patch.object(a, 'E', root), patch.object(Path, 'read_text', text):
                a.verify_live_bulk(record, self.binding(), record['qualification_sha256'], owner)
                owner.gpu_lock_row.assert_called_once_with('cpu lock rows',
                    {'device_major': 1, 'device_minor': 2, 'inode': 3}, record['controller_pid'])
                self.assertEqual(owner.process_ticks.call_count, 2)
                owner.process_ticks.side_effect = [record['controller_start_ticks'], record['controller_start_ticks'] + 1]
                with self.assertRaises(ValueError):
                    a.verify_live_bulk(record, self.binding(), record['qualification_sha256'], owner)
                owner.process_ticks.side_effect = None
                owner.gpu_lock_row.side_effect = ValueError('foreign holder')
                with self.assertRaises(ValueError):
                    a.verify_live_bulk(record, self.binding(), record['qualification_sha256'], owner)

    def gate(self, root, admitted=True):
        gate = object.__new__(a.SelectedGate)
        gate.binding = self.binding(); gate.q = {'future_bulk_qualification_sha256': 'a' * 64}
        gate.admitted = admitted; gate.owner = Mock()
        gate.host = types.SimpleNamespace(idle=Mock(return_value=True), get=Mock(return_value={}), guard_binding=Mock())
        gate.healthy = types.SimpleNamespace(health_contract=Mock())
        (root / 'STATE.json').write_text(json.dumps(self.state()))
        return gate

    def test_private_and_foreign_build_deferral_precedes_all_endpoints(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); gate = self.gate(root)
            for key in ('active_private_phase', 'production_restore_in_progress', 'active_cpu_build'):
                state = self.state(); state[key] = {'mode': 'native-build'}
                (root / 'STATE.json').write_text(json.dumps(state))
                with patch.object(a, 'E', root), patch.object(a, 'verify_live_bulk', side_effect=ValueError('foreign')):
                    with self.assertRaises(a.Deferred): gate()
                gate.host.get.assert_not_called(); gate.host.guard_binding.assert_not_called()

    def test_healthy_fault_and_owner_change_still_stop_passive_work(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); gate = self.gate(root)
            gate.healthy.health_contract.side_effect = ValueError('fault')
            with patch.object(a, 'E', root), self.assertRaises(ValueError): gate()
            gate.healthy.health_contract.side_effect = None
            def change(endpoint):
                state = self.state(); state['decode_optimization_current']['selected_identity']['start_binding']['native_pid'] = 6000
                (root / 'STATE.json').write_text(json.dumps(state)); return {}
            gate.host.get.side_effect = change
            with patch.object(a, 'E', root), self.assertRaises(ValueError): gate()

    def test_admitted_qualified_bulk_coexists_with_healthy_endpoint_observations(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); gate = self.gate(root)
            state = self.state(); state['active_cpu_build'] = self.record()
            (root / 'STATE.json').write_text(json.dumps(state))
            with patch.object(a, 'E', root), patch.object(a, 'verify_live_bulk',
                    side_effect=lambda record, binding, pin, owner: a.bulk_contract(record, binding, pin)):
                gate()
            gate.host.idle.assert_not_called()
            self.assertEqual(gate.host.get.call_count, 2)
            gate.healthy.health_contract.assert_called_once()

    def test_normal_bulk_completion_race_rechecks_only_meaningful_state_once(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); gate = self.gate(root)
            state = self.state(); state['active_cpu_build'] = self.record()
            (root / 'STATE.json').write_text(json.dumps(state))
            def released(*args):
                (root / 'STATE.json').write_text(json.dumps(self.state()))
                raise ValueError('lock just released after own CAS closure')
            with patch.object(a, 'E', root), patch.object(a, 'verify_live_bulk', side_effect=released):
                gate()
            self.assertEqual(gate.host.get.call_count, 2)

    def test_transport_reuses_qualified_mechanics_with_only128mib_rate(self):
        old = a.transport()
        self.assertEqual(old.RATE, 128 * 2**20); self.assertEqual(old.CHUNK, 128 * 2**20)
        source = Path(a.__file__).read_text()
        self.assertIn("(LEGACY / 'acquisition.lock').open('a')", source)
        self.assertNotIn('cas_state(', source)
        self.assertIn('old.acquire_file(spec, root, gate, deadline=deadline)', source)


if __name__ == '__main__': unittest.main(verbosity=2)
