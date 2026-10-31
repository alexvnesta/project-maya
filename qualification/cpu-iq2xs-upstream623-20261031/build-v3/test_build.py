"""Prospective build custody controls. Compiler/ar/native execution is mocked."""
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import select
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import build as b


def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive(rows):
    result = b'!<arch>\n'; longnames = b''; names = []
    for name, data in rows:
        if len(name) > 15:
            names.append('/' + str(len(longnames))); longnames += name.encode() + b'/\n'
        else:
            names.append(name + '/')
    members = ([('//', longnames)] if longnames else []) + [(n, data) for n, (_, data) in zip(names, rows)]
    for name, data in members:
        header = (name.ljust(16) + '0'.ljust(12) + '0'.ljust(6) + '0'.ljust(6) +
                  '644'.ljust(8) + str(len(data)).ljust(10) + '`\n').encode()
        result += header + data + (b'\n' if len(data) % 2 else b'')
    return result


class Recipe(unittest.TestCase):
    def setUp(self):
        self.first, self.second = b.observations()
        self.folder = b.HERE / 'synthetic-owned'

    def test_actual_two_cpu_recipes_preserve_arithmetic(self):
        common = b.compiler(self.first)
        self.assertIn('-DSTRATA_VERSION="0.1.27"', common)
        self.assertLess(common.index('-I' + str(b.N / 'candidate/include')), common.index('-I' + str(b.S / 'include')))
        iq = b.compile_command(self.first, 'iq_avx2.cpp', self.folder)
        other = b.compile_command(self.first, 'native_expert.cpp', self.folder)
        self.assertIn('-mavx2', iq); self.assertIn('-ffp-contract=off', iq)
        self.assertNotIn('-mavx2', other); self.assertNotIn('-ffast-math', iq)

    def test_control_only_redirects_outputs_and_resolves_inputs(self):
        argv = b.native_link(self.first, self.folder)
        self.assertEqual(argv[argv.index('-o') + 1], str(self.folder / 'selected-relink'))
        self.assertIn('-Wl,--dependency-file=' + str(self.folder / 'selected-relink.link.d'), argv)
        self.assertEqual(len([x for x in argv if x.endswith('.o')]), 10)
        self.assertTrue(all(Path(x).is_absolute() for x in argv if x.endswith(('.o', '.a', '.so'))))
        self.assertIn(str(b.B / 'libstrata_kernels_cpu.a'), argv)

    def test_candidate_changes_only_archive_input(self):
        control = b.native_link(self.first, self.folder)
        candidate = b.native_link(self.first, self.folder, candidate=True)
        self.assertEqual([x for x in control if x.endswith('.o')], [x for x in candidate if x.endswith('.o')])
        self.assertIn(str(self.folder / 'libstrata_kernels_cpu.a'), candidate)
        self.assertNotIn(str(b.B / 'libstrata_kernels_cpu.a'), candidate)

    def test_dependency_scan_has_no_compile(self):
        for name in ('iq_avx2.cpp', 'native_expert.cpp', 'iq2xs_exact.cpp'):
            argv = b.compile_command(self.first, name, self.folder, scan=True)
            self.assertIn('-M', argv); self.assertNotIn('-c', argv)
            self.assertEqual(Path(argv[argv.index('-o') + 1]).parent, self.folder)

    def test_fixture_retains_original_ds4_wrapper_and_cpu_libraries(self):
        argv = b.fixture_link(self.folder)
        self.assertIn(str(b.B / 'CMakeFiles/maya-ds4.dir/src/ds4/ds4_iq_cpu.cpp.o'), argv)
        self.assertNotIn(str(b.B / 'libstrata_kernels_cpu.a'), argv)
        self.assertFalse(any('cuda' in x for x in argv))

    def test_changed_arithmetic_refused(self):
        key = str(b.B / 'CMakeFiles/strata_kernels_cpu.dir/flags.make')
        self.first['files'][key]['text'] = self.first['files'][key]['text'].replace('-O3', '-Ofast')
        with self.assertRaisesRegex(ValueError, 'arithmetic'):
            b.compiler(self.first)

    def test_changed_recipe_refused(self):
        self.first['recipes']['iq_avx2.cpp'][0] += ' -ffast-math'
        with self.assertRaisesRegex(ValueError, 'compile recipe'):
            b.compiler(self.first)

    def test_original_saved_link_phony_rules_parse(self):
        names = b.dependencies(self.second['original_link_dependency_text'], b.B)
        self.assertIn(str(b.B / 'libstrata_kernels_cpu.a'), names)
        self.assertIn(str(b.B / 'CMakeFiles/maya-ds4.dir/src/ds4/ds4_model.cu.o'), names)
        self.assertEqual(len(names), len(set(names)))

    def test_missing_and_malformed_rules_refuse(self):
        for text in ('', 'a:', ': x', 'a x', 'a: b:c'):
            with self.assertRaises(ValueError): b.dependencies(text, self.folder)

    def test_input_conflict_refused(self):
        a = {'files': {'/tmp/a': {'sha256': 'a' * 64}}}
        c = {'files': {'/tmp/a': {'sha256': 'b' * 64}}}
        with self.assertRaisesRegex(ValueError, 'Conflicting'): b.inventory(a, c)


class Archive(unittest.TestCase):
    def setUp(self):
        self.rows = [(n, ('original-' + n).encode()) for n in b.MEMBERS]
        self.before = archive(self.rows)
        self.replacements = {n: ('changed-' + n).encode() for n in b.REPLACED}
        self.after = archive([(n, self.replacements.get(n, data)) for n, data in self.rows])

    def test_exact_two_replacements_and_longnames(self):
        b.archive_contract(self.before, self.after, {n: digest(v) for n, v in self.replacements.items()})
        self.assertEqual(tuple(n for n, _ in b.archive_members(self.after)), b.MEMBERS)

    def test_other_member_mutation_refused(self):
        changed = archive([(n, b'foreign' if n == b.MEMBERS[0] else self.replacements.get(n, data)) for n, data in self.rows])
        with self.assertRaisesRegex(ValueError, 'Unchanged'): b.archive_contract(self.before, changed, {n: digest(v) for n, v in self.replacements.items()})

    def test_reordering_refused(self):
        with self.assertRaisesRegex(ValueError, 'order'):
            b.archive_contract(self.before, archive(list(reversed(self.rows))), {n: digest(v) for n, v in self.replacements.items()})

    def test_missing_replacement_refused(self):
        with self.assertRaisesRegex(ValueError, 'Exactly two'): b.archive_contract(self.before, self.after, {})

    def test_truncated_thin_duplicate_refused(self):
        for value in (self.before[:-1], b'!<thin>\n', archive([('a.o', b'a'), ('a.o', b'b')])):
            with self.assertRaises(ValueError): b.archive_members(value)


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.file = self.root / 'header.h'; self.file.write_text('header')

    def test_known_tool_alias_checked_against_resolved_target(self):
        alias = self.root / 'tool'; alias.symlink_to(self.file)
        row = {'sha256': b.sha(self.file), 'resolved': str(self.file)}
        b.verify_files({str(alias): row['sha256']}, {str(alias): row})
        alias.unlink(); other = self.root / 'other'; other.write_text('header'); alias.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'target changed'): b.verify_files({str(alias): row['sha256']}, {str(alias): row})

    def test_unknown_dependency_refused(self):
        path = self.root / 'a.d'; path.write_text('a: ' + str(self.file))
        with self.assertRaisesRegex(ValueError, 'Unknown dependency'): b.actual_dependencies(path, self.root, {})

    def test_changed_dependency_refused(self):
        path = self.root / 'a.d'; path.write_text('a: ' + str(self.file))
        with self.assertRaisesRegex(ValueError, 'bytes changed'): b.actual_dependencies(path, self.root, {str(self.file): '0' * 64})

    def test_unknown_object_is_not_header_discovery(self):
        bad = self.root / 'bad.o'; bad.write_bytes(b'object')
        with patch.object(b, 'S', self.root):
            with self.assertRaisesRegex(ValueError, 'non-header'): b.discover_header(str(bad))

    def test_owned_output_alias_refused(self):
        alias = self.root / 'alias'; alias.symlink_to(self.file)
        with self.assertRaisesRegex(ValueError, 'regular'): b.regular(alias)

    def test_existing_stage_refused(self):
        with self.assertRaisesRegex(ValueError, 'Fresh'): b.fresh(self.root)


