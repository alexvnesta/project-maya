"""Pure contracts and scripted owned-controller tests, never model/service actions."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest import mock

import prose_measure as m

ID = 'a' * 12
OTHER = 'b' * 12


def snapshot(seq=0, events=(), requests=(), *, active=0, queued=0, reserved=0, inflight=0, waiting=0, busy=False):
    return {'instance': {'id': 'api-instance', 'state': 'ready'},
            'work': {'active': active, 'queued': queued, 'admission_reserved': reserved,
                     'requests_omitted': 0, 'requests': list(requests)},
            'activity': {'last_seq': seq, 'events': list(events)},
            'router': {'active_model': 'deepseek', 'default_model': 'deepseek', 'inflight': inflight,
                       'waiting': waiting, 'fault': None, 'status': 'ok', 'busy': busy}}


def events(identity=ID):
    return [{'seq': 1, 'request_id': identity, 'event': 'queued'},
            {'seq': 2, 'request_id': identity, 'event': 'admitted'},
            {'seq': 3, 'request_id': identity, 'event': 'finished', 'outcome': 'stop'}]


def response():
    return {'content': 'Useful prose. Last.', 'reasoning': 'Synthetic reasoning.', 'finish_reason': 'stop',
            'done': True, 'usage': {'completion_tokens': 10},
            'timings': {'predicted_n': 10, 'predicted_ms': 1000.0, 'predicted_per_second': 12.0,
                        'prompt_n': 20, 'cache_n': 0, 'prompt_ms': 1.0, 'draft_n': 8, 'draft_n_accepted': 7},
            'client_full_seconds': 1.5, 'buffered_first_visible_seconds': 1.4}


def history():
    return {'id': ID, 'finish': 'stop', 'engine_generated': 12, 'output_tokens': 10, 'decode_ms': 1000.0, 'prompt_tokens': 20,
            'prompt_total': 20, 'prompt_read': 20, 'reused': 0, 'drafts_offered': 8, 'drafts_accepted': 7, 'hit_rate': .123, 'reasoning_recoveries': 0}


class FakeStream:
    def __init__(self, body, finished=True):
        self.finished = threading.Event()
        if finished: self.finished.set()
        self.started = False
        self.cancelled = False
    def start(self): self.started = True; return self
    def result(self): return response()
    def cancel(self, timeout=3): self.cancelled = True; self.finished.set()
    def partial(self): return {'cancelled': self.cancelled}


class FixtureTests(unittest.TestCase):
    def test_frozen_profile_and_literal_cases(self):
        value = m.load(m.HERE / 'prose-fixtures.json')
        self.assertEqual([c['id'] for c in m.fixtures(value)['cases']], list(m.CASES))
        self.assertEqual(value['policy']['max_tokens'], 32768)
        self.assertTrue(value['prior_numerical_HOLD'])

    def test_profile_type_and_limit_changes_rejected(self):
        original = m.load(m.HERE / 'prose-fixtures.json')
        for key, change in [('max_tokens', 64), ('reasoning_effort', 100.0), ('stream', 1), ('seed', 2)]:
            with self.subTest(key=key):
                value = copy.deepcopy(original); value['cases'][0]['request'][key] = change
                with self.assertRaises(ValueError): m.fixtures(value)
        value = copy.deepcopy(original); value['candidate_allowed'] = True
        with self.assertRaises(ValueError): m.fixtures(value)

    def test_encoded_bounds_never_resize(self):
        original = m.load(m.HERE / 'prose-fixtures.json')
        value = copy.deepcopy(original); value['CPU_only'] = True
        for case in value['cases']: case.update(prompt_ids=[1] * 64, prompt_tokens=64)
        self.assertIs(m.encoded_fixture(value, original), value)
        for n in (63, 1025):
            changed = copy.deepcopy(value); changed['cases'][0].update(prompt_ids=[1] * n, prompt_tokens=n)
            with self.assertRaises(ValueError): m.encoded_fixture(changed, original)


class EpochTests(unittest.TestCase):
    def test_unique_epoch_released_and_own_router_busy_allowed(self):
        epoch = m.Epoch(snapshot())
        active = snapshot(2, events()[:2], [{'id': ID, 'state': 'reading'}], active=1, reserved=1, busy=True)
        epoch.safe(active)
        self.assertFalse(epoch.released(active))
        self.assertTrue(epoch.released(snapshot(3, events())))

    def test_initial_busy_or_nondefault_refused(self):
        for value in (snapshot(busy=True), snapshot(reserved=1), snapshot(inflight=1), snapshot(waiting=1)):
            with self.assertRaises(ValueError): m.Epoch(value)
        value = snapshot(); value['router']['active_model'] = 'qwen'
        with self.assertRaises(ValueError): m.Epoch(value)

    def test_router_user_arrival_cancels_even_with_one_native_id(self):
        for key in ('inflight', 'waiting'):
            value = snapshot(2, events()[:2], [{'id': ID, 'state': 'reading'}], active=1, reserved=1)
            value['router'][key] = 1
            with self.assertRaisesRegex(ValueError, 'FOREIGN_ROUTER'):
                m.Epoch(snapshot()).safe(value)

    def test_native_extra_request_and_queue_reservation_refused(self):
        for value in (snapshot(reserved=2), snapshot(active=1, queued=1),
                      snapshot(2, [events()[0], {'seq': 2, 'request_id': OTHER, 'event': 'queued'}])):
            with self.assertRaisesRegex(ValueError, 'FOREIGN_OR_AMBIGUOUS'):
                m.Epoch(snapshot()).safe(value)

    def test_event_gap_duplicate_reset_and_restart_refused(self):
        for value in (snapshot(3, events()[1:]), snapshot(2, [events()[0], events()[0]])):
            with self.assertRaises(ValueError): m.Epoch(snapshot()).safe(value)
        epoch = m.Epoch(snapshot(4))
        with self.assertRaises(ValueError): epoch.safe(snapshot(3))
        value = snapshot(); value['instance']['id'] = 'restarted'
        with self.assertRaises(ValueError): m.Epoch(snapshot()).safe(value)

    def test_boolean_counters_omitted_and_wrong_id_namespace_refused(self):
        for key in ('active', 'queued', 'admission_reserved'):
            value = snapshot(); value['work'][key] = True
            with self.assertRaises(ValueError): m.Epoch(snapshot()).safe(value)
        value = snapshot(); value['work']['requests_omitted'] = 1
        with self.assertRaises(ValueError): m.Epoch(snapshot()).safe(value)
        with self.assertRaises(ValueError): m.Epoch(snapshot()).safe(snapshot(3, events('chatcmpl-own')))

    def test_own_release_not_global_idle_and_ambiguity_not_attribution(self):
        epoch = m.Epoch(snapshot()); epoch.safe(snapshot(3, events()))
        # User may remain reserved while our identified terminal is absent.
        self.assertTrue(epoch.released(snapshot(3, events(), reserved=1)))
        row = {'seq': 4, 'request_id': OTHER, 'event': 'queued'}
        self.assertFalse(epoch.released(snapshot(4, [*events(), row], [{'id': OTHER, 'state': 'queued'}], reserved=1)))

    def test_observer_drops_shared_content_and_unrelated_history(self):
        native = snapshot()
        native['secret_user_text'] = 'do not copy'
        native['work']['requests'] = [{'id': ID, 'state': 'reading', 'messages': ['private']}]
        router = {'switcher': native['router'], 'status': 'ok', 'busy': False, 'content': 'private'}
        result = m.observe(lambda port, path: native if port == 18141 else router)
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn('do not copy', json.dumps(result))


class MetricsTests(unittest.TestCase):
    def test_native_engine_count_kept_separate_from_api_count(self):
        value = m.metrics(response(), history())
        self.assertEqual(value['api_generated_tokens'], 10)
        self.assertEqual(value['exact_native_generated_tokens'], 12)
        self.assertEqual(value['exact_native_tokens_per_second'], 12)
        self.assertIsNone(value['raw_expert_hits']); self.assertIsNone(value['true_TTFT'])

    def test_nonfinite_negative_boolean_drafts_and_continuation_refused(self):
        for key, value in [('engine_generated', True), ('decode_ms', float('nan')),
                           ('decode_ms', 0), ('drafts_accepted', 9), ('reasoning_recoveries', 1)]:
            row = history(); row[key] = value
            with self.assertRaises(ValueError): m.metrics(response(), row)
        bad = response(); bad['timings']['predicted_ms'] = -1
        with self.assertRaises(ValueError): m.metrics(bad, history())

    def test_slot_session_cache_uses_exact_server_max_expression(self):
        result = response(); native = history()
        native['prompt_read'] = 5
        result['timings'].update(prompt_n=5, cache_n=15)
        value = m.metrics(result, native)
        self.assertEqual(value['prompt_reused'], 15)
        native['prompt_read'] = 6
        with self.assertRaisesRegex(ValueError, 'counters disagree'): m.metrics(result, native)

    def test_history_sse_draft_decode_prompt_conflicts_refused(self):
        for key, value in [('drafts_offered', 9), ('decode_ms', 1001), ('prompt_total', 21), ('output_tokens', 11)]:
            native = history(); native[key] = value
            with self.assertRaises(ValueError): m.metrics(response(), native)

    def test_history_keeps_only_exact_own_metadata(self):
        own = history(); own['content'] = 'never export'
        other = dict(history(), id=OTHER, messages=['user private'])
        result = m.own_history(ID, lambda *args: {'requests': [other, own]})
        self.assertEqual(result['engine_generated'], 12)
        self.assertNotIn('content', result); self.assertNotIn('messages', result)
        for rows in ([], [own, own]):
            with self.assertRaises(ValueError): m.own_history(ID, lambda *args: {'requests': rows})


class CaseTests(unittest.TestCase):
    def setUp(self):
        self.case = {'id': 'expository-prose', 'request': {}, 'expected_last_sentence': 'Last.'}
        self.done = snapshot(3, events())

    def run_case(self, rows, **kwargs):
        defaults = dict(stream_factory=FakeStream, observe_fn=mock.Mock(side_effect=rows),
                        history_fn=lambda _: history(), deadline=10, cleanup_deadline=20,
                        clock=lambda: 0, sleep=lambda _: None)
        defaults.update(kwargs)
        return m.measure_case(self.case, **defaults)

    def test_natural_prose_is_manual_pending_not_wordcount_quality(self):
        row = self.run_case([snapshot(), snapshot(), self.done, self.done])
        self.assertEqual(row['status'], 'NATURAL_COMPLETION_MANUAL_REVIEW_PENDING')
        self.assertFalse(row['manual_quality_passed'])
        self.assertEqual(row['observed_words'], 3)
        self.assertTrue(row['last_sentence_matches'])

    def test_before_post_foreign_epoch_defers_without_stream(self):
        factory = mock.Mock()
        with self.assertRaises(ValueError):
            self.run_case([snapshot(), self.done], stream_factory=factory)
        factory.assert_not_called()

    def test_racing_user_after_post_closes_only_owned_stream(self):
        own = FakeStream({}, finished=False)
        raced = snapshot(3, events(), inflight=1, busy=True)
        row = self.run_case([snapshot(), snapshot(), raced, self.done], stream_factory=lambda _: own)
        self.assertTrue(own.cancelled)
        self.assertEqual(row['status'], 'INCOMPLETE_HOLD_NO_RETRY')
        self.assertFalse(row['retry_allowed'])

    def test_foreign_arrival_during_history_capture_blocks_rate(self):
        raced = snapshot(4, [*events(), {'seq': 4, 'request_id': OTHER, 'event': 'queued'}], reserved=1)
        row = self.run_case([snapshot(), snapshot(), self.done, raced])
        self.assertNotIn('metrics', row); self.assertEqual(row['status'], 'INCOMPLETE_HOLD_NO_RETRY')

    def test_resource_failure_cancels_and_preserves_primary(self):
        own = FakeStream({})
        light = mock.Mock(side_effect=[None, ValueError('root floor')])
        # No native ID observed: clean-up observation supplies unique terminal evidence.
        row = self.run_case([snapshot(), snapshot(), self.done], stream_factory=lambda _: own, lightweight=light)
        self.assertTrue(own.cancelled); self.assertIn('root floor', row['primary_error'])

    def test_primary_and_cancel_failure_both_preserved(self):
        own = FakeStream({}); own.cancel = mock.Mock(side_effect=ValueError('reader failed'))
        row = self.run_case([snapshot(), snapshot(), self.done], stream_factory=lambda _: own,
                            lightweight=mock.Mock(side_effect=[None, ValueError('primary')]))
        self.assertIn('primary', row['primary_error']); self.assertIn('reader failed', row['cleanup_errors'][0])

    def test_soft_deadline_cancels_without_extending_cap(self):
        own = FakeStream({})
        clock = mock.Mock(side_effect=[0, 11, 11, 11, 11, 11])
        row = self.run_case([snapshot(), snapshot(), self.done], stream_factory=lambda _: own, clock=clock)
        self.assertTrue(own.cancelled); self.assertIn('deadline', row['primary_error'])

    def test_panel_preserves_unrun_second_after_partial_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = [dict(self.case, id=name) for name in m.CASES]
            with mock.patch.object(m, 'measure_case', return_value={'status': 'INCOMPLETE_HOLD_NO_RETRY'}) as run:
                rows = m.panel(cases, Path(tmp).resolve())
            self.assertEqual(run.call_count, 1); self.assertEqual(rows[1]['status'], 'UNRUN')


class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.path = self.root / 'STATE.json'
        self.original = {'decode_optimization_current': {'selected_identity': 'untouched'}, 'old_HOLD': True,
                         'active_gpu_experiment': False}
        self.path.write_text(json.dumps(self.original))
        self.record = {'pid': 123, 'nonce': 'own', 'output': str(self.root / 'P0-FIRST')}
    def tearDown(self): self.tmp.cleanup()

    def test_claim_release_preserves_old_selected_and_hold(self):
        m.claim(self.path, self.record); m.release(self.path, self.record)
        value = m.load(self.path)
        self.assertEqual(value['decode_optimization_current'], self.original['decode_optimization_current'])
        self.assertTrue(value['old_HOLD']); self.assertFalse(value['active_gpu_experiment'])

    def test_busy_claim_has_no_mutation(self):
        self.original['active_private_phase'] = {'pid': 999}; self.path.write_text(json.dumps(self.original))
        before = self.path.read_bytes()
        with self.assertRaises(ValueError): m.claim(self.path, self.record)
        self.assertEqual(self.path.read_bytes(), before)

    def test_foreign_cleanup_and_missing_reservation_untouched(self):
        for value in ({'active_gpu_experiment': {'pid': 999}}, self.original):
            self.path.write_text(json.dumps(value)); before = self.path.read_bytes()
            with self.assertRaises(ValueError): m.release(self.path, self.record)
            self.assertEqual(self.path.read_bytes(), before)

    def test_compare_write_conflict_refuses_no_foreign_overwrite(self):
        before = self.path.read_bytes(); self.path.write_text('{"foreign":true}')
        with self.assertRaises(ValueError): m.cas_state(self.path, before, self.original)
        self.assertEqual(m.load(self.path), {'foreign': True})

    def test_real_directory_symlink_ancestor_refused(self):
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): m.real_directory(alias)

    def test_resource_root_swap_reset_limit_and_log_symlink(self):
        disk = lambda _: types.SimpleNamespace(free=132 * 2**30)
        self.assertEqual(m.resource_check(self.root, 5, disk=disk, swap=lambda: 5)['swap_delta_bytes'], 0)
        for swap in (lambda: 4, lambda: 5 + 2**18):
            with self.assertRaises(ValueError): m.resource_check(self.root, 5, disk=disk, swap=swap)
        with self.assertRaises(ValueError):
            m.resource_check(self.root, 5, disk=lambda _: types.SimpleNamespace(free=119 * 2**30), swap=lambda: 5)
        (self.root / 'link').symlink_to(self.path)
        with self.assertRaises(ValueError): m.resource_check(self.root, 5, disk=disk, swap=lambda: 5)

    def test_existing_output_never_replayed(self):
        (self.root / 'P0-FIRST').mkdir()
        with mock.patch.object(m, 'HERE', self.root):
            with self.assertRaisesRegex(ValueError, 'already attempted'):
                m.run(mock.Mock(), types.SimpleNamespace(current_binding=lambda state: {}), {}, 'q', {})

    def test_production_lock_is_observed_not_held_for_benchmark(self):
        import fcntl
        lock = self.root / 'experiment.lock'; lock.touch()
        with mock.patch.object(fcntl, 'flock', side_effect=BlockingIOError) as operation:
            m.held_production_lock(lock)
            self.assertEqual(operation.call_count, 1)
        with mock.patch.object(fcntl, 'flock') as operation:
            with self.assertRaisesRegex(ValueError, 'unheld'): m.held_production_lock(lock)
            self.assertEqual(operation.call_args_list[-1].args[1], fcntl.LOCK_UN)

    def test_actual_run_failure_releases_only_own_reservation(self):
        (self.root / 'prose-fixtures.json').write_text((m.HERE / 'prose-fixtures.json').read_text())
        runtime = types.SimpleNamespace(current_binding=lambda state: {'id': 'current'})
        with mock.patch.object(m, 'HERE', self.root), mock.patch.object(m, 'E', self.root), \
             mock.patch.object(m, 'observe', return_value=snapshot()), \
             mock.patch.object(m, 'held_production_lock'), \
             mock.patch.object(m, 'process_identity', side_effect=ValueError('owned pre-request fault')), \
             mock.patch.object(m.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=200 * 2**30)):
            with self.assertRaises(ValueError): m.run(mock.Mock(), runtime, {'id': 'current'}, 'q', {})
        result = m.load(self.root / 'P0-FIRST/controller-result.json')
        self.assertIn('owned pre-request fault', result['primary_error'])
        self.assertTrue(result['own_reservation_released'])
        self.assertEqual(m.load(self.path)['decode_optimization_current'], self.original['decode_optimization_current'])

    def test_actual_run_foreign_replacement_is_not_cleared(self):
        def replace(_):
            value = m.load(self.path); value['active_gpu_experiment'] = {'pid': 999}
            self.path.write_text(json.dumps(value)); raise ValueError('owner race')
        with mock.patch.object(m, 'HERE', self.root), mock.patch.object(m, 'E', self.root), \
             mock.patch.object(m, 'observe', return_value=snapshot()), mock.patch.object(m, 'held_production_lock'), \
             mock.patch.object(m, 'process_identity', side_effect=replace), \
             mock.patch.object(m.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=200 * 2**30)):
            with self.assertRaises(ValueError): m.run(mock.Mock(), types.SimpleNamespace(current_binding=lambda state: {}), {}, 'q', {})
        self.assertEqual(m.load(self.path)['active_gpu_experiment'], {'pid': 999})
        row = m.load(self.root / 'P0-FIRST/controller-result.json')
        self.assertIn('owner race', row['primary_error']); self.assertIsNotNone(row['reservation_release_error'])


class QualificationTests(unittest.TestCase):
    def proof(self):
        q = {'test_ids': ['test.module.control'], 'source_sha256': {'a.py': 'pin'}, 'source_input_sha256': {'old.py': 'old'}}
        receipt = dict(q, passed=True, controls=1, GPU_execution=False, native_execution=False, compiler_execution=False)
        child = {'returncode': 0, 'CPU_s': 30, 'wall_s': 90, 'nice': 15, 'CUDA_hidden': True,
                 'Linux_AS_MiB': 512, 'error': None, 'cleanup_errors': []}
        return q, receipt, child

    def test_exact_cpu_maps_ids_and_typed_limits(self):
        q, receipt, child = self.proof()
        m.cpu_contract(receipt, child, q, 'linux')
        child['Linux_AS_MiB'] = None
        m.cpu_contract(receipt, child, q, 'darwin')

    def test_missing_changed_cpu_ids_sources_inputs_or_execution_refused(self):
        for key, value in [('test_ids', ['other']), ('source_sha256', {}), ('source_input_sha256', {}),
                           ('controls', True), ('passed', False), ('GPU_execution', True)]:
            q, receipt, child = self.proof(); receipt[key] = value
            with self.assertRaises(ValueError): m.cpu_contract(receipt, child, q, 'linux')

    def test_relaxed_limits_cleanup_errors_and_bool_returncode_refused(self):
        for key, value in [('CPU_s', 60), ('wall_s', 120), ('nice', 0), ('Linux_AS_MiB', None),
                           ('CUDA_hidden', False), ('returncode', False), ('cleanup_errors', ['failure']), ('error', 'failure')]:
            q, receipt, child = self.proof(); child[key] = value
            with self.assertRaises(ValueError): m.cpu_contract(receipt, child, q, 'linux')

    def test_changed_qualification_or_wrong_scope_refused_before_input_reads(self):
        with mock.patch.object(m, 'sha', return_value='changed'), mock.patch.object(m, 'load') as read:
            with self.assertRaises(ValueError): m.qualified(m.HERE / 'qualification.json', 'frozen')
            read.assert_not_called()
        with mock.patch.object(m, 'sha', return_value='frozen'), mock.patch.object(m, 'load', return_value={'scope': 'candidate'}):
            with self.assertRaises(ValueError): m.qualified(m.HERE / 'qualification.json', 'frozen')


if __name__ == '__main__':
    unittest.main()
