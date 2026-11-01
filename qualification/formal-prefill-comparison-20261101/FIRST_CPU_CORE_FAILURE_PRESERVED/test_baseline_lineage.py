"""Accepted baseline92 raw finite/workload authority; no tensor reads or native use."""
import copy,json,unittest
from pathlib import Path
import baseline_lineage as b
class Lineage(unittest.TestCase):
    def docs(self):
        f=json.loads((b.HERE/'BASELINE_LINEAGE_FROZEN.json').read_text())
        return {k:json.loads((b.E/r['relative_to_E']).read_text()) for k,r in f.items()}
    def test_actual_baseline_accepted_finite_and_literal_common_workload(self):self.assertTrue(b.contract(**self.docs()))
    def test_unreviewed_failed_or_wrong_review_refused(self):
        for key,val in [('accepted',False),('fully_reviewed',False),('arm','QS1'),('decision','OTHER')]:
            d=self.docs();d['review'][key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):b.contract(**d)
    def test_actual_native_or_qualification_mismatch_refused(self):
        for key,val in [('passed',False),('arm','QS1'),('qualification_sha256','a'*64)]:
            d=self.docs();d['audit'][key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):b.contract(**d)
        d=self.docs();d['audit']['whole_pack_factor']['native_sha256']='a'*64
        with self.assertRaises(ValueError):b.contract(**d)
    def test_partial_nonfinite_or_false_row_alignment_refused(self):
        for key,val in [('all_finite',False),('rows',True),('bytes',1),('token_row_alignment_claimed',True),('sha256','bad')]:
            d=self.docs();d['audit']['rows'][0]['dump'][key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):b.contract(**d)
    def test_wrong_answer_or_incomplete_prior_execution_refused(self):
        for key,val in [('typed_known_answer_correct',False),('natural_stop',False)]:
            d=self.docs();d['audit']['rows'][0][key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):b.contract(**d)
    def test_request_or_actual_ID_substitution_refused(self):
        d=self.docs();d['fixtureB']['cases'][0]['request']['max_tokens']=1024
        with self.assertRaises(ValueError):b.contract(**d)
        d=self.docs();d['fixtureB']['cases'][0]['prompt_ids'][0]+=1
        with self.assertRaises(ValueError):b.contract(**d)
    def test_prior_instrumented_time_not_promotion_or_fresh_timing(self):
        for key in ('performance_claim','deployment_admitted'):
            d=self.docs();d['audit'][key]=True
            with self.assertRaises(ValueError):b.contract(**d)
    def test_missing_private_cleanup_or_wrong_fence_refused(self):
        for key,val in [('passed',False),('swap_max',1),('swap_max',False),('transient_collected',False)]:
            d=self.docs();d['audit']['private_fence'][key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):b.contract(**d)
if __name__=='__main__':unittest.main()
