"""Saved-stream, bounded finite-scan and exact state comparison controls."""
import array
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import cpu_driver as driver
import cpu_model_numerical_audit as a
import cpu_model_audit_runner as runner


class SavedStream(unittest.TestCase):
    def event(self,content=None,finish=None):
        return 'data: '+json.dumps({'choices':[{'delta':{'content':content},'finish_reason':finish}]})+'\n'
    def test_split_READY_is_assembled(self):
        raw=self.event('READ')+self.event('Y')+self.event(finish='stop')+'data: [DONE]\n'
        self.assertEqual(a.assembled_ready(raw),{'content':'READY','finish':'stop','DONE':True})
    def test_error_partial_duplicate_or_after_done_rejected(self):
        good=self.event('READY')+self.event(finish='stop')+'data: [DONE]\n'
        for raw in (self.event('READY'),good+'data: [DONE]\n',good+self.event('extra'),self.event('WRONG')+self.event(finish='stop')+'data: [DONE]\n',self.event('READY')+self.event(finish='length')+'data: [DONE]\n','data: {"error":"fault"}\n'+good):
            with self.assertRaises(ValueError):a.assembled_ready(raw)
    def test_saved_request_cannot_reduce_output_or_change_effort(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve();req=p/'public-default-output-request.json';raw=p/'public-default-output-sse.txt'
            req.write_text(json.dumps(a.PUBLIC_DEFAULT_REQUEST));raw.write_text(self.event('READY')+self.event(finish='stop')+'data: [DONE]\n')
            self.assertTrue(a.public_saved_contract(p)['DONE'])
            for delta in ({'max_tokens':64},{'reasoning_effort':'low'}):
                req.write_text(json.dumps(dict(a.PUBLIC_DEFAULT_REQUEST,**delta)))
                with self.assertRaises(ValueError):a.public_saved_contract(p)


class FiniteScans(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name).resolve()/'logits.1.f32'
        self.path.write_bytes(array.array('f',[0.0]*129280).tobytes())
        self.dump=a.controls.finite_dump(self.path)
        self.scan={'passed':True,'operation':'scan','arm':'N0','index':0,'case_id':'case','path':str(self.path),
                   'qualification_sha256':'a'*64,'before':a.fingerprint(self.path),'after':a.fingerprint(self.path),'dump':self.dump}
    def test_one_full_finite_row_requires_no_alignment_claim(self):
        self.assertEqual(a.scanned_dump(self.path,self.scan,'N0',0,'case','a'*64),self.dump)
        self.assertFalse(self.dump['token_row_alignment_claimed'])
    def test_wrong_scan_association_or_changed_dump_refused(self):
        for delta in ({'arm':'N1'},{'index':1},{'case_id':'other'},{'qualification_sha256':'b'*64},{'path':'/foreign'},{'passed':False}):
            with self.assertRaises(ValueError):a.scanned_dump(self.path,dict(self.scan,**delta),'N0',0,'case','a'*64)
        self.path.write_bytes(array.array('f',[1.0]*129280).tobytes())
        with self.assertRaises(ValueError):a.scanned_dump(self.path,self.scan,'N0',0,'case','a'*64)
    def test_nonfinite_partial_and_token_alignment_claim_rejected(self):
        for raw in (b'x',array.array('f',[float('inf')]*129280).tobytes()):
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError):a.controls.finite_dump(self.path)
        self.path.write_bytes(array.array('f',[0.0]*129280).tobytes())
        self.scan['before']=self.scan['after']=a.fingerprint(self.path)
        self.scan['dump']=dict(self.dump,token_row_alignment_claimed=True)
        with self.assertRaises(ValueError):a.scanned_dump(self.path,self.scan,'N0',0,'case','a'*64)
    def test_scan_index_bool_or_foreign_arm_blocks_before_context(self):
        with patch.object(a,'arm_context',side_effect=AssertionError('no read')):
            for i in (True,-1,4):
                with self.assertRaises(ValueError):a.scan_one('N0',i,'a'*64)
    def test_four_scans_and_guard_required_before_terminal_audit(self):
        for scans in ([],{},[{}]*3):
            with self.assertRaises(ValueError):a.audit('N0',scans,guard=lambda:None)
        with self.assertRaises(ValueError):a.audit('N0',[{}]*4,guard=None)


