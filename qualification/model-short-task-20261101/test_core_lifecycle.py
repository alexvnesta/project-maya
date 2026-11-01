"""New-mode exact CPU lifecycle/resource/source boundaries, synthetic only."""
import copy,json,tempfile,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import current_compat as c
import current_runtime as r
import current_config as config
BASE=r.P/'profile-base-config.json'

class Runtime(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.e=Path(self.temp.name).resolve()
        self.p=self.e/'mode';self.p.mkdir();(self.e/'results').mkdir();(self.e/'maintenance').mkdir()
        for x in (patch.object(r,'E',self.e),patch.object(r,'P',self.p)):
            x.start();self.addCleanup(x.stop)
    def test_all_active_phases_block(self):
        self.assertTrue(r.phase_free({}))
        for key in r.PHASE_KEYS:self.assertFalse(r.phase_free({key:True}))
    def test_exact_new_namespace(self):
        out=self.e/'results/maya145-modeltask-P-HGU-1-20261031T170000Z';self.assertEqual(r.owned_paths(out,'task','P-HGU-1')[1].name,out.name)
        for bad,arm in [(self.e/'results/maya-s-compatibility-CS1-20261030T180000Z','P-HGU-1'),(out,'P-UNSLOTH-1')]:
            with self.assertRaises(ValueError):r.owned_paths(bad,'task',arm)
    def test_existing_directory_or_alias_refused(self):
        out=self.e/'results/maya145-modeltask-P-HGU-1-20261031T170000Z';out.mkdir()
        with self.assertRaises(ValueError):r.owned_paths(out,'task','P-HGU-1')
        out.rmdir();out.symlink_to(self.p,target_is_directory=True)
        with self.assertRaises(ValueError):r.owned_paths(out,'task','P-HGU-1')
    def test_attempt_registry_one_shot_no_automatic_timing(self):
        r.prerequisite('task','P-HGU-1',{})
        for registry in ({'P-HGU-1':{'fully_reviewed':True}},{'P-UNSLOTH-1':{'fully_reviewed':False}},{'P-UNSLOTH-1':{'fully_reviewed':True,'accepted':False}},{'CS1':{'fully_reviewed':True}}):
            with self.assertRaises(ValueError):r.prerequisite('task','P-HGU-1',registry)
        with self.assertRaises(ValueError):r.prerequisite('prose','B1',{})
    def test_interrupted_receipt_kept(self):
        path=self.p/'r.json';path.with_name('r.json.tmp').write_text('prior')
        with self.assertRaises(ValueError):r.emit(path,{'x':1})
        self.assertEqual(path.with_name('r.json.tmp').read_text(),'prior')
    def test_resource_refusal_separate_from_native_fault(self):
        old=types.SimpleNamespace(coordinate=Mock(side_effect=r.ResourceAdmissionDeferred('RAM')));save=Mock()
        with self.assertRaises(r.ResourceAdmissionDeferred):r.coordinate(old,object(),'unused',{},save,preflight_only=False)
        save.assert_not_called()
    def test_native_fault_HOLD_preserved(self):
        (self.e/'STATE.json').write_text('{}');h=types.SimpleNamespace(audit_dir=self.p,controller_pid=99,restored_pid=None,start_binding=None)
        old=types.SimpleNamespace(coordinate=Mock(side_effect=RuntimeError('native rc1')));save=Mock()
        with self.assertRaises(RuntimeError):r.coordinate(old,h,'unused',{},save,preflight_only=False)
        self.assertEqual(save.call_args.args[0]['status'],'STOPPED_FOR_OFFLINE_DIAGNOSIS')
    def test_foreign_restored_owner_never_cleaned(self):
        (self.e/'STATE.json').write_text(json.dumps({'maintenance_controller':'foreign','decode_optimization_current':{'controller_pid':22}}))
        h=types.SimpleNamespace(audit_dir=self.p,controller_pid=99,restored_pid=100,start_binding={},cleanup_owned_target=Mock())
        r.hold_owned(h,{},Mock(),RuntimeError('primary'));h.cleanup_owned_target.assert_not_called()
    def test_owned_cleanup_fault_remains_with_primary(self):
        (self.e/'STATE.json').write_text(json.dumps({'maintenance_controller':str(self.p/'state.json'),'decode_optimization_current':{'controller_pid':99}}))
        h=types.SimpleNamespace(audit_dir=self.p,controller_pid=99,restored_pid=100,start_binding={},cleanup_owned_target=Mock(side_effect=RuntimeError('cleanup')))
        save=Mock();r.hold_owned(h,{},save,RuntimeError('primary'))
        self.assertIn('primary',save.call_args.args[0]['error']);self.assertIn('cleanup',save.call_args.args[0]['cleanup_error'])

class CPU(unittest.TestCase):
    def pair(self,platform='linux'):
        group={'source_sha256':{'new.py':'a'},'input_sha256':{'input':'b'},'test_ids':['one']}
        obs={'pid':3,'pgid':3,'platform':platform,'cpu':[30,30],'as':[512*2**20]*2 if platform=='linux' else None,
            'nice':15,'dont_write_bytecode':True,'environment':{'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1',
                'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}}
        return group,{'passed':True,'controls':1,'source_sha256':group['source_sha256'],'input_sha256':group['input_sha256'],'test_ids':['one'],'observed':obs}, {'pid':3,'returncode':0,'error':None,'cleanup':[],'elapsed_seconds':.1}
    def test_exact_both_platform_observed_contract(self):
        for platform in ('linux','darwin'):r.cpu_contract(*self.pair(platform),platform)
    def test_changed_ids_source_and_input_refused(self):
        for key,value in [('test_ids',['other']),('source_sha256',{}),('input_sha256',{}),('passed',False)]:
            g,p,c=self.pair();p[key]=value
            with self.assertRaises(ValueError):r.cpu_contract(g,p,c,'linux')
    def test_failed_unbounded_or_unclean_child_refused(self):
        for key,value in [('returncode',1),('returncode',False),('error','fault'),('cleanup',['fault']),('elapsed_seconds',91)]:
            g,p,c=self.pair();c[key]=value
            with self.assertRaises(ValueError):r.cpu_contract(g,p,c,'linux')
    def test_actual_limits_env_or_process_group_drift_refused(self):
        for key,value in [('cpu',[60,60]),('as',None),('pgid',2),('nice',0),('environment',{}),('platform','darwin')]:
            g,p,c=self.pair();p['observed'][key]=value
            with self.assertRaises(ValueError):r.cpu_contract(g,p,c,'linux')

class Window(unittest.TestCase):
    def test_exact_entry_window_and_terminal_rejection(self):
        out=r.E/'results/maya145-modeltask-P-HGU-1-20261031T170000Z';proof=r.E/'maintenance'/out.name/'proof.json'
        argv=[str(c.R/'venv/bin/python3.14'),'-B',str(c.P/'current_compat.py'),'--phase','--mode','task','--arm','P-HGU-1','--output',str(out),'--proof',str(proof)]
        value={'command':argv,'continued_from':'prior','test_returncode':None,'maintenance_held':False,'restored':False}
        old=types.SimpleNamespace(owned_window=Mock(return_value=(c.R/'windows/new.json',value)))
        c.window_contract(old,out,'task','P-HGU-1',proof)
        for delta in [{'command':argv[:2]+['old.py']+argv[3:]},{'test_returncode':0},{'restored':True}]:
            old.owned_window.return_value=(c.R/'windows/new.json',{**value,**delta})
            with self.assertRaises(ValueError):c.window_contract(old,out,'task','P-HGU-1',proof)

class Host(unittest.TestCase):
    def prior(self):
        error=type('ResourceDeferred',(RuntimeError,),{})
        class Parent:
            def free(self):raise error('RAM')
            def launch_owned(self,prior,argv,seconds):return (prior,argv,seconds)
        return types.SimpleNamespace(make_host=lambda *a:Parent,ResourceAdmissionDeferred=error)
    def test_resource_refusal_preserves_distinct_class(self):
        with patch.object(r,'reusable',return_value=self.prior()):
            host=r.make_host(None,None,None,None,None)()
            with self.assertRaises(r.ResourceAdmissionDeferred):host.free()
    def test_new_qualification_before_single1200_window(self):
        with patch.object(r,'reusable',return_value=self.prior()),patch.object(r,'qualified',return_value={}) as qualify:
            host=r.make_host(None,None,None,None,None)();host.mode='task';host.arm='P-HGU-1'
            host.audit_dir=Path('/owned/meta');host.qualification_sha256='a'*64
            host.reserve_attempt=Mock();host.phase_argv=Mock(return_value=['new-phase'])
            self.assertEqual(host.launch('prior','output',host.audit_dir/'proof.json'),('prior',['new-phase'],1200))
            qualify.assert_called_once_with('task','a'*64);host.reserve_attempt.assert_called_once()
            self.assertTrue(host.private_attempted);self.assertEqual(host.private_output,'output')
    def test_foreign_proof_never_reserves(self):
        with patch.object(r,'reusable',return_value=self.prior()),patch.object(r,'qualified',return_value={}):
            host=r.make_host(None,None,None,None,None)();host.mode='task';host.arm='P-HGU-1'
            host.audit_dir=Path('/owned/meta');host.qualification_sha256='a'*64;host.reserve_attempt=Mock()
            with self.assertRaises(ValueError):host.launch('prior','output','/foreign/proof.json')
            host.reserve_attempt.assert_not_called()

class MemoryRelease(unittest.TestCase):
    def rig(self,values,*,step=1):
        now=[0.];values=iter(values);samples=[];guard=Mock()
        def read():return next(values)
        def pause(seconds):now[0]+=seconds*step
        return read,guard,lambda:now[0],pause,samples
    def test_immediate_floor_no_pause(self):
        read,guard,clock,pause,samples=self.rig([r.MEMORY_MAX+r.HOST_MARGIN])
        self.assertEqual(r.await_headroom(read,guard,clock=clock,pause=Mock(side_effect=AssertionError('no wait')),samples=samples),88*2**30)
        self.assertEqual(len(samples),1)
    def test_actual_release_observed_before_admission(self):
        read,guard,clock,pause,samples=self.rig([73*2**30,80*2**30,90*2**30])
        self.assertEqual(r.await_headroom(read,guard,clock=clock,pause=pause,samples=samples),90*2**30)
        self.assertEqual([x['elapsed_seconds'] for x in samples],[0.,1.,2.]);self.assertEqual(guard.call_count,3)
    def test_fixed_floor_not_reduced_for_fitting(self):
        read,guard,clock,pause,samples=self.rig([87*2**30]*61)
        with self.assertRaises(r.ResourceAdmissionDeferred):r.await_headroom(read,guard,clock=clock,pause=pause,samples=samples)
        self.assertEqual(samples[-1]['elapsed_seconds'],60.)
    def test_foreign_custody_refuses_before_read(self):
        read=Mock();samples=[]
        with self.assertRaises(ValueError):r.await_headroom(read,Mock(side_effect=ValueError('foreign')),clock=lambda:0,pause=Mock(),samples=samples)
        read.assert_not_called();self.assertEqual(samples,[])
    def test_late_release_never_admitted(self):
        read,guard,clock,pause,samples=self.rig([73*2**30,100*2**30],step=61)
        with self.assertRaises(r.ResourceAdmissionDeferred):r.await_headroom(read,guard,clock=clock,pause=pause,samples=samples)
    def test_untyped_memory_refused(self):
        for value in (True,88.*2**30,-1):
            with self.assertRaises(ValueError):r.await_headroom(lambda:value,lambda:None,clock=lambda:0,pause=Mock(),samples=[])
    def test_new_qualification_file_preserves_original(self):
        self.assertEqual(r.qualification_path().name,'task-qualification.json')

class MemoryHost(unittest.TestCase):
    def setup_host(self,root):
        error=type('PriorResourceDeferred',(RuntimeError,),{});calls=[]
        class Parent:
            def free(self):
                calls.append('free')
                row={'available_bytes':70*2**30,'required_bytes':88*2**30,'passed':False}
                if len(calls)==1:
                    r.emit(self.audit_dir/'post-stop-memory.json',row);raise error('RAM')
                r.emit(self.audit_dir/'post-stop-memory.json',{**row,'available_bytes':95*2**30,'passed':True})
                return 'actual-sole-GPU-lock-floor-rechecked'
        prior=types.SimpleNamespace(make_host=lambda *a:Parent,ResourceAdmissionDeferred=error)
        fake=patch.object(r,'reusable',return_value=prior);fake.start();self.addCleanup(fake.stop)
        h=r.make_host(None,None,None,None,None)();h.audit_dir=root/'metadata';h.audit_dir.mkdir()
        h.mode='task';h.arm='P-HGU-1';h.controller_pid=99;h.baseline_binding={'native_pid':44}
        h.old_close_verified=True;h.private_attempted=False;h.start_binding=None
        state={'maintenance_controller':str(h.audit_dir/'state.json'),'active_private_phase':str(h.audit_dir),
            'production_temporarily_stopped':True,'active_cpu_build':False,'production_verification_pending':False,
            'decode_optimization_current':{'controller_pid':99,'mode':h.mode,'arm':h.arm,'selected_identity':{'start_binding':h.baseline_binding}}}
        (root/'STATE.json').write_text(json.dumps(state));return h,calls,state
    def test_own_release_rechecks_actual_free_and_preserves_initial_refusal(self):
        with tempfile.TemporaryDirectory() as d,patch.object(r,'E',Path(d)),patch.object(r,'memory_available',return_value=95*2**30):
            h,calls,state=self.setup_host(Path(d));self.assertEqual(h.free(),'actual-sole-GPU-lock-floor-rechecked')
            self.assertEqual(calls,['free','free']);self.assertFalse(h.private_attempted)
            self.assertFalse(json.loads((h.audit_dir/'post-stop-memory-initial.json').read_text())['passed'])
            row=json.loads((h.audit_dir/'post-stop-memory-wait.json').read_text());self.assertTrue(row['passed']);self.assertFalse(row['private_window_extended'])
    def test_foreign_controller_refuses_without_second_GPU_check(self):
        with tempfile.TemporaryDirectory() as d,patch.object(r,'E',Path(d)),patch.object(r,'memory_available') as memory:
            h,calls,state=self.setup_host(Path(d));state['decode_optimization_current']['controller_pid']=100
            (Path(d)/'STATE.json').write_text(json.dumps(state))
            with self.assertRaises(ValueError):h.free()
            self.assertEqual(calls,['free']);memory.assert_not_called();self.assertFalse(json.loads((h.audit_dir/'post-stop-memory-wait.json').read_text())['passed'])
    def test_timeout_remains_resource_deferral_before_any_attempt(self):
        with tempfile.TemporaryDirectory() as d,patch.object(r,'E',Path(d)),patch.object(r,'memory_available',return_value=70*2**30),patch('time.monotonic',side_effect=[0.,60.]):
            h,calls,state=self.setup_host(Path(d))
            with self.assertRaises(r.ResourceAdmissionDeferred):h.free()
            self.assertEqual(calls,['free']);self.assertFalse(h.private_attempted)
            row=json.loads((h.audit_dir/'post-stop-memory-wait.json').read_text());self.assertFalse(row['passed']);self.assertEqual(row['samples'][0]['elapsed_seconds'],60.)

class CurrentStartupRegression(unittest.TestCase):
    def sample(self):
        ready={'pid':71,'context':1048576,'can_stop':True,'batch_slots':0,'info':{'kv_resident':1048576,'engine_kind':'ds4','cpu_experts':6490,'ram_experts':6490,'expert_slots':8870,'vision':'ds4','vision_mib':0,'vision_room_mib':318,'vision_room':'chunk','vision_max_tokens':1024}}
        health={'loaded':True,'max_context':1048576,'images':True}
        models={'data':[{'id':'deepseek-v4.1-flash-iq2-xs','meta':{'n_ctx':1048576},'architecture':{'input_modalities':['text','image']},'capabilities':{'image_input':True}}]}
        log='prompts in chunks of 4096\n6490 of the CPU lane\'s 6490 experts copied into RAM\nno disk fallback\n'
        return ready,health,models,log
    def check(self,args):return c.controls.current_capacity(*args,4096,expected_context=1048576)
    def test_borrowed_chunk_vision_preserves_raw(self):
        args=self.sample();before=copy.deepcopy(args);self.assertTrue(self.check(args)['passed']);self.assertEqual(args,before)
    def test_resident_accounting_or_missing_room_refused(self):
        for key,value in [('vision','off'),('vision_mib',318),('vision_mib',False),('vision_room_mib',317),('vision_room_mib',True),('vision_room','resident'),('vision_max_tokens',512)]:
            args=self.sample();args[0]['info'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.check(args)
        args=self.sample();del args[0]['info']['vision_room_mib']
        with self.assertRaises(ValueError):self.check(args)
    def test_context_cancel_RAM_and_placement_gates_retained(self):
        for key,value in [('pid',True),('context',262144),('can_stop',False),('batch_slots',2)]:
            args=self.sample();args[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(args)
        for key,value in [('kv_resident',262144),('engine_kind','glm'),('cpu_experts',0),('ram_experts',0),('expert_slots',0)]:
            args=self.sample();args[0]['info'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(args)
    def test_HTTP_and_models_gates_retained(self):
        for key,value in [('loaded',False),('max_context',262144),('images',False)]:
            args=self.sample();args[1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(args)
        for key,value in [('id','wrong'),('meta',{'n_ctx':262144}),('architecture',{'input_modalities':['text']}),('capabilities',{'image_input':False})]:
            args=self.sample();args[2]['data'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(args)
    def test_real_chunk_RAM_log_gates_retained(self):
        for log in ('',self.sample()[3].replace('4096','2048'),self.sample()[3].replace('6490 experts','6489 experts'),self.sample()[3].replace('no disk fallback','')):
            args=list(self.sample());args[3]=log
            with self.assertRaises(ValueError):self.check(args)
    def test_loaded_drafter_is_not_execution(self):
        self.assertFalse(c.controls.draft_execution({},required=False)['execution_proven'])
        with self.assertRaises(ValueError):c.controls.draft_execution({'drafts_offered':20,'drafts_accepted':20},required=True)
    def test_actual_drafter_rounds_allow_zero_acceptance(self):
        value=c.controls.draft_execution({'draft_rounds':1,'draft_ms':.2,'verify_ms':0.,'drafts_accepted':0},required=True)
        self.assertTrue(value['execution_proven'])
    def test_invalid_or_lookup_only_drafting_refused(self):
        for stats in ({'draft_rounds':True},{'draft_rounds':-1},{'draft_rounds':0,'draft_ms':1.},{'draft_rounds':1,'draft_ms':0.},{'draft_rounds':1,'draft_ms':float('nan')},{'draft_rounds':1,'draft_ms':1.,'verify_ms':float('inf')}):
            with self.subTest(stats=stats),self.assertRaises(ValueError):c.controls.draft_execution(stats,required=True)

class NativeStatRegression(unittest.TestCase):
    def setUp(self):
        import hashlib
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)/'native-000';self.folder.mkdir()
        self.raw='STAT tok_s=50 draft_rounds=2 draft_ms=1.5 verify_ms=2.0'
        self.rows=[{'native_pid':71,'trace_number':0,'seconds':.1,'raw':self.raw}]
        self.receipt={'native_pid':71,'trace_number':0,'complete':True,'DONE_observed':True,'capture_error':None,'primary_error':None,'samples':1,'raw_lines_sha256':hashlib.sha256((self.raw+'\n').encode()).hexdigest()}
    def runstat(self,required=True):
        (self.folder/'stat-lines.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in self.rows));(self.folder/'stat-receipt.json').write_text(json.dumps(self.receipt));return c.controls.native_stat(self.folder,71,required=required)
    def test_exact_owned_raw_DSpark_STAT(self):self.assertTrue(self.runstat()['execution_proven'])
    def test_changed_pid_incomplete_count_or_hash_refused(self):
        for key,value in [('native_pid',72),('complete',False),('DONE_observed',False),('samples',2),('raw_lines_sha256','a'*64),('capture_error','fault')]:
            before=copy.deepcopy(self.receipt);self.receipt[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.runstat()
            self.receipt=before
    def test_raw_duplicate_clock_or_foreign_pid_refused(self):
        for key,value in [('native_pid',72),('seconds',float('nan')),('raw',self.raw+' draft_ms=1'),('raw','STAT draft_ms=1 verify_ms=1'),('raw',self.raw+'\nSTAT forged')]:
            before=copy.deepcopy(self.rows);self.rows[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.runstat()
            self.rows=before

class ActualFenceIntegration(unittest.TestCase):
    def test_installs80GiB_and_restores_captured_properties(self):
        owner=c.controls.fence_owner
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();group=root/'user.slice/strata-deepseek-window.service';group.mkdir(parents=True);proc=root/'proc';proc.write_text('0::/user.slice/strata-deepseek-window.service\n');out=root/'out';out.mkdir();tr=root/'transient';tr.mkdir();fragment=tr/owner.UNIT;fragment.write_text('owned')
            unit={'InvocationID':'a'*32,'Transient':'yes','ControlGroup':'/user.slice/strata-deepseek-window.service','MemoryMax':'infinity','MemorySwapMax':'infinity','FragmentPath':str(fragment),'DropInPaths':'','LoadState':'loaded'}
            for name,value in {'memory.max':'max','memory.swap.max':'max','memory.current':'1024','memory.events':'oom 0\noom_kill 0\n'}.items():(group/name).write_text(value)
            writes=[]
            def command(argv,**kw):
                if 'show' in argv:return types.SimpleNamespace(returncode=0,stdout=''.join(k+'='+unit[k]+'\n' for k in owner.FENCE_FIELDS))
                self.assertEqual(argv[:5],['systemctl','--user','set-property','--runtime',owner.UNIT]);writes.append(argv)
                for arg in argv[5:]:
                    key,value=arg.split('=',1);unit[key]=value;(group/('memory.max' if key=='MemoryMax' else 'memory.swap.max')).write_text(owner.limit_value(value))
                return types.SimpleNamespace(returncode=0,stdout='')
            install=owner.install_private_fence;restore=owner.restore_private_fence
            with patch.object(owner.runtime,'memory_available',return_value=8*2**30),patch.object(owner,'install_private_fence',side_effect=lambda output:install(output,command=command,proc=proc,root=root,transient_root=tr)),patch.object(owner,'restore_private_fence',side_effect=lambda fence,**kw:restore(fence,command=command,**kw)),patch.object(owner,'private_children_closed',return_value=True):
                with c.controls.fenced_phase(out) as (fence,handles):
                    self.assertEqual(fence['memory_max'],80*2**30);self.assertEqual((group/'memory.max').read_text(),str(80*2**30));self.assertEqual((group/'memory.swap.max').read_text(),'0')
            self.assertEqual((group/'memory.max').read_text(),'max');self.assertEqual((group/'memory.swap.max').read_text(),'max');self.assertEqual(len(writes),2)

class SavedStartupRegression(unittest.TestCase):
    def test_actual_failed_startup_observed_without_regrading_arm(self):
        folder=r.P/'recorded-startup-RTP2-failed'
        value=c.controls.startup(None,None,json.loads((folder/'native-ready.json').read_text()),json.loads((folder/'startup-health.json').read_text()),json.loads((folder/'startup-models.json').read_text()),(folder/'engine.log').read_text(),'HGU')
        self.assertTrue(value['passed']);self.assertEqual(value['current_engine']['identical_placement_repeat_rows'],2)
        self.assertEqual(len(value['current_engine']['placement']),2);self.assertFalse(value['drafter']['execution_proven']);self.assertFalse(value['current_engine']['model_quality_or_speed_proof'])
