"""CPU-only exact factor and native process contract controls."""
import copy,json,pathlib,unittest
import cpu_model_config as c
class Configuration(unittest.TestCase):
    def setUp(self):self.base=json.loads((pathlib.Path(__file__).parent/'base-config.json').read_text())
    def directory(self,mode='numerical',arm='N0'):
        return c.E/'results'/('decode-cpu-iq2xs-'+mode+'-'+arm+'-20261029T010203Z')/'native'
    def test_selected_exact_baseline(self):self.assertTrue(c.selected_base(self.base))
    def test_both_exact_numerical_factors(self):
        for mode,arms in c.MODES.items():
            for arm in arms:
                f=c.factor(mode,arm);v=c.make_config(self.base,self.directory(mode,arm),mode,arm)
                self.assertEqual(v['exe'],f['exe']);self.assertEqual(f['CPU_IQ2XS_candidate'],arm=='N1')
                self.assertNotIn('STRATA_DS4_IQ_PERSIST',v['env']);self.assertNotIn('DS4_IQ_PERSIST',v['env'])
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
        with self.assertRaises(ValueError):c.native_directory(c.E/'results/../results/decode-cpu-iq2xs-numerical-N0-20261029T010203Z/native','numerical','N0')
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
    def test_performance_mode_is_not_admitted(self):
        with self.assertRaises(ValueError):c.factor('performance','B1')
    def test_alias_disagreement_rejected(self):
        d=self.directory('numerical','N1');v=c.make_config(self.base,d,'numerical','N1');v['env']['STRATA_DS4_IQ_PERSIST']='0'
        with self.assertRaises(ValueError):c.check_config(self.base,v,d,'numerical','N1')
    def test_projection_or_model_replacement_rejected(self):
        self.base['exe']='/foreign/model'
        with self.assertRaises(ValueError):c.selected_base(self.base)

class NativeProcess(unittest.TestCase):
    def setUp(self):
        base=json.loads((pathlib.Path(__file__).parent/'base-config.json').read_text())
        self.config=c.make_config(base,c.E/'results/decode-cpu-iq2xs-numerical-N1-20261029T010203Z/native','numerical','N1')
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
        self.env['MAYA_DS4_IQ_PERSIST']='1'
        with self.assertRaises(ValueError):c.process_contract(self.config,self.argv,self.env,self.group,same_executable=True)
    def test_actual_factor_mismatch_rejected(self):
        self.env['DS4_IQ_PERSIST']='0'
        with self.assertRaises(ValueError):c.process_contract(self.config,self.argv,self.env,self.group,same_executable=True)
    def test_unrelated_env_not_exported(self):
        self.env['UNRELATED_PRIVATE']='never-record'
        got=c.controlled_environment(self.env);self.assertNotIn('UNRELATED_PRIVATE',got)
    def test_all_CPU_dispatch_overrides_are_captured_and_forbidden(self):
        for key in c.CPU_OVERRIDES:
            env=dict(self.env,**{key:'1'})
            self.assertEqual(c.controlled_environment(env)[key],'1')
            with self.assertRaises(ValueError):c.process_contract(self.config,self.argv,env,self.group,same_executable=True)
    def test_layer_override_rejected(self):
        self.config['args']+=['--layer-split','20,20']
        with self.assertRaises(ValueError):c.expected_native_argv(self.config)
    def test_native_factor_has_no_unobserved_model_traffic_claim(self):
        for arm in ('N0','N1'):
            got=c.factor_activation('ordinary startup','numerical',arm)
            self.assertEqual(got['CPU_IQ2XS_candidate'],arm=='N1')
            self.assertFalse(got['per_model_type17_dispatch_count_observed'])
            with self.assertRaises(ValueError):c.factor_activation('IQ2_S_PERSIST dispatch kind=gate_up blocks=432','numerical',arm)

if __name__=='__main__':unittest.main()
