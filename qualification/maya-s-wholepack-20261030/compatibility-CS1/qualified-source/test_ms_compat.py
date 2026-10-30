"""CS1 contracts and scripted ownership boundaries. No native/service/model execution."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import ms_compat as c
import ms_fixtures as f

r, config = c.runtime, c.config
SOURCE = r.P / 'prose-fixtures-B.json'
BASE = f.E / 'decode-optimization-20261028/model-v1/base-config.json'


def sample():
    case = copy.deepcopy(json.loads(SOURCE.read_text())['lifecycle_cases'][-1])
    case.pop('dependency'); case.update(id=r.COMPAT_CASE_ID, expected_reuse='zero')
    return case


def answer():
    response = {'status': 200, 'done': True, 'cancelled': False, 'finish_reason': 'stop',
                'content': 'RECOVERED_Q8_LITERAL', 'reasoning': 'synthetic only'}
    proof = {'observed_tokens': 7, 'prompt_tokens': 44, 'client_full_s': .02,
             'native': {'generated': 7, 'finish': 'stop', 'reused': 0, 'drafts_offered': 0,
                        'drafts_accepted': 0, 'prompt_ms': 1.0, 'decode_ms': 2.0}}
    return response, proof


class Manifest(unittest.TestCase):
    def test_exact_already_encoded_candidate_slice_without_encoding(self):
        original = SOURCE.read_bytes()
        with patch.object(f, 'load_support', side_effect=AssertionError('No encoding')):
            m = c.manifest('compatibility', 'CS1')
        self.assertEqual(SOURCE.read_bytes(), original)
        self.assertEqual(m['cases'], [sample()]); self.assertEqual(m['context'], 1048576)
        self.assertEqual(m['default_output'], 262144); self.assertTrue(m['derived_without_reencoding'])
        self.assertFalse(m['quality_or_performance_pass']); self.assertFalse(m['automatic_next_arm'])

    def test_changed_source_bytes_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'prose-fixtures-B.json').write_bytes(SOURCE.read_bytes()+b' ')
            with patch.object(r,'P',p), self.assertRaisesRegex(ValueError,'artifact'):
                r.compatibility_manifest()

    def test_changed_actual_ids_refused_even_with_repointed_test_pin(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); m=json.loads(SOURCE.read_text()); m['lifecycle_cases'][-1]['prompt_ids'][0]+=1
            target=p/'prose-fixtures-B.json'; target.write_text(json.dumps(m))
            with patch.object(r,'P',p), patch.object(r,'COMPAT_SOURCE_SHA',r.sha(target)):
                with self.assertRaises(ValueError): r.compatibility_manifest()

    def test_other_arms_and_modes_refused_before_manifest(self):
        with patch.object(r,'compatibility_manifest') as read:
            for mode,arm in [('quality','QS1'),('compatibility','QS1'),('prose','B1')]:
                with self.assertRaises(ValueError): c.manifest(mode,arm)
        read.assert_not_called()

    def test_exact_tokenizer_and_template_membership_required(self):
        m=json.loads(SOURCE.read_text()); directory=f.CANDIDATE_PACK/'tokenizer'
        files={str(SOURCE):r.sha(SOURCE),**{str(directory/k):v for k,v in m['tokenizer_source_sha256'].items()}}
        with patch.object(f,'tokenizer_directory',return_value=directory):
            r.encoded_custody({'files':files},'compatibility')
            for key in list(files):
                missing=dict(files);missing.pop(key)
                with self.subTest(key=key),self.assertRaises(ValueError):
                    r.encoded_custody({'files':missing},'compatibility')

    def test_full_policy_selected_native_candidate_pack_no_dump(self):
        base=json.loads(BASE.read_text()); before=copy.deepcopy(base)
        path=config.E/'results/maya-s-compatibility-CS1-20261030T180000Z/native'
        value=config.make_config(base,path,'compatibility','CS1')
        self.assertTrue(config.check_config(base,value,path,'compatibility','CS1'))
        self.assertEqual(config.factor('compatibility','CS1')['native_sha256'],config.BASE_NATIVE)
        self.assertEqual(value['args'][value['args'].index('--pack')+1],str(config.CANDIDATE_PACK))
        self.assertEqual(value['args'][value['args'].index('--max-context')+1],'1048576')
        self.assertEqual(value['hosted_default_effort'],100);self.assertEqual(base,before)
        self.assertNotIn('DS4_SERVE_DUMP',value['env']);self.assertNotIn('max_tokens',value)
        self.assertEqual(value['tokenizer'],str(config.CANDIDATE_PACK/'tokenizer'))
        for field,changed in [('hosted_default_effort',100.0),('exe','new-engine'),('tokenizer',base['tokenizer'])]:
            wrong=copy.deepcopy(value);wrong[field]=changed
            with self.assertRaises(ValueError):config.check_config(base,wrong,path,'compatibility','CS1')
        wrong=copy.deepcopy(value);wrong['env']['DS4_SERVE_DUMP']='dump'
        with self.assertRaises(ValueError):config.check_config(base,wrong,path,'compatibility','CS1')

    def test_compatibility_is_one_shot_without_prior_quality_bypass_for_timing(self):
        with tempfile.TemporaryDirectory() as d, patch.object(r,'P',Path(d)):
            r.prerequisite('compatibility','CS1',{})
            with self.assertRaises(ValueError):r.prerequisite('compatibility','CS1',{'CS1':{'attempted':True}})
            (Path(d)/'quality-arms.json').write_text('{}')
            with self.assertRaises(ValueError):r.prerequisite('prose','A1',{})
            with self.assertRaises(ValueError):r.prerequisite('compatibility','CS2',{})


class OneRequest(unittest.TestCase):
    def test_one_natural_literal_zero_drafts_valid_without_quality_or_speed_claim(self):
        issue=Mock(return_value=answer()); progress=[]
        result=c.run_one(sample(),Path('/unused'),71,1000,issue=issue,
                         save_progress=lambda x:progress.append(copy.deepcopy(x)))
        issue.assert_called_once(); self.assertTrue(result['complete']); self.assertFalse(result['retry'])
        self.assertFalse(result['automatic_next_arm']);self.assertFalse(result['quality_or_performance_pass'])
        self.assertEqual(result['rows'][0]['native']['drafts_offered'],0)
        self.assertEqual(progress[0]['scores'][0]['status'],'UNRUN')

    def test_wrong_literal_is_incomplete_without_second_issue(self):
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
        for key,value in [('generated',8),('reused',1),('drafts_offered',True),('drafts_accepted',1),('decode_ms',float('nan'))]:
            response,proof=answer();proof['native'][key]=value;issue=Mock(return_value=(response,proof))
            with self.subTest(key=key):
                try: result=c.run_one(sample(),'.',71,1000,issue=issue)
                except ValueError: pass
                else:self.assertFalse(result['complete'])
            issue.assert_called_once()

    def test_wrong_actual_prompt_count_refused(self):
        response,proof=answer();proof['prompt_tokens']=43
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
        for key,value in [('id','ms-quality-cold-text'),('expected','other'),('prompt_ids',[0]*44)]:
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
            self.assertEqual(c.phase(self.out,'compatibility','CS1','unused'),0)
        self.assertEqual(events,['install','body','restore','receipt'])

    def test_failed_fence_restoration_never_publishes_terminal_success(self):
        class Fence:
            def __enter__(self):return {},[]
            def __exit__(self,*a):raise RuntimeError('restore failure')
        with patch.object(c.controls,'fenced_phase',return_value=Fence()),patch.object(c,'phase_body',return_value={}):
            with self.assertRaisesRegex(RuntimeError,'restore failure'):c.phase(self.out,'compatibility','CS1','unused')
        self.assertFalse((self.out/'receipt.json').exists())

    def test_fence_install_failure_blocks_body(self):
        with patch.object(c.controls,'fenced_phase',side_effect=RuntimeError('fence')),patch.object(c,'phase_body') as body:
            with self.assertRaises(RuntimeError):c.phase(self.out,'compatibility','CS1','unused')
        body.assert_not_called()

    def test_foreign_mode_blocks_before_support(self):
        with self.assertRaises(ValueError):c.phase(self.out,'quality','QS1','unused')
        c.helpers.assert_not_called()

    def test_existing_output_blocks_replay(self):
        self.out.mkdir()
        with patch.object(c.controls,'fenced_phase') as fence:
            with self.assertRaises(FileExistsError):c.phase(self.out,'compatibility','CS1','unused')
        fence.assert_not_called()


class Custody(unittest.TestCase):
    def test_exact_window_entry_and_no_completed_or_foreign_window(self):
        output=r.E/'results/maya-s-compatibility-CS1-20261030T180000Z';proof=r.E/'maintenance'/output.name/'proof.json'
        command=[str(c.R/'venv/bin/python3.14'),'-B',str(c.P/'ms_compat.py'),'--phase','--mode','compatibility',
                 '--arm','CS1','--output',str(output),'--proof',str(proof)]
        value={'command':command,'continued_from':'last-clean','test_returncode':None,'maintenance_held':False,'restored':False}
        old=types.SimpleNamespace(owned_window=Mock(return_value=(c.R/'windows/new.json',value)))
        c.window_contract(old,output,'compatibility','CS1',proof)
        for change in [{'test_returncode':0},{'restored':True},{'command':command[:2]+['ms_quality.py']+command[3:]}]:
            old.owned_window.return_value=(c.R/'windows/new.json',{**value,**change})
            with self.assertRaises(ValueError):c.window_contract(old,output,'compatibility','CS1',proof)

    def test_registry_reserves_only_CS1_once(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c,'P',Path(d)),patch.object(r,'P',Path(d)):
            p=Path(d)/'compatibility-arms.json';p.write_text('{}')
            c.reserve('compatibility','CS1','owned-output','owned-proof');value=json.loads(p.read_text())
            self.assertEqual(list(value),['CS1']);self.assertFalse(value['CS1']['accepted'])
            with self.assertRaises(ValueError):c.reserve('compatibility','CS1','owned-output','owned-proof')
            self.assertEqual(json.loads(p.read_text()),value)

    def test_compatibility_requires_new_entry_file_and_cpu_membership(self):
        with tempfile.TemporaryDirectory() as d, patch.object(r,'P',Path(d)):
            p=Path(d); path=p/'compatibility-qualification.json'; pin='a'*64
            names=('ms_config.py','ms_fixtures.py','ms_runtime.py','ms_controls.py','ms_audit.py',
                   'ms_quality_audit.py','ms_audit_dispatch.py','ms_compat.py')
            sources={n:'e'*64 for n in names}; files={str(p/n):v for n,v in sources.items()}
            files.update({str(r.R/'window.py'):'170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f',
                          str(r.D/'config.json'):config.BASE_SHA,str(r.D/'bin/maya-ds4'):config.BASE_NATIVE})
            q={'mode':'compatibility','root_manual_review':True,'astra_manual_review':True,
               'authorization_sha256':'cb2698ff10b5bd42b029968f20f59aa78d3d6924b4b8a4b5548bc3b28e78ce5a',
               'context':1048576,'output_allowance':262144,'files':files,
               'CPU_groups':[{'source_sha256':sources,'proofs':{}}], 'pack_and_resource_prerequisite_reviewed':True,
               'private_memory_max':r.MEMORY_MAX,'host_margin':r.HOST_MARGIN}
            # Existing proof/pack contracts have separate real controls; isolate the new entry selector here.
            with patch.object(r,'sha',side_effect=lambda x:pin if Path(x)==path else files.get(str(x),'e'*64)), \
                 patch.object(r,'cpu_membership'),patch.object(r,'pack_custody'),patch.object(r,'encoded_custody'):
                path.write_text(json.dumps(q)); self.assertEqual(r.qualified('compatibility',pin)['mode'],'compatibility')
                for missing in ('file','CPU'):
                    bad=copy.deepcopy(q)
                    if missing=='file':bad['files'].pop(str(p/'ms_compat.py'))
                    else:bad['CPU_groups'][0]['source_sha256'].pop('ms_compat.py')
                    path.write_text(json.dumps(bad))
                    with self.subTest(missing=missing),self.assertRaisesRegex(ValueError,'Executing changed source'):
                        r.qualified('compatibility',pin)

    def test_full_phase_proof_requires_same_owned_controller(self):
        with tempfile.TemporaryDirectory() as d:
            e=Path(d).resolve();p=e/'mode';p.mkdir();(e/'results').mkdir();(e/'maintenance').mkdir()
            output=e/'results/maya-s-compatibility-CS1-20261030T180000Z';meta=e/'maintenance'/output.name;meta.mkdir()
            proof={'mode':'compatibility','arm':'CS1','output':str(output),'qualification_sha256':'a'*64,
                   'qualified_for_owned_maya_s':True}
            state={**proof,'status':r.statuses('compatibility')['running'],'controller_pid':99}
            active={'decode_optimization_current':state,'active_private_phase':str(meta),'active_gpu_experiment':True,
                    'maintenance_controller':str(meta/'state.json')}
            registry={'CS1':{'attempted':True,'output':str(output),'controller_pid':99}}
            for path,value in [(meta/'proof.json',proof),(meta/'state.json',state),(e/'STATE.json',active),(p/'compatibility-arms.json',registry)]:
                path.write_text(json.dumps(value))
            with patch.object(c,'E',e),patch.object(c,'P',p),patch.object(r,'E',e),patch.object(r,'P',p):
                self.assertEqual(c.read_proof(output,'compatibility','CS1',meta/'proof.json'),proof)
                active['decode_optimization_current']['controller_pid']=100;(e/'STATE.json').write_text(json.dumps(active))
                with self.assertRaises(ValueError):c.read_proof(output,'compatibility','CS1',meta/'proof.json')


class Body(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.e=Path(self.tmp.name).resolve();self.out=self.e/'results/maya-s-compatibility-CS1-20261030T180000Z'
        self.folder=self.out/'native';self.folder.mkdir(parents=True);(self.folder/'tmp').mkdir()
        self.d=self.e/'selected';self.d.mkdir();(self.d/'config.json').write_bytes(BASE.read_bytes())
        (self.d/'profile-seed.bin').write_bytes(b'synthetic seed')
        (self.folder/'engine.log').write_text('synthetic short startup; no skip activated\n')
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
                                       activation=Mock(return_value={'activation_early_rows':[]}))
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
        return c.phase_body(self.out,'compatibility','CS1',{}, {'allowed_automatic_cuts':{'B':[19,20]}},
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
        self.skip.activation.assert_called_once_with((self.folder/'engine.log').read_text(),1,required=False)
        cfg=json.loads((self.out/'candidate-config.json').read_text())
        self.assertNotIn('DS4_SERVE_DUMP',cfg['env'])
        self.assertEqual(json.loads((self.out/'candidate-config.shared-settings.json').read_text()),{'max_tokens':262144})
        argv=c.subprocess.Popen.call_args.args[0];self.assertIn(str(c.P/'ms_compat.py'),argv)
        self.assertIn('CS1',argv);self.assertEqual(argv.count('--entry'),1)

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


if __name__=='__main__':unittest.main()
