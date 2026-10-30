"""New family pure contracts and sole actual baseline CPU prompt encodings."""
import copy
import json
from pathlib import Path
import resource
import tempfile
import unittest
from unittest.mock import patch,Mock
import ms_config as c
import ms_fixtures as f
import ms_inputs_cpu as d

ACTUAL_MANIFESTS={}
BASE=f.E/'decode-optimization-20261028/model-v1/base-config.json'


def directory(mode,arm):return c.E/'results'/('maya-s-'+mode+'-'+arm+'-20261030T160000Z')/'native'


def encoded(mode):
    cases=f.quality_cases(f.source_images()[0]) if mode=='quality' else f.performance_cases()
    for i,x in enumerate(cases):
        ids=[10]*(7000 if mode=='quality' or i<2 else 100)
        if mode=='quality' and i==2:ids[100:103]=[129264]*3;ids[5000:5003]=[129264]*3
        x.update(prompt_ids=ids,prompt_tokens=len(ids),prompt_ids_sha256=f.sha(f.packed(ids)),
                 request_sha256=f.sha(f.packed(x['request'])),image_spans=f.image_spans(ids))
    return cases


class Config(unittest.TestCase):
    def setUp(self):self.base=json.loads(BASE.read_bytes())
    def test_exact_baseline_and_all_six_factors(self):
        original=copy.deepcopy(self.base)
        for mode,arms in c.MODE_ARMS.items():
            for arm in arms:
                v=c.make_config(self.base,directory(mode,arm),mode,arm);fac=c.factor(mode,arm)
                self.assertTrue(c.check_config(self.base,v,directory(mode,arm),mode,arm))
                self.assertEqual(v['exe'],self.base['exe']);self.assertEqual(fac['native_sha256'],c.BASE_NATIVE)
                self.assertEqual(v['args'][v['args'].index('--pack')+1],fac['pack'])
                self.assertEqual('DS4_SERVE_DUMP' in v['env'],mode=='quality')
        self.assertEqual(self.base,original)
    def test_candidate_tokenizer_template_directory_baseline_untouched(self):
        a=c.make_config(self.base,directory('quality','QS0'),'quality','QS0')
        b=c.make_config(self.base,directory('quality','QS1'),'quality','QS1')
        self.assertEqual(a['tokenizer'],self.base['tokenizer']);self.assertEqual(b['tokenizer'],str(c.CANDIDATE_PACK/'tokenizer'))
        self.assertNotIn('chat_template',b);self.assertNotIn('template',b)
    def test_unknown_mode_or_old_arm_refused(self):
        for mode,arm in [('numerical','N0'),('quality','B1'),('performance','QS1'),('quality',True),('quality','QS2')]:
            with self.assertRaises(ValueError):c.factor(mode,arm)
    def test_namespace_foreign_alias_old_or_wrong_arm(self):
        for p in [Path('/tmp/native'),directory('quality','QS0')/'..'/'native',directory('quality','QS1'),Path('native')]:
            with self.assertRaises(ValueError):c.make_config(self.base,p,'quality','QS0')
    def test_baseline_typed_quality_and_native_mutations(self):
        for key,val in [('hosted_default_effort',100.0),('gpus_asked',1),('exe','candidate'),('fit_max_tokens',True)]:
            v=copy.deepcopy(self.base);v[key]=val
            with self.assertRaises(ValueError):c.selected_base(v)
    def test_private_pack_tokenizer_and_setting_mutations(self):
        a=c.make_config(self.base,directory('quality','QS1'),'quality','QS1')
        for key,val in [('tokenizer',self.base['tokenizer']),('hosted_default_effort',100.0),('port',18141),('exe','other'),('layer_split','19,21')]:
            v=copy.deepcopy(a);v[key]=val
            with self.assertRaises(ValueError):c.check_config(self.base,v,directory('quality','QS1'),'quality','QS1')
    def test_no_held_kernel_flags_or_context_cap_override(self):
        a=c.make_config(self.base,directory('performance','B1'),'performance','B1')
        for key in ['DS4_Q5K_IMMA','DS4_IQ_PERSIST','DS4_HEAD_BATCH','DS4_Q8_SHARE','STRATA_DS4_HEAD_BATCH']:
            v=copy.deepcopy(a);v['env'][key]='1'
            with self.assertRaises(ValueError):c.check_config(self.base,v,directory('performance','B1'),'performance','B1')
        self.assertNotIn('max_tokens',a);self.assertEqual(a['args'][a['args'].index('--max-context')+1],'1048576')
    def test_process_contract_exact_auto_and_extra_environment(self):
        a=c.make_config(self.base,directory('quality','QS1'),'quality','QS1');argv=c.expected_native_argv(a)
        cg='/user.slice/strata-deepseek-window.service'
        self.assertTrue(c.process_contract(a,argv,{**a['env'],'PATH':'unused'},cg,same_executable=True)['owned_window_cgroup'])
        for args,env,group,ex in [(argv+['extra'],a['env'],cg,True),(argv,{**a['env'],'DS4_Q8_SHARE':'1'},cg,True),
                                  (argv,a['env'],'/foreign.service',True),(argv,a['env'],cg,False)]:
            with self.assertRaises(ValueError):c.process_contract(a,args,env,group,same_executable=ex)
    def test_nonfinite_and_duplicate_pack_arg_refused(self):
        v=copy.deepcopy(self.base);v['hosted_default_effort']=float('nan')
        with self.assertRaises(ValueError):c.selected_base(v)
        v=copy.deepcopy(self.base);v['args']+=['--pack',str(c.BASE_PACK)]
        with self.assertRaises(ValueError):c.selected_base(v)


