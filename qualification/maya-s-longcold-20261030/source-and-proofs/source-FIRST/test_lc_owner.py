"""LC1 contracts and scripted ownership boundaries. No native/service/model execution."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import lc_owner as c
f = c.runtime.original_module('ms_fixtures')

r, config = c.runtime, c.config
SOURCE = r.original_model_dir / 'quality-fixtures-B.json'
BASE = f.E / 'decode-optimization-20261028/model-v1/base-config.json'


def sample():
    case = copy.deepcopy(json.loads(SOURCE.read_text())['cases'][0])
    case.update(id=r.LONG_CASE_ID)
    return case


def answer():
    response = {'status': 200, 'done': True, 'cancelled': False, 'finish_reason': 'stop',
                'content': json.dumps({'values':list(range(1,65))}), 'reasoning': 'synthetic only'}
    proof = {'observed_tokens': 7, 'prompt_tokens': 8469, 'client_full_s': .02,
             'native': {'generated': 7, 'finish': 'stop', 'reused': 0, 'drafts_offered': 3,
                        'drafts_accepted': 2, 'prompt_ms': 1.0, 'decode_ms': 2.0}}
    return response, proof


class Manifest(unittest.TestCase):
    def test_exact_already_encoded_candidate_slice_without_encoding(self):
        original = SOURCE.read_bytes()
        with patch.object(f, 'load_support', side_effect=AssertionError('No encoding')):
            m = c.manifest('longcold', 'LC1')
        self.assertEqual(SOURCE.read_bytes(), original)
        self.assertEqual(m['cases'], [sample()]); self.assertEqual(m['context'], 1048576)
        self.assertEqual(m['default_output'], 262144); self.assertTrue(m['derived_without_reencoding'])
        self.assertFalse(m['quality_or_performance_pass']); self.assertFalse(m['automatic_next_arm'])

    def test_changed_source_bytes_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve(); (p/'quality-fixtures-B.json').write_bytes(SOURCE.read_bytes()+b' ')
            with patch.object(r,'original_model_dir',p), patch.object(r,'original_module',return_value=f), self.assertRaisesRegex(ValueError,'artifact'):
                r.longcold_manifest()

    def test_changed_actual_ids_refused_even_with_repointed_test_pin(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve(); m=json.loads(SOURCE.read_text()); m['cases'][0]['prompt_ids'][0]+=1
            target=p/'quality-fixtures-B.json'; target.write_text(json.dumps(m))
            with patch.object(r,'original_model_dir',p), patch.object(r,'original_module',return_value=f), patch.object(r,'LONG_SOURCE_SHA',r.sha(target)):
                with self.assertRaises(ValueError): r.longcold_manifest()

    def test_other_arms_and_modes_refused_before_manifest(self):
        with patch.object(r,'longcold_manifest') as read:
            for mode,arm in [('quality','QS1'),('longcold','QS1'),('prose','B1')]:
                with self.assertRaises(ValueError): c.manifest(mode,arm)
        read.assert_not_called()

    def test_exact_tokenizer_and_template_membership_required(self):
        m=json.loads(SOURCE.read_text()); directory=f.CANDIDATE_PACK/'tokenizer'
        files={str(SOURCE):r.sha(SOURCE),**{str(directory/k):v for k,v in m['tokenizer_source_sha256'].items()}}
        with patch.object(f,'tokenizer_directory',return_value=directory):
            r.encoded_custody({'files':files},'longcold')
            for key in list(files):
                missing=dict(files);missing.pop(key)
                with self.subTest(key=key),self.assertRaises(ValueError):
                    r.encoded_custody({'files':missing},'longcold')

    def test_full_policy_selected_native_candidate_pack_no_dump(self):
        base=json.loads(BASE.read_text()); before=copy.deepcopy(base)
        path=config.E/'results/maya-s-longcold-LC1-20261030T180000Z/native'
        value=config.make_config(base,path,'longcold','LC1')
        self.assertTrue(config.check_config(base,value,path,'longcold','LC1'))
        self.assertEqual(config.factor('longcold','LC1')['native_sha256'],config.BASE_NATIVE)
        self.assertEqual(value['args'][value['args'].index('--pack')+1],str(config.CANDIDATE_PACK))
        self.assertEqual(value['args'][value['args'].index('--max-context')+1],'1048576')
        self.assertEqual(value['hosted_default_effort'],100);self.assertEqual(base,before)
        self.assertNotIn('DS4_SERVE_DUMP',value['env']);self.assertNotIn('max_tokens',value)
        self.assertEqual(value['tokenizer'],str(config.CANDIDATE_PACK/'tokenizer'))
        for field,changed in [('hosted_default_effort',100.0),('exe','new-engine'),('tokenizer',base['tokenizer'])]:
            wrong=copy.deepcopy(value);wrong[field]=changed
            with self.assertRaises(ValueError):config.check_config(base,wrong,path,'longcold','LC1')
        wrong=copy.deepcopy(value);wrong['env']['DS4_SERVE_DUMP']='dump'
        with self.assertRaises(ValueError):config.check_config(base,wrong,path,'longcold','LC1')

    def test_longcold_is_one_shot_without_quality_or_timing_advancement(self):
        with tempfile.TemporaryDirectory() as d, patch.object(r,'P',Path(d).resolve()):
            r.prerequisite('longcold','LC1',{})
            with self.assertRaises(ValueError):r.prerequisite('longcold','LC1',{'LC1':{'attempted':True}})
            with self.assertRaises(ValueError):r.prerequisite('prose','A1',{})
            with self.assertRaises(ValueError):r.prerequisite('longcold','CS2',{})


class OneRequest(unittest.TestCase):
    def test_one_natural_exact_JSON_positive_drafts_without_full_quality_or_speed_claim(self):
        issue=Mock(return_value=answer()); progress=[]
        result=c.run_one(sample(),Path('/unused'),71,1000,issue=issue,
                         save_progress=lambda x:progress.append(copy.deepcopy(x)))
        issue.assert_called_once(); self.assertTrue(result['complete']); self.assertFalse(result['retry'])
        self.assertFalse(result['automatic_next_arm']);self.assertFalse(result['quality_or_performance_pass'])
        self.assertEqual(result['rows'][0]['native']['drafts_offered'],3)
        self.assertEqual(progress[0]['scores'][0]['status'],'UNRUN')

    def test_wrong_JSON_is_incomplete_without_second_issue(self):
        response,proof=answer();response['content']='other'
        issue=Mock(return_value=(response,proof));result=c.run_one(sample(),'.',71,1000,issue=issue)
        self.assertFalse(result['complete']);self.assertEqual(result['scores'][0]['status'],'INCOMPLETE_HOLD')
        issue.assert_called_once()

    def test_cap_partial_error_and_missing_DONE_cannot_pass(self):
        for change in [{'done':False},{'finish_reason':'length'},{'status':500},{'cancelled':True},
                       {'intentional_budget_stop':True},{'budget_not_started':True}]:
            response,proof=answer();response.update(change);issue=Mock(return_value=(response,proof))
            with self.subTest(change=change):self.assertFalse(c.run_one(sample(),'.',71,1000,issue=issue)['complete'])
            issue.assert_called_once()

    def test_native_count_reuse_and_draft_contradictions_refused(self):
        for key,value in [('generated',8),('reused',1),('drafts_offered',True),('drafts_accepted',4),('decode_ms',float('nan'))]:
            response,proof=answer();proof['native'][key]=value;issue=Mock(return_value=(response,proof))
            with self.subTest(key=key):
                try: result=c.run_one(sample(),'.',71,1000,issue=issue)
                except ValueError: pass
                else:self.assertFalse(result['complete'])
            issue.assert_called_once()

    def test_wrong_actual_prompt_count_refused(self):
        response,proof=answer();proof['prompt_tokens']=8468
        with self.assertRaisesRegex(ValueError,'prompt'):
            c.run_one(sample(),'.',71,1000,issue=Mock(return_value=(response,proof)))

    def test_native_or_transport_fault_retained_no_retry(self):
        issue=Mock(side_effect=RuntimeError('native failure'));progress=[]
        with self.assertRaisesRegex(RuntimeError,'native failure'):
            c.run_one(sample(),'.',71,1000,issue=issue,save_progress=lambda x:progress.append(copy.deepcopy(x)))
        issue.assert_called_once();self.assertEqual(progress[-1]['scores'][0]['status'],'FAULT_HOLD')

    def test_progress_fault_cannot_hide_primary(self):
        saved=Mock(side_effect=[None,None,RuntimeError('write')]);issue=Mock(side_effect=RuntimeError('primary'))
        with self.assertRaisesRegex(RuntimeError,'primary') as caught:c.run_one(sample(),'.',71,1000,issue=issue,save_progress=saved)
        self.assertIn('write',str(caught.exception.__notes__))

    def test_foreign_case_refused_before_issue(self):
        for key,value in [('id','ms-quality-cold-text'),('expected','other'),('prompt_ids',[0]*8469)]:
            case=sample();case[key]=value;issue=Mock()
            with self.assertRaises(ValueError):c.run_one(case,'.',71,1000,issue=issue)
            issue.assert_not_called()
        case=sample();case['request']['max_tokens']=64;issue=Mock()
        with self.assertRaises(ValueError):c.run_one(case,'.',71,1000,issue=issue)
        issue.assert_not_called()

    def test_budget_incomplete_retained(self):
        issue=Mock(side_effect=c.controls.Incomplete('UNRUN before unchanged soft deadline'))
        result=c.run_one(sample(),'.',71,1000,issue=issue)
        self.assertFalse(result['complete']);self.assertFalse(result['retry']);issue.assert_called_once()


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
            self.assertEqual(c.phase(self.out,'longcold','LC1','unused'),0)
        self.assertEqual(events,['install','body','restore','receipt'])

    def test_failed_fence_restoration_never_publishes_terminal_success(self):
        class Fence:
            def __enter__(self):return {},[]
            def __exit__(self,*a):raise RuntimeError('restore failure')
        with patch.object(c.controls,'fenced_phase',return_value=Fence()),patch.object(c,'phase_body',return_value={}):
            with self.assertRaisesRegex(RuntimeError,'restore failure'):c.phase(self.out,'longcold','LC1','unused')
        self.assertFalse((self.out/'receipt.json').exists())

    def test_fence_install_failure_blocks_body(self):
        with patch.object(c.controls,'fenced_phase',side_effect=RuntimeError('fence')),patch.object(c,'phase_body') as body:
            with self.assertRaises(RuntimeError):c.phase(self.out,'longcold','LC1','unused')
        body.assert_not_called()

    def test_foreign_mode_blocks_before_support(self):
        with self.assertRaises(ValueError):c.phase(self.out,'quality','QS1','unused')
        c.helpers.assert_not_called()

    def test_existing_output_blocks_replay(self):
        self.out.mkdir()
        with patch.object(c.controls,'fenced_phase') as fence:
            with self.assertRaises(FileExistsError):c.phase(self.out,'longcold','LC1','unused')
        fence.assert_not_called()


class Custody(unittest.TestCase):
    def test_exact_window_entry_and_no_completed_or_foreign_window(self):
        output=r.E/'results/maya-s-longcold-LC1-20261030T180000Z';proof=r.E/'maintenance'/output.name/'proof.json'
        command=[str(c.R/'venv/bin/python3.14'),'-B',str(c.P/'lc_owner.py'),'--phase','--mode','longcold',
                 '--arm','LC1','--output',str(output),'--proof',str(proof)]
        value={'command':command,'continued_from':'last-clean','test_returncode':None,'maintenance_held':False,'restored':False}
        old=types.SimpleNamespace(owned_window=Mock(return_value=(c.R/'windows/new.json',value)))
        c.window_contract(old,output,'longcold','LC1',proof)
        for change in [{'test_returncode':0},{'restored':True},{'command':command[:2]+['ms_quality.py']+command[3:]}]:
            old.owned_window.return_value=(c.R/'windows/new.json',{**value,**change})
            with self.assertRaises(ValueError):c.window_contract(old,output,'longcold','LC1',proof)

    def test_registry_reserves_only_LC1_once(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c,'P',Path(d).resolve()),patch.object(r,'P',Path(d).resolve()):
            p=Path(d).resolve()/'longcold-arms.json';p.write_text('{}')
            c.reserve('longcold','LC1','owned-output','owned-proof');value=json.loads(p.read_text())
            self.assertEqual(list(value),['LC1']);self.assertFalse(value['LC1']['accepted'])
            with self.assertRaises(ValueError):c.reserve('longcold','LC1','owned-output','owned-proof')
            self.assertEqual(json.loads(p.read_text()),value)

    def test_longcold_requires_new_entry_file_and_cpu_membership(self):
        with tempfile.TemporaryDirectory() as d, patch.object(r,'P',Path(d).resolve()):
            p=Path(d).resolve(); path=p/'longcold-qualification.json'; pin='a'*64
            names=('lc_config.py','lc_runtime.py','lc_controls.py','lc_owner.py','lc_audit.py','lc_audit_dispatch.py')
            sources={n:'e'*64 for n in names}; files={str(p/n):v for n,v in sources.items()}
            files.update({str(r.E/k):v for k,v in r.PINS.items()})
            files.update({str(r.R/'window.py'):'170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f',
                          str(r.D/'config.json'):config.BASE_SHA,str(r.D/'bin/maya-ds4'):config.BASE_NATIVE})
            q={'mode':'longcold','root_manual_review':True,'astra_manual_review':True,
               'authorization_sha256':'cb2698ff10b5bd42b029968f20f59aa78d3d6924b4b8a4b5548bc3b28e78ce5a',
               'context':1048576,'output_allowance':262144,'files':files,
               'CPU_groups':[{'source_sha256':sources,'proofs':{}}], 'pack_and_resource_prerequisite_reviewed':True,
               'private_memory_max':r.MEMORY_MAX,'host_margin':r.HOST_MARGIN}
            # Existing proof/pack contracts have separate real controls; isolate the new entry selector here.
            with patch.object(r,'sha',side_effect=lambda x:pin if Path(x)==path else files.get(str(x),'e'*64)), \
                 patch.object(r,'cpu_membership'),patch.object(r,'closed_cs1'),patch.object(r,'pack_custody'),patch.object(r,'encoded_custody'):
                path.write_text(json.dumps(q)); self.assertEqual(r.qualified('longcold',pin)['mode'],'longcold')
                for missing in ('file','CPU'):
                    bad=copy.deepcopy(q)
                    if missing=='file':bad['files'].pop(str(p/'lc_owner.py'))
                    else:bad['CPU_groups'][0]['source_sha256'].pop('lc_owner.py')
                    path.write_text(json.dumps(bad))
                    with self.subTest(missing=missing),self.assertRaisesRegex(ValueError,'Executing changed source'):
                        r.qualified('longcold',pin)

    def test_full_phase_proof_requires_same_owned_controller(self):
        with tempfile.TemporaryDirectory() as d:
            e=Path(d).resolve();p=e/'mode';p.mkdir();(e/'results').mkdir();(e/'maintenance').mkdir()
            output=e/'results/maya-s-longcold-LC1-20261030T180000Z';meta=e/'maintenance'/output.name;meta.mkdir()
            proof={'mode':'longcold','arm':'LC1','output':str(output),'qualification_sha256':'a'*64,
                   'qualified_for_owned_maya_s':True}
            state={**proof,'status':r.statuses('longcold')['running'],'controller_pid':99}
            active={'decode_optimization_current':state,'active_private_phase':str(meta),'active_gpu_experiment':True,
                    'maintenance_controller':str(meta/'state.json')}
            registry={'LC1':{'attempted':True,'output':str(output),'controller_pid':99}}
            for path,value in [(meta/'proof.json',proof),(meta/'state.json',state),(e/'STATE.json',active),(p/'longcold-arms.json',registry)]:
                path.write_text(json.dumps(value))
            with patch.object(c,'E',e),patch.object(c,'P',p),patch.object(r,'E',e),patch.object(r,'P',p):
                self.assertEqual(c.read_proof(output,'longcold','LC1',meta/'proof.json'),proof)
                active['decode_optimization_current']['controller_pid']=100;(e/'STATE.json').write_text(json.dumps(active))
                with self.assertRaises(ValueError):c.read_proof(output,'longcold','LC1',meta/'proof.json')


class Body(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.e=Path(self.tmp.name).resolve();self.out=self.e/'results/maya-s-longcold-LC1-20261030T180000Z'
        self.folder=self.out/'native';self.folder.mkdir(parents=True);(self.folder/'tmp').mkdir()
        self.d=self.e/'selected';self.d.mkdir();(self.d/'config.json').write_bytes(BASE.read_bytes())
        (self.d/'profile-seed.bin').write_bytes(b'synthetic seed')
        (self.folder/'engine.log').write_text('synthetic long startup; mocked exact skip5801\n')
        self.proc=types.SimpleNamespace(pid=71);self.processes=[]
        def body_cleanup(body,cleanup):
            try:return body()
            finally:cleanup()
        self.old=types.SimpleNamespace(
            q8_phase=types.SimpleNamespace(SEED_SHA=r.sha(self.d/'profile-seed.bin'), environment=Mock(return_value={}),
                wait_startup=Mock(return_value=({'pid':72},{'ok':True},{'data':[]})),
                native_paths=lambda path: sorted(Path(path).glob('native-[0-9][0-9][0-9]'))),
            body_and_cleanup=body_cleanup,stop_server=Mock())
        response,proof=answer()
        def issue(case,folder,pid,deadline,*,requester):
            self.assertEqual(pid,72);self.assertEqual(deadline,1100)
            actual=requester('private-test',case['request'],deadline)
            trace=Path(folder)/'native-001';trace.mkdir()
            (trace/'tokens.jsonl').write_text(''.join(json.dumps({'token':i,'seconds':i*.001})+'\n' for i in range(7)))
            return actual,proof
        self.skip=types.SimpleNamespace(issue=Mock(side_effect=issue),ControlBudgetStop=type('Stop',(Exception,),{}),
                                       activation=Mock(return_value={'activation_early_rows':[5801]}))
        self.protocol=types.SimpleNamespace(Stream=Mock(),json_get=Mock(),wait_for=Mock())
        self.numerical=types.SimpleNamespace(dump_snapshot=Mock(side_effect=AssertionError('no dumps')),
                                            owned_storage_snapshot=Mock())
        self.patches=[patch.object(c,'D',self.d),patch.object(config,'E',self.e),
                      patch.object(c.time,'monotonic',return_value=101),
                      patch.object(c.subprocess,'Popen',return_value=self.proc),
                      patch.object(c.controls,'startup',return_value={}),
                      patch.object(c.controls,'actual_native',return_value={'native_pid':72}),
                      patch.object(c.controls,'fence_terminal',return_value={'passed':True}),
                      patch.object(c.controls,'bounded_request',return_value=response),
                      patch.dict(c.sys.modules,{'skip_controls':self.skip,'protocol':self.protocol})]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def call(self):
        return c.phase_body(self.out,'longcold','LC1',{}, {'allowed_automatic_cuts':{'B':[19,20]}},
                            'window',{'cases':[sample()]},self.folder,{},self.processes,100,
                            object(),self.old,self.numerical,object())

    def test_actual_body_one_scripted_request_trace_cleanup_and_no_dump_hook(self):
        result=self.call();self.assertTrue(result['arm_results']['complete'])
        self.assertEqual(result['arm_results']['native_request_count'],1)
        self.assertEqual(self.processes,[self.proc]);self.skip.issue.assert_called_once()
        self.old.stop_server.assert_called_once_with(self.proc,self.folder,timeout=100)
        args=c.controls.bounded_request.call_args.args
        self.assertFalse(args[4]);self.assertEqual(args[1]['max_tokens'],32768)
        self.assertEqual(args[1]['reasoning_effort'],100)
        self.numerical.dump_snapshot.assert_not_called()
        self.skip.activation.assert_called_once_with((self.folder/'engine.log').read_text(),1,required=True)
        cfg=json.loads((self.out/'candidate-config.json').read_text())
        self.assertNotIn('DS4_SERVE_DUMP',cfg['env'])
        self.assertEqual(json.loads((self.out/'candidate-config.shared-settings.json').read_text()),{'max_tokens':262144})
        argv=c.subprocess.Popen.call_args.args[0];self.assertIn(str(c.P/'lc_owner.py'),argv)
        self.assertIn('LC1',argv);self.assertEqual(argv.count('--entry'),1)

    def test_extra_native_trace_fails_and_cleans_once(self):
        original=self.skip.issue.side_effect
        def extra(*args,**kwargs):
            value=original(*args,**kwargs);(self.folder/'native-002').mkdir();return value
        self.skip.issue.side_effect=extra
        with self.assertRaisesRegex(ValueError,'Exactly one trace'):self.call()
        self.old.stop_server.assert_called_once();self.skip.issue.assert_called_once()

    def test_first_server_receipt_failure_still_closes_captured_process(self):
        emit=r.emit
        def fault(path,value):
            if Path(path).name=='server-start.json':raise RuntimeError('first receipt')
            return emit(path,value)
        with patch.object(r,'emit',side_effect=fault):
            with self.assertRaisesRegex(RuntimeError,'first receipt'):self.call()
        self.assertEqual(self.processes,[self.proc]);self.old.stop_server.assert_called_once()
        self.skip.issue.assert_not_called()

    def test_wrong_mode1_skip_refuses_and_closes_once(self):
        self.skip.activation.return_value={'activation_early_rows':[5800]}
        with self.assertRaisesRegex(ValueError,'mode1 skip'):self.call()
        self.old.stop_server.assert_called_once();self.skip.issue.assert_called_once()

    def test_startup_timeout_uses_original_phase_clock_and_closes_once(self):
        self.old.q8_phase.wait_startup.side_effect=TimeoutError('startup')
        with self.assertRaises(TimeoutError):self.call()
        self.assertEqual(self.old.q8_phase.wait_startup.call_args.args[-1],900)
        self.old.stop_server.assert_called_once();self.skip.issue.assert_not_called()


class LongContract(unittest.TestCase):
    def test_zero_actual_drafts_holds_without_second_request(self):
        response,proof=answer();proof['native']['drafts_offered']=proof['native']['drafts_accepted']=0
        issue=Mock(return_value=(response,proof));out=c.run_one(sample(),'.',71,1000,issue=issue)
        self.assertFalse(out['complete']);issue.assert_called_once()

    def test_json_values_float_is_not_exact_typed_answer(self):
        response,proof=answer();values=list(range(1,65));values[0]=1.0
        response['content']=json.dumps({'values':values})
        out=c.run_one(sample(),'.',71,1000,issue=Mock(return_value=(response,proof)))
        self.assertFalse(out['complete'])


if __name__=='__main__':unittest.main()
