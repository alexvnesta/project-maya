"""No native process; frozen known-answer and bounded transport negatives."""
import copy,json,pathlib,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
import iq2s_explore_controls as c
from test_iq2s_explore_fixtures import synthetic_manifest

def response(case):return {'status':200,'done':True,'finish_reason':'stop','content':json.dumps(case['expected'])}
def proof(case):return {'observed_tokens':2000,'native':{'finish':'stop','generated':2000,'prompt_tokens':1200,
    'reused':0 if case['expected_reuse']=='zero'else 1199,'drafts_offered':20,'drafts_accepted':15}}

class Contracts(unittest.TestCase):
    def test_two_correct_natural_cases_keep_HOLD_and_no_speed_acceptance(self):
        m=synthetic_manifest()
        with patch.object(c,'no_dumps'),patch.object(c,'owned_storage_snapshot',return_value={'status':'WITHIN_BUDGET'}):
            r=c.run_cases(m,None,1,100,issue=lambda case,*args:(response(case),proof(case)))
        self.assertTrue(r['complete']);self.assertEqual(r['native_count'],2);self.assertTrue(r['prior_numerical_HOLD'])
        self.assertFalse(r['quality_or_speed_pass']);self.assertFalse(r['promotion_allowed'])
    def test_wrong_cap_partial_and_zero_draft_score_failure_leave_second_unrun(self):
        m=synthetic_manifest()
        for change in ('wrong','cap','partial','draft'):
            def issue(case,*args):
                r=response(case);p=proof(case)
                if change=='wrong':r['content']='{"values":[1]}'
                if change=='cap':r['finish_reason']='length'
                if change=='partial':r['intentional_budget_stop']=True
                if change=='draft':p['native']['drafts_accepted']=0
                return r,p
            r=c.run_cases(m,None,1,100,issue=issue)
            self.assertFalse(r['complete']);self.assertEqual(len(r['case_scores']),2);self.assertEqual(r['unrun_ids'],[m['cases'][1]['id']]);self.assertFalse(r['retry'])
    def test_wrong_cache_reuse_blocks(self):
        case=synthetic_manifest()['cases'][1];p=proof(case);p['native']['reused']=0
        with self.assertRaises(c.Incomplete):c.natural_contract(case,response(case),p)
    def test_dump_even_empty_is_forbidden(self):
        with tempfile.TemporaryDirectory()as d:
            self.assertTrue(c.no_dumps(d));(pathlib.Path(d)/'logits.1.f32').touch()
            with self.assertRaises(ValueError):c.no_dumps(d)
    def test_no_short_prompt_skip_line_and_zero_or_positive_row_rejected(self):
        self.assertEqual(c.short_prompt_activation('normal')['activation_early_rows'],[])
        for n in (0,1,5798):
            with self.assertRaises(ValueError):c.short_prompt_activation(f'ds4: prompt skip: layers20-39, {n} early rows')

class Transport(unittest.TestCase):
    def stream(self,finished=False):
        calls=[]
        class Stream:
            def __init__(self,*a,**k):self.finished=SimpleNamespace(wait=lambda timeout:finished);self.thread=SimpleNamespace(is_alive=lambda:False)
            def start(self):calls.append('start');return self
            def cancel(self):calls.append('cancel')
            def result(self,timeout):calls.append('result');return {'status':200}
        return Stream,calls
    def test_unstarted_deadline_has_no_request(self):
        s,calls=self.stream();r=c.bounded_request('',{},5,None,stream_class=s,observe=None,wait_for=None,clock=lambda:0)
        self.assertTrue(r['budget_not_started']);self.assertEqual(calls,[])
    def test_storage_cancel_once_waits_owned_release_no_retry(self):
        s,calls=self.stream()
        def wait(fn,timeout,why):self.assertTrue(fn());self.assertEqual(timeout,45)
        with patch.object(c,'no_dumps'),patch.object(c,'owned_storage_snapshot',return_value={'status':'INCOMPLETE_HOLD'}):
            r=c.bounded_request('',{},100,None,stream_class=s,observe=lambda *x:{'work':{'active':0,'queued':0,'admission_reserved':0}},wait_for=wait,clock=lambda:0)
        self.assertTrue(r['intentional_budget_stop']);self.assertFalse(r['retry']);self.assertEqual(calls,['start','cancel','result'])
    def test_soft_deadline_cancel_no_time_extension(self):
        s,calls=self.stream();times=iter([0,100,100])
        with patch.object(c,'no_dumps'),patch.object(c,'owned_storage_snapshot',return_value={'status':'WITHIN_BUDGET'}):
            r=c.bounded_request('',{},100,None,stream_class=s,observe=None,wait_for=lambda *a:None,clock=lambda:next(times))
        self.assertEqual(r['incomplete_reason'],'UNCHANGED_SOFT_DEADLINE');self.assertEqual(calls.count('cancel'),1)
    def test_complete_request_no_dump_scan_or_repeat(self):
        s,calls=self.stream(True)
        with patch.object(c,'no_dumps'),patch.object(c,'owned_storage_snapshot',return_value={'status':'WITHIN_BUDGET'}):
            r=c.bounded_request('',{},100,None,stream_class=s,observe=None,wait_for=None,clock=lambda:0)
        self.assertEqual(r,{'status':200});self.assertEqual(calls,['start','result'])

if __name__=='__main__':unittest.main()