class Requests(unittest.TestCase):
    def test_literal_prose_and_code_match_pinned_sources(self):
        f.validate_request_sources();self.assertEqual(len(f.performance_cases()),5)
    def test_quality_order_known_answers_and_new_family(self):
        cases=f.quality_cases(f.source_images()[0]);f.validate_requests(cases,'quality')
        self.assertEqual([x['id'] for x in cases],list(f.QUALITY_IDS))
        self.assertIn('Maya-S whole-pack quality',cases[0]['request']['messages'][0]['content'])
        self.assertEqual(cases[2]['expected'],{'first':'red','second':'blue'})
    def test_no_remote_image_inputs(self):
        for urls in [['https://example.com/a.png','x'],['x'],[True,False]]:
            with self.assertRaises(ValueError):f.quality_cases(urls)
    def test_copy_isolation_and_full_policy(self):
        a=f.performance_cases();a[0]['request']['max_tokens']=1;a[2]['request']['messages'][0]['content']='changed'
        b=f.performance_cases();f.validate_requests(b,'performance')
        self.assertEqual(b[0]['request']['max_tokens'],32768);self.assertNotEqual(b[2]['request']['messages'][0]['content'],'changed')
    def test_request_types_caps_effort_and_extra_override(self):
        for key,val in [('reasoning_effort',100.0),('max_tokens',64),('temperature',1),('seed',True),('chat_template_kwargs',{})]:
            x=f.performance_cases();x[0]['request'][key]=val
            with self.assertRaises(ValueError):f.validate_requests(x,'performance')
    def test_answer_reuse_order_and_word_fitting_mutations(self):
        for mut in [lambda x:x.reverse(),lambda x:x[0].update(expected={'values':[1]}),
                    lambda x:x[1].update(expected_reuse='zero'),lambda x:x[2].update(length_is_observed_not_fitted=False)]:
            x=f.performance_cases();mut(x)
            with self.assertRaises(ValueError):f.validate_requests(x,'performance')
    def test_unknown_fixture_mode(self):
        with self.assertRaises(ValueError):f.sequence('old')
        with self.assertRaises(ValueError):f.build_manifest(f.BASE_PACK,'old')
    def test_changed_frozen_work_source_refused(self):
        with patch.object(f,'SOURCE_PINS',{**f.SOURCE_PINS,f.PROSE_SOURCE:'0'*64}):
            with self.assertRaises(ValueError):f.validate_request_sources()
    def test_no_prose_response_format_or_output_length_enforcement(self):
        cases=f.performance_cases()
        for x in cases[2:]:self.assertNotIn('response_format',x['request']);self.assertEqual(x['request']['max_tokens'],32768)
        self.assertTrue(cases[2]['manual_quality_review_required']);self.assertFalse(cases[4]['generated_code_execution_admitted'])


