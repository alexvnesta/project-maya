"""New caller/native-limit/actual HTTP CPU proofs; no native binary or GPU."""
import array,copy,json,pathlib,sys,tempfile,threading,time,unittest
from types import SimpleNamespace
from unittest.mock import patch
import iq2s_explore as n
import iq2s_explore_config as c
import iq2s_explore_controls as controls
import iq2s_explore_audit as audit
E=pathlib.Path(__file__).resolve().parents[3]

class CallerContracts(unittest.TestCase):
    def test_first_baseline_then_reviewed_candidate_only(self):
        n.prerequisites('X0',{})
        for arm,reg in [('X0',{'X0':{}}),('X1',{}),('X1',{'X0':{'fully_reviewed':False}}),('A1',{})]:
            with self.assertRaises(ValueError):n.prerequisites(arm,reg)
        with tempfile.TemporaryDirectory() as d,patch.object(n,'P',pathlib.Path(d).resolve()):
            path=n.P/'X0/terminal-audit.json';path.parent.mkdir()
            path.write_text(json.dumps({'passed':True,'arm':'X0','purpose':n.fixtures.PURPOSE,'prior_numerical_HOLD':True,'promotion_allowed':False}))
            row={'fully_reviewed':True,'terminal_audit':str(path),'terminal_audit_sha256':n.runtime.sha(path)}
            n.prerequisites('X1',{'X0':row})
            path.write_text('{}')
            with self.assertRaises(ValueError):n.prerequisites('X1',{'X0':row})
    def limit_config(self):
        base=json.loads((n.P/'base-config.json').read_text())
        return c.make_config(base,c.E/'results/decode-iq2s-exploratory-X0-20261029T010203Z/native','exploratory','X0')
    def test_native_guard_exact_one_launch_preserves_hook_without_FSIZE(self):
        called=[];hooks=[]
        def popen(what,args,role='engine',**kw):hooks.append(kw['preexec_fn']);called.append((what,args,role));return SimpleNamespace(pid=123)
        server=SimpleNamespace(popen=popen);cfg=self.limit_config()
        with tempfile.TemporaryDirectory() as d:
            count=n.install_native_guard(server,cfg,pathlib.Path(d).resolve())
            self.assertEqual(called,[])
            server.popen('the Strata engine',c.expected_native_argv(cfg)[:-1],preexec_fn=lambda:called.append('AFFINITY'))
            self.assertEqual(count,[123]);self.assertNotIn('FSIZE',called)
            hooks[0]();self.assertEqual(called[-1],'AFFINITY');self.assertNotIn('FSIZE',called)
            with self.assertRaises(ValueError):server.popen('the Strata engine',c.expected_native_argv(cfg)[:-1])
    def test_native_guard_rejects_foreign_role_argv_or_api_launch_before_popen(self):
        cfg=self.limit_config()
        for name,argv,role in [('API',[sys.executable],'api'),('the Strata engine',['wrong'],'engine'),('the Strata engine',c.expected_native_argv(cfg)[:-1],'api')]:
            server=SimpleNamespace(popen=lambda *a,**k:(_ for _ in ()).throw(AssertionError('must not spawn')))
            with tempfile.TemporaryDirectory() as d:
                n.install_native_guard(server,cfg,pathlib.Path(d).resolve())
                with self.assertRaises(ValueError):server.popen(name,argv,role=role)
    def test_startup_uses_current4096_and_exact_placement(self):
        for cpu,gpu in [(4045,11315),(3950,11410),(4045,11314)]:
            fake=SimpleNamespace(m=SimpleNamespace(runtime=SimpleNamespace(startup=lambda *args:{'cpu_experts':cpu,'expert_slots':gpu})))
            if (cpu,gpu)==(4045,11315):self.assertEqual(n.startup(fake,None,{}, {},{},'')['expert_slots'],11315)
            else:
                with self.assertRaises(ValueError):n.startup(fake,None,{}, {},{},'')
    def test_foreign_proof_blocks_before_qualification_window_or_gpu(self):
        with patch.object(n.runtime,'qualified',side_effect=AssertionError('must not hash')):
            with self.assertRaises(ValueError):n.window_admission(None,{},'X0',pathlib.Path('/foreign'))
    def test_launch_receipt_failure_cleans_only_new_native_preserving_primary(self):
        cfg=self.limit_config();events=[]
        class Proc:
            pid=123
            def poll(self):return None
            def terminate(self):events.append('terminate')
            def wait(self,timeout):events.append(('wait',timeout));return 0
        server=SimpleNamespace(popen=lambda *a,**k:Proc())
        with patch.object(n.runtime,'emit',side_effect=OSError('receipt failed')):
            n.install_native_guard(server,cfg,pathlib.Path('/owned'))
            with self.assertRaisesRegex(OSError,'receipt failed'):server.popen('the Strata engine',c.expected_native_argv(cfg)[:-1])
        self.assertEqual(events,['terminate',('wait',10)])
    def test_launch_receipt_primary_survives_native_cleanup_error(self):
        cfg=self.limit_config()
        class Proc:
            pid=123
            def poll(self):return None
            def terminate(self):raise RuntimeError('cleanup failed')
        server=SimpleNamespace(popen=lambda *a,**k:Proc())
        with patch.object(n.runtime,'emit',side_effect=OSError('receipt failed')):
            n.install_native_guard(server,cfg,pathlib.Path('/owned'))
            with self.assertRaisesRegex(OSError,'receipt failed') as exc:server.popen('the Strata engine',c.expected_native_argv(cfg)[:-1])
        self.assertIn('cleanup failed',exc.exception.__notes__[0])
    def test_body_primary_and_cleanup_failure_are_both_preserved(self):
        def body():raise ValueError('body failure')
        def cleanup():raise RuntimeError('cleanup failure')
        with self.assertRaisesRegex(ValueError,'body failure') as exc:n.body_and_cleanup(body,cleanup)
        self.assertIn('cleanup failure',exc.exception.__notes__[0])
        with self.assertRaisesRegex(RuntimeError,'cleanup failure'):n.body_and_cleanup(lambda:None,cleanup)
        self.assertEqual(n.body_and_cleanup(lambda:7,lambda:None),7)

