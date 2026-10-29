"""No native/model execution; scripted transport, exact state and dump controls."""
import copy,json,pathlib,struct,tempfile,unittest
from unittest.mock import patch
from types import SimpleNamespace
import imma_numeric_controls as n

def case():return {'id':'cold-text','request':{'max_tokens':32768},'expected':{'values':[1,2]},'expected_reuse':'zero','prompt_tokens':8000}
def response():return {'status':200,'done':True,'finish_reason':'stop','content':'{"values":[1,2]}'}
def proof():return {'observed_tokens':10,'native':{'finish':'stop','reused':0,'drafts_offered':5,'drafts_accepted':3,'prompt_tokens':8000,'generated':10}}
def rows():return [{'id':x,'tokens':[1,2,3],'dump':{'bytes':4,'rows':1,'sha256':'a','all_finite':True},'native':proof()['native']} for x in ('cold-text','rewind-text','two-images','restore-text')]

class NaturalControls(unittest.TestCase):
    def test_correct_typed_natural_answer_positive_draft(self):
        got=n.natural_contract(case(),response(),proof());self.assertTrue(got['natural_stop']);self.assertFalse(got['numerical_equivalence_pass'])
    def test_wrong_bool_float_extra_or_malformed_answer_is_incomplete(self):
        for content in ('{"values":[true,2]}','{"values":[1.0,2]}','{"values":[1,2],"extra":0}','notJSON'):
            r=response();r['content']=content
            with self.assertRaises(n.NumericalIncomplete):n.natural_contract(case(),r,proof())
    def test_cap_cancel_budget_unrun_and_bad_status_block(self):
        for key,value in [('finish_reason','length'),('finish_reason','cancel'),('intentional_budget_stop',True),('budget_not_started',True),('status',503),('done',False),('cancelled',True)]:
            r=response();r[key]=value
            with self.subTest(key=key),self.assertRaises(n.NumericalIncomplete):n.natural_contract(case(),r,proof())
    def test_cap1_zero_or_caplength_output_block(self):
        for count in (0,1,32768,True):
            p=proof();p['observed_tokens']=count
            with self.assertRaises(n.NumericalIncomplete):n.natural_contract(case(),response(),p)
    def test_zero_missing_or_bool_draft_never_qualifies(self):
        for key in ('drafts_offered','drafts_accepted'):
            for value in (0,None,True):
                p=proof();p['native'][key]=value
                with self.assertRaises(n.NumericalIncomplete):n.natural_contract(case(),response(),p)
    def test_impossible_draft_accounting_rejected(self):
        p=proof();p['native']['drafts_accepted']=6
        with self.assertRaises(ValueError):n.natural_contract(case(),response(),p)
    def test_exact_cache_rewind_or_slot_return_required(self):
        c=case();c['expected_reuse']='prompt-minus-one';p=proof();p['native']['reused']=7999
        self.assertTrue(n.natural_contract(c,response(),p)['typed_answer_correct'])
        p['native']['reused']=7998
        with self.assertRaises(n.NumericalIncomplete):n.natural_contract(c,response(),p)
    def test_compare_requires_identical_path_and_finite_dump_proof(self):
        a=rows();b=copy.deepcopy(a);self.assertTrue(n.compare_matched(a,b)['passed'])
        b[2]['tokens']=[1,4,3];self.assertEqual(n.compare_matched(a,b)['status'],'HOLD_TOKEN_PATH_DIFFERS')
    def test_nonzero_logit_or_row_count_drift_holds_without_tolerance(self):
        for key,value in [('sha256','b'),('rows',2),('bytes',8)]:
            a=rows();b=copy.deepcopy(a);b[1]['dump'][key]=value
            self.assertEqual(n.compare_matched(a,b)['status'],'HOLD_NONZERO_LOGIT_OR_ROW_DRIFT')
    def test_native_draft_or_cache_path_drift_blocks(self):
        for key in ('prompt_tokens','generated','reused','drafts_offered','drafts_accepted'):
            a=rows();b=copy.deepcopy(a);b[0]['native'][key]+=1
            self.assertEqual(n.compare_matched(a,b)['status'],'HOLD_NATIVE_STATE_DIFFERS')
    def test_compare_missing_case_cannot_pass(self):
        with self.assertRaises(ValueError):n.compare_matched(rows()[:-1],rows())
    def test_wrong_case_keeps_all_four_scored_and_remaining_unrun(self):
        cases=[{**case(),'id':name} for name in n.fixture.IDS]
        def issue(case,folder,pid,deadline):return {**response(),'finish_reason':'length'},proof()
        with patch.object(n.fixture,'validate_encoded'):
            r=n.run_cases({'cases':cases},None,123,100,issue=issue)
        self.assertFalse(r['complete']);self.assertEqual(len(r['case_scores']),4)
        self.assertEqual(r['case_scores'][0]['status'],'WRONG_CAP_PARTIAL_OR_UNRUN_HOLD')
        self.assertEqual(r['unrun_ids'],list(n.fixture.IDS[1:]));self.assertFalse(r['retry'])

