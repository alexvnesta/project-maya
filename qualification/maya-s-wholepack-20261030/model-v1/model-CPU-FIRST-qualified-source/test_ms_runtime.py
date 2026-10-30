"""Owned lifecycle tests with filesystem/process/service boundaries mocked."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import ms_config as config
import ms_runtime as r


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.e = Path(self.tmp.name); self.p = self.e / 'mode'; self.p.mkdir()
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
        output, meta = r.owned_paths(self.e / 'results/maya-s-quality-QS0-20261030T150000Z', 'quality', 'QS0')
        self.assertEqual(meta, self.e / 'maintenance' / output.name)

    def test_replay_directory_rejected(self):
        out = self.e / 'results/maya-s-quality-QS0-20261030T150000Z'; out.mkdir()
        with self.assertRaises(ValueError): r.owned_paths(out, 'quality', 'QS0')

    def test_foreign_namespace_rejected(self):
        with self.assertRaises(ValueError): r.owned_paths(self.e / 'results/old-N0-20261030T150000Z', 'quality', 'QS0')

    def test_leaf_symlink_rejected(self):
        out = self.e / 'results/maya-s-quality-QS0-20261030T150000Z'; out.symlink_to(self.p, target_is_directory=True)
        with self.assertRaises(ValueError): r.owned_paths(out, 'quality', 'QS0')

    def test_first_quality_arm_unattempted(self): r.prerequisite('quality', 'QS0', {})

    def test_attempted_arm_not_replayed(self):
        with self.assertRaises(ValueError): r.prerequisite('quality', 'QS0', {'QS0': {'attempted': True}})

    def test_second_quality_requires_accepted_previous(self):
        with self.assertRaises(ValueError): r.prerequisite('quality', 'QS1', {'QS0': {'fully_reviewed': True, 'accepted': False}})

    def test_second_quality_reviewed_previous(self):
        r.prerequisite('quality', 'QS1', {'QS0': {'fully_reviewed': True, 'accepted': True}})

    def test_timing_requires_both_quality_screens(self):
        (self.p / 'quality-arms.json').write_text('{}')
        mode = next(m for m in config.MODE_ARMS if m != 'quality')
        with self.assertRaises(ValueError): r.prerequisite(mode, 'A1', {})

    def test_confirmation_requires_first_pair_permission(self):
        (self.p / 'quality-arms.json').write_text(json.dumps({a: {'fully_reviewed': True, 'accepted': True} for a in config.MODE_ARMS['quality']}))
        mode = next(m for m in config.MODE_ARMS if m != 'quality')
        (self.p / ('first-pair-' + mode + '.json')).write_text('{"confirmation_admitted":false}')
        with self.assertRaises(ValueError): r.prerequisite(mode, 'B2', {'B1': {'fully_reviewed': True, 'accepted': True}})

    def test_confirmation_requires_full_previous_review(self):
        with self.assertRaises(ValueError): r.prerequisite(next(m for m in config.MODE_ARMS if m != 'quality'), 'B2', {'B1': {'accepted': True}})

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
        self.root=Path(self.tmp.name);self.p=self.root/'source';self.p.mkdir()
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


class PackCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.e=Path(self.tmp.name);self.q=self.e/'q';self.pack=self.q/'pack-v1';self.acq=self.q/'acquisition-authorized-v2'
        self.assets=self.q/'assets';self.pack.mkdir(parents=True);self.acq.mkdir();self.assets.mkdir()
        self.vision=self.e/'vision-assets-1017';self.vision.mkdir()
        self.stats={};self.rows=[]
        for i in range(8):
            path=self.assets/str(i);path.write_bytes(b'asset')
            st=path.stat();self.stats[str(path)]=[st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns]
            self.rows.append({'path':str(i),'bytes':5,'sha256':r.sha(path)})
        vision_stats={}
        for n in ('vision.json','vision.bin'):
            path=self.vision/n;path.write_bytes(b'v');st=path.stat()
            vision_stats[str(path)]=[st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns]
        self.receipt=self.acq/'acquisition-attempt-FIRST.json'
        self.receipt.write_text(json.dumps({'status':'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN','returncode':0,'files':self.rows}))
        self.contract={'acquisition_receipt':str(self.receipt),'acquisition_receipt_sha256':r.sha(self.receipt),'asset_stats':self.stats,'vision_stats':vision_stats}
        self.result={'status':'PACK_METADATA_VERIFIED_NO_MODEL_ADMISSION','asset_stats':self.stats,'vision_stats':vision_stats,
                     'asset_sha256':{x['path']:x['sha256'] for x in self.rows},'output_sha256':{'pack.json':'d'*64}}
        self.cp=self.pack/'construct-contract-FIRST.json';self.rp=self.pack/'pack-result.json'
        self.cp.write_text(json.dumps(self.contract));self.rp.write_text(json.dumps(self.result))
        self.value={'pack_custody':{'constructor_contract':str(self.cp),'constructor_result':str(self.rp),'acquisition_receipt':str(self.receipt)},
                    'files':{str(x):r.sha(x) for x in (self.cp,self.rp,self.receipt)}}
        self.value['files'][str(self.pack/'pack-FIRST/pack.json')]='d'*64
        for field,value in (('E',self.e),('Q',self.q)):
            patcher=patch.object(r,field,value);patcher.start();self.addCleanup(patcher.stop)

    def test_acquired_full_hash_and_current_stat_custody(self):
        self.assertEqual(r.pack_custody(self.value)['asset_stats'],self.stats)

    def test_changed_asset_identity_blocks_without_rehash(self):
        path=self.assets/'0';path.unlink();path.write_bytes(b'asset')
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_changed_vision_identity_blocks(self):
        (self.vision/'vision.bin').write_bytes(b'changed')
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_missing_constructed_metadata_pin_blocks(self):
        self.value['files'].pop(str(self.pack/'pack-FIRST/pack.json'))
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_changed_constructor_contract_blocks(self):
        self.cp.write_text('{}')
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_payload_hardlink_alias_blocks(self):
        (self.assets/'alias').hardlink_to(self.assets/'0')
        with self.assertRaises(ValueError):r.pack_custody(self.value)


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


if __name__ == '__main__': unittest.main()