class Supervisor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name).resolve(); self.process = Mock(pid=54321, returncode=0)
        self.process.poll.return_value = 0
        self.guard = Mock()

    def popen(self, argv, **kw):
        self.options = kw
        _, cpu, memory, _ = b.resource_class(argv, '-c' in argv)
        b.emit(self.folder / 'tool.observed.json', {'pid': 54321, 'ppid': os.getpid(), 'pgid': 54321,
               'cpu': [cpu, cpu], 'as': [memory, memory], 'nice': 15,
               'environment': dict(b.ENV, TMPDIR=str(self.folder / 'tool.tmp'))})
        return self.process

    def test_compiler_bounds_command_and_owned_group(self):
        with patch.object(b.subprocess, 'Popen', side_effect=self.popen), patch.object(b, 'cleanup') as clean:
            row = b.run_child(['/usr/bin/c++', '-c', 'input', '-o', str(self.folder / 'object.o')], 'tool', self.folder, self.guard, compiler_child=True)
        self.assertEqual((row['CPU_s'], row['AS_bytes'], row['wall_s']), (120, 4 * 2**30, 300))
        self.assertTrue(self.options['start_new_session']); self.assertEqual(self.options['cwd'], self.folder)
        self.assertEqual(self.options['env']['CUDA_VISIBLE_DEVICES'], '')
        self.assertEqual(self.options['env']['TMPDIR'], str(self.folder / 'tool.tmp'))
        self.assertEqual(self.options['env']['PATH'], '/usr/bin:/bin'); clean.assert_called_once()

    def test_link_cpu_wall_retained_with_memory_for_actual_cuda_libraries(self):
        with patch.object(b.subprocess, 'Popen', side_effect=self.popen), patch.object(b, 'cleanup'):
            row = b.run_child(['/usr/bin/c++', '-o', 'fresh'], 'tool', self.folder, self.guard)
        self.assertEqual((row['CPU_s'], row['AS_bytes'], row['wall_s']), (30, 4 * 2**30, 90))

    def test_compiler_environment_output_and_tool_overrides_removed(self):
        with patch.dict(b.os.environ, {'CPATH': '/foreign', 'GCC_EXEC_PREFIX': '/foreign',
                                      'DEPENDENCIES_OUTPUT': '/foreign/file', 'TMPDIR': '/foreign',
                                      'LD_PRELOAD': '/foreign.so', 'PATH': '/foreign'}):
            env = b.environment()
        for name in ('CPATH', 'GCC_EXEC_PREFIX', 'DEPENDENCIES_OUTPUT', 'TMPDIR', 'LD_PRELOAD'):
            self.assertNotIn(name, env)
        self.assertEqual(env['PATH'], '/usr/bin:/bin'); self.assertEqual(env['LC_ALL'], 'C')

    def test_scan_and_archive_remain_small(self):
        self.assertEqual(b.resource_class(['/usr/bin/c++', '-M', '-o', '/fresh/headers.d'], False),
                         ('scan', 30, 512 * 2**20, 90))
        self.assertEqual(b.resource_class(['/usr/bin/ar', 'r'], False), ('archive', 30, 512 * 2**20, 90))

    def test_busy_is_controlled_deferral_not_native_fault(self):
        self.guard.side_effect = ValueError('DEFERRED_BUSY_UNTOUCHED_OR_CLEANUP_OWNED_COMPILER')
        with patch.object(b.subprocess, 'Popen') as popen:
            with self.assertRaises(b.BuildDeferred): b.run_child(['/usr/bin/ar'], 'tool', self.folder, self.guard)
        popen.assert_not_called()
        self.assertEqual(json.loads((self.folder / 'tool.json').read_text())['status'], 'DEFERRED_BUSY_PARTIALS_RETAINED')

    def test_resource_class_and_native_execution_refused(self):
        with patch.object(b.subprocess, 'Popen') as popen:
            for argv, flag in ((['/usr/bin/c++', '-c', 'x'], False), (['/tmp/maya-ds4'], False)):
                with self.assertRaises(ValueError): b.run_child(argv, 'tool', self.folder, self.guard, compiler_child=flag)
        popen.assert_not_called()

    def test_initial_busy_creates_no_child(self):
        self.guard.side_effect = ValueError('busy')
        with patch.object(b.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'cleanup failed'): b.run_child(['/usr/bin/ar'], 'tool', self.folder, self.guard)
        popen.assert_not_called(); self.assertIn('busy', json.loads((self.folder / 'tool.json').read_text())['error'])

    def test_busy_during_child_cleans_owned_group(self):
        self.process.poll.side_effect = [None, 0]
        self.guard.side_effect = [None, ValueError('new user work')]
        with patch.object(b.subprocess, 'Popen', side_effect=self.popen), patch.object(b, 'cleanup') as clean:
            with self.assertRaises(ValueError): b.run_child(['/usr/bin/ar'], 'tool', self.folder, self.guard)
        clean.assert_called_once(); self.assertIn('new user work', json.loads((self.folder / 'tool.json').read_text())['error'])

    def test_nonzero_preserves_cleanup_fault(self):
        self.process.returncode = 2; self.process.poll.return_value = 2
        with patch.object(b.subprocess, 'Popen', side_effect=self.popen), patch.object(b, 'cleanup', side_effect=ValueError('cleanup fault')):
            with self.assertRaises(ValueError): b.run_child(['/usr/bin/ar'], 'tool', self.folder, self.guard)
        row = json.loads((self.folder / 'tool.json').read_text())
        self.assertIn('nonzero', row['error']); self.assertIn('cleanup fault', row['cleanup'][0])

    def test_start_failure_has_no_cleanup_target(self):
        with patch.object(b.subprocess, 'Popen', side_effect=OSError('refused')), patch.object(b, 'cleanup') as clean:
            with self.assertRaises(ValueError): b.run_child(['/usr/bin/ar'], 'tool', self.folder, self.guard)
        clean.assert_not_called()

    def test_deadline_stops_before_next_poll(self):
        self.process.poll.side_effect = [None, 0]
        with patch.object(b.subprocess, 'Popen', side_effect=self.popen), patch.object(b, 'cleanup'), \
             patch.object(b.time, 'monotonic', side_effect=[0, 0, 86, 86]):
            with self.assertRaises(ValueError): b.run_child(['/usr/bin/ar'], 'tool', self.folder, self.guard)
        self.assertIn('deadline', json.loads((self.folder / 'tool.json').read_text())['error'])

    def test_live_group_change_refuses_signal(self):
        self.process.poll.return_value = None
        with patch.object(b.os, 'getpgid', return_value=54322), patch.object(b.os, 'killpg') as kill:
            with self.assertRaisesRegex(ValueError, 'group changed'): b.cleanup(self.process, time.monotonic() + 1)
        kill.assert_not_called()

    def test_exited_child_descendants_still_cleaned(self):
        with patch.object(b, 'group_alive', side_effect=[True, True, False, False]), patch.object(b.os, 'killpg') as kill:
            b.cleanup(self.process, time.monotonic() + 1)
        self.assertEqual([x.args[1] for x in kill.call_args_list], [b.signal.SIGTERM, b.signal.SIGKILL])