class Encoding(unittest.TestCase):
    def test_synthetic_encoded_state_contracts(self):
        for mode in ('quality','performance'):self.assertEqual(f.validate_encoded(encoded(mode),mode),encoded(mode))
    def test_token_type_range_hash_and_count(self):
        for val in [True,-1,129280]:
            x=encoded('quality');x[0]['prompt_ids'][0]=val
            with self.assertRaises(ValueError):f.validate_encoded(x,'quality')
        x=encoded('quality');x[0]['prompt_tokens']=7000.0
        with self.assertRaises(ValueError):f.validate_encoded(x,'quality')
        x=encoded('performance');x[0]['prompt_ids_sha256']='0'*64
        with self.assertRaises(ValueError):f.validate_encoded(x,'performance')
    def test_prompt_bounds_no_auto_resize(self):
        for i,n in [(0,5999),(0,12000),(2,63),(4,2049)]:
            x=encoded('performance');x[i]['prompt_ids']=[10]*n;x[i]['prompt_tokens']=n;x[i]['prompt_ids_sha256']=f.sha(f.packed(x[i]['prompt_ids']))
            with self.assertRaises(ValueError):f.validate_encoded(x,'performance')
    def test_image_cut_and_text_token_exclusion(self):
        x=encoded('quality');x[2]['prompt_ids'][5000:5003]=[10]*3;x[2]['image_spans']=f.image_spans(x[2]['prompt_ids']);x[2]['prompt_ids_sha256']=f.sha(f.packed(x[2]['prompt_ids']))
        with self.assertRaises(ValueError):f.validate_encoded(x,'quality')
        x=encoded('performance');x[2]['prompt_ids'][0]=129264;x[2]['image_spans']=f.image_spans(x[2]['prompt_ids']);x[2]['prompt_ids_sha256']=f.sha(f.packed(x[2]['prompt_ids']))
        with self.assertRaises(ValueError):f.validate_encoded(x,'performance')
    def test_warm_text_token_difference(self):
        x=encoded('quality');x[1]['prompt_ids'][0]=11;x[1]['prompt_ids_sha256']=f.sha(f.packed(x[1]['prompt_ids']))
        with self.assertRaises(ValueError):f.validate_encoded(x,'quality')
    def test_explicit_pack_selects_candidate_without_baseline_fallback(self):
        self.assertEqual(f.tokenizer_directory(f.BASE_PACK),f.V/'tokenizer')
        self.assertEqual(f.tokenizer_directory(f.CANDIDATE_PACK),f.CANDIDATE_PACK/'tokenizer')
        for p in [Path('/tmp/foreign'),Path('relative'),f.BASE_PACK/'..'/'pack-native-vision-v1']:
            with self.assertRaises(ValueError):f.tokenizer_directory(p)
    def test_missing_candidate_tokenizer_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t).resolve()/'candidate'
            with patch.object(f,'E',Path(t).resolve()),patch.object(f,'CANDIDATE_PACK',p):
                with self.assertRaises(ValueError):f.tokenizer_bytes(p)
    def test_tokenizer_symlink_refused_before_target_read(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();p=root/'candidate';p.mkdir();(p/'tokenizer').symlink_to('/nonexistent')
            with patch.object(f,'E',root),patch.object(f,'CANDIDATE_PACK',p):
                with self.assertRaises(ValueError):f.tokenizer_bytes(p)
    def test_tokenizer_schema_and_foreign_specials(self):
        raw,_,_=f.tokenizer_bytes(f.BASE_PACK);self.assertEqual(len(f.tokenizer_schema(raw)[0]),129280)
        for cfg in [{'pre':'qwen35','special_ids':{'bos':0,'eos':1,'pad':1}},
                    {'pre':'deepseek3','special_ids':{'bos':False,'eos':1,'pad':1}}]:
            bad=dict(raw,**{'tokenizer.json':f.packed(cfg)})
            with self.assertRaises(ValueError):f.tokenizer_schema(bad)
    def test_duplicate_vocab_ids_and_typed_token_types(self):
        raw,_,_=f.tokenizer_bytes(f.BASE_PACK);v=json.loads(raw['vocab.json']);v[next(iter(v))]=True
        with self.assertRaises(ValueError):f.tokenizer_schema(dict(raw,**{'vocab.json':f.packed(v)}))
        types=json.loads(raw['token_type.json']);types[0]=True
        with self.assertRaises(ValueError):f.tokenizer_schema(dict(raw,**{'token_type.json':f.packed(types)}))
    def test_empty_template_refused(self):
        raw,_,_=f.tokenizer_bytes(f.BASE_PACK)
        with self.assertRaises(ValueError):f.tokenizer_schema(dict(raw,**{'chat_template.jinja':b''}))
    def test_support_source_tamper_before_import(self):
        with patch.object(f,'SUPPORT_PINS',{'native-vision-v2/test_native_vision.py':'0'*64}),patch.object(f.importlib.util,'spec_from_file_location') as loader:
            with self.assertRaises(ValueError):f.load_support()
            loader.assert_not_called()
    def test_foreign_cached_support_refused_before_loader(self):
        with patch.dict(f.sys.modules,{'strata_tokenizer':Mock(__file__='/tmp/foreign.py')}),patch.object(f.importlib.util,'spec_from_file_location') as loader:
            with self.assertRaises(ValueError):f.load_support()
            loader.assert_not_called()
    def test_actual_baseline_api_encodes_each_mode_once(self):
        # Actual selected API, explicit verified baseline tokenizer and MockEngine only.
        for mode in ('quality','performance'):
            m=f.build_manifest(f.BASE_PACK,mode);ACTUAL_MANIFESTS[mode]=m
            self.assertFalse(m['native_model_executed']);self.assertFalse(m['GPU_launch_ready'])
            self.assertEqual(m['tokenizer_source_sha256'],f.BASE_TOKENIZER_PINS)
            self.assertEqual(m['context'],1048576);self.assertEqual(m['default_output'],262144)
            self.assertEqual(m['expected_reuse_tokens'][1],m['cases'][0]['prompt_tokens']-1)
            self.assertEqual(len(m['cases']),4 if mode=='quality' else 5)
            for x in m['cases']:self.assertEqual(x['request']['max_tokens'],32768)


class Driver(unittest.TestCase):
    def test_canonical_input_rejects_escape_before_read(self):
        for name in ['../foreign','/tmp/foreign','',True]:
            with self.assertRaises(ValueError):d.canonical_input(name)
    def test_review_pin_checked_before_test_import(self):
        with patch.object(d,'sha',return_value='wrong'):
            with self.assertRaises(ValueError):d.checked('expected')
    def test_inherited_import_closure_cannot_be_omitted(self):
        with self.assertRaisesRegex(ValueError,'closure incomplete'):d.input_pins({'input_sha256':{}})
    def test_input_symlink_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();(root/'link').symlink_to('/nonexistent')
            with patch.object(d,'E',root):
                with self.assertRaisesRegex(ValueError,'alias'):d.canonical_input('link')
    def test_literal_cpu_limits(self):
        with patch.object(d.os,'nice') as nice,patch.object(d.resource,'setrlimit') as limit,patch.object(d.sys,'platform','linux'):
            d.limits();nice.assert_called_once_with(15)
            self.assertEqual(limit.call_args_list[0].args,(resource.RLIMIT_CPU,(30,30)))
            self.assertEqual(limit.call_args_list[1].args,(resource.RLIMIT_AS,(512*1024**2,)*2))
    def test_cleanup_only_owned_group_and_no_retry(self):
        p=Mock(pid=123)
        with patch.object(d,'gone',side_effect=[False,True,True,True]),patch.object(d.os,'killpg') as kill:
            self.assertEqual(d.cleanup(p),[]);kill.assert_called_once_with(123,d.signal.SIGTERM)
    def test_actual_encoder_is_not_repeated_by_driver(self):
        source=(f.HERE/'ms_inputs_cpu.py').read_text()
        self.assertNotIn('build_manifest(',source);self.assertIn('tests.ACTUAL_MANIFESTS',source)


if __name__=='__main__':unittest.main()
