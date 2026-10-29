"""Mocked supervisor controls; never start a disassembler, compiler or service."""
from contextlib import ExitStack
import io
import json
from pathlib import Path
import signal
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import static_diagnostic as s


class TemporaryFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()


class Files(TemporaryFiles):
    def test_exact_six_commands_no_compiler_or_execution(self):
        plan = s.commands()
        self.assertEqual([n for n, _ in plan], ['old-sass', 'old-resources', 'old-elf',
                         'candidate-sass', 'candidate-resources', 'candidate-elf'])
        for _, argv in plan:
            self.assertEqual(argv[:3], [str(s.TOOL), '--gpu-architecture', 'sm_80'])
            self.assertIn(argv[3], ['--dump-sass', '--dump-resource-usage', '--dump-elf'])
            self.assertEqual(len(argv), 5)

    def test_fresh_leaf_rejects_residue_and_dangling_alias(self):
        leaf = self.root / 'out'
        s.fresh_leaf(leaf)
        leaf.mkdir()
        with self.assertRaises(ValueError): s.fresh_leaf(leaf)
        alias = self.root / 'alias'; alias.symlink_to(self.root / 'missing')
        with self.assertRaises(ValueError): s.fresh_leaf(alias)

    def test_root_first_rejects_ancestor_alias(self):
        (self.root / 'real').mkdir()
        (self.root / 'alias').symlink_to(self.root / 'real', target_is_directory=True)
        with self.assertRaises(ValueError): s.real_directory(self.root / 'alias')

    def test_receipt_exclusive_no_overwrite(self):
        f = self.root / 'receipt.json'; s.emit_new(f, {'original': True})
        with self.assertRaises(FileExistsError): s.emit_new(f, {'original': False})
        self.assertEqual(json.loads(f.read_text()), {'original': True})

    def test_tool_alias_and_object_content_custody(self):
        tool = self.root / 'tool'; tool.write_bytes(b'tool')
        alias = self.root / 'alias'; alias.symlink_to(tool)
        obj = self.root / 'object'; obj.write_bytes(b'original')
        with patch.multiple(s, TOOL=alias, TOOL_REAL=tool, TOOL_SHA=s.sha(tool),
                            OBJECTS={'old': (obj, s.sha(obj))}):
            s.check_inputs()
            obj.write_bytes(b'changed')
            with self.assertRaises(ValueError): s.check_inputs()

    def test_tool_alias_retarget_rejected_even_same_content(self):
        one = self.root / 'one'; two = self.root / 'two'
        one.write_bytes(b'tool'); two.write_bytes(b'tool')
        alias = self.root / 'alias'; alias.symlink_to(two)
        with patch.multiple(s, TOOL=alias, TOOL_REAL=one, TOOL_SHA=s.sha(one), OBJECTS={}):
            with self.assertRaises(ValueError): s.check_inputs()

    def test_object_symlink_rejected(self):
        tool = self.root / 'tool'; tool.write_bytes(b'tool')
        alias = self.root / 'obj'; alias.symlink_to(tool)
        with patch.multiple(s, TOOL=tool, TOOL_REAL=tool, TOOL_SHA=s.sha(tool),
                            OBJECTS={'old': (alias, s.sha(tool))}):
            with self.assertRaises(ValueError): s.check_inputs()

    def test_output_exact_boundary_and_one_byte_over(self):
        counts = {'stdout': 0, 'stderr': 0}; total = [0]; out = io.BytesIO()
        with patch.dict(s.STREAM_LIMITS, {'stdout': 3, 'stderr': 1}), patch.object(s, 'TOTAL_LIMIT', 4):
            s.append_bounded(out, b'abc', 'stdout', counts, total)
            with self.assertRaises(ValueError): s.append_bounded(out, b'd', 'stdout', counts, total)
        self.assertEqual(out.getvalue(), b'abc'); self.assertEqual(total, [3])

    def test_stderr_and_aggregate_bounds_preserve_prefix(self):
        counts = {'stdout': 0, 'stderr': 0}; total = [2]; out = io.BytesIO()
        with patch.dict(s.STREAM_LIMITS, {'stdout': 9, 'stderr': 1}), patch.object(s, 'TOTAL_LIMIT', 3):
            with self.assertRaises(ValueError): s.append_bounded(out, b'ab', 'stderr', counts, total)
        self.assertEqual(out.getvalue(), b'a'); self.assertEqual(total, [3])

    def test_short_output_write_is_failure(self):
        out = Mock(); out.write.return_value = 0
        with self.assertRaises(ValueError):
            s.append_bounded(out, b'x', 'stdout', {'stdout': 0, 'stderr': 0}, [0])

    def test_child_limits_linux_exact_no_fsize_or_gpu(self):
        with patch.object(s.sys, 'platform', 'linux'), patch.object(s.resource, 'setrlimit') as limits, patch.object(s.os, 'nice') as nice:
            s.child_limits()
        self.assertEqual(limits.call_args_list[0].args, (s.resource.RLIMIT_CPU, (30, 30)))
        self.assertEqual(limits.call_args_list[1].args, (s.resource.RLIMIT_AS, (512 * 2**20,) * 2))
        self.assertEqual(limits.call_count, 2); nice.assert_called_once_with(15)


