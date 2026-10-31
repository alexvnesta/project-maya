"""CPU-only Q8-specific compiler planning and custody fault injection."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import build as q

N = '/usr/bin/c++ -O3 -Wl,--dependency-file=CMakeFiles/maya-ds4.dir/link.d CMakeFiles/maya-ds4.dir/src/ds4/ds4_iq.cu.o CMakeFiles/maya-ds4.dir/src/ds4/ds4_gguf.cu.o CMakeFiles/maya-ds4.dir/src/ds4/ds4_model.cu.o -o maya-ds4 -lm'
T = '/usr/bin/c++ -O3 -Wl,--dependency-file=CMakeFiles/ds4_gguf_test.dir/link.d CMakeFiles/ds4_gguf_test.dir/tests/ds4_gguf_test.cu.o CMakeFiles/ds4_gguf_test.dir/src/ds4/ds4_iq.cu.o CMakeFiles/ds4_gguf_test.dir/src/ds4/ds4_gguf.cu.o -o ds4_gguf_test -lm'


class Plan(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        # Load only the pinned qualified pure planner, without support()/host work.
        import sys
        sys.path.insert(0, str(q.P))
        import selected_build as b
        self.b = b
        p = patch.object(b, 'B', self.root); p.start(); self.addCleanup(p.stop)
        for target, value in [('maya-ds4', N), ('ds4_gguf_test', T)]:
            folder = self.root / 'CMakeFiles' / (target + '.dir')
            folder.mkdir(parents=True); (folder / 'link.txt').write_text(value)

    def test_native_replaces_only_original_gguf_object(self):
        _, comp = q.plans(self.b); args = comp[2][1]
        self.assertIn(str(q.OUT / 'ds4_gguf.cu.o'), args)
        self.assertIn('CMakeFiles/maya-ds4.dir/src/ds4/ds4_iq.cu.o', args)
        self.assertIn('CMakeFiles/maya-ds4.dir/src/ds4/ds4_model.cu.o', args)
        self.assertNotIn('CMakeFiles/maya-ds4.dir/src/ds4/ds4_gguf.cu.o', args)
    def test_control_relink_uses_all_original_objects(self):
        prep, _ = q.plans(self.b)
        self.assertEqual([a for a in prep[0][1] if a.endswith('.o')],
                         [a for a in N.split() if a.endswith('.o')])
    def test_prepare_has_only_link_and_dependency_queries(self):
        prep, _ = q.plans(self.b)
        self.assertEqual([n for n, _ in prep], ['selected-relink', 'deps-gguf', 'deps-test'])
        for _, args in prep[1:]:
            self.assertIn('-M', args); self.assertNotIn('-c', args)
    def test_new_fixture_uses_candidate_gguf_and_selected_iq(self):
        _, comp = q.plans(self.b); args = comp[-1][1]
        self.assertIn(str(q.OUT / 'q8_share_check.cu.o'), args)
        self.assertIn(str(q.OUT / 'ds4_gguf.cu.o'), args)
        self.assertIn('CMakeFiles/maya-ds4.dir/src/ds4/ds4_iq.cu.o', args)
    def test_compile_flags_preserve_arithmetic_architecture_threads(self):
        _, comp = q.plans(self.b)
        for _, args in comp[:2]:
            self.assertIn('-O3', args); self.assertIn('-std=c++20', args)
            self.assertIn('--generate-code=arch=compute_80,code=[compute_80,sm_80]', args)
            self.assertEqual(args[args.index('--threads') + 1], '1')
            self.assertNotIn('--use_fast_math', args)
    def test_compile_local_candidate_headers_before_source(self):
        _, comp = q.plans(self.b); args = comp[0][1]
        self.assertLess(args.index('-I' + str(q.HERE / 'candidate/src/ds4')), args.index('-c'))
        self.assertLess(args.index('-I' + str(q.HERE / 'candidate/src/ds4')),
                        args.index('-I' + str(self.b.S / 'src/ds4')))
        self.assertEqual(args[-3], str(q.HERE / 'candidate/src/ds4/ds4_gguf.cu'))
    def test_all_outputs_in_fresh_stage(self):
        prep, comp = q.plans(self.b)
        for jobs, directory in [(prep, q.PREP), (comp, q.OUT)]:
            for _, args in jobs:
                self.assertEqual(Path(args[args.index('-o') + 1]).parent, directory)
    def test_missing_native_gguf_object_rejected(self):
        p = self.root / 'CMakeFiles/maya-ds4.dir/link.txt'
        p.write_text(N.replace(' CMakeFiles/maya-ds4.dir/src/ds4/ds4_gguf.cu.o', ''))
        with self.assertRaises(ValueError): q.plans(self.b)
    def test_missing_fixture_object_rejected(self):
        p = self.root / 'CMakeFiles/ds4_gguf_test.dir/link.txt'
        p.write_text(T.replace(' CMakeFiles/ds4_gguf_test.dir/tests/ds4_gguf_test.cu.o', ''))
        with self.assertRaises(ValueError): q.plans(self.b)
    def test_foreign_linker_output_rejected(self):
        real = self.b.link_plan
        def bad(*a, **kw):
            args = real(*a, **kw); args[args.index('-o') + 1] = '/foreign/output'; return args
        with patch.object(self.b, 'link_plan', side_effect=bad), self.assertRaises(ValueError):
            q.plans(self.b)
    def test_fastmath_inherited_command_rejected(self):
        real = self.b.commands
        def bad(*a, **kw):
            jobs = real(*a, **kw); jobs[3][1].insert(1, '--use_fast_math'); return jobs
        with patch.object(self.b, 'commands', side_effect=bad), self.assertRaises(ValueError): q.plans(self.b)
    def test_parallel_compiler_rejected(self):
        real = self.b.commands
        def bad(*a, **kw):
            jobs = real(*a, **kw); args = jobs[3][1]; args[args.index('--threads') + 1] = '2'; return jobs
        with patch.object(self.b, 'commands', side_effect=bad), self.assertRaises(ValueError): q.plans(self.b)


class Stage(unittest.TestCase):
    def test_bad_mode_refused_before_support(self):
        with patch.object(q, 'support') as s, self.assertRaises(ValueError): q.main('gpu', 'pin')
        s.assert_not_called()
    def test_nonlinux_refused_before_support(self):
        with patch.object(q.sys, 'platform', 'darwin'), patch.object(q, 'support') as s, self.assertRaises(ValueError):
            q.main('prepare', 'pin')
        s.assert_not_called()
    def test_original92_is_fixed_control(self):
        self.assertEqual(q.BASE, '92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1')
class Custody(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.state = self.root / 'STATE.json'
        self.state.write_text(json.dumps({'active_cpu_build': False, 'keep': 1}))
        self.binding = {'native_pid': 7}; self.host = Mock()
        c = SimpleNamespace(fresh=Mock())
        def guard(r, h, b, reservation=None):
            value = json.loads(self.state.read_text())
            if reservation is not None and value.get('active_cpu_build') != reservation:
                raise ValueError('foreign reservation')
            return value
        c.guard = Mock(side_effect=guard)
        def cas(path, before, value):
            if path.read_bytes() != before: raise ValueError('changed state')
            path.write_text(json.dumps(value))
        self.c = c; self.m = SimpleNamespace(__file__=str(q.P / 'prose-speed-v1/prose_measure.py'), cas_state=Mock(side_effect=cas))
        self.sha = '8d10d003bbbd7ffbb87251bacdf53d91af9f074151d34f06c957fa179f3108cf'
        for obj, name, value in [(q, 'HERE', self.root), (q, 'EXPECTED', self.root), (q, 'E', self.root),
                (q.sys, 'platform', 'linux'), (q, 'support', Mock(return_value=(c, Mock(), Mock(), Mock(), self.host, self.binding))),
                (q, 'verify_q', Mock(return_value={})), (q, 'sha', Mock(return_value=self.sha)),
                (q.importlib, 'import_module', Mock(return_value=self.m))]:
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
    def test_success_releases_preserving_other_keys(self):
        with patch.object(q, 'prepare', return_value='ok') as run:
            self.assertEqual(q.main('prepare', self.sha), 'ok'); self.assertEqual(run.call_count, 1)
        value = json.loads(self.state.read_text()); self.assertFalse(value['active_cpu_build']); self.assertEqual(value['keep'], 1)
    def test_stage_failure_is_not_retried_and_releases(self):
        err = RuntimeError('first compiler fault')
        with patch.object(q, 'prepare', side_effect=err) as run, self.assertRaises(RuntimeError) as got:
            q.main('prepare', self.sha)
        self.assertIs(got.exception, err); self.assertEqual(run.call_count, 1)
        self.assertFalse(json.loads(self.state.read_text())['active_cpu_build'])
    def test_compile_only_runs_compile_stage(self):
        with patch.object(q, 'prepare') as prep, patch.object(q, 'compile_candidate', return_value='ok') as comp:
            self.assertEqual(q.main('compile', self.sha), 'ok')
        comp.assert_called_once(); prep.assert_not_called()
    def test_preclaim_busy_does_not_write(self):
        before = self.state.read_bytes(); self.c.guard.side_effect = ValueError('busy')
        with patch.object(q, 'prepare') as run, self.assertRaises(ValueError): q.main('prepare', self.sha)
        run.assert_not_called(); self.assertEqual(self.state.read_bytes(), before)
    def test_invalid_qualification_does_not_claim(self):
        before = self.state.read_bytes(); q.verify_q.side_effect = ValueError('proof')
        with self.assertRaises(ValueError): q.main('prepare', self.sha)
        self.assertEqual(self.state.read_bytes(), before)
    def test_foreign_replacement_preserved(self):
        foreign = {'controller_pid': 1}
        def stage(*a): self.state.write_text(json.dumps({'active_cpu_build': foreign}))
        with patch.object(q, 'prepare', side_effect=stage), self.assertRaises(ValueError): q.main('prepare', self.sha)
        self.assertEqual(json.loads(self.state.read_text())['active_cpu_build'], foreign)
    def test_claim_writes_then_raises_is_released(self):
        real = self.m.cas_state.side_effect
        def partial(path, before, value):
            real(path, before, value)
            if value.get('active_cpu_build'): raise OSError('after publish')
        self.m.cas_state.side_effect = partial
        with patch.object(q, 'prepare') as run, self.assertRaises(OSError): q.main('prepare', self.sha)
        run.assert_not_called(); self.assertFalse(json.loads(self.state.read_text())['active_cpu_build'])
    def test_cleanup_error_does_not_hide_primary(self):
        real = self.m.cas_state.side_effect; err = RuntimeError('primary')
        def fail_release(path, before, value):
            if value.get('active_cpu_build') is False: raise OSError('release')
            real(path, before, value)
        self.m.cas_state.side_effect = fail_release
        with patch.object(q, 'prepare', side_effect=err), self.assertRaises(RuntimeError) as got: q.main('prepare', self.sha)
        self.assertIs(got.exception, err); self.assertIn('release', str(err.__notes__))
        self.host.guard_binding.assert_called_once()
    def test_owner_failure_after_release_is_not_success(self):
        self.host.guard_binding.side_effect = RuntimeError('owner')
        with patch.object(q, 'prepare', return_value='ok'), self.assertRaisesRegex(RuntimeError, 'owner'):
            q.main('prepare', self.sha)
        self.assertFalse(json.loads(self.state.read_text())['active_cpu_build'])
    def test_foreign_CAS_module_rejected_before_claim(self):
        import sys
        before = self.state.read_bytes()
        with patch.dict(sys.modules, {'prose_measure': SimpleNamespace(__file__='/foreign/file')}), self.assertRaises(ValueError):
            q.main('prepare', self.sha)
        self.assertEqual(self.state.read_bytes(), before)


class Qualification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.parent = self.root / 'parent'; self.parent.mkdir()
        for obj, name, value in [(q, 'HERE', self.root), (q, 'P', self.parent)]:
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
        support = self.parent / 'iq2s-persistent-v1/iq2s_build.py'
        support.parent.mkdir(); support.write_text('frozen support')
        p = patch.object(q, 'SUPPORT_SHA', q.sha(support)); p.start(); self.addCleanup(p.stop)
        for name in ('build.py', 'test_build.py', 'test_driver.py', 'qualify_cpu.py'):
            (self.root / name).write_text(name)
        sources = {n: q.sha(self.root / n) for n in ('build.py', 'test_build.py', 'test_driver.py', 'qualify_cpu.py')}
        candidate = {}
        for i in range(5):
            n = 'candidate/file' + str(i); p = self.root / n; p.parent.mkdir(exist_ok=True)
            p.write_text(n); candidate[n] = q.sha(p)
        sources.update(candidate)
        manifest = self.root / 'candidate-files.json'
        policy_ids = ['policy-' + str(i) for i in range(46)]
        manifest.write_text(json.dumps({'files': candidate, 'policy_test_ids': policy_ids}))
        cas = self.parent / 'prose-speed-v1/prose_measure.py'; cas.parent.mkdir(); cas.write_text('CAS')
        oldq = self.parent / 'model-v1/numerical-qualification.json'; oldq.parent.mkdir()
        helper = self.parent / 'old_helper.py'; helper.write_text('helper')
        oldq.write_text(json.dumps({'files': {str(helper): q.sha(helper)}}))
        for name, value in [('CAS_SHA', q.sha(cas)), ('IMPORT_Q_SHA', q.sha(oldq))]:
            p = patch.object(q, name, value); p.start(); self.addCleanup(p.stop)
        self.value = {'mode': 'prepare', 'manual_source_reviewed': True, 'CPU_both_hosts_passed': True,
                      'source_sha256': sources, 'source_input_sha256': {'frozen': 'input'},
                      'test_ids': ['one', 'two'], 'policy_test_ids': policy_ids,
                      'files': {str(p): q.sha(p) for p in (support, manifest, cas, oldq, helper)}}
        for n, pin in sources.items(): self.value['files'][str(self.root / n)] = pin
        for label in ('darwin', 'linux'):
            folder = self.root / ('build-CPU-FIRST-' + label); folder.mkdir()
            child = {'returncode': 0, 'CPU_s': 30, 'wall_s': 90, 'nice': 15,
                     'CUDA_hidden': True, 'Linux_AS_MiB': 512 if label == 'linux' else None,
                     'error': None, 'cleanup_errors': []}
            receipt = {'passed': True, 'controls': 2, 'test_ids': ['one', 'two'],
                       'source_sha256': sources, 'source_input_sha256': {'frozen': 'input'},
                       'GPU_execution': False, 'native_execution': False, 'compiler_execution': False}
            self.write_cpu(label, 'child.json', child)
            self.write_cpu(label, 'receipt.json', receipt)
            (folder / 'child.log').write_text('raw proof')
            self.value['files'][str(folder / 'child.log')] = q.sha(folder / 'child.log')
            policy = self.root / ('policy-CPU-FIRST-' + label); policy.mkdir()
            for n, value in [('compile.json', child), ('run.json', child), ('receipt.json', {
                    'passed': True, 'controls': 46, 'test_ids': policy_ids, 'source_sha256': sources,
                    'GPU_execution': False, 'CUDA_compilation': False, 'children': [child, child]})]:
                p = policy / n; p.write_text(json.dumps(value)); self.value['files'][str(p)] = q.sha(p)
            for n in ('compile.stdout', 'compile.stderr', 'run.stdout', 'run.stderr'):
                p = policy / n; p.write_text('raw'); self.value['files'][str(p)] = q.sha(p)
    def write_cpu(self, label, name, value):
        p = self.root / ('build-CPU-FIRST-' + label) / name
        p.write_text(json.dumps(value)); self.value['files'][str(p)] = q.sha(p)
    def verify(self):
        p = self.root / 'prepare-qualification.json'; p.write_text(json.dumps(self.value))
        return q.verify_q(None, 'prepare', q.sha(p))
    def change_child(self, key, value):
        p = self.root / 'build-CPU-FIRST-linux/child.json'
        child = json.loads(p.read_text()); child[key] = value; self.write_cpu('linux', 'child.json', child)
    def change_receipt(self, key, value):
        p = self.root / 'build-CPU-FIRST-linux/receipt.json'
        r = json.loads(p.read_text()); r[key] = value; self.write_cpu('linux', 'receipt.json', r)
    def test_complete_exact_proof_accepted(self): self.assertEqual(self.verify(), self.value)
    def test_manual_review_missing_rejected(self):
        self.value['manual_source_reviewed'] = False
        with self.assertRaises(ValueError): self.verify()
    def test_changed_new_source_rejected(self):
        (self.root / 'build.py').write_text('changed')
        with self.assertRaises(ValueError): self.verify()
    def test_unpinned_source_rejected(self):
        self.value['files'].pop(str(self.root / 'test_build.py'))
        with self.assertRaises(ValueError): self.verify()
    def test_control_ids_differ_rejected(self):
        self.change_receipt('test_ids', ['two', 'one'])
        with self.assertRaises(ValueError): self.verify()
    def test_cpu_source_map_differs_rejected(self):
        self.change_receipt('source_sha256', {})
        with self.assertRaises(ValueError): self.verify()
    def test_cpu_input_map_differs_rejected(self):
        self.change_receipt('source_input_sha256', {})
        with self.assertRaises(ValueError): self.verify()
    def test_boolean_control_count_rejected(self):
        self.change_receipt('controls', True)
        with self.assertRaises(ValueError): self.verify()
    def test_nonzero_child_exit_rejected(self):
        self.change_child('returncode', 1)
        with self.assertRaises(ValueError): self.verify()
    def test_child_supervision_error_rejected(self):
        self.change_child('error', 'timeout')
        with self.assertRaises(ValueError): self.verify()
    def test_changed_CPU_limits_rejected(self):
        self.change_child('CPU_s', 31)
        with self.assertRaises(ValueError): self.verify()
    def test_missing_cuda_hide_rejected(self):
        self.change_child('CUDA_hidden', False)
        with self.assertRaises(ValueError): self.verify()
    def test_cpu_cleanup_error_rejected(self):
        self.change_child('cleanup_errors', ['group alive'])
        with self.assertRaises(ValueError): self.verify()
    def test_raw_cpu_proof_unpinned_rejected(self):
        self.value['files'].pop(str(self.root / 'build-CPU-FIRST-darwin/child.log'))
        with self.assertRaises(ValueError): self.verify()
    def test_candidate_source_unpinned_rejected(self):
        self.value['source_sha256'].pop('candidate/file2')
        with self.assertRaises(ValueError): self.verify()
    def test_driver_source_unpinned_rejected(self):
        self.value['source_sha256'].pop('qualify_cpu.py')
        with self.assertRaises(ValueError): self.verify()
    def test_candidate_manifest_unpinned_rejected(self):
        self.value['files'].pop(str(self.root / 'candidate-files.json'))
        with self.assertRaises(ValueError): self.verify()
    def test_policy_proof_unpinned_rejected(self):
        self.value['files'].pop(str(self.root / 'policy-CPU-FIRST-linux/run.json'))
        with self.assertRaises(ValueError): self.verify()
    def test_inherited_helper_missing_rejected(self):
        self.value['files'].pop(str(self.parent / 'old_helper.py'))
        with self.assertRaises(ValueError): self.verify()
    def test_CAS_helper_missing_rejected(self):
        self.value['files'].pop(str(self.parent / 'prose-speed-v1/prose_measure.py'))
        with self.assertRaises(ValueError): self.verify()


class Loops(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.parent = self.root / 'parent'; self.parent.mkdir()
        self.prep = self.root / 'prepare'; self.out = self.root / 'out'; self.original = self.root / 'original'
        self.original.mkdir(); (self.original / 'maya-ds4').write_bytes(b'original')
        for name, value in [('P', self.parent), ('PREP', self.prep), ('OUT', self.out)]:
            p = patch.object(q, name, value); p.start(); self.addCleanup(p.stop)
        prior = self.parent / 'prepare-r2/prepare-inputs.json'; prior.parent.mkdir()
        prior.write_text(json.dumps({'input_sha256': {'/frozen': 'pin'}, 'tools': []}))
        self.proof = {'files': {str(prior): q.sha(prior), 'q-input': 'pin'}}
        self.c = SimpleNamespace(fresh=lambda p: None, emit_new=lambda p, v: p.write_text(json.dumps(v)))
        self.b = Mock(); self.b.B = self.original
        self.b.dependencies.return_value = ['/frozen']
        self.calls = []; self.tampered = False
        def checks(values):
            if self.tampered and values is self.proof['files']: raise ValueError('qualification changed')
            for n, pin in values.items():
                p = Path(n)
                if p.is_relative_to(self.out) and p.exists() and q.sha(p) != pin:
                    raise ValueError('produced input changed')
        self.b.check_files.side_effect = checks
        prep = [('selected-relink', ['/usr/bin/c++', '-o', str(self.prep / 'selected-relink')]),
                ('deps-gguf', ['/usr/local/cuda/bin/nvcc', '-M', '-o', str(self.prep / 'gguf.headers.d')]),
                ('deps-test', ['/usr/local/cuda/bin/nvcc', '-M', '-o', str(self.prep / 'test.headers.d')])]
        comp = [(name, ['/usr/bin/c++', '-o', str(self.out / leaf)]) for name, leaf in (
            ('compile-gguf', 'gguf.o'), ('compile-test', 'test.o'), ('candidate-link', 'native'), ('test-link', 'fixture'))]
        p = patch.object(q, 'plans', return_value=(prep, comp)); p.start(); self.addCleanup(p.stop)
        real = q.sha
        def digest(path):
            p = Path(path)
            if p in (self.original / 'maya-ds4', self.prep / 'selected-relink'): return q.BASE
            if str(path) == '/frozen': return 'pin'
            if str(path) == '/unknown': return 'unknown-pin'
            return real(p)
        p = patch.object(q, 'sha', side_effect=digest); p.start(); self.addCleanup(p.stop)
        def run(args, name, out, admission):
            self.calls.append(name); admission(); target = Path(args[args.index('-o') + 1]); target.write_text(name)
            if name == 'selected-relink': (out / 'selected-relink.link.d').write_text('deps')
            if name.endswith('-link'): Path(str(target) + '.link.d').write_text('deps')
            return {'returncode': 0, 'pid': 100 + len(self.calls)}
        self.b.run_child.side_effect = run; self.run = run; self.admission = Mock()
    def ready_compile(self):
        self.prep.mkdir(); (self.prep / 'selected-relink').write_bytes(b'original')
        receipt = {'passed': True, 'status': 'PREPARED_STOP_FOR_ACTUAL_INPUT_REVIEW',
                   'original_relink_sha256': q.BASE, 'input_sha256': {'/frozen': 'pin'}, 'tools': []}
        (self.prep / 'receipt.json').write_text(json.dumps(receipt)); self.proof['files']['/frozen'] = 'pin'
    def test_prepare_three_children_stops_before_compile(self):
        result = q.prepare(self.c, self.b, self.proof, self.admission)
        self.assertTrue(result['passed']); self.assertEqual(self.calls, ['selected-relink', 'deps-gguf', 'deps-test'])
        self.assertFalse(self.out.exists())
    def test_prepare_first_fault_stops_without_retry(self):
        self.b.run_child.side_effect = RuntimeError('first')
        with self.assertRaises(RuntimeError): q.prepare(self.c, self.b, self.proof, self.admission)
        self.assertEqual(self.b.run_child.call_count, 1); self.assertFalse((self.prep / 'receipt.json').exists())
    def test_last_prepare_child_source_tamper_blocks_PASS(self):
        def run(*a):
            r = self.run(*a)
            if a[1] == 'deps-test': self.tampered = True
            return r
        self.b.run_child.side_effect = run
        with self.assertRaisesRegex(ValueError, 'qualification'): q.prepare(self.c, self.b, self.proof, self.admission)
        self.assertFalse((self.prep / 'receipt.json').exists())
    def test_compile_four_children_only(self):
        self.ready_compile(); result = q.compile_candidate(self.c, self.b, self.proof, self.admission)
        self.assertTrue(result['passed']); self.assertEqual(self.calls, ['compile-gguf', 'compile-test', 'candidate-link', 'test-link'])
    def test_compile_first_fault_stops_without_retry(self):
        self.ready_compile(); self.b.run_child.side_effect = RuntimeError('first')
        with self.assertRaises(RuntimeError): q.compile_candidate(self.c, self.b, self.proof, self.admission)
        self.assertEqual(self.b.run_child.call_count, 1); self.assertFalse((self.out / 'receipt.json').exists())
    def test_compile_changed_prior_produced_object_blocks_link(self):
        self.ready_compile()
        def run(*a):
            r = self.run(*a)
            if a[1] == 'compile-test': (self.out / 'gguf.o').write_text('changed')
            return r
        self.b.run_child.side_effect = run
        with self.assertRaisesRegex(ValueError, 'produced'): q.compile_candidate(self.c, self.b, self.proof, self.admission)
        self.assertEqual(self.calls, ['compile-gguf', 'compile-test'])
    def test_compile_unknown_link_input_blocks_next_child(self):
        self.ready_compile(); self.b.dependencies.return_value = ['/frozen', '/unknown']
        with self.assertRaises(ValueError): q.compile_candidate(self.c, self.b, self.proof, self.admission)
        self.assertEqual(self.calls, ['compile-gguf', 'compile-test', 'candidate-link'])
    def test_compile_unpinned_actual_input_blocks_all_children(self):
        self.ready_compile(); self.proof['files'].pop('/frozen')
        with self.assertRaises(ValueError): q.compile_candidate(self.c, self.b, self.proof, self.admission)
        self.b.run_child.assert_not_called()


if __name__ == '__main__': unittest.main()