class PhaseCustody(unittest.TestCase):
    def values(self):
        out=n.E/'results/decode-iq2s-exploratory-X0-20261029T010203Z';meta=n.E/'maintenance'/out.name
        selected={'mode':'exploratory','arm':'X0','output':str(out),'proof_path':str(meta/'proof.json'),'controller_pid':123,
                  'qualification_sha256':'a'*64,'status':n.runtime.statuses('exploratory','X0')['running']}
        proof={'qualified_for_owned_iq2s_model':True,'mode':'exploratory','arm':'X0','output':str(out),'qualification_sha256':'a'*64}
        current={'decode_optimization_current':selected,'maintenance_controller':str(meta/'state.json'),'active_private_phase':str(meta),'active_gpu_experiment':True}
        registry={'X0':{'attempted':True,'fully_reviewed':False,'output':str(out),'proof':str(meta/'proof.json'),'controller_pid':123}}
        return proof,current,registry,copy.deepcopy(selected),out,'X0',meta
    def test_exact_active_reserved_attempt_and_controller_proof(self):self.assertTrue(n.custody_contract(*self.values()))
    def test_foreign_missing_replaced_controller_or_attempt_rejected(self):
        for which,key,value in [(0,'arm','X1'),(0,'qualification_sha256','b'*64),(1,'active_private_phase','foreign'),(1,'maintenance_controller','foreign'),(1,'active_gpu_experiment',False),
                                 (3,'controller_pid',124),(3,'status','finished')]:
            args=list(self.values());args[which][key]=value
            with self.assertRaises(ValueError):n.custody_contract(*args)
        args=list(self.values());args[2]['X0']['attempted']=False
        with self.assertRaises(ValueError):n.custody_contract(*args)
    def test_foreign_proof_path_rejected_before_reading_file(self):
        args=self.values();out=args[4];meta=args[6]
        with patch.object(n.runtime,'owned_paths',return_value=(out,meta)),patch.object(n.runtime,'real_file',side_effect=AssertionError('must not read')):
            with self.assertRaises(ValueError):n.read_phase_proof(out,'X0','/foreign/proof.json')
    def test_current_window_exact_command_and_incomplete_ownership_required(self):
        args=self.values();out,meta=args[4],args[6]
        command=[str(n.R/'venv/bin/python3.14'),'-B',str(n.P/'iq2s_explore.py'),'--phase','--arm','X0','--output',str(out),'--proof',str(meta/'proof.json')]
        state={'command':command,'maintenance_root_window':'20261025T032914Z.json','continued_from':'prior','restored':False}
        window=n.R/'windows/20261029T010204Z.json';self.assertTrue(n.window_contract(window,state,out,'X0',meta))
        for key,value in [('command',command+['extra']),('maintenance_held',True),('test_returncode',0),('restored',True),('maintenance_root_window','other')]:
            with self.assertRaises(ValueError):n.window_contract(window,{**state,key:value},out,'X0',meta)

