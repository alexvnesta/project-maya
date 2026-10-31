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

import cpu_model_runtime as r

LOCAL_E = Path(__file__).resolve().parents[3]
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
        self.output = self.e / 'results/decode-cpu-iq2xs-numerical-N0-20261029T010203Z'
        self.meta = self.e / 'maintenance' / self.output.name; self.meta.mkdir()
        self.initial = {'decode_optimization_current': {'selected_identity': {'start_binding': BIND}},
                        'chunk4096_activation': {'selected_identity': {'start_binding': dict(BIND, native_pid=999)}},
                        'unrelated_user_state': {'preserve': True}}
        r.emit(self.e / 'STATE.json', self.initial)
        context = patch.object(r.controls, 'memory_available', return_value=128 * 2**30)
        self.memory = context.start(); self.addCleanup(context.stop)
        context = patch.object(r.controls, 'fence_collected', return_value={'passed': True})
        self.collection = context.start(); self.addCleanup(context.stop)

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
                output = Path(argv[argv.index('--output') + 1]); output.mkdir()
                r.emit(output / 'private-memory-fence.json', {'synthetic': True})
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
                str(self.p / 'cpu_model_numerical.py'), '--phase', '--arm', 'N0', '--output', str(output), '--proof', str(proof)]
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


class QualificationFixture(TempCase):
    """Real generic driver contracts over small synthetic files, never a child launch."""
    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')
        return r.sha(path)

    def patched(self, target, name, value):
        context = patch.object(target, name, value)
        result = context.start(); self.addCleanup(context.stop)
        return result

    def prepare_finite(self):
        report = self.p / 'finite-combined.json'; review = self.p / 'finite-independent.json'
        raw = self.p / 'finite-raw.txt'
        self.write(raw, 'synthetic accepted finite row evidence\n')
        self.write(report, {'status': 'COMPOSED_FINITE_SYNTHETIC_CPU_COVERAGE_46_JOBS_6336_CASE_ROWS_PASS',
            'native_candidate_sha256': r.config.CANDIDATE_NATIVE, 'combined_disjoint_jobs': 46,
            'combined_finite_case_rows': 6336, 'old_v4_job26_regraded': False})
        self.write(review, {'status': 'COMPOSED_FINITE_SYNTHETIC_46_JOB_6336_ROW_COVERAGE_PASS'})
        gate = {'status': 'CPU_IQ2XS_FINITE_PREREQUISITE_COMPLETE_NOT_MODEL_QUALIFICATION',
            'candidate_native_sha256': r.config.CANDIDATE_NATIVE, 'accepted_jobs': 46,
            'accepted_case_rows': 6336, 'old_failure_and_partial_regraded': False,
            'combined_result': str(report), 'combined_result_sha256': r.sha(report),
            'independent_review': str(review), 'independent_review_sha256': r.sha(review),
            'files': {str(f): r.sha(f) for f in (report, review, raw)}}
        self.write(self.p / 'finite-prerequisite.json', gate)
        self.patched(r, 'FINITE_GATE_SHA', r.sha(self.p / 'finite-prerequisite.json'))
        return {**gate['files'], str(self.p / 'finite-prerequisite.json'): r.FINITE_GATE_SHA}

    def prepare_q(self):
        paths = []
        for name, path in [('OWNER_SHA', r.F / 'activate_chunk4096.py'),
            ('WINDOW_SHA', r.R / 'window.py'),
            ('COORDINATE_SHA', self.e / 'decode-profile-v1/maintenance.py'),
            ('PERFORMANCE_HELPER_SHA', self.e / 'prefill-cache-improvements-20261027/performance-v1/performance_mode.py')]:
            self.patched(r, name, self.write(path, 'synthetic source ' + name)); paths.append(path)
        candidate = self.d / 'candidate.bin'
        for name, path in [('BASE_NATIVE', self.d / 'bin/maya-ds4'),
                           ('BASE_SHA', self.d / 'config.json'), ('CANDIDATE_NATIVE', candidate)]:
            self.patched(r.config, name, self.write(path, 'synthetic artifact ' + name)); paths.append(path)
        self.patched(r.config, 'CANDIDATE_EXE', candidate)
        source_names = ['cpu_driver.py', 'cpu_model_config.py', 'cpu_model_controls.py',
            'cpu_model_dependencies.py', 'cpu_model_numerical.py', 'cpu_model_numerical_audit.py',
            'cpu_model_runtime.py', 'test_cpu_model_runtime.py', 'test_synthetic_case.py']
        for name in source_names:
            self.write(self.p / name, '# synthetic source ' + name + '\n'); paths.append(self.p / name)
        # Copy the real stdlib-only driver. Importing definitions here cannot launch
        # its __main__; checked/bounds/attempt_contract themselves remain unmocked.
        driver_bytes = Path(__file__).with_name('cpu_driver.py').read_text()
        self.write(self.p / 'cpu_driver.py', driver_bytes)
        self.write(self.p / 'test_synthetic_case.py',
                   'class Control:\n    def test_retained(self):\n        pass\n')
        self.write(self.p / 'base-config.json', '{}\n'); paths.append(self.p / 'base-config.json')
        input_path = self.e / 'input.txt'; self.write(input_path, 'frozen synthetic input\n'); paths.append(input_path)
        sources = {name: r.sha(self.p / name) for name in source_names}
        inputs = {str(input_path): r.sha(input_path)}
        ids = ['test_synthetic_case.Control.test_retained']
        review = {'root_entire_new_source_tests_and_candidate_delta_read': True,
                  'astra_entire_new_source_tests_and_candidate_delta_read': True,
                  'source_sha256': sources, 'input_sha256': inputs, 'test_ids': ids}
        self.write(self.p / 'SOURCE_ROOT_REVIEW.json', review); paths.append(self.p / 'SOURCE_ROOT_REVIEW.json')
        review_pin = r.sha(self.p / 'SOURCE_ROOT_REVIEW.json')
        alias = 'cpu_iq2xs_model_portable_driver'
        absent = object(); previous = r.sys.modules.pop(alias, absent)
        def restore_module():
            r.sys.modules.pop(alias, None)
            if previous is not absent: r.sys.modules[alias] = previous
        self.addCleanup(restore_module)
        driver = r.exact_module(alias, self.p / 'cpu_driver.py', sources['cpu_driver.py'])
        for name, value in [('HERE', self.p), ('R', self.e), ('REMOTE', self.e),
                            ('SOURCES', source_names), ('INPUTS', inputs), ('TEST_MODULES', ['test_synthetic_case'])]:
            self.patched(driver, name, value)
        self.driver = driver
        before = (sources, inputs, ids)
        self.assertEqual(driver.checked(review_pin), before)
        for label, pid, parent_pid in [('darwin', 101, 100), ('linux', 201, 200)]:
            folder = self.p / ('CPU-FIRST-' + label)
            observed = {'pid': pid, 'ppid': parent_pid, 'pgid': pid, 'cpu': [30, 30],
                'as': [536870912, 536870912] if label == 'linux' else None, 'nice': 15,
                'environment': dict(driver.ENV), 'platform': label, 'dont_write_bytecode': True}
            attempt = {'review_sha256': review_pin, 'parent_pid': parent_pid,
                       'source_sha256': sources, 'input_sha256': inputs, 'test_ids': ids}
            child = {'pid': pid, 'returncode': 0, 'error': None, 'cleanup': [], 'elapsed_seconds': .25,
                     'argv': ['synthetic-python', '-I', '-B', str(self.p / 'cpu_driver.py'), '--child']}
            receipt = {'status': 'PASS', 'pid': pid, 'review_sha256': review_pin,
                'source_sha256': sources, 'input_sha256': inputs, 'source_after_sha256': sources,
                'input_after_sha256': inputs, 'test_ids': ids, 'tests_run': 1,
                'observed': observed, 'post_observed': observed, 'failures': 0, 'errors': 0}
            for name, value in [('attempt.json', attempt), ('observed.json', observed), ('child.json', child),
                                ('receipt.json', receipt), ('child.log', 'synthetic control ... ok\nOK\n')]:
                self.write(folder / name, value); paths.append(folder / name)
            self.write(folder / 'parent.json', {'status': 'PASS', 'pid': pid, 'review_sha256': review_pin,
                'receipt_sha256': r.sha(folder / 'receipt.json'), 'child_sha256': r.sha(folder / 'child.json'),
                'log_sha256': r.sha(folder / 'child.log')}); paths.append(folder / 'parent.json')
        files = {str(f): r.sha(f) for f in paths}; files.update(self.prepare_finite())
        self.q = {'mode': 'numerical', 'source_manually_reviewed': True, 'CPU_both_hosts_passed': True,
                  'source_review_sha256': review_pin, 'files': files, 'source_sha256': sources,
                  'input_sha256': inputs, 'test_ids': ids}
        self.save_q(self.q)
        self.original_bytes = {Path(f): Path(f).read_bytes() for f in self.q['files']}
        return copy.deepcopy(self.q)

    def save_q(self, q):
        self.write(self.p / 'numerical-qualification.json', q)
        return r.sha(self.p / 'numerical-qualification.json')

    def reset_fixture(self):
        for path, raw in self.original_bytes.items(): path.write_bytes(raw)
        q = copy.deepcopy(self.q); self.save_q(q); return q

    def rewrite_cpu(self, q, label, name, value, *, fix_parent=True):
        folder = self.p / ('CPU-FIRST-' + label)
        self.write(folder / name, value); q['files'][str(folder / name)] = r.sha(folder / name)
        keys = {'receipt.json': 'receipt_sha256', 'child.json': 'child_sha256', 'child.log': 'log_sha256'}
        if fix_parent and name in keys:
            parent = json.loads((folder / 'parent.json').read_text())
            parent[keys[name]] = r.sha(folder / name)
            self.write(folder / 'parent.json', parent)
            q['files'][str(folder / 'parent.json')] = r.sha(folder / 'parent.json')


