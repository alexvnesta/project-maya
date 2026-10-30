"""Saved synthetic evidence only. No model, CUDA, service, or remote actions."""
import copy
import array
import ast
import hashlib
import importlib.util
import json
import math
import os
import pathlib
from contextlib import ExitStack
from pathlib import Path
import shutil
import struct
import stat
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import ms_quality_audit as m


class Temporary:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
    def write(self, name, value):
        p = self.p / name; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value)); return p


def response():
    events = [{'choices': [{'delta': {'reasoning_content': 'Check. '}, 'finish_reason': None}]},
              {'choices': [{'delta': {'content': '{"values":'}, 'finish_reason': None}]},
              {'choices': [{'delta': {'content': '[1]}'}, 'finish_reason': 'stop'}],
               'usage': {'completion_tokens': 3, 'prompt_tokens': 2},
               'timings': {'predicted_n': 3}}]
    return {'status': 200, 'content': '{"values":[1]}', 'reasoning': 'Check. ',
            'finish_reason': 'stop', 'done': True, 'cancelled': False, 'tool_calls': [],
            'events': events, 'usage': events[-1]['usage'], 'timings': events[-1]['timings'],
            'raw': [{'seconds': i, 'line': 'data: ' + json.dumps(e)} for i, e in enumerate(events)]
                   + [{'seconds': 4, 'line': 'data: [DONE]'}], 'client_full_seconds': .2}


class SSE(unittest.TestCase):
    def test_split_content_and_reasoning_reconstructed(self):
        self.assertTrue(m.sse_contract(response())['raw_SSE_reconstructed'])
    def test_edited_content_or_reasoning_refused(self):
        for key in ('content', 'reasoning'):
            r = response(); r[key] += 'x'
            with self.subTest(key=key), self.assertRaises(ValueError): m.sse_contract(r)
    def test_missing_or_duplicate_DONE_refused(self):
        for remove in (True, False):
            r = response(); r['raw'] = r['raw'][:-1] if remove else r['raw'] + [r['raw'][-1]]
            with self.subTest(remove=remove), self.assertRaises(ValueError): m.sse_contract(r)
    def test_saved_events_usage_timings_cannot_diverge(self):
        for key in ('events', 'usage', 'timings'):
            r = response(); r[key] = None
            with self.subTest(key=key), self.assertRaises(ValueError): m.sse_contract(r)
    def test_error_length_or_tool_delta_refused(self):
        for event in ({'error': 'fault'}, {'choices': [{'delta': {}, 'finish_reason': 'length'}]},
                      {'choices': [{'delta': {'tool_calls': [{'id': 'bad'}]}}]}):
            r = response(); r['raw'].insert(0, {'line': 'data: ' + json.dumps(event)})
            with self.subTest(event=event), self.assertRaises(ValueError): m.sse_contract(r)


class Fence(unittest.TestCase):
    def setUp(self):
        self.initial = {'memory_max': 76 * 2**30, 'swap_max': 0, 'events_before': {'oom': 1, 'oom_kill': 0}}
        unit = {'Transient': 'yes', 'InvocationID': 'a' * 32, 'ControlGroup': '/user/strata-deepseek-window.service',
                'MemoryMax': 'infinity', 'MemorySwapMax': 'infinity',
                'FragmentPath': '/run/user/1000/systemd/transient/strata-deepseek-window.service'}
        self.initial.update(prior_properties={'MemoryMax': 'max', 'MemorySwapMax': 'max'},
                            unit_before=unit, fragment=unit['FragmentPath'], owned_dropin_directory=unit['FragmentPath'] + '.d')
        self.end = {'passed': True, 'events_after': {'oom': 1, 'oom_kill': 0}, 'events_delta': {'oom': 0, 'oom_kill': 0}}
        self.restore = {'passed': True, 'same_invocation': True, 'children_closed': True,
                        'prior_properties': {'MemoryMax': 'max', 'MemorySwapMax': 'max'},
                        'restored_properties': {'MemoryMax': 'max', 'MemorySwapMax': 'max'}, 'unit_after': copy.deepcopy(unit)}
        self.collected = dict.fromkeys(('passed', 'transient', 'unit_collected', 'fragment_absent', 'dropins_absent'), True)
        self.collected.update(original_invocation=unit['InvocationID'], fragment=unit['FragmentPath'],
                              owned_dropin_directory=unit['FragmentPath'] + '.d')
    def test_complete_fence_and_collection(self):
        self.assertTrue(m.fence_contract(self.initial, self.end, self.restore, self.collected)['passed'])
    def test_OOM_not_cleared_by_success_label(self):
        self.end['events_after']['oom'] += 1; self.end['events_delta']['oom'] += 1
        with self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, self.restore, self.collected)
    def test_changed_limits_or_counter_types(self):
        for key, value in [('memory_max', 80 * 2**30), ('swap_max', False)]:
            i = copy.deepcopy(self.initial); i[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.fence_contract(i, self.end, self.restore, self.collected)
    def test_foreign_invocation_or_children_still_open(self):
        for key in ('same_invocation', 'children_closed'):
            r = copy.deepcopy(self.restore); r[key] = False
            with self.subTest(key=key), self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, r, self.collected)
    def test_old_properties_and_collection_are_required(self):
        r = copy.deepcopy(self.restore); r['restored_properties']['MemorySwapMax'] = '0'
        with self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, r, self.collected)
        for key in self.collected:
            c = dict(self.collected); c[key] = False
            with self.subTest(key=key), self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, self.restore, c)
    def test_restoration_cannot_substitute_prior_or_unit_identity(self):
        for key in ('InvocationID', 'ControlGroup', 'FragmentPath'):
            r = copy.deepcopy(self.restore); r['unit_after'][key] += 'x'
            with self.subTest(key=key), self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, r, self.collected)
        r = copy.deepcopy(self.restore)
        r['prior_properties']['MemoryMax'] = r['restored_properties']['MemoryMax'] = '123'
        with self.assertRaises(ValueError): m.fence_contract(self.initial, self.end, r, self.collected)


