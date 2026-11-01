"""Actual saved selected92 STAT with malformed/foreign/stale/counter negatives; no native."""
import copy,hashlib,json,unittest
from pathlib import Path
import selected92_observer as o
HERE=Path(__file__).resolve().parent

class Observer(unittest.TestCase):
    def setUp(self):
        p=HERE/'recorded-native92-stat'
        self.req=json.loads((p/'request.json').read_text());self.trace=json.loads((p/'trace-receipt.json').read_text())
        self.n=json.loads((p/'native-statistics.json').read_text());self.receipt=json.loads((p/'stat-receipt.json').read_text())
        self.rows=[json.loads(x) for x in (p/'stat-lines.jsonl').read_text().splitlines()]
        self.pid=self.req['native_pid'];self.expected=copy.deepcopy(self.req['sampling']);self.ids=self.req['ids'][:]
    def run_contract(self,**kw):return o.contract(self.req,self.trace,self.n,self.receipt,self.rows,self.pid,self.expected,self.ids,**kw)
    def rehash(self):self.receipt['raw_lines_sha256']=hashlib.sha256(''.join(r['raw']+'\n' for r in self.rows).encode()).hexdigest()
    def test_actual_saved_selected92_STAT_and_DONE(self):
        r=self.run_contract();self.assertTrue(r['execution_proven']);self.assertIsNone(r['draft_rounds']);self.assertIsNone(r['draft_ms']);self.assertTrue(r['unavailable_native92_counters_not_inferred'])
    def test_exact_both_native_source_hashes(self):
        self.assertTrue(o.source_contract((HERE/'selected92-source/ds4_main.cpp').read_bytes(),(HERE/'selected92-source/ds4_model.cu').read_bytes()))
    def test_changed_source_refused(self):
        with self.assertRaises(ValueError):o.source_contract(b'changed',(HERE/'selected92-source/ds4_model.cu').read_bytes())
    def test_foreign_native_sha_refused(self):
        with self.assertRaises(ValueError):self.run_contract(native_sha256='a'*64)
    def test_foreign_request_PID_or_command_refused(self):
        for key,value in [('native_pid',self.pid+1),('max_new',256),('has_images',True)]:
            before=copy.deepcopy(self.req);self.req[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_contract()
            self.req=before
    def test_full_policy_and_exact_ID_drift_refused(self):
        self.expected['reasoning_effort']=99
        with self.assertRaises(ValueError):self.run_contract()
        self.expected=copy.deepcopy(self.req['sampling']);self.ids[0]+=1
        with self.assertRaises(ValueError):self.run_contract()
    def test_missing_DONE_error_or_T_mismatch_refused(self):
        for key,value in [('DONE_observed',False),('error','fault'),('T_lines',0),('native_pid',True)]:
            before=copy.deepcopy(self.trace);self.trace[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_contract()
            self.trace=before
    def test_bool_negative_inconsistent_or_cap_counters_refused(self):
        for key,value in [('generated',True),('generated',32768),('drafts_offered',False),('drafts_accepted',-1),('drafts_accepted',self.n['drafts_offered']+1),('finish','length'),('prompt_tokens',1)]:
            before=copy.deepcopy(self.n);self.n[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_contract()
            self.n=before
    def test_zero_offered_never_proves_execution(self):
        self.n.update(drafts_offered=0,drafts_accepted=0)
        for row in self.rows:row['raw']=' '.join('drafts=0.000' if part.startswith('drafts=') else part for part in row['raw'].split())
        self.rehash()
        with self.assertRaises(ValueError):self.run_contract()
        self.assertFalse(self.run_contract(required=False)['execution_proven'])
    def test_zero_acceptance_valid_with_actual_offered_and_ratio(self):
        self.n['drafts_accepted']=0
        for row in self.rows:row['raw']=' '.join('drafts=0.000' if part.startswith('drafts=') else part for part in row['raw'].split())
        self.rehash()
        self.assertTrue(self.run_contract()['execution_proven'])
    def test_wrong_final_STAT_ratio_refused(self):
        self.rows[-1]['raw']=' '.join('drafts=0.000' if part.startswith('drafts=') else part for part in self.rows[-1]['raw'].split());self.rehash()
        with self.assertRaises(ValueError):self.run_contract()
    def test_receipt_foreign_incomplete_or_count_refused(self):
        for key,value in [('native_pid',self.pid+1),('trace_number',1),('samples',0),('complete',False),('DONE_observed',False),('capture_error','fault'),('raw_lines_sha256','a'*64)]:
            before=copy.deepcopy(self.receipt);self.receipt[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_contract()
            self.receipt=before
    def test_STAT_foreign_PID_trace_clock_and_nonfinite_refused(self):
        for key,value in [('native_pid',self.pid+1),('trace_number',1),('seconds',-1.),('seconds',float('nan'))]:
            before=copy.deepcopy(self.rows);self.rows[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_contract()
            self.rows=before
        self.rows[-1]['seconds']=0.
        with self.assertRaises(ValueError):self.run_contract()
    def test_duplicate_field_injected_newline_and_nonfinite_STAT_refused(self):
        for raw in [self.rows[-1]['raw']+' drafts=1',self.rows[-1]['raw']+'\nSTAT x=1',self.rows[-1]['raw']+' forged=nan']:
            old=self.rows[-1]['raw'];self.rows[-1]['raw']=raw;self.rehash()
            with self.assertRaises(ValueError):self.run_contract()
            self.rows[-1]['raw']=old
    def test_duplicate_or_nonfinite_JSON_refused(self):
        for raw in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):o.parsed(raw)
    def test_empty_saved_samples_refused(self):
        self.rows=[];self.receipt['samples']=0;self.rehash()
        with self.assertRaises(ValueError):self.run_contract()

if __name__=='__main__':unittest.main()