class Matched(unittest.TestCase):
    def values(self):
        rows=[]
        for name in a.controls.fixture.IDS:
            rows.append({'id':name,'tokens':[1,2],'native':dict(prompt_tokens=8,generated=2,reused=0,drafts_offered=3,drafts_accepted=1),
                         'dump':dict(all_finite=True,rows=2,bytes=2*129280*4,sha256='a'*64,token_row_alignment_claimed=False)})
        startup={'cpu_experts':4045,'expert_slots':11315,'placement':{'trunk_split':[19,21],'head_GPU':1,'drafter_GPU':0,
                 'human_rows':[dict(device=0,first=0,last=42,human_experts_including_drafter=5746,human_total=7680),
                               dict(device=1,first=19,last=39,human_experts_including_drafter=5953,human_total=8064)]}}
        x=dict(passed=True,arm='N0',qualification_sha256='a'*64,startup=startup,rows=rows)
        y=copy.deepcopy(x);y['arm']='N1';return x,y
    def test_exact_complete_paths_only_numerical_not_speed_claim(self):
        x,y=self.values();result=a.compare_complete(x,y)
        self.assertTrue(result['passed']);self.assertFalse(result['speed_pass']);self.assertFalse(result['general_quality_claim'])
    def test_one_token_logit_row_or_native_difference_blocks(self):
        for field in ('tokens','dump','native'):
            x,y=self.values()
            if field=='tokens':y['rows'][0]['tokens']=[1,3]
            if field=='dump':y['rows'][0]['dump']['sha256']='b'*64
            if field=='native':y['rows'][0]['native']['drafts_accepted']=2
            result=a.compare_complete(x,y);self.assertFalse(result['passed']);self.assertFalse(result['retry'])
    def test_placement_count_change_or_unaccepted_arm_blocks(self):
        x,y=self.values();y['startup']['placement']['human_rows'][0]['human_experts_including_drafter']+=1
        with self.assertRaises(ValueError):a.compare_complete(x,y)
        for delta in ({'passed':False},{'arm':'N0'},{'qualification_sha256':'b'*64}):
            x,y=self.values();y.update(delta)
            with self.assertRaises(ValueError):a.compare_complete(x,y)


class BoundedAuditCustody(unittest.TestCase):
    def test_namespace_job_and_parent_record(self):
        for arm,job in (('N2',None),('N0','other')):
            with self.assertRaises(ValueError):runner.paths(arm,job)
        binding={'native_pid':12};record=dict(mode='cpu-iq2xs-model-offline-audit',arm='N0',qualification_sha256='a'*64,
            controller_pid=123,controller_start_ticks=42,nonce='b'*32,start_binding=binding)
        runner.record_contract(record,'N0','a'*64,123,binding)
        for delta in ({'controller_pid':124},{'qualification_sha256':'c'*64},{'controller_start_ticks':True},{'nonce':False}):
            with self.assertRaises(ValueError):runner.record_contract(dict(record,**delta),'N0','a'*64,123,binding)
    def test_child_chain_requires_actual_command_exit_bounds_and_source_maps(self):
        with tempfile.TemporaryDirectory() as d,patch.object(runner,'HERE',Path(d).resolve()):
            arm='N0';job='scan-0';parent=321;pin='a'*64;q=dict(qualification_sha256=pin,source_sha256={'s':'b'*64},input_sha256={'i':'c'*64})
            folder=runner.paths(arm,job);folder.mkdir(parents=True)
            observed=dict(pid=123,ppid=parent,pgid=123,cpu=[30,30],nice=15,environment=driver.ENV,platform='linux',dont_write_bytecode=True,as_value=[driver.AS_BYTES]*2)
            observed['as']=observed.pop('as_value')
            argv=[runner.sys.executable,'-I','-B',str(runner.HERE/'cpu_model_audit_runner.py'),'--arm',arm,'--qualification-pin',pin,'--worker',job,'--parent-pid',str(parent)]
            result=dict(passed=True,arm=arm,job=job,qualification_sha256=pin,observed=observed,post_observed=observed,
                        source_sha256=q['source_sha256'],source_after_sha256=q['source_sha256'],input_sha256=q['input_sha256'],input_after_sha256=q['input_sha256'],value={'finite':True})
            child=dict(pid=123,argv=argv,error=None,cleanup=[],returncode=0,elapsed_seconds=1)
            attempt=dict(arm=arm,job=job,parent_pid=parent,qualification_sha256=pin)
            for name,value in [('attempt.json',attempt),('child.json',child),('observed.json',observed),('result.json',result)]:runner.emit(folder/name,value)
            self.assertEqual(runner.child_chain(driver,q,arm,job,parent),{'finite':True})
            for delta in ({'returncode':False},{'cleanup':['uncertain']},{'elapsed_seconds':-1},{'elapsed_seconds':float('inf')},{'argv':['other']}):
                (folder/'child.json').write_text(json.dumps(dict(child,**delta)))
                with self.assertRaises(ValueError):runner.child_chain(driver,q,arm,job,parent)