class DumpControls(unittest.TestCase):
    def test_private_phase_dump_size_does_not_open_hash_or_scan_float_data(self):
        with tempfile.TemporaryDirectory() as d,patch.object(n.storage,'ROW_BYTES',8):
            p=pathlib.Path(d)/'logits.1.f32';p.write_bytes(struct.pack('<ff',1,2))
            with patch.object(pathlib.Path,'open',side_effect=AssertionError('private phase must only stat')):
                r=n.dump_size(p)
            self.assertEqual(r['rows'],1);self.assertFalse(r['finite_or_equivalence_proven'])
    def test_private_cache_and_log_auxiliary_budgets_include_dumps_and_driver_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);(root/'cache').mkdir();(root/'cuda-cache').mkdir()
            (root/'cache/slot').write_bytes(b'abc');(root/'logits.1.f32').write_bytes(b'1234');(root/'cuda-cache/kernel').write_bytes(b'xy')
            r=n.owned_storage_snapshot(root);self.assertEqual(r['cache_bytes'],3);self.assertEqual(r['log_and_auxiliary_bytes'],6)
            self.assertEqual(r['status'],'WITHIN_BUDGET')
            (root/'cache/slot').unlink();(root/'cache/slot').symlink_to(root/'logits.1.f32')
            with self.assertRaises(ValueError):n.owned_storage_snapshot(root)
    def test_stream_finite_rows_exact_hash_and_no_token_alignment_claim(self):
        with tempfile.TemporaryDirectory() as d,patch.object(n.storage,'ROW_BYTES',8):
            p=pathlib.Path(d)/'logits.1.f32';p.write_bytes(struct.pack('<ffff',1,2,3,4));r=n.finite_dump(p)
            self.assertEqual(r['rows'],2);self.assertEqual(r['bytes'],16);self.assertTrue(r['all_finite']);self.assertFalse(r['token_row_alignment_claimed'])
    def test_nonfinite_and_partial_rows_rejected(self):
        with tempfile.TemporaryDirectory() as d,patch.object(n.storage,'ROW_BYTES',8):
            p=pathlib.Path(d)/'logits.1.f32'
            for raw in (b'',b'abc',struct.pack('<ff',float('nan'),0),struct.pack('<ff',float('inf'),0)):
                p.write_bytes(raw)
                with self.assertRaises(ValueError):n.finite_dump(p)
    def test_symlink_and_unexpected_fifth_dump_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);p=root/'real';p.write_bytes(b'x');(root/'logits.1.f32').symlink_to(p)
            with self.assertRaises(ValueError):n.dump_snapshot(root)
            (root/'logits.1.f32').unlink()
            (root/'logits.5.f32').write_bytes(b'x')
            with self.assertRaises(ValueError):n.dump_snapshot(root)

class TransportControls(unittest.TestCase):
    def stream(self,finished=False):
        calls=[]
        class Stream:
            def __init__(self,*a,**kw):self.finished=SimpleNamespace(wait=lambda timeout:finished);self.thread=SimpleNamespace(is_alive=lambda:False)
            def start(self):calls.append('start');return self
            def cancel(self):calls.append('cancel')
            def result(self,timeout):calls.append('result');return response()
        return Stream,calls
    def test_unstarted_deadline_allocates_no_stream(self):
        S,calls=self.stream();r=n.bounded_request('',{},5,None,stream_class=S,observe=None,wait_for=None,clock=lambda:0)
        self.assertTrue(r['budget_not_started']);self.assertEqual(calls,[])
    def test_soft_dump_budget_cancels_once_releases_and_marks_incomplete(self):
        S,calls=self.stream()
        def wait(fn,timeout,why):self.assertTrue(fn());self.assertEqual(timeout,45)
        with patch.object(n,'dump_snapshot',return_value={'status':'INCOMPLETE_HOLD'}):
            r=n.bounded_request('',{},100,None,stream_class=S,observe=lambda *x:{'work':{'active':0,'queued':0,'admission_reserved':0}},wait_for=wait,clock=lambda:0)
        self.assertTrue(r['intentional_budget_stop']);self.assertFalse(r['retry']);self.assertEqual(calls,['start','cancel','result'])
    def test_natural_transport_completion_never_retries(self):
        S,calls=self.stream(True)
        with patch.object(n,'dump_snapshot',return_value={'status':'WITHIN_BUDGET'}),patch.object(n,'owned_storage_snapshot',return_value={'status':'WITHIN_BUDGET'}):
            self.assertEqual(n.bounded_request('',{},100,None,stream_class=S,observe=None,wait_for=None,clock=lambda:0),response())
        self.assertEqual(calls,['start','result'])
    def test_cache_log_budget_cancels_and_records_incomplete_without_retry(self):
        S,calls=self.stream()
        with patch.object(n,'dump_snapshot',return_value={'status':'WITHIN_BUDGET'}),patch.object(n,'owned_storage_snapshot',return_value={'status':'INCOMPLETE_HOLD'}):
            r=n.bounded_request('',{},100,None,stream_class=S,observe=lambda *x:{'work':{'active':0,'queued':0,'admission_reserved':0}},wait_for=lambda *a:None,clock=lambda:0)
        self.assertEqual(r['incomplete_reason'],'PRIVATE_CACHE_OR_LOG_LIMIT');self.assertEqual(calls.count('cancel'),1)

if __name__=='__main__':unittest.main()
