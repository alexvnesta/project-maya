"""CPU-only compiler planning, custody, resource-admission and first-failure controls.

Every compiler action is mocked. No candidate/native code is imported or run.
"""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import iq2s_build as c

N = '/usr/bin/c++ -O3 -Wl,--dependency-file=CMakeFiles/maya-ds4.dir/link.d CMakeFiles/maya-ds4.dir/src/ds4/ds4_iq.cu.o -o maya-ds4 -lm'
T = '/usr/bin/c++ -O3 -Wl,--dependency-file=CMakeFiles/ds4_gguf_test.dir/link.d CMakeFiles/ds4_gguf_test.dir/tests/ds4_gguf_test.cu.o CMakeFiles/ds4_gguf_test.dir/src/ds4/ds4_iq.cu.o -o ds4_gguf_test -lm'


class Plans(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.b = c.load_exact('selected_build', c.P / 'selected_build.py', c.BUILD_SHA)
        for name, value in [('B', self.root)]:
            p = patch.object(self.b, name, value); p.start(); self.addCleanup(p.stop)
        for target, text in [('maya-ds4', N), ('ds4_gguf_test', T)]:
            f = self.root / 'CMakeFiles' / (target + '.dir')
            f.mkdir(parents=True)
            (f / 'link.txt').write_text(text)
    def test_exact_prepare_and_compile_names(self):
        prep, comp = c.plans(self.b)
        self.assertEqual([n for n, _ in prep], ['selected-relink', 'deps-iq', 'deps-test'])
        self.assertEqual([n for n, _ in comp], ['compile-iq', 'compile-test', 'candidate-link', 'test-link'])
    def test_candidate_is_distinct_from_held_imma(self):
        prep, comp = c.plans(self.b)
        for _, argv in prep + comp:
            self.assertNotIn(str(c.P / 'selected-candidate'), ' '.join(argv))
        self.assertIn(str(c.HERE / 'candidate/src/ds4/ds4_iq.cu'), comp[0][1])
    def test_prepare_never_compiles_cuda(self):
        prep, _ = c.plans(self.b)
        self.assertTrue(all('-M' in argv and '-c' not in argv for _, argv in prep[1:]))
    def test_compilation_keeps_sm80_threads1_and_no_fastmath(self):
        _, comp = c.plans(self.b)
        for _, argv in comp[:2]:
            self.assertIn('--generate-code=arch=compute_80,code=[compute_80,sm_80]', argv)
            self.assertEqual(argv[argv.index('--threads') + 1], '1')
            self.assertNotIn('--use_fast_math', argv)
    def test_only_fresh_owned_outputs(self):
        prep, comp = c.plans(self.b)
        for jobs, parent in [(prep, c.PREP), (comp, c.OUT)]:
            for _, argv in jobs:
                self.assertEqual(Path(argv[argv.index('-o') + 1]).parent, parent)
    def test_foreign_output_refused(self):
        real = self.b.commands
        def bad(*a):
            jobs = real(*a)
            jobs[3][1][-1] = '/foreign/out'
            return jobs
        with patch.object(self.b, 'commands', side_effect=bad), self.assertRaises(ValueError):
            c.plans(self.b)
    def test_fastmath_refused(self):
        real = self.b.commands
        def bad(*a):
            jobs = real(*a); jobs[3][1].append('--use_fast_math'); return jobs
        with patch.object(self.b, 'commands', side_effect=bad), self.assertRaises(ValueError):
            c.plans(self.b)
    def test_parallel_compiler_refused(self):
        real = self.b.commands
        def bad(*a):
            jobs = real(*a)
            argv = jobs[3][1]; argv[argv.index('--threads') + 1] = '2'
            return jobs
        with patch.object(self.b, 'commands', side_effect=bad), self.assertRaises(ValueError):
            c.plans(self.b)


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.binding = {'native_pid': 7}
        self.runtime = SimpleNamespace(PHASE_KEYS=('active_cpu_build', 'active_private_phase',
            'active_GPU_phase', 'active_gpu_experiment', 'private_window',
            'production_restore_in_progress', 'production_verification_pending',
            'production_temporarily_stopped'), current_binding=lambda s: s['binding'])
        self.host = Mock(); self.host.idle.return_value = True
        self.state = {'binding': self.binding, 'active_cpu_build': False}
        p = patch.object(c, 'E', self.root); p.start(); self.addCleanup(p.stop)
        p = patch('shutil.disk_usage', return_value=SimpleNamespace(free=132 * 2**30))
        p.start(); self.addCleanup(p.stop)
    def save(self): (self.root / 'STATE.json').write_text(json.dumps(self.state))
    def run_guard(self, reservation=None):
        self.save()
        return c.guard(self.runtime, self.host, self.binding, reservation)
    def test_fresh_idle_default_owner_accepted(self):
        self.assertEqual(self.run_guard(), self.state); self.host.guard_binding.assert_called_once()
    def test_every_active_phase_refused_before_idle(self):
        for key in self.runtime.PHASE_KEYS:
            self.state = {'binding': self.binding, key: True}
            with self.assertRaises(ValueError): self.run_guard()
        self.host.idle.assert_not_called()
    def test_busy_refused_before_owner_hash(self):
        self.host.idle.return_value = False
        with self.assertRaisesRegex(ValueError, 'BUSY'): self.run_guard()
        self.host.guard_binding.assert_not_called()
    def test_changed_owner_refused_before_idle(self):
        self.state['binding'] = {'native_pid': 8}
        with self.assertRaises(ValueError): self.run_guard()
        self.host.idle.assert_not_called()
    def test_exact_owned_reservation_accepted(self):
        reservation = {'controller_pid': 9}
        self.state['active_cpu_build'] = reservation
        self.run_guard(reservation)
    def test_foreign_reservation_refused(self):
        self.state['active_cpu_build'] = {'controller_pid': 8}
        with self.assertRaises(ValueError): self.run_guard({'controller_pid': 9})
    def test_root132_is_admission_floor(self):
        with patch('shutil.disk_usage', return_value=SimpleNamespace(free=132 * 2**30 - 1)):
            with self.assertRaisesRegex(ValueError, 'Root132'): self.run_guard()
    def test_actual_owner_guard_fault_propagates(self):
        self.host.guard_binding.side_effect = ValueError('owner changed')
        with self.assertRaisesRegex(ValueError, 'owner changed'): self.run_guard()


class Reservation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.state = self.root / 'STATE.json'
        self.state.write_text(json.dumps({'active_cpu_build': False, 'foreign_key': 'keep'}))
        self.binding = {'native_pid': 7}
        self.host = Mock()
        self.b = SimpleNamespace(check_files=Mock())
        self.runtime = SimpleNamespace()
        self.a = SimpleNamespace(emit=lambda p, s: p.write_text(json.dumps(s)))
        def guard(r, h, b, reservation=None):
            state = json.loads(self.state.read_text())
            if reservation is not None and state.get('active_cpu_build') != reservation:
                raise ValueError('reservation changed')
            return state
        for obj, name, value in [(c, 'HERE', self.root), (c, 'EXPECTED', self.root),
                (c, 'E', self.root), (c.sys, 'platform', 'linux'),
                (c, 'support', Mock(return_value=(self.b, self.runtime, self.a, self.host, self.binding))),
                (c, 'guard', Mock(side_effect=guard)), (c, 'verify_q', Mock(return_value={'files': {}})),
                (c, 'fresh', Mock()), (c, 'sha', Mock(return_value='pin'))]:
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
    def read(self): return json.loads(self.state.read_text())
    def test_claim_success_release_preserves_foreign_state(self):
        def run(b, q, admission):
            self.assertEqual(self.read()['active_cpu_build']['mode'], 'iq2s-persistent-prepare-only')
            admission(); return 'ok'
        with patch.object(c, 'prepare', side_effect=run):
            self.assertEqual(c.main('prepare', 'pin'), 'ok')
        self.assertFalse(self.read()['active_cpu_build'])
        self.assertEqual(self.read()['foreign_key'], 'keep')
    def test_first_failure_releases_no_retry(self):
        err = RuntimeError('first failure')
        with patch.object(c, 'prepare', side_effect=err) as run, self.assertRaises(RuntimeError) as got:
            c.main('prepare', 'pin')
        self.assertIs(got.exception, err); self.assertEqual(run.call_count, 1)
        self.assertFalse(self.read()['active_cpu_build'])
    def test_foreign_reservation_replacement_preserved(self):
        foreign = {'controller_pid': 1234}
        def run(b, q, admission):
            self.state.write_text(json.dumps({'active_cpu_build': foreign})); admission()
        with patch.object(c, 'prepare', side_effect=run), self.assertRaises(ValueError):
            c.main('prepare', 'pin')
        self.assertEqual(self.read()['active_cpu_build'], foreign)
    def test_preclaim_guard_failure_untouched(self):
        before = self.state.read_bytes(); c.guard.side_effect = ValueError('busy')
        with patch.object(c, 'prepare') as run, self.assertRaises(ValueError):
            c.main('prepare', 'pin')
        run.assert_not_called(); self.assertEqual(self.state.read_bytes(), before)
    def test_invalid_proof_no_claim(self):
        before = self.state.read_bytes(); c.verify_q.side_effect = ValueError('unqualified')
        with patch.object(c, 'prepare') as run, self.assertRaises(ValueError):
            c.main('prepare', 'pin')
        run.assert_not_called(); self.assertEqual(self.state.read_bytes(), before)
    def test_changed_coordination_no_claim(self):
        def verify(*a):
            self.state.write_text(json.dumps({'foreign': 1})); return {}
        c.verify_q.side_effect = verify
        with patch.object(c, 'prepare') as run, self.assertRaises(ValueError):
            c.main('prepare', 'pin')
        run.assert_not_called(); self.assertEqual(self.read(), {'foreign': 1})
    def test_compile_mode_only_compiles(self):
        with patch.object(c, 'compile_candidate', return_value='ok') as comp, patch.object(c, 'prepare') as prep:
            self.assertEqual(c.main('compile', 'pin'), 'ok')
        comp.assert_called_once(); prep.assert_not_called()
    def test_changed_qualification_aborts_owned_stage(self):
        c.sha.return_value = 'different'
        with patch.object(c, 'prepare', side_effect=lambda b, q, a: a()), self.assertRaises(ValueError):
            c.main('prepare', 'pin')
        self.assertFalse(self.read()['active_cpu_build'])
    def test_release_error_retains_primary_failure(self):
        err = RuntimeError('first')
        real = self.a.emit
        def emit(p, s):
            if s.get('active_cpu_build') is False: raise OSError('release')
            return real(p, s)
        self.a.emit = emit
        with patch.object(c, 'prepare', side_effect=err), self.assertRaises(RuntimeError) as got:
            c.main('prepare', 'pin')
        self.assertIs(got.exception, err); self.assertIn('release', err.__notes__[0])
    def test_success_foreign_replacement_is_hold_and_preserved(self):
        foreign = {'controller_pid': 2468}
        def run(b, q, admission):
            self.state.write_text(json.dumps({'active_cpu_build': foreign}))
            return 'not-qualified'
        with patch.object(c, 'prepare', side_effect=run), self.assertRaisesRegex(ValueError, 'lost'):
            c.main('prepare', 'pin')
        self.assertEqual(self.read()['active_cpu_build'], foreign)
    def test_noop_release_is_hold(self):
        real = self.a.emit
        def emit(p, s):
            if s.get('active_cpu_build') is not False: real(p, s)
        self.a.emit = emit
        with patch.object(c, 'prepare', return_value='done'), self.assertRaisesRegex(ValueError, 'not persisted'):
            c.main('prepare', 'pin')
    def test_partial_claim_publish_failure_releases_actual_owned_slot(self):
        err = OSError('publish failed after write')
        real = self.a.emit
        def emit(p, s):
            real(p, s)
            if s.get('active_cpu_build') is not False: raise err
        self.a.emit = emit
        with patch.object(c, 'prepare') as run, self.assertRaises(OSError) as got:
            c.main('prepare', 'pin')
        self.assertIs(got.exception, err); run.assert_not_called()
        self.assertFalse(self.read()['active_cpu_build'])


class Compile(unittest.TestCase):
    def execute(self, mode):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); prep = root / 'prepare'; prep.mkdir()
            out = root / 'out'
            control = prep / 'selected-relink'; control.write_bytes(b'control')
            evidence = {'passed': True, 'status': 'PREPARED_STOP_FOR_ACTUAL_INPUT_REVIEW',
                'original_relink_sha256': c.BASE, 'input_sha256': {'/old/input': 'pin'}, 'tools': []}
            receipt = prep / 'receipt.json'; receipt.write_text(json.dumps(evidence))
            q = {'files': {str(receipt): c.BASE, '/old/input': 'pin'},
                 'actual_inputs_manually_reviewed': True}
            jobs = [(name, ['/usr/bin/c++', '-o', str(out / target)]) for name, target in
                [('compile-iq', 'ds4_iq.cu.o'), ('compile-test', 'ds4_gguf_test.cu.o'),
                 ('candidate-link', 'maya-ds4-candidate'), ('test-link', 'ds4_gguf_test-candidate')]]
            b = SimpleNamespace(B=root, check_files=Mock(), check_tools=Mock(),
                                dependencies=lambda text, relative_to: text.split())
            calls = []
            def run(argv, name, folder, admission):
                calls.append(name); admission()
                if mode == 'child_failure': raise RuntimeError('first compiler fault')
                artifact = Path(argv[-1]); artifact.write_bytes(b'object')
                if name.endswith('-link'):
                    deps = '/old/input ' + str(out / 'ds4_iq.cu.o')
                    if mode == 'unknown_link': deps += ' /unknown/lib'
                    Path(str(artifact) + '.link.d').write_text(deps)
                return {'returncode': 0}
            b.run_child = run
            if mode == 'missing_review': q['actual_inputs_manually_reviewed'] = False
            if mode == 'missing_pin': del q['files']['/old/input']
            if mode == 'bad_control': evidence['original_relink_sha256'] = 'bad'; receipt.write_text(json.dumps(evidence))
            if mode == 'existing': out.mkdir()
            with patch.object(c, 'PREP', prep), patch.object(c, 'OUT', out), patch.object(c, 'sha', return_value=c.BASE), patch.object(c, 'plans', return_value=([], jobs)):
                if mode == 'ok':
                    result = c.compile_candidate(b, q, Mock())
                    self.assertTrue(result['passed']); self.assertFalse(result['GPU_execution'])
                    self.assertFalse(result['production_changed']); self.assertEqual(len(calls), 4)
                else:
                    with self.assertRaises((ValueError, RuntimeError)): c.compile_candidate(b, q, Mock())
                    self.assertFalse((out / 'receipt.json').exists())
                    self.assertEqual(len(calls), {'child_failure': 1, 'unknown_link': 3,
                        'missing_review': 0, 'missing_pin': 0, 'bad_control': 0, 'existing': 0}[mode])
    def test_first_compile_four_children_only(self): self.execute('ok')
    def test_first_child_failure_no_retry(self): self.execute('child_failure')
    def test_unreviewed_actual_link_input_no_next_child(self): self.execute('unknown_link')
    def test_actual_header_review_required(self): self.execute('missing_review')
    def test_all_actual_header_pins_required(self): self.execute('missing_pin')
    def test_exact_control_relink_required(self): self.execute('bad_control')
    def test_existing_build_refused_no_adoption(self): self.execute('existing')