class FinitePrerequisite(QualificationFixture):
    def test_complete_finite_prerequisite_and_whole_qualification(self):
        q = self.prepare_q(); pin = self.save_q(q)
        gate = r.finite_prerequisite(q['files'])
        self.assertEqual((gate['accepted_jobs'], gate['accepted_case_rows']), (46, 6336))
        self.assertEqual(r.qualified('numerical', pin)['qualification_sha256'], pin)

    def test_missing_gate_or_any_finite_raw_membership_refuses(self):
        q = self.prepare_q()
        for name in ['finite-prerequisite.json', 'finite-raw.txt', 'finite-combined.json', 'finite-independent.json']:
            bad = copy.deepcopy(q['files']); del bad[str(self.p / name)]
            with self.subTest(name=name), self.assertRaises(ValueError): r.finite_prerequisite(bad)

    def test_changed_gate_bytes_or_unreviewed_digest_refuses(self):
        q = self.prepare_q(); path = self.p / 'finite-prerequisite.json'
        path.write_text(path.read_text() + ' ')
        with self.assertRaises(ValueError): r.finite_prerequisite(q['files'])

    def test_repin_does_not_allow_wrong_candidate_scope_or_regrade(self):
        self.prepare_q()
        changes = [('candidate_native_sha256', 'd' * 64), ('accepted_jobs', 45),
                   ('accepted_case_rows', 6335), ('old_failure_and_partial_regraded', True),
                   ('status', 'MODEL_QUALIFIED')]
        for key, value in changes:
            q = self.reset_fixture(); path = self.p / 'finite-prerequisite.json'
            gate = json.loads(path.read_text()); gate[key] = value; self.write(path, gate)
            q['files'][str(path)] = r.sha(path)
            with self.subTest(key=key), patch.object(r, 'FINITE_GATE_SHA', r.sha(path)):
                with self.assertRaises(ValueError): r.finite_prerequisite(q['files'])

    def test_report_digest_and_independent_review_digest_are_checked(self):
        self.prepare_q()
        for name in ['finite-combined.json', 'finite-independent.json']:
            q = self.reset_fixture(); path = self.p / name; path.write_text(path.read_text() + ' ')
            with self.subTest(name=name), self.assertRaises(ValueError): r.finite_prerequisite(q['files'])

    def test_repinned_report_cannot_change_candidate_counts_or_old_HOLD(self):
        self.prepare_q()
        for field, value in [('native_candidate_sha256', 'f' * 64), ('combined_disjoint_jobs', 45),
                             ('combined_finite_case_rows', 6335), ('old_v4_job26_regraded', True), ('status', 'PASS')]:
            q = self.reset_fixture(); report_path = self.p / 'finite-combined.json'
            report = json.loads(report_path.read_text()); report[field] = value; self.write(report_path, report)
            gate_path = self.p / 'finite-prerequisite.json'; gate = json.loads(gate_path.read_text())
            gate['combined_result_sha256'] = r.sha(report_path); gate['files'][str(report_path)] = r.sha(report_path)
            self.write(gate_path, gate); q['files'].update(gate['files']); q['files'][str(gate_path)] = r.sha(gate_path)
            with self.subTest(field=field), patch.object(r, 'FINITE_GATE_SHA', r.sha(gate_path)):
                with self.assertRaises(ValueError): r.finite_prerequisite(q['files'])

    def test_repinned_independent_review_must_have_exact_finite_status(self):
        q = self.prepare_q(); path = self.p / 'finite-independent.json'
        self.write(path, {'status': 'UNREVIEWED'})
        gate_path = self.p / 'finite-prerequisite.json'; gate = json.loads(gate_path.read_text())
        gate['independent_review_sha256'] = r.sha(path); gate['files'][str(path)] = r.sha(path)
        self.write(gate_path, gate); q['files'].update(gate['files']); q['files'][str(gate_path)] = r.sha(gate_path)
        with patch.object(r, 'FINITE_GATE_SHA', r.sha(gate_path)):
            with self.assertRaises(ValueError): r.finite_prerequisite(q['files'])


