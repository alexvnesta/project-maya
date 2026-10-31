"""Review before execution. One CPU-only real tokenizer test; no native engine."""
import copy
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import imma_fixtures as f


def cases():
    return f.make_cases(['data:image/png;base64,red-synthetic-test-only',
                         'data:image/png;base64,blue-synthetic-test-only'])


def encoded():
    result = cases()
    for c in result:
        ids = [7] * 8000
        if c['id'] == 'two-images':
            ids[100:200] = [129264] * 100
            ids[6000:6100] = [129264] * 100
        c.update(prompt_ids=ids, prompt_tokens=len(ids), prompt_ids_sha256=f.digest(f.packed(ids)),
                 request_sha256=f.digest(f.packed(c['request'])), image_spans=f.image_spans(ids))
    return result


def update_ids(c, ids):
    c.update(prompt_ids=ids, prompt_tokens=len(ids), prompt_ids_sha256=f.digest(f.packed(ids)),
             image_spans=f.image_spans(ids))


class FixtureContracts(unittest.TestCase):
    def test_fullcap_policy_all_cases(self):
        cs = cases()
        f.validate_requests(cs)
        self.assertEqual([c['id'] for c in cs], list(f.IDS))
        self.assertEqual([c['expected_reuse'] for c in cs], ['zero', 'prompt-minus-one', 'zero', 'prompt-minus-one'])
        for c in cs:
            self.assertEqual(c['request']['max_tokens'], 32768)
            self.assertEqual(c['request']['reasoning_effort'], 100)
            self.assertEqual(c['request']['temperature'], 1.0)
            self.assertEqual(c['request']['seed'], 1)

    def test_cap_effort_sampler_override_rejected_before_encoder_import(self):
        for key, value in [('max_tokens', 1), ('reasoning_effort', 0), ('temperature', 0.0),
                           ('seed', 2), ('top_p', 0.9), ('reasoning_budget_tokens', 64), ('stream', False)]:
            cs = cases(); cs[0]['request'][key] = value
            with self.subTest(key=key), patch.object(f, 'load_support', side_effect=AssertionError('must not import')):
                with self.assertRaises(ValueError):
                    f.encode_cases(cs)

    def test_policy_bool_or_float_substitutions_rejected(self):
        for key, value in [('seed', True), ('max_tokens', 32768.0), ('temperature', 1), ('reasoning_effort', 100.0)]:
            cs = cases(); cs[0]['request'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                f.validate_requests(cs)

    def test_order_missing_extra_and_duplicate_cases_rejected(self):
        cs = cases()
        for changed in [cs[::-1], cs[:-1], cs + [copy.deepcopy(cs[0])], [cs[0], cs[0], cs[2], cs[3]]]:
            with self.assertRaises(ValueError):
                f.validate_requests(changed)

    def test_sequence64_exact_typed_expected_and_future256_distinct(self):
        cs = cases()
        self.assertEqual(cs[0]['expected'], {'values': list(range(1, 65))})
        self.assertIn('through 64', cs[0]['request']['messages'][0]['content'])
        self.assertIn('through 256', f.sequence_request(256)['messages'][0]['content'])
        self.assertEqual(f.sequence_request(256)['max_tokens'], 32768)
        cs[0]['expected']['values'][0] = True
        with self.assertRaises(ValueError): f.validate_requests(cs)
        for n in (True, 64.0, 63, 257):
            with self.assertRaises(ValueError): f.sequence_expected(n)

    def test_requests_are_independent_and_input_urls_not_mutated(self):
        urls = ['red', 'blue']; before = urls[:]
        cs = f.make_cases(urls)
        cs[0]['request']['messages'][0]['content'] = 'changed'
        cs[0]['expected']['values'].clear()
        self.assertEqual(urls, before)
        self.assertEqual(cs[1]['expected']['values'], list(range(1, 65)))
        self.assertNotEqual(cs[0]['request'], cs[1]['request'])

    def test_request_extra_field_or_changed_ledger_rejected(self):
        for field in ('extra', 'ledger'):
            cs = cases()
            if field == 'extra': cs[0]['request']['logit_bias'] = {'1': 100}
            else: cs[0]['request']['messages'][0]['content'] += ' changed'
            with self.assertRaises(ValueError): f.validate_requests(cs)

    def test_valid_encoded_state_and_image_cut_without_mutation(self):
        cs = encoded(); before = copy.deepcopy(cs)
        self.assertIs(f.validate_encoded(cs), cs)
        self.assertEqual(cs, before)
        self.assertEqual(cs[2]['image_spans'], [{'start': 100, 'length': 100}, {'start': 6000, 'length': 100}])

    def test_encoded_token_type_range_and_length_rejected(self):
        for bad in (True, -1, 129280, 7.0):
            cs = encoded(); ids = cs[0]['prompt_ids']; ids[0] = bad; update_ids(cs[0], ids)
            with self.subTest(bad=bad), self.assertRaises(ValueError): f.validate_encoded(cs)
        for n in (2668, 5999, 12000):
            cs = encoded(); update_ids(cs[0], [7] * n)
            with self.subTest(n=n), self.assertRaises(ValueError): f.validate_encoded(cs)

    def test_changed_hash_count_text_tokens_and_span_receipt_rejected(self):
        for key in ('prompt_ids_sha256', 'request_sha256', 'prompt_tokens', 'image_spans'):
            cs = encoded()
            cs[0][key] = 8000.0 if key == 'prompt_tokens' else ([] if key == 'image_spans' else '0' * 64)
            if key == 'image_spans': cs[2][key] = []
            with self.subTest(key=key), self.assertRaises(ValueError): f.validate_encoded(cs)
        cs = encoded(); ids = cs[1]['prompt_ids']; ids[20] = 8; update_ids(cs[1], ids)
        with self.assertRaises(ValueError): f.validate_encoded(cs)

    def test_first_image_cut_crossing_or_second_not_retained_rejected(self):
        for spans in (((5300, 5400), (6000, 6100)), ((100, 200), (5000, 5100)), ((100, 200),)):
            cs = encoded(); ids = [7] * 8000
            for start, end in spans: ids[start:end] = [129264] * (end - start)
            update_ids(cs[2], ids)
            with self.assertRaises(ValueError): f.validate_encoded(cs)

    def test_text_cannot_contain_image_tokens(self):
        cs = encoded()
        for i in (0, 1, 3):
            ids = cs[i]['prompt_ids']; ids[0] = 129264; update_ids(cs[i], ids)
        with self.assertRaises(ValueError): f.validate_encoded(cs)

    def test_image_source_hash_change_rejected(self):
        with patch.object(type(f.IMAGE_MANIFEST), 'read_bytes', return_value=b'{}'):
            with self.assertRaises(ValueError): f.source_images()

    def test_api_hash_change_blocks_support_import(self):
        with patch.object(type(f.IMAGE_MANIFEST), 'read_bytes', return_value=b'changed'), \
             patch.object(f.importlib.util, 'spec_from_file_location', side_effect=AssertionError('must not import')):
            with self.assertRaises(ValueError): f.load_support()

    def test_same_name_foreign_cpu_module_is_rejected(self):
        support = SimpleNamespace(
            server=SimpleNamespace(__file__='/foreign/server.py'),
            ds4_vision=SimpleNamespace(__file__=str(f.V / 'runtime/serve/ds4_vision.py')),
            dsml=SimpleNamespace(__file__=str(f.V / 'runtime/serve/dsml.py')),
            ST=SimpleNamespace(__file__=str(f.V / 'runtime/tools/strata_tokenizer.py')))
        loader = SimpleNamespace(exec_module=lambda module: None)
        with patch.object(f.importlib.util, 'spec_from_file_location', return_value=SimpleNamespace(loader=loader)), \
             patch.object(f.importlib.util, 'module_from_spec', return_value=support):
            with self.assertRaises(ValueError): f.load_support()

    def test_real_frozen_images_and_cpu_mock_api_tokenization(self):
        # First actual tokenizer use occurs only in later admitted bounded CPU qualification.
        manifest = f.build_manifest()
        self.assertEqual(manifest['purpose'], 'UNMEASURED_NUMERICAL_ONLY')
        self.assertFalse(manifest['native_model_executed'])
        self.assertFalse(manifest['GPU_launch_ready'])
        self.assertEqual(manifest['context'], 1048576)
        self.assertEqual(manifest['default_output'], 262144)
        self.assertEqual(len(manifest['images_sha256']), 2)
        self.assertEqual(len(manifest['cases']), 4)
        f.validate_encoded(manifest['cases'])
        n = manifest['cases'][0]['prompt_tokens']
        self.assertEqual(manifest['expected_reuse_tokens'], [0, n - 1, 0, n - 1])
        self.assertEqual(manifest['expected_mode1_activation_skipped_tokens'],
                         [manifest['cases'][i]['prompt_tokens'] - 2668 for i in (0, 2)])
        lengths = manifest['canonical_answer_token_lengths_CPU_only']
        self.assertIs(type(lengths['64']), int)
        self.assertGreater(lengths['64'], 0)
        self.assertGreater(lengths['256'], lengths['64'])
        self.assertFalse(manifest['timed256_variant_admitted'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