class AuditContracts(unittest.TestCase):
    def test_exact_two_native_traces_no_missing_extra_duplicate(self):
        audit.trace_inventory(['native-001','native-000'])
        for names in ([],['native-000'],['native-000','native-000'],['native-000','native-001','native-002']):
            with self.assertRaises(ValueError):audit.trace_inventory(names)
    def test_all_case_scores_and_typed_counts_required(self):
        result={'complete':True,'actual_native_count':2,'native_count':2,'quality_or_speed_pass':False,
            'prior_numerical_HOLD':True,'promotion_allowed':False,'unrun_ids':[],'incomplete_reason':None,'DSI1_leftovers':[],
            'rows':[{'id':name}for name in n.fixtures.IDS],
            'case_scores':[{'id':name,'status':'NATURAL_KNOWN_ANSWER_PASSED','passed':True}for name in n.fixtures.IDS]}
        audit.result_contract(result)
        for key,value in [('complete',False),('actual_native_count',True),('native_count',1),('unrun_ids',['sequence1024-warm']),
                          ('case_scores',[]),('incomplete_reason','budget'),('promotion_allowed',True)]:
            with self.assertRaises(ValueError):audit.result_contract({**result,key:value})

    def test_audit_busy_or_private_phase_defers_before_bound_or_heavy_checks(self):
        class Deferred(RuntimeError):pass
        events=[]
        class Host:
            def idle(self):events.append('idle');return False
            def guard_binding(self):events.append('bound')
        a=SimpleNamespace(ChunkProductionHost=Host,m=SimpleNamespace(runtime=SimpleNamespace(old=SimpleNamespace(AdmissionDeferred=Deferred))))
        with patch.object(audit.pathlib.Path,'read_text',return_value='{}'),patch.object(audit.runtime,'current_binding',return_value={'native_pid':123}):
            with self.assertRaises(Deferred):audit.idle_guard(a)
        self.assertEqual(events,['idle'])
        events.clear()
        with patch.object(audit.pathlib.Path,'read_text',return_value='{"active_private_phase":"other"}'):
            with self.assertRaises(Deferred):audit.idle_guard(a)
        self.assertEqual(events,[])
    def test_cleanup_requires_private_native_API_zero_and_single_close(self):
        clean={'passed':True,'server_returncode':0,'grace_timeout':False,'application_stopped':True,'native_ready_pid':123}
        close={'native_pid':123,'returncode':0,'closed':True};audit.cleanup_contract(clean,[close],123)
        for key,value in [('server_returncode',1),('grace_timeout',True),('native_ready_pid',124),('passed',False)]:
            bad={**clean,key:value}
            with self.assertRaises(ValueError):audit.cleanup_contract(bad,[close],123)
        for closes in ([],[close,close],[{**close,'returncode':-9}]):
            with self.assertRaises(ValueError):audit.cleanup_contract(clean,closes,123)
    def test_resource_floors_and_swap_delta_are_typed_and_bounded(self):
        samples=[{'root_free_bytes':140*2**30,'swap_pages':{'pswpout':1}},{'root_free_bytes':130*2**30,'swap_pages':{'pswpout':2}}]
        self.assertEqual(audit.resource_contract(samples)['system_swapout_delta_bytes'],4096)
        for bad in ([],[{'root_free_bytes':100*2**30,'swap_pages':{'pswpout':0}}],[{'root_free_bytes':True,'swap_pages':{'pswpout':0}}],
                    [samples[0],{'root_free_bytes':130*2**30,'swap_pages':{'pswpout':262145}}]):
            with self.assertRaises(ValueError):audit.resource_contract(bad)
    def test_restoration_rejects_old2048_outputloss_bad_stream_or_wrong_default(self):
        identity={'native_sha256':c.BASE_NATIVE,'config_sha256':c.BASE_SHA,'context':1048576,'output_default':262144,'prompt_skip_mode':1,'prefill_chunk':4096,
                  'Q8':[1,1],'TP':1,'images':True,'runtime_ablation':True,'CPU_experts':4045,'all_CPU_experts_RAM':True,'native_pid':123,
                  'start_binding':{'invocation':'a'*32,'main_pid':122,'native_pid':123,'native_start_ticks':100}}
        public={'unauthenticated_models':401,'authenticated_models':200,'SSE_done':True,'finish':'stop','known_answer_passed':True}
        health={'loaded':True,'max_context':1048576,'images':True,'switcher':{'active_model':'deepseek','fault':None}}
        audit.restoration_contract(identity,public,health)
        for key,value in [('prefill_chunk',2048),('output_default',32768),('context',524288),('images',False),('native_sha256',c.CANDIDATE_NATIVE)]:
            with self.assertRaises(ValueError):audit.restoration_contract({**identity,key:value},public,health)
        with self.assertRaises(ValueError):audit.restoration_contract(identity,{**public,'SSE_done':False},health)
        with self.assertRaises(ValueError):audit.restoration_contract(identity,public,{**health,'switcher':{'active_model':'qwen'}})