class CPUProofs(QualificationFixture):
    def test_actual_driver_positive_both_host_chain_without_child_launch(self):
        q = self.prepare_q()
        with patch.object(self.driver, 'supervise', side_effect=AssertionError('No child allowed')):
            self.assertIsNone(r.cpu_proofs(q))
        self.assertEqual(self.driver.__file__, str(self.p / 'cpu_driver.py'))

    def test_missing_driver_source_input_and_each_raw_member_refuses(self):
        q = self.prepare_q()
        paths = [self.p / 'cpu_driver.py', self.p / 'cpu_model_numerical.py', self.e / 'input.txt']
        paths += [self.p / ('CPU-FIRST-' + host) / name for host in ['darwin', 'linux']
                  for name in ['attempt.json', 'observed.json', 'receipt.json', 'child.json', 'child.log', 'parent.json']]
        for path in paths:
            bad = copy.deepcopy(q); del bad['files'][str(path)]
            with self.subTest(path=str(path)), self.assertRaises(ValueError): r.cpu_proofs(bad)

    def test_changed_source_input_manual_review_or_test_order_refuses(self):
        self.prepare_q()
        for path in [self.p / 'cpu_model_numerical.py', self.e / 'input.txt', self.p / 'SOURCE_ROOT_REVIEW.json']:
            q = self.reset_fixture(); path.write_text(path.read_text() + '# changed')
            with self.subTest(path=str(path)), self.assertRaises(ValueError): r.cpu_proofs(q)
        q = self.reset_fixture(); q['test_ids'] = ['foreign.test']
        with self.assertRaises(ValueError): r.cpu_proofs(q)

    def test_foreign_driver_module_origin_refuses_before_import(self):
        q = self.prepare_q()
        with patch.dict(r.sys.modules, {'cpu_iq2xs_model_portable_driver': SimpleNamespace(__file__=str(self.root / 'foreign.py'))}):
            with self.assertRaisesRegex(ValueError, 'Foreign module'): r.cpu_proofs(q)

    def test_repinned_failed_child_cleanup_and_elapsed_values_refuse(self):
        self.prepare_q()
        changes = [('returncode', 1), ('returncode', False), ('error', 'fault'), ('cleanup', ['survivor']),
                   ('elapsed_seconds', -1), ('elapsed_seconds', True), ('elapsed_seconds', float('nan')),
                   ('elapsed_seconds', float('inf')), ('elapsed_seconds', 90.1)]
        for key, value in changes:
            q = self.reset_fixture(); path = self.p / 'CPU-FIRST-linux/child.json'
            child = json.loads(path.read_text()); child[key] = value; self.rewrite_cpu(q, 'linux', 'child.json', child)
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): r.cpu_proofs(q)

    def test_repinned_receipt_counts_IDs_maps_and_postbounds_refuse(self):
        self.prepare_q()
        changes = [('status', 'FAIL'), ('pid', True), ('failures', False), ('errors', False),
                   ('failures', 1), ('tests_run', True), ('tests_run', 0), ('test_ids', ['different']),
                   ('source_after_sha256', {}), ('input_after_sha256', {}), ('post_observed', {}),
                   ('review_sha256', 'f' * 64)]
        for key, value in changes:
            q = self.reset_fixture(); path = self.p / 'CPU-FIRST-linux/receipt.json'
            receipt = json.loads(path.read_text()); receipt[key] = value
            self.rewrite_cpu(q, 'linux', 'receipt.json', receipt)
            with self.subTest(key=key), self.assertRaises(ValueError): r.cpu_proofs(q)

    def test_actual_bounds_PID_platform_AS_environment_and_bytecode_refuse(self):
        self.prepare_q()
        changes = [('pid', 999), ('ppid', 999), ('pgid', 999), ('platform', 'darwin'),
                   ('as', None), ('cpu', [60, 60]), ('nice', 0), ('environment', {}), ('dont_write_bytecode', False)]
        for key, value in changes:
            q = self.reset_fixture(); path = self.p / 'CPU-FIRST-linux/observed.json'
            observed = json.loads(path.read_text()); observed[key] = value
            self.rewrite_cpu(q, 'linux', 'observed.json', observed)
            with self.subTest(key=key), self.assertRaises(ValueError): r.cpu_proofs(q)

    def test_repin_of_log_does_not_repair_stale_parent_hash(self):
        q = self.prepare_q()
        self.rewrite_cpu(q, 'linux', 'child.log', 'changed log\n', fix_parent=False)
        with self.assertRaisesRegex(ValueError, 'parent chain'): r.cpu_proofs(q)

    def test_repinned_parent_or_attempt_identity_refuses(self):
        self.prepare_q()
        for name, key, value in [('parent.json', 'status', 'FAIL'), ('parent.json', 'pid', 999),
                                 ('parent.json', 'receipt_sha256', 'a' * 64),
                                 ('attempt.json', 'parent_pid', 999), ('attempt.json', 'source_sha256', {})]:
            q = self.reset_fixture(); path = self.p / 'CPU-FIRST-linux' / name
            row = json.loads(path.read_text()); row[key] = value; self.rewrite_cpu(q, 'linux', name, row)
            with self.subTest(name=name, key=key), self.assertRaises(ValueError): r.cpu_proofs(q)

    def test_manual_read_flags_cannot_be_replaced_by_matching_hash(self):
        q = self.prepare_q(); path = self.p / 'SOURCE_ROOT_REVIEW.json'; value = json.loads(path.read_text())
        value['astra_entire_new_source_tests_and_candidate_delta_read'] = False; self.write(path, value)
        q['source_review_sha256'] = r.sha(path); q['files'][str(path)] = r.sha(path)
        with self.assertRaisesRegex(ValueError, 'manual reads'): r.cpu_proofs(q)


