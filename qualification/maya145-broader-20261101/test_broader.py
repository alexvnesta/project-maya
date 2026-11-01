"""Focused prospective five-case owner tests. No model, service or generated-code execution."""
import copy,json
from pathlib import Path
import tempfile,types,unittest,threading
from unittest.mock import Mock,patch
import broader_cases as cases
import broader_suite as suite
import broader_cancel as cancel
import current_runtime as r
import current_config as config
import current_controls as controls
HERE=Path(__file__).resolve().parent

def manifest():return cases.manifest(HERE/'broader-fixtures.json',r.Q/'model-v1')
def actual_start():return json.loads((HERE/'saved-QTP2/startup-audit.json').read_text())

class Cases(unittest.TestCase):
    def test_exact_five_sources_and_unchanged_full_policy(self):
        m=manifest();self.assertEqual([c['id'] for c in m['cases']],cases.IDS);self.assertEqual([c['prompt_tokens'] for c in m['cases']],cases.COUNTS);self.assertEqual(m['context'],1048576);self.assertEqual(m['default_output'],262144)
    def test_request_ids_order_cap_or_effort_change_rejected(self):
        for change in ('order','cap','effort','ids','source'):
            m=manifest()
            if change=='order':m['cases'].reverse()
            if change=='cap':m['cases'][-1]['request']['max_tokens']=1024
            if change=='effort':m['cases'][-1]['request']['reasoning_effort']=50
            if change=='ids':m['cases'][-1]['prompt_ids']=[0]
            if change=='source':m['source_manifests']['coding-fixtures-B.json']='other'
            with tempfile.TemporaryDirectory() as tmp:
                f=Path(tmp)/'fixture.json';f.write_text(json.dumps(m))
                with self.assertRaises(ValueError):cases.manifest(f,r.Q/'model-v1')
    def test_actual_bound_panel_helpers_are_pv_tool_and_cancel_aware(self):
        expected=r.reusable('pv_controls');self.assertIs(controls.prior,expected);self.assertIs(controls.score,expected.score);self.assertIs(controls.Incomplete,expected.Incomplete);self.assertTrue(callable(controls.prior.followup_case));self.assertTrue(callable(controls.prior.cancel_score))
    def test_two_profiles_same_native_model_drafter_capacity(self):
        for arm in ('BTP1','BTP2'):
            f=config.factor('broader',arm);self.assertEqual(f['context_total'],1048576);self.assertEqual(f['output_allowance'],262144);self.assertEqual(f['native_sha256'],config.BASE_NATIVE)
        with self.assertRaises(ValueError):config.factor('quality','QTP2')