class Pipe:
    def __init__(self, fd): self.fd = fd; self.closed = False
    def fileno(self): return self.fd
    def close(self): self.closed = True


class FakeSelector:
    def __init__(self): self.mapping = {}; self.closed = False
    def register(self, pipe, event, data):
        self.mapping[pipe] = SimpleNamespace(fileobj=pipe, data=data)
    def get_map(self): return self.mapping
    def select(self, timeout): return [(k, 1) for k in list(self.mapping.values())]
    def unregister(self, pipe): self.mapping.pop(pipe)
    def close(self): self.closed = True


class Children(TemporaryFiles):
    """Actual run_child with mocked OS/process edges."""
    def call(self, *, admission=None, wait=None, read=None, check=None, clock=None, selector_error=None,
             cleanup_error=None, group_survives=False):
        child = Mock(pid=98765432, stdout=Pipe(101), stderr=Pipe(102))
        child.wait.side_effect = wait
        child.wait.return_value = 0
        child.poll.return_value = -15
        chunks = {101: [b'assembly\n', b''], 102: [b'']}
        def reading(fd, size): return chunks[fd].pop(0)
        self.child = child
        with ExitStack() as stack:
            self.spawn = stack.enter_context(patch.object(s.subprocess, 'Popen', return_value=child))
            stack.enter_context(patch.object(s.os, 'set_blocking'))
            stack.enter_context(patch.object(s.os, 'read', side_effect=read or reading))
            stack.enter_context(patch.object(s.selectors, 'DefaultSelector', side_effect=selector_error or FakeSelector))
            self.input_check = stack.enter_context(patch.object(s, 'check_inputs', side_effect=check))
            stack.enter_context(patch.object(s, 'group_alive', return_value=group_survives))
            self.clean = stack.enter_context(patch.object(s, 'cleanup', side_effect=cleanup_error,
                                                         return_value={'complete': True, 'errors': []}))
            if clock is not None: stack.enter_context(patch.object(s.time, 'monotonic', side_effect=clock))
            return s.run_child(*s.commands()[0], self.root, admission or Mock(), [0])

    def test_actual_child_success_exact_env_newsession_and_logs(self):
        row = self.call()
        self.assertEqual(row['returncode'], 0); self.clean.assert_not_called()
        kwargs = self.spawn.call_args.kwargs
        self.assertTrue(kwargs['start_new_session'])
        self.assertIs(kwargs['preexec_fn'], s.child_limits)
        self.assertEqual(kwargs['env']['CUDA_VISIBLE_DEVICES'], '')
        self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual((self.root / 'old-sass.stdout').read_bytes(), b'assembly\n')

    def test_pipe_eof_waits_remaining_work_with_guards(self):
        admission = Mock()
        self.call(wait=[subprocess.TimeoutExpired('mock', 1), 0], admission=admission)
        self.assertEqual(self.child.wait.call_count, 2)
        self.assertGreaterEqual(admission.call_count, 5)

    def test_busy_before_spawn_no_process(self):
        with self.assertRaisesRegex(ValueError, 'busy'):
            self.call(admission=Mock(side_effect=ValueError('busy')))
        self.spawn.assert_not_called(); self.clean.assert_not_called()

    def test_busy_after_spawn_cleans_only_owned_process(self):
        with self.assertRaisesRegex(ValueError, 'busy'):
            self.call(admission=Mock(side_effect=[None, ValueError('busy')]))
        self.clean.assert_called_once_with(self.child)

    def test_busy_post_guard_skips_input_hash_and_preserves_primary(self):
        admission = Mock(side_effect=[None, ValueError('primary busy'), ValueError('private phase')])
        with self.assertRaisesRegex(ValueError, 'primary busy'):
            self.call(admission=admission)
        self.assertEqual(self.input_check.call_count, 1)
        self.clean.assert_called_once_with(self.child)
        row = json.loads((self.root / 'old-sass.json').read_text())
        self.assertEqual(row['post_input_custody'], 'POST_CUSTODY_UNVERIFIED_HOLD')
        self.assertIn('private phase', str(row['secondary_notes']))

    def test_wall_timeout_cleans_owned_group(self):
        with self.assertRaisesRegex(ValueError, 'WALL_TIMEOUT'):
            self.call(clock=[0, 91])
        self.clean.assert_called_once_with(self.child)

    def test_keyboardinterrupt_retains_primary_and_cleanup_receipt(self):
        with self.assertRaises(KeyboardInterrupt):
            self.call(admission=Mock(side_effect=[None, KeyboardInterrupt('interrupt')]))
        row = json.loads((self.root / 'old-sass.json').read_text())
        self.assertIn('KeyboardInterrupt', row['error']); self.assertTrue(row['owned_cleanup']['complete'])

    def test_stdout_overflow_bounded_and_terminal_hold(self):
        with patch.dict(s.STREAM_LIMITS, {'stdout': 3, 'stderr': 1}):
            with self.assertRaisesRegex(ValueError, 'OUTPUT_OVERFLOW'): self.call()
        self.assertEqual((self.root / 'old-sass.stdout').read_bytes(), b'ass')
        self.clean.assert_called_once_with(self.child)

    def test_nonzero_exit_stops_child(self):
        with self.assertRaisesRegex(ValueError, 'Disassembler failed'): self.call(wait=[7])
        self.clean.assert_called_once_with(self.child)

    def test_post_input_change_cleans_and_preserves(self):
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.call(check=[None, ValueError('changed')])
        self.assertIn('changed', json.loads((self.root / 'old-sass.json').read_text())['error'])
        self.assertEqual(self.input_check.call_count, 2)

    def test_selector_creation_failure_after_spawn_is_owned_cleanup(self):
        with self.assertRaisesRegex(OSError, 'selector'):
            self.call(selector_error=OSError('selector'))
        self.clean.assert_called_once_with(self.child)

    def test_read_fault_cleanup(self):
        with self.assertRaisesRegex(OSError, 'read'):
            self.call(read=Mock(side_effect=OSError('read')))
        self.clean.assert_called_once_with(self.child)

    def test_receipt_failure_preserves_original_error(self):
        with patch.object(s, 'emit_new', side_effect=OSError('receipt')):
            with self.assertRaises(ValueError) as caught:
                self.call(admission=Mock(side_effect=[None, ValueError('busy')]))
        self.assertIn('busy', str(caught.exception))
        self.assertIn('receipt', str(caught.exception.__notes__))

    def test_unplanned_command_refused_before_process(self):
        with patch.object(s.subprocess, 'Popen') as spawn:
            with self.assertRaises(ValueError): s.run_child('new', ['nvcc'], self.root, Mock(), [0])
        spawn.assert_not_called()

    def test_cleanup_fault_does_not_mask_primary(self):
        with self.assertRaisesRegex(ValueError, 'busy') as caught:
            self.call(admission=Mock(side_effect=[None,ValueError('busy')]),cleanup_error=OSError('cleanup'))
        self.assertIn('cleanup', str(caught.exception.__notes__))

    def test_surviving_descendant_blocks_clean_exit(self):
        with self.assertRaisesRegex(ValueError, 'descendant'):
            self.call(group_survives=True)
        self.clean.assert_called_once_with(self.child)