class Qualification(QualificationFixture):
    def test_changed_qualification_bytes_rejected(self):
        self.prepare_q()
        with self.assertRaises(ValueError): r.qualified('numerical', 'f' * 64)

    def test_missing_canonical_owner_window_native_or_required_source_refuses(self):
        q = self.prepare_q()
        for path in [r.R / 'window.py', r.F / 'activate_chunk4096.py', self.d / 'bin/maya-ds4',
                     self.d / 'config.json', r.config.CANDIDATE_EXE, self.p / 'cpu_model_config.py',
                     self.p / 'SOURCE_ROOT_REVIEW.json']:
            bad = copy.deepcopy(q); del bad['files'][str(path)]; self.save_q(bad)
            with self.subTest(path=str(path)), self.assertRaises(ValueError): r.qualified('numerical')
        bad = copy.deepcopy(q); del bad['source_sha256']['cpu_model_controls.py']; self.save_q(bad)
        with self.assertRaises(ValueError): r.qualified('numerical')

    def test_wrong_mode_duplicate_ID_and_foreign_source_name_refuse(self):
        q = self.prepare_q()
        for change in [{'mode': 'performance'}, {'test_ids': ['same', 'same']},
                       {'source_sha256': dict(q['source_sha256'], **{'../foreign.py': 'a' * 64})},
                       {'source_manually_reviewed': False}, {'CPU_both_hosts_passed': False}]:
            bad = dict(q, **change); self.save_q(bad)
            with self.subTest(change=change), self.assertRaises(ValueError): r.qualified('numerical')

    def test_changed_input_fails_before_finite_or_CPU_consumption(self):
        self.prepare_q(); (self.e / 'input.txt').write_text('changed input')
        with patch.object(r, 'finite_prerequisite', side_effect=AssertionError('No late read')):
            with self.assertRaisesRegex(ValueError, 'Immutable input changed'): r.qualified('numerical')

    def test_q_mutation_during_CPU_validation_refuses_publication(self):
        self.prepare_q(); original = r.cpu_proofs
        def change(q):
            original(q)
            path = self.p / 'numerical-qualification.json'; path.write_text(path.read_text() + ' ')
        with patch.object(r, 'cpu_proofs', side_effect=change):
            with self.assertRaisesRegex(ValueError, 'Qualification changed during'): r.qualified('numerical')


