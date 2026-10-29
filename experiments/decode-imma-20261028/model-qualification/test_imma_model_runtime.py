"""CPU-only lifecycle controls. Actual canonical coordinate, scripted host only.

No production module import, subprocess, network, native binary or service runs.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import imma_model_runtime as r

LOCAL_E = Path(__file__).resolve().parents[2]
BIND = {'invocation': 'a' * 32, 'main_pid': 10, 'native_pid': 11, 'native_start_ticks': 12}
NEW = {'invocation': 'b' * 32, 'main_pid': 20, 'native_pid': 21, 'native_start_ticks': 22}
Q = 'c' * 64


class Deferred(RuntimeError): pass


def canonical():
    path = LOCAL_E / 'decode-profile-v1/maintenance.py'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != r.COORDINATE_SHA:
        raise ValueError('Actual canonical coordinate source changed')
    tree = ast.parse(raw)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'coordinate')
    env = {'pathlib': SimpleNamespace(Path=Path), 'AdmissionDeferred': Deferred,
           'time': SimpleNamespace(sleep=lambda delay: None), 'emit': r.emit}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), env)
    return env['coordinate']


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.e = self.root / 'e'; self.p = self.e / 'model-v1'; self.d = self.root / 'host'
        for path in (self.e / 'results', self.e / 'maintenance', self.p, self.d / 'receipts'):
            path.mkdir(parents=True, exist_ok=True)
        for name, value in [('E', self.e), ('P', self.p), ('D', self.d), ('R', self.root), ('F', self.e / 'owner')]:
            context = patch.object(r, name, value); context.start(); self.addCleanup(context.stop)
        self.output = self.e / 'results/decode-imma-numerical-N0-20261029T010203Z'
        self.meta = self.e / 'maintenance' / self.output.name; self.meta.mkdir()
        self.initial = {'decode_optimization_current': {'selected_identity': {'start_binding': BIND}},
                        'chunk4096_activation': {'selected_identity': {'start_binding': dict(BIND, native_pid=999)}},
                        'unrelated_user_state': {'preserve': True}}
        r.emit(self.e / 'STATE.json', self.initial)

    def state(self):
        statuses = r.statuses('numerical', 'N0')
        return {'utc': '2026-10-29 01:02:03 UTC', 'mode': 'numerical', 'arm': 'N0',
                'output': str(self.output), 'proof_path': str(self.meta / 'proof.json'),
                'qualification_sha256': Q, 'running_status': statuses['running'],
                'complete_status': statuses['complete']}

    def global_state(self): return json.loads((self.e / 'STATE.json').read_text())

    def fake_support(self, fault=None):
        outer = self; events = []; flags = {'idle_calls': 0}
        class Base:
            start_binding = None; restored_pid = None; baseline_binding = None
            def guard_binding(self, expected_pid=None):
                b = r.binding_contract(self.start_binding)
                if expected_pid is not None and expected_pid != b['native_pid']: raise ValueError('Owner changed')
                events.append(('guard', b['native_pid'])); return b['native_pid']
            def target_identity(self):
                return {'native_pid': self.start_binding['native_pid'], 'start_binding': copy.deepcopy(self.start_binding)}
            def idle(self):
                flags['idle_calls'] += 1
                return not (fault == 'initial_busy' or (fault == 'late_busy' and flags['idle_calls'] >= 2))
            def native_pid(self): return (self.start_binding or self.baseline_binding)['native_pid']
            def previous(self): events.append(('previous',)); return outer.root / 'prior.json'
            def stop_router(self):
                if self.start_binding is None: self.baseline_reader().guard_binding(self.baseline_binding['native_pid'])
                events.append(('stop_router',))
            def stop_ds(self):
                if self.start_binding is None: self.baseline_reader().guard_binding(self.baseline_binding['native_pid'])
                events.append(('stop_ds',))
                b = self.start_binding or self.baseline_binding
                row = {'native_pid': b['native_pid'], 'server_pid': b['main_pid'], 'returncode': 0, 'closed': True}
                if fault == 'bad_close': row['returncode'] = 1
                (outer.d / 'receipts/native-close.jsonl').write_text(json.dumps(row) + '\n')
            def command(self, argv, timeout=15):
                events.append(('unit_exit_read',))
                b = self.start_binding or self.baseline_binding
                fields = {'InvocationID': b['invocation'], 'MainPID': '0', 'ActiveState': 'inactive',
                          'ExecMainCode': '1', 'ExecMainStatus': '0', 'Result': 'success'}
                if fault == 'bad_API_exit': fields['ExecMainStatus'] = '1'
                return SimpleNamespace(stdout='\n'.join(k + '=' + v for k, v in fields.items()) + '\n')
            def free(self): events.append(('free',))
            def kernel(self, since): events.append(('kernel', since))
            def launch_owned(self, prior, argv, timeout):
                events.append(('launch', timeout))
                if fault == 'private_fault': raise RuntimeError('private failure')
                return str(outer.root / 'new-window.json')
            def restore_ds(self):
                events.append(('restore',)); self.start_binding = dict(NEW); self.restored_pid = NEW['native_pid']
                if fault == 'foreign_restore':
                    foreign = outer.global_state(); foreign['maintenance_controller'] = '/new-owner/state.json'
                    r.emit(outer.e / 'STATE.json', foreign)
                    raise RuntimeError('restore failed after custody changed')
                if fault == 'partial_restore':
                    self.start_command_cleanup_error = 'command cleanup failure'
                    raise RuntimeError('primary startup failure')
            def restore_router(self): events.append(('restore_router',))
            def verify_target(self, expected_pid=None):
                events.append(('verify', expected_pid)); self.guard_binding(expected_pid)
                if fault == 'public_fault': raise RuntimeError('public failure')
                if fault == 'pending': return {'pending_public_probe': True, 'selected_identity': self.target_identity()}
                return {'passed': True, 'selected_identity': self.target_identity()}
            def cleanup_owned_target(self, pid):
                self.guard_binding(pid); events.append(('cleanup', pid))
                if fault == 'partial_restore': raise RuntimeError('owned cleanup failure')
        a = SimpleNamespace(ChunkProductionHost=Base,
                            m=SimpleNamespace(runtime=SimpleNamespace(old=SimpleNamespace(coordinate=canonical(), AdmissionDeferred=Deferred))))
        return a, events

    def host(self, fault=None):
        a, events = self.fake_support(fault)
        host = r.load_current_host(a, 'numerical', 'N0', self.meta, Q)
        host.since = self.state()['utc']
        host.extra_preflight = lambda output: {'caller_gate': True}
        host.phase_argv = lambda output, proof: [str(self.root / 'venv/bin/python3.14'), '-B',
                str(self.p / 'imma_numerical.py'), '--phase', '--arm', 'N0', '--output', str(output), '--proof', str(proof)]
        def reserve(output, proof):
            events.append(('reserve',)); (self.p / 'attempt.json').write_text(json.dumps({'output': str(output), 'proof': str(proof)}))
            if fault == 'reserve_fault': raise RuntimeError('attempt receipt fault')
        host.reserve_attempt = reserve
        return a, host, events

    def run_coordinate(self, fault=None, preflight_only=False, root_bytes=200 * 2**30):
        a, host, events = self.host(fault)
        saver = r.make_saver(host, self.meta, 'numerical', 'N0', not preflight_only)
        with patch.object(r, 'qualified', return_value={'files': {}, 'qualification_sha256': Q}), \
             patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=200 * 2**30)):
            result = r.coordinate_mode(a, host, self.output, self.state(), saver,
                                       preflight_only=preflight_only, root_free=lambda: root_bytes)
        return result, host, events


class BindingPaths(TempCase):
    def test_current_binding_not_historical_activation(self):
        self.assertEqual(r.current_binding(), BIND)
        self.assertNotEqual(r.current_binding()['native_pid'], 999)

    def test_fallback_only_when_current_identity_absent(self):
        self.assertEqual(r.current_binding({'chunk4096_activation': {'selected_identity': {'start_binding': BIND}}}), BIND)
        bad = copy.deepcopy(self.initial); bad['decode_optimization_current']['selected_identity']['start_binding'] = {}
        with self.assertRaises(ValueError): r.current_binding(bad)

    def test_binding_types_extras_and_invocation(self):
        for binding in (dict(BIND, native_pid=True), dict(BIND, native_start_ticks=0), dict(BIND, invocation='wrong'), dict(BIND, extra=1)):
            with self.assertRaises(ValueError): r.binding_contract(binding)

    def test_all_phase_and_stopped_markers_block(self):
        for key in r.PHASE_KEYS: self.assertFalse(r.phase_keys_free({key: True}), key)
        self.assertTrue(r.phase_keys_free({}))

    def test_exact_fresh_namespace_and_wrong_mode_arm(self):
        self.assertEqual(r.owned_paths(self.output, 'numerical', 'N0'), (self.output, self.meta))
        with self.assertRaises(ValueError): r.owned_paths(self.output, 'numerical', 'N1')
        with self.assertRaises(ValueError): r.owned_paths(self.output, 'performance', 'N0')
        with self.assertRaises(ValueError): r.owned_paths(self.root / self.output.name, 'numerical', 'N0')

    def test_existing_and_dangling_output_refused(self):
        self.output.mkdir()
        with self.assertRaises(ValueError): r.owned_paths(self.output, 'numerical', 'N0')
        self.output.rmdir(); self.output.symlink_to(self.root / 'missing')
        with self.assertRaises(ValueError): r.owned_paths(self.output, 'numerical', 'N0')

    def test_root_first_ancestor_symlink_rejected_before_child_read(self):
        alias = self.root / 'alias'; alias.symlink_to(self.e, target_is_directory=True)
        touched = []; original = Path.is_symlink
        def observe(path): touched.append(path); return original(path)
        with patch.object(Path, 'is_symlink', observe):
            with self.assertRaises(ValueError): r.real_directory(alias / 'results')
        self.assertIn(alias, touched); self.assertNotIn(alias / 'results', touched)

    def test_real_file_hardlink_and_receipt_temp_residue_refused(self):
        f = self.meta / 'file'; f.write_text('x'); os.link(f, self.meta / 'alias')
        with self.assertRaises(ValueError): r.real_file(f)
        (self.meta / 'state.json.tmp').write_text('preserve')
        with self.assertRaises(ValueError): r.emit(self.meta / 'state.json', {})
        self.assertEqual((self.meta / 'state.json.tmp').read_text(), 'preserve')

    def test_current_host_has_no_restored_cleanup_authority(self):
        a, host, events = self.host()
        self.assertEqual(host.baseline_binding, BIND)
        self.assertIsNone(host.start_binding); self.assertIsNone(host.restored_pid)
        self.assertFalse(host.old_close_verified); self.assertEqual(events, [])


class CanonicalLifecycle(TempCase):
    def test_actual_canonical_success_captures_old_API_and_native_before_restore(self):
        result, host, events = self.run_coordinate()
        self.assertEqual(result['status'], r.statuses('numerical', 'N0')['complete'])
        close = json.loads((self.meta / 'old-owner-close.json').read_text())
        self.assertTrue(close['passed']); self.assertEqual(close['native_close']['returncode'], 0)
        self.assertEqual(close['before']['ExecMainStatus'], '0')
        self.assertEqual(close['before']['InvocationID'], BIND['invocation'])
        self.assertLess(events.index(('unit_exit_read',)), events.index(('restore',)))
        self.assertLess(events.index(('reserve',)), events.index(('launch', 1200)))
        self.assertEqual(r.current_binding(), NEW)
        self.assertFalse(self.global_state()['active_private_phase'])
        self.assertEqual(self.global_state()['unrelated_user_state'], {'preserve': True})

    def test_readonly_does_not_claim_or_drain(self):
        result, host, events = self.run_coordinate(preflight_only=True)
        self.assertEqual(result['status'], 'READ_ONLY_PREFLIGHT_PASS')
        self.assertEqual(self.global_state(), self.initial)
        self.assertNotIn(('stop_router',), events); self.assertFalse((self.p / 'attempt.json').exists())

    def test_initial_busy_defers_before_hash_claim_or_callback(self):
        a, host, events = self.host('initial_busy')
        saver = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        with patch.object(r, 'qualified', side_effect=AssertionError('hash must not run')):
            result = r.coordinate_mode(a, host, self.output, self.state(), saver)
        self.assertEqual(result['status'], 'DEFERRED_NO_PRODUCTION_MUTATION')
        self.assertEqual(events, []); self.assertEqual(self.global_state(), self.initial)

    def test_late_busy_deferral_keeps_entire_global_state(self):
        result, host, events = self.run_coordinate('late_busy')
        self.assertEqual(result['status'], 'DEFERRED_BUSY_OR_MANUAL_MODEL_NO_MUTATION')
        self.assertEqual(self.global_state(), self.initial); self.assertNotIn(('stop_router',), events)

    def test_root_admission_before_source_and_drain(self):
        a, host, events = self.host()
        with patch.object(r, 'qualified', side_effect=AssertionError('hash must not run')), \
             patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=131 * 2**30)):
            with self.assertRaises(Deferred): host.preflight(self.output)
        self.assertEqual(events, [])

    def test_current_binding_change_blocks_preflight_before_qualification(self):
        a, host, events = self.host()
        changed = copy.deepcopy(self.initial); changed['decode_optimization_current']['selected_identity']['start_binding'] = NEW
        r.emit(self.e / 'STATE.json', changed)
        with patch.object(r, 'qualified', side_effect=AssertionError('must not hash')), \
             patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=200 * 2**30)):
            with self.assertRaises(ValueError): host.preflight(self.output)
        self.assertEqual(events, [])

    def test_postdrain_root_refusal_restores_once_without_attempt(self):
        result, host, events = self.run_coordinate(root_bytes=125 * 2**30)
        self.assertEqual(result['status'], 'DEFERRED_PRIVATE_ADMISSION_SELECTED_DS_RESTORED')
        self.assertEqual(events.count(('restore',)), 1); self.assertNotIn(('reserve',), events)
        self.assertFalse((self.p / 'attempt.json').exists()); self.assertEqual(r.current_binding(), NEW)

    def test_postdrain_below_restore_floor_holds_without_restart(self):
        with self.assertRaises(ValueError): self.run_coordinate(root_bytes=119 * 2**30)
        self.assertEqual(self.global_state()['decode_optimization_current']['status'], 'STOPPED_FOR_OFFLINE_DIAGNOSIS')
        self.assertFalse((self.p / 'attempt.json').exists())

    def test_old_native_nonzero_blocks_private_and_restore(self):
        with self.assertRaises(ValueError): self.run_coordinate('bad_close')
        close = json.loads((self.meta / 'old-owner-close.json').read_text())
        self.assertFalse(close['passed']); self.assertEqual(close['native_close']['returncode'], 1)
        self.assertFalse((self.p / 'attempt.json').exists())

    def test_old_API_nonzero_preserved_and_blocks_private(self):
        with self.assertRaises(ValueError): self.run_coordinate('bad_API_exit')
        close = json.loads((self.meta / 'old-owner-close.json').read_text())
        self.assertEqual(close['before']['ExecMainStatus'], '1'); self.assertFalse(close['passed'])
        self.assertFalse((self.p / 'attempt.json').exists())

    def test_private_fault_keeps_attempt_and_does_not_restore(self):
        a, host, events = self.host('private_fault'); saver = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        with patch.object(r, 'qualified', return_value={'files': {}}), \
             patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=200 * 2**30)):
            with self.assertRaisesRegex(RuntimeError, 'private failure'):
                r.coordinate_mode(a, host, self.output, self.state(), saver)
        self.assertTrue((self.p / 'attempt.json').exists()); self.assertNotIn(('restore',), events)

    def test_attempt_receipt_fault_cannot_launch_or_retry(self):
        a, host, events = self.host('reserve_fault'); saver = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        with patch.object(r, 'qualified', return_value={'files': {}}), \
             patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=200 * 2**30)):
            with self.assertRaisesRegex(RuntimeError, 'attempt receipt fault'):
                r.coordinate_mode(a, host, self.output, self.state(), saver)
        self.assertTrue(host.private_attempted); self.assertNotIn(('launch', 1200), events)

    def test_partial_restore_retains_primary_and_both_cleanup_errors(self):
        with self.assertRaisesRegex(RuntimeError, 'primary startup failure'): self.run_coordinate('partial_restore')
        hold = self.global_state()['decode_optimization_current']
        self.assertIn('primary startup failure', hold['error'])
        self.assertIn('owned cleanup failure', hold['cleanup_error'])
        self.assertEqual(hold['start_command_cleanup_error'], 'command cleanup failure')
        self.assertEqual(hold['start_binding'], NEW)

    def test_public_fault_cleans_only_bound_restored_owner(self):
        a, host, events = self.host('public_fault'); saver = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        with patch.object(r, 'qualified', return_value={'files': {}}), \
             patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=200 * 2**30)):
            with self.assertRaisesRegex(RuntimeError, 'public failure'):
                r.coordinate_mode(a, host, self.output, self.state(), saver)
        self.assertEqual([x for x in events if x[0] == 'cleanup'], [('cleanup', NEW['native_pid'])])

    def test_foreign_custody_during_restore_never_cleanup_or_global_overwrite(self):
        a, host, events = self.host('foreign_restore'); saver = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        with patch.object(r, 'qualified', return_value={'files': {}}), \
             patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=200 * 2**30)):
            with self.assertRaisesRegex(RuntimeError, 'restore failed after custody changed'):
                r.coordinate_mode(a, host, self.output, self.state(), saver)
        self.assertEqual(self.global_state()['maintenance_controller'], '/new-owner/state.json')
        self.assertFalse(any(x[0] == 'cleanup' for x in events))

    def test_pending_normalizes_actual_canonical_result_and_blocks_admission(self):
        result, host, events = self.run_coordinate('pending')
        self.assertEqual(result['status'], r.statuses('numerical', 'N0')['pending'])
        self.assertEqual(result['resume_terminal_status'], r.statuses('numerical', 'N0')['complete'])
        self.assertEqual(r.current_binding(), NEW)
        self.assertFalse(r.phase_keys_free(self.global_state()))
        self.assertFalse(self.global_state()['active_private_phase'])

    def test_used_host_cannot_enter_coordinate_again(self):
        a, host, events = self.host(); host.start_binding = dict(NEW)
        with self.assertRaises(ValueError): r.coordinate_mode(a, host, self.output, self.state(), lambda value: None)
        self.assertEqual(events, [])

    def test_foreign_phase_argv_stops_before_attempt(self):
        a, host, events = self.host(); host.phase_argv = lambda out, proof: ['/bin/false']
        r.emit(self.meta / 'proof.json', {'qualification_sha256': Q})
        with patch.object(r, 'qualified', return_value={}):
            with self.assertRaises(ValueError): host.launch('prior', self.output, self.meta / 'proof.json')
        self.assertNotIn(('reserve',), events)

    def test_proof_digest_mismatch_stops_before_attempt(self):
        a, host, events = self.host(); r.emit(self.meta / 'proof.json', {'qualification_sha256': 'd' * 64})
        with patch.object(r, 'qualified', side_effect=AssertionError('must not qualify')):
            with self.assertRaises(ValueError): host.launch('prior', self.output, self.meta / 'proof.json')
        self.assertNotIn(('reserve',), events)

    def test_canonical_HOLD_write_failure_retains_original_error(self):
        a, host, events = self.host('private_fault'); saver = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        def broken(value):
            if value['status'] == 'STOPPED_FOR_OFFLINE_DIAGNOSIS': raise OSError('HOLD receipt failed')
            saver(value)
        with patch.object(r, 'qualified', return_value={'files': {}}), \
             patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=200 * 2**30)):
            with self.assertRaisesRegex(RuntimeError, 'private failure') as exc:
                r.coordinate_mode(a, host, self.output, self.state(), broken)
        self.assertTrue(any('HOLD' in note for note in exc.exception.__notes__))


class SaverCustody(TempCase):
    def test_selected_identity_preserved_through_private_phase(self):
        a, host, events = self.host(); save = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        save(dict(self.state(), status='DRAINING_ROUTER'))
        save(dict(self.state(), status=r.statuses('numerical', 'N0')['running']))
        self.assertEqual(r.current_binding(), BIND)
        self.assertTrue(self.global_state()['active_gpu_experiment'])

    def test_foreign_controller_no_global_overwrite_or_baseline_cleanup(self):
        a, host, events = self.host(); save = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        save(dict(self.state(), status='DRAINING_ROUTER'))
        foreign = self.global_state(); foreign['maintenance_controller'] = '/foreign/state.json'
        r.emit(self.e / 'STATE.json', foreign)
        with self.assertRaises(r.PendingCustodyChanged): save(dict(self.state(), status=r.statuses('numerical', 'N0')['running']))
        save(dict(self.state(), status='STOPPED_FOR_OFFLINE_DIAGNOSIS', error='original failure'))
        self.assertEqual(self.global_state(), foreign); self.assertEqual(events, [])

    def test_canonical_change_after_local_receipt_blocks_commit(self):
        a, host, events = self.host(); save = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        original = r.emit; foreign = dict(self.initial, maintenance_controller='foreign')
        def change(path, value):
            original(path, value)
            if path == self.meta / 'state.json': original(self.e / 'STATE.json', foreign)
        with patch.object(r, 'emit', side_effect=change):
            with self.assertRaises(r.PendingCustodyChanged): save(dict(self.state(), status='DRAINING_ROUTER'))
        self.assertEqual(self.global_state(), foreign)


class PendingOnly(TempCase):
    def prepare(self, fault=None):
        a, events = self.fake_support(fault)
        value = dict(self.state(), status=r.statuses('numerical', 'N0')['pending'],
                     resume_terminal_status=r.statuses('numerical', 'N0')['complete'], start_binding=NEW,
                     kernel_since='ORIGINAL INTERVAL', controller_pid=700000)
        current = dict(self.initial, decode_optimization_current=value, maintenance_controller=str(self.meta / 'state.json'),
                       production_verification_pending=str(self.meta / 'state.json'), active_private_phase=None)
        r.emit(self.meta / 'state.json', value); r.emit(self.e / 'STATE.json', current)
        return a, events, current

    def test_pending_busy_is_readonly_before_hash_or_probe(self):
        a, events, before = self.prepare('initial_busy')
        with patch.object(r, 'pid_alive', return_value=False), patch.object(r, 'qualified', side_effect=AssertionError('hash forbidden')):
            self.assertEqual(r.verify_pending(a, self.meta, 'numerical', 'N0')['status'], 'DEFERRED_BUSY_UNTOUCHED')
        self.assertEqual(self.global_state(), before); self.assertFalse(any(x[0] == 'verify' for x in events))

    def test_pending_once_same_binding_original_interval_no_restart(self):
        a, events, before = self.prepare()
        with patch.object(r, 'pid_alive', return_value=False), patch.object(r, 'qualified', return_value={}) as qualified:
            result = r.verify_pending(a, self.meta, 'numerical', 'N0')
        qualified.assert_called_once_with('numerical', Q)
        self.assertEqual(result['kernel_since'], 'ORIGINAL INTERVAL')
        self.assertEqual([x for x in events if x[0] == 'verify'], [('verify', NEW['native_pid'])])
        self.assertFalse(any(x[0] in ('restore', 'launch') for x in events))
        with self.assertRaises(ValueError): r.verify_pending(a, self.meta, 'numerical', 'N0')

    def test_pending_changed_qualification_no_probe_cleanup_or_restart(self):
        a, events, before = self.prepare()
        with patch.object(r, 'pid_alive', return_value=False), patch.object(r, 'qualified', side_effect=ValueError('changed')):
            with self.assertRaises(ValueError): r.verify_pending(a, self.meta, 'numerical', 'N0')
        self.assertEqual(self.global_state(), before)
        self.assertFalse(any(x[0] in ('verify', 'cleanup', 'restore') for x in events))

    def test_pending_original_controller_alive_blocks(self):
        a, events, before = self.prepare()
        with patch.object(r, 'pid_alive', return_value=True):
            with self.assertRaises(ValueError): r.verify_pending(a, self.meta, 'numerical', 'N0')
        self.assertEqual(events, [])

    def test_pending_public_fault_owned_cleanup_HOLD(self):
        a, events, before = self.prepare('public_fault')
        with patch.object(r, 'pid_alive', return_value=False), patch.object(r, 'qualified', return_value={}):
            with self.assertRaisesRegex(RuntimeError, 'public failure'): r.verify_pending(a, self.meta, 'numerical', 'N0')
        self.assertIn(('cleanup', NEW['native_pid']), events)
        self.assertTrue(self.global_state()['production_temporarily_stopped'])

    def test_pending_foreign_controller_after_probe_no_cleanup(self):
        a, events, before = self.prepare(); original = a.ChunkProductionHost.verify_target
        foreign = dict(before, maintenance_controller='foreign')
        def change(host, expected_pid=None):
            result = original(host, expected_pid); r.emit(self.e / 'STATE.json', foreign); return result
        with patch.object(a.ChunkProductionHost, 'verify_target', change), patch.object(r, 'pid_alive', return_value=False), \
             patch.object(r, 'qualified', return_value={}):
            with self.assertRaises(r.PendingCustodyChanged): r.verify_pending(a, self.meta, 'numerical', 'N0')
        self.assertEqual(self.global_state(), foreign); self.assertFalse(any(x[0] == 'cleanup' for x in events))

    def test_pending_forged_output_or_completion_rejected_before_probe(self):
        for key, bad in [('output', '/foreign'), ('proof_path', '/foreign/proof.json'), ('resume_terminal_status', 'MADE_UP')]:
            a, events, before = self.prepare()
            value = json.loads((self.meta / 'state.json').read_text()); value[key] = bad
            r.emit(self.meta / 'state.json', value)
            with self.assertRaises(ValueError): r.verify_pending(a, self.meta, 'numerical', 'N0')
            self.assertEqual(events, [])


class CloseMetadata(TempCase):
    def test_raw_close_contract_rejects_pid_bool_replacement_and_nonzero_API(self):
        good = {'InvocationID': BIND['invocation'], 'MainPID': '0', 'ActiveState': 'inactive',
                'ExecMainCode': '1', 'ExecMainStatus': '0', 'Result': 'success'}
        row = {'native_pid': 11, 'server_pid': 10, 'returncode': 0, 'closed': True}
        self.assertTrue(r.close_contract(BIND, row, good, good))
        for bad in (dict(row, returncode=False), dict(row, native_pid=21), dict(row, server_pid=True)):
            with self.assertRaises(ValueError): r.close_contract(BIND, bad, good, good)
        for field, value in [('InvocationID', NEW['invocation']), ('MainPID', '20'), ('ActiveState', 'active'),
                             ('ExecMainCode', '2'), ('ExecMainStatus', '1'), ('Result', 'failed')]:
            bad = dict(good, **{field: value})
            with self.assertRaises(ValueError): r.close_contract(BIND, row, bad, bad)

    def test_raw_snapshot_missing_duplicate_or_unstable_refused(self):
        with self.assertRaises(ValueError): r.exit_snapshot_fields('MainPID=0\nMainPID=0\n')
        with self.assertRaises(ValueError): r.exit_snapshot_fields('MainPID=0\n')
        with self.assertRaises(ValueError): r.close_contract(BIND, {}, {}, {'changed': True})

    def test_bounded_close_tail_preserves_only_last_complete_metadata_row(self):
        f = self.d / 'receipts/native-close.jsonl'
        f.write_bytes(b'x' * 70000 + b'\n' + b'{"native_pid":11,"returncode":0}\n')
        self.assertEqual(r.last_close_row(f), {'native_pid': 11, 'returncode': 0})
        f.write_bytes(b'x' * 70000)
        with self.assertRaises(ValueError): r.last_close_row(f)

    def test_restore_without_raw_old_API_native_closure_refused(self):
        a, host, events = self.host()
        with self.assertRaises(ValueError): host.restore_ds()
        self.assertNotIn(('restore',), events)

    def test_close_primary_survives_secondary_receipt_write_error(self):
        a, host, events = self.host('bad_close'); host.stop_ds()
        with patch.object(r, 'emit', side_effect=OSError('close receipt failed')):
            with self.assertRaisesRegex(ValueError, 'Bound native close0') as exc: host.clean_stop(11)
        self.assertIn('close receipt failed', exc.exception.__notes__[0])


class Qualification(TempCase):
    def prepare_q(self):
        def write(path, text):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text); return r.sha(path)
        constants = [('OWNER_SHA', r.F / 'activate_chunk4096.py'), ('WINDOW_SHA', r.R / 'window.py'),
                     ('COORDINATE_SHA', r.E / 'decode-profile-v1/maintenance.py'),
                     ('PERFORMANCE_HELPER_SHA', r.E / 'prefill-cache-improvements-20261027/performance-v1/performance_mode.py')]
        paths = []
        for name, path in constants:
            pin = write(path, 'synthetic pinned source: ' + name)
            context = patch.object(r, name, pin); context.start(); self.addCleanup(context.stop); paths.append(path)
        candidate = self.root / 'candidate.bin'
        for name, path in [('BASE_NATIVE', self.d / 'bin/maya-ds4'), ('BASE_SHA', self.d / 'config.json'),
                           ('CANDIDATE_NATIVE', candidate)]:
            pin = write(path, 'synthetic pinned artifact: ' + name)
            context = patch.object(r.config, name, pin); context.start(); self.addCleanup(context.stop); paths.append(path)
        context = patch.object(r.config, 'CANDIDATE_EXE', candidate); context.start(); self.addCleanup(context.stop)
        source_names = ['imma_model_runtime.py', 'test_imma_model_runtime.py', 'imma_numerical.py']
        for name in source_names + ['qualify_numerical_cpu.py', 'imma_config.py', 'imma_storage.py', 'base-config.json']:
            path = self.p / name; write(path, 'synthetic source ' + name); paths.append(path)
        sources = {name: r.sha(self.p / name) for name in source_names}
        for label in ('darwin', 'linux'):
            directory = self.p / ('numerical-CPU-' + label); directory.mkdir()
            proof = {'passed': True, 'source_sha256': sources, 'test_ids': ['synthetic.test'], 'controls': 1,
                     'native_execution': False, 'GPU_execution': False}
            child = {'returncode': 0, 'CPU_s': 30, 'wall_s': 90, 'nice': 15, 'CUDA_hidden': True,
                     'Linux_AS_MiB': 512 if label == 'linux' else None}
            for name, value in [('receipt.json', json.dumps(proof)), ('child.json', json.dumps(child)), ('child.log', 'OK\n')]:
                path = directory / name; write(path, value); paths.append(path)
        q = {'mode': 'numerical', 'source_manually_reviewed': True, 'CPU_both_hosts_passed': True,
             'files': {str(path): r.sha(path) for path in paths}, 'source_sha256': sources, 'test_ids': ['synthetic.test']}
        r.emit(self.p / 'numerical-qualification.json', q)
        return q

    def test_exact_qualification_source_CPU_and_digest(self):
        q = self.prepare_q(); pin = r.sha(self.p / 'numerical-qualification.json')
        self.assertEqual(r.qualified('numerical', pin)['qualification_sha256'], pin)

    def test_changed_qualification_bytes_rejected(self):
        self.prepare_q()
        with self.assertRaises(ValueError): r.qualified('numerical', 'f' * 64)

    def test_missing_canonical_window_owner_or_raw_child_pin_refused(self):
        q = self.prepare_q()
        for path in (r.R / 'window.py', r.F / 'activate_chunk4096.py', self.p / 'numerical-CPU-linux/child.log'):
            altered = copy.deepcopy(q); del altered['files'][str(path)]
            r.emit(self.p / 'numerical-qualification.json', altered)
            with self.assertRaises(ValueError): r.qualified('numerical')

    def test_changed_source_or_artifact_rejected(self):
        self.prepare_q(); (self.p / 'imma_numerical.py').write_text('changed')
        with self.assertRaises(ValueError): r.qualified('numerical')

    def test_wrong_mode_duplicate_ID_and_foreign_source_name_rejected(self):
        q = self.prepare_q()
        for change in ({'mode': 'performance'}, {'test_ids': ['same', 'same']},
                       {'source_sha256': dict(q['source_sha256'], **{'../foreign.py': 'a' * 64})}):
            altered = dict(q, **change); r.emit(self.p / 'numerical-qualification.json', altered)
            with self.assertRaises(ValueError): r.qualified('numerical')

    def test_changed_CPU_ID_or_bool_count_rejected_even_when_repinned(self):
        q = self.prepare_q(); path = self.p / 'numerical-CPU-linux/receipt.json'
        original = json.loads(path.read_text())
        for change in ({'test_ids': ['different']}, {'controls': True}, {'native_execution': True}, {'passed': False}):
            r.emit(path, dict(original, **change)); q['files'][str(path)] = r.sha(path)
            r.emit(self.p / 'numerical-qualification.json', q)
            with self.assertRaises(ValueError): r.qualified('numerical')

    def test_nonzero_bool_child_exit_and_relaxed_limits_rejected(self):
        q = self.prepare_q(); path = self.p / 'numerical-CPU-linux/child.json'; original = json.loads(path.read_text())
        for change in ({'returncode': False}, {'returncode': 1}, {'CPU_s': 60}, {'Linux_AS_MiB': 1024}, {'CUDA_hidden': False}):
            r.emit(path, dict(original, **change)); q['files'][str(path)] = r.sha(path)
            r.emit(self.p / 'numerical-qualification.json', q)
            with self.assertRaises(ValueError): r.qualified('numerical')


class SupportOrigins(TempCase):
    def test_actual_helper_alias_origins_and_foreign_alias_rejection(self):
        canonical_path = self.e / 'decode-profile-v1/maintenance.py'
        helper_path = self.e / 'prefill-cache-improvements-20261027/performance-v1/performance_mode.py'
        env = {'__name__': 'maintenance'}
        exec(compile('def coordinate(*args, **kwargs): pass', str(canonical_path), 'exec'), env)
        coordinate = env['coordinate']
        old = SimpleNamespace(__file__=str(helper_path), coordinate=coordinate)
        runtime = SimpleNamespace(__file__=str(r.F.parent / 'chunk4096_runtime.py'), old=old)
        mode = SimpleNamespace(__file__=str(r.F.parent / 'chunk4096_performance.py'), runtime=runtime)
        a = SimpleNamespace(__file__=str(r.F / 'activate_chunk4096.py'), m=mode)
        maintenance = SimpleNamespace(__file__=str(canonical_path), coordinate=coordinate)
        pins = {r.F / 'activate_chunk4096.py': r.OWNER_SHA, canonical_path: r.COORDINATE_SHA,
                helper_path: r.PERFORMANCE_HELPER_SHA}
        modules = {'activate_chunk4096': a, 'maintenance': maintenance,
                   'imma_config': SimpleNamespace(__file__=str(self.p / 'imma_config.py'))}
        before = list(r.sys.path)
        try:
            with patch.dict(r.sys.modules, modules), patch.object(r, 'sha', side_effect=lambda path: pins[Path(path)]), \
                 patch.object(r.importlib, 'import_module', return_value=a):
                self.assertEqual(r.support(), (a, old))
                old.__file__ = str(canonical_path)
                with self.assertRaises(ValueError): r.support()
                old.__file__ = str(helper_path); old.coordinate = lambda *args: None
                with self.assertRaises(ValueError): r.support()
        finally:
            r.sys.path[:] = before


if __name__ == '__main__':
    unittest.main(verbosity=2)
