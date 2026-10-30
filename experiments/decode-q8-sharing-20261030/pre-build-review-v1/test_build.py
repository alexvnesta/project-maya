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
        self.c = c; self.m = SimpleNamespace(__file__='/qualified/prose_measure.py', cas_state=Mock(side_effect=cas))
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


class Qualification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.parent = self.root / 'parent'; self.parent.mkdir()
        for obj, name, value in [(q, 'HERE', self.root), (q, 'P', self.parent)]:
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
        support = self.parent / 'iq2s-persistent-v1/iq2s_build.py'
        support.parent.mkdir(); support.write_text('frozen support')
        p = patch.object(q, 'SUPPORT_SHA', q.sha(support)); p.start(); self.addCleanup(p.stop)
        for name in ('build.py', 'test_build.py'):
            (self.root / name).write_text(name)
        sources = {n: q.sha(self.root / n) for n in ('build.py', 'test_build.py')}
        self.value = {'mode': 'prepare', 'manual_source_reviewed': True, 'CPU_both_hosts_passed': True,
                      'source_sha256': sources, 'source_input_sha256': {'frozen': 'input'},
                      'test_ids': ['one', 'two'], 'files': {str(support): q.sha(support)}}
        for n, pin in sources.items(): self.value['files'][str(self.root / n)] = pin
        for label in ('darwin', 'linux'):
            folder = self.root / ('build-CPU-FIRST-' + label); folder.mkdir()
            child = {'returncode': 0, 'CPU_s': 30, 'wall_s': 90, 'nice': 15,
                     'CUDA_hidden': True, 'Linux_AS_MiB': 512 if label == 'linux' else None,
                     'error': None, 'cleanup_errors': []}
            receipt = {'passed': True, 'controls': 2, 'test_ids': ['one', 'two'],
                       'source_sha256': sources, 'source_input_sha256': {'frozen': 'input'}}
            self.write_cpu(label, 'child.json', child)
            self.write_cpu(label, 'receipt.json', receipt)
            (folder / 'child.log').write_text('raw proof')
            self.value['files'][str(folder / 'child.log')] = q.sha(folder / 'child.log')
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


if __name__ == '__main__': unittest.main()
