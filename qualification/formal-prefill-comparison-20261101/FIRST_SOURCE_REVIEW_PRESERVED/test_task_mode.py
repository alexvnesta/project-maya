"""Single-task scoring, refusal and captured API lifetime. Synthetic CPU only."""
import copy,json,tempfile,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import current_compat as c
import current_runtime as r
import current_config as config
BASE=r.P/'profile-base-config.json'
def sample(arm='A1'):return r.compatibility_manifest(arm)['cases'][0]
def answer(case=None):
    case=sample() if case is None else case
    content=json.dumps({'values':list(range(1,65))})
    return {'status':200,'done':True,'cancelled':False,'finish_reason':'stop','content':content}, {'observed_tokens':7,'prompt_tokens':case['prompt_tokens'],'emitted_token_contract':{'count':7,'valid_vocabulary_ids':True,'ordered_ids_sha256':'a'*64},'native':{'generated':7,'finish':'stop','reused':0,'drafts_offered':0,'drafts_accepted':0,'prompt_ms':1.,'decode_ms':2.}}
class OneMain(unittest.TestCase):
    def test_natural_typed_knownanswer_keeps_comparison_separate(self):
        issue=Mock(return_value=answer());v=c.run_suite([sample()],'unused',71,100,issue=issue)
        self.assertTrue(v['complete']);self.assertFalse(v['rows'][0]['manual_review_pending']);self.assertFalse(v['quality_or_performance_pass']);self.assertFalse(v['automatic_next_arm']);issue.assert_called_once()
    def test_actual_baseline_same_full_knownanswer(self):
        case=sample('A1');issue=Mock(return_value=answer(case));v=c.run_suite([case],'unused',71,100,issue=issue)
        self.assertTrue(v['complete']);self.assertFalse(v['rows'][0]['manual_review_pending']);self.assertFalse(v['quality_or_performance_pass'])
    def test_zero_or_multiple_cases_refused_before_issue(self):
        for cases in ([],[sample(),sample()]):
            issue=Mock()
            with self.assertRaises(ValueError):c.run_suite(cases,'unused',71,100,issue=issue)
            issue.assert_not_called()
    def test_changed_prompt_cap_or_effort_refused_before_issue(self):
        for key,value in [('max_tokens',1024),('reasoning_effort',50),('seed',2)]:
            case=sample();case['request'][key]=value;issue=Mock()
            with self.assertRaises(ValueError):c.run_suite([case],'unused',71,100,issue=issue)
            issue.assert_not_called()
    def test_long_or_wrong_encoded_prompt_refused(self):
        for key,value in [('prompt_tokens',169),('prompt_tokens',True),('prompt_ids_sha256','0'*64)]:
            case=sample();case[key]=value;issue=Mock()
            with self.assertRaises(ValueError):c.run_suite([case],'unused',71,100,issue=issue)
            issue.assert_not_called()
    def test_cap_partial_and_wrong_prose_ending_stay_scored(self):
        for key,value in [('finish_reason','length'),('done',False),('content','{}')]:
            response,proof=answer();response[key]=value;issue=Mock(return_value=(response,proof));v=c.run_suite([sample()],'unused',71,100,issue=issue)
            self.assertFalse(v['complete']);self.assertEqual(v['scores'][0]['status'],'WRONG_CAP_PARTIAL_HOLD');issue.assert_called_once()
    def test_deadline_before_issue_preserves_UNRUN(self):
        e=c.controls.Incomplete('no budget before issue');e.native_started=False;issue=Mock(side_effect=e)
        v=c.run_suite([sample()],'unused',71,100,issue=issue);self.assertFalse(v['complete']);self.assertEqual(v['scores'][0]['status'],'UNRUN');self.assertFalse(v['retry'])
    def test_token_count_or_actual_prompt_contradiction_refused(self):
        for key,value in [('observed_tokens',8),('prompt_tokens',168)]:
            response,proof=answer();proof[key]=value;issue=Mock(return_value=(response,proof))
            with self.assertRaises(ValueError):c.run_suite([sample()],'unused',71,100,issue=issue)
            issue.assert_called_once()
    def test_native_execution_fault_never_retried(self):
        progress=[];issue=Mock(side_effect=RuntimeError('native fault'))
        with self.assertRaisesRegex(RuntimeError,'native fault'):c.run_suite([sample()],'unused',71,100,issue=issue,save_progress=lambda v:progress.append(copy.deepcopy(v)))
        issue.assert_called_once();self.assertEqual(progress[-1]['scores'][0]['status'],'EXECUTION_FAULT_HOLD')
    def test_confirmation_needs_frozen_firstpair_gate_and_separate_admission(self):
        good={'fully_reviewed':True,'owned_execution_closed':True,'task_passed':True,'reversed_confirmation_admitted':True,'first_pair_prefill_screen_passed':True}
        r.prerequisite('task','B2',{'A1':good,'B1':good})
        for key in ('fully_reviewed','owned_execution_closed','task_passed','reversed_confirmation_admitted','first_pair_prefill_screen_passed'):
            bad=copy.deepcopy(good);bad[key]=False
            with self.assertRaises(ValueError):r.prerequisite('task','B2',{'A1':good,'B1':bad})
    def test_wrong_firsttask_or_order_blocks_further_comparison(self):
        good={'fully_reviewed':True,'owned_execution_closed':True,'task_passed':True}
        r.prerequisite('task','A1',{})
        r.prerequisite('task','B1',{'A1':good})
        for arm,reg in [('B1',{}),('A1',{'B1':good}),('B1',{'A1':{**good,'task_passed':False}})]:
            with self.assertRaises(ValueError):r.prerequisite('task',arm,reg)