class TokenizerFiles(Temporary):
    def tokenizer_fixture(self, *, swapped=True):
        self.pack = self.p / 'pack'; self.v = self.p / 'native-vision-v2'
        self.tok = self.v / 'tokenizer'; self.tok.mkdir(parents=True)
        pins = {}
        for name in m.fixtures.TOKENIZER_NAMES:
            path = self.tok / name; path.write_bytes(('synthetic:' + name).encode()); pins[name] = m.runtime.sha(path)
        fallback = self.p / m.fixtures.FALLBACK_TEMPLATE; fallback.parent.mkdir(parents=True, exist_ok=True); fallback.write_text('fallback')
        picker_name = 'native-vision-v2/runtime/serve/dsml.py'
        picker = self.p / picker_name; picker.parent.mkdir(parents=True, exist_ok=True); picker.write_text('picker')
        source = self.tok / 'chat_template.jinja'; selected = fallback if swapped else source
        self.tm = {'tokenizer_source_sha256': pins, 'effective_template': {
            'pack_template_relative_to_E': str(source.relative_to(self.p)), 'pack_template_sha256': pins['chat_template.jinja'],
            'effective_template_relative_to_E': str(selected.relative_to(self.p)), 'effective_template_sha256': m.runtime.sha(selected),
            'pack_template_replaced': swapped, 'api_picker_sha256': m.runtime.sha(picker),
            'selection_policy': 'EXACT_UNCHANGED_B1_DSML_PICKER_WITH_PINNED_V41_FALLBACK'}}
        self.tq = {'files': {str(self.tok / n): v for n, v in pins.items()}}
        self.tq['files'].update({str(fallback): m.runtime.sha(fallback), str(picker): m.runtime.sha(picker)})
        stack = ExitStack(); self.addCleanup(stack.close)
        for key, value in [('E', self.p), ('V', self.v), ('BASE_PACK', self.pack)]: stack.enter_context(patch.object(m.fixtures, key, value))
        stack.enter_context(patch.dict(m.fixtures.SUPPORT_PINS, {m.fixtures.FALLBACK_TEMPLATE: m.runtime.sha(fallback), picker_name: m.runtime.sha(picker)}))


