"""Synthetic saved-data contracts; no model, live service or actual audit run.

Reuse only the prior Terminal.setUp data builder, never its tests. Existing live
authority/startup mocks remain explicit; raw request/SSE, native, tokenizer,
configuration, closure, fence and resource checks remain real byte consumers.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import ms_compat_completion as m
import ms_compat_audit as original
import test_ms_compat_audit as prior

qa = prior.qa
PRODUCER = prior.REAL_E / 'hosting-1m-output256k-v3-20261027/capacity_mode.py'


class ProducerContract(unittest.TestCase):
    def test_request_and_filenames_match_exact_producer_source_without_execution(self):
        source = PRODUCER.read_text()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), m.PRODUCER_SHA256)
        tree = ast.parse(source)
        model = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'MODEL' for t in n.targets))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'public_probe')
        body = copy.deepcopy(next(n.value for n in ast.walk(function) if isinstance(n, ast.Assign)
                                  and any(isinstance(t, ast.Name) and t.id == 'body' for t in n.targets)))
        class ModelLiteral(ast.NodeTransformer):
            def visit_Name(self, node):
                if node.id != 'MODEL': raise ValueError('Unexpected public request expression')
                return ast.Constant(model)
        self.assertEqual(ast.literal_eval(ModelLiteral().visit(body)), m.PUBLIC_DEFAULT_REQUEST)
        names = {n.value for n in ast.walk(function) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertIn('public-default-output-request.json', names)
        self.assertIn('public-default-output-sse.txt', names)
        self.assertNotIn('public-ready-sse.txt', names)
        self.assertNotIn('max_tokens', m.PUBLIC_DEFAULT_REQUEST)


class Completion(unittest.TestCase):
    def setUp(self):
        self.h = prior.Terminal('runTest'); self.h.setUp(); self.addCleanup(self.h.doCleanups)
        self.meta = self.h.meta
        # These are freshly constructed SYNTHETIC receipts only. No real raw
        # evidence is moved, copied to an alias, or altered by these controls.
        (self.meta / 'public-ready-sse.txt').unlink()
        self.request = self.meta / 'public-default-output-request.json'
        self.stream = self.meta / 'public-default-output-sse.txt'
        self.h.put(self.request, copy.deepcopy(m.PUBLIC_DEFAULT_REQUEST))
        self.sse = '\n'.join('data: ' + json.dumps(e) for e in [
            {'choices': [{'delta': {'role': 'assistant', 'content': ''}, 'finish_reason': None}]},
            {'choices': [{'delta': {'content': 'READ'}, 'finish_reason': None}]},
            {'choices': [{'delta': {'content': 'Y'}, 'finish_reason': None}]},
            {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
        ]) + '\ndata: [DONE]\n'
        self.stream.write_text(self.sse)
        producer = self.h.p / 'hosting-1m-output256k-v3-20261027/capacity_mode.py'
        self.h.q['files'][str(producer)] = m.PRODUCER_SHA256
        self.sync_qualification()

    def sync_qualification(self):
        path = self.h.p / 'compatibility-qualification.json'; self.h.put(path, self.h.q)
        self.h.qpin = original.sha(path)
        self.h.change(self.meta / 'state.json', lambda d: d.update(qualification_sha256=self.h.qpin))
        self.h.change(self.meta / 'proof.json', lambda d: d.update(
            qualification_sha256=self.h.qpin, files=self.h.q['files']))

    def audit(self):
        return m.audit_saved(qa.runtime, qa.config, qa.fixtures, qa.saved, qa,
                             self.h.q, self.h.qpin, self.h.binding, original=original)

    def test_full_saved_terminal_with_actual_filename_and_fragmented_READY_contracts(self):
        with patch.object(qa.saved, 'restoration_contract', side_effect=AssertionError('Old consumer must not run')):
            result = self.audit()
        self.assertTrue(result['passed']); self.assertEqual(result['rows'][0]['observed_tokens'], 3)
        self.assertEqual(result['rows'][0]['native']['drafts_offered'], 0)
        for key in ('performance_claim', 'general_quality_claim', 'deployment_admitted',
                    'automatic_next_arm', 'finite_logits_checked', 'original_audit_regraded', 'model_execution_performed'):
            self.assertIs(result[key], False)
        self.assertEqual(result['qualification_sha256'], self.h.qpin)
        for path in (self.request, self.stream, self.meta / 'old-owner-close.json'):
            self.assertEqual(result['evidence_sha256'][str(path)], original.sha(path))
        self.assertFalse((self.meta / 'public-ready-sse.txt').exists())

    def test_old_filename_only_cannot_clear_completion(self):
        self.stream.unlink(); (self.meta / 'public-ready-sse.txt').write_text(self.sse)
        with self.assertRaises(ValueError): self.audit()

    def test_missing_default_request_refused(self):
        self.request.unlink()
        with self.assertRaises(ValueError): self.audit()

    def test_missing_default_stream_refused(self):
        self.stream.unlink()
        with self.assertRaises(ValueError): self.audit()

    def test_capped_changed_or_wrong_typed_public_request_refused(self):
        mutations = [{'max_tokens': 262144}, {'temperature': False}, {'seed': True},
                     {'stream': False}, {'reasoning_effort': 'high'}, {'model': 'foreign'}]
        for mutation in mutations:
            self.h.put(self.request, {**m.PUBLIC_DEFAULT_REQUEST, **mutation})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.audit()

    def test_changed_public_prompt_refused(self):
        request = copy.deepcopy(m.PUBLIC_DEFAULT_REQUEST); request['messages'][0]['content'] = 'READY'
        self.h.put(self.request, request)
        with self.assertRaises(ValueError): self.audit()

    def test_duplicate_or_nonfinite_public_request_refused(self):
        for data in ('{"stream":true,"stream":true}', '{"temperature":NaN}'):
            self.request.write_text(data)
            with self.subTest(data=data), self.assertRaises(ValueError): self.audit()

    def test_incomplete_wrong_or_duplicate_DONE_public_stream_refused(self):
        for raw in ('data: [DONE]\n', self.sse.replace('data: [DONE]\n', ''),
                    self.sse.replace('READ', 'WRONG'), self.sse.replace('"stop"', '"length"'),
                    self.sse + 'data: [DONE]\n'):
            self.stream.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError): self.audit()

    def test_alias_public_evidence_refused(self):
        target = self.meta / 'other-request.json'; self.request.rename(target); self.request.symlink_to(target)
        with self.assertRaises(ValueError): self.audit()

    def test_exact_producer_membership_required(self):
        path = str(self.h.p / 'hosting-1m-output256k-v3-20261027/capacity_mode.py')
        self.h.q['files'][path] = '0' * 64; self.sync_qualification()
        with self.assertRaisesRegex(ValueError, 'producer membership'): self.audit()

    def test_original_model_qualification_still_required(self):
        self.h.qpin = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Exact admitted qualification'): self.audit()

    def test_changed_current_binding_refused(self):
        self.h.binding = {**self.h.binding, 'native_pid': 999}
        with self.assertRaises(ValueError): self.audit()

    def test_raw_old_API_exit_failure_not_hidden_by_producer_pass(self):
        self.h.change(self.meta / 'old-owner-close.json', lambda d: d['after'].update(ExecMainStatus='1'))
        with self.assertRaises(ValueError): self.audit()

    def test_private_native_exit_failure_retained(self):
        path = self.h.folder / 'native-close.jsonl'; row = json.loads(path.read_text()); row['returncode'] = 1
        path.write_text(json.dumps(row) + '\n')
        with self.assertRaises(ValueError): self.audit()

    def test_wrong_model_literal_still_refused(self):
        self.h.change(self.h.dest / 'response.json', lambda d: d.update(content='WRONG'))
        with self.assertRaises(ValueError): self.audit()

    def test_transient_fence_collection_required(self):
        self.h.change(self.meta / 'private-memory-fence-collected.json', lambda d: d.update(dropins_absent=False))
        with self.assertRaises(ValueError): self.audit()

    def test_completion_is_read_only_and_does_not_publish(self):
        before = {str(p): original.sha(p) for p in self.h.p.rglob('*') if p.is_file()}
        self.audit()
        after = {str(p): original.sha(p) for p in self.h.p.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
