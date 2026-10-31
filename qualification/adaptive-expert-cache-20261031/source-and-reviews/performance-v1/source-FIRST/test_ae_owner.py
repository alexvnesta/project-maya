"""Fresh nine-request cache-policy owner controls; all process/service boundaries are synthetic."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import ae_owner as c
f = c.runtime.original_module('ms_fixtures')
r, config = c.runtime, c.config
q = c
SOURCE = r.original_model_dir / 'prose-fixtures-A.json'
BASE = f.E / 'decode-optimization-20261028/model-v1/base-config.json'


def cases(which='B'):
    return copy.deepcopy(json.loads(r.encoded_path('prose',which).read_text())['cases'])


def sample(): return cases()[0]


def answer(case=None):
    case=case or sample()
    response={'status':200,'done':True,'cancelled':False,'finish_reason':'stop',
              'content':json.dumps(case.get('expected')),'reasoning':'synthetic only'}
    if case['kind']=='prose':response['content']='Synthetic. '+case['expected_last_sentence']
    if case['kind']=='tool':response.update(f.synthetic_call('actual-call-731'));response['content']=''
    if case['kind']=='literal':response['content']=case['expected']
    reuse=case['prompt_tokens']-1 if case.get('expected_reuse')=='prompt-minus-one' else 0
    proof={'observed_tokens':7,'prompt_tokens':case['prompt_tokens'],'client_full_s':.02,
           'native':{'generated':7,'prompt_tokens':case['prompt_tokens'],'finish':'stop','reused':reuse,
                     'drafts_offered':3,'drafts_accepted':2,'prompt_ms':1.0,'decode_ms':2.0}}
    return response,proof


class Manifest(unittest.TestCase):
    def test_identical_selected_composite_both_policies_without_encoding(self):
        with patch.object(f,'load_support',side_effect=AssertionError('No encoding')):
            a=c.manifest('prose','A1');b=c.manifest('prose','B1')
        self.assertEqual(a,b)
        self.assertEqual([x['prompt_tokens'] for x in a['cases']],[8469,8469,8656,8469,169])
        self.assertEqual([x['prompt_tokens'] for x in a['lifecycle_cases']],[372,465,8471,44])
        quality,prose=r.source_manifests()
        for actual,original in zip(a['cases'],quality['cases']+[prose['cases'][2]]):
            self.assertEqual(actual['request'],original['request']);self.assertEqual(actual['prompt_ids'],original['prompt_ids'])
            self.assertEqual(actual['source_case_id'],original['id'])
        self.assertEqual(a['lifecycle_cases'][1]['dependency'],'ae-prose-tool')

    def test_source_bytes_changed_refused(self):
        with patch.object(r,'sha',return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'entire selected source'):r.source_manifests()

    def test_changed_requests_ids_or_metadata_refused(self):
        original=c.manifest('prose','A1')
        for field in ('cases','lifecycle_cases'):
            bad=copy.deepcopy(original);bad[field][0]['prompt_ids'][0]+=1
            with self.subTest(field=field),self.assertRaises(ValueError):r.validate_manifest(bad)
        for field,value in [('context',262144),('tool_call_ID_normalization_CPU_proved',False),
                            ('same_selected_pack_drafter_tokenizer',False),('expected_reuse_tokens',[0]*5)]:
            bad=copy.deepcopy(original);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):r.validate_manifest(bad)

    def test_source_tokenizer_or_template_difference_blocks_composition(self):
        quality,prose=r.source_manifests()
        for key in ('tokenizer_source_sha256','effective_template','policy','pack_relative_to_E'):
            bad=copy.deepcopy(prose);bad[key]='foreign'
            with self.subTest(key=key),self.assertRaises(ValueError):r.compose_manifest(quality,bad)

    def test_dependency_id_or_callbody_change_refused(self):
        for which in ('dependency','request'):
            bad=copy.deepcopy(c.manifest('prose','B1'))
            if which=='dependency':bad['lifecycle_cases'][1]['dependency']='old-family'
            else:bad['lifecycle_cases'][1]['request']['messages'][-1]['tool_call_id']='changed'
            with self.subTest(which=which),self.assertRaises(ValueError):r.validate_manifest(bad)

    def test_wrong_mode_arm_rejected_before_manifest(self):
        with patch.object(r,'performance_manifest') as read:
            for mode,arm in [('quality','QS1'),('longcold','LC1'),('prose','B3'),('coding','A1')]:
                with self.assertRaises(ValueError):c.manifest(mode,arm)
        read.assert_not_called()

    def test_no_native_dump_or_fsize_hook_fullpolicy(self):
        base=json.loads(BASE.read_text())
        for arm in ('A1','B1'):
            folder=config.E/('results/adaptive-cache-prose-v1-'+arm+'-20261030T180000Z/native')
            value=config.make_config(base,folder,'prose',arm)
            self.assertNotIn('DS4_SERVE_DUMP',value['env']);self.assertEqual(value['hosted_default_effort'],100)
            self.assertNotIn('max_tokens',value);self.assertFalse(hasattr(c,'install_dump_limit'))


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name).resolve();self.out=self.p/'output'
        self.old=types.SimpleNamespace(q8_phase=types.SimpleNamespace(admission=Mock(return_value='window')))
        self.patchers=[patch.object(c,'helpers',return_value=(object(),self.old,object(),object(),object(),object(),object())),
                      patch.object(c,'read_proof',return_value={'qualification_sha256':'a'*64}),
                      patch.object(r,'qualified',return_value={}),patch.object(c,'window_contract'),
                      patch.object(c,'manifest',return_value={'cases':[sample()]})]
        for x in self.patchers:x.start();self.addCleanup(x.stop)

    def test_fence_wraps_body_and_restores_before_terminal_receipt(self):
        events=[]
        class Fence:
            def __enter__(self):events.append('install');return {},[]
            def __exit__(self,*a):events.append('restore')
        emit=r.emit
        def write(path,value):events.append('receipt');emit(path,value)
        with patch.object(c.controls,'fenced_phase',return_value=Fence()), \
             patch.object(c,'phase_body',side_effect=lambda *a:(events.append('body') or {'passed':True})), \
             patch.object(r,'emit',side_effect=write):
            self.assertEqual(c.phase(self.out,'prose','A1','unused'),0)
        self.assertEqual(events,['install','body','restore','receipt'])

    def test_failed_fence_restoration_never_publishes_terminal_success(self):
        class Fence:
            def __enter__(self):return {},[]
            def __exit__(self,*a):raise RuntimeError('restore failure')
        with patch.object(c.controls,'fenced_phase',return_value=Fence()),patch.object(c,'phase_body',return_value={}):
            with self.assertRaisesRegex(RuntimeError,'restore failure'):c.phase(self.out,'prose','A1','unused')
        self.assertFalse((self.out/'receipt.json').exists())

    def test_fence_install_failure_blocks_body(self):
        with patch.object(c.controls,'fenced_phase',side_effect=RuntimeError('fence')),patch.object(c,'phase_body') as body:
            with self.assertRaises(RuntimeError):c.phase(self.out,'prose','A1','unused')
        body.assert_not_called()

    def test_foreign_mode_blocks_before_support(self):
        with self.assertRaises(ValueError):c.phase(self.out,'quality','QS0','unused')
        c.helpers.assert_not_called()

    def test_existing_output_blocks_replay(self):
        self.out.mkdir()
        with patch.object(c.controls,'fenced_phase') as fence:
            with self.assertRaises(FileExistsError):c.phase(self.out,'prose','A1','unused')
        fence.assert_not_called()

class Custody(unittest.TestCase):
    def test_exact_window_entry_and_no_completed_or_foreign_window(self):
        output=r.E/'results/adaptive-cache-prose-v1-A1-20261030T180000Z';proof=r.E/'maintenance'/output.name/'proof.json'
        command=[str(c.R/'venv/bin/python3.14'),'-B',str(c.P/'ae_owner.py'),'--phase','--mode','prose',
                 '--arm','A1','--output',str(output),'--proof',str(proof)]
        value={'command':command,'continued_from':'last-clean','test_returncode':None,'maintenance_held':False,'restored':False}
        old=types.SimpleNamespace(owned_window=Mock(return_value=(c.R/'windows/new.json',value)))
        c.window_contract(old,output,'prose','A1',proof)
        for change in [{'test_returncode':0},{'restored':True},{'command':command[:2]+['ms_quality.py']+command[3:]}]:
            old.owned_window.return_value=(c.R/'windows/new.json',{**value,**change})
            with self.assertRaises(ValueError):c.window_contract(old,output,'prose','A1',proof)

    def test_registry_reserves_baseline_once(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c,'P',Path(d).resolve()),patch.object(r,'P',Path(d).resolve()):
            p=Path(d).resolve()/'prose-arms.json';p.write_text('{}')
            c.reserve('prose','A1','owned-output','owned-proof');value=json.loads(p.read_text())
            self.assertEqual(list(value),['A1']);self.assertFalse(value['A1']['accepted'])
            with self.assertRaises(ValueError):c.reserve('prose','A1','owned-output','owned-proof')
            self.assertEqual(json.loads(p.read_text()),value)

    def test_quality_requires_current_entry_and_CPU_membership(self):
        with tempfile.TemporaryDirectory() as d, patch.object(r,'P',Path(d).resolve()):
            p=Path(d).resolve(); path=p/'prose-qualification.json'; pin='a'*64
            names=('ae_config.py','ae_runtime.py','ae_controls.py','ae_owner.py','ae_audit.py','ae_dispatch.py')
            sources={n:'e'*64 for n in names}; files={str(p/n):v for n,v in sources.items()}
            files.update({str(r.E/k):v for k,v in r.PINS.items()})
            files.update({str(r.R/'window.py'):'170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f',
                          str(r.D/'config.json'):config.BASE_SHA,str(r.D/'bin/maya-ds4'):config.BASE_NATIVE})
            q={'mode':'prose','root_manual_review':True,'astra_manual_review':True,
               'authorization_sha256':'c0abfa664a6e08a6893e3cb607c805ddf93eb5318bddbb8a8d3ff541a7ddf0c0',
               'context':1048576,'output_allowance':262144,'files':files,
               'CPU_groups':[{'source_sha256':sources,'proofs':{}}], 'pack_and_resource_prerequisite_reviewed':True,
               'private_memory_max':r.MEMORY_MAX,'host_margin':r.HOST_MARGIN}
            files[str(p.parent/'AUTHORIZATION.json')]=q['authorization_sha256']
            # Existing proof/pack contracts have separate real controls; isolate the new entry selector here.
            with patch.object(r,'sha',side_effect=lambda x:pin if Path(x)==path else files.get(str(x),'e'*64)), \
                 patch.object(r,'cpu_membership'),patch.object(r,'closed_cs1'),patch.object(r,'closed_lc1'),patch.object(r,'closed_quality'),patch.object(r,'STORAGE_PINS',{}),patch.object(r,'pack_custody'),patch.object(r,'encoded_custody'):
                path.write_text(json.dumps(q)); self.assertEqual(r.qualified('prose',pin)['mode'],'prose')
                for missing in ('file','CPU','authorization'):
                    bad=copy.deepcopy(q)
                    if missing=='file':bad['files'].pop(str(p/'ae_owner.py'))
                    elif missing=='CPU':bad['CPU_groups'][0]['source_sha256'].pop('ae_owner.py')
                    else:bad['files'].pop(str(p.parent/'AUTHORIZATION.json'))
                    path.write_text(json.dumps(bad))
                    with self.subTest(missing=missing),self.assertRaisesRegex(ValueError,'Executing changed source|New cache authorization'):
                        r.qualified('prose',pin)

    def test_full_phase_proof_requires_same_owned_controller(self):
        with tempfile.TemporaryDirectory() as d:
            e=Path(d).resolve();p=e/'mode';p.mkdir();(e/'results').mkdir();(e/'maintenance').mkdir()
            output=e/'results/adaptive-cache-prose-v1-A1-20261030T180000Z';meta=e/'maintenance'/output.name;meta.mkdir()
            proof={'mode':'prose','arm':'A1','output':str(output),'qualification_sha256':'a'*64,
                   'qualified_for_owned_adaptive_cache':True}
            state={**proof,'status':r.statuses('prose')['running'],'controller_pid':99}
            active={'decode_optimization_current':state,'active_private_phase':str(meta),'active_gpu_experiment':True,
                    'maintenance_controller':str(meta/'state.json')}
            registry={'A1':{'attempted':True,'output':str(output),'controller_pid':99}}
            for path,value in [(meta/'proof.json',proof),(meta/'state.json',state),(e/'STATE.json',active),(p/'prose-arms.json',registry)]:
                path.write_text(json.dumps(value))
            with patch.object(c,'E',e),patch.object(c,'P',p),patch.object(r,'E',e),patch.object(r,'P',p):
                self.assertEqual(c.read_proof(output,'prose','A1',meta/'proof.json'),proof)
                active['decode_optimization_current']['controller_pid']=100;(e/'STATE.json').write_text(json.dumps(active))
                with self.assertRaises(ValueError):c.read_proof(output,'prose','A1',meta/'proof.json')

class Body(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.e=Path(self.tmp.name).resolve();self.out=self.e/'results/adaptive-cache-prose-v1-A1-20261030T180000Z'
        self.folder=self.out/'native';self.folder.mkdir(parents=True);(self.folder/'tmp').mkdir()
        self.d=self.e/'selected';self.d.mkdir();(self.d/'config.json').write_bytes(BASE.read_bytes())
        (self.d/'profile-seed.bin').write_bytes(b'synthetic seed')
        (self.folder/'engine.log').write_text('synthetic startup and exact skip5801,5988\n')
        self.proc=types.SimpleNamespace(pid=71);self.processes=[];self.issued=0;self.requests=cases('A')
        self.m=json.loads(r.encoded_path('prose','A').read_text());self.cancelled=0
        self.cancellation=types.SimpleNamespace(prefill_cancel=Mock(side_effect=self.cancel),reconcile=Mock(side_effect=self.reconcile_cancel))
        def body_cleanup(body,cleanup):
            try:return body()
            finally:cleanup()
        self.old=types.SimpleNamespace(
            q8_phase=types.SimpleNamespace(SEED_SHA=r.sha(self.d/'profile-seed.bin'),environment=Mock(return_value={}),
                wait_startup=Mock(return_value=({'pid':72},{'ok':True},{'data':[]})),
                native_paths=lambda path:sorted(Path(path).glob('native-[0-9][0-9][0-9]')),BASE='http://127.0.0.1:18041',await_trace=Mock()),
            body_and_cleanup=body_cleanup,stop_server=Mock())
        self.bounded=Mock()
        def issue(case,folder,pid,deadline,*,requester):
            self.assertEqual(pid,72);self.assertEqual(deadline,1100);self.issued+=1
            response,proof=answer(case);self.bounded.return_value=response
            actual=requester('private-test',case['request'],deadline)
            trace=Path(folder)/('native-%03d'%self.issued);trace.mkdir()
            (trace/'tokens.jsonl').write_text(''.join(json.dumps({'token':i,'seconds':i*.001})+'\n' for i in range(7)))
            return actual,proof
        self.skip=types.SimpleNamespace(issue=Mock(side_effect=issue),ControlBudgetStop=type('Stop',(Exception,),{}),
            activation=Mock(return_value={'activation_early_rows':[5801,5988,5803]}))
        self.protocol=types.SimpleNamespace(Stream=Mock(),json_get=Mock(),wait_for=Mock())
        self.numerical=types.SimpleNamespace(dump_snapshot=Mock(return_value={'status':'COMPLETE_SIZE_ONLY'}),
            dump_size=Mock(return_value={'bytes':517120,'rows':1}),owned_storage_snapshot=Mock())
        self.storage=types.SimpleNamespace(HARD_FILE_BYTES=512*2**20)
        original_read=Path.read_text
        def read(path,*args,**kwargs):
            if str(path)=='/proc/72/limits':return 'Max file size             unlimited            unlimited            bytes\n'
            return original_read(path,*args,**kwargs)
        patches=[patch.object(c,'P',self.d),patch.object(c,'D',self.d),patch.object(config,'E',self.e),
            patch.object(c.time,'monotonic',return_value=101),patch.object(c.subprocess,'Popen',return_value=self.proc),
            patch.object(c.controls,'startup',return_value={}),patch.object(c.controls,'actual_native',return_value={'native_pid':72}),
            patch.object(c.controls,'fence_terminal',return_value={'passed':True}),
            patch.object(c.controls,'bounded_request',self.bounded),patch.object(Path,'read_text',read),
            patch.object(r,'lifecycle_helper',return_value=self.cancellation),
            patch.dict(c.sys.modules,{'skip_controls':self.skip,'protocol':self.protocol})]
        for p in patches:p.start();self.addCleanup(p.stop)

    def call(self):
        return c.phase_body(self.out,'prose','A1',{}, {'allowed_automatic_cuts':{'A':[19]}},
            'window',self.m,self.folder,{},self.processes,100,
            object(),self.old,self.numerical,self.storage)

    def cancel(self,base,body,deadline,log,mode,**observations):
        self.assertEqual(deadline,1100);self.issued+=1;self.cancelled+=1
        trace=self.folder/('native-%03d'%self.issued);trace.mkdir();(trace/'tokens.jsonl').write_text('')
        return {'passed':True,'classification':'confirmed_prefill_cancel','replay':False,'recovery_required':True,
                'client_disconnect_cancels_delta':1,'observed_before_cancel':{'state':'reading','read':4096,'total':8471,'first_delta':False},
                'transport':{'cancelled':True,'content':'','reasoning':'','tool_calls':[]}}

    def reconcile_cancel(self,trace,case,response,pid,*,cancelled):
        self.assertEqual(pid,72);self.assertTrue(cancelled);self.assertEqual(case['prompt_tokens'],8471)
        return {'native':{'generated':0,'finish':'cancel'},'observed_tokens':0,'cancelled_control_or_budget':True}

    def test_full_actual_owner_path_nine_requests_same_clock_no_dump_cleanup(self):
        result=self.call();panel=result['arm_results'];self.assertTrue(panel['complete'])
        self.assertEqual(panel['native_request_count'],9);self.assertEqual(len(panel['rows']),5)
        self.assertEqual(len(panel['lifecycle']['rows']),4);self.assertEqual(self.skip.issue.call_count,8)
        self.assertEqual(self.cancelled,1);self.assertEqual(self.processes,[self.proc])
        self.old.stop_server.assert_called_once_with(self.proc,self.folder,timeout=100)
        self.numerical.dump_snapshot.assert_not_called();self.numerical.dump_size.assert_not_called()
        self.assertTrue(all(call.args[4] is False for call in self.bounded.call_args_list))
        self.assertTrue(all(call.args[1]['max_tokens']==32768 and call.args[1]['reasoning_effort']==100 for call in self.bounded.call_args_list))
        cfg=json.loads((self.out/'candidate-config.json').read_text());self.assertNotIn('DS4_SERVE_DUMP',cfg['env'])
        self.assertEqual(json.loads((self.out/'candidate-config.shared-settings.json').read_text()),{'max_tokens':262144})
        self.assertIn(str(c.P/'ae_owner.py'),c.subprocess.Popen.call_args.args[0])
        self.assertEqual((self.out/'profile-seed-at-start.bin').read_bytes(),b'synthetic seed')
        (self.folder/'expert-profile.bin').write_bytes(b'learned private profile')
        self.assertEqual((self.out/'profile-seed-at-start.bin').read_bytes(),b'synthetic seed')
        follow=json.loads((self.folder/'skip-controls/ae-prose-prefill-cancel/request.json').read_text())
        self.assertEqual(follow,self.m['lifecycle_cases'][2]['request'])

    def test_changed_initial_seed_blocks_before_API_launch(self):
        (self.d/'profile-seed.bin').write_bytes(b'changed seed')
        with self.assertRaisesRegex(ValueError,'Immutable arm seed'):self.call()
        c.subprocess.Popen.assert_not_called();self.assertEqual(self.processes,[])

    def test_corrupt_initial_snapshot_blocks_before_API_launch(self):
        original=c.shutil.copyfile
        def copied(source,target):
            result=original(source,target)
            if Path(target).name=='profile-seed-at-start.bin':Path(target).write_bytes(b'corrupt snapshot')
            return result
        with patch.object(c.shutil,'copyfile',side_effect=copied),self.assertRaisesRegex(ValueError,'Initial seed snapshot'):
            self.call()
        c.subprocess.Popen.assert_not_called();self.assertEqual(self.processes,[])

    def test_prefill_cancel_unstarted_leaves_recovery_unrun(self):
        self.cancellation.prefill_cancel.side_effect=None
        self.cancellation.prefill_cancel.return_value={'passed':False,'budget_not_started':True,'replay':False}
        self.skip.activation.return_value={'activation_early_rows':[5801,5988]}
        result=self.call()['arm_results'];self.assertFalse(result['complete']);self.assertEqual(self.skip.issue.call_count,7)
        self.assertEqual(result['native_request_count'],7);self.assertIn('ae-prose-prefill-recovery',result['unrun_ids'])
        self.old.stop_server.assert_called_once()

    def test_prefill_after_decode_rejected_and_cleanup_once(self):
        self.cancellation.reconcile.return_value=None
        self.cancellation.reconcile.side_effect=lambda *a,**kw:{'native':{'generated':1,'finish':'stop'},'observed_tokens':0,'cancelled_control_or_budget':True}
        with self.assertRaises(ValueError):self.call()
        self.old.stop_server.assert_called_once();self.assertEqual(self.skip.issue.call_count,7)

    def test_timed_native_unexpected_fsize_blocks_before_requests(self):
        original=Path.read_text
        def read(path,*a,**kw):
            if str(path)=='/proc/72/limits':return 'Max file size 536870912 536870912 bytes\n'
            return original(path,*a,**kw)
        with patch.object(Path,'read_text',read),self.assertRaisesRegex(ValueError,'FSIZE'):self.call()
        self.skip.issue.assert_not_called();self.old.stop_server.assert_called_once()

    def test_extra_native_trace_blocks_and_cleans_once(self):
        original=self.skip.issue.side_effect
        def extra(*args,**kwargs):
            value=original(*args,**kwargs);(self.folder/'native-099').mkdir();return value
        self.skip.issue.side_effect=extra
        with self.assertRaisesRegex(ValueError,'Exactly one trace'):self.call()
        self.old.stop_server.assert_called_once();self.skip.issue.assert_called_once()

    def test_first_receipt_fault_still_closes_captured_API(self):
        emit=r.emit
        def fault(path,value):
            if Path(path).name=='server-start.json':raise RuntimeError('first receipt')
            return emit(path,value)
        with patch.object(r,'emit',side_effect=fault):
            with self.assertRaisesRegex(RuntimeError,'first receipt'):self.call()
        self.assertEqual(self.processes,[self.proc]);self.old.stop_server.assert_called_once();self.skip.issue.assert_not_called()

    def test_wrong_image_skip_state_blocks_and_closes(self):
        self.skip.activation.return_value={'activation_early_rows':[5801,5802]}
        with self.assertRaisesRegex(ValueError,'skip state'):self.call()
        self.old.stop_server.assert_called_once()

    def test_startup_timeout_has_no_new_clock_or_requests(self):
        self.old.q8_phase.wait_startup.side_effect=TimeoutError('startup')
        with self.assertRaises(TimeoutError):self.call()
        self.assertEqual(self.old.q8_phase.wait_startup.call_args.args[-1],900)
        self.old.stop_server.assert_called_once();self.skip.issue.assert_not_called()

    def test_partial_issue_holds_remaining_cases_without_retry(self):
        original=self.skip.issue.side_effect
        def partial(*args,**kwargs):
            result=original(*args,**kwargs);result[0]['done']=False;return result
        self.skip.issue.side_effect=partial;self.skip.activation.return_value={'activation_early_rows':[5801]}
        result=self.call()['arm_results']
        self.assertFalse(result['complete']);self.assertEqual(self.skip.issue.call_count,1)
        self.assertEqual(len(result['unrun_ids']),8);self.old.stop_server.assert_called_once()


if __name__=='__main__':unittest.main()
