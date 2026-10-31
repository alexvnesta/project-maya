"""New-native compatibility integration boundaries; synthetic CPU only."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
import current_compat as c
import current_runtime as r
import current_config as config

SOURCE=r.Q/'model-v1/prose-fixtures-B.json'
BASE=r.P/'profile-base-config.json'


def sample():
    case=copy.deepcopy(json.loads(SOURCE.read_text())['lifecycle_cases'][-1])
    case.pop('dependency');case['request']['seed']=2;case.update(id=r.COMPAT_CASE_ID,expected_reuse='zero');return case


def warm_sample():
    value=sample();value.update(id='state44-warm',expected_reuse='prompt-minus-one',dependency='state44-cold');return value


def answer():
    return ({'status':200,'done':True,'cancelled':False,'finish_reason':'stop','content':'RECOVERED_Q8_LITERAL'},
        {'observed_tokens':7,'prompt_tokens':44,'native':{'generated':7,'finish':'stop','reused':0,
            'drafts_offered':0,'drafts_accepted':0,'prompt_ms':1.,'decode_ms':2.}})


class Policy(unittest.TestCase):
    def test_both_new_profiles_only(self):
        for arm in ('STP2','STP1'):
            f=config.factor('state',arm);self.assertEqual(f['context_total'],1048576)
            self.assertEqual(f['output_allowance'],262144);self.assertEqual(f['native_sha256'],config.BASE_NATIVE)
            self.assertNotEqual(config.SELECTED_NATIVE,config.BASE_NATIVE)
        for mode,arm in [('prose','B1'),('quality','QS1'),('state','CS1'),('state','CTP3')]:
            with self.assertRaises(ValueError):config.factor(mode,arm)
    def test_new_profile_preserves_full_policy(self):
        base=json.loads(BASE.read_text());before=copy.deepcopy(base)
        d=config.E/'results/maya145-state-mayas-TP2-20261031T170000Z/native'
        v=config.make_config(base,d,'state','STP2')
        self.assertTrue(config.check_config(base,v,d,'state','STP2'));self.assertEqual(base,before)
        self.assertEqual(v['env']['DS4_TP_GGUF_UNEVEN'],'1');self.assertEqual(v['env']['DS4_AR2'],'1')
        self.assertEqual(v['args'][v['args'].index('--dspark')+1],'on');self.assertEqual(v['env']['DS4_SERVE_DUMP'],str(d/'logits'))
        for name,value in [('exe',str(config.D/'bin/maya-ds4')),('hosted_default_effort',50),('max_tokens',32768)]:
            bad=copy.deepcopy(v);bad[name]=value
            with self.assertRaises(ValueError):config.check_config(base,bad,d,'state','STP2')
    def test_real_process_exact_policy_and_cgroup(self):
        base=json.loads(BASE.read_text());d=config.E/'results/maya145-state-mayas-TP2-20261031T170000Z/native'
        v=config.make_config(base,d,'state','STP2');argv=config.expected_native_argv(v)
        self.assertTrue(config.process_contract(v,argv,v['env'],'0::/user.slice/strata-deepseek-window.service',same_executable=True)['argv_matches'])
        for a,e,g,s in [(argv[:-1],v['env'],'strata-deepseek-window.service',True),(argv,v['env'],'other.service',True),
                        (argv,{**v['env'],'DS4_TP_GGUF_UNEVEN':'0'},'strata-deepseek-window.service',True),
                        (argv,v['env'],'strata-deepseek-window.service',False)]:
            with self.assertRaises(ValueError):config.process_contract(v,a,e,g,same_executable=s)
    def test_single_encoded_short_request_no_retokenize(self):
        m=c.manifest('state','STP2');self.assertEqual(m['cases'],[sample(),warm_sample()]);self.assertEqual(m['cases'][0]['prompt_tokens'],44)
        self.assertFalse(m['quality_or_performance_pass']);self.assertFalse(m['automatic_next_arm'])
    def test_foreign_mode_before_manifest(self):
        with patch.object(r,'compatibility_manifest') as read:
            with self.assertRaises(ValueError):c.manifest('prose','B1')
        read.assert_not_called()


class OneRequest(unittest.TestCase):
    def test_one_natural_result_no_speed_or_quality_claim(self):
        issue=Mock(return_value=answer());v=c.run_one(sample(),'.',71,1000,issue=issue)
        issue.assert_called_once();self.assertTrue(v['complete']);self.assertFalse(v['quality_or_performance_pass']);self.assertFalse(v['retry'])
    def test_wrong_literal_and_partial_never_accepted(self):
        for delta in [{'content':'other'},{'done':False},{'finish_reason':'length'},{'cancelled':True},
                      {'intentional_budget_stop':True},{'status':500},{'budget_not_started':True}]:
            response,proof=answer();response.update(delta);issue=Mock(return_value=(response,proof))
            self.assertFalse(c.run_one(sample(),'.',71,1000,issue=issue)['complete']);issue.assert_called_once()
    def test_native_fault_no_retry(self):
        issue=Mock(side_effect=RuntimeError('native'));progress=[]
        with self.assertRaises(RuntimeError):c.run_one(sample(),'.',71,1000,issue=issue,save_progress=lambda x:progress.append(copy.deepcopy(x)))
        issue.assert_called_once();self.assertEqual(progress[-1]['scores'][0]['status'],'FAULT_HOLD')
    def test_deadline_UNRUN_retained(self):
        issue=Mock(side_effect=c.controls.Incomplete('UNRUN deadline'))
        v=c.run_one(sample(),'.',71,1000,issue=issue);self.assertFalse(v['complete']);self.assertFalse(v['retry']);issue.assert_called_once()
    def test_token_count_and_reuse_contradictions_refused(self):
        for key,value in [('generated',8),('reused',1),('drafts_offered',True),('drafts_accepted',1),('decode_ms',float('nan'))]:
            response,proof=answer();proof['native'][key]=value;issue=Mock(return_value=(response,proof))
            try:v=c.run_one(sample(),'.',71,1000,issue=issue)
            except ValueError:pass
            else:self.assertFalse(v['complete'])
            issue.assert_called_once()
    def test_prompt_and_policy_change_before_issue(self):
        for key,value in [('id','other'),('expected','other'),('prompt_ids',[0]*44)]:
            case=sample();case[key]=value;issue=Mock()
            with self.assertRaises(ValueError):c.run_one(case,'.',71,1000,issue=issue)
            issue.assert_not_called()
        case=sample();case['request']['max_tokens']=64
        with self.assertRaises(ValueError):c.run_one(case,'.',71,1000,issue=Mock())


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
        out=self.e/'results/maya145-state-mayas-TP2-20261031T170000Z';self.assertEqual(r.owned_paths(out,'state','STP2')[1].name,out.name)
        for bad,arm in [(self.e/'results/maya-s-compatibility-CS1-20261030T180000Z','STP2'),(out,'STP1')]:
            with self.assertRaises(ValueError):r.owned_paths(bad,'state',arm)
    def test_existing_directory_or_alias_refused(self):
        out=self.e/'results/maya145-state-mayas-TP2-20261031T170000Z';out.mkdir()
        with self.assertRaises(ValueError):r.owned_paths(out,'state','STP2')
        out.rmdir();out.symlink_to(self.p,target_is_directory=True)
        with self.assertRaises(ValueError):r.owned_paths(out,'state','STP2')
    def test_attempt_registry_one_shot_no_automatic_timing(self):
        r.prerequisite('state','STP2',{})
        for registry in ({'STP2':{'fully_reviewed':True}},{'STP1':{'fully_reviewed':False}},{'STP1':{'fully_reviewed':True,'accepted':False}},{'CS1':{'fully_reviewed':True}}):
            with self.assertRaises(ValueError):r.prerequisite('state','STP2',registry)
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


class Phase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.out=Path(self.temp.name)/'output'
        old=types.SimpleNamespace(q8_phase=types.SimpleNamespace(admission=Mock(return_value='window')))
        for x in (patch.object(c,'helpers',return_value=(None,old,None,None,None,None,None)),
                  patch.object(c,'read_proof',return_value={'qualification_sha256':'a'*64}),
                  patch.object(r,'qualified',return_value={}),patch.object(c,'window_contract'),patch.object(c,'manifest',return_value={'cases':[sample(),warm_sample()]})):
            x.start();self.addCleanup(x.stop)
    def test_fence_restored_before_terminal_receipt(self):
        events=[]
        class Fence:
            def __enter__(self):events.append('install');return {},[]
            def __exit__(self,*args):events.append('restore')
        emit=r.emit
        def write(p,v):events.append('receipt');emit(p,v)
        with patch.object(c.controls,'fenced_phase',return_value=Fence()),patch.object(c,'phase_body',side_effect=lambda *a:(events.append('body') or {})),patch.object(r,'emit',side_effect=write):
            c.phase(self.out,'state','STP2','unused')
        self.assertEqual(events,['install','body','restore','receipt'])
    def test_failed_fence_never_success(self):
        class Fence:
            def __enter__(self):return {},[]
            def __exit__(self,*args):raise RuntimeError('fence restore')
        with patch.object(c.controls,'fenced_phase',return_value=Fence()),patch.object(c,'phase_body',return_value={}):
            with self.assertRaises(RuntimeError):c.phase(self.out,'state','STP2','unused')
        self.assertFalse((self.out/'receipt.json').exists())
    def test_replay_stops_before_fence(self):
        self.out.mkdir()
        with patch.object(c.controls,'fenced_phase') as fence:
            with self.assertRaises(FileExistsError):c.phase(self.out,'state','STP2','unused')
        fence.assert_not_called()
    def test_old_arm_refused_before_support(self):
        with self.assertRaises(ValueError):c.phase(self.out,'state','CS1','unused')
        c.helpers.assert_not_called()


class Window(unittest.TestCase):
    def test_exact_entry_window_and_terminal_rejection(self):
        out=r.E/'results/maya145-state-mayas-TP2-20261031T170000Z';proof=r.E/'maintenance'/out.name/'proof.json'
        argv=[str(c.R/'venv/bin/python3.14'),'-B',str(c.P/'current_compat.py'),'--phase','--mode','state','--arm','STP2','--output',str(out),'--proof',str(proof)]
        value={'command':argv,'continued_from':'prior','test_returncode':None,'maintenance_held':False,'restored':False}
        old=types.SimpleNamespace(owned_window=Mock(return_value=(c.R/'windows/new.json',value)))
        c.window_contract(old,out,'state','STP2',proof)
        for delta in [{'command':argv[:2]+['old.py']+argv[3:]},{'test_returncode':0},{'restored':True}]:
            old.owned_window.return_value=(c.R/'windows/new.json',{**value,**delta})
            with self.assertRaises(ValueError):c.window_contract(old,out,'state','STP2',proof)



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
            host=r.make_host(None,None,None,None,None)();host.mode='state';host.arm='STP2'
            host.audit_dir=Path('/owned/meta');host.qualification_sha256='a'*64
            host.reserve_attempt=Mock();host.phase_argv=Mock(return_value=['new-phase'])
            self.assertEqual(host.launch('prior','output',host.audit_dir/'proof.json'),('prior',['new-phase'],1200))
            qualify.assert_called_once_with('state','a'*64);host.reserve_attempt.assert_called_once()
            self.assertTrue(host.private_attempted);self.assertEqual(host.private_output,'output')
    def test_foreign_proof_never_reserves(self):
        with patch.object(r,'reusable',return_value=self.prior()),patch.object(r,'qualified',return_value={}):
            host=r.make_host(None,None,None,None,None)();host.mode='state';host.arm='STP2'
            host.audit_dir=Path('/owned/meta');host.qualification_sha256='a'*64;host.reserve_attempt=Mock()
            with self.assertRaises(ValueError):host.launch('prior','output','/foreign/proof.json')
            host.reserve_attempt.assert_not_called()


class Body(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.e=Path(self.tmp.name).resolve();self.out=self.e/'results/maya145-state-mayas-TP2-20261031T170000Z'
        self.folder=self.out/'native';self.folder.mkdir(parents=True);(self.folder/'tmp').mkdir()
        self.d=self.e/'selected';self.d.mkdir();(self.d/'config.json').write_bytes(BASE.read_bytes())
        (self.d/'profile-seed.bin').write_bytes(b'seed');(self.folder/'engine.log').write_text('short startup')
        self.proc=types.SimpleNamespace(pid=71);self.handles=[]
        def body_cleanup(body,cleanup):
            try:return body()
            finally:cleanup()
        self.old=types.SimpleNamespace(q8_phase=types.SimpleNamespace(SEED_SHA=r.sha(self.d/'profile-seed.bin'),
            environment=Mock(return_value={}),wait_startup=Mock(return_value=({'pid':72},{},{})),
            native_paths=lambda p:sorted(Path(p).glob('native-[0-9][0-9][0-9]'))),
            body_and_cleanup=body_cleanup,stop_server=Mock())
        response,proof=answer()
        def issue(case,folder,pid,deadline,*,requester):
            self.assertEqual(pid,72);self.assertEqual(deadline,1100)
            actual=requester('private-test',case['request'],deadline);index=len(self.old.q8_phase.native_paths(folder));trace=Path(folder)/('native-%03d'%index);trace.mkdir()
            (trace/'tokens.jsonl').write_text(''.join(json.dumps({'token':i,'seconds':i*.001})+'\n' for i in range(7)))
            observed=copy.deepcopy(proof);observed['native']['reused']=0 if case['expected_reuse']=='zero' else 43
            return actual,observed
        self.skip=types.SimpleNamespace(issue=Mock(side_effect=issue),ControlBudgetStop=type('Stop',(Exception,),{}),
            activation=Mock(return_value={'activation_early_rows':[]}))
        protocol=types.SimpleNamespace(Stream=Mock(),json_get=Mock(),wait_for=Mock())
        self.numerical=types.SimpleNamespace(dump_snapshot=Mock(return_value={'status':'WITHIN_BUDGET','count':2}),dump_size=Mock(return_value={'bytes':517120,'rows':1,'finite_or_equivalence_proven':False}),owned_storage_snapshot=Mock())
        # Keep profile's canonical namespace/policy validation; only transform
        # the synthetic root before passing the generated config to the phase.
        frozen=config.make_config(json.loads(BASE.read_text()),config.E/'results/maya145-state-mayas-TP2-20261031T170000Z/native','state','STP2')
        for x in (patch.object(c,'D',self.d),patch.object(c.time,'monotonic',return_value=101),
                  patch.object(c.subprocess,'Popen',return_value=self.proc),
                  patch.object(c.config,'make_config',return_value=frozen),patch.object(c.controls,'startup',return_value={}),
                  patch.object(c.controls,'actual_native',return_value={}),patch.object(c.controls,'native_limit_read',return_value={'file_limit_bytes':512*2**20}),patch.object(c.controls,'observed_cold_path',return_value={'historical_reference_required':False}),patch.object(c.controls,'round_schedule',return_value={'diagnostic_only':True}),patch.object(c.controls,'fence_terminal',return_value={'passed':True}),
                  patch.object(c.controls,'bounded_request',return_value=response),patch.object(c.controls,'native_stat',return_value={'execution_proven':True}),
                  patch.dict(c.sys.modules,{'skip_controls':self.skip,'protocol':protocol})):
            x.start();self.addCleanup(x.stop)
    def call(self):
        return c.phase_body(self.out,'state','STP2',{}, {},'window',{'cases':[sample(),warm_sample()]},self.folder,{},self.handles,100,None,self.old,self.numerical,None)
    def test_scripted_native_trace_and_cleaned_API(self):
        value=self.call();self.assertTrue(value['arm_results']['complete']);self.assertEqual(self.handles,[self.proc])
        self.assertEqual(self.skip.issue.call_count,2);self.old.stop_server.assert_called_once_with(self.proc,self.folder,timeout=100)
        self.assertTrue(c.controls.bounded_request.call_args.args[4]);self.numerical.dump_snapshot.assert_called_once_with(self.folder,complete=False)
        self.assertEqual(json.loads((self.out/'candidate-config.shared-settings.json').read_text()),{'max_tokens':262144})
        self.assertIn(str(c.P/'current_compat.py'),c.subprocess.Popen.call_args.args[0])
    def test_first_receipt_fault_still_closes_captured_API(self):
        emit=r.emit
        def fail(path,value):
            if Path(path).name=='server-start.json':raise RuntimeError('first receipt')
            return emit(path,value)
        with patch.object(r,'emit',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'first receipt'):self.call()
        self.assertEqual(self.handles,[self.proc]);self.old.stop_server.assert_called_once();self.skip.issue.assert_not_called()
    def test_extra_native_request_refused_and_cleaned(self):
        original=self.skip.issue.side_effect
        def extra(*args,**kwargs):
            value=original(*args,**kwargs);(self.folder/'native-002').mkdir();return value
        self.skip.issue.side_effect=extra
        with self.assertRaises(ValueError):self.call()
        self.old.stop_server.assert_called_once();self.skip.issue.assert_called_once()



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
        self.assertEqual(r.qualification_path().name,'state-qualification.json')



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
        h.mode='state';h.arm='STP2';h.controller_pid=99;h.baseline_binding={'native_pid':44}
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
        value=c.controls.startup(None,None,json.loads((folder/'native-ready.json').read_text()),json.loads((folder/'startup-health.json').read_text()),json.loads((folder/'startup-models.json').read_text()),(folder/'engine.log').read_text(),'TP2')
        self.assertTrue(value['passed']);self.assertEqual(value['current_engine']['identical_placement_repeat_rows'],2)
        self.assertEqual(len(value['current_engine']['placement']),2);self.assertFalse(value['drafter']['execution_proven']);self.assertFalse(value['current_engine']['model_quality_or_speed_proof'])

if __name__=='__main__':unittest.main()
