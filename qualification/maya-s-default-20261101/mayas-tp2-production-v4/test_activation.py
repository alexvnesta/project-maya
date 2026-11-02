"""Actual metadata, adversarial settings and real temporary-file publication tests."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
from contextlib import nullcontext

import policy as p
import activate_mayas as a

H = Path(__file__).resolve().parent
Q = H.parent/'s2-reconstruction-v1/candidate-pack-v1'


def load(name):
    spec = importlib.util.spec_from_file_location(name,H/(name+'.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class Config(unittest.TestCase):
    def setUp(self): self.base = json.loads((H/'base-config.json').read_text())
    def test_actual_base_and_only_explicit_changes(self):
        self.assertEqual(a.sha(H/'base-config.json'),p.BASE_SHA)
        before = copy.deepcopy(self.base); c = p.target_config(self.base)
        self.assertEqual(before,self.base); p.config_contract(self.base,c)
        self.assertEqual(c['args'][c['args'].index('--tp')+1],'2')
        self.assertEqual(c['tokenizer'],str(p.PACK/'tokenizer'))
        self.assertEqual(c['model_name'],self.base['model_name'])
    def test_context_effort_output_related_policy_cannot_drift(self):
        c = p.target_config(self.base)
        for k,v in (('hosted_default_effort',50),('answer_room',True),('reasoning_budget_tokens',2048),('fit_max_tokens',True)):
            with self.subTest(k=k), self.assertRaises(ValueError):p.config_contract(self.base,dict(c,**{k:v}))
    def test_argument_and_native_factors_cannot_drift(self):
        c = p.target_config(self.base)
        for flag,value in (('--max-context','262144'),('--dspark','off'),('--cpu-threads','12'),('--ablate-scale','0'),('--tp','1')):
            changed = copy.deepcopy(c); changed['args'][changed['args'].index(flag)+1] = value
            with self.subTest(flag=flag),self.assertRaises(ValueError):p.config_contract(self.base,changed)
    def test_missing_required_TP2_copy_flag(self):
        c = p.target_config(self.base)
        for k in p.FLAGS:
            changed = copy.deepcopy(c); changed['env'].pop(k)
            with self.subTest(k=k),self.assertRaises(ValueError):p.config_contract(self.base,changed)
    def test_other_native_factor_and_old_cache_rejected(self):
        c = p.target_config(self.base)
        for k,v in (('DS4_SERVE_DUMP','/tmp'),('DS4_REQUIRE_ALL_RAM','0'),('DS4_STREAM','1'),('STRATA_DS4_SLOT_DIR',self.base['env']['STRATA_DS4_SLOT_DIR'])):
            changed = copy.deepcopy(c); changed['env'][k] = v
            with self.subTest(k=k),self.assertRaises(ValueError):p.config_contract(self.base,changed)
    def test_config_preflight_accepts_only_target(self):
        pre = load('hosting_preflight'); c = p.target_config(self.base); pre.validate_config(c)
        with self.assertRaises(RuntimeError):pre.validate_config(self.base)
        for k in p.FLAGS:
            changed = copy.deepcopy(c); changed['env'].pop(k)
            with self.subTest(k=k),self.assertRaises(RuntimeError):pre.validate_config(changed)
    def test_output_and_drafter_global_defaults_unchanged(self):
        c = p.target_config(self.base)
        self.assertEqual(c['env']['DS4_DSPARK_MAX'],'4')
        for k in ('reasoning_budget_tokens','repeat_stop_tokens','reasoning_loop_recovery','fit_max_tokens','hosted_default_effort','engine_ready_s'):
            self.assertEqual(c[k],self.base[k])
    def test_preflight_unavailable_unit_status_refused(self):
        pre=load('hosting_preflight')
        for n in (3,4):pre.inactive_status(n)
        for n in (0,1,2,5,False,None):
            with self.subTest(n=n),self.assertRaises(RuntimeError):pre.inactive_status(n)


class SwitchGuard(unittest.TestCase):
    def setUp(self):
        self.binding={'invocation':'1'*32,'main_pid':11,'native_pid':12,'native_start_ticks':13}
        self.state={'decode_optimization_current':{'selected_identity':{'start_binding':self.binding}}}
        self.health={'status':'ok','loaded':True,'images':True,'max_context':1048576,'busy':True,
                     'switcher':{'active_model':'deepseek','default_model':'deepseek','fault':None,'inflight':1,'waiting':2}}
    def test_user_authorized_busy_DeepSeek_staging_is_read_only_allowed(self):
        self.assertTrue(p.switch_guard_contract(self.state,self.binding,self.health,user_interrupt_authorized=True))
    def test_no_implicit_busy_override(self):
        with self.assertRaises(ValueError):p.switch_guard_contract(self.state,self.binding,self.health,user_interrupt_authorized=False)
    def test_foreign_private_build_or_pending_restoration_refused(self):
        for key in a.PHASES:
            with self.subTest(key=key),self.assertRaises(ValueError):p.switch_guard_contract(dict(self.state,**{key:True}),self.binding,self.health,user_interrupt_authorized=True)
    def test_other_selected_owner_refused(self):
        with self.assertRaises(ValueError):p.switch_guard_contract(self.state,dict(self.binding,native_pid=99),self.health,user_interrupt_authorized=True)
    def test_other_model_or_fault_refused(self):
        for key,value in (('active_model','qwen'),('default_model','qwen'),('fault','bad')):
            h=copy.deepcopy(self.health);h['switcher'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.switch_guard_contract(self.state,self.binding,h,user_interrupt_authorized=True)
    def test_capacity_or_unloaded_health_refused(self):
        for key,value in (('max_context',262144),('loaded',False),('images',False)):
            with self.subTest(key=key),self.assertRaises(ValueError):p.switch_guard_contract(self.state,self.binding,dict(self.health,**{key:value}),user_interrupt_authorized=True)


class Metadata(unittest.TestCase):
    def setUp(self):
        self.pins = json.loads((Q/'BASE_METADATA_PINS.json').read_text())
        self.blobs = {k:(Q/'base-metadata'/k).read_bytes() for k in self.pins}
    def test_all_actual_tensor_metadata_unmodified_except_paths(self):
        out = p.rebind_metadata(self.blobs,self.pins)
        for k in self.blobs:
            if k not in ('ds4.txt','tensors.txt'):self.assertEqual(out[k],self.blobs[k])
        self.assertIn(('model_dir '+p.NEW_ROOT+'\n').encode(),out['ds4.txt'])
        old = [l for l in self.blobs['tensors.txt'].splitlines() if not l.startswith(b'file ')]
        new = [l for l in out['tensors.txt'].splitlines() if not l.startswith(b'file ')]
        self.assertEqual(old,new); self.assertGreater(len(new),40000)
        self.assertNotIn(b'overlay.iq3s',out['tensors.txt']); self.assertNotIn(b'native.cpu',out['tensors.txt'])
    def test_one_modified_tensor_or_tokenizer_byte_rejected(self):
        for k in ('tensors.txt','tokenizer/chat_template.jinja','engram.bin'):
            blobs = dict(self.blobs); blobs[k] += b'x'
            with self.subTest(k=k),self.assertRaises(ValueError):p.rebind_metadata(blobs,self.pins)
    def test_foreign_root_even_with_matching_pin_rejected(self):
        blobs = dict(self.blobs); blobs['ds4.txt'] = blobs['ds4.txt'].replace(p.OLD_ROOT.encode(),b'/foreign')
        pins = dict(self.pins,**{'ds4.txt':p.sha(blobs['ds4.txt'])})
        with self.assertRaises(ValueError):p.rebind_metadata(blobs,pins)
    def test_foreign_file_table_even_with_matching_pin_rejected(self):
        blobs = dict(self.blobs); blobs['tensors.txt'] = blobs['tensors.txt'].replace(b'file 6 ../dspark/dspark.bin',b'file 6 /foreign')
        pins = dict(self.pins,**{'tensors.txt':p.sha(blobs['tensors.txt'])})
        with self.assertRaises(ValueError):p.rebind_metadata(blobs,pins)
    def test_missing_shared_metadata_refused(self):
        blobs = dict(self.blobs); blobs.pop('engram.bin')
        with self.assertRaises(ValueError):p.rebind_metadata(blobs,self.pins)


class Process(unittest.TestCase):
    def setUp(self):
        self.c = p.target_config(json.loads((H/'base-config.json').read_text()))
        self.argv = [self.c['exe'],'--serve',*self.c['args'],'--layer-split','auto','']
        self.group = '0::/user.slice/deepseek-hosted.service'
    def test_exact_native_and_allowed_non_native_environment(self):
        p.process_contract(self.c,self.argv,dict(self.c['env'],PATH='/bin'),self.group,True)
    def test_foreign_cgroup_executable_argv_or_env_refused(self):
        for args,env,group,same in ((self.argv,self.c['env'],'0::/foreign.service',True),(self.argv,self.c['env'],self.group,False),
                                   (self.argv[:-1],self.c['env'],self.group,True),(self.argv,dict(self.c['env'],DS4_DRAFT_VRAM='1'),self.group,True)):
            with self.assertRaises(ValueError):p.process_contract(self.c,args,env,group,same)
    def test_real_file_fingerprint_changes(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t).resolve()/'f';f.write_bytes(b'a');before=a.fingerprint(f);f.write_bytes(b'bb')
            self.assertNotEqual(before,a.fingerprint(f))
            alias=f.with_name('alias');alias.symlink_to(f)
            with self.assertRaises(ValueError):a.fingerprint(alias)
    def test_exact_physical_CPU_contract_and_mutations(self):
        review={'source_map':{'a':'x'},'input_map':{'b':'y'},'test_ids':['one']}
        r=dict(review,passed=True,returncode=0,controls=1,failures=0,errors=0,isolated=True,supervisor_pid=11,
               observed={'platform':'linux','cpu':[30,30],'nice':15,'as':[512*2**20]*2,'environment':dict(a.CPU_ENV),
                         'pid':12,'pgid':12,'ppid':11,'dont_write_bytecode':True})
        child={'returncode':0,'error':None,'cleanup':[],'pid':12,'elapsed_seconds':.5}
        a.cpu_contract(r,child,review,'linux')
        for key,value in (('environment',{}),('cpu',[31,31]),('as',None),('pid',13),('ppid',0),('nice',0)):
            wrong=copy.deepcopy(r);wrong['observed'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a.cpu_contract(wrong,child,review,'linux')
        for key,value in (('returncode',1),('cleanup',['survived']),('pid',13)):
            with self.subTest(key=key),self.assertRaises(ValueError):a.cpu_contract(r,dict(child,**{key:value}),review,'linux')
    def test_activation_helper_has_unique_module_name(self):
        self.assertEqual(a.__name__,'activate_mayas')
        self.assertIn('activate_mayas.py',a.SOURCES)
    def test_foreign_legacy_cached_module_is_rejected_not_replaced(self):
        from types import SimpleNamespace
        with patch.dict(a.sys.modules,{'activate':SimpleNamespace(__file__='/foreign/activate.py')}):
            with self.assertRaises(ValueError):a.legacy_import_guard()
            self.assertEqual(a.sys.modules['activate'].__file__,'/foreign/activate.py')


class Readiness(unittest.TestCase):
    def test_new_Q8_exact_numerical_check_not_old_counts(self):
        ready=load('hosting_ready')
        log='\n'.join("ds4: CUDA%d Q8 batch check: 8 jobs (fixture): 50976 int8 and 1593 scales the per-job launches' bit for bit, every guard intact (DS4_Q8_CHECK)"%i for i in (0,1))
        self.assertEqual(ready.q8_receipt(log)['devices'],[0,1])
        with self.assertRaises(RuntimeError):ready.q8_receipt(log.replace('50976','42784').replace('1593','1337'))
        with self.assertRaises(RuntimeError):ready.q8_receipt(log.splitlines()[0])
    def test_real_saved_TP2_startup_passes_current_parser(self):
        root=H.parent/'maya145-directstate-v1';file=root/'engine_profile.py'
        self.assertEqual(a.sha(file),'c43e07ed6a4019fb6252c64d40a0b3cd7a9bfe98e64c36e94436e159406ff983')
        spec=importlib.util.spec_from_file_location('saved_TP2_parser',file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        log=(H/'TP2_STARTUP_FIXTURE.txt').read_text();self.assertTrue(m.startup(log,'TP2')['passed'])
        with self.assertRaises(ValueError):m.startup(log.replace('(DS4_TP_CHECK)','(NOT_CHECKED)'),'TP2')


class Publication(unittest.TestCase):
    def fixture(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.d=self.root/'deployment';(self.d/'bin').mkdir(parents=True);(self.d/'state').mkdir();(self.d/'releases').mkdir()
        self.h=self.root/'candidate';self.h.mkdir();self.out=self.h/'activation-FIRST';self.out.mkdir()
        for name in ('config.json','hosting_preflight.py','hosting_ready.py','release.json','startup-ready.json','startup-preflight.json'):(self.d/name).write_text('old-'+name)
        (self.d/'bin/maya-ds4').write_bytes(b'old-native');self.native=self.h/'native';self.native.write_bytes(b'new-native')
        self.files={}
        for name in ('candidate-config.json','hosting_preflight.py','hosting_ready.py'):
            f=self.h/name;f.write_text('new-'+name);self.files[str(f)]=a.sha(f)
        (self.h/'candidate-release.json').write_text(json.dumps({'files':{'expected':'pin'}}))
        self.q={'base_release_sha256':a.sha(self.d/'release.json'),'files':self.files,'target_release_files':{'expected':'pin'}}
        self.patch=patch.multiple(p,D=self.d,CACHE=self.d/'state/cache',PROFILE=self.d/'state/profile',NATIVE=self.native,NATIVE_SHA=a.sha(self.native),BASE_SHA=a.sha(self.d/'config.json'));self.patch.start();self.addCleanup(self.patch.stop)
        patcher=patch.object(a,'HERE',self.h);patcher.start();self.addCleanup(patcher.stop)
    def test_real_staging_publication_and_exact_backup(self):
        self.fixture();value=a.install(self.q,self.out)
        self.assertEqual((self.d/'bin/maya-ds4').read_bytes(),b'new-native')
        self.assertEqual((Path(value['backup'])/'maya-ds4').read_bytes(),b'old-native')
        self.assertEqual(json.loads((self.d/'release.json').read_text())['files'],{'expected':'pin'})
    def test_source_drift_rejected_before_publication(self):
        self.fixture();(self.h/'hosting_ready.py').write_text('changed')
        with self.assertRaises(ValueError):a.install(self.q,self.out)
        self.assertEqual((self.d/'config.json').read_text(),'old-config.json')
    def test_wrong_native_copied_bytes_rejected_before_any_replacement(self):
        self.fixture();self.native.write_bytes(b'wrong-native')
        with self.assertRaises(ValueError):a.install(self.q,self.out)
        self.assertEqual((self.d/'bin/maya-ds4').read_bytes(),b'old-native')
        self.assertEqual((self.d/'config.json').read_text(),'old-config.json')
    def test_existing_cache_and_staging_residue_refused(self):
        self.fixture();p.CACHE.mkdir()
        with self.assertRaises(ValueError):a.install(self.q,self.out)
        self.assertEqual((self.d/'config.json').read_text(),'old-config.json')
    def test_atomic_receipt_preserves_residue(self):
        self.fixture();f=self.root/'receipt.json';a.emit(f,{'one':1});f.with_name(f.name+'.new').write_text('residue')
        with self.assertRaises(ValueError):a.emit(f,{'two':2})
        self.assertEqual(json.loads(f.read_text()),{'one':1})


class Custody(unittest.TestCase):
    def setUp(self):
        self.binding={'invocation':'1'*32,'main_pid':11,'native_pid':12,'native_start_ticks':13}
        self.state={'decode_optimization_current':{'selected_identity':{'start_binding':self.binding}},
                    'production_verification_pending':False,'current_native_pid':12,'production_temporarily_stopped':False}
        self.record={'pid':17,'status':'DRAINING_EXACT_SELECTED_OWNER','active':True}
    def test_exact_initial_and_followup_reservation_preserves_foreign_fields(self):
        state=dict(self.state,keep={'other':'owner'}); claimed=a.state_update(state,None,self.record,self.binding)
        self.assertEqual(claimed['keep'],state['keep'])
        value=dict(self.record,status='PUBLISHING_AFTER_BOUND_OLD_EXIT0')
        changed=a.state_update(claimed,self.record,value,self.binding)
        self.assertIsNone(changed['current_native_pid']);self.assertTrue(changed['production_temporarily_stopped'])
    def test_foreign_phase_or_activation_same_PID_is_not_ours(self):
        state=a.state_update(self.state,None,self.record,self.binding)
        for change in ({'production_restore_in_progress':{'pid':17,'foreign':True}},
                       {'mayas_tp2_activation':dict(self.record,status='FOREIGN')},
                       {'active_private_phase':'other'}, {'production_verification_pending':'other'},
                       {'maintenance_controller':'other'}, {'production_temporarily_stopped':True}):
            with self.subTest(change=change),self.assertRaises(ValueError):a.state_update(dict(state,**change),self.record,self.record,self.binding)
    def test_stopped_failure_clears_previously_verified_dead_owner(self):
        identity={'native_pid':88,'start_binding':dict(self.binding,native_pid=88)}
        previous=dict(self.record,status='MAYAS_TP2_DEFAULT_ACTIVE_VERIFIED',active=False,verified={'passed':True,'selected_identity':identity})
        state=a.state_update(self.state,None,previous,self.binding)
        failure=dict(self.record,status='HOLD_ACTIVATION_FAILURE_NO_RETRY',active=False,production_stopped=True)
        out=a.state_update(state,previous,failure,self.binding)
        self.assertIsNone(out['current_native_pid']);self.assertTrue(out['production_temporarily_stopped']);self.assertFalse(out['production_verification_pending'])
        self.assertIn('NO_CURRENT_OWNER',out['decode_optimization_current']['status'])
    def test_live_pre_stop_failure_keeps_baseline_identity(self):
        claimed=a.state_update(self.state,None,self.record,self.binding)
        failure=dict(self.record,status='HOLD_ACTIVATION_FAILURE_NO_RETRY',active=False,production_stopped=False)
        out=a.state_update(claimed,self.record,failure,self.binding)
        self.assertEqual(out['current_native_pid'],12);self.assertFalse(out['production_temporarily_stopped'])
    def test_initial_foreign_pending_or_wrong_binding_refused(self):
        for change in ({'production_verification_pending':'foreign'},{'mayas_tp2_activation':{'foreign':True}},
                       {'decode_optimization_current':{'selected_identity':{'start_binding':{}}}}):
            with self.subTest(change=change),self.assertRaises(ValueError):a.state_update(dict(self.state,**change),None,self.record,self.binding)


class Coordinator(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.e=self.root/'e';self.e.mkdir();self.h=self.root/'mode';self.h.mkdir();self.d=self.root/'d';self.d.mkdir()
        self.binding={'invocation':'1'*32,'main_pid':11,'native_pid':12,'native_start_ticks':13}
        self.state={'decode_optimization_current':{'selected_identity':{'start_binding':self.binding}},'current_native_pid':12,
                    'production_verification_pending':False,'production_temporarily_stopped':False}
        (self.e/'STATE.json').write_text(json.dumps(self.state))
        (self.d/'release.json').write_text(json.dumps({'id':a.RELEASE,'production_active':False}))
        self.q={'selected_binding':self.binding}
        (self.h/'ADMISSION_FIRST.json').write_text(json.dumps({'selected_binding':self.binding,'qualification_sha256':'q','single_use':True,'user_selected_MayaS_TP2':True}))
        self.host=MagicMock();self.host.publication_lock.side_effect=lambda:nullcontext()
        self.host.clean_stop.side_effect=lambda pid:setattr(self.host,'old_close_verified',True)
        self.new_binding=dict(self.binding,native_pid=88,main_pid=77,invocation='2'*32)
        def start():self.host.start_binding=self.new_binding;self.host.restored_pid=88
        self.host.restore_ds.side_effect=start
        self.identity={'native_pid':88,'start_binding':self.new_binding}
        self.host.verify_target.return_value={'passed':True,'selected_identity':self.identity}
        self.base=MagicMock();self.base.current_binding.return_value=self.binding
        self.cas=MagicMock();self.cas.cas_state.side_effect=self.cas_write
    def cas_write(self,path,before,after):
        if path.read_bytes()!=before:raise ValueError('changed')
        a.emit(path,after)
    def invoke(self):
        with patch.object(a,'HERE',self.h),patch.multiple(p,E=self.e,D=self.d),patch.object(a,'qualified',return_value=self.q),\
             patch.object(a,'support',return_value=(self.base,MagicMock(),MagicMock(),MagicMock())),patch.object(a,'cas_library',return_value=self.cas),\
             patch.object(a,'production_host',return_value=lambda:self.host),patch.object(a,'install',return_value={'backup':'saved'}),\
             patch.object(a.shutil,'disk_usage',return_value=MagicMock(free=132*2**30)):
            return a.run('q',a.sha(self.h/'ADMISSION_FIRST.json'))
    def test_single_start_then_actual_verified_identity(self):
        out=self.invoke();self.assertEqual(out['status'],'MAYAS_TP2_DEFAULT_ACTIVE_VERIFIED')
        self.host.restore_ds.assert_called_once();self.host.clean_stop.assert_called_once_with(12)
        state=a.read(self.e/'STATE.json');self.assertEqual(state['current_native_pid'],88);self.assertFalse(state['production_restore_in_progress'])
    def test_old_native_close_fault_never_publishes_or_starts(self):
        self.host.clean_stop.side_effect=ValueError('close fault')
        with self.assertRaisesRegex(ValueError,'close fault'):self.invoke()
        self.host.restore_ds.assert_not_called();state=a.read(self.e/'STATE.json')
        self.assertIsNone(state['current_native_pid']);self.assertTrue(state['production_temporarily_stopped'])
        self.assertTrue(state['production_restore_in_progress']['active'])
    def test_uncaptured_attempted_start_remains_active_HOLD(self):
        self.host.restore_ds.side_effect=ValueError('start fault')
        with self.assertRaisesRegex(ValueError,'start fault'):self.invoke()
        state=a.read(self.e/'STATE.json');self.assertTrue(state['production_restore_in_progress']['active']);self.assertIsNone(state['current_native_pid'])
    def test_failed_final_release_write_cleans_owned_native_and_clears_PID(self):
        emit=a.emit
        def write(path,row):
            if path==self.d/'release.json' and row.get('production_active'):raise OSError('publication failed')
            return emit(path,row)
        with patch.object(a,'emit',side_effect=write),self.assertRaisesRegex(OSError,'publication failed'):self.invoke()
        self.host.cleanup_owned_target.assert_called_once_with(expected_pid=88)
        state=a.read(self.e/'STATE.json');self.assertIsNone(state['current_native_pid']);self.assertTrue(state['production_temporarily_stopped'])
        self.assertFalse(a.read(self.d/'release.json')['production_active'])
    def test_partial_CAS_claim_readback_failure_released_without_service_change(self):
        calls=[]
        def cas(path,before,after):
            self.cas_write(path,before,after);calls.append(1)
            if len(calls)==1:raise ValueError('readback')
        self.cas.cas_state.side_effect=cas
        with self.assertRaisesRegex(ValueError,'readback'):self.invoke()
        self.host.stop_router.assert_not_called();self.host.stop_ds.assert_not_called();self.assertFalse(a.read(self.e/'STATE.json')['production_restore_in_progress'])
    def test_foreign_CAS_replacement_preserved_without_service_signal(self):
        foreign=dict(self.state,production_restore_in_progress={'foreign':True},mayas_tp2_activation={'foreign':True})
        def cas(path,before,after):a.emit(path,foreign);raise ValueError('foreign CAS')
        self.cas.cas_state.side_effect=cas
        with self.assertRaisesRegex(ValueError,'foreign CAS'):self.invoke()
        self.assertEqual(a.read(self.e/'STATE.json'),foreign);self.host.stop_router.assert_not_called();self.host.cleanup_owned_target.assert_not_called()
    def test_foreign_phase_replacement_blocks_cleanup_before_any_signal(self):
        def verify(**kw):
            state=a.read(self.e/'STATE.json');state['production_restore_in_progress']={'foreign':True}
            a.emit(self.e/'STATE.json',state);raise ValueError('phase replaced')
        self.host.verify_target.side_effect=verify
        with self.assertRaises(ValueError):self.invoke()
        self.host.cleanup_owned_target.assert_not_called()
        self.assertEqual(a.read(self.e/'STATE.json')['production_restore_in_progress'],{'foreign':True})
