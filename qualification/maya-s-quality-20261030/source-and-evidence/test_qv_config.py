"""Exact QS1 full policy and fresh private namespace. Pure config controls."""
import copy
import json
from pathlib import Path
import unittest
import qv_config as c
import qv_runtime as r

BASE = r.E / 'decode-optimization-20261028/model-v1/base-config.json'

class Config(unittest.TestCase):
    def setUp(self):
        self.base=json.loads(BASE.read_text())
        self.folder=c.E/'results/maya-s-quality-v2-QS1-20261030T220000Z/native'

    def test_two_pack_factors_share_selected_native(self):
        self.assertEqual(c.MODE_ARMS,{'quality':('QS0','QS1')})
        self.assertEqual(c.factor('quality','QS1')['native_sha256'],c.BASE_NATIVE)
        self.assertTrue(c.factor('quality','QS1')['candidate'])

    def test_full_policy_candidate_pack_and_original_baseline_untouched(self):
        before=copy.deepcopy(self.base);value=c.make_config(self.base,self.folder,'quality','QS1')
        self.assertEqual(self.base,before);self.assertTrue(c.check_config(self.base,value,self.folder,'quality','QS1'))
        self.assertEqual(value['args'][value['args'].index('--max-context')+1],'1048576')
        self.assertEqual(value['hosted_default_effort'],100)
        self.assertEqual(value['tokenizer'],str(c.CANDIDATE_PACK/'tokenizer'))
        self.assertEqual(value['env']['DS4_SERVE_DUMP'],str(self.folder/'logits'));self.assertNotIn('max_tokens',value)

    def test_other_mode_arm_rejected(self):
        for mode,arm in [('longcold','LC1'),('compatibility','CS1'),('quality','QS2'),('prose','B1')]:
            with self.subTest(mode=mode),self.assertRaises(ValueError):c.factor(mode,arm)

    def test_config_numeric_type_change_refused(self):
        value=c.make_config(self.base,self.folder,'quality','QS1');value['hosted_default_effort']=100.0
        with self.assertRaises(ValueError):c.check_config(self.base,value,self.folder,'quality','QS1')

    def test_context_reduction_refused(self):
        for flag in ('--max-context',):
            value=c.make_config(self.base,self.folder,'quality','QS1')
            value['args'][value['args'].index(flag)+1]='262144'
            with self.assertRaises(ValueError):c.check_config(self.base,value,self.folder,'quality','QS1')

    def test_baseline_tokenizer_substitution_refused(self):
        value=c.make_config(self.base,self.folder,'quality','QS1');value['tokenizer']=self.base['tokenizer']
        with self.assertRaises(ValueError):c.check_config(self.base,value,self.folder,'quality','QS1')

    def test_dump_or_optimization_flag_refused(self):
        for key in ('DS4_SERVE_DUMP','DS4_Q8_SHARE','DS4_HEAD_BATCH'):
            value=c.make_config(self.base,self.folder,'quality','QS1');value['env'][key]='1'
            with self.assertRaises(ValueError):c.check_config(self.base,value,self.folder,'quality','QS1')

    def test_foreign_namespace_refused(self):
        with self.assertRaises(ValueError):c.make_config(self.base,c.E/'results/old-CS1/native','quality','QS1')

    def test_exact_native_process_contract(self):
        value=c.make_config(self.base,self.folder,'quality','QS1')
        result=c.process_contract(value,c.expected_native_argv(value),value['env'],
            '/user.slice/strata-deepseek-window.service',same_executable=True)
        self.assertTrue(result['owned_window_cgroup'])

    def test_foreign_process_or_env_refused(self):
        value=c.make_config(self.base,self.folder,'quality','QS1');argv=c.expected_native_argv(value)
        for group,same,env in [('/production.service',True,value['env']),
                             ('/strata-deepseek-window.service',False,value['env']),
                             ('/strata-deepseek-window.service',True,{**value['env'],'DS4_Q8_SHARE':'1'})]:
            with self.subTest(group=group),self.assertRaises(ValueError):c.process_contract(value,argv,env,group,same_executable=same)

    def test_baseline_pack_and_tokenizer_unchanged_but_private_dump_owned(self):
        folder=c.E/'results/maya-s-quality-v2-QS0-20261030T220000Z/native'
        value=c.make_config(self.base,folder,'quality','QS0')
        self.assertFalse(c.factor('quality','QS0')['candidate'])
        self.assertEqual(value['tokenizer'],self.base['tokenizer'])
        self.assertEqual(value['args'][value['args'].index('--pack')+1],str(c.BASE_PACK))
        self.assertEqual(value['env']['DS4_SERVE_DUMP'],str(folder/'logits'))

    def test_old_quality_namespace_refused(self):
        with self.assertRaises(ValueError):
            c.make_config(self.base,c.E/'results/maya-s-quality-QS1-20261030T220000Z/native','quality','QS1')

if __name__=='__main__':unittest.main()
