"""Actual two-pack CPU encoding and provenance negatives, never model execution."""
import copy
import unittest
from unittest.mock import patch
import fixtures as f
MANIFESTS={}

class Fixture(unittest.TestCase):
    def check_manifest(self,name):
        m=f.encode(name);self.assertEqual(m['context'],1048576);self.assertEqual(m['default_output'],262144)
        self.assertEqual(m['benchmark_cap'],32768);self.assertEqual(m['effort'],100);self.assertTrue(m['drafter'])
        self.assertFalse(m['automatic_next_arm']);self.assertFalse(m['performance_or_general_quality_proof'])
        self.assertEqual(m['cases'][0]['prompt_ids'],m['cases'][1]['prompt_ids'])
        self.assertEqual([c['expected_reuse'] for c in m['cases']],['zero','prompt-minus-one'])
        self.assertEqual(m['cases'][1]['dependency'],m['cases'][0]['id'])
        self.assertEqual(m['cases'][0]['request_sha256'],f.REQUEST_SHA)
        self.assertEqual(m['effective_template']['pack_template_sha256'],f.registry()[name]['tokenizer_sha256']['chat_template.jinja'])
        self.assertEqual(m['tokenizer_source_sha256'],f.registry()[name]['tokenizer_sha256'])
        self.assertTrue(0<m['actual_prompt_tokens']<=1024)
        MANIFESTS[name]=m
    def test_actual_HGU_encoder_and_original_pack_template(self):self.check_manifest('HGU')
    def test_actual_Unsloth_encoder_and_original_pack_template(self):self.check_manifest('UNSLOTH')
    def test_only_explicit_candidates_before_API_import(self):
        with patch.object(f,'helper') as load:
            with self.assertRaises(ValueError):f.encode('OLD')
        load.assert_not_called()
    def test_full_policy_cannot_reduce_context_output_effort_or_drafter(self):
        rows=f.registry()
        for key,value in [('context_total',262144),('output_allowance',32768),('benchmark_cap',8192),('effort',50),('drafter_unchanged',False),('exact_private_S2',True)]:
            bad=copy.deepcopy(rows);bad['HGU'][key]=value
            with patch.object(f.json,'loads',return_value=bad):
                with self.assertRaises(ValueError):f.registry()
    def test_registry_rejects_unknown_or_missing_candidate(self):
        rows=f.registry()
        for bad in [{}, {'HGU':rows['HGU']},{**rows,'OTHER':rows['HGU']}]:
            with patch.object(f.json,'loads',return_value=bad):
                with self.assertRaises(ValueError):f.registry()
    def test_pack_path_parent_escape_and_absolute_refused(self):
        rows=f.registry()
        for relative in ['../foreign','/foreign']:
            bad=copy.deepcopy(rows);bad['HGU']['pack_relative_to_E']=relative
            with patch.object(f,'registry',return_value=bad):
                with self.assertRaises(ValueError):f.pack_inputs('HGU')
    def test_tokenizer_source_byte_difference_refused(self):
        rows=f.registry();rows['UNSLOTH']['tokenizer_sha256']['chat_template.jinja']='0'*64
        with patch.object(f,'registry',return_value=rows):
            with self.assertRaises(ValueError):f.pack_inputs('UNSLOTH')
    def test_metadata_source_byte_difference_refused(self):
        rows=f.registry();rows['HGU']['metadata_sha256']['tensors.txt']='0'*64
        with patch.object(f,'registry',return_value=rows):
            with self.assertRaises(ValueError):f.pack_inputs('HGU')
    def test_missing_or_extra_source_map_refused(self):
        rows=f.registry();del rows['HGU']['tokenizer_sha256']['vocab.json']
        with patch.object(f,'registry',return_value=rows):
            with self.assertRaises(ValueError):f.pack_inputs('HGU')
    def test_request_source_change_refused_before_encoding(self):
        with patch.object(f,'SOURCE_SHA','0'*64):
            with self.assertRaises(ValueError):f.literal_request()
    def test_original_API_helper_change_refused_before_import(self):
        with patch.object(f,'HELPER_SHA','0'*64),patch.object(f.importlib.util,'spec_from_file_location') as load:
            with self.assertRaises(ValueError):f.helper()
        load.assert_not_called()
