"""Exact B1 full policy and fresh private namespace. Pure config controls."""
import copy
import json
from pathlib import Path
import unittest
import ae_config as c
import ae_runtime as r

BASE = r.E / 'decode-optimization-20261028/model-v1/base-config.json'

class Config(unittest.TestCase):
    def setUp(self):
        self.base=json.loads(BASE.read_text())
        self.folder=c.E/'results/adaptive-cache-prose-v1-B1-20261030T220000Z/native'

    def test_two_pack_factors_share_selected_native(self):
        self.assertEqual(c.MODE_ARMS,{'prose':('A1','B1')})
        self.assertEqual(c.factor('prose','B1')['native_sha256'],c.BASE_NATIVE)
        self.assertTrue(c.factor('prose','B1')['candidate'])
        self.assertEqual(c.factor('prose','A1')['pack'],c.factor('prose','B1')['pack'])
        self.assertEqual(c.factor('prose','B1')['adaptive_cache_policy'],'current-adaptive')

    def test_full_policy_candidate_pack_and_original_baseline_untouched(self):
        before=copy.deepcopy(self.base);value=c.make_config(self.base,self.folder,'prose','B1')
        self.assertEqual(self.base,before);self.assertTrue(c.check_config(self.base,value,self.folder,'prose','B1'))
        self.assertEqual(value['args'][value['args'].index('--max-context')+1],'1048576')
        self.assertEqual(value['hosted_default_effort'],100)
        self.assertEqual(value['tokenizer'],self.base['tokenizer'])
        self.assertNotIn('DS4_SERVE_DUMP',value['env']);self.assertNotIn('max_tokens',value)

    def test_other_mode_arm_rejected(self):
        for mode,arm in [('prose','A2'),('prose','B2'),('coding','A1'),('longcold','LC1'),('compatibility','CS1'),('prose','QS2'),('quality','QS1')]:
            with self.subTest(mode=mode),self.assertRaises(ValueError):c.factor(mode,arm)

    def test_config_numeric_type_change_refused(self):
        value=c.make_config(self.base,self.folder,'prose','B1');value['hosted_default_effort']=100.0
        with self.assertRaises(ValueError):c.check_config(self.base,value,self.folder,'prose','B1')

    def test_context_reduction_refused(self):
        for flag in ('--max-context',):
            value=c.make_config(self.base,self.folder,'prose','B1')
            value['args'][value['args'].index(flag)+1]='262144'
            with self.assertRaises(ValueError):c.check_config(self.base,value,self.folder,'prose','B1')

    def test_baseline_tokenizer_substitution_refused(self):
        value=c.make_config(self.base,self.folder,'prose','B1');value['tokenizer']='/foreign/tokenizer'
        with self.assertRaises(ValueError):c.check_config(self.base,value,self.folder,'prose','B1')

    def test_dump_or_optimization_flag_refused(self):
        for key in ('DS4_SERVE_DUMP','DS4_Q8_SHARE','DS4_HEAD_BATCH','DS4_CACHE_REUSE_MIB','DS4_CACHE_MARGIN','DS4_PROF','DS4_CHECK_SWAPS'):
            value=c.make_config(self.base,self.folder,'prose','B1');value['env'][key]='1'
            with self.assertRaises(ValueError):c.check_config(self.base,value,self.folder,'prose','B1')

    def test_foreign_namespace_refused(self):
        with self.assertRaises(ValueError):c.make_config(self.base,c.E/'results/old-CS1/native','prose','B1')

    def test_exact_native_process_contract(self):
        value=c.make_config(self.base,self.folder,'prose','B1')
        result=c.process_contract(value,c.expected_native_argv(value),value['env'],
            '/user.slice/strata-deepseek-window.service',same_executable=True)
        self.assertTrue(result['owned_window_cgroup'])

    def test_foreign_process_or_env_refused(self):
        value=c.make_config(self.base,self.folder,'prose','B1');argv=c.expected_native_argv(value)
        for group,same,env in [('/production.service',True,value['env']),
                             ('/strata-deepseek-window.service',False,value['env']),
                             ('/strata-deepseek-window.service',True,{**value['env'],'DS4_Q8_SHARE':'1'})]:
            with self.subTest(group=group),self.assertRaises(ValueError):c.process_contract(value,argv,env,group,same_executable=same)

    def test_baseline_pack_and_tokenizer_unchanged_but_without_timed_dump(self):
        folder=c.E/'results/adaptive-cache-prose-v1-A1-20261030T220000Z/native'
        value=c.make_config(self.base,folder,'prose','A1')
        self.assertFalse(c.factor('prose','A1')['candidate'])
        self.assertEqual(value['args'].count('--no-expert-cache'),1)
        self.assertEqual(value['tokenizer'],self.base['tokenizer'])
        self.assertEqual(value['args'][value['args'].index('--pack')+1],str(c.BASE_PACK))
        self.assertNotIn('DS4_SERVE_DUMP',value['env'])

    def test_missing_or_extra_fixed_flag_refused(self):
        for arm in ('A1','B1'):
            folder=c.E/('results/adaptive-cache-prose-v1-'+arm+'-20261030T220000Z/native')
            value=c.make_config(self.base,folder,'prose',arm)
            if arm=='A1':value['args'].remove('--no-expert-cache')
            else:value['args'].append('--no-expert-cache')
            with self.assertRaises(ValueError):c.check_config(self.base,value,folder,'prose',arm)

    def test_old_prose_namespace_refused(self):
        with self.assertRaises(ValueError):
            c.make_config(self.base,c.E/'results/maya-s-prose-B1-20261030T220000Z/native','prose','B1')

if __name__=='__main__':unittest.main()