class Execute(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.here = self.root / 'new'; self.here.mkdir()
        self.old = self.root / 'original'; self.old.mkdir(); self.source = self.root / 'source.h'; self.source.write_text('header')
        (self.old / 'maya-ds4').write_bytes(b'selected')
        self.rows = [(n, n.encode()) for n in b.MEMBERS]
        self.archive = archive(self.rows); (self.old / 'libstrata_kernels_cpu.a').write_bytes(self.archive)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for name, value in {'HERE': self.here, 'B': self.old, 'R': self.root,
                            'BASE': digest(b'selected'), 'ARCHIVE': digest(self.archive)}.items():
            self.stack.enter_context(patch.object(b, name, value))
        self.stack.enter_context(patch.object(b, 'observations', return_value=({}, {})))
        self.stack.enter_context(patch.object(b, 'native_link', side_effect=lambda first, folder, candidate=False:
            ['/usr/bin/c++', '-o', str(folder / ('maya-ds4-candidate' if candidate else 'selected-relink'))]))
        self.stack.enter_context(patch.object(b, 'compile_command', side_effect=lambda first, name, folder, scan=False:
            ['/usr/bin/c++', '-M' if scan else '-c', '-o', str(folder / (name + ('.headers.d' if scan else '.o')))]))
        self.stack.enter_context(patch.object(b, 'fixture_link', side_effect=lambda folder: ['/usr/bin/c++', '-o', str(folder / 'iq2xs_exact')]))
        self.q = {'files': {str(self.source): b.sha(self.source)}}; self.calls = []
        self.runner = self.stack.enter_context(patch.object(b, 'run_child', side_effect=self.fake_run))

    def fake_run(self, argv, name, folder, guard, **kw):
        self.calls.append(name)
        if argv[0] == '/usr/bin/ar':
            (folder / 'libstrata_kernels_cpu.a').write_bytes(archive([(n, (folder / n).read_bytes() if n in b.REPLACED else data) for n, data in self.rows]))
        elif argv[0] != '/usr/bin/ranlib':
            target = Path(argv[argv.index('-o') + 1])
            if '-M' in argv: target.write_text('x: ' + str(self.source))
            else:
                target.write_bytes(b'selected' if name == 'control-link' else name.encode())
                dep = Path(str(target) + ('.d' if '-c' in argv else '.link.d'))
                dep.write_text('x: ' + str(self.source))
        return {'returncode': 0, 'error': None, 'cleanup': []}

    def prepare(self):
        return b.execute('prepare', self.q, {}, Mock())

    def compile_q(self):
        self.prepare(); self.calls.clear()
        prep = self.here / 'prepare-FIRST/receipt.json'
        self.q['actual_inputs_manually_reviewed'] = True; self.q['files'][str(prep)] = b.sha(prep)

    def test_prepare_control_first_and_three_scans_no_compile(self):
        result = self.prepare()
        self.assertEqual(self.calls, ['control-link', 'deps-iq_avx2.cpp', 'deps-native_expert.cpp', 'deps-iq2xs_exact.cpp'])
        self.assertEqual(result['status'], 'PREPARED_STOP_FOR_ACTUAL_INPUT_REVIEW')
        self.assertFalse((self.here / 'build-FIRST').exists())

    def test_failed_control_stops_before_scans(self):
        def wrong(*args, **kwargs):
            result = self.fake_run(*args, **kwargs); (self.here / 'prepare-FIRST/selected-relink').write_bytes(b'wrong'); return result
        self.runner.side_effect = wrong
        with self.assertRaisesRegex(ValueError, 'reproduce'): self.prepare()
        self.assertEqual(self.calls, ['control-link'])

    def test_first_child_fault_stops_following_children(self):
        self.runner.side_effect = ValueError('first fault')
        with self.assertRaisesRegex(ValueError, 'first fault'): self.prepare()
        self.assertEqual(self.runner.call_count, 1); self.assertFalse((self.here / 'prepare-FIRST/receipt.json').exists())

    def test_compile_requires_separate_actual_input_review(self):
        with self.assertRaisesRegex(ValueError, 'prepare review'): b.execute('compile', self.q, {}, Mock())
        self.runner.assert_not_called(); self.assertFalse((self.here / 'build-FIRST').exists())

    def test_compile_two_objects_fixture_archive_and_two_links(self):
        self.compile_q(); result = b.execute('compile', self.q, {}, Mock())
        self.assertEqual(len(self.calls), 7)
        self.assertEqual(self.calls[-4:], ['archive-replace', 'archive-index', 'candidate-link', 'fixture-link'])
        self.assertEqual((self.old / 'libstrata_kernels_cpu.a').read_bytes(), self.archive)
        self.assertFalse(result['native_execution']); self.assertFalse(result['fixture_execution'])

    def test_source_change_between_steps_refuses_next_child(self):
        def changed(*args, **kwargs):
            result = self.fake_run(*args, **kwargs); self.source.write_text('changed'); return result
        self.runner.side_effect = changed
        with self.assertRaisesRegex(ValueError, 'Pinned input'): self.prepare()
        self.assertEqual(len(self.calls), 1)

    def test_produced_object_tamper_refuses_archive(self):
        self.compile_q()
        def changed(argv, name, folder, guard, **kw):
            result = self.fake_run(argv, name, folder, guard, **kw)
            if name == 'compile-native_expert.cpp': (folder / 'iq_avx2.cpp.o').write_bytes(b'tamper')
            return result
        self.runner.side_effect = changed
        with self.assertRaisesRegex(ValueError, 'Produced'): b.execute('compile', self.q, {}, Mock())
        self.assertEqual(len(self.calls), 2)

    def test_unknown_link_input_stops_before_next_child(self):
        def unknown(argv, name, folder, guard, **kw):
            result = self.fake_run(argv, name, folder, guard, **kw)
            (folder / 'selected-relink.link.d').write_text('x: /foreign/object.o'); return result
        self.runner.side_effect = unknown
        with self.assertRaisesRegex(ValueError, 'Unknown dependency'): self.prepare()
        self.assertEqual(len(self.calls), 1)


def coordination(e):
    return {'single_coordinator_maintenance_freeze': True, 'state_CAS_is_global_atomic': False,
            'GPU_lease_untouched': True, 'cpu_lock_path': str(e / 'cpu-build.lock')}


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.here = self.root / 'build'; self.here.mkdir()
        self.e = self.root / 'E'; self.e.mkdir(); (self.root / 'experiment.lock').write_text('')
        self.state = self.e / 'STATE.json'; self.state.write_text(json.dumps({'active_cpu_build': False}))
        (self.here / 'prepare-qualification.json').write_text('{}')
        self.pin = b.sha(self.here / 'prepare-qualification.json'); self.binding = {'native_pid': 123, 'main_pid': 122}
        self.host = Mock(); self.runtime = Mock(); self.c = Mock(); self.cas = Mock()
        self.c.support.return_value = (None, self.runtime, None, self.host, self.binding)
        self.c.guard.side_effect = lambda *args: json.loads(self.state.read_text())
        def write(path, before, value):
            if path.read_bytes() != before: raise ValueError('synthetic CAS race')
            path.write_text(json.dumps(value))
        self.cas.cas_state.side_effect = write
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for name, value in {'HERE': self.here, 'EXPECTED': self.here, 'R': self.root, 'E': self.e}.items():
            self.stack.enter_context(patch.object(b, name, value))
        self.stack.enter_context(patch.object(b.sys, 'platform', 'linux'))
        self.stack.enter_context(patch.object(b, 'bootstrap', return_value=dict(coordination(self.e), selected_binding=self.binding)))
        self.stack.enter_context(patch.object(b, 'process_ticks', return_value=123456))
        def gpu(host, binding, expected=None):
            host.guard_binding()
            return {'identity': {'device_major': 1, 'device_minor': 2, 'inode': 3},
                    'main_pid': binding['main_pid'], 'kernel_lock': 'synthetic selected lock'}
        self.gpu = self.stack.enter_context(patch.object(b, 'observe_gpu_lease', side_effect=gpu))
        self.verify = self.stack.enter_context(patch.object(b, 'verify_q', return_value=({'selected_binding': self.binding}, {})))
        self.stack.enter_context(patch.object(b, 'load_cas', return_value=self.cas))
        self.stack.enter_context(patch.object(b, 'load_exact', side_effect=lambda name, *args: self.c if name == 'iq2s_build' else self.cas))
        self.space = self.stack.enter_context(patch.object(b.shutil, 'disk_usage', return_value=Mock(free=140 * 2**30)))
        self.execute = self.stack.enter_context(patch.object(b, 'execute', return_value={'passed': True}))

    def test_claim_and_release_only_owned_build(self):
        self.assertEqual(b.main('prepare', self.pin), {'passed': True})
        self.assertEqual(json.loads(self.state.read_text())['active_cpu_build'], False)
        self.assertEqual(self.cas.cas_state.call_count, 2); self.assertGreaterEqual(self.host.guard_binding.call_count, 1)
        self.host.restore_ds.assert_not_called()

    def test_CAS_import_fault_precedes_CPU_lease_claim_and_namespace(self):
        with patch.object(b, 'load_cas', side_effect=ModuleNotFoundError('transport')), \
             patch.object(b, 'CPULease') as lease:
            with self.assertRaisesRegex(ModuleNotFoundError, 'transport'): b.main('prepare', self.pin)
        lease.assert_not_called(); self.cas.cas_state.assert_not_called(); self.execute.assert_not_called()
        self.assertFalse((self.e / 'cpu-build.lock').exists())
        self.assertFalse((self.here / 'prepare-supervision-FIRST').exists())
        self.assertFalse(json.loads(self.state.read_text())['active_cpu_build'])

    def test_idle_refusal_precedes_large_qualification_hash(self):
        self.c.guard.side_effect = ValueError('busy')
        with self.assertRaisesRegex(ValueError, 'busy'): b.main('prepare', self.pin)
        self.verify.assert_not_called(); self.execute.assert_not_called()

    def test_root136_refuses_before_claim(self):
        self.space.return_value = Mock(free=135 * 2**30)
        with self.assertRaisesRegex(ValueError, 'Root136'): b.main('prepare', self.pin)
        self.execute.assert_not_called(); self.cas.cas_state.assert_not_called()

    def test_changed_owner_refuses_before_hash_and_claim(self):
        self.c.support.return_value = (None, self.runtime, None, self.host, {'native_pid': 124})
        with self.assertRaisesRegex(ValueError, 'owner differs'): b.main('prepare', self.pin)
        self.verify.assert_not_called(); self.cas.cas_state.assert_not_called()

    def test_primary_build_fault_preserved_and_claim_released(self):
        self.execute.side_effect = ValueError('primary child fault')
        with self.assertRaisesRegex(ValueError, 'primary child fault'): b.main('prepare', self.pin)
        self.assertIs(json.loads(self.state.read_text())['active_cpu_build'], False)
        self.assertGreaterEqual(self.host.guard_binding.call_count, 1)

    def test_foreign_claim_preserved_with_primary_and_owner_check(self):
        def foreign(*args):
            self.state.write_text(json.dumps({'active_cpu_build': {'foreign': True}}))
            raise ValueError('primary child fault')
        self.execute.side_effect = foreign
        with self.assertRaisesRegex(ValueError, 'primary child fault') as caught: b.main('prepare', self.pin)
        self.assertIn('claim changed', caught.exception.__notes__[0])
        self.assertEqual(json.loads(self.state.read_text())['active_cpu_build'], {'foreign': True})
        self.assertGreaterEqual(self.host.guard_binding.call_count, 1)

    def test_lock_conflict_creates_no_claim(self):
        with patch.object(b.fcntl, 'flock', side_effect=BlockingIOError('locked')):
            with self.assertRaises(BlockingIOError): b.main('prepare', self.pin)
        self.cas.cas_state.assert_not_called(); self.execute.assert_not_called()

    def test_foreign_GPU_holder_refuses_before_full_hash_or_claim(self):
        self.gpu.side_effect = ValueError('GPU lease is not exact selected API holder')
        with self.assertRaisesRegex(ValueError, 'selected API'): b.main('prepare', self.pin)
        self.verify.assert_not_called(); self.cas.cas_state.assert_not_called()

    def test_stale_CPU_claim_refused_without_adoption(self):
        stale = {'controller_pid': 87654, 'nonce': 'stale'}
        self.state.write_text(json.dumps({'active_cpu_build': stale}))
        with self.assertRaisesRegex(ValueError, 'no automatic adoption'): b.main('prepare', self.pin)
        self.assertEqual(json.loads(self.state.read_text())['active_cpu_build'], stale)
        self.cas.cas_state.assert_not_called(); self.execute.assert_not_called()

    def test_cooperative_boundary_required_before_support_import(self):
        with patch.object(b, 'bootstrap', return_value={'selected_binding': self.binding}), \
             patch.object(b, 'load_exact') as loader:
            with self.assertRaisesRegex(ValueError, 'cooperative'): b.main('prepare', self.pin)
        loader.assert_not_called()

    def test_cleanup_fault_retains_claim_even_if_group_now_absent(self):
        def failed(mode, q, observed, guard, owned):
            process = Mock(pid=54321); process.poll.return_value = 0
            owned.starting('compiler'); owned.registered(process, 'compiler')
            owned.cleanup_failed('compiler', ValueError('cleanup fault'))
            raise ValueError('primary tool failure')
        self.execute.side_effect = failed
        with patch.object(b, 'group_alive', return_value=False):
            with self.assertRaisesRegex(ValueError, 'primary tool failure') as caught:
                b.main('prepare', self.pin)
        self.assertIn('absence unproved', caught.exception.__notes__[0])
        claim = json.loads(self.state.read_text())['active_cpu_build']
        self.assertEqual(claim['controller_pid'], os.getpid())
        self.assertEqual(claim['controller_start_ticks'], 123456)
        self.assertEqual(len(claim['nonce']), 32); self.assertEqual(self.cas.cas_state.call_count, 1)
        result = json.loads((self.here / 'prepare-supervision-FIRST/result.json').read_text())
        self.assertEqual(result['status'], 'HOLD'); self.assertFalse(result['own_claim_released'])

    def test_surviving_group_retains_claim_and_does_not_retry_cleanup(self):
        def failed(mode, q, observed, guard, owned):
            process = Mock(pid=54321); process.poll.return_value = 0
            owned.starting('compiler'); owned.registered(process, 'compiler')
            raise ValueError('primary tool failure')
        self.execute.side_effect = failed
        with patch.object(b, 'group_alive', return_value=True), patch.object(b, 'cleanup') as clean:
            with self.assertRaisesRegex(ValueError, 'primary tool failure'): b.main('prepare', self.pin)
        clean.assert_not_called(); self.assertEqual(self.cas.cas_state.call_count, 1)
        self.assertTrue(json.loads(self.state.read_text())['active_cpu_build'])

    def test_indeterminate_spawn_retains_claim_with_empty_PID_list(self):
        def failed(mode, q, observed, guard, owned):
            owned.starting('compiler'); raise OSError('Popen incomplete')
        self.execute.side_effect = failed
        with self.assertRaisesRegex(OSError, 'Popen incomplete'): b.main('prepare', self.pin)
        result = json.loads((self.here / 'prepare-supervision-FIRST/result.json').read_text())
        self.assertEqual(result['owned_groups_absence']['pending_spawn'], 'compiler')
        self.assertFalse(result['own_claim_released']); self.assertEqual(self.cas.cas_state.call_count, 1)

    def test_absent_owned_group_proof_precedes_release(self):
        def complete(mode, q, observed, guard, owned):
            process = Mock(pid=54321); process.poll.return_value = 0
            owned.starting('compiler'); owned.registered(process, 'compiler')
            return {'passed': True}
        self.execute.side_effect = complete
        seen = []
        original = self.cas.cas_state.side_effect
        def state_write(path, before, value):
            if value['active_cpu_build'] is False: self.assertEqual(seen, [54321])
            original(path, before, value)
        self.cas.cas_state.side_effect = state_write
        with patch.object(b, 'group_alive', side_effect=lambda pid: seen.append(pid) or False):
            self.assertEqual(b.main('prepare', self.pin), {'passed': True})
        journal = (self.here / 'prepare-supervision-FIRST/owned-children.jsonl').read_text()
        self.assertEqual(json.loads(journal)['pgid'], 54321)

    def test_vanished_claim_after_success_is_HOLD_not_silent_release(self):
        def lost(*args):
            self.state.write_text(json.dumps({'active_cpu_build': False})); return {'passed': True}
        self.execute.side_effect = lost
        with self.assertRaisesRegex(ValueError, 'claim vanished'): b.main('prepare', self.pin)
        self.assertEqual(self.cas.cas_state.call_count, 1)

    def test_busy_with_no_children_releases_owned_claim_and_records_deferral(self):
        self.execute.side_effect = b.BuildDeferred('DEFERRED_BUSY_PARTIALS_RETAINED')
        with self.assertRaises(b.BuildDeferred): b.main('prepare', self.pin)
        result = json.loads((self.here / 'prepare-supervision-FIRST/result.json').read_text())
        self.assertEqual(result['status'], 'DEFERRED_BUSY_PARTIALS_RETAINED')
        self.assertTrue(result['own_claim_released'])

    def test_busy_between_tools_is_controlled_deferral_after_safe_release(self):
        self.execute.side_effect = ValueError('DEFERRED_BUSY_UNTOUCHED_OR_CLEANUP_OWNED_COMPILER')
        with self.assertRaises(b.BuildDeferred): b.main('prepare', self.pin)
        result = json.loads((self.here / 'prepare-supervision-FIRST/result.json').read_text())
        self.assertEqual(result['status'], 'DEFERRED_BUSY_PARTIALS_RETAINED')
        self.assertTrue(result['owned_groups_absence']['passed']); self.assertTrue(result['own_claim_released'])

    def test_primary_error_preserved_if_supervision_receipt_write_fails(self):
        self.execute.side_effect = ValueError('primary tool fault')
        original = b.emit
        def emit(path, value):
            if path.name == 'result.json': raise OSError('receipt fault')
            original(path, value)
        with patch.object(b, 'emit', side_effect=emit):
            with self.assertRaisesRegex(ValueError, 'primary tool fault') as caught:
                b.main('prepare', self.pin)
        self.assertIn('receipt fault', caught.exception.__notes__[-1])
        self.assertIs(json.loads(self.state.read_text())['active_cpu_build'], False)

    def test_other_state_fields_preserved_on_own_release(self):
        def complete(*args):
            value = json.loads(self.state.read_text()); value['unrelated_receipt'] = 'keep'
            self.state.write_text(json.dumps(value)); return {'passed': True}
        self.execute.side_effect = complete
        b.main('prepare', self.pin)
        self.assertEqual(json.loads(self.state.read_text()), {'active_cpu_build': False, 'unrelated_receipt': 'keep'})

    def test_GPU_owner_change_after_execute_retains_failure(self):
        def complete(*args):
            self.gpu.side_effect = ValueError('selected owner changed'); return {'passed': True}
        self.execute.side_effect = complete
        with self.assertRaisesRegex(ValueError, 'selected owner changed'): b.main('prepare', self.pin)
        result = json.loads((self.here / 'prepare-supervision-FIRST/result.json').read_text())
        self.assertEqual(result['status'], 'HOLD')

    def test_claim_CAS_refusal_never_starts_tool_or_rewrites_state(self):
        self.cas.cas_state.side_effect = ValueError('CAS refused')
        with self.assertRaisesRegex(ValueError, 'CAS refused'): b.main('prepare', self.pin)
        self.execute.assert_not_called(); self.assertEqual(self.cas.cas_state.call_count, 1)
        self.assertIs(json.loads(self.state.read_text())['active_cpu_build'], False)


class Qualification(unittest.TestCase):
    def setUp(self):
        import cpu_driver as d
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.here = self.root / 'new'; self.here.mkdir()
        self.d = self.root / 'decode'; self.d.mkdir(); self.n = self.root / 'N'
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for name, value in {'HERE': self.here, 'R': self.root, 'D': self.d, 'N': self.n, 'E': self.root}.items():
            self.stack.enter_context(patch.object(b, name, value))
        self.files = {}
        def put(path, data):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(data)
            self.files[str(path)] = b.sha(path); return self.files[str(path)]
        self.put = put
        self.binding = {'native_pid': 123}
        self.first = {'files': {}, 'binding': self.binding}
        self.stack.enter_context(patch.object(b, 'observations', return_value=(self.first, copy.deepcopy(self.first))))
        for name in ('DEPENDENCY_OBSERVATION.json', 'LINK_TOOL_CLOSURE_OBSERVATION.json'):
            put(self.n / 'build-v1' / name, '{}')
        helper = self.d / 'helper.py'; helper_pin = put(helper, '# untouched helper')
        pin = put(self.d / 'model-v1/numerical-qualification.json', json.dumps({'files': {str(helper): helper_pin}}))
        self.stack.enter_context(patch.object(b, 'IMPORT_Q_SHA', pin))
        for field, name in (('SUPPORT_SHA', 'iq2s-persistent-v1/iq2s_build.py'), ('CAS_SHA', 'prose-speed-v1/prose_measure.py'),
                            ('TRANSPORT_SHA', 'prose-speed-v1/transport.py')):
            self.stack.enter_context(patch.object(b, field, put(self.d / name, '# support')))
        sources = {name: put(self.here / name, '# new') for name in ('build.py', 'test_build.py', 'cpu_driver.py', 'test_cpu_driver.py')}
        input_path = self.root / 'input.json'; input_pin = put(input_path, '{}')
        before = (sources, {str(input_path): input_pin}, ['test_build.Exact.test_one'])
        review_pin = put(self.here / 'SOURCE_ROOT_REVIEW.json', '{}')
        self.driver = Mock(); self.driver.checked.return_value = before
        self.driver.bounds.side_effect = d.bounds; self.driver.attempt_contract.side_effect = d.attempt_contract
        self.loader = self.stack.enter_context(patch.object(b, 'load_exact', return_value=self.driver))
        self.q = {'mode': 'prepare', 'manual_source_reviewed': True, 'CPU_both_hosts_passed': True,
                  'files': self.files, 'source_sha256': sources, 'input_sha256': before[1],
                  'test_ids': before[2], 'source_review_sha256': review_pin, 'selected_binding': self.binding, **coordination(self.root)}
        for label in ('darwin', 'linux'):
            folder = self.here / ('CPU-FIRST-' + label)
            actual = {'pid': 12345, 'ppid': 12344, 'pgid': 12345, 'cpu': [30, 30],
                      'as': [512 * 2**20] * 2 if label == 'linux' else None,
                      'nice': 15, 'environment': d.ENV, 'platform': label, 'dont_write_bytecode': True}
            attempt = {'review_sha256': review_pin, 'parent_pid': 12344, 'source_sha256': sources,
                       'input_sha256': before[1], 'test_ids': before[2]}
            receipt = {'status': 'PASS', 'pid': 12345, 'review_sha256': review_pin, 'observed': actual,
                       'post_observed': actual, 'failures': 0, 'errors': 0, 'tests_run': 1, 'test_ids': before[2],
                       'source_sha256': sources, 'source_after_sha256': sources,
                       'input_sha256': before[1], 'input_after_sha256': before[1]}
            child = {'pid': 12345, 'returncode': 0, 'error': None, 'cleanup': [], 'elapsed_seconds': .1}
            for name, value in (('attempt', attempt), ('receipt', receipt), ('child', child), ('observed', actual)):
                put(folder / (name + '.json'), json.dumps(value))
            put(folder / 'child.log', 'one synthetic test passed')
            put(folder / 'parent.json', json.dumps({'status': 'PASS', 'pid': 12345, 'review_sha256': review_pin,
                'receipt_sha256': b.sha(folder / 'receipt.json'), 'child_sha256': b.sha(folder / 'child.json'),
                'log_sha256': b.sha(folder / 'child.log')}))

    def run_q(self):
        path = self.here / 'prepare-qualification.json'; path.write_text(json.dumps(self.q))
        return b.verify_q('prepare', b.sha(path))

    def test_complete_both_host_qualification_chain(self):
        result, observed = self.run_q()
        self.assertEqual(result['test_ids'], self.q['test_ids']); self.assertEqual(observed, {})
        self.assertEqual(self.driver.bounds.call_count, 2)

    def test_missing_or_false_cooperative_scope_refused_before_import(self):
        for key, value in (('single_coordinator_maintenance_freeze', False),
                           ('state_CAS_is_global_atomic', True), ('GPU_lease_untouched', False),
                           ('cpu_lock_path', str(self.root / 'experiment.lock'))):
            with self.subTest(key=key):
                old = self.q[key]; self.q[key] = value
                with self.assertRaisesRegex(ValueError, 'cooperative'): self.run_q()
                self.q[key] = old
        self.loader.assert_not_called()

    def test_omitted_python_closure_refuses_before_import(self):
        self.files.pop(str(self.d / 'helper.py'))
        with self.assertRaisesRegex(ValueError, 'Python closure'): self.run_q()
        self.loader.assert_not_called()

    def test_transport_membership_required_before_import(self):
        self.files.pop(str(self.d / 'prose-speed-v1/transport.py'))
        with self.assertRaisesRegex(ValueError, 'support/CAS'): self.run_q()
        self.loader.assert_not_called()

    def test_bootstrap_transport_membership_required_before_import(self):
        self.files.pop(str(self.d / 'prose-speed-v1/transport.py'))
        path = self.here / 'prepare-qualification.json'; path.write_text(json.dumps(self.q))
        with self.assertRaisesRegex(ValueError, 'Bootstrap Python closure'):
            b.bootstrap('prepare', b.sha(path))
        self.loader.assert_not_called()

    def test_missing_raw_log_membership_refused(self):
        self.files.pop(str(self.here / 'CPU-FIRST-linux/child.log'))
        with self.assertRaisesRegex(ValueError, 'raw proof'): self.run_q()

    def test_forged_success_with_wrong_as_refused(self):
        path = self.here / 'CPU-FIRST-linux/observed.json'; value = json.loads(path.read_text()); value['as'] = [-1, -1]
        self.put(path, json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'address-space'): self.run_q()

    def test_source_missing_from_full_map_refused(self):
        self.files.pop(str(self.here / 'test_build.py'))
        with self.assertRaisesRegex(ValueError, 'New source absent'): self.run_q()

    def test_no_actual_compile_review_refuses_before_import(self):
        self.q['mode'] = 'compile'
        path = self.here / 'compile-qualification.json'; path.write_text(json.dumps(self.q))
        with self.assertRaisesRegex(ValueError, 'Actual input review'): b.verify_q('compile', b.sha(path))
        self.loader.assert_not_called()


class LeaseContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.path = self.root / 'cpu-build.lock'
        self.identity = {'device_major': 252, 'device_minor': 1, 'inode': 1449998}
        self.row = '20: FLOCK ADVISORY WRITE 3998190 fc:01:1449998 0 EOF'

    def test_exact_API_lease_and_unrelated_locks(self):
        text = '1: POSIX ADVISORY READ 22 00:00:123 0 5\n' + self.row + '\n'
        self.assertEqual(b.gpu_lock_row(text, self.identity, 3998190), self.row)

    def test_native_or_foreign_PID_is_not_API_holder(self):
        for pid in ('3998227', '12', '-1'):
            with self.assertRaisesRegex(ValueError, 'selected API'):
                b.gpu_lock_row(self.row.replace('3998190', pid), self.identity, 3998190)

    def test_wrong_type_mode_range_and_read_lock_refused(self):
        for text in (self.row.replace('FLOCK', 'OFDLCK'), self.row.replace('ADVISORY', 'MANDATORY'),
                     self.row.replace('WRITE', 'READ'), self.row.replace(' 0 EOF', ' 1 EOF'),
                     self.row.replace(' EOF', ' 100')):
            with self.assertRaisesRegex(ValueError, 'selected API'):
                b.gpu_lock_row(text, self.identity, 3998190)

    def test_wrong_device_or_inode_missing_and_duplicate_refused(self):
        for text in (self.row.replace('fc:01', 'fd:01'), self.row.replace('fc:01', 'fc:02'),
                     self.row.replace('1449998', '1449999'), '', self.row + '\n' + self.row):
            with self.assertRaisesRegex(ValueError, 'Exactly one'):
                b.gpu_lock_row(text, self.identity, 3998190)

    def test_blocked_waiter_refused_even_when_holder_correct(self):
        waiter = self.row.replace('20:', '21: ->').replace('3998190', '777')
        with self.assertRaisesRegex(ValueError, 'blocked waiter'):
            b.gpu_lock_row(self.row + '\n' + waiter, self.identity, 3998190)

    def test_malformed_kernel_rows_and_boolean_PID_refused(self):
        for text in ('bad', self.row + ' extra', self.row.replace('fc:01', 'xx:01'),
                     self.row.replace('1449998', 'inode'), self.row.replace('20:', 'x:')):
            with self.assertRaises(ValueError): b.gpu_lock_row(text, self.identity, 3998190)
        with self.assertRaisesRegex(ValueError, 'API PID'): b.gpu_lock_row(self.row, self.identity, True)

    def test_observe_is_read_only_and_brackets_binding(self):
        gpu = self.root / 'experiment.lock'; gpu.write_bytes(b'preserve')
        st = gpu.stat(); ident = {'device_major': os.major(st.st_dev), 'device_minor': os.minor(st.st_dev), 'inode': st.st_ino}
        row = f"4: FLOCK ADVISORY WRITE 123 {ident['device_major']:x}:{ident['device_minor']:x}:{ident['inode']} 0 EOF"
        host = Mock(); original = Path.read_text
        def read(path, *args, **kw):
            return row if str(path) == '/proc/locks' else original(path, *args, **kw)
        with patch.object(b, 'R', self.root), patch.object(Path, 'read_text', read), \
             patch.object(b.fcntl, 'flock') as flock:
            result = b.observe_gpu_lease(host, {'main_pid': 123}, ident)
        self.assertEqual(result['kernel_lock'], row); self.assertEqual(host.guard_binding.call_count, 2)
        flock.assert_not_called(); self.assertEqual(gpu.read_bytes(), b'preserve')

    def test_observation_rejects_changed_inode_before_proc_read(self):
        (self.root / 'experiment.lock').write_text('')
        with patch.object(b, 'R', self.root), patch.object(Path, 'read_text') as read:
            with self.assertRaisesRegex(ValueError, 'inode changed'):
                b.observe_gpu_lease(Mock(), {'main_pid': 123}, self.identity)
        read.assert_not_called()

    def test_stable_CPU_inode_remains_and_descriptor_not_inherited(self):
        with b.CPULease(self.path) as lease:
            initial = dict(lease.identity); lease.check()
            self.assertFalse(os.get_inheritable(lease.fd))
        self.assertTrue(self.path.exists())
        with b.CPULease(self.path) as lease: self.assertEqual(lease.identity, initial)

    def test_CPU_alias_hardlink_and_ancestor_alias_refused(self):
        other = self.root / 'target'; other.write_text('untouched'); self.path.symlink_to(other)
        with self.assertRaises(OSError):
            with b.CPULease(self.path): pass
        self.path.unlink(); os.link(other, self.path)
        with self.assertRaisesRegex(ValueError, 'inode/owner/link'):
            with b.CPULease(self.path): pass
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'ancestor alias'):
            with b.CPULease(alias / 'other.lock'): pass
        self.assertEqual(other.read_text(), 'untouched')

    def test_CPU_named_inode_replacement_refused_without_deleting_replacement(self):
        with b.CPULease(self.path) as lease:
            self.path.unlink(); self.path.write_text('replacement')
            with self.assertRaisesRegex(ValueError, 'inode/owner/link'): lease.check()
        self.assertEqual(self.path.read_text(), 'replacement')

    def test_real_two_process_CPU_lease_contention_and_release(self):
        import cpu_driver as d
        folder = self.root / 'contender'; folder.mkdir()
        prefix = ('import sys,os,json,resource; '
                  'assert sys.dont_write_bytecode; '
                  'assert resource.getrlimit(resource.RLIMIT_CPU)==(30,30); '
                  'assert sys.platform!="linux" or resource.getrlimit(resource.RLIMIT_AS)==(536870912,536870912); '
                  'assert os.getpriority(os.PRIO_PROCESS,0)==15; '
                  'assert os.environ.get("CUDA_VISIBLE_DEVICES")==""; '
                  'sys.path.insert(0,' + repr(str(b.HERE)) + '); import build; from pathlib import Path; '
                  'path=Path(' + repr(str(self.path)) + ')\n')
        holder_code = prefix + ('with build.CPULease(path) as lease:\n'
            ' print(json.dumps(dict(ready=True,pid=os.getpid(),identity=lease.identity)),flush=True)\n'
            ' sys.stdin.buffer.read(1)\n')
        contender_code = prefix + ('try:\n'
            ' with build.CPULease(path): raise AssertionError("Second contender acquired lease")\n'
            'except BlockingIOError:\n'
            ' print("CONTENTION_REFUSED",flush=True)\n')
        holder = None; started = time.monotonic()
        try:
            holder = subprocess.Popen([sys.executable, '-I', '-B', '-c', holder_code],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=b.HERE, env=d.environment(), start_new_session=True, preexec_fn=d.limits)
            self.assertTrue(select.select([holder.stdout], [], [], 2)[0], 'Holder readiness deadline')
            ready = json.loads(holder.stdout.readline()); self.assertEqual(ready['pid'], holder.pid)
            self.assertTrue(ready['ready'])
            result = d.supervise([sys.executable, '-I', '-B', '-c', contender_code], folder,
                                 run_seconds=3, wall_seconds=5)
            self.assertEqual((result['returncode'], result['error'], result['cleanup']), (0, None, []))
            self.assertEqual((folder / 'child.log').read_text().strip(), 'CONTENTION_REFUSED')
            holder.stdin.write(b'x'); holder.stdin.flush(); holder.stdin.close()
            self.assertEqual(holder.wait(timeout=2), 0)
            with b.CPULease(self.path) as lease: self.assertEqual(lease.identity, ready['identity'])
        finally:
            if holder is not None:
                try: d.cleanup(holder, holder.pid, started + 9)
                finally:
                    if holder.stdin and not holder.stdin.closed: holder.stdin.close()
                    if holder.stdout: holder.stdout.close()


class ChildRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.journal = self.root / 'children.jsonl'
        self.owned = b.OwnedChildren(self.journal)
        self.process = Mock(pid=54321, returncode=0); self.process.poll.return_value = 0

    def test_capture_survives_journal_write_failure(self):
        self.owned.starting('compiler'); self.journal.unlink()
        with self.assertRaises(FileNotFoundError): self.owned.registered(self.process, 'compiler')
        self.assertEqual(self.owned.children, [('compiler', self.process, 54321)])
        with patch.object(b, 'group_alive', return_value=False): self.assertTrue(self.owned.absence()['passed'])

    def test_journal_alias_is_not_written_and_handle_still_tracked(self):
        foreign = self.root / 'foreign'; foreign.write_text('preserve')
        self.journal.unlink(); self.journal.symlink_to(foreign)
        self.owned.starting('compiler')
        with self.assertRaises(OSError): self.owned.registered(self.process, 'compiler')
        self.assertEqual(foreign.read_text(), 'preserve'); self.assertEqual(len(self.owned.children), 1)

    def test_pending_spawn_and_cleanup_error_each_prevent_release(self):
        self.owned.starting('compiler'); self.assertFalse(self.owned.absence()['passed'])
        self.owned.registered(self.process, 'compiler')
        self.owned.cleanup_failed('compiler', ValueError('fault'))
        with patch.object(b, 'group_alive', return_value=False): self.assertFalse(self.owned.absence()['passed'])

    def test_live_parent_or_descendants_each_prevent_release(self):
        self.owned.starting('compiler'); self.owned.registered(self.process, 'compiler')
        with patch.object(b, 'group_alive', return_value=True): self.assertFalse(self.owned.absence()['passed'])
        self.process.poll.return_value = None
        with patch.object(b, 'group_alive', return_value=False): self.assertFalse(self.owned.absence()['passed'])

    def test_run_child_tracks_before_first_post_Popen_guard_and_receipt(self):
        def popen(*args, **kw):
            b.emit(self.root / 'tool.observed.json', {'pid': 54321, 'ppid': os.getpid(), 'pgid': 54321,
                   'cpu': [30, 30], 'as': [512 * 2**20] * 2, 'nice': 15,
                   'environment': dict(b.ENV, TMPDIR=str(self.root / 'tool.tmp'))})
            return self.process
        calls = []
        def guard():
            calls.append(1)
            if len(calls) > 1: self.assertEqual(self.owned.children[0][2], 54321)
        with patch.object(b.subprocess, 'Popen', side_effect=popen), patch.object(b, 'cleanup'):
            b.run_child(['/usr/bin/ar'], 'tool', self.root, guard, owned=self.owned)
        self.assertEqual(json.loads(self.journal.read_text())['pid'], 54321)

    def test_run_child_cleanup_failure_latches_before_result_write(self):
        def popen(*args, **kw):
            return self.process
        with patch.object(b.subprocess, 'Popen', side_effect=popen), \
             patch.object(b, 'cleanup', side_effect=ValueError('group survives')):
            with self.assertRaises(ValueError):
                b.run_child(['/usr/bin/ar'], 'tool', self.root, Mock(), owned=self.owned)
        self.assertEqual(self.owned.cleanup_faults[0]['name'], 'tool')
        self.assertEqual(self.owned.children[0][2], 54321)


