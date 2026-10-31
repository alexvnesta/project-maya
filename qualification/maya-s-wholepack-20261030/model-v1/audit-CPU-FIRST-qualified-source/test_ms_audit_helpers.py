"""Prospective independent helper negatives. No live endpoints or model access."""
import copy
import unittest
import ms_audit as a


def pair():
    baseline={'mode':'prose','accepted':True,'main_metric':{'generated_tokens':2000,'native_decode_tps':50.},
              'cold_metric':{'prompt_tokens':8000,'prompt_ms':1000.}}
    candidate=copy.deepcopy(baseline);candidate['main_metric']['native_decode_tps']=53.
    return baseline,candidate


class Helpers(unittest.TestCase):
    def test_matched_natural_decode_gain_and_prefill_screen(self):
        x,y=pair();r=a.compare_pair(x,y);self.assertTrue(r['screen_passed']);self.assertFalse(r['deployment_authorized'])

    def test_output_lengths_are_kept_not_normalized_away(self):
        x,y=pair();y['main_metric']['generated_tokens']=3000
        self.assertEqual(a.compare_pair(x,y)['output_tokens'],{'baseline':2000,'candidate':3000})

    def test_unmatched_prompts_cannot_pass_prefill_gate(self):
        x,y=pair();y['cold_metric']['prompt_tokens']=8001
        r=a.compare_pair(x,y);self.assertFalse(r['screen_passed']);self.assertIsNone(r['cold_prefill_change_percent'])

    def test_decode_regression_blocks(self):
        x,y=pair();y['main_metric']['native_decode_tps']=49.
        self.assertFalse(a.compare_pair(x,y)['screen_passed'])

    def test_prefill_regression_blocks(self):
        x,y=pair();y['cold_metric']['prompt_ms']=1040.
        self.assertFalse(a.compare_pair(x,y)['screen_passed'])

    def test_nonfinite_or_boolean_primary_rates_refused(self):
        for value in (float('nan'),float('inf'),float('-inf'),True,0,-1):
            for index in (0,1):
                items=pair();items[index]['main_metric']['native_decode_tps']=value
                with self.subTest(index=index,value=value),self.assertRaises(ValueError):a.compare_pair(*items)

    def test_nonfinite_or_boolean_prefill_metrics_refused(self):
        for value in (float('nan'),float('inf'),True,0,-1):
            items=pair();items[1]['cold_metric']['prompt_ms']=value
            with self.subTest(value=value),self.assertRaises(ValueError):a.compare_pair(*items)

    def test_wrong_capped_or_boolean_output_count_refused(self):
        for value in (True,0,1,32768,32769,2000.):
            items=pair();items[1]['main_metric']['generated_tokens']=value
            with self.subTest(value=value),self.assertRaises(ValueError):a.compare_pair(*items)

    def test_wrong_prompt_count_type_refused(self):
        items=pair();items[1]['cold_metric']['prompt_tokens']=True
        with self.assertRaises(ValueError):a.compare_pair(*items)

    def test_unreviewed_or_cross_family_result_refused(self):
        for field,value in (('accepted',False),('mode','coding')):
            items=pair();items[1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):a.compare_pair(*items)

    def test_resource_counter_and_floor_exact(self):
        samples=[{'root_free_bytes':130*2**30,'swap_pages':{'pswpout':10}},
                 {'root_free_bytes':120*2**30,'swap_pages':{'pswpout':11}}]
        self.assertEqual(a.resource_contract(samples,4096)['system_swapout_delta_bytes'],4096)
        samples[1]['root_free_bytes']-=1
        with self.assertRaises(ValueError):a.resource_contract(samples,4096)

    def test_swap_limit_and_regression_refused(self):
        for value in (9,10+2**18):
            samples=[{'root_free_bytes':130*2**30,'swap_pages':{'pswpout':10}},
                     {'root_free_bytes':130*2**30,'swap_pages':{'pswpout':value}}]
            with self.subTest(value=value),self.assertRaises(ValueError):a.resource_contract(samples,4096)

    def test_public_READY_can_span_serialized_chunks(self):
        raw='data: {"choices":[{"delta":{"content":"READ"},"finish_reason":null}]}\n'
        raw+='data: {"choices":[{"delta":{"content":"Y"},"finish_reason":"stop"}]}\ndata: [DONE]\n'
        self.assertEqual(a.assembled_ready(raw)['content'],'READY')


if __name__=='__main__':unittest.main()