class Cleanup(unittest.TestCase):
    def test_TERM_then_gone_does_not_KILL_foreign(self):
        child = Mock(pid=1234)
        with patch.object(s.os, 'killpg') as kill, patch.object(s, 'group_alive', return_value=False):
            result = s.cleanup(child)
        kill.assert_called_once_with(1234, signal.SIGTERM)
        self.assertTrue(result['complete'])

    def test_primary_wait_and_signal_errors_retained_then_KILL(self):
        child = Mock(pid=1234); child.wait.side_effect = [subprocess.TimeoutExpired('x', 3), 0]
        with patch.object(s.os, 'killpg', side_effect=[PermissionError('term'), None]) as kill, \
             patch.object(s, 'group_alive', side_effect=[True, False]), \
             patch.object(s.time, 'monotonic', side_effect=[0, 4, 4]):
            result = s.cleanup(child)
        self.assertEqual([c.args[1] for c in kill.call_args_list], [signal.SIGTERM, signal.SIGKILL])
        self.assertEqual(len(result['errors']), 2); self.assertTrue(result['complete'])

    def test_unresolved_owned_group_marked_incomplete(self):
        with patch.object(s.os, 'killpg'), patch.object(s, 'group_alive', return_value=True), \
             patch.object(s.time, 'monotonic', side_effect=[0, 4, 4, 10]):
            result = s.cleanup(Mock(pid=1234))
        self.assertFalse(result['complete'])


