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
    """Small real files exercise P3 custody; only published literal pins are synthetic."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.e=Path(self.tmp.name).resolve();self.q=self.e/'q';self.pack=self.q/'pack-v1/pack-FIRST'
        self.p3=self.q/'pack-v3';self.assets=self.q/'assets';self.vision=self.e/'vision-assets-1017'
        for path in (self.pack,self.p3,self.assets,self.vision):path.mkdir(parents=True)
        self.value={'pack_custody':{},'files':{}};self.pins={};self.paths={}
        for key,(relative,_) in r.PACK_CUSTODY_FILES.items():
            path=self.q/relative;path.parent.mkdir(parents=True,exist_ok=True)
            self.paths[key]=path;self.value['pack_custody'][key]=str(path)
            self.pins[key]=(relative,'pending')
        self.rows=[];self.stats={}
        for name in [*('Maya-S/shard'+str(i)+'.gguf' for i in range(6)),'dspark.json','dspark.bin']:
            path=self.assets/name;path.parent.mkdir(exist_ok=True);path.write_bytes(b'asset')
            self.stats[str(path)]=self.stat(path)
            self.rows.append({'path':name,'bytes':5,'sha256':r.sha(path),'status':'DOWNLOADED_VERIFIED'})
        self.vision_stats={}
        for name in ('vision.json','vision.bin'):
            path=self.vision/name;path.write_bytes(b'v');self.vision_stats[str(path)]=self.stat(path)
        self.acquired={'status':'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN','returncode':0,
                       'model_or_service_actions':0,'files':self.rows}
        self.record('acquisition_receipt',self.acquired)
        self.contract={'acquisition_receipt':str(self.paths['acquisition_receipt']),
             'acquisition_receipt_sha256':self.pins['acquisition_receipt'][1],
             'asset_stats':self.stats,'vision_stats':self.vision_stats,'output':str(self.pack),
             'assets_root':str(self.assets),'vision_dir':str(self.vision),'profile':{'context':1048576}}
        self.record('constructor_contract',self.contract)
        outputs={}
        for name in sorted(r.PACK_OUTPUTS):
            path=self.pack/name;path.parent.mkdir(exist_ok=True);path.write_bytes(b'metadata')
            outputs[name]=r.sha(path);self.value['files'][str(path)]=r.sha(path)
        self.result={'status':'PACK_METADATA_VERIFIED_NO_MODEL_ADMISSION','asset_stats':self.stats,
             'vision_stats':self.vision_stats,'asset_sha256':{x['path']:x['sha256'] for x in self.rows},
             'output_sha256':outputs,'capacity_inputs':{'limits_preserved':self.contract['profile']}}
        self.record('constructor_result',self.result)
        self.env={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
                  'MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}
        self.cq={'root_manual_review':True,'astra_manual_review':True,
             'pack_guard_both_physical_hosts_passed':True,'construct_controller_both_physical_hosts_passed':True,
             'actual_contract':str(self.paths['constructor_contract']),
             'actual_contract_sha256':self.pins['constructor_contract'][1],
             'pack_output_is_original_never_created_fresh_target':str(self.pack),'files':{},'CPU_groups':[]}
        inp=self.e/'input.json';inp.write_text('{}');self.add_cq_file(inp)
        for name,count,prefix,sources in (
            ('pack_guard',94,'CPU-FIRST',('pack_guard.py','test_pack_guard.py','run_cpu.py')),
            ('construct_controller',31,'CONSTRUCT-FIRST',('pack_guard.py','construct_pack.py','test_construct_pack.py','construct_cpu.py'))):
            sm={}
            for source in sources:
                path=self.p3/source;path.write_text('# synthetic pinned source\n')
                sm[source]=r.sha(path);self.add_cq_file(path)
            group={'name':name,'source_sha256':sm,'input_sha256':{'input.json':r.sha(inp)},
                   'test_ids':[name+'.test_'+str(i).zfill(3) for i in range(count)],'proofs':{}}
            for host in ('darwin','linux'):
                folder=self.p3/(prefix+'-'+host);folder.mkdir()
                receipt={'passed':True,'controls':count,'test_ids':group['test_ids'],
                     'source_sha256':sm,'input_sha256':group['input_sha256'],'CPU_seconds':[30,30],
                     'Linux_AS_bytes':[512*2**20]*2 if host=='linux' else None,'nice':15,'environment':self.env}
                child={'returncode':0,'error':None,'cleanup_errors':[],'CPU_limit_seconds':30,
                     'wall_limit_seconds':90,'nice_increment':15,'environment':self.env}
                paths={}
                for key,leaf,data in (('receipt','receipt.json',receipt),('child','child.json',child),('log','child.log',None)):
                    path=folder/leaf;path.write_text(json.dumps(data) if data is not None else 'Ran controls OK\n')
                    paths[key]=str(path);self.add_cq_file(path)
                group['proofs'][host]=paths
            self.cq['CPU_groups'].append(group)
        for key in ('constructor_contract','acquisition_receipt'):self.add_cq_file(self.paths[key])
        self.record('constructor_qualification',self.cq)
        self.child={'command':[str(r.R/'venv/bin/python3.14'),'-B',str(self.p3/'construct_pack.py'),'--child',
             '--qualification',str(self.paths['constructor_qualification']),'--qualification-sha256',
             self.pins['constructor_qualification'][1],'--contract',str(self.paths['constructor_contract']),
             '--output',str(self.p3/'construct-CPU-FIRST')], 'returncode':0,'error':None,'cleanup_errors':[],
             'pid':123,'seconds':2.2,'CPU_limit_seconds':30,'wall_limit_seconds':90,'nice_increment':15,
             'Linux_AS_bytes':512*2**20,'environment':self.env,'GPU_or_service_actions':0}
        self.record('constructor_child',self.child);self.record('constructor_log',None)
        self.review={'passed':True,'model_or_GPU_admitted':False,'qualification_sha256':self.pins['constructor_qualification'][1]}
        self.record('constructor_result_review',self.review)
        for field,value in (('E',self.e),('Q',self.q),('PACK_CUSTODY_FILES',self.pins)):
            patcher=patch.object(r,field,value);patcher.start();self.addCleanup(patcher.stop)

    @staticmethod
    def stat(path):
        s=path.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

    def record(self,key,value):
        path=self.paths[key];path.write_text(json.dumps(value) if value is not None else '')
        self.pins[key]=(str(path.relative_to(self.q)),r.sha(path));self.value['files'][str(path)]=r.sha(path)

    def add_cq_file(self,path):
        self.cq['files'][str(path)]=r.sha(path);self.value['files'][str(path)]=r.sha(path)

    def refresh_cq(self):
        self.record('constructor_qualification',self.cq)
        self.child['command'][7]=self.pins['constructor_qualification'][1];self.record('constructor_child',self.child)
        self.review['qualification_sha256']=self.pins['constructor_qualification'][1];self.record('constructor_result_review',self.review)

    def test_completed_p3_all125_controls_and_original_target(self):
        self.assertEqual(r.pack_custody(self.value)['asset_stats'],self.stats)
        self.assertEqual(sum(len(g['test_ids']) for g in self.cq['CPU_groups']),125)

    def test_old_failed_p1_result_not_relabelled_success(self):
        old=self.q/'pack-v1/pack-result.json';old.write_text(json.dumps(self.result))
        self.value['pack_custody']['constructor_result']=str(old);self.value['files'][str(old)]=r.sha(old)
        with self.assertRaisesRegex(ValueError,'P3 evidence path'):r.pack_custody(self.value)

    def test_missing_qualification_or_result_review_refused(self):
        for key in ('constructor_qualification','constructor_result_review'):
            value=copy.deepcopy(self.value);value['pack_custody'].pop(key)
            with self.subTest(key=key),self.assertRaises(ValueError):r.pack_custody(value)

    def test_constructor_original_closure_missing_from_model_q_refused(self):
        for path in (self.p3/'pack_guard.py',self.e/'input.json',Path(self.cq['CPU_groups'][0]['proofs']['linux']['log'])):
            value=copy.deepcopy(self.value);value['files'].pop(str(path))
            with self.subTest(path=path),self.assertRaises(ValueError):r.pack_custody(value)

    def test_unapproved_cpu_source_base_refused(self):
        with self.assertRaisesRegex(ValueError,'source base'):
            r.cpu_membership(self.cq['CPU_groups'][0],self.value['files'],source_base=self.q/'pack-v1')

    def test_missing_physical_constructor_proof_refused(self):
        self.cq['CPU_groups'][1]['proofs'].pop('linux');self.refresh_cq()
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_missing_constructor_cpu_group_refused(self):
        self.cq['CPU_groups'].pop();self.refresh_cq()
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_failed_constructor_cpu_child_refused(self):
        path=Path(self.cq['CPU_groups'][1]['proofs']['linux']['child'])
        child=json.loads(path.read_text());child['returncode']=1;path.write_text(json.dumps(child))
        self.add_cq_file(path);self.refresh_cq()
        with self.assertRaisesRegex(ValueError,'CPU supervision'):r.pack_custody(self.value)

    def test_wrong_cpu_source_map_refused(self):
        path=Path(self.cq['CPU_groups'][0]['proofs']['darwin']['receipt'])
        receipt=json.loads(path.read_text());receipt['source_sha256']['pack_guard.py']='0'*64
        path.write_text(json.dumps(receipt));self.add_cq_file(path);self.refresh_cq()
        with self.assertRaisesRegex(ValueError,'Exact new CPU proof'):r.pack_custody(self.value)

    def test_wrong_cpu_ordered_ids_refused(self):
        path=Path(self.cq['CPU_groups'][0]['proofs']['linux']['receipt'])
        receipt=json.loads(path.read_text());receipt['test_ids'].reverse()
        path.write_text(json.dumps(receipt));self.add_cq_file(path);self.refresh_cq()
        with self.assertRaisesRegex(ValueError,'Exact new CPU proof'):r.pack_custody(self.value)

    def test_p3_raw_log_alias_refused_before_read(self):
        path=Path(self.cq['CPU_groups'][0]['proofs']['linux']['log']);other=self.e/'other-log'
        path.rename(other);path.symlink_to(other)
        with self.assertRaisesRegex(ValueError,'alias'):r.pack_custody(self.value)

    def test_changed_constructor_contract_blocks(self):
        self.paths['constructor_contract'].write_text('{}')
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_pinned_wrong_output_target_refused(self):
        self.contract['output']=str(self.q/'pack-v3/pack-FIRST');self.record('constructor_contract',self.contract)
        self.cq['actual_contract_sha256']=self.pins['constructor_contract'][1]
        self.add_cq_file(self.paths['constructor_contract']);self.refresh_cq()
        with self.assertRaisesRegex(ValueError,'acquisition/pack construction'):r.pack_custody(self.value)

    def test_failed_or_wrong_actual_constructor_child_refused(self):
        original=copy.deepcopy(self.child)
        for key,value in (('returncode',1),('returncode',False),('cleanup_errors',['surviving child']),
                          ('Linux_AS_bytes',0),('GPU_or_service_actions',1),('seconds',91)):
            self.child=copy.deepcopy(original);self.child[key]=value;self.record('constructor_child',self.child)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Actual P3 constructor child'):r.pack_custody(self.value)

    def test_wrong_actual_command_or_contract_refused(self):
        self.child['command'][-1]=str(self.q/'pack-v1/construct-CPU-FIRST');self.record('constructor_child',self.child)
        with self.assertRaisesRegex(ValueError,'Actual P3 constructor child'):r.pack_custody(self.value)

    def test_changed_asset_identity_blocks_without_rehash(self):
        path=self.assets/self.rows[0]['path'];path.write_bytes(b'changed')
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_changed_vision_identity_blocks(self):
        (self.vision/'vision.bin').write_bytes(b'changed')
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_missing_constructed_metadata_pin_blocks(self):
        self.value['files'].pop(str(self.pack/'ds4.txt'))
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_changed_actual_output_bytes_blocks(self):
        (self.pack/'ds4.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError,'metadata omitted/changed'):r.pack_custody(self.value)

    def test_exact_eight_outputs_no_omission_or_extra(self):
        original=copy.deepcopy(self.result)
        for extra in (False,True):
            self.result=copy.deepcopy(original)
            if extra:self.result['output_sha256']['extra.txt']='0'*64
            else:self.result['output_sha256'].pop('engram.bin')
            self.record('constructor_result',self.result)
            with self.subTest(extra=extra),self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_duplicate_asset_row_refused(self):
        self.acquired['files'][-1]=self.acquired['files'][0];self.record('acquisition_receipt',self.acquired)
        self.contract['acquisition_receipt_sha256']=self.pins['acquisition_receipt'][1];self.record('constructor_contract',self.contract)
        self.cq['actual_contract_sha256']=self.pins['constructor_contract'][1]
        for key in ('acquisition_receipt','constructor_contract'):self.add_cq_file(self.paths[key])
        self.refresh_cq()
        with self.assertRaisesRegex(ValueError,'eight asset identities'):r.pack_custody(self.value)

    def test_payload_hardlink_alias_blocks(self):
        (self.assets/'alias').hardlink_to(self.assets/self.rows[0]['path'])
        with self.assertRaises(ValueError):r.pack_custody(self.value)

    def test_output_ancestor_alias_blocks(self):
        original=self.pack/'tokenizer';other=self.q/'borrowed-tokenizer';original.rename(other)
        original.symlink_to(other,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'alias'):r.pack_custody(self.value)


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