class NumericalSource(unittest.TestCase):
    def test_all_actual_ten_mixed_pairs_are_literal_and_no_unused_formats(self):
        import re
        metadata = json.loads((b.N / 'SELECTED_MAIN_EXPERT_FORMATS_ROOT.json').read_text())
        types = {'IQ2_XXS': 16, 'IQ2_XS': 17, 'IQ3_XXS': 18, 'IQ2_S': 22}
        actual = {(types[r['gate_up_down'][0]], types[r['gate_up_down'][2]]) for r in metadata['combinations']}
        source = (b.N / 'numerical-v2/iq2xs_exact.cpp').read_text()
        block = source.split('selected[] = ', 1)[1].split(';', 1)[0]
        declared = {(int(a), int(c)) for a, c in re.findall(r'\{(\d+),(\d+)\}', block)}
        self.assertEqual(declared, actual); self.assertEqual(len(actual), 10)
        self.assertEqual(sum(r['experts'] for r in metadata['combinations']), 15360)
        self.assertTrue(all(r['gate_up_down'][0] == r['gate_up_down'][1] for r in metadata['combinations']))

    def test_fixture_uses_new_path_and_original_frozen_fixture_is_input(self):
        first, _ = b.observations()
        argv = b.compile_command(first, 'iq2xs_exact.cpp', b.HERE / 'fresh')
        self.assertEqual(argv[-1], str(b.N / 'numerical-v2/iq2xs_exact.cpp'))
        self.assertEqual(b.sha(b.N / 'tests/iq2xs_exact.cpp'), '46054c27abe0538fea5d3c58c0c7585a40ba89c2002a3ca4e7abd98491dc8b6b')

    def test_oracle_and_canary_comparison_preserved_exactly(self):
        old = (b.N / 'tests/iq2xs_exact.cpp').read_text()
        new = (b.N / 'numerical-v2/iq2xs_exact.cpp').read_text()
        self.assertEqual(old.split('void same(', 1)[1].split('void check(', 1)[0],
                         new.split('void same(', 1)[1].split('void check(', 1)[0])
        self.assertEqual(old.split('    constexpr float limit = ', 1)[1].split('    cpu::NativeFmt', 1)[0],
                         new.split('    constexpr float limit = ', 1)[1].split('    cpu::NativeFmt', 1)[0])
        self.assertIn('gg::iq_cpu_gate_up(selected,', new); self.assertIn('gg::iq_cpu_down(selected,', new)
        self.assertIn('cases == (mixed ? 72 : 576)', new)
        self.assertIn('need(one == (expected == "optimized") && multi == (expected == "optimized")', new)