class Sequencing(unittest.TestCase):
    def setUp(self):
        self.m=manifest()['cases'];self.fixtures=r.original_module('ms_fixtures');self.calls=[];self.saved=[]
    def natural(self,case,*args):
        self.calls.append((case['id'],args[-1],copy.deepcopy(case['request'])))
        response={'status':200,'done':True,'finish_reason':'stop','cancelled':False,'reasoning':'synthetic'}
        if case['kind']=='tool':response.update(self.fixtures.synthetic_call('actual-provider-731'));response['content']=''
        elif case['kind']=='code':response['content']='def coalesce_ranges(ranges):\n    return []\n'
        elif case['kind']=='literal':response['content']=case['expected']
        else:response['content']=json.dumps(case['expected'])
        n={'generated':7,'finish':'stop','reused':case['prompt_tokens']-1 if case.get('expected_reuse')=='prompt-minus-one' else 0,'drafts_offered':4,'drafts_accepted':3,'prompt_ms':1.,'decode_ms':2.}
        return response,{'native':n,'prompt_tokens':case['prompt_tokens'],'observed_tokens':7,'client_full_s':.03,'emitted_token_contract':{'count':7}}
    def cancelled(self,case,*args):
        self.calls.append((case['id'],args[-1],copy.deepcopy(case['request'])))
        response={'passed':True,'classification':'confirmed_prefill_cancel','replay':False,'recovery_required':True,'client_disconnect_cancels_delta':1,'observed_before_cancel':{'state':'reading','read':4096,'total':case['prompt_tokens'],'first_delta':False},'transport':{'cancelled':True,'content':'','reasoning':'','tool_calls':[]}}
        return response,{'native':{'generated':0,'finish':'cancel'},'prompt_tokens':case['prompt_tokens'],'observed_tokens':0,'cancelled_control_or_budget':True}
    def run_suite(self,issue=None,canceller=None):
        return suite.run_suite(self.m,'.',71,1000,issue=issue or self.natural,cancel=canceller or self.cancelled,fixtures=self.fixtures,controls=controls,save_progress=lambda v:self.saved.append(copy.deepcopy(v)))
    def test_real_five_order_dependencies_clock_and_actual_call_ID(self):
        v=self.run_suite();self.assertTrue(v['complete']);self.assertEqual([c[0] for c in self.calls],cases.IDS);self.assertEqual({c[1] for c in self.calls},{1000});self.assertEqual(self.calls[1][2]['messages'][-1]['tool_call_id'],'actual-provider-731');self.assertFalse(v['quality_or_performance_pass']);self.assertTrue(v['rows'][-1]['manual_review_pending'])
    def test_tool_wrong_argument_stops_before_followup_and_code(self):
        def bad(case,*args):
            response,proof=self.natural(case,*args);response['tool_calls'][0]['function']['arguments']='{"sku":"wrong","quantity":6}';return response,proof
        v=self.run_suite(issue=bad);self.assertFalse(v['complete']);self.assertEqual(len(self.calls),1);self.assertTrue(all(x['status']=='UNRUN' for x in v['scores'][1:]))
    def test_cancellation_must_be_before_first_output(self):
        for field,value in [('first_delta',True),('read',8471),('state','decode')]:
            self.calls=[]
            def bad(case,*args):
                response,proof=self.cancelled(case,*args);response['observed_before_cancel'][field]=value;return response,proof
            with self.assertRaises(ValueError):self.run_suite(canceller=bad)
            v=self.saved[-1];self.assertEqual([c[0] for c in self.calls],cases.IDS[:3]);self.assertTrue(all(x['status']=='UNRUN' for x in v['scores'][3:]))
    def test_cancellation_cannot_generate_tokens_or_retain_owner(self):
        for kind in ('generated','cleanup','disconnect'):
            def bad(case,*args):
                response,proof=self.cancelled(case,*args)
                if kind=='generated':proof['native']['generated']=proof['observed_tokens']=1
                if kind=='cleanup':response['cleanup_error']='owned task retained'
                if kind=='disconnect':response['client_disconnect_cancels_delta']=0
                return response,proof
            with self.assertRaises(ValueError):self.run_suite(canceller=bad)
    def test_partial_coding_keeps_all_prior_and_blocks_advancement(self):
        def issue(case,*args):
            response,proof=self.natural(case,*args)
            if case['kind']=='code':response['finish_reason']='length'
            return response,proof
        v=self.run_suite(issue=issue);self.assertFalse(v['complete']);self.assertEqual(len(v['rows']),4);self.assertEqual(v['scores'][-1]['status'],'WRONG_CAP_PARTIAL_HOLD');self.assertFalse(v['retry'])
    def test_code_syntax_screen_does_not_execute_generated_module(self):
        def issue(case,*args):
            response,proof=self.natural(case,*args)
            if case['kind']=='code':response['content']='raise RuntimeError("never execute")\ndef coalesce_ranges(ranges):\n return []\n'
            return response,proof
        self.assertTrue(self.run_suite(issue=issue)['complete'])
    def test_missing_dependency_or_prompt_mismatch_fault_is_not_retry(self):
        self.m=self.m[1:]
        with self.assertRaises(ValueError):self.run_suite()
        self.assertEqual(self.calls,[])
    def test_execution_fault_preserves_remaining_UNRUN(self):
        issue=Mock(side_effect=RuntimeError('native'))
        with self.assertRaisesRegex(RuntimeError,'native'):self.run_suite(issue=issue)
        issue.assert_called_once();self.assertEqual(self.saved[-1]['scores'][0]['status'],'EXECUTION_FAULT_HOLD');self.assertTrue(all(x['status']=='UNRUN' for x in self.saved[-1]['scores'][1:]))
    def test_recovery_literal_wrong_and_native_count_drift_refused(self):
        for key in ('literal','count'):
            def issue(case,*args):
                response,proof=self.natural(case,*args)
                if case['kind']=='literal':
                    if key=='literal':response['content']='wrong'
                    else:proof['prompt_tokens']+=1
                return response,proof
            if key=='count':
                with self.assertRaises(ValueError):self.run_suite(issue=issue)
            else:self.assertFalse(self.run_suite(issue=issue)['complete'])

