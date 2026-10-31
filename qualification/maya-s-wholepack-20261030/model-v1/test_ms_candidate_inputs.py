"""First actual candidate CPU encodings, once per physical host; no model."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import ms_candidate_inputs as c

ACTUAL_MANIFESTS={}


class Candidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global ACTUAL_MANIFESTS
        if ACTUAL_MANIFESTS:raise ValueError('Do not silently re-encode actual candidate')
        ACTUAL_MANIFESTS=c.produce()

    def test_actual_triplet_has_all_fixed_requests_and_capacities(self):
        self.assertEqual(c.validate(ACTUAL_MANIFESTS),ACTUAL_MANIFESTS)
        self.assertEqual([len(ACTUAL_MANIFESTS[m]['cases']) for m in ('quality','prose','coding')],[4,3,3])
        self.assertEqual(len(ACTUAL_MANIFESTS['prose']['lifecycle_cases']),4)

    def test_candidate_metadata_source_is_explicit_not_baseline(self):
        for m in ACTUAL_MANIFESTS.values():
            self.assertEqual(m['pack_relative_to_E'],str(c.fixtures.CANDIDATE_PACK.relative_to(c.fixtures.E)))
            self.assertEqual(set(m['tokenizer_source_sha256']),set(c.fixtures.TOKENIZER_NAMES))
            self.assertNotEqual(m['pack_relative_to_E'],str(c.fixtures.BASE_PACK.relative_to(c.fixtures.E)))

    def test_wrong_total_or_output_limit_refused(self):
        for key,value in (('context',262144),('default_output',32768)):
            m=copy.deepcopy(ACTUAL_MANIFESTS);m['quality'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.validate(m)

    def test_baseline_or_foreign_pack_substitution_refused(self):
        m=copy.deepcopy(ACTUAL_MANIFESTS);m['quality']['pack_relative_to_E']=str(c.fixtures.BASE_PACK.relative_to(c.fixtures.E))
        with self.assertRaises(ValueError):c.validate(m)

    def test_resized_request_or_effort_refused(self):
        for key,value in (('max_tokens',256),('reasoning_effort',99)):
            m=copy.deepcopy(ACTUAL_MANIFESTS);m['prose']['cases'][0]['request'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.validate(m)

    def test_tokenizer_drift_between_families_refused(self):
        m=copy.deepcopy(ACTUAL_MANIFESTS);m['coding']['tokenizer_source_sha256']['vocab.json']='0'*64
        with self.assertRaises(ValueError):c.validate(m)

    def test_uniform_tokenizer_drift_refused(self):
        m=copy.deepcopy(ACTUAL_MANIFESTS)
        for family in m.values():family['tokenizer_source_sha256']['vocab.json']='0'*64
        with self.assertRaises(ValueError):c.validate(m)

    def test_uniform_fallback_or_wrong_template_path_refused(self):
        for key,value in (('pack_template_replaced',True),('pack_template_replaced',0),
                          ('effective_template_relative_to_E',c.fixtures.FALLBACK_TEMPLATE),
                          ('pack_template_relative_to_E',c.fixtures.FALLBACK_TEMPLATE)):
            m=copy.deepcopy(ACTUAL_MANIFESTS)
            for family in m.values():family['effective_template'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):c.validate(m)

    def test_uniform_wrong_template_hash_refused(self):
        for key in ('pack_template_sha256','effective_template_sha256'):
            m=copy.deepcopy(ACTUAL_MANIFESTS)
            for family in m.values():family['effective_template'][key]='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):c.validate(m)

    def test_uniform_wrong_picker_or_policy_refused(self):
        for key,value in (('api_picker_sha256','0'*64),('selection_policy','borrow baseline')):
            m=copy.deepcopy(ACTUAL_MANIFESTS)
            for family in m.values():family['effective_template'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.validate(m)

    def test_encoded_prompt_corruption_refused(self):
        m=copy.deepcopy(ACTUAL_MANIFESTS);m['quality']['cases'][0]['prompt_ids'][0]=129280
        with self.assertRaises(ValueError):c.validate(m)

    def test_missing_family_or_unmeasured_lifecycle_refused(self):
        m=copy.deepcopy(ACTUAL_MANIFESTS);m.pop('coding')
        with self.assertRaises(ValueError):c.validate(m)
        m=copy.deepcopy(ACTUAL_MANIFESTS);m['quality']['lifecycle_cases']=[{}]
        with self.assertRaises(ValueError):c.validate(m)

    def test_missing_candidate_metadata_never_borrows_baseline(self):
        with patch.object(c.fixtures,'tokenizer_bytes',side_effect=ValueError('Candidate missing')),patch.object(c.fixtures,'build_manifest') as encode:
            with self.assertRaises(ValueError):c.produce()
        encode.assert_not_called()


if __name__=='__main__':unittest.main()