class ActualFullCapAPI(unittest.TestCase):
    def test_two_natural_HTTP_fullcap_short_prompts_no_dump_DSpark_and_rewind(self):
        # New natural-stop/dump-budget caller exercised on actual API sockets;
        # only the token producer is a scripted CPU MockEngine.
        support=n.fixtures.load_support();s=support.server;tok=support.tokenizer()
        import test_iq2s_explore_fixtures as ft
        m=ft.BUILT_MANIFEST
        self.assertIsNotNone(m,'Fixture encoder module must run first exactly once');seen=[];images=[]
        sys.path[:0]=[str(E/'prefill-cache-improvements-20261027'),str(E/'q8-batch-v1'),str(E/'prefill-v2')]
        from skip_controls import issue
        from protocol import Stream,json_get,wait_for
        # All loaded trace wrappers implement identical native observation; use
        # the qualified1M version explicitly for this new mode.
        spec=__import__('importlib').util.spec_from_file_location('iq2s_capacity_observer_cpu',E/'hosting-1m-output256k-v3-20261027/capacity_observer.py')
        observer=__import__('importlib').util.module_from_spec(spec);spec.loader.exec_module(observer)
        with tempfile.TemporaryDirectory() as d:
            folder=pathlib.Path(d)
            class Engine(s.MockEngine):
                def __init__(self,*a,**kw):
                    super().__init__(*a,**kw);self.proc=SimpleNamespace(pid=321);self.info={};self.can_stop=True;self.batch=0;self.last={}
                def _parse_done(self,line):return s.StrataEngine._parse_done(self,line)
                def generate(self,ids,max_new,sampling,cancel,embeddings=None):
                    index=self.turns;count=0;seen.append((max_new,bool(embeddings),list(ids)))
                    if embeddings:images.append(pathlib.Path(embeddings))
                    try:
                        for t in super().generate(ids,max_new,sampling,cancel,embeddings):count+=1;yield t
                    finally:
                        reuse=len(ids)-1 if index==1 else 0
                        self._parse_done(f'DONE {count} {len(ids)} 1.0 2.0 stop 3 5 {reuse} 0 0')
            outputs=['</think>\n\n'+json.dumps(case['expected']) for case in m['cases']]
            engine=observer.trace_class(Engine,folder)(tok,outputs,max_context=1048576)
            engine.scripts=[tok.encode(text)+[1] for text in outputs];engine.script=engine.scripts[0]
            vision=support.ds4_vision.Vision(support.ds4_vision.Geometry(),folder/'images',s.Vision.load)
            svc=s.Service(engine,tok,s.ChatTemplate(support.dsml.pick_template(E/'native-vision-v2/tokenizer/chat_template.jinja')[0]),model_name='deepseek-v4.1-flash-iq2-xs',vision=vision,fit_max_tokens=False)
            svc.set_family('deepseek41');svc.answer_room=False;svc.reasoning_budget_configured=True;svc.reasoning_budget_tokens=0;svc.reasoning_loop_recovery=False;svc.repeat_stop_tokens=0
            http=s.serve(svc,'127.0.0.1',0);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(http.server_port)
            try:
                def requester(base,body,deadline):return controls.bounded_request(base,body,deadline,folder,stream_class=Stream,observe=json_get,wait_for=wait_for)
                result=controls.run_cases(m,folder,321,time.monotonic()+60,issue=lambda case,folder,pid,deadline:issue(case,folder,pid,deadline,requester=requester,base=base))
                self.assertTrue(result['complete'],result);self.assertEqual(result['native_count'],2);self.assertFalse(result['quality_or_speed_pass'])
                self.assertEqual([x[0] for x in seen],[32768]*2);self.assertEqual([x[1] for x in seen],[False,False])
                self.assertEqual([x[2] for x in seen],[case['prompt_ids'] for case in m['cases']])
                self.assertFalse(list(folder.glob('logits*')));self.assertEqual(images,[]);self.assertNotIn('torch',sys.modules)
                self.assertTrue(result['prior_numerical_HOLD']);self.assertFalse(result['promotion_allowed'])
            finally:http.shutdown();http.server_close();thread.join(2);vision.shutdown()

if __name__=='__main__':unittest.main()
