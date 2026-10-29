"""New wrapper boundaries. Existing socket/API transport proofs remain pinned."""
import math
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
import approved as a


def response():
    return {'done': True, 'finish_reason': 'stop', 'model': 'selected', 'content': 'Complete prose. End.',
            'reasoning': 'retained', 'client_full_seconds': 2,
            'usage': {'completion_tokens': 12},
            'timings': {'predicted_n': 12, 'prompt_n': 169, 'cache_n': 0,
                        'draft_n': 10, 'draft_n_accepted': 8, 'predicted_ms': 1000,
                        'prompt_ms': 1, 'predicted_per_second': 13.1}}


class Stream:
    def __init__(self, body):
        self.finished = threading.Event(); self.finished.set(); self.cancelled = False
    def start(self): return self
    def result(self): return response()
    def cancel(self, timeout=3): self.cancelled = True
    def partial(self): return {'cancelled': self.cancelled}


class Contracts(unittest.TestCase):
    def setUp(self):
        self.case = {'id': 'case', 'request': {'model': 'selected'}, 'expected_last_sentence': 'End.'}
        self.finite = lambda n: type(n) in (float, int) and math.isfinite(n)
    def test_rate_is_server_reported_not_recomputed_from_API_count(self):
        r = a.rates(response(), self.finite)
        self.assertEqual(r['server_reported_rounded_native_tokens_per_second'], 13.1)
        self.assertIsNone(r['exact_native_generated_tokens'])
        self.assertEqual(r['API_generated_tokens'], 12)
    def test_missing_done_length_boolean_and_nonfinite_counters_block(self):
        for field, value in [('done', False), ('finish_reason', 'length')]:
            r = response(); r[field] = value
            with self.assertRaises(ValueError): a.rates(r, self.finite)
        for field, value in [('draft_n', True), ('predicted_ms', 0), ('predicted_per_second', float('nan'))]:
            r = response(); r['timings'][field] = value
            with self.assertRaises(ValueError): a.rates(r, self.finite)
    def test_complete_prose_keeps_full_answer_and_requires_manual_review(self):
        r = a.sample(self.case, factory=Stream, check=lambda: None, deadline=10,
                     finite=self.finite, clock=lambda: 0)
        self.assertEqual(r['status'], 'COMPLETE_MANUAL_REVIEW_PENDING')
        self.assertEqual(r['result']['reasoning'], 'retained')
        self.assertFalse(r['manual_quality_passed'])
    def test_owner_resource_fault_cancels_only_owned_socket(self):
        stream = Stream({}); check = Mock(side_effect=[None, ValueError('owner changed')])
        r = a.sample(self.case, factory=lambda _: stream, check=check, deadline=10,
                     finite=self.finite, clock=lambda: 0)
        self.assertTrue(stream.cancelled); self.assertEqual(r['status'], 'INCOMPLETE_HOLD')
        self.assertIn('owner changed', r['error']); self.assertFalse(r['retry'])
    def test_deadline_preserves_incomplete_no_extension(self):
        r = a.sample(self.case, factory=Stream, check=lambda: None, deadline=0,
                     finite=self.finite, clock=lambda: 1)
        self.assertEqual(r['status'], 'INCOMPLETE_HOLD')
    def test_secondary_cleanup_failure_keeps_primary(self):
        stream = Stream({}); stream.cancel = Mock(side_effect=ValueError('cleanup'))
        r = a.sample(self.case, factory=lambda _: stream, check=Mock(side_effect=ValueError('primary')),
                     deadline=10, finite=self.finite, clock=lambda: 0)
        self.assertIn('primary', r['error']); self.assertIn('cleanup', r['cleanup_errors'][0])
    def test_panel_preserves_remaining_UNRUN_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = a.panel([dict(self.case, id='one'), dict(self.case, id='two')], Path(tmp),
                lambda path, row: None, factory=Stream, check=lambda: None, deadline=0,
                finite=self.finite, clock=lambda: 1)
        self.assertEqual(rows[1]['status'], 'UNRUN')
    def test_old_helpers_and_two_full_policy_fixtures_are_exact(self):
        m = a.helpers(); f = m.fixtures(m.load(a.OLD / 'prose-fixtures.json'))
        self.assertEqual([c['id'] for c in f['cases']], ['expository-prose', 'creative-prose'])
        self.assertEqual(f['policy']['reasoning_effort'], 100)
        self.assertEqual(f['policy']['max_tokens'], 32768)
        self.assertEqual(f['context'], 1048576); self.assertEqual(f['output_allowance'], 262144)
    def test_claim_write_then_raise_releases_owned_record_and_checks_owner(self):
        record = {'pid': 1}; state = {}; released = []
        def claim(path, value):
            state.update(active_gpu_experiment=value, prose_speed_current=dict(value, active=True))
            raise ValueError('claim readback failed')
        m = SimpleNamespace(E=Path('/synthetic'), claim=claim, load=lambda _: state,
                            release=lambda *args: released.append(True))
        host = SimpleNamespace(guard_binding=Mock())
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'claim readback failed'):
                a.with_custody(m, host, record, Path(tmp)/'out', Mock())
        self.assertEqual(released, [True]); host.guard_binding.assert_called_once()
    def test_primary_and_release_failure_both_retained_owner_check_still_runs(self):
        record = {'pid': 1}; state = {'active_gpu_experiment': record, 'prose_speed_current': dict(record, active=True)}
        with tempfile.TemporaryDirectory() as tmp:
            m = SimpleNamespace(E=Path(tmp), claim=Mock(), load=lambda _: state,
                release=Mock(side_effect=ValueError('release failed')),
                emit=lambda path, value: path.write_text(__import__('json').dumps(value)))
            host = SimpleNamespace(guard_binding=Mock())
            with self.assertRaisesRegex(ValueError, 'body failed'):
                a.with_custody(m, host, record, Path(tmp)/'out', Mock(side_effect=ValueError('body failed')))
            row = __import__('json').loads((Path(tmp)/'out/cleanup.json').read_text())
            self.assertIn('body failed', row['primary_error']); self.assertIn('release failed', row['release_error'])
            host.guard_binding.assert_called_once()


if __name__ == '__main__':
    unittest.main()