class FullSavedTerminal(unittest.TestCase):
    """Synthetic terminal custody exercises the whole independent assembler."""
    def setUp(self):
        from contextlib import ExitStack
        import sys
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.stack=ExitStack();self.addCleanup(self.stack.close)
        local_e=Path(__file__).resolve().parents[3]
        self.stack.enter_context(patch.object(sys,'path',[str(local_e/'q8-batch-v1'),str(local_e/'prefill-cache-improvements-20261027'),str(local_e/'prefill-v2'),*sys.path]))
        self.manifest=a.mode.frozen();self.pin='a'*64;self.pid=123
        self.e=self.root/'e';self.r=self.root/'r';self.p=self.root/'mode'
        for path in (self.e/'results',self.e/'maintenance',self.r/'windows',self.p):path.mkdir(parents=True)
        self.out=self.e/'results/decode-cpu-iq2xs-numerical-N0-20261031T010203Z';self.out.mkdir();self.folder=self.out/'native';self.folder.mkdir()
        for path in ('tmp','cache','cuda-cache'):(self.folder/path).mkdir()
        self.meta=self.e/'maintenance'/self.out.name;self.meta.mkdir()
        for target,name,value in ((a.runtime,'E',self.e),(a.runtime,'R',self.r),(a.mode,'P',self.p),(a.config,'E',self.e)):
            self.stack.enter_context(patch.object(target,name,value))
        self.stack.enter_context(patch.object(a.mode,'frozen',return_value=self.manifest))
        self.stack.enter_context(patch.object(a.runtime,'support',return_value=(None,None)))
        self.q={'files':{},'allowed_automatic_cuts':{'N0':[19],'N1':[19]}}
        self.stack.enter_context(patch.object(a.runtime,'qualified',return_value=self.q))
        self.write(self.p/'numerical-arms.json',{'N0':dict(attempted=True,output=str(self.out),proof=str(self.meta/'proof.json'),controller_pid=456)})
        binding=dict(invocation='b'*32,main_pid=122,native_pid=123,native_start_ticks=100)
        identity=dict(native_sha256=a.config.BASE_NATIVE,config_sha256=a.config.BASE_SHA,context=1048576,output_default=262144,
            prompt_skip_mode=1,prefill_chunk=4096,Q8=[1,1],TP=1,images=True,runtime_ablation=True,CPU_experts=4045,all_CPU_experts_RAM=True,native_pid=123,start_binding=binding)
        public=dict(unauthenticated_models=401,authenticated_models=200,SSE_done=True,finish='stop',known_answer_passed=True)
        health=dict(loaded=True,max_context=1048576,images=True,switcher=dict(active_model='deepseek',fault=None))
        self.window=self.r/'windows/20261031T010204Z.json'
        self.state=dict(status=a.runtime.statuses(a.mode.MODE,'N0')['complete'],output=str(self.out),proof_path=str(self.meta/'proof.json'),
            qualification_sha256=self.pin,controller_pid=456,window=str(self.window),verified=dict(selected_identity=identity,public=public,health=health))
        self.write(self.meta/'state.json',self.state)
        self.write(self.meta/'proof.json',dict(files={},arm='N0',mode=a.mode.MODE,output=str(self.out),qualification_sha256=self.pin,qualified_for_owned_cpu_iq2xs_model=True))
        self.write(self.meta/'post-stop-memory.json',dict(passed=True,available_bytes=90*2**30,required_bytes=88*2**30))
        command=[str(self.r/'venv/bin/python3.14'),'-B',str(self.p/'cpu_model_numerical.py'),'--phase','--arm','N0','--output',str(self.out),'--proof',str(self.meta/'proof.json')]
        self.write(self.window,dict(command=command,maintenance_root_window='20261025T032914Z.json',continued_from='prior',test_returncode=0,maintenance_held=True,maintenance_resume_allowed=True,restored=False))
        self.window.with_suffix('.telemetry.jsonl').write_text(json.dumps(dict(kernel_capture_returncode=0,kernel_fault_lines=[],root_free_bytes=140*2**30,swap_pages={'pswpout':0}))+'\n')
        before=dict(InvocationID=binding['invocation'],MainPID='0',ActiveState='inactive',ExecMainCode='1',ExecMainStatus='0',Result='success')
        close=dict(native_pid=123,server_pid=122,returncode=0,closed=True)
        self.write(self.meta/'old-owner-close.json',dict(passed=True,binding=binding,native_close=close,before=before,after=before))
        self.write(self.meta/'public-default-output-request.json',a.PUBLIC_DEFAULT_REQUEST)
        (self.meta/'public-default-output-sse.txt').write_text('data: '+json.dumps({'choices':[{'delta':{'content':'READ'},'finish_reason':None}]})+'\ndata: '+json.dumps({'choices':[{'delta':{'content':'Y'},'finish_reason':'stop'}]})+'\ndata: [DONE]\n')
        base=json.loads((Path(__file__).parent/'base-config.json').read_text());self.write(self.p/'base-config.json',base)
        c=a.config.make_config(base,self.folder,a.mode.MODE,'N0');self.write(self.out/'candidate-config.json',c);self.write(self.out/'fixture.json',self.manifest)
        log='DS4_PROMPT_SKIP mode=1\n'
        # Activation has its own qualified source parser; retain its independently
        # tested result here so full-terminal negatives target saved custody.
        self.activation={'activation_early_rows':self.manifest['expected_mode1_activation_skipped_tokens']}
        import skip_controls
        self.stack.enter_context(patch.object(skip_controls,'activation',return_value=self.activation))
        (self.folder/'engine.log').write_text(log);self.write(self.folder/'native-ready.json',{'pid':123})
        self.startup={'actual_process':dict(actual_argv=a.config.expected_native_argv(c),controlled_env=c['env'],
            actual_cgroup='0::/user.slice/strata-deepseek-window.service\n',same_executable=True,native_sha256=a.config.BASE_NATIVE,native_pid=123,
            native_fsize_limits_raw='Max file size '+str(a.mode.storage.HARD_FILE_BYTES)+' '+str(a.mode.storage.HARD_FILE_BYTES)+' bytes')}
        self.stack.enter_context(patch.object(a.mode,'startup',return_value=self.startup))
        for path,value in ((self.out/'startup-audit.json',self.startup),(self.out/'startup-health.json',{}),(self.out/'startup-models.json',{}),
            (self.folder/'native-fsize-launch.json',dict(native_pid=123,argv=a.config.expected_native_argv(c)[:-1],API_limit_changed=False,hard_file_bytes=a.mode.storage.HARD_FILE_BYTES)),
            (self.folder/'entry-audit.json',dict(server_pid=124,startup_retries=0,default_effort=100,native_sha256=a.config.BASE_NATIVE)),
            (self.out/'server-start.json',dict(pid=124))):self.write(path,value)
        cleanup=dict(passed=True,server_returncode=0,server_pid=124,grace_timeout=False,application_stopped=True,native_ready_pid=123)
        self.write(self.folder/'server-cleanup.json',cleanup);(self.folder/'native-close.jsonl').write_text(json.dumps(close)+'\n')
        self.write(self.folder/'private-api-exit.json',dict(passed=True,actual_Popen_returncode=0,server_pid=124,server_cleanup=cleanup))
        self.write(self.out/'private-child-closure.json',{'passed':True})
        self.stack.enter_context(patch.object(a,'fence_contract',return_value={'passed':True}))
        for path in (self.out/'private-memory-fence.json',self.out/'private-memory-fence-restored.json',self.meta/'private-memory-fence-collected.json'):self.write(path,{})
        self.rows=[];self.scans=[]
        from q8_audit import reconcile
        for i,case in enumerate(self.manifest['cases']):
            trace=self.folder/('native-%03d'%i);trace.mkdir();dest=self.folder/'skip-controls'/case['id'];dest.mkdir(parents=True)
            prompt=case['prompt_ids'];req=case['request'];has_images=any(isinstance(m.get('content'),list) and any(x.get('type')=='image_url' for x in m['content']) for m in req['messages'])
            self.write(trace/'request.json',dict(native_pid=123,ids=prompt,max_new=32768,sampling={k:req[k] for k in ('temperature','top_p','seed')},has_images=has_images))
            self.write(trace/'trace-receipt.json',dict(native_pid=123,error=None,DONE_observed=True,T_lines=2))
            native=dict(generated=2,prompt_tokens=len(prompt),prompt_ms=1.0,decode_ms=2.0,finish='stop',reused=0 if case['expected_reuse']=='zero' else len(prompt)-1,drafts_offered=5,drafts_accepted=1)
            self.write(trace/'native-statistics.json',native);(trace/'tokens.jsonl').write_text('{"token":1}\n{"token":2}\n')
            usage=dict(prompt_tokens=len(prompt),completion_tokens=2);content=json.dumps(case['expected'])
            events=[dict(choices=[dict(delta={'content':content},finish_reason='stop')],usage=usage,timings=None)]
            response=dict(status=200,done=True,cancelled=False,finish_reason='stop',content=content,reasoning='',events=events,usage=usage,timings=None,tool_calls=[],
                raw=[dict(seconds=0.1,line='data: '+json.dumps(events[0])+'\n'),dict(seconds=0.2,line='data: [DONE]\n')])
            self.write(dest/'request.json',req);self.write(dest/'response.json',response)
            proof=reconcile(trace,case,response,123);self.write(dest/'native-audit.json',proof)
            dump=self.folder/('logits.%d.f32'%(i+1));dump.write_bytes(array.array('f',[float(i)]*129280).tobytes())
            row=a.controls.natural_contract(case,response,proof);row['dump_size_only']=a.controls.dump_size(dump);self.rows.append(row)
            self.scans.append(dict(passed=True,operation='scan',arm='N0',index=i,case_id=case['id'],path=str(dump),qualification_sha256=self.pin,
                before=a.fingerprint(dump),after=a.fingerprint(dump),dump=a.controls.finite_dump(dump)))
        self.write(self.out/'receipt.json',dict(arm_results=dict(complete=True,actual_native_count=4,native_count=4,quality_or_speed_pass=False,
            DSI1_leftovers=[],CPU_IQ2XS=a.config.factor_activation(log,a.mode.MODE,'N0'),activation=self.activation,rows=self.rows),resource_fence_terminal={}))
    def write(self,path,value):path.write_text(json.dumps(value,indent=2)+'\n')
    def run_audit(self):return a.audit('N0',self.scans,guard=lambda:None)
    def change(self,path,key,value):
        row=json.loads(path.read_text());row[key]=value;self.write(path,row)
    def test_full_four_state_saved_assembler_accepts_and_retains_tokens(self):
        result=self.run_audit();self.assertTrue(result['passed']);self.assertEqual([r['tokens'] for r in result['rows']],[[1,2]]*4)
        self.assertFalse(result['speed_pass']);self.assertEqual(result['qualification_sha256'],self.pin)
    def test_foreign_window_command_blocks(self):
        self.change(self.window,'command',['foreign'])
        with self.assertRaisesRegex(ValueError,'window command'):self.run_audit()
    def test_poststop_RAM_witness_required(self):
        self.change(self.meta/'post-stop-memory.json','available_bytes',87*2**30)
        with self.assertRaisesRegex(ValueError,'88GiB'):self.run_audit()
    def test_actual_FSIZE_line_is_independently_parsed(self):
        self.startup['actual_process']['native_fsize_limits_raw']='Max file size unlimited unlimited bytes';self.write(self.out/'startup-audit.json',self.startup)
        with self.assertRaisesRegex(ValueError,'FSIZE'):self.run_audit()
    def test_private_raw_transport_mutation_blocks_even_matching_native_counts(self):
        case=self.manifest['cases'][0];path=self.folder/'skip-controls'/case['id']/'response.json';row=json.loads(path.read_text())
        row['raw'][0]['line']='data: '+json.dumps({'choices':[{'delta':{'content':'WRONG'},'finish_reason':'stop'}]})+'\n';self.write(path,row)
        with self.assertRaisesRegex(ValueError,'Raw private SSE'):self.run_audit()
    def test_proof_output_or_qpin_and_missing_score_block(self):
        self.change(self.meta/'proof.json','qualification_sha256','f'*64)
        with self.assertRaises(ValueError):self.run_audit()
    def test_saved_evidence_rejects_mutation_after_bounded_snapshot(self):
        evidence=a.saved_evidence('N0');self.assertTrue(a.evidence_fingerprints(evidence))
        (self.folder/'engine.log').write_text('mutated')
        with self.assertRaises(ValueError):a.evidence_fingerprints(evidence)