class Qualification(TemporaryFiles):
    def setUp(self):
        super().setUp()
        self.here = self.root / 'diagnostic'; self.here.mkdir()
        self.m = self.root / 'model'; self.m.mkdir()
        for name in s.SOURCES: (self.here/name).write_text('# mock source '+name)
        for name in ['imma_model_runtime.py', 'imma_config.py', 'dependency.py']:
            (self.m/name).write_text('# mock '+name)
        (self.m/'offline-sass-tool-FIRST').mkdir()
        (self.m/'offline-sass-tool-FIRST/receipt.json').write_text('{}')
        prior = {'files': {str(self.m/'dependency.py'): s.sha(self.m/'dependency.py')}}
        (self.m/'numerical-qualification.json').write_text(json.dumps(prior))
        self.sources = {name:s.sha(self.here/name) for name in s.SOURCES}
        self.ids = ['test_static_diagnostic.Mock.test_one', 'test_static_diagnostic.Mock.test_two']
        for label in ['darwin','linux']:
            folder=self.here/('CPU-FIRST-'+label);folder.mkdir()
            (folder/'receipt.json').write_text(json.dumps({'passed':True,'source_sha256':self.sources,
                'test_ids':self.ids,'controls':2,'GPU_execution':False,'compiler_execution':False}))
            (folder/'child.json').write_text(json.dumps({'returncode':0,'CPU_s':30,'wall_s':90,'nice':15,
                'CUDA_hidden':True,'Linux_AS_MiB':512 if label=='linux' else None}))
            (folder/'child.log').write_text('mock proof')
        self.q={'source_manually_reviewed':True,'CPU_both_hosts_passed':True,
                'source_sha256':self.sources,'test_ids':self.ids,
                'files':{str(f):s.sha(f) for f in self.root.rglob('*') if f.is_file()}}

    def call(self):
        path=self.here/'qualification.json';path.write_text(json.dumps(self.q))
        with patch.multiple(s,HERE=self.here,M=self.m,
                NUMERIC_Q=s.sha(self.m/'numerical-qualification.json'),
                RUNTIME_SHA=s.sha(self.m/'imma_model_runtime.py'),CONFIG_SHA=s.sha(self.m/'imma_config.py')):
            return s.qualification(s.sha(path))

    def repin(self,path): self.q['files'][str(path)]=s.sha(path)

    def test_exact_source_closure_and_cpu_proof(self):
        self.assertEqual(self.call()['test_ids'], self.ids)

    def test_changed_source_rejected(self):
        (self.here/s.SOURCES[0]).write_text('changed')
        with self.assertRaises(ValueError): self.call()

    def test_missing_dependency_pin_rejected(self):
        self.q['files'].pop(str(self.m/'dependency.py'))
        with self.assertRaises(ValueError): self.call()

    def test_changed_inherited_dependency_rejected(self):
        (self.m/'dependency.py').write_text('changed')
        with self.assertRaises(ValueError): self.call()

    def test_cpu_wrong_ids_rejected_even_repinned(self):
        f=self.here/'CPU-FIRST-linux/receipt.json';d=json.loads(f.read_text())
        d['test_ids']=list(reversed(self.ids));f.write_text(json.dumps(d));self.repin(f)
        with self.assertRaises(ValueError):self.call()

    def test_cpu_wrong_or_boolean_limits_rejected(self):
        f=self.here/'CPU-FIRST-linux/child.json';d=json.loads(f.read_text());d['returncode']=False
        f.write_text(json.dumps(d));self.repin(f)
        with self.assertRaises(ValueError):self.call()
        d['returncode']=0;d['Linux_AS_MiB']=1024;f.write_text(json.dumps(d));self.repin(f)
        with self.assertRaises(ValueError):self.call()

    def test_missing_raw_log_pin_rejected(self):
        self.q['files'].pop(str(self.here/'CPU-FIRST-darwin/child.log'))
        with self.assertRaises(ValueError):self.call()

    def test_bad_qualification_digest_rejected_before_inputs(self):
        f=self.here/'qualification.json';f.write_text('{}')
        with patch.object(s,'HERE',self.here):
            with self.assertRaises(ValueError):s.qualification('0'*64)

    def test_foreign_same_name_import_refused(self):
        with patch.multiple(s,M=self.m,RUNTIME_SHA=s.sha(self.m/'imma_model_runtime.py'),
                            CONFIG_SHA=s.sha(self.m/'imma_config.py')), \
             patch.dict(s.sys.modules,{'imma_model_runtime':SimpleNamespace(__file__='/foreign/runtime.py')}), \
             patch.object(s.importlib,'import_module') as load:
            with self.assertRaises(ValueError):s.load_support()
        load.assert_not_called()

    def test_load_support_changed_source_before_import(self):
        with patch.multiple(s,M=self.m,RUNTIME_SHA='0'*64), \
             patch.object(s.importlib,'import_module') as load:
            with self.assertRaises(ValueError):s.load_support()
        load.assert_not_called()