class CASImports(unittest.TestCase):
    """Actual import in a fresh bounded interpreter; no CAS call or socket use."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def test_actual_pinned_transport_and_CAS_import_in_isolated_bounded_child(self):
        import cpu_driver as d
        folder = self.root / 'actual-import'; folder.mkdir()
        # Explicit file import only. Do not add the prose directory to sys.path.
        code = ("import importlib.util,json,os,resource,sys; from pathlib import Path; "
                "assert sys.dont_write_bytecode; "
                "assert resource.getrlimit(resource.RLIMIT_CPU)==(30,30); "
                "assert sys.platform!='linux' or resource.getrlimit(resource.RLIMIT_AS)==(536870912,536870912); "
                "assert os.getpriority(os.PRIO_PROCESS,0)==15; "
                "assert os.environ.get('CUDA_VISIBLE_DEVICES')==''; "
                "before=list(sys.path); "
                "assert 'transport' not in sys.modules and 'prose_measure' not in sys.modules; "
                "p=Path(" + repr(str(b.HERE / 'build.py')) + "); "
                "spec=importlib.util.spec_from_file_location('isolated_build_v3',p); "
                "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                "cas=m.load_cas(); "
                "assert list(sys.path)==before; assert callable(cas.cas_state); "
                "assert cas.transport is sys.modules['transport']; "
                "assert Path(cas.__file__).resolve()==m.D/'prose-speed-v1/prose_measure.py'; "
                "assert Path(cas.transport.__file__).resolve()==m.D/'prose-speed-v1/transport.py'; "
                "assert m.load_cas() is cas; "
                "print(json.dumps(dict(pid=os.getpid(),cas_sha256=m.sha(cas.__file__),"
                "transport_sha256=m.sha(cas.transport.__file__),path_unchanged=True,"
                "CPU=list(resource.getrlimit(resource.RLIMIT_CPU)),"
                "AS=list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform=='linux' else None,"
                "nice=os.getpriority(os.PRIO_PROCESS,0))))")
        result = d.supervise([sys.executable, '-I', '-B', '-c', code], folder,
                             run_seconds=5, wall_seconds=7)
        self.assertEqual((result['returncode'], result['error'], result['cleanup']), (0, None, []))
        value = json.loads((folder / 'child.log').read_text())
        self.assertEqual(value, {'pid': result['pid'], 'cas_sha256': b.CAS_SHA,
            'transport_sha256': b.TRANSPORT_SHA, 'path_unchanged': True, 'CPU': [30, 30],
            'AS': [512 * 2**20] * 2 if sys.platform == 'linux' else None, 'nice': 15})

    def test_missing_transport_refuses_before_CAS_import(self):
        with patch.object(b, 'D', self.root), patch.object(b.importlib.util, 'spec_from_file_location') as spec:
            with self.assertRaisesRegex(ValueError, 'regular'): b.load_cas()
        spec.assert_not_called()

    def test_wrong_transport_bytes_refuse_before_CAS_import(self):
        path = self.root / 'prose-speed-v1/transport.py'; path.parent.mkdir(); path.write_text('# changed')
        with patch.object(b, 'D', self.root), patch.object(b.importlib.util, 'spec_from_file_location') as spec:
            with self.assertRaisesRegex(ValueError, 'Support changed'): b.load_cas()
        spec.assert_not_called()

    def test_foreign_transport_origin_refuses_without_import(self):
        foreign = type('Foreign', (), {'__file__': str(self.root / 'transport.py')})()
        with patch.dict(sys.modules, {'transport': foreign}), \
             patch.object(b.importlib.util, 'spec_from_file_location') as spec:
            with self.assertRaisesRegex(ValueError, 'Foreign support origin'): b.load_cas()
        spec.assert_not_called()

    def test_foreign_module_without_origin_refuses(self):
        with patch.dict(sys.modules, {'transport': object()}), \
             patch.object(b.importlib.util, 'spec_from_file_location') as spec:
            with self.assertRaisesRegex(ValueError, 'Foreign support origin'): b.load_cas()
        spec.assert_not_called()

    def test_cached_CAS_bound_to_different_transport_refuses(self):
        transport = object(); cas = type('CAS', (), {'transport': object()})()
        with patch.object(b, 'load_exact', side_effect=[transport, cas]) as loader:
            with self.assertRaisesRegex(ValueError, 'CAS transport identity'): b.load_cas()
        self.assertEqual([c.args[0] for c in loader.call_args_list], ['transport', 'prose_measure'])




if __name__ == '__main__':
    unittest.main()
