"""Actual C0/A1 CPU prompt encoding once each; no model execution."""
import copy
from pathlib import Path
import tempfile
import unittest
import fixtures as f


class EssentialFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=f.input_map()
        cls.C0=f.encode('C0');cls.A1=f.encode('A1')

    def test_actual_both_manifest_schemas_requests_caps_effort_and_counts(self):
        runtime,fixture=f.helpers()
        self.assertEqual(set(self.C0),set(self.A1))
        for arm,value,count in (('C0',self.C0,11),('A1',self.A1,3)):
            self.assertEqual(value['schema'],'s2-essential-encoded-v1')
            self.assertEqual(value['arm'],arm);self.assertEqual(len(value['cases']),count)
            self.assertEqual((value['context_total'],value['output_allowance']),(1048576,262144))
            runtime.fixture_contract(value,fixture,arm)
            for case in value['cases']:
                self.assertEqual(case['prompt_tokens'],len(case['prompt_ids']))
                self.assertEqual(case['prompt_ids_sha256'],f.digest(case['prompt_ids']))
                self.assertEqual(case['request_sha256'],f.digest(case['request']))
                self.assertEqual(case['request']['reasoning_effort'],100)
                self.assertEqual(case['request']['max_tokens'],32768)
                self.assertTrue(all(type(x) is int and 0<=x<129280 for x in case['prompt_ids']))
            self.assertFalse(value['native_model_executed']);self.assertFalse(value['GPU_launch_ready'])

    def test_same_final_recovery_and_two_mains_have_identical_actual_IDs_on_both_profiles(self):
        for b,a in zip(self.C0['cases'][-3:],self.A1['cases']):
            self.assertEqual(b['id'],a['id']);self.assertEqual(b['request'],a['request'])
            self.assertEqual(b['request_sha256'],a['request_sha256'])
            self.assertEqual(b['prompt_ids'],a['prompt_ids'])
            self.assertEqual(b['prompt_ids_sha256'],a['prompt_ids_sha256'])
        self.assertFalse(any(c['request'].get('logprobs') for c in self.A1['cases']))

    def test_actual_candidate_constructor_tokenizer_and_unchanged_picker_provenance(self):
        self.assertEqual(self.C0['constructed_metadata_receipt_sha256'],f.CONSTRUCTOR_SHA)
        self.assertIsNone(self.A1['constructed_metadata_receipt_sha256'])
        self.assertEqual(self.C0['tokenizer_relative_to_E'],str((f.Q/'candidate-pack-v1/pack-FIRST/tokenizer').relative_to(f.E)))
        self.assertEqual(self.A1['tokenizer_relative_to_E'],'native-vision-v2/tokenizer')
        self.assertEqual(self.C0['effective_template']['api_picker_sha256'],self.A1['effective_template']['api_picker_sha256'])
        for name in f.NAMES[:-1]:self.assertEqual(self.C0['tokenizer_source_sha256'][name],self.A1['tokenizer_source_sha256'][name])
        self.assertEqual(f.input_map(),self.inputs)

    def test_actual_images_cache_identity_and_tool_call_ID_normalization(self):
        cold=next(c for c in self.C0['cases'] if c['id']=='ms-quality-cold-text')
        for name in ('ms-quality-warm-text','ms-quality-return-text'):
            self.assertEqual(next(c for c in self.C0['cases'] if c['id']==name)['prompt_ids'],cold['prompt_ids'])
        image=next(c for c in self.C0['cases'] if c['id']=='ms-quality-two-images')
        self.assertEqual(len(image['image_spans']),2)
        self.assertTrue(all(s['length']>0 and s['start']>=0 for s in image['image_spans']))
        self.assertTrue(self.C0['tool_ID_normalization_CPU_proved'])
        self.assertFalse(self.A1['tool_ID_normalization_CPU_proved'])

    def test_original_fixture_globals_not_repointed_to_new_pack(self):
        _,fixture=f.helpers()
        self.assertEqual(fixture.CANDIDATE_PACK,f.DC/'maya-s-comparison-v1/pack-v1/pack-FIRST')
        self.assertNotEqual(fixture.CANDIDATE_PACK,f.PACKS['C0'])
        self.assertEqual(fixture.tokenizer_directory(fixture.BASE_PACK),f.DIRECTORIES['A1'])

    def test_wrong_prompt_count_hash_or_changed_frozen_request_rejected(self):
        runtime,fixture=f.helpers()
        for mutation in ('count','hash','request','short-schedule'):
            wrong=copy.deepcopy(self.A1)
            if mutation=='count':wrong['cases'][0]['prompt_tokens']+=1
            elif mutation=='hash':wrong['cases'][0]['prompt_ids_sha256']='0'*64
            elif mutation=='request':wrong['cases'][-1]['request']['max_tokens']=256
            else:wrong['cases'].pop()
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):runtime.fixture_contract(wrong,fixture,'A1')

    def test_manifest_publication_is_exclusive_and_metadata_alias_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();out=root/'A1.json'
            f.write_manifest(out,self.A1)
            with self.assertRaises(FileExistsError):f.write_manifest(out,self.A1)
            alias=root/'alias';alias.symlink_to(out)
            with self.assertRaises(ValueError):f.ordinary(alias)
            with self.assertRaises(ValueError):f.exact('essential_fixture_wrong_source',out,'0'*64)


if __name__=='__main__':unittest.main(verbosity=2)