class Tokenizer(TokenizerFiles, unittest.TestCase):
    def setUp(self): super().setUp(); self.tokenizer_fixture()
    def test_exact_fallback_and_unswapped_template_bytes(self):
        self.assertTrue(m.tokenizer_contract(self.tm, self.pack, self.tq)['passed'])
        t = copy.deepcopy(self.tm); x = t['effective_template']; x['pack_template_replaced'] = False
        x['effective_template_relative_to_E'] = x['pack_template_relative_to_E']; x['effective_template_sha256'] = x['pack_template_sha256']
        self.assertTrue(m.tokenizer_contract(t, self.pack, self.tq)['passed'])
    def test_every_tokenizer_and_template_pin_is_required(self):
        for path in self.tq['files']:
            q = copy.deepcopy(self.tq); del q['files'][path]
            with self.subTest(path=path), self.assertRaises(ValueError): m.tokenizer_contract(self.tm, self.pack, q)
    def test_changed_current_bytes_or_mismatched_pin_refused(self):
        path = self.tok / 'vocab.json'; old = path.read_bytes(); path.write_bytes(old + b'x')
        with self.assertRaises(ValueError): m.tokenizer_contract(self.tm, self.pack, self.tq)
        path.write_bytes(old); q = copy.deepcopy(self.tq); q['files'][str(path)] = '0' * 64
        with self.assertRaises(ValueError): m.tokenizer_contract(self.tm, self.pack, q)
    def test_template_traversal_and_selection_substitution_refused(self):
        for key, value in [('effective_template_relative_to_E', '../elsewhere'), ('pack_template_replaced', 1),
                           ('api_picker_sha256', '0' * 64), ('effective_template_sha256', '0' * 64)]:
            t = copy.deepcopy(self.tm); t['effective_template'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.tokenizer_contract(t, self.pack, self.tq)
    def test_tokenizer_extra_file_or_alias_refused(self):
        t = copy.deepcopy(self.tm); t['tokenizer_source_sha256']['extra'] = '0' * 64
        with self.assertRaises(ValueError): m.tokenizer_contract(t, self.pack, self.tq)
        path = self.tok / 'vocab.json'; dest = self.p / 'replacement'; path.rename(dest); path.symlink_to(dest)
        with self.assertRaises(ValueError): m.tokenizer_contract(self.tm, self.pack, self.tq)


class Contracts(Temporary, unittest.TestCase):
    def test_unique_JSON_and_no_nonfinite(self):
        p = self.p / 'x.json'
        for text in ('{"a":1,"a":2}', '{"a":NaN}'):
            p.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError): m.j(p)
    def test_alias_and_hardlink_refused(self):
        p = self.write('x.json', {}); s = self.p / 's.json'; s.symlink_to(p)
        with self.assertRaises(ValueError): m.regular(s)
        s.unlink(); s.hardlink_to(p)
        with self.assertRaises(ValueError): m.regular(p)
    def test_window_exact_command_and_clean_exit(self):
        out = self.p / 'out'; meta = self.p / 'meta'
        cmd = [str(m.runtime.R / 'venv/bin/python3.14'), '-B', str(m.runtime.P / 'ms_quality.py'),
               '--phase', '--mode', 'quality', '--arm', 'QS0', '--output', str(out), '--proof', str(meta / 'proof.json')]
        w = {'command': cmd, 'continued_from': 'prior', 'test_returncode': 0, 'maintenance_held': True,
             'maintenance_resume_allowed': True, 'restored': False}
        m.window_contract(w, out, meta, 'QS0')
        for key, value in [('test_returncode', False), ('test_returncode', 1), ('maintenance_resume_allowed', False),
                           ('command', cmd + ['--extra']), ('continued_from', None)]:
            x = copy.deepcopy(w); x[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): m.window_contract(x, out, meta, 'QS0')
    def test_four_case_no_partial_retry_or_unrun(self):
        cases = [{'id': 'case' + str(i)} for i in range(4)]
        r = {'mode': 'quality', 'arm': 'QS0', 'private_cleanup_passed': True, 'not_a_promotion': True,
             'arm_results': {'complete': True, 'native_request_count': 4, 'retry': False, 'reason': None,
                 'unrun_ids': [], 'DSI1_leftovers': [], 'rows': cases,
                 'scores': [{'id': c['id'], 'passed': True, 'status': 'NATURAL_RESULT_SOURCE_AND_STATE_PASSED'} for c in cases]}}
        m.complete_contract(r, {'cases': cases}, 'QS0')
        for key, value in [('complete', False), ('retry', True), ('unrun_ids', ['x']), ('native_request_count', 5)]:
            x = copy.deepcopy(r); x['arm_results'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.complete_contract(x, {'cases': cases}, 'QS0')
    def test_dependency_pin_and_origin_before_import(self):
        p = self.write('fake.py', {})
        with patch.object(m.importlib, 'import_module') as imp:
            with self.assertRaises(ValueError): m.dependency('test_audit_fake', p, {'files': {}})
            imp.assert_not_called()
        pin = hashlib.sha256(p.read_bytes()).hexdigest()
        with patch.dict(m.sys.modules, {'test_audit_fake': NS(__file__='/foreign.py')}), patch.object(m.importlib, 'import_module') as imp:
            with self.assertRaises(ValueError): m.dependency('test_audit_fake', p, {'files': {str(p): pin}})
            imp.assert_not_called()


class CaseFiles(Temporary):
    def setUp(self):
        super().setUp()
        # The unchanged dependency is pure saved-data code. No producer imports.
        path = m.runtime.E / 'q8-batch-v1/q8_audit.py'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), '59c396154604496ec01a0ef8d0e3dddf677e31e9b57d91472fb0e0965af3dcd1')
        spec = importlib.util.spec_from_file_location('quality_test_raw_reconcile', path)
        dep = importlib.util.module_from_spec(spec); spec.loader.exec_module(dep); self.reconcile = dep.reconcile
        self.case = {'id': 'test-json', 'kind': 'json', 'expected_reuse': 'zero', 'expected': {'values': [1]},
                     'prompt_ids': [1, 2], 'prompt_tokens': 2,
                     'request': {'messages': [{'role': 'user', 'content': 'synthetic'}], 'max_tokens': 32768,
                                 'reasoning_effort': 100, 'temperature': 1, 'top_p': 1, 'seed': 1}}
        self.response = response(); self.pid = 123
        self.write('skip-controls/test-json/request.json', self.case['request'])
        self.write('skip-controls/test-json/response.json', self.response)
        self.write('native-000/request.json', {'native_pid': 123, 'ids': [1, 2], 'max_new': 32768,
                   'has_images': False, 'sampling': {'temperature': 1, 'top_p': 1, 'seed': 1}})
        self.write('native-000/trace-receipt.json', {'native_pid': 123, 'error': None, 'DONE_observed': True, 'T_lines': 3})
        self.native = {'generated': 3, 'prompt_tokens': 2, 'reused': 0, 'finish': 'stop',
                       'prompt_ms': 1, 'decode_ms': 100, 'drafts_offered': 3, 'drafts_accepted': 2}
        self.write('native-000/native-statistics.json', self.native)
        (self.p / 'native-000/tokens.jsonl').write_text(''.join(json.dumps({'token': x, 'seconds': i * .1}) + '\n' for i, x in enumerate([3, 4, 5])))
        binding = self.reconcile(self.p / 'native-000', self.case, self.response, 123)
        self.write('skip-controls/test-json/native-audit.json', binding)
        self.write('logits.1.f32', {})
        self.size = {'bytes': 517120 * 7, 'rows': 7, 'finite_or_equivalence_proven': False}
        self.numerical = NS(dump_size=Mock(return_value=self.size), finite_dump=Mock(return_value={
            'bytes': 517120 * 7, 'rows': 7, 'sha256': 'a' * 64, 'all_finite': True, 'token_row_alignment_claimed': False}))
        self.row = {'id': 'test-json', 'passed': True, 'native': self.native, 'observed_tokens': 3,
                    'native_decode_tokens_per_second': 30.0, 'client_seconds': .2,
                    'content_characters': len(self.response['content']), 'reasoning_characters': len(self.response['reasoning']),
                    'manual_review_pending': False, 'general_quality_or_equivalence_claim': False, 'dump_size_only': self.size}
    def run_case(self):
        return m.case_audit(self.case, self.p, 0, 123, self.row, self.reconcile, self.numerical)