class Coordination(TemporaryFiles):
    def setUp(self):
        super().setUp()
        self.state = self.root / 'STATE.json'
        self.initial = {'unrelated': {'keep': 1}, 'active_cpu_build': False}
        self.state.write_text(json.dumps(self.initial))
        self.binding = {'invocation': 'a' * 32, 'main_pid': 1, 'native_pid': 2, 'native_start_ticks': 3}
        self.runtime = SimpleNamespace(PHASE_KEYS=('active_cpu_build', 'private_window'),
                                       current_binding=lambda state: self.binding)
        self.host = Mock(); self.host.idle.return_value = True
        self.a = SimpleNamespace(emit=lambda path, value: path.write_text(json.dumps(value)))

    def run_execute(self, child=None, guard=None, emit=None):
        with patch.multiple(s, HERE=self.root, E=self.root), \
             patch.object(s, 'guard', side_effect=guard or (lambda *args: json.loads(self.state.read_text()))), \
             patch.object(s, 'check_inputs'), patch.object(s, 'sha', return_value='q'), \
             patch.object(s, 'run_child', side_effect=child or (lambda *args: {'returncode': 0})) as call:
            self.child_call = call
            if emit is not None: self.a.emit = emit
            return s.execute('q', self.runtime, self.a, self.host, self.binding)

    def test_actual_guard_busy_root_and_other_phase(self):
        with patch.object(s, 'E', self.root), patch.object(s.shutil, 'disk_usage', return_value=SimpleNamespace(free=132*2**30)):
            self.assertEqual(s.guard(self.runtime, self.host, self.binding), self.initial)
            self.host.idle.return_value = False
            with self.assertRaises(ValueError): s.guard(self.runtime, self.host, self.binding)
            self.host.idle.return_value = True
            self.state.write_text(json.dumps({**self.initial, 'private_window': True}))
            with self.assertRaises(ValueError): s.guard(self.runtime, self.host, self.binding)
        self.assertEqual(self.host.guard_binding.call_count, 1)

    def test_actual_guard_root_before_reservation(self):
        with patch.object(s, 'E', self.root), patch.object(s.shutil, 'disk_usage', return_value=SimpleNamespace(free=132*2**30-1)):
            with self.assertRaisesRegex(ValueError, 'Root132'):
                s.guard(self.runtime, self.host, self.binding)
        self.assertEqual(json.loads(self.state.read_text()), self.initial)

    def test_actual_guard_changed_owner(self):
        with patch.object(s, 'E', self.root):
            with self.assertRaisesRegex(ValueError, 'owner'):
                s.guard(self.runtime, self.host, {**self.binding, 'native_pid': 99})
        self.host.idle.assert_not_called()

    def test_actual_guard_foreign_reservation_untouched(self):
        state={**self.initial,'active_cpu_build':{'controller_pid':99}}
        self.state.write_text(json.dumps(state))
        with patch.object(s,'E',self.root):
            with self.assertRaisesRegex(ValueError,'reservation'):
                s.guard(self.runtime,self.host,self.binding,{'controller_pid':1})
        self.host.idle.assert_not_called()
        self.assertEqual(json.loads(self.state.read_text()),state)

    def test_six_serial_children_and_own_reservation_release(self):
        seen = []
        def child(name, argv, out, admission, total):
            seen.append(name)
            self.assertEqual(json.loads(self.state.read_text())['active_cpu_build']['controller_pid'], s.os.getpid())
            return {'returncode': 0}
        result = self.run_execute(child=child)
        self.assertEqual(seen, [n for n, _ in s.commands()])
        self.assertEqual(json.loads(self.state.read_text()), self.initial)
        self.assertEqual(result['numerical_gate'], 'HOLD_TOKEN_PATH_DIFFERS')

    def test_first_child_fault_no_next_and_release(self):
        with self.assertRaisesRegex(ValueError, 'fault'):
            self.run_execute(child=Mock(side_effect=ValueError('fault')))
        self.assertEqual(self.child_call.call_count, 1)
        self.assertEqual(json.loads(self.state.read_text()), self.initial)
        self.assertEqual(json.loads((self.root/'output-FIRST/receipt.json').read_text())['status'], 'HOLD')

    def test_preflight_busy_no_output_or_state_mutation(self):
        with self.assertRaisesRegex(ValueError, 'busy'):
            self.run_execute(guard=Mock(side_effect=ValueError('busy')))
        self.assertFalse((self.root/'output-FIRST').exists())
        self.assertEqual(json.loads(self.state.read_text()), self.initial)

    def test_existing_output_no_adoption(self):
        (self.root/'output-FIRST').mkdir()
        with self.assertRaises(ValueError): self.run_execute()
        self.child_call.assert_not_called()
        self.assertFalse((self.root/'output-FIRST/receipt.json').exists())
        self.assertEqual(json.loads(self.state.read_text()), self.initial)

    def test_foreign_reservation_preserved_and_reported(self):
        foreign = {'controller_pid': 77, 'mode': 'other'}
        def child(*args):
            self.state.write_text(json.dumps({**self.initial, 'active_cpu_build': foreign}))
            raise ValueError('primary')
        with self.assertRaisesRegex(ValueError, 'primary') as caught: self.run_execute(child=child)
        self.assertIn('ownership changed', str(caught.exception.__notes__))
        self.assertEqual(json.loads(self.state.read_text())['active_cpu_build'], foreign)

    def test_own_release_failure_retained(self):
        def emit(path, value):
            if not value.get('active_cpu_build'): raise OSError('release')
            path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'primary') as caught:
            self.run_execute(child=Mock(side_effect=ValueError('primary')), emit=emit)
        self.assertIn('release', str(caught.exception.__notes__))

    def test_reservation_write_fault_after_commit_still_releases_own(self):
        count=[0]
        def emit(path,value):
            path.write_text(json.dumps(value));count[0]+=1
            if count[0]==1:raise OSError('reservation receipt')
        with self.assertRaisesRegex(OSError,'reservation receipt'):
            self.run_execute(emit=emit)
        self.assertEqual(json.loads(self.state.read_text()),self.initial)
        self.assertFalse((self.root/'output-FIRST').exists())

    def test_unobserved_release_blocks_success(self):
        def emit(path, value):
            if value.get('active_cpu_build'): path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'release not observed'):
            self.run_execute(emit=emit)

    def test_main_idle_before_heavy_qualification(self):
        events = []
        with patch.multiple(s, HERE=self.root, EXPECTED_HERE=self.root), \
             patch.object(s.sys, 'platform', 'linux'), \
             patch.object(s.sys, 'argv', ['static_diagnostic.py', '--qualification-sha256', 'q']), \
             patch.object(s, 'load_support', return_value=(self.runtime,self.a,self.host,self.binding)), \
             patch.object(s, 'guard', side_effect=lambda *a:events.append('guard')), \
             patch.object(s, 'qualification', side_effect=lambda *a:events.append('qualification')), \
             patch.object(s, 'execute', side_effect=lambda *a:events.append('execute')):
            s.main()
        self.assertEqual(events, ['guard','qualification','guard','execute'])

    def test_main_busy_never_hashes_full_qualification(self):
        with patch.multiple(s,HERE=self.root,EXPECTED_HERE=self.root), \
             patch.object(s.sys,'platform','linux'), \
             patch.object(s.sys,'argv',['static_diagnostic.py','--qualification-sha256','q']), \
             patch.object(s,'load_support',return_value=(self.runtime,self.a,self.host,self.binding)), \
             patch.object(s,'guard',side_effect=ValueError('busy')), \
             patch.object(s,'qualification') as qualify, patch.object(s,'execute') as execute:
            with self.assertRaisesRegex(ValueError,'busy'):s.main()
        qualify.assert_not_called();execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
