"""Descriptive-rate controls: no tolerance, selection threshold or speed acceptance."""
import copy,unittest
import iq2s_explore_summary as s

def pair():
    result=[]
    for arm,generated,decode,client in [('X0',2000,50000,54),('X1',2400,48000,52)]:
        rows=[]
        for i,name in enumerate(s.fixtures.IDS):
            native={'generated':generated,'decode_ms':decode,'prompt_ms':2000,'prompt_tokens':1200,'reused':1199 if i else 0,
                    'drafts_offered':100,'drafts_accepted':80,'hits':90,'lookups':100,'finish':'stop'}
            r={'id':name,'native':native,'tokens':[7]*generated,'natural_stop':True,'typed_answer_correct':True}
            response={'client_full_seconds':client,'client_first_content_seconds':client-.01,'client_first_reasoning_seconds':client-.01,
                      'client_first_tool_seconds':None,'content':'synthetic','reasoning':'synthetic reasoning'}
            r['observations']=s.observation(r,response);rows.append(r)
        result.append({'passed':True,'arm':arm,'purpose':s.fixtures.PURPOSE,'prior_numerical_HOLD':True,'promotion_allowed':False,'rows':rows})
    return result

class Summary(unittest.TestCase):
    def test_variable_generated_length_kept_without_matched_token_speedup(self):
        a,b=pair();r=s.compare(a,b)
        self.assertTrue(r['prior_numerical_HOLD']);self.assertFalse(r['promotion_allowed']);self.assertFalse(r['speed_acceptance'])
        self.assertFalse(r['rows'][0]['emitted_paths_identical']);self.assertAlmostEqual(r['rows'][0]['diagnostic_native_rate_ratio'],1.25)
        self.assertAlmostEqual(r['rows'][0]['fixed_known_answer_client_latency_ratio'],52/54)
        self.assertFalse(r['rows'][0]['matched_token_speedup_claim'])
    def test_identical_path_still_no_acceptance_or_replication(self):
        a,b=pair();b['rows']=copy.deepcopy(a['rows']);r=s.compare(a,b)
        self.assertTrue(r['rows'][0]['emitted_paths_identical']);self.assertFalse(r['speed_acceptance']);self.assertFalse(r['replication_authorized'])
    def test_bad_mode_missing_reordered_or_regraded_input_refused(self):
        for key,value in [('prior_numerical_HOLD',False),('promotion_allowed',True),('arm','N1'),('passed',False)]:
            a,b=pair();b[key]=value
            with self.assertRaises(ValueError):s.compare(a,b)
        a,b=pair();b['rows'].reverse()
        with self.assertRaises(ValueError):s.compare(a,b)
    def test_cache_difference_and_wrong_or_partial_answer_refused(self):
        for key,value in [('natural_stop',False),('typed_answer_correct',False)]:
            a,b=pair();b['rows'][1][key]=value
            with self.assertRaises(ValueError):s.compare(a,b)
        a,b=pair();b['rows'][1]['native']['reused']=0
        with self.assertRaises(ValueError):s.compare(a,b)
    def test_nonfinite_bool_or_zero_denominator_refused(self):
        for value in (0,True,float('nan'),float('inf'),-1):
            a,b=pair();b['rows'][0]['observations']['native_tokens_per_second']=value
            with self.assertRaises(ValueError):s.compare(a,b)
    def test_buffered_visible_delta_not_real_TTFT(self):
        a,b=pair();o=a['rows'][0]['observations'];self.assertFalse(o['actual_TTFT_proven'])
        self.assertEqual(o['buffered_first_visible_delta_seconds']['client_first_content_seconds'],53.99)
    def test_token_count_and_nonfinite_native_metrics_refused(self):
        a,b=pair();row=a['rows'][0];response={'client_full_seconds':1,'content':'x','reasoning':''}
        for key,value in [('generated',True),('decode_ms',0),('decode_ms',float('nan')),('prompt_ms',-1)]:
            bad=copy.deepcopy(row);bad['native'][key]=value
            with self.assertRaises(ValueError):s.observation(bad,response)
        with self.assertRaises(ValueError):s.observation(row,{**response,'client_first_content_seconds':2})

if __name__=='__main__':unittest.main()