class AuditOrchestration(unittest.TestCase):
    def test_bootstrap_initial_phase_guard_precedes_source_hash_import(self):
        with patch.object(runner,'early_guard',side_effect=ValueError('private busy')),patch.object(runner,'sha') as sha,patch.object(runner,'exact_module') as load:
            with self.assertRaisesRegex(ValueError,'private busy'):runner.bootstrap('a'*64)
        sha.assert_not_called();load.assert_not_called()
    def test_worker_actual_bounds_precede_bootstrap_or_evidence(self):
        events=[]
        with patch.object(runner,'early_bounds',side_effect=lambda parent:(events.append('bounds') or (_ for _ in ()).throw(ValueError('bad bounds')))),patch.object(runner,'bootstrap') as boot:
            with self.assertRaisesRegex(ValueError,'bad bounds'):runner.worker('N0','scan-0','a'*64,123)
        self.assertEqual(events,['bounds']);boot.assert_not_called()
    def parent_fixture(self,root,stack,fault=None):
        from types import SimpleNamespace as S
        e=root/'e';here=e/'decode-optimization-20261028/cpu-iq2xs-upstream623-v1/model-v1';(here/'N0').mkdir(parents=True)
        (e/'STATE.json').write_text(json.dumps({'active_cpu_build':False}));events=[];live={'lease':False}
        class Lease:
            identity={'inode':12}
            def __init__(self,*args):pass
            def __enter__(self):live['lease']=True;events.append('lease');return self
            def __exit__(self,*args):live['lease']=False;events.append('lease released')
            def check(self):
                if not live['lease']:raise AssertionError('lease not held')
        class Owned:
            def __init__(self,*args):self.rows=[]
            def starting(self,job):events.append(('starting',job))
            def registered(self,p,job):self.rows.append(p);events.append(('registered',job,p.pid))
            def cleanup_failed(self,*args):events.append('cleanup uncertain')
            def absence(self):events.append('absence');return {'passed':fault!='survivor','children':[]}
        def cas(path,before,value):
            if path.read_bytes()!=before:raise ValueError('CAS changed')
            path.write_text(json.dumps(value));events.append('claim' if value['active_cpu_build'] else 'claim released')
        def guard(*args):
            state=json.loads((e/'STATE.json').read_text());events.append('guard')
            if fault=='postguard' and 'claim released' in events:raise ValueError('postguard refusal')
            return state
        def supervise(argv,folder,on_spawn):
            job=folder.name;on_spawn(S(pid=100+len(events)))
            for name,value in [('child.json',{}),('observed.json',{}),('result.json',{'evidence':{'synthetic':{'fingerprint':{}}}})]:runner.emit(folder/name,value)
            (folder/'child.log').write_text('synthetic')
            return dict(returncode=1 if fault=='child' else 0,error='child fault' if fault=='child' else None,cleanup=[])
        d=S(supervise=supervise,checked=lambda pin:events.append('source rechecked'))
        b=S(CPULease=Lease,OwnedChildren=Owned,fresh=lambda p:None,observe_gpu_lease=lambda *a:{'identity':{'inode':3}},load_cas=lambda:S(cas_state=cas),process_ticks=lambda pid:42)
        rt=S(support=lambda:(S(ChunkProductionHost=lambda:S()),None),current_binding=lambda:{'native_pid':123})
        q={'source_review_sha256':'b'*64}
        stack.enter_context(patch.object(runner,'HERE',here));stack.enter_context(patch.object(runner,'E',e))
        stack.enter_context(patch.object(runner.sys,'platform','linux'));stack.enter_context(patch.object(runner.sys,'dont_write_bytecode',True))
        stack.enter_context(patch.object(runner,'bootstrap',return_value=(q,d,rt,b,S(guard=guard))))
        stack.enter_context(patch.object(runner,'child_chain',side_effect=lambda *args:{'passed':True,'arm':'N0'}))
        def fingerprint(evidence):
            events.append('evidence stat checked')
            if fault=='evidence' and 'claim released' in events:raise ValueError('raw evidence changed')
        stack.enter_context(patch.object(a,'evidence_fingerprints',side_effect=fingerprint))
        original=runner.emit
        def emit(path,value):
            if path.name=='terminal-audit.json':
                if not live['lease'] or json.loads((e/'STATE.json').read_text())['active_cpu_build']:raise AssertionError('publication without closed claim and held lease')
                events.append('publication')
            return original(path,value)
        stack.enter_context(patch.object(runner,'emit',side_effect=emit))
        return e,here,events
    def test_positive_parent_holds_lease_through_exact_publication(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            e,here,events=self.parent_fixture(Path(d).resolve(),stack)
            value=runner.parent('N0','a'*64);self.assertTrue(value['passed'])
            self.assertEqual(sum(isinstance(x,tuple) and x[0]=='registered' for x in events),5)
            self.assertLess(events.index('absence'),events.index('claim released'));self.assertLess(events.index('claim released'),events.index('publication'))
            self.assertLess(events.index('publication'),events.index('lease released'))
            self.assertTrue((here/'N0/terminal-audit.json').is_file())
    def test_actual_child_failure_cleans_and_releases_without_terminal(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            e,here,events=self.parent_fixture(Path(d).resolve(),stack,'child')
            with self.assertRaisesRegex(ValueError,'Audit child failed'):runner.parent('N0','a'*64)
            self.assertIn('absence',events);self.assertIn('claim released',events)
            self.assertFalse((here/'N0/terminal-audit.json').exists())
    def test_unknown_descendants_keep_claim_and_block_publication(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            e,here,events=self.parent_fixture(Path(d).resolve(),stack,'survivor')
            with self.assertRaisesRegex(ValueError,'descendants'):runner.parent('N0','a'*64)
            self.assertTrue(json.loads((e/'STATE.json').read_text())['active_cpu_build'])
            self.assertNotIn('publication',events)
    def test_postrelease_guard_or_evidence_refusal_never_publishes(self):
        from contextlib import ExitStack
        for fault in ('postguard','evidence'):
            with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
                e,here,events=self.parent_fixture(Path(d).resolve(),stack,fault)
                with self.assertRaises(ValueError):runner.parent('N0','a'*64)
                self.assertIn('claim released',events);self.assertNotIn('publication',events)