class ResourceAndHold(TempCase):
    def test_poststop_memory_gate_follows_original_free_and_records_floor(self):
        a, host, events = self.host()
        self.memory.side_effect = lambda: (events.append(('memory',)) or 88 * 2**30)
        host.free()
        self.assertEqual(events, [('free',), ('memory',)])
        proof = json.loads((self.meta / 'post-stop-memory.json').read_text())
        self.assertEqual(proof, {'available_bytes': 88 * 2**30,
                                'required_bytes': 88 * 2**30, 'passed': True})
        self.collection.assert_not_called()

    def test_low_RAM_refusal_preserves_canonical_HOLD_without_private_or_start(self):
        a, host, events = self.host(); self.memory.return_value = 87 * 2**30
        saver = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        with patch.object(r, 'qualified', return_value={'files': {}}), \
             patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=200 * 2**30)):
            with self.assertRaises(r.ResourceAdmissionDeferred):
                r.coordinate_mode(a, host, self.output, self.state(), saver)
        self.assertTrue(host.old_close_verified)
        self.assertFalse(host.private_attempted)
        self.assertFalse(any(x[0] in ('restore', 'reserve', 'launch') for x in events))
        self.assertFalse(json.loads((self.meta / 'post-stop-memory.json').read_text())['passed'])
        self.assertEqual(self.global_state()['decode_optimization_current']['status'],
                         'STOPPED_FOR_OFFLINE_DIAGNOSIS')

    def test_original_free_fault_precedes_memory_or_fence_checks(self):
        a, host, events = self.host()
        with patch.object(a.ChunkProductionHost, 'free', side_effect=ValueError('GPU owner remains')):
            with self.assertRaisesRegex(ValueError, 'GPU owner'): host.free()
        self.memory.assert_not_called(); self.collection.assert_not_called()

    def test_private_free_collects_exact_owned_fence_without_new_RAM_gate(self):
        a, host, events = self.host()
        host.private_attempted = True; host.private_output = str(self.output)
        self.output.mkdir(); r.emit(self.output / 'private-memory-fence.json', {'synthetic': True})
        self.memory.side_effect = AssertionError('No second prewindow RAM admission')
        host.free()
        self.collection.assert_called_once_with(self.output, self.meta)
        self.assertEqual(events, [('free',)])

    def test_pre_fence_failure_does_not_fabricate_collection(self):
        a, host, events = self.host()
        host.private_attempted = True; host.private_output = str(self.output)
        host.free()
        self.collection.assert_not_called()
        self.assertFalse((self.meta / 'private-memory-fence-collected.json').exists())

    def test_collection_failure_stops_restore_and_retains_primary_notes(self):
        a, host, events = self.host('private_fault')
        saver = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        self.collection.side_effect = RuntimeError('transient still present')
        with patch.object(r, 'qualified', return_value={'files': {}}), \
             patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=200 * 2**30)):
            with self.assertRaisesRegex(RuntimeError, 'private failure') as caught:
                r.coordinate_mode(a, host, self.output, self.state(), saver)
        self.assertTrue(any('transient still present' in x for x in caught.exception.__notes__))
        self.assertNotIn(('restore',), events)
        self.assertEqual(self.global_state()['decode_optimization_current']['status'],
                         'STOPPED_FOR_OFFLINE_DIAGNOSIS')

    def test_foreign_HOLD_cannot_cleanup_target_or_collect_fence(self):
        a, host, events = self.host(); host.start_binding = dict(NEW); host.restored_pid = NEW['native_pid']
        host.private_attempted = True; host.private_output = str(self.output)
        before = self.global_state(); primary = RuntimeError('original')
        saved = []
        r.hold_owned(host, self.state(), saved.append, primary)
        self.assertEqual(self.global_state(), before); self.assertEqual(events, [])
        self.collection.assert_not_called()
        self.assertEqual(saved[0]['error'], "RuntimeError('original')")

    def test_own_HOLD_records_cleanup_error_and_secondary_save_error(self):
        a, host, events = self.host('partial_restore')
        save = r.make_saver(host, self.meta, 'numerical', 'N0', True)
        save(dict(self.state(), status='DRAINING_ROUTER'))
        host.start_binding = dict(NEW); host.restored_pid = NEW['native_pid']
        primary = RuntimeError('primary'); captured = []
        def broken(value):
            captured.append(value); raise OSError('secondary save')
        r.hold_owned(host, self.state(), broken, primary)
        self.assertEqual(events, [('guard', NEW['native_pid']), ('cleanup', NEW['native_pid'])])
        self.assertIn('owned cleanup failure', captured[0]['cleanup_error'])
        self.assertTrue(any('secondary save' in x for x in primary.__notes__))

    def test_capture_pending_start_delegates_exact_pinned_helper_without_class_patch(self):
        a, host, events = self.host(); calls = []
        before = dict(a.ChunkProductionHost.__dict__)
        helper = SimpleNamespace(capture=lambda target, previous, *, emit:
                                 calls.append((target, previous, emit)))
        with patch.object(r, 'exact_module', return_value=helper) as load:
            host.capture_pending_start(BIND['invocation'])
        load.assert_called_once_with('cpu_iq2xs_selected_startup',
            self.e / 'decode-optimization-20261028/head-batching-v1/head_startup.py',
            '53988e95be7c1883f7aeeb7ae2b87081da74d64b3f38eb43b6a274d93d1ff4f4')
        self.assertEqual(calls, [(host, BIND['invocation'], r.emit)])
        self.assertEqual(dict(a.ChunkProductionHost.__dict__), before)


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
                   'cpu_model_config': SimpleNamespace(__file__=str(self.p / 'cpu_model_config.py'))}
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
