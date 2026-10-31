"""CPU-only exact factor and native process contract controls."""
import copy,json,pathlib,unittest
import imma_config as c
class Configuration(unittest.TestCase):
    def setUp(self):self.base=json.loads((pathlib.Path(__file__).parent/'base-config.json').read_text())
    def directory(self,mode='numerical',arm='N0'):
        return c.E/'results'/('decode-imma-'+mode+'-'+arm+'-20261029T010203Z')/'native'
    def test_selected_exact_baseline(self):self.assertTrue(c.selected_base(self.base))
    def test_all_six_exact_factors(self):
        for mode,arms in c.MODES.items():
            for arm in arms:
                f=c.factor(mode,arm);v=c.make_config(self.base,self.directory(mode,arm),mode,arm)
                self.assertEqual(v['exe'],f['exe']);self.assertEqual(v['env']['STRATA_DS4_Q5K_IMMA'],str(f['minimum_columns']))
                self.assertEqual(v['env']['DS4_Q5K_IMMA'],str(f['minimum_columns']))
                self.assertEqual(v['hosted_default_effort'],100);self.assertEqual(self.base['args'][self.base['args'].index('--prefill-chunk')+1],'4096')
                self.assertEqual('DS4_SERVE_DUMP' in v['env'],mode=='numerical')
    def test_original_value_not_mutated(self):
        before=copy.deepcopy(self.base);c.make_config(self.base,self.directory(),'numerical','N0');self.assertEqual(self.base,before)
    def test_extra_knob_rejected(self):
        self.base['env']['DS4_OTHER']='1'
        with self.assertRaises(ValueError):c.selected_base(self.base)
    def test_context_reduction_rejected(self):
        self.base['args'][self.base['args'].index('--max-context')+1]='524288'
        with self.assertRaises(ValueError):c.selected_base(self.base)
    def test_effort_reduction_rejected(self):
        self.base['hosted_default_effort']=50
        with self.assertRaises(ValueError):c.selected_base(self.base)
    def test_no_native_promotion_or_factor_switch(self):
        for mode,arms in c.MODES.items():
            for arm in arms:
                if arm in ['N0','A1','A2']:
                    self.assertEqual(c.factor(mode,arm)['native_sha256'],c.BASE_NATIVE)
                    self.assertEqual(c.factor(mode,arm)['exe'],str(c.D/'bin/maya-ds4'))
                else:self.assertEqual(c.factor(mode,arm)['native_sha256'],c.CANDIDATE_NATIVE)
    def test_wrong_mode_arm_pair_rejected(self):
        for mode,arm in [('numerical','B1'),('performance','N0'),('other','A1'),('performance',True)]:
            with self.assertRaises(ValueError):c.factor(mode,arm)
    def test_foreign_namespace_rejected(self):
        with self.assertRaises(ValueError):c.make_config(self.base,pathlib.Path('/tmp/native'),'numerical','N0')
    def test_traversal_namespace_rejected(self):
        with self.assertRaises(ValueError):c.native_directory(c.E/'results/../results/decode-imma-numerical-N0-20261029T010203Z/native','numerical','N0')
    def test_wrong_arm_namespace_rejected(self):
        with self.assertRaises(ValueError):c.make_config(self.base,self.directory('numerical','N0'),'numerical','N1')
    def test_hidden_factor_in_private_config_rejected(self):
        d=self.directory();v=c.make_config(self.base,d,'numerical','N0');v['env']['DS4_OTHER']='1'
        with self.assertRaises(ValueError):c.check_config(self.base,v,d,'numerical','N0')
    def test_private_integer_float_substitution_rejected(self):
        d=self.directory();v=c.make_config(self.base,d,'numerical','N0');v['hosted_default_effort']=100.0
        with self.assertRaises(ValueError):c.check_config(self.base,v,d,'numerical','N0')
    def test_private_bool_integer_substitution_rejected(self):
        d=self.directory();v=c.make_config(self.base,d,'numerical','N0');v['gpus_asked']=1
        with self.assertRaises(ValueError):c.check_config(self.base,v,d,'numerical','N0')
    def test_dump_not_allowed_in_timed_config(self):
        d=self.directory('performance','B1');v=c.make_config(self.base,d,'performance','B1');v['env']['DS4_SERVE_DUMP']='file'
        with self.assertRaises(ValueError):c.check_config(self.base,v,d,'performance','B1')
    def test_alias_disagreement_rejected(self):
        d=self.directory('numerical','N1');v=c.make_config(self.base,d,'numerical','N1');v['env']['STRATA_DS4_Q5K_IMMA']='0'
        with self.assertRaises(ValueError):c.check_config(self.base,v,d,'numerical','N1')
    def test_projection_or_model_replacement_rejected(self):
        self.base['exe']='/foreign/model'
        with self.assertRaises(ValueError):c.selected_base(self.base)

class NativeProcess(unittest.TestCase):
    def setUp(self):
        base=json.loads((pathlib.Path(__file__).parent/'base-config.json').read_text())
        self.config=c.make_config(base,c.E/'results/decode-imma-numerical-N1-20261029T010203Z/native','numerical','N1')
        self.argv=c.expected_native_argv(self.config);self.env=dict(self.config['env']);self.group='0::/user.slice/app.slice/strata-deepseek-window.service\n'
    def test_complete_bound_process(self):
        self.assertTrue(c.process_contract(self.config,self.argv,self.env,self.group,same_executable=True)['argv_matches'])
    def test_foreign_executable_rejected(self):
        with self.assertRaises(ValueError):c.process_contract(self.config,self.argv,self.env,self.group,same_executable=False)
    def test_nonwindow_group_rejected(self):
        with self.assertRaises(ValueError):c.process_contract(self.config,self.argv,self.env,self.group+'-other',same_executable=True)
    def test_foreign_argv_rejected(self):
        with self.assertRaises(ValueError):c.process_contract(self.config,self.argv+['--extra'],self.env,self.group,same_executable=True)
    def test_unfrozen_MAYA_alias_rejected(self):
        self.env['MAYA_DS4_Q5K_IMMA']='1'
        with self.assertRaises(ValueError):c.process_contract(self.config,self.argv,self.env,self.group,same_executable=True)
    def test_actual_factor_mismatch_rejected(self):
        self.env['DS4_Q5K_IMMA']='0'
        with self.assertRaises(ValueError):c.process_contract(self.config,self.argv,self.env,self.group,same_executable=True)
    def test_unrelated_env_not_exported(self):
        self.env['UNRELATED_PRIVATE']='never-record'
        got=c.controlled_environment(self.env);self.assertNotIn('UNRELATED_PRIVATE',got)
    def test_layer_override_rejected(self):
        self.config['args']+=['--layer-split','20,20']
        with self.assertRaises(ValueError):c.expected_native_argv(self.config)
    def test_activation_required_only_on_candidate_after_requests(self):
        line='ds4: Q5_K GEMVs of >= 2 activations on the int8 tensor cores (DS4_Q5K_IMMA)'
        self.assertTrue(c.factor_activation(line,'numerical','N1')['eligible_flag_observed'])
        self.assertFalse(c.factor_activation('','numerical','N0')['per_model_kernel_launch_count_observed'])
        for mode,arm,log in [('numerical','N1',''),('numerical','N0',line),('performance','B1',line+'\n'+line)]:
            with self.assertRaises(ValueError):c.factor_activation(log,mode,arm)

if __name__=='__main__':unittest.main()
