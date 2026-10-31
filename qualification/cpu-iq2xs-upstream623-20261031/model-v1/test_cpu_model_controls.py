"""Prospective actual API exit, private descendants and fence cleanup controls."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import cpu_model_controls as c


class ActualExit(unittest.TestCase):
    def test_actual_handle_zero_and_cleanup_saved(self):
        proc=Mock(pid=123);proc.poll.return_value=0;proc.wait.return_value=0
        row={'passed':True,'server_pid':123,'server_returncode':0}
        emit=Mock();old=SimpleNamespace(stop_server=Mock(return_value=row))
        result=c.stop_api(old,proc,Path('/owned'),emit)
        self.assertTrue(result['passed']);proc.wait.assert_called_once_with(timeout=0)
        emit.assert_called_once();self.assertEqual(emit.call_args.args[1]['actual_Popen_returncode'],0)
    def test_nonzero_or_bool_or_unwaited_actual_exit_never_accepted(self):
        for rc in (1,False,None):
            proc=Mock(pid=123);proc.poll.return_value=rc;proc.wait.return_value=rc
            emit=Mock();old=SimpleNamespace(stop_server=Mock(return_value={'passed':True,'server_pid':123,'server_returncode':0}))
            with self.assertRaises(ValueError):c.stop_api(old,proc,Path('/owned'),emit)
            self.assertFalse(emit.call_args.args[1]['passed'])
    def test_cleanup_primary_survives_exit_receipt_failure(self):
        proc=Mock(pid=123);proc.poll.return_value=7
        old=SimpleNamespace(stop_server=Mock(side_effect=RuntimeError('native cleanup')))
        with self.assertRaisesRegex(RuntimeError,'native cleanup') as exc:
            c.stop_api(old,proc,Path('/owned'),Mock(side_effect=OSError('receipt')))
        self.assertIn('receipt',exc.exception.__notes__[0])
    def test_actual_server_pid_must_match(self):
        proc=Mock(pid=123);proc.poll.return_value=0;proc.wait.return_value=0
        old=SimpleNamespace(stop_server=Mock(return_value={'passed':True,'server_pid':124,'server_returncode':0}))
        with self.assertRaises(ValueError):c.stop_api(old,proc,Path('/owned'),Mock())


class Descendants(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();(self.root/'cgroup.procs').write_text('12\n')
        self.record={'cgroup':str(self.root),'unit_before':{'ControlGroup':'/owned'}}
    def call(self):
        with patch.object(c.fence,'private_children_closed',return_value=True),patch.object(c,'own_ancestry',return_value={12}),patch.object(c.os,'killpg',side_effect=ProcessLookupError):
            return c.private_closed(self.root,[Mock(pid=123)],self.record)
    def test_only_live_phase_ancestors_permitted(self):self.assertTrue(self.call()['passed'])
    def test_unknown_descendant_blocks_fence_relaxation(self):
        (self.root/'cgroup.procs').write_text('12\n99\n')
        with self.assertRaisesRegex(ValueError,'Unregistered'):self.call()
    def test_existing_subgroup_or_symlink_blocks(self):
        sub=self.root/'child';sub.mkdir()
        with self.assertRaisesRegex(ValueError,'Nested'):self.call()
        sub.rmdir();sub.symlink_to('/foreign')
        with self.assertRaisesRegex(ValueError,'Nested'):self.call()
    def test_subgroup_appearing_at_second_enumeration_blocks(self):
        original=Path.iterdir;calls=[]
        def late(path):
            if path==self.root:
                calls.append(1)
                if len(calls)==2:(self.root/'late').mkdir()
            return original(path)
        with patch.object(Path,'iterdir',late):
            with self.assertRaisesRegex(ValueError,'Nested'):self.call()
        self.assertEqual(len(calls),2)
    def test_api_group_survival_blocks(self):
        with patch.object(c.fence,'private_children_closed',return_value=True),patch.object(c.os,'killpg',return_value=None):
            with self.assertRaisesRegex(ValueError,'group still'):c.private_closed(self.root,[Mock(pid=123)],self.record)
    def test_private_native_survival_blocks(self):
        with patch.object(c.fence,'private_children_closed',return_value=False):
            with self.assertRaises(ValueError):c.private_closed(self.root,[],self.record)
    def test_fence_never_restored_after_unknown_descendant(self):
        restore=Mock()
        with patch.object(c.fence,'install_private_fence',return_value=self.record),patch.object(c,'private_closed',side_effect=ValueError('descendant')),patch.object(c.fence,'restore_private_fence',restore):
            with self.assertRaisesRegex(ValueError,'descendant'):
                with c.fenced_phase(self.root):pass
        restore.assert_not_called()
    def test_body_fault_preserved_when_closure_also_fails(self):
        with patch.object(c.fence,'install_private_fence',return_value=self.record),patch.object(c,'private_closed',side_effect=ValueError('descendant')):
            with self.assertRaisesRegex(RuntimeError,'primary') as exc:
                with c.fenced_phase(self.root):raise RuntimeError('primary')
        self.assertIn('descendant',exc.exception.__notes__[0])
    def test_success_saves_closure_before_restoring_properties(self):
        events=[]
        with patch.object(c.fence,'install_private_fence',return_value=self.record),patch.object(c,'private_closed',return_value={'passed':True}),patch.object(c.fence.runtime,'emit',side_effect=lambda *a:events.append('receipt')),patch.object(c.fence,'restore_private_fence',side_effect=lambda *a,**k:events.append('restore')):
            with c.fenced_phase(self.root):events.append('body')
        self.assertEqual(events,['body','receipt','restore'])
    def test_exact_phase_ancestry_and_cycles(self):
        proc=self.root/'proc';proc.mkdir()
        for pid,parent in ((12,13),(13,1)):
            p=proc/str(pid);p.mkdir();(p/'cgroup').write_text('0::/owned\n');(p/'stat').write_text(f'{pid} (phase name) S {parent} 0 0')
        self.assertEqual(c.own_ancestry('/owned',proc=proc,current=12),{12,13})
        (proc/'13/stat').write_text('13 (phase) S 12 0 0')
        with self.assertRaisesRegex(ValueError,'cycle'):c.own_ancestry('/owned',proc=proc,current=12)
