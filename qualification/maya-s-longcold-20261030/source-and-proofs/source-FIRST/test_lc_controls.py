"""Synthetic negatives for the new whole-pack boundary. No GPU/service action."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import lc_controls as c
import lc_runtime as r


def sample():
    case = {'id': 'new', 'kind': 'json', 'request': {'max_tokens': 32768},
            'expected': {'n': 3}, 'expected_reuse': 'zero', 'prompt_tokens': 7000}
    response = {'status': 200, 'done': True, 'finish_reason': 'stop', 'content': '{"n":3}'}
    proof = {'observed_tokens': 5, 'native': {'finish': 'stop', 'generated': 5, 'reused': 0,
             'drafts_offered': 9, 'drafts_accepted': 4, 'prompt_ms': 1000., 'decode_ms': 100.}}
    return case, response, proof


class ScoreTests(unittest.TestCase):
    def test_natural_exact_known_answer(self):
        case, response, proof = sample(); out = c.score(case, response, proof, quality=True)
        self.assertTrue(out['passed']); self.assertEqual(out['native_decode_tokens_per_second'], 50.)
        self.assertFalse(out['general_quality_or_equivalence_claim'])

    def test_wrong_json_type(self):
        case, response, proof = sample(); response['content'] = '{"n":3.0}'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_duplicate_key(self):
        case, response, proof = sample(); response['content'] = '{"n":2,"n":3}'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_nonfinite_json(self):
        case, response, proof = sample(); response['content'] = '{"n":NaN}'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_cap_is_not_speed_result(self):
        case, response, proof = sample(); response['finish_reason'] = 'length'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_wrong_native_finish(self):
        case, response, proof = sample(); proof['native']['finish'] = 'cancel'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_no_DONE(self):
        case, response, proof = sample(); response['done'] = False
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_budget_partial(self):
        case, response, proof = sample(); response['intentional_budget_stop'] = True
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_zero_output(self):
        case, response, proof = sample(); proof['observed_tokens'] = proof['native']['generated'] = 0
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_fullcap_even_with_stop(self):
        case, response, proof = sample(); proof['observed_tokens'] = proof['native']['generated'] = 32768
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_warm_reuse(self):
        case, response, proof = sample(); case['expected_reuse'] = 'prompt-minus-one'; proof['native']['reused'] = 6999
        self.assertTrue(c.score(case, response, proof, quality=False)['passed'])

    def test_bad_warm_reuse(self):
        case, response, proof = sample(); case['expected_reuse'] = 'prompt-minus-one'
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_actual_drafter_required_quality(self):
        case, response, proof = sample(); proof['native']['drafts_accepted'] = 0
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=True)

    def test_draft_overacceptance_fault(self):
        case, response, proof = sample(); proof['native']['drafts_accepted'] = 10
        with self.assertRaises(ValueError): c.score(case, response, proof, quality=False)

    def test_nonfinite_timing_fault(self):
        case, response, proof = sample(); proof['native']['decode_ms'] = float('nan')
        with self.assertRaises(ValueError): c.score(case, response, proof, quality=False)

    def test_prose_manual_pending(self):
        case, response, proof = sample(); case['kind'] = 'prose'
        self.assertTrue(c.score(case, response, proof, quality=False)['manual_review_pending'])

    def test_unmatched_native_count_fault(self):
        case, response, proof = sample(); proof['native']['generated'] = 6
        with self.assertRaises(ValueError): c.score(case, response, proof, quality=False)

    def test_required_prose_ending(self):
        case, response, proof = sample(); case.update(kind='prose', expected_last_sentence='Required end.')
        with self.assertRaises(c.Incomplete): c.score(case, response, proof, quality=False)

    def test_fault_retains_issued_and_unrun_scores(self):
        case, _, _ = sample(); saved = []
        with self.assertRaises(RuntimeError):
            c.run_cases([case, dict(case, id='later')], Path('/unused'), 7, 100,
                        issue=Mock(side_effect=RuntimeError('fault')), quality=False,
                        dump_snapshot=Mock(), dump_size=Mock(), save_progress=lambda v: saved.append(copy.deepcopy(v)))
        self.assertEqual([s['status'] for s in saved[-1]['scores']], ['EXECUTION_FAULT_HOLD', 'UNRUN'])

    def test_first_wrong_retains_unrun(self):
        case, response, proof = sample(); response['content'] = '{}'; issued = Mock(return_value=(response, proof))
        out = c.run_cases([case, dict(case, id='later')], Path('/unused'), 7, 100,
                          issue=issued, quality=False, dump_snapshot=Mock(), dump_size=Mock())
        self.assertFalse(out['complete']); self.assertEqual(out['unrun_ids'], ['later'])
        self.assertEqual(out['scores'][0]['status'], 'WRONG_CAP_PARTIAL_HOLD'); self.assertEqual(issued.call_count, 1)

    def test_genuine_fault_escapes_no_retry(self):
        case, _, _ = sample(); issued = Mock(side_effect=RuntimeError('native fault'))
        with self.assertRaisesRegex(RuntimeError, 'native fault'):
            c.run_cases([case], Path('/unused'), 7, 100, issue=issued, quality=False,
                        dump_snapshot=Mock(), dump_size=Mock())
        self.assertEqual(issued.call_count, 1)

    def test_incomplete_four_dumps_blocks(self):
        case, response, proof = sample()
        out = c.run_cases([case], Path('/unused'), 7, 100, issue=Mock(return_value=(response, proof)),
                          quality=True, dump_snapshot=Mock(return_value={'status': 'INCOMPLETE_HOLD'}), dump_size=Mock())
        self.assertFalse(out['complete'])


class TokenTests(unittest.TestCase):
    def check(self, rows, n=2):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'tokens'; p.write_text(''.join(json.dumps(x) + '\n' for x in rows))
            return c.token_contract(p, n)

    def test_complete_source_ids(self):
        out = self.check([{'token': 0, 'seconds': .1}, {'token': 129279, 'seconds': .1}])
        self.assertEqual(out['count'], 2); self.assertEqual(len(out['ordered_ids_sha256']), 64)

    def test_invalid_vocabulary(self):
        with self.assertRaises(ValueError): self.check([{'token': 129280, 'seconds': .1}], 1)

    def test_bool_token(self):
        with self.assertRaises(ValueError): self.check([{'token': True, 'seconds': .1}], 1)

    def test_clock_regression(self):
        with self.assertRaises(ValueError): self.check([{'token': 1, 'seconds': 2}, {'token': 2, 'seconds': 1}])

    def test_nonfinite_clock(self):
        with self.assertRaises(ValueError): self.check([{'token': 1, 'seconds': float('inf')}], 1)

    def test_missing_row(self):
        with self.assertRaises(ValueError): self.check([{'token': 1, 'seconds': 1}], 2)


class FenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.group = self.root / 'user.slice/strata-deepseek-window.service'
        self.group.mkdir(parents=True); self.proc = self.root / 'proc-cgroup'
        self.proc.write_text('0::/user.slice/strata-deepseek-window.service\n')
        self.output = self.root / 'output'; self.output.mkdir()
        self.transient = self.root / 'transient'; self.transient.mkdir()
        self.fragment = self.transient / c.UNIT; self.fragment.write_text('owned')
        self.unit = {'InvocationID': 'a' * 32, 'Transient': 'yes',
                     'ControlGroup': '/user.slice/strata-deepseek-window.service',
                     'MemoryMax': 'infinity', 'MemorySwapMax': 'infinity',
                     'FragmentPath': str(self.fragment), 'DropInPaths': '', 'LoadState': 'loaded'}
        for name, value in {'memory.max': 'max', 'memory.swap.max': 'max', 'memory.current': '1024',
                            'memory.events': 'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n'}.items():
            (self.group / name).write_text(value)
        self.commands = []; self.write_readback = True; self.partial_failure = False

    def command(self, argv, **kwargs):
        self.commands.append(argv)
        if 'show' in argv:
            return types.SimpleNamespace(returncode=0, stdout=''.join(k + '=' + self.unit[k] + '\n' for k in c.FENCE_FIELDS))
        self.assertEqual(argv[:5], ['systemctl', '--user', 'set-property', '--runtime', c.UNIT])
        for arg in argv[5:]:
            key, value = arg.split('=', 1); self.unit[key] = value
            if self.write_readback:
                filename = 'memory.max' if key == 'MemoryMax' else 'memory.swap.max'
                (self.group / filename).write_text(c.limit_value(value))
            if self.partial_failure:
                self.partial_failure = False; raise RuntimeError('partial set-property failure')
        return types.SimpleNamespace(returncode=0, stdout='')

    def install(self):
        with patch.object(r, 'memory_available', return_value=r.HOST_MARGIN):
            return c.install_private_fence(self.output, command=self.command, proc=self.proc,
                                          root=self.root, transient_root=self.transient)

    def writes(self): return [x for x in self.commands if 'set-property' in x]

    def test_exact_invocation_property_install_restore(self):
        fence = self.install()
        self.assertEqual(fence['prior_properties'], {'MemoryMax': 'max', 'MemorySwapMax': 'max'})
        self.assertTrue(c.fence_terminal(fence)['passed'])
        value = c.restore_private_fence(fence, children_closed=True, command=self.command)
        self.assertTrue(value['passed']); self.assertEqual(value['restored_properties'], fence['prior_properties'])
        self.assertEqual((self.group / 'memory.max').read_text(), 'max')
        self.assertEqual(len(self.writes()), 2)
        self.assertNotIn('revert', str(self.commands))

    def test_finite_prior_properties_and_zero_swap_restored(self):
        self.unit.update(MemoryMax=str(r.MEMORY_MAX + 1024), MemorySwapMax='0')
        (self.group / 'memory.max').write_text(self.unit['MemoryMax']); (self.group / 'memory.swap.max').write_text('0')
        fence = self.install(); c.restore_private_fence(fence, children_closed=True, command=self.command)
        self.assertEqual((self.group / 'memory.max').read_text(), str(r.MEMORY_MAX + 1024))
        self.assertEqual((self.group / 'memory.swap.max').read_text(), '0')

    def test_infinity_normalized(self):
        self.assertEqual([c.limit_value(x) for x in ('infinity', 'max', str(2**64 - 1))], ['max'] * 3)

    def test_boolean_property_rejected(self):
        with self.assertRaises(ValueError): c.limit_value(True)

    def test_production_cgroup_no_commands(self):
        self.proc.write_text('0::/user.slice/deepseek-hosted.service\n')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.commands, [])

    def test_nontransient_no_mutation(self):
        self.unit['Transient'] = 'no'
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.writes(), [])

    def test_foreign_fragment_no_mutation(self):
        self.unit['FragmentPath'] = '/etc/systemd/user/other.service'
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.writes(), [])

    def test_stricter_prior_limit_never_relaxed(self):
        self.unit['MemoryMax'] = '1024'; (self.group / 'memory.max').write_text('1024')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.writes(), [])

    def test_prior_cgroup_disagreement_no_write(self):
        (self.group / 'memory.swap.max').write_text('1234')
        with self.assertRaises(ValueError): self.install()
        self.assertEqual(self.writes(), [])

    def test_partial_set_failure_restores_prior_properties(self):
        self.partial_failure = True
        with self.assertRaisesRegex(RuntimeError, 'partial set-property'): self.install()
        record = json.loads((self.output / 'private-memory-fence-restored.json').read_text())
        self.assertTrue(record['passed']); self.assertEqual(c.memory_properties(self.unit), {'MemoryMax': 'max', 'MemorySwapMax': 'max'})

    def test_readback_fault_preserves_first_and_restores(self):
        self.write_readback = False
        with self.assertRaisesRegex(ValueError, 'readback'): self.install()
        self.assertTrue(json.loads((self.output / 'private-memory-fence-restored.json').read_text())['passed'])

    def test_margin_missing_restores_prior(self):
        with patch.object(r, 'memory_available', return_value=0):
            with self.assertRaises(ValueError):
                c.install_private_fence(self.output, command=self.command, proc=self.proc,
                                        root=self.root, transient_root=self.transient)
        self.assertTrue(json.loads((self.output / 'private-memory-fence-restored.json').read_text())['passed'])

    def test_live_child_prevents_relaxation(self):
        fence = self.install(); before = len(self.writes())
        with self.assertRaises(ValueError): c.restore_private_fence(fence, children_closed=False, command=self.command)
        self.assertEqual(len(self.writes()), before)
        self.assertFalse(json.loads((self.output / 'private-memory-fence-restored.json').read_text())['passed'])

    def test_foreign_invocation_never_written(self):
        fence = self.install(); before = len(self.writes()); self.unit['InvocationID'] = 'b' * 32
        with self.assertRaises(ValueError): c.restore_private_fence(fence, children_closed=True, command=self.command)
        self.assertEqual(len(self.writes()), before)

    def test_foreign_property_never_overwritten(self):
        fence = self.install(); before = len(self.writes()); self.unit['MemorySwapMax'] = '77'
        with self.assertRaises(ValueError): c.restore_private_fence(fence, children_closed=True, command=self.command)
        self.assertEqual(len(self.writes()), before)

    def test_collection_requires_unit_gone_and_files_absent(self):
        self.install(); self.unit.update(InvocationID='', LoadState='not-found'); self.fragment.unlink()
        out = c.fence_collected(self.output, self.root, command=self.command)
        self.assertTrue(out['unit_collected']); self.assertTrue(out['dropins_absent'])

    def test_surviving_dropin_blocks_collection(self):
        self.install(); self.unit.update(InvocationID='', LoadState='not-found'); self.fragment.unlink()
        Path(str(self.fragment) + '.d').mkdir()
        with self.assertRaises(ValueError): c.fence_collected(self.output, self.root, command=self.command)

    def test_new_invocation_blocks_collection(self):
        self.install(); self.unit['InvocationID'] = 'b' * 32
        with self.assertRaises(ValueError): c.fence_collected(self.output, self.root, command=self.command)

    def test_collection_timeout_no_write(self):
        self.install(); clock = Mock(side_effect=[0, 31])
        with self.assertRaisesRegex(RuntimeError, 'collection'):
            c.fence_collected(self.output, self.root, command=self.command, clock=clock, pause=Mock())
        self.assertFalse((self.root / 'private-memory-fence-collected.json').exists())

    def test_missing_start_receipt_does_not_hide_live_API(self):
        handle = types.SimpleNamespace(poll=lambda: None); command = Mock()
        self.assertFalse(c.private_children_closed(self.output, [handle], command=command))
        command.assert_not_called()

    def test_dead_API_without_ready_requires_GPU_empty(self):
        handle = types.SimpleNamespace(poll=lambda: 1)
        command = Mock(return_value=types.SimpleNamespace(stdout='1234\n'))
        self.assertFalse(c.private_children_closed(self.output, [handle], command=command))

    def test_prelaunch_empty_GPU_allows_original_limit_restore(self):
        command = Mock(return_value=types.SimpleNamespace(stdout=''))
        self.assertTrue(c.private_children_closed(self.output, [], command=command))

    def test_ready_native_still_present_blocks(self):
        (self.output / 'native-ready.json').write_text('{"pid": 91}')
        (self.root / '91').mkdir(); command = Mock()
        self.assertFalse(c.private_children_closed(self.output, [], command=command, proc=self.root))
        command.assert_not_called()

    def test_GPU_query_error_not_empty(self):
        command = Mock(side_effect=RuntimeError('query failed'))
        with self.assertRaises(RuntimeError): c.private_children_closed(self.output, [], command=command)

    def test_fenced_body_error_retains_primary_and_cleanup_note(self):
        with patch.object(c, 'install_private_fence', return_value={}), patch.object(c, 'private_children_closed', return_value=False), \
             patch.object(c, 'restore_private_fence', side_effect=RuntimeError('cleanup failed')):
            error = RuntimeError('body first')
            with self.assertRaisesRegex(RuntimeError, 'body first'):
                with c.fenced_phase(self.output): raise error
        self.assertIn('cleanup failed', str(error.__notes__))

    def test_fenced_cleanup_error_fails_successful_body(self):
        with patch.object(c, 'install_private_fence', return_value={}), patch.object(c, 'private_children_closed', return_value=False), \
             patch.object(c, 'restore_private_fence', side_effect=RuntimeError('unsafe children')):
            with self.assertRaisesRegex(RuntimeError, 'unsafe children'):
                with c.fenced_phase(self.output): pass

    def test_restore_receipt_failure_does_not_mask_primary(self):
        fence=self.install();self.unit['InvocationID']='b'*32
        with patch.object(r,'emit',side_effect=OSError('receipt failed')):
            with self.assertRaisesRegex(ValueError,'Foreign private invocation') as caught:
                c.restore_private_fence(fence,children_closed=True,command=self.command)
        self.assertIn('receipt failed',str(caught.exception.__notes__))

    def test_collection_query_uses_remaining_deadline(self):
        self.install();self.unit.update(InvocationID='',LoadState='not-found');self.fragment.unlink()
        command=Mock(side_effect=self.command)
        c.fence_collected(self.output,self.root,command=command,clock=Mock(side_effect=[0,25,26]))
        self.assertEqual(command.call_args.kwargs['timeout'],5)

    def test_memory_events_oom_blocks(self):
        before = {'cgroup': str(self.group), 'events_before': c.memory_events(self.group)}
        (self.group / 'memory.events').write_text('low 0\nhigh 0\nmax 0\noom 1\noom_kill 0\n')
        with self.assertRaises(ValueError): c.fence_terminal(before)

    def test_event_regression(self):
        with self.assertRaises(ValueError): c.fence_terminal({'cgroup': str(self.group), 'events_before': {'oom': 1, 'oom_kill': 0}})

    def test_path_traversal(self):
        with self.assertRaises(ValueError): c.private_cgroup('0::/x/../strata-deepseek-window.service', self.root)

    def test_memory_counter_malformed(self):
        (self.group / 'memory.events').write_text('oom -1\noom_kill 0\n')
        with self.assertRaises(ValueError): c.memory_events(self.group)


class PlacementTests(unittest.TestCase):
    def log(self, cut=19):
        return ('ds4: CUDA0 layers [0, 42]: weights 3.31 GB, experts 58.32 GB (5746 of 7680 in VRAM), caches 0.58 GB, 2026 MiB free\n'
                'ds4: CUDA1 layers [%d, 39] + head: weights 3.31 GB, experts 58.86 GB (5953 of 8064 in VRAM), caches 0.54 GB, 2030 MiB free' % cut)

    def test_baseline_automatic_observed(self):
        self.assertEqual(c.placement(self.log(), [19, 20])['trunk_split'], [19, 21])

    def test_alternate_frozen_automatic_split(self):
        self.assertEqual(c.placement(self.log(20), [19, 20])['trunk_split'], [20, 20])

    def test_unreviewed_split_rejected(self):
        with self.assertRaises(ValueError): c.placement(self.log(21), [19, 20])

    def test_missing_GPU_rejected(self):
        with self.assertRaises(ValueError): c.placement(self.log().splitlines()[0], [19])

    def test_head_wrong_device(self):
        with self.assertRaises(ValueError): c.placement(self.log().replace(' + head:', ':'), [19])

    def test_unknown_format_rejected(self):
        with self.assertRaises(ValueError): c.placement(self.log().replace('MiB free', 'MB free'), [19])


class RequestTests(unittest.TestCase):
    def perform(self, *, deadline=100, immediate=True, dump='OK', storage='OK', margin=True,
                result_error=None, advance=0):
        clock = types.SimpleNamespace(value=0.)
        objects = []
        class FakeStream:
            def __init__(self, base, body, timeout):
                self.base, self.body, self.timeout = base, body, timeout
                self.cancel = Mock(); self.thread = types.SimpleNamespace(is_alive=lambda: False)
                self.finished = types.SimpleNamespace(wait=self.wait); objects.append(self)
            def start(self): return self
            def wait(self, timeout): clock.value += advance; return immediate
            def result(self, timeout):
                if result_error: raise result_error
                return {'status': 200, 'done': True, 'finish_reason': 'stop', 'content': 'ok'}
        def wait_for(fn, timeout, why):
            if not fn(): raise RuntimeError(why)
        with patch.object(r, 'memory_available', return_value=r.HOST_MARGIN if margin else 0):
            out = c.bounded_request('http://127.0.0.1:18041', {'max_tokens': 32768}, deadline, Path('/unused'), True,
                    stream_class=FakeStream, observe=lambda *a: {'work': {'active': 0, 'queued': 0, 'admission_reserved': 0}},
                    wait_for=wait_for, dump_snapshot=lambda *a: {'status': dump},
                    storage_snapshot=lambda *a: {'status': storage}, clock=lambda: clock.value)
        return out, objects

    def test_no_budget_no_request(self):
        out, objects = self.perform(deadline=9); self.assertTrue(out['budget_not_started']); self.assertFalse(objects)

    def test_complete_without_retry(self):
        out, objects = self.perform(); self.assertTrue(out['done']); self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].timeout, 1200); objects[0].cancel.assert_not_called()

    def test_deadline_owned_cancel(self):
        out, objects = self.perform(deadline=11, immediate=False, advance=12)
        self.assertEqual(out['incomplete_reason'], 'UNCHANGED_SOFT_DEADLINE'); objects[0].cancel.assert_called_once()

    def test_dump_limit_owned_cancel(self):
        out, objects = self.perform(immediate=False, dump='INCOMPLETE_HOLD')
        self.assertEqual(out['incomplete_reason'], 'FINITE_DUMP_LIMIT'); objects[0].cancel.assert_called_once()

    def test_storage_limit_owned_cancel(self):
        out, objects = self.perform(immediate=False, storage='INCOMPLETE_HOLD')
        self.assertEqual(out['incomplete_reason'], 'PRIVATE_STORAGE_LIMIT'); objects[0].cancel.assert_called_once()

    def test_physical_margin_owned_cancel(self):
        out, objects = self.perform(immediate=False, margin=False)
        self.assertEqual(out['incomplete_reason'], 'PHYSICAL_HOST_MARGIN'); objects[0].cancel.assert_called_once()

    def test_terminal_storage_partial_not_passed(self):
        out, objects = self.perform(storage='INCOMPLETE_HOLD')
        self.assertTrue(out['intentional_budget_stop']); self.assertFalse(out['retry']); self.assertEqual(len(objects), 1)

    def test_transport_fault_raw_preserved(self):
        error = RuntimeError('transport')
        with self.assertRaisesRegex(RuntimeError, 'transport'): self.perform(result_error=error)
        self.assertIsInstance(error.raw_transport, dict)


if __name__ == '__main__': unittest.main()