class Cases(CaseFiles, unittest.TestCase):
    def test_actual_raw_native_SSE_typed_state_reconciliation(self):
        row = self.run_case()
        self.assertEqual(row['observed_tokens'], 3); self.assertEqual(row['dump_size_only']['rows'], 7)
        self.numerical.finite_dump.assert_not_called()
    def test_changed_native_pid_request_or_DONE_refused(self):
        for name, key, value in [('request.json', 'native_pid', 124), ('request.json', 'max_new', 64),
                                 ('trace-receipt.json', 'DONE_observed', False)]:
            p = self.p / 'native-000' / name; old = p.read_text(); d = json.loads(old); d[key] = value; p.write_text(json.dumps(d))
            with self.subTest(key=key), self.assertRaises(ValueError): self.run_case()
            p.write_text(old)
    def test_typed_answer_float_is_not_integer(self):
        self.case['expected'] = {'values': [1.0]}
        with self.assertRaises(ValueError): self.run_case()
    def test_wrong_reuse_or_zero_draft_refused(self):
        for key, value in [('reused', 1), ('drafts_accepted', 0)]:
            p = self.p / 'native-000/native-statistics.json'; original = p.read_text(); n = json.loads(original); n[key] = value
            p.write_text(json.dumps(n))
            b = self.reconcile(self.p / 'native-000', self.case, self.response, 123)
            self.write('skip-controls/test-json/native-audit.json', b)
            with self.subTest(key=key), self.assertRaises(ValueError): self.run_case()
            p.write_text(original)
    def test_saved_phase_row_mutation_refused(self):
        self.row['observed_tokens'] = 4
        with self.assertRaises(ValueError): self.run_case()
    def test_stored_rate_uses_source_operation_order(self):
        self.native['decode_ms'] = 100.1
        self.write('native-000/native-statistics.json', self.native)
        binding = self.reconcile(self.p / 'native-000', self.case, self.response, 123)
        self.write('skip-controls/test-json/native-audit.json', binding)
        self.row['native_decode_tokens_per_second'] = 3 / (100.1 / 1000)
        self.assertTrue(self.run_case()['natural_stop'])
    def test_scan_keeps_variable_batch_rows_not_token_alignment(self):
        guard = Mock(); rows = m.scan_cases([self.case], self.p, 123, [self.row], self.reconcile, self.numerical, guard)
        guard.assert_called_once(); self.numerical.finite_dump.assert_called_once()
        self.assertEqual(rows[0]['dump']['rows'], 7); self.assertFalse(rows[0]['dump']['token_row_alignment_claimed'])
    def test_busy_blocks_before_any_finite_scan(self):
        with self.assertRaises(ValueError):
            m.scan_cases([self.case], self.p, 123, [self.row], self.reconcile, self.numerical, Mock(side_effect=ValueError('busy')))
        self.numerical.finite_dump.assert_not_called()
    def test_nonfinite_or_changed_size_stops_scan(self):
        for field, value in [('all_finite', False), ('bytes', 4), ('token_row_alignment_claimed', True)]:
            old = dict(self.numerical.finite_dump.return_value); self.numerical.finite_dump.return_value[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.scan_cases([self.case], self.p, 123, [self.row], self.reconcile, self.numerical, Mock())
            self.numerical.finite_dump.return_value = old


class Admission(Temporary, unittest.TestCase):
    def test_phase_before_host_or_heavy_hash(self):
        self.write('STATE.json', {'active_private_phase': 'foreign'})
        a = NS(ChunkProductionHost=Mock())
        with patch.object(m.runtime, 'E', self.p), self.assertRaises(ValueError): m.fresh_idle(a, Mock())
        a.ChunkProductionHost.assert_not_called()
    def test_busy_before_binding_scan(self):
        self.write('STATE.json', {}); host = Mock(); host.idle.return_value = False
        with patch.object(m.runtime, 'E', self.p), self.assertRaises(ValueError):
            m.fresh_idle(NS(ChunkProductionHost=lambda: host), NS(current_binding=lambda s: {'native_pid': 123}))
        host.guard_binding.assert_not_called()
    def test_actual_audit_phase_refusal_before_qualification(self):
        self.write('STATE.json', {'production_verification_pending': True})
        with patch.object(m.runtime, 'E', self.p), patch.object(m.runtime, 'support', return_value=(Mock(), Mock(), Mock(), Mock(), Mock())), patch.object(m.runtime, 'qualified') as q:
            with self.assertRaises(ValueError): m.audit('QS0')
            q.assert_not_called()
    def test_old_arm_refused_before_support(self):
        with patch.object(m.runtime, 'support') as support, self.assertRaises(ValueError): m.audit('N0')
        support.assert_not_called()


class Terminal(CaseFiles, TokenizerFiles, unittest.TestCase):
    """Synthetic terminal tree; live authority/source-observation adapters mocked.

    Actual saved byte readers, config contract, tokenizer pins, SSE/native
    reconciliation, closure/resource validators and finite scans remain real.
    """
    def setUp(self):
        super().setUp(); self.tokenizer_fixture()
        helper = m.runtime.E / 'decode-optimization-20261028/model-v1'
        path = helper / 'imma_storage.py'
        self.assertEqual(m.runtime.sha(path), 'd03c8f6d69e198e648014b15a00a4a7c3dd986815dac4a391b747924239e0143')
        spec = importlib.util.spec_from_file_location('quality_test_storage', path)
        storage = importlib.util.module_from_spec(spec); spec.loader.exec_module(storage)
        path = helper / 'imma_numeric_controls.py'
        self.assertEqual(m.runtime.sha(path), 'cb3252d95fdbeef733b7f14a1dea1629f59f2d7f6b741709b95b4ac654eab323')
        names = {'owned_storage_snapshot', 'dump_snapshot', 'dump_size', 'finite_dump'}
        tree = ast.parse(path.read_text()); funcs = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name in names]
        self.assertEqual({x.name for x in funcs}, names)
        ns = dict(array=array, hashlib=hashlib, math=math, os=os, pathlib=pathlib, stat=stat, sys=sys, storage=storage)
        exec(compile(ast.Module(body=funcs, type_ignores=[]), str(path), 'exec'), ns)
        numerical = NS(**{n: ns[n] for n in names})
        self.output = self.p / 'results/maya-s-quality-QS0-20261030T000000Z'
        self.folder = self.output / 'native'; self.folder.mkdir(parents=True)
        meta = self.p / 'maintenance'; meta.mkdir()
        window = self.p / 'windows/20261030T000001Z.json'
        self.write(str(window.relative_to(self.p)), {'command': [str(self.p / 'venv/bin/python3.14'), '-B', str(self.p / 'ms_quality.py'),
            '--phase', '--mode', 'quality', '--arm', 'QS0', '--output', str(self.output), '--proof', str(meta / 'proof.json')],
            'continued_from': 'synthetic-clean-parent', 'test_returncode': 0, 'maintenance_held': True,
            'maintenance_resume_allowed': True, 'restored': False})
        window.with_suffix('.telemetry.jsonl').write_text(json.dumps({'root_free_bytes': 130 * 2**30,
            'swap_pages': {'pswpout': 0}, 'kernel_capture_returncode': 0, 'kernel_fault_lines': []}) + '\n')
        def emit(path, obj): return self.write(str(path.relative_to(self.p)), obj)
        cases = []; rows = []
        for i in range(4):
            case = copy.deepcopy(self.case); case['id'] = 'terminal-' + str(i); cases.append(case)
            shutil.copytree(self.p / 'native-000', self.folder / ('native-%03d' % i))
            dest = self.folder / 'skip-controls' / case['id']
            emit(dest / 'request.json', case['request']); emit(dest / 'response.json', self.response)
            check = self.reconcile(self.folder / ('native-%03d' % i), case, self.response, 123)
            emit(dest / 'native-audit.json', check)
            dump = self.folder / ('logits.%d.f32' % (i + 1)); dump.write_bytes(struct.pack('<f', .25) * 129280)
            row = copy.deepcopy(self.row); row.update(id=case['id'], dump_size_only=numerical.dump_size(dump)); rows.append(row)
        manifest = {**self.tm, 'mode': 'quality', 'context': 1048576, 'default_output': 262144,
            'policy': m.fixtures.POLICY, 'cases': cases, 'lifecycle_cases': [], 'pack_relative_to_E': 'pack',
            'expected_mode1_activation_skipped_tokens': []}
        emit(self.p / 'quality-fixtures-A.json', manifest); emit(self.output / 'fixtures.json', manifest)
        base = {'exe': str(m.config.D / 'bin/maya-ds4'), 'tokenizer': str(self.tok),
                'args': ['--pack', str(self.pack), '--expert-profile', 'seed'], 'env': {}}
        stack = ExitStack(); self.addCleanup(stack.close)
        for module, key, value in [(m.runtime, 'P', self.p), (m.runtime, 'E', self.p), (m.runtime, 'R', self.p),
                                    (m.config, 'E', self.p), (m.config, 'BASE_PACK', self.pack),
                                    (m.config, 'BASE_NORMALIZED', m.config.normalized(base))]:
            stack.enter_context(patch.object(module, key, value))
        c = m.config.make_config(base, self.folder, 'quality', 'QS0'); factor = m.config.factor('quality', 'QS0')
        emit(self.p / 'base-config.json', base); emit(self.output / 'candidate-config.json', c)
        emit(self.output / 'candidate-config.shared-settings.json', {'max_tokens': 262144})
        configsha = m.runtime.sha(self.output / 'candidate-config.json')
        emit(self.folder / 'native-ready.json', {'pid': 123}); (self.folder / 'engine.log').write_text('synthetic startup')
        emit(self.output / 'startup-health.json', {}); emit(self.output / 'startup-models.json', {})
        actual = {'synthetic_observation': True}
        emit(self.output / 'startup-audit.json', {**actual, 'actual_process': {
            'actual_argv': m.config.expected_native_argv(c), 'controlled_env': c['env'],
            'actual_cgroup': '0::/user/strata-deepseek-window.service', 'same_executable': True,
            'native_sha256': m.config.BASE_NATIVE, 'native_pid': 123, 'start_ticks': 10},
            'native_file_limit_raw': 'Max file size %d %d bytes' % (storage.HARD_FILE_BYTES, storage.HARD_FILE_BYTES)})
        emit(self.output / 'server-start.json', {'pid': 122, 'argv': [str(self.p / 'venv/bin/python3.14'), '-u', '-B',
            str(self.p / 'ms_quality.py'), '--entry', '--mode', 'quality', '--arm', 'QS0', '--config',
            str(self.output / 'candidate-config.json'), '--config-sha256', configsha, '--trace-directory', str(self.folder)]})
        emit(self.folder / 'entry-audit.json', {'server_pid': 122, 'startup_retries': 0, 'default_effort': 100,
            'native_sha256': m.config.BASE_NATIVE, 'config_sha256': configsha, 'owned_window': str(window),
            'context': 1048576, 'output_allowance': 262144, 'whole_pack_factor': factor})
        close = {'native_pid': 123, 'server_pid': 122, 'returncode': 0, 'closed': True}
        (self.folder / 'native-close.jsonl').write_text(json.dumps(close) + '\n'); (self.folder / 'server.log').write_text('[strata] stopped')
        emit(self.folder / 'server-cleanup.json', {'passed': True, 'server_pid': 122, 'server_returncode': 0,
            'grace_timeout': False, 'application_stopped': True, 'native_ready_pid': 123, 'wait_error': None, 'native_close': [close]})
        emit(self.folder / 'native-file-bound.json', {'native_pid': 123, 'argv': m.config.expected_native_argv(c)[:-1],
            'API_limits_changed': False, 'file_limit_bytes': storage.HARD_FILE_BYTES})
        fence = Fence(); fence.setUp()
        emit(self.output / 'private-memory-fence.json', fence.initial)
        emit(self.output / 'private-memory-fence-restored.json', fence.restore)
        emit(meta / 'private-memory-fence-collected.json', fence.collected)
        emit(self.output / 'receipt.json', {'mode': 'quality', 'arm': 'QS0', 'private_cleanup_passed': True,
            'not_a_promotion': True, 'resource_fence_terminal': fence.end, 'arm_results': {
                'complete': True, 'native_request_count': 4, 'retry': False, 'reason': None, 'unrun_ids': [], 'DSI1_leftovers': [],
                'rows': rows, 'mode1_activation': {'activation_early_rows': []},
                'scores': [{'id': x['id'], 'passed': True, 'status': 'NATURAL_RESULT_SOURCE_AND_STATE_PASSED'} for x in cases]}})
        identity = {'native_sha256': m.config.BASE_NATIVE, 'config_sha256': m.config.BASE_SHA, 'context': 1048576,
            'output_default': 262144, 'prompt_skip_mode': 1, 'prefill_chunk': 4096, 'Q8': [1, 1], 'DSpark': True, 'images': True,
            'runtime_ablation': True, 'TP': 1, 'all_CPU_experts_RAM': True, 'native_pid': 321, 'start_binding': {'native_pid': 321}}
        verified = {'passed': True, 'selected_identity': identity, 'public': {'unauthenticated_models': 401,
            'authenticated_models': 200, 'known_answer_passed': True, 'SSE_done': True, 'finish': 'stop'},
            'health': {'loaded': True, 'max_context': 1048576, 'images': True,
                       'switcher': {'active_model': 'deepseek', 'default_model': 'deepseek', 'fault': None}}}
        (meta / 'public-ready-sse.txt').write_text('data: {"choices":[{"delta":{"content":"READY"},"finish_reason":"stop"}]}\ndata: [DONE]\n')
        emit(meta / 'old-owner-close.json', {'passed': True, 'binding': {}, 'native_close': {}, 'before': {}, 'after': {}})
        for name in ('ms_quality_audit.py', 'ms_audit.py'): (self.p / name).write_text('qualified synthetic source boundary')
        q = {'files': dict(self.tq['files']), 'allowed_automatic_cuts': {'A': [[19, 21]]}}
        for name in ('ms_quality_audit.py', 'ms_audit.py', 'quality-fixtures-A.json'): q['files'][str(self.p / name)] = m.runtime.sha(self.p / name)
        emit(self.p / 'quality-qualification.json', q); qpin = m.runtime.sha(self.p / 'quality-qualification.json')
        emit(meta / 'state.json', {'status': m.runtime.statuses('quality')['complete'], 'mode': 'quality', 'arm': 'QS0',
            'output': str(self.output), 'proof_path': str(meta / 'proof.json'), 'controller_pid': 55,
            'qualification_sha256': qpin, 'window': str(window), 'verified': verified})
        emit(meta / 'proof.json', {'qualified_for_owned_maya_s': True, 'mode': 'quality', 'arm': 'QS0',
            'output': str(self.output), 'qualification_sha256': qpin, 'files': q['files']})
        emit(self.p / 'quality-arms.json', {'QS0': {'attempted': True, 'controller_pid': 55, 'output': str(self.output)}})
        modules = {'ms_controls': NS(startup=Mock(return_value=actual)), 'imma_numeric_controls': numerical,
                   'imma_storage': storage, 'q8_audit': NS(reconcile=self.reconcile),
                   'skip_controls': NS(activation=Mock(return_value={'activation_early_rows': []}))}
        for obj, name, value in [(m, 'fresh_idle', Mock()), (m.runtime, 'support', Mock(return_value=(Mock(), Mock(),
            NS(binding_contract=Mock()), NS(close_contract=Mock(return_value=True)), Mock()))),
            (m.runtime, 'qualified', Mock(return_value=q)), (m.runtime, 'owned_paths', Mock(return_value=(self.output, meta))),
            (m.fixtures, 'validate_encoded', Mock()), (m, 'dependency', Mock(side_effect=lambda name, path, q: modules[name]))]:
            stack.enter_context(patch.object(obj, name, value))
    def metadata(self):
        d = m.audit('QS0'); root, path = m.stage_paths('QS0')
        self.write(str(path.relative_to(self.p)), d); self.child('metadata', path, d)
        return d, root
    def child(self, stage, path, d):
        root, meta = m.stage_paths('QS0')
        r = {'stage': stage, 'arm': 'QS0', 'qualification_sha256': d['qualification_sha256'],
             'metadata_sha256': m.runtime.sha(meta), 'result_path': str(path), 'result_sha256': m.runtime.sha(path),
             'audit_source_sha256': d['audit_source_sha256'], 'child': {'pid': 100, 'returncode': 0,
             'error': None, 'cleanup_errors': [], 'wall_seconds': .01, 'CPU_limit_seconds': 30,
             'wall_limit_seconds': 90, 'nice_increment': 15, 'Linux_AS_bytes': 512 * 2**20,
             'environment': {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
                             'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1'}}}
        return self.write(str((root / (stage + '.child.json')).relative_to(self.p)), r)
    def scan(self, i, d, root):
        row = m.scan_index('QS0', i); p = self.write(str((root / ('scan-%d.json' % i)).relative_to(self.p)), row)
        self.child('scan-%d' % i, p, d)
        return row
    def test_full_terminal_success_keeps_real_byte_and_case_checks(self):
        d, root = self.metadata(); self.assertFalse(d['passed']); self.assertTrue(d['metadata_passed'])
        for i in range(1, 5): self.scan(i, d, root)
        result = m.assemble('QS0')
        self.assertTrue(result['passed']); self.assertEqual(len(result['rows']), 4)
        for row in result['rows']:
            self.assertEqual(row['dump']['rows'], 1); self.assertEqual(row['observed_tokens'], 3)
            self.assertEqual(row['dump']['sha256'], hashlib.sha256(struct.pack('<f', .25) * 129280).hexdigest())
        self.assertFalse(result['cross_pack_numeric_equivalence'])
    def test_terminal_nonfinite_bytes_fail_without_mocking_scan(self):
        with (self.folder / 'logits.3.f32').open('r+b') as f: f.write(struct.pack('<f', float('nan')))
        d, root = self.metadata()
        self.scan(1, d, root); self.scan(2, d, root)
        with self.assertRaisesRegex(ValueError, 'Nonfinite model logit'): m.scan_index('QS0', 3)
    def test_terminal_raw_public_SSE_failure_not_hidden_by_passed_state(self):
        (self.p / 'maintenance/public-ready-sse.txt').write_text('data: [DONE]\n')
        with self.assertRaises(ValueError): m.audit('QS0')
    def test_one_scan_reads_only_its_exact_dump(self):
        d, root = self.metadata(); real = m.regular
        # All four are stat-checked, but only index1 reaches the full byte scanner.
        dep = m.dependency('imma_numeric_controls', None, {})
        with patch.object(dep, 'finite_dump', wraps=dep.finite_dump) as scan:
            row = self.scan(1, d, root)
            scan.assert_called_once_with(self.folder / 'logits.1.f32')
        self.assertEqual(row['index'], 1)
    def test_missing_or_failed_child_prevents_advancement(self):
        d, root = self.metadata()
        with self.assertRaises(FileNotFoundError): m.scan_index('QS0', 2)
        self.scan(1, d, root)
        p = root / 'scan-1.child.json'; r = m.j(p); r['child']['returncode'] = 1; p.write_text(json.dumps(r))
        with self.assertRaises(ValueError): m.scan_index('QS0', 2)
        with self.assertRaises((ValueError, FileNotFoundError)): m.assemble('QS0')
    def test_changed_dump_identity_rejected_before_scan(self):
        d, root = self.metadata()
        with (self.folder / 'logits.1.f32').open('ab') as f: f.write(b'xxxx')
        dep = m.dependency('imma_numeric_controls', None, {})
        with patch.object(dep, 'finite_dump') as scan, self.assertRaises(ValueError): m.scan_index('QS0', 1)
        scan.assert_not_called()
    def test_changed_raw_evidence_or_source_refuses_scan(self):
        d, root = self.metadata()
        for p in (self.folder / 'server.log', self.p / 'ms_quality_audit.py'):
            old = p.read_bytes(); p.write_bytes(old + b'x')
            with self.subTest(path=p), self.assertRaises(ValueError): m.scan_index('QS0', 1)
            p.write_bytes(old)
    def test_child_bounds_and_result_map_cannot_be_invented(self):
        d, root = self.metadata(); p = root / 'metadata.child.json'; old = p.read_bytes()
        for key, value in [('Linux_AS_bytes', None), ('CPU_limit_seconds', 120), ('returncode', False),
                           ('wall_seconds', 91), ('cleanup_errors', ['survivor'])]:
            r = json.loads(old); r['child'][key] = value; p.write_text(json.dumps(r))
            with self.subTest(key=key), self.assertRaises(ValueError): m.scan_index('QS0', 1)
        r = json.loads(old); r['result_sha256'] = '0' * 64; p.write_text(json.dumps(r))
        with self.assertRaises(ValueError): m.scan_index('QS0', 1)
    def test_first_attempt_marker_blocks_replay(self):
        root, meta = m.stage_paths('QS0'); root.mkdir(parents=True); (root / 'metadata.attempt.json').write_text('{}')
        with patch.object(m.sys, 'argv', ['audit', '--arm', 'QS0', '--stage', 'metadata']), patch.object(m, 'audit') as work:
            with self.assertRaises(FileExistsError): m.main()
            work.assert_not_called()


if __name__ == '__main__': unittest.main()