class NativeFileLimit(unittest.TestCase):
    def sample(self):return {'native_pid':72,'soft':'unlimited','hard':'unlimited','raw':'Max file size             unlimited            unlimited            bytes','mutated':False}
    def test_actual_unlimited_record_is_required_without_mutation(self):self.assertEqual(c.controls.native_file_limit_record(self.sample(),72),self.sample())
    def test_numerical_limit_wrong_native_or_mutation_refused(self):
        for key,value in [('native_pid',73),('soft','536870912'),('hard','536870912'),('mutated',True),('raw','Max file size 536870912 536870912 bytes')]:
            v=self.sample();v[key]=value
            with self.assertRaises(ValueError):c.controls.native_file_limit_record(v,72)

class Body(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.e=Path(self.tmp.name).resolve()
        self.out=self.e/'results/maya145-formal-prefill-B1-20261101T050000Z';self.folder=self.out/'native';self.folder.mkdir(parents=True);(self.folder/'tmp').mkdir()
        self.d=self.e/'selected';self.d.mkdir();(self.d/'config.json').write_bytes(BASE.read_bytes());(self.d/'profile-seed.bin').write_bytes(b'seed');(self.folder/'engine.log').write_text('known-workload startup')
        self.proc=types.SimpleNamespace(pid=71);self.handles=[]
        def body_cleanup(body,cleanup):
            try:return body()
            finally:cleanup()
        self.old=types.SimpleNamespace(q8_phase=types.SimpleNamespace(SEED_SHA=r.sha(self.d/'profile-seed.bin'),environment=Mock(return_value={}),wait_startup=Mock(return_value=({'pid':72},{},{})),native_paths=lambda p:sorted(Path(p).glob('native-[0-9][0-9][0-9]'))),body_and_cleanup=body_cleanup,stop_server=Mock())
        response,proof=answer()
        def issue(case,folder,pid,deadline,*,requester):
            self.assertEqual(pid,72);self.assertEqual(deadline,1100);actual=requester('private-test',case['request'],deadline)
            trace=Path(folder)/('native-%03d'%len(self.old.q8_phase.native_paths(folder)));trace.mkdir();(trace/'tokens.jsonl').write_text(''.join(json.dumps({'token':i,'seconds':i*.001})+'\n' for i in range(7)))
            return actual,copy.deepcopy(proof)
        self.skip=types.SimpleNamespace(issue=Mock(side_effect=issue),ControlBudgetStop=type('Stop',(Exception,),{}),activation=Mock(return_value={'activation_early_rows':[5801]}))
        protocol=types.SimpleNamespace(Stream=Mock(),json_get=Mock(),wait_for=Mock());self.numerical=types.SimpleNamespace(dump_snapshot=Mock(),owned_storage_snapshot=Mock())
        frozen=config.make_config(json.loads(BASE.read_text()),config.E/'results/maya145-formal-prefill-B1-20261101T050000Z/native','task','B1')
        for x in (patch.object(c,'D',self.d),patch.object(c.time,'monotonic',return_value=101),patch.object(c.subprocess,'Popen',return_value=self.proc),patch.object(c.config,'make_config',return_value=frozen),patch.object(c.controls,'startup',return_value={}),patch.object(c.controls,'actual_native',return_value={}),patch.object(r,'asset_expectation',return_value={}),patch.object(c.controls,'direct_witness',return_value={'synthetic':True}),patch.object(c.controls,'native_file_limit',return_value={'soft':'unlimited','hard':'unlimited','mutated':False}),patch.object(c.controls,'fence_terminal',return_value={'passed':True}),patch.object(c.controls,'bounded_request',return_value=response),patch.object(c.controls,'native_stat',return_value={'execution_proven':True}),patch.dict(c.sys.modules,{'skip_controls':self.skip,'protocol':protocol})):
            x.start();self.addCleanup(x.stop)
    def call(self):return c.phase_body(self.out,'task','B1',{}, {},'window',{'cases':[sample()]},self.folder,{},self.handles,100,None,self.old,self.numerical,None)
    def test_one_actual_scripted_trace_cleaned_API_no_dumps_or_FSIZE(self):
        v=self.call();self.assertTrue(v['arm_results']['complete']);self.assertEqual(self.handles,[self.proc]);self.skip.issue.assert_called_once();self.old.stop_server.assert_called_once_with(self.proc,self.folder,timeout=100)
        self.assertFalse(c.controls.bounded_request.call_args.args[4]);self.numerical.dump_snapshot.assert_not_called();self.assertEqual(v['arm_results']['native_request_count'],1)
        self.assertEqual(json.loads((self.out/'candidate-config.shared-settings.json').read_text()),{'max_tokens':262144});self.assertFalse((self.folder/'native-file-bound.json').exists())
    def test_first_receipt_failure_still_closes_captured_API(self):
        emit=r.emit
        def fail(path,value):
            if Path(path).name=='server-start.json':raise RuntimeError('first receipt')
            return emit(path,value)
        with patch.object(r,'emit',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'first receipt'):self.call()
        self.assertEqual(self.handles,[self.proc]);self.old.stop_server.assert_called_once();self.skip.issue.assert_not_called()
    def test_direct_source_witness_failure_closes_before_issue(self):
        c.controls.direct_witness.side_effect=ValueError('bad descriptor')
        with self.assertRaisesRegex(ValueError,'bad descriptor'):self.call()
        self.old.stop_server.assert_called_once();self.skip.issue.assert_not_called()
    def test_extra_native_request_refused_and_owned_API_closed(self):
        original=self.skip.issue.side_effect
        def extra(*args,**kwargs):
            value=original(*args,**kwargs);(self.folder/'native-002').mkdir();return value
        self.skip.issue.side_effect=extra
        with self.assertRaises(ValueError):self.call()
        self.old.stop_server.assert_called_once();self.skip.issue.assert_called_once()
if __name__=='__main__':unittest.main()