class Qualification(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.here = self.root / 'iq'; self.here.mkdir()
        model = self.root / 'model-v1'; model.mkdir()
        prior = model / 'numerical-qualification.json'
        prior.write_text(json.dumps({'files': {'/inherited/module.py': 'pin'}}))
        manifest = self.here / 'candidate-files.json'
        manifest.write_text(json.dumps({'files': ['source.cu']}))
        candidate = self.here / 'candidate'; candidate.mkdir()
        (candidate / 'source.cu').write_text('source')
        self.q = {'mode': 'prepare', 'manual_source_reviewed': True, 'CPU_both_hosts_passed': True,
            'source_sha256': {'iq2s_build.py': 'pin', 'test_iq2s_build.py': 'pin',
                              'candidate/source.cu': 'pin'},
            'test_ids': ['case'], 'policy_test_ids': ['policy.case'],
            'files': {str(prior): '6eb179b8b7edb7a87133c4e24bd99dc2f35863cfe6ef56f8385590bf50c6315b',
                      '/inherited/module.py': 'pin', str(manifest): 'pin'}}
        self.q['files'].update({str(self.here / n): v for n, v in self.q['source_sha256'].items()})
        self.receipt = {'passed': True, 'controls': 1, 'test_ids': ['case'],
            'source_sha256': self.q['source_sha256'], 'GPU_execution': False, 'compiler_execution': False}
        self.children = {}
        for label in ('darwin', 'linux'):
            f = self.here / ('build-CPU-FIRST-' + label); f.mkdir()
            policy = self.here / ('policy-CPU-FIRST-' + label); policy.mkdir()
            for name in ('receipt.json', 'compile.json', 'run.json', 'compile.stdout',
                         'compile.stderr', 'run.stdout', 'run.stderr'):
                self.q['files'][str(policy / name)] = 'pin'
                (policy / name).write_text('raw')
            for name in ('receipt.json', 'child.json', 'child.log'):
                self.q['files'][str(f / name)] = 'pin'
            (f / 'child.log').write_text('raw')
            self.children[label] = {'returncode': 0, 'CPU_s': 30, 'wall_s': 90, 'nice': 15,
                'CUDA_hidden': True, 'Linux_AS_MiB': 512 if label == 'linux' else None,
                'error': None, 'cleanup_errors': []}
        prior_pin = self.q['files'][str(prior)]
        digest = lambda path: prior_pin if Path(path) == prior else 'pin'
        for obj, name, value in [(c, 'HERE', self.here), (c, 'P', self.root), (c, 'sha', Mock(side_effect=digest))]:
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
    def execute(self, stage='prepare'):
        qp = self.here / (stage + '-qualification.json'); qp.write_text(json.dumps(self.q))
        for label in ('darwin', 'linux'):
            f = self.here / ('build-CPU-FIRST-' + label)
            (f / 'receipt.json').write_text(json.dumps(self.receipt))
            (f / 'child.json').write_text(json.dumps(self.children[label]))
            proof = {'passed': True, 'controls': 1, 'test_ids': ['policy.case'],
                     'source_sha256': self.q['source_sha256'], 'GPU_execution': False,
                     'CUDA_compilation': False, 'children': [self.children[label]] * 2}
            (self.here / ('policy-CPU-FIRST-' + label) / 'receipt.json').write_text(json.dumps(proof))
        return c.verify_q(qp, 'pin')
    def test_exact_qualification_accepted(self): self.assertEqual(self.execute(), self.q)
    def test_missing_manual_review_refused(self):
        self.q['manual_source_reviewed'] = False
        with self.assertRaises(ValueError): self.execute()
    def test_missing_both_hosts_refused(self):
        self.q['CPU_both_hosts_passed'] = False
        with self.assertRaises(ValueError): self.execute()
    def test_wrong_stage_refused(self):
        self.q['mode'] = 'compile'
        with self.assertRaises(ValueError): self.execute()
    def test_inherited_import_closure_required(self):
        del self.q['files']['/inherited/module.py']
        with self.assertRaises(ValueError): self.execute()
    def test_candidate_source_cpu_pin_required(self):
        del self.q['source_sha256']['candidate/source.cu']
        with self.assertRaises(ValueError): self.execute()
    def test_candidate_manifest_pinned(self):
        del self.q['files'][str(self.here / 'candidate-files.json')]
        with self.assertRaises(ValueError): self.execute()
    def test_unreviewed_lexical_parent_input_refused(self):
        self.q['files']['/compiler/../unreviewed'] = 'pin'
        with self.assertRaises(ValueError): self.execute()
    def test_actual_reviewed_compiler_parent_alias_accepted(self):
        prep = self.root / 'prepare-FIRST'; prep.mkdir()
        receipt = prep / 'receipt.json'
        receipt.write_text(json.dumps({'input_sha256': {'/compiler/../checked': 'pin'}}))
        self.q['mode'] = 'compile'; self.q['actual_inputs_manually_reviewed'] = True
        self.q['files'].update({str(receipt): 'pin', '/compiler/../checked': 'pin'})
        with patch.object(c, 'PREP', prep):
            self.assertEqual(self.execute('compile'), self.q)
    def test_changed_cpu_ids_refused(self):
        self.receipt['test_ids'] = ['different']
        with self.assertRaises(ValueError): self.execute()
    def test_boolean_test_count_refused(self):
        self.receipt['controls'] = True
        with self.assertRaises(ValueError): self.execute()
    def test_missing_raw_cpu_log_refused(self):
        del self.q['files'][str(self.here / 'build-CPU-FIRST-linux/child.log')]
        with self.assertRaises(ValueError): self.execute()
    def test_linux_address_space_bound_required(self):
        self.children['linux']['Linux_AS_MiB'] = 513
        with self.assertRaises(ValueError): self.execute()
    def test_failed_cpu_child_refused(self):
        self.children['linux']['returncode'] = 1
        with self.assertRaises(ValueError): self.execute()
    def test_cpu_supervision_error_blocks_qualification(self):
        self.children['linux']['error'] = 'busy during child'
        with self.assertRaises(ValueError): self.execute()
    def test_unrun_cpu_receipt_refused(self):
        self.receipt['passed'] = False
        with self.assertRaises(ValueError): self.execute()
    def test_duplicate_case_ids_refused(self):
        self.q['test_ids'] = ['case', 'case']
        with self.assertRaises(ValueError): self.execute()


class ChildCleanup(unittest.TestCase):
    def test_term_reaps_only_owned_session_and_verifies_group_gone(self):
        import qualify_iq2s_build_cpu as driver
        process = Mock(pid=12345)
        def signal(pid, sig):
            self.assertEqual(pid, 12345)
            if sig == 0: raise ProcessLookupError()
        with patch.object(driver.os, 'killpg', side_effect=signal) as kill:
            self.assertEqual(driver.cleanup_child(process), [])
        self.assertEqual(kill.call_count, 2)
        process.wait.assert_called_once_with(timeout=3)
    def test_remaining_descendants_receive_kill(self):
        import qualify_iq2s_build_cpu as driver
        process = Mock(pid=12345)
        events = []
        def signal(pid, sig):
            events.append((pid, sig))
            if sig == 0 and any(s == driver.signal.SIGKILL for _, s in events):
                raise ProcessLookupError()
        with patch.object(driver.os, 'killpg', side_effect=signal), patch.object(driver.time, 'monotonic', side_effect=[0, 4, 5]):
            self.assertEqual(driver.cleanup_child(process), [])
        self.assertIn((12345, driver.signal.SIGKILL), events)


class Files(unittest.TestCase):
    def test_existing_attempt_refused(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError): c.fresh(Path(t).resolve())
    def test_output_symlink_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t).resolve() / 'alias'; p.symlink_to('/missing')
            with self.assertRaises(ValueError): c.fresh(p)
    def test_real_parent_required(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t).resolve() / 'alias'; p.symlink_to(t)
            with self.assertRaises(ValueError): c.fresh(p / 'new')
    def test_receipt_never_overwrites(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t).resolve() / 'receipt.json'; c.emit_new(p, {'a': 1})
            with self.assertRaises(FileExistsError): c.emit_new(p, {'a': 2})
    def test_import_hash_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t).resolve() / 'x.py'; p.write_text('raise RuntimeError("never")')
            with self.assertRaises(ValueError): c.load_exact('x', p, 'wrong')


if __name__ == '__main__':
    unittest.main()

