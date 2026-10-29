"""New exact short fixture controls. One explicitly admitted actual CPU encoding."""
import copy,unittest
import iq2s_explore_fixtures as f
BUILT_MANIFEST=None

def synthetic_manifest():
    cases=f.make_cases()
    for c in cases:
        ids=[7]*1200;c.update(prompt_ids=ids,prompt_tokens=len(ids),prompt_ids_sha256=f.digest(f.packed(ids)),
                            request_sha256=f.digest(f.packed(c['request'])),image_spans=[])
    return {'id':'iq2s-exploratory-sequence1024-v1','purpose':f.PURPOSE,'context':1048576,'default_output':262144,
            'policy':dict(f.POLICY),'cases':cases,'prior_numerical_HOLD':True,'promotion_allowed':False,
            'GPU_launch_ready':False,'API_sha256':f.SERVER_SHA,'expected_reuse_tokens':[0,1199],
            'expected_mode1_activation_skipped_tokens':[],'canonical_answer_tokens':2051}

class Fixtures(unittest.TestCase):
    def test_exact_two_requests_same_visible_task_and_policy(self):
        cases=f.make_cases();self.assertEqual(cases[0]['request'],cases[1]['request'])
        self.assertEqual(cases[0]['expected']['values'],list(range(1,1025)))
        self.assertEqual(cases[0]['request']['max_tokens'],32768);self.assertEqual(cases[0]['request']['reasoning_effort'],100)
        self.assertEqual(cases[0]['request']['messages'][0]['content'].count(f.prior.LINE),80)
        self.assertIs(f.validate_requests(cases),cases)
    def test_old64_four_cases_changed_arms_or_missing_case_refused(self):
        for cases in [f.make_cases()[:1],f.make_cases()*2]:
            with self.assertRaises(ValueError):f.validate_requests(cases)
        cases=f.make_cases();cases[0]['expected']['values']=list(range(1,65))
        with self.assertRaises(ValueError):f.validate_requests(cases)
    def test_caps_effort_sampler_types_and_extra_keys_refused(self):
        for key,value in [('max_tokens',64),('reasoning_effort',100.0),('temperature',0),('seed',2),('extra',1)]:
            cases=f.make_cases();cases[0]['request'][key]=value
            with self.assertRaises(ValueError):f.validate_requests(cases)
    def test_synthetic_encoded_contract_with_exact_cache(self):
        m=synthetic_manifest();self.assertIs(f.validate_manifest(m),m)
    def test_prompt_bounds_and_bool_ids_never_autoresized(self):
        for ids in ([7]*1023,[7]*2049,[True]*1200,[129280]*1200):
            m=synthetic_manifest();c=m['cases'][0];c['prompt_ids']=ids;c['prompt_tokens']=len(ids);c['prompt_ids_sha256']=f.digest(f.packed(ids))
            with self.assertRaises(ValueError):f.validate_manifest(m)
    def test_warm_mutation_and_image_tokens_refused(self):
        for value in (8,129264):
            m=synthetic_manifest();c=m['cases'][1];c['prompt_ids'][0]=value;c['prompt_ids_sha256']=f.digest(f.packed(c['prompt_ids']))
            with self.assertRaises(ValueError):f.validate_manifest(m)
    def test_answer_token_budget_and_diagnostic_invariants(self):
        for key,value in [('canonical_answer_tokens',4097),('canonical_answer_tokens',True),('promotion_allowed',True),
                          ('prior_numerical_HOLD',False),('context',524288),('default_output',32768),('GPU_launch_ready',True)]:
            m=synthetic_manifest();m[key]=value
            with self.assertRaises(ValueError):f.validate_manifest(m)
    def test_z_FIRST_actual_CPU_encoding_once_retained_for_HTTP_and_receipt(self):
        global BUILT_MANIFEST
        self.assertIsNone(BUILT_MANIFEST)
        BUILT_MANIFEST=f.build_manifest()
        self.assertTrue(1024<=BUILT_MANIFEST['cases'][0]['prompt_tokens']<=2048)
        self.assertLessEqual(BUILT_MANIFEST['canonical_answer_tokens'],4096)
        self.assertEqual(BUILT_MANIFEST['cases'][0]['prompt_ids'],BUILT_MANIFEST['cases'][1]['prompt_ids'])
        self.assertFalse(BUILT_MANIFEST['promotion_allowed'])

if __name__=='__main__':unittest.main()
