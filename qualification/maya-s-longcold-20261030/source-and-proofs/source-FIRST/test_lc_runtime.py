"""Owned lifecycle tests with filesystem/process/service boundaries mocked."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import lc_config as config
import lc_runtime as r


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.e = Path(self.tmp.name).resolve(); self.p = self.e / 'mode'; self.p.mkdir()
        for n in ('results', 'maintenance'): (self.e / n).mkdir()
        self.patchers = [patch.object(r, 'E', self.e), patch.object(r, 'P', self.p)]
        for p in self.patchers: p.start(); self.addCleanup(p.stop)

    def test_phase_free(self): self.assertTrue(r.phase_free({}))

    def test_every_active_key_blocks(self):
        for key in r.PHASE_KEYS:
            with self.subTest(key=key): self.assertFalse(r.phase_free({key: True}))

    def test_emit_retains_residue(self):
        p = self.p / 'r.json'; p.with_name('r.json.tmp').write_text('interrupted')
        with self.assertRaises(ValueError): r.emit(p, {'x': 1})
        self.assertEqual(p.with_name('r.json.tmp').read_text(), 'interrupted')

    def test_emit_disallows_nan(self):
        with self.assertRaises(ValueError): r.emit(self.p / 'r.json', {'x': float('nan')})

    def test_owned_new_namespace(self):
        output, meta = r.owned_paths(self.e / 'results/maya-s-longcold-LC1-20261030T150000Z', 'longcold', 'LC1')
        self.assertEqual(meta, self.e / 'maintenance' / output.name)

    def test_replay_directory_rejected(self):
        out = self.e / 'results/maya-s-longcold-LC1-20261030T150000Z'; out.mkdir()
        with self.assertRaises(ValueError): r.owned_paths(out, 'longcold', 'LC1')

    def test_foreign_namespace_rejected(self):
        with self.assertRaises(ValueError): r.owned_paths(self.e / 'results/old-N0-20261030T150000Z', 'longcold', 'LC1')

    def test_leaf_symlink_rejected(self):
        out = self.e / 'results/maya-s-longcold-LC1-20261030T150000Z'; out.symlink_to(self.p, target_is_directory=True)
        with self.assertRaises(ValueError): r.owned_paths(out, 'longcold', 'LC1')

    def test_only_diagnostic_arm_unattempted(self): r.prerequisite('longcold', 'LC1', {})

    def test_attempted_arm_not_replayed(self):
        with self.assertRaises(ValueError): r.prerequisite('longcold', 'LC1', {'LC1': {'attempted': True}})


    def test_coordinate_primary_fault_kept(self):
        old = types.SimpleNamespace(coordinate=Mock(side_effect=RuntimeError('native rc1')))
        h = types.SimpleNamespace(audit_dir=self.e / 'maintenance/ours', controller_pid=77,
                                 restored_pid=None, start_binding=None)
        (self.e / 'STATE.json').write_text('{}'); save = Mock()
        with self.assertRaisesRegex(RuntimeError, 'native rc1'):
            r.coordinate(old, h, self.e / 'results/new', {}, save, preflight_only=False)
        self.assertEqual(save.call_args.args[0]['status'], 'STOPPED_FOR_OFFLINE_DIAGNOSIS')
        self.assertIn('native rc1', save.call_args.args[0]['error'])

    def test_coordinate_resource_refusal_separate(self):
        old = types.SimpleNamespace(coordinate=Mock(side_effect=r.ResourceAdmissionDeferred('low RAM'))); save = Mock()
        with self.assertRaises(r.ResourceAdmissionDeferred): r.coordinate(old, object(), 'unused', {}, save, preflight_only=False)
        save.assert_not_called()

    def test_owned_restored_target_cleanup(self):
        meta = self.e / 'maintenance/ours'; h = types.SimpleNamespace(audit_dir=meta, controller_pid=77,
             restored_pid=90, start_binding={'native_pid': 90}, cleanup_owned_target=Mock())
        (self.e / 'STATE.json').write_text(json.dumps({'maintenance_controller': str(meta / 'state.json'),
             'decode_optimization_current': {'controller_pid': 77}})); save = Mock()
        r.hold_owned(h, {}, save, RuntimeError('bad public'))
        h.cleanup_owned_target.assert_called_once_with(90)

    def test_foreign_target_not_cleaned(self):
        h = types.SimpleNamespace(audit_dir=self.e / 'maintenance/ours', controller_pid=77,
             restored_pid=90, start_binding={'native_pid': 90}, cleanup_owned_target=Mock())
        (self.e / 'STATE.json').write_text(json.dumps({'maintenance_controller': 'other',
             'decode_optimization_current': {'controller_pid': 88}}))
        r.hold_owned(h, {}, Mock(), RuntimeError('bad public')); h.cleanup_owned_target.assert_not_called()

    def test_cleanup_fault_retained_beside_primary(self):
        meta = self.e / 'maintenance/ours'; h = types.SimpleNamespace(audit_dir=meta, controller_pid=77,
             restored_pid=90, start_binding={'native_pid': 90}, cleanup_owned_target=Mock(side_effect=RuntimeError('cleanup failed')))
        (self.e / 'STATE.json').write_text(json.dumps({'maintenance_controller': str(meta / 'state.json'),
             'decode_optimization_current': {'controller_pid': 77}})); save = Mock()
        r.hold_owned(h, {}, save, RuntimeError('primary'))
        self.assertIn('primary', save.call_args.args[0]['error']); self.assertIn('cleanup failed', save.call_args.args[0]['cleanup_error'])


class CPUMembershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.p=self.root/'source';self.p.mkdir()
        patcher=patch.object(r,'P',self.p);patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.object(r,'E',self.root);patcher.start();self.addCleanup(patcher.stop)
        self.group={'source_sha256':{'new.py':'a'*64},'input_sha256':{'input.json':'b'*64},'proofs':{}}
        self.files={str(self.p/'new.py'):'a'*64,str(self.root/'input.json'):'b'*64}
        for host in ('darwin','linux'):
            paths={}
            for name in ('receipt','child','log'):
                f=self.root/(host+'-'+name);f.write_text('{}');paths[name]=str(f);self.files[str(f)]=r.sha(f)
            self.group['proofs'][host]=paths

    def test_source_input_and_all_six_raw_proofs_pinned(self):r.cpu_membership(self.group,self.files)

    def test_source_pin_omission_refused(self):
        self.files.pop(str(self.p/'new.py'))
        with self.assertRaises(ValueError):r.cpu_membership(self.group,self.files)

    def test_input_pin_omission_refused(self):
        self.files.pop(str(self.root/'input.json'))
        with self.assertRaises(ValueError):r.cpu_membership(self.group,self.files)

    def test_raw_log_omission_refused(self):
        self.files.pop(self.group['proofs']['linux']['log'])
        with self.assertRaises(ValueError):r.cpu_membership(self.group,self.files)

    def test_changed_raw_child_refused(self):
        Path(self.group['proofs']['linux']['child']).write_text('{"returncode":1}')
        with self.assertRaises(ValueError):r.cpu_membership(self.group,self.files)

    def test_one_host_not_qualification(self):
        self.group['proofs'].pop('linux')
        with self.assertRaises(ValueError):r.cpu_membership(self.group,self.files)


class HostTests(unittest.TestCase):
    def host(self):
        calls = []
        class Owner:
            restored_pid = None
            def free(self): calls.append('free')
            def idle(self): calls.append('idle'); return 'restored-idle'
        class Legacy(Owner):
            def restore_ds(self): calls.append('legacy'); return super().restore_ds()
        class Startup(Owner):
            def restore_ds(self): calls.append('fixed-startup'); return 'one-start'
        a = types.SimpleNamespace(ChunkProductionHost=Owner)
        legacy = types.SimpleNamespace(host_class=lambda a: Legacy)
        startup = types.SimpleNamespace(guarded_host=lambda a: Startup)
        h = r.make_host(a, object(), object(), legacy, startup)()
        h.private_attempted = False; h.get = Mock(return_value={'status': 'ok', 'loaded': True,
             'images': True, 'max_context': 1048576, 'busy': True,
             'switcher': {'active_model': 'deepseek', 'default_model': 'deepseek', 'fault': None}})
        return h, calls

    def test_startup_adapter_composed_without_legacy_launch(self):
        h, calls = self.host(); self.assertEqual(h.restore_ds(), 'one-start'); self.assertEqual(calls, ['legacy', 'fixed-startup'])

    def test_explicit_authorization_allows_healthy_active(self):
        h, _ = self.host(); self.assertTrue(h.idle())

    def test_different_default_blocks(self):
        h, _ = self.host(); h.get.return_value['switcher']['default_model'] = 'glm'; self.assertFalse(h.idle())

    def test_wrong_context_blocks(self):
        h, _ = self.host(); h.get.return_value['max_context'] = 262144; self.assertFalse(h.idle())

    def test_restored_public_verification_preserves_busy_deferral(self):
        h, calls = self.host(); h.restored_pid = 44; self.assertEqual(h.idle(), 'restored-idle'); self.assertEqual(calls, ['idle'])

    def test_poststop_low_memory_refuses_before_attempt(self):
        h, calls = self.host(); h.audit_dir = Path('/synthetic')
        with patch.object(r, 'memory_available', return_value=r.MEMORY_MAX + r.HOST_MARGIN - 1), patch.object(r, 'emit') as emit:
            with self.assertRaises(r.ResourceAdmissionDeferred): h.free()
        self.assertEqual(calls, ['free']); self.assertFalse(h.private_attempted); self.assertFalse(emit.call_args.args[1]['passed'])

    def test_poststop_observed_memory_allows(self):
        h, calls = self.host(); h.audit_dir = Path('/synthetic')
        with patch.object(r, 'memory_available', return_value=r.MEMORY_MAX + r.HOST_MARGIN), patch.object(r, 'emit'):
            h.free()
        self.assertEqual(calls, ['free'])

    def test_postwindow_cleanup_does_not_repeat_admission(self):
        h, calls = self.host(); h.private_attempted = True; h.collect_fence = Mock()
        with patch.object(r, 'memory_available') as available: h.free()
        available.assert_not_called(); self.assertEqual(calls, ['free'])
        h.collect_fence.assert_called_once_with()

    def test_collection_failure_prevents_clean_restore_path(self):
        h, calls = self.host(); h.private_attempted = True
        h.collect_fence = Mock(side_effect=RuntimeError('transient files remain'))
        with self.assertRaisesRegex(RuntimeError, 'transient files remain'): h.free()
        self.assertEqual(calls, ['free'])


class NarrowScope(unittest.TestCase):
    def test_exact_80_plus_8_poststop_bound(self):
        self.assertEqual(r.MEMORY_MAX, 85899345920)
        self.assertEqual(r.MEMORY_MAX + r.HOST_MARGIN, 94489280512)

    def test_old_or_second_arm_refused(self):
        for mode, arm in [('quality','QS1'), ('compatibility','CS1'), ('longcold','LC2')]:
            with self.subTest(mode=mode), self.assertRaises(ValueError): r.prerequisite(mode, arm, {})

    def test_foreign_registry_blocks_first_arm(self):
        with self.assertRaises(ValueError): r.prerequisite('longcold','LC1',{'foreign':{}})

    def test_empty_cpu_proofs_never_bypass_contract(self):
        with self.assertRaises(ValueError): r.cpu_membership({'proofs':{},'source_sha256':{},'input_sha256':{}},{})

    def test_changed_original_module_refused_before_import(self):
        with patch.object(r,'sha',return_value='0'*64), patch.object(r.importlib,'import_module') as load:
            with self.assertRaises(ValueError): r.original_module('ms_runtime')
        load.assert_not_called()

    def test_foreign_loaded_original_refused_without_replacing_it(self):
        foreign=types.SimpleNamespace(__file__='/foreign/ms_config.py')
        with patch.dict(r.sys.modules,{'ms_config':foreign}), patch.object(r.importlib,'import_module') as load:
            with self.assertRaises(ValueError): r.original_module('ms_runtime')
            self.assertIs(r.sys.modules['ms_config'],foreign)
        load.assert_not_called()

    def test_undeclared_original_name_refused(self):
        with self.assertRaises(ValueError): r.original_module('unknown')

    def test_pack_custody_delegates_only_to_pinned_original(self):
        old=types.SimpleNamespace(pack_custody=Mock(return_value='checked'))
        with patch.object(r,'original_module',return_value=old) as load:
            self.assertEqual(r.pack_custody({'files':{}}),'checked')
        load.assert_called_once_with('ms_runtime');old.pack_custody.assert_called_once_with({'files':{}})

    def test_closed_CS1_evidence_membership_required(self):
        with self.assertRaises(ValueError):r.closed_cs1({'files':{}})


class PriorClosure(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.files={}
        for name,pin in r.CS1_PINS.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((r.original_model_dir/name).read_bytes());self.files[str(path)]=pin
        snapshot=json.loads((self.root/'CS1/compatibility-arms-at-terminal.json').read_text())['CS1']
        self.current={**snapshot,'fully_reviewed':True,'accepted':False,'short_literal_compatibility_passed':True,
            'quality_or_performance_qualified':False,'original_audit_returncode':1,'original_audit_regraded':False,
            'no_automatic_next_arm':True,'completion_sha256':r.CS1_PINS['CS1/terminal-completion.json'],
            'completion_review_sha256':r.CS1_PINS['CS1_COMPLETION_ASTRA_RESULT_REVIEW.json']}
        p=patch.object(r,'original_model_dir',self.root);p.start();self.addCleanup(p.stop)
        self.path=self.root/'compatibility-arms.json';self.write()

    def write(self):self.path.write_text(json.dumps({'CS1':self.current}))

    def test_real_immutable_closed_evidence_distinct_from_reviewed_registry(self):
        self.assertTrue(r.closed_cs1({'files':self.files}))
        self.assertFalse(json.loads((self.root/'CS1/compatibility-arms-at-terminal.json').read_text())['CS1']['fully_reviewed'])

    def test_missing_or_changed_closed_proof_refused(self):
        for key in self.files:
            with self.subTest(path=key),self.assertRaises(ValueError):
                r.closed_cs1({'files':{k:v for k,v in self.files.items() if k!=key}})

    def test_mutable_registry_not_disguised_as_historical_pin(self):
        with self.assertRaises(ValueError):r.closed_cs1({'files':{**self.files,str(self.path):r.sha(self.path)}})

    def test_regrade_or_quality_promotion_refused(self):
        for key,value in [('accepted',True),('original_audit_regraded',True),('original_audit_returncode',0),
                          ('quality_or_performance_qualified',True),('fully_reviewed',False),('no_automatic_next_arm',False)]:
            before=dict(self.current);self.current[key]=value;self.write()
            with self.subTest(key=key),self.assertRaises(ValueError):r.closed_cs1({'files':self.files})
            self.current=before;self.write()

    def test_foreign_old_controller_refused(self):
        self.current['controller_pid']+=1;self.write()
        with self.assertRaises(ValueError):r.closed_cs1({'files':self.files})


if __name__=='__main__':unittest.main()