class PlacementAdapter(unittest.TestCase):
    def test_actual_TP2_cancellation_uses_source0_and5803(self):
        start=actual_start();f=cancel.adapter(start,'TP2',5803);x=f('ds4: prompt skip: layers 20-39 from CUDA0, 5803 early rows KV-only, 2668 kept',1,required=True);self.assertEqual(x['source_device'],0);self.assertEqual(x['activation_early_rows'],[5803])
    def test_old_device_wrong_span_count_or_mode_refused(self):
        f=cancel.adapter(actual_start(),'TP2',5803);line='ds4: prompt skip: layers 20-39 from CUDA0, 5803 early rows KV-only, 2668 kept'
        for text in (line.replace('CUDA0','CUDA1'),line.replace('5803','5801'),line.replace('20-39','19-39')):
            with self.assertRaises(ValueError):f(text,1,required=True)
        with self.assertRaises(ValueError):f(line,0,required=False)
    def test_real_private_transport_uses_new_callback_before_first_output(self):
        module=r.reusable('pv_runtime').lifecycle_helper();module.activation=cancel.adapter(actual_start(),'TP2',5803)
        state={'cancelled':False,'counter':0}
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'engine.log';log.write_text('startup\n')
            class FakeStream:
                def __init__(self,*args,**kw):
                    self.error=None;self.first_delta=threading.Event();self.finished=threading.Event();self.thread=types.SimpleNamespace(is_alive=lambda:not state['cancelled'])
                def start(self):
                    with log.open('a') as f:f.write('ds4: prompt skip: layers 20-39 from CUDA0, 5803 early rows KV-only, 2668 kept\n')
                    return self
                def cancel(self):state.update(cancelled=True,counter=1)
                def result(self,*args):return {'cancelled':state['cancelled'],'content':'','reasoning':'','tool_calls':[]}
            def observe(*args):return {'work':{'active':0,'queued':0,'admission_reserved':0,'client_disconnect_cancels':state['counter']}}
            result=module.prefill_cancel('http://127.0.0.1:18041',manifest()['cases'][2]['request'],1000,log,1,stream_class=FakeStream,observe=observe,observe_progress=lambda base:{'state':'reading','prompt_read':1024,'prompt_total':8471},clock=lambda:0.,pause=lambda x:None)
        self.assertTrue(result['passed']);self.assertEqual(result['activation']['source_device'],0);self.assertEqual(result['classification'],'confirmed_prefill_cancel');self.assertTrue(result['transport']['cancelled'])
    def test_private_module_adaptation_leaves_original_qualified_helper_unchanged(self):
        original=Mock();private=types.SimpleNamespace(activation=original);runtime=types.SimpleNamespace(reusable=Mock(return_value=types.SimpleNamespace(lifecycle_helper=Mock(return_value=private))))
        cancel.requester(runtime,None,None,None,None,actual_start(),'TP2');self.assertIsNot(private.activation,original);original.assert_not_called()

if __name__=='__main__':unittest.main()
