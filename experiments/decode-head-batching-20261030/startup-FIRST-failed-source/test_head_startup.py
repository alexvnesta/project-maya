"""Pure scripted startup controls, including the actual unchanged supervisor."""
import ast
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import head_startup as s

LOCAL_E = Path(__file__).resolve().parents[2]
ORIGINAL = LOCAL_E / 'autonomous-optimization-12h-20261028/chunk4096-v1/activation-v1/activate_chunk4096.py'
OLD = 'a' * 32
INV = 'b' * 32
BIND = {'invocation': INV, 'main_pid': 20, 'native_pid': 21, 'native_start_ticks': 22}


def source_method(name, namespace):
    raw = ORIGINAL.read_bytes()
    if hashlib.sha256(raw).hexdigest() != s.OWNER_SHA:
        raise ValueError('Original qualified supervisor source changed')
    cls = next(x for x in ast.parse(raw).body if isinstance(x, ast.ClassDef) and x.name == 'ChunkProductionHost')
    node = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(ORIGINAL), 'exec'), namespace)
    return namespace[name]


class Capture(unittest.TestCase):
    def host(self, pid=20, state='activating'):
        h = SimpleNamespace(start_invocation=None, start_main_pid=None, start_binding=None,
            restored_pid=None, audit_dir=Path('/owned'))
        h.unit_snapshot = Mock(return_value={'invocation': INV, 'main_pid': pid, 'state': state})
        h.native_snapshot = Mock(return_value=dict(BIND))
        return h
    def test_initial_zero_never_queries_or_claims_native(self):
        h=self.host(0);emit=Mock();s.capture(h,OLD,emit=emit)
        h.native_snapshot.assert_not_called();emit.assert_not_called()
        self.assertEqual(h.start_invocation,INV);self.assertIsNone(h.start_binding)
    def test_positive_stable_owner_captured_once(self):
        h=self.host();emit=Mock();s.capture(h,OLD,emit=emit);s.capture(h,OLD,emit=emit)
        emit.assert_called_once_with(Path('/owned/start-binding.json'),BIND)
        self.assertEqual(h.start_binding,BIND);self.assertEqual(h.restored_pid,21)
    def test_old_or_empty_invocation_is_not_claimed(self):
        for inv in ('',OLD):
            h=self.host();h.unit_snapshot.return_value['invocation']=inv
            s.capture(h,OLD,emit=Mock());h.native_snapshot.assert_not_called();self.assertIsNone(h.start_invocation)
    def test_empty_invocation_after_any_frozen_owner_is_fault(self):
        for name,value in [('start_invocation',INV),('start_main_pid',20),('start_binding',dict(BIND))]:
            h=self.host();setattr(h,name,value);h.unit_snapshot.return_value['invocation']=''
            with self.assertRaises(ValueError):s.capture(h,OLD,emit=Mock())
            h.native_snapshot.assert_not_called()
    def test_reverted_old_invocation_after_any_frozen_owner_is_fault(self):
        for name,value in [('start_invocation',INV),('start_main_pid',20),('start_binding',dict(BIND))]:
            h=self.host();setattr(h,name,value);h.unit_snapshot.return_value['invocation']=OLD
            with self.assertRaises(ValueError):s.capture(h,OLD,emit=Mock())
            h.native_snapshot.assert_not_called()
    def test_invocation_replacement_at_zero_is_fault(self):
        h=self.host(0);h.start_invocation='c'*32
        with self.assertRaises(ValueError):s.capture(h,OLD,emit=Mock())
    def test_positive_main_replacement_is_fault(self):
        h=self.host();h.start_main_pid=19
        with self.assertRaises(ValueError):s.capture(h,OLD,emit=Mock())
        h.native_snapshot.assert_not_called()
    def test_disappearing_observed_main_is_fault(self):
        h=self.host(0);h.start_main_pid=20
        with self.assertRaises(ValueError):s.capture(h,OLD,emit=Mock())
    def test_disappearing_bound_native_is_fault(self):
        h=self.host(0);h.start_binding=dict(BIND)
        with self.assertRaises(ValueError):s.capture(h,OLD,emit=Mock())
    def test_bool_negative_or_float_main_is_fault(self):
        for pid in (False,-1,20.0):
            with self.assertRaises(ValueError):s.capture(self.host(pid),OLD,emit=Mock())
    def test_other_unit_state_does_not_query_native(self):
        h=self.host(state='failed');s.capture(h,OLD,emit=Mock());h.native_snapshot.assert_not_called()
    def test_native_absence_does_not_claim_or_emit(self):
        h=self.host();h.native_snapshot.return_value=None;emit=Mock();s.capture(h,OLD,emit=emit)
        self.assertIsNone(h.start_binding);emit.assert_not_called()
    def test_positive_unit_change_during_snapshot_remains_fault(self):
        h=self.host();h.unit_snapshot.side_effect=[{'invocation':INV,'main_pid':20,'state':'activating'},{'invocation':INV,'main_pid':30,'state':'active'}]
        with self.assertRaises(ValueError):s.capture(h,OLD,emit=Mock())
        self.assertIsNone(h.start_binding)
    def test_native_replacement_never_recaptured(self):
        h=self.host();h.start_binding=dict(BIND,native_pid=99)
        with self.assertRaises(ValueError):s.capture(h,OLD,emit=Mock())
        self.assertEqual(h.start_binding['native_pid'],99)
    def test_native_snapshot_error_is_not_suppressed(self):
        h=self.host();h.native_snapshot.side_effect=ValueError('native fault')
        with self.assertRaisesRegex(ValueError,'native fault'):s.capture(h,OLD,emit=Mock())
    def test_binding_receipt_fault_is_not_suppressed(self):
        h=self.host()
        with self.assertRaises(OSError):s.capture(h,OLD,emit=Mock(side_effect=OSError('receipt')))
    def test_actual_old_method_reproduces_empty_snapshot_transition_failure(self):
        h=self.host();h.unit_snapshot.side_effect=[{'invocation':INV,'main_pid':0,'state':'activating'},{'invocation':INV,'main_pid':20,'state':'activating'}];h.native_snapshot.return_value=None
        old=source_method('capture_pending_start',{'emit':Mock()})
        with self.assertRaisesRegex(ValueError,'Unstable startup invocation'):old(h,OLD)
    def test_new_method_waits_then_captures_same_initial_transition(self):
        h=self.host(0);emit=Mock();s.capture(h,OLD,emit=emit)
        h.unit_snapshot.return_value={'invocation':INV,'main_pid':20,'state':'activating'}
        s.capture(h,OLD,emit=emit);self.assertEqual(h.start_binding,BIND);emit.assert_called_once()


class OriginalSupervisor(unittest.TestCase):
    def run_supervisor(self, mode):
        with tempfile.TemporaryDirectory() as d:
            states=[{'invocation':OLD,'main_pid':0,'state':'inactive'}, {'invocation':INV,'main_pid':0,'state':'activating'}, {'invocation':INV,'main_pid':20,'state':'activating'}]
            h=SimpleNamespace(start_binding=None,start_invocation=None,start_main_pid=None,restored_pid=None,audit_dir=Path(d),start_command_cleanup_error=None)
            h.unit_snapshot=Mock(side_effect=lambda:states.pop(0) if len(states)>1 else states[0])
            h.native_snapshot=Mock(return_value=dict(BIND));emit=Mock()
            h.capture_pending_start=lambda old:s.capture(h,old,emit=emit)
            h.guard_binding=Mock(side_effect=lambda:self.assertEqual(h.start_binding,BIND))
            proc=Mock();proc.poll.side_effect=[None,None,0,0] if mode=='ok' else [None,None,None,None]
            ticks=iter([0,1,1300] if mode=='deadline' else [0,1,2])
            fake=SimpleNamespace(Popen=Mock(return_value=proc),CalledProcessError=RuntimeError,TimeoutExpired=TimeoutError)
            restore=source_method('restore_ds',{'subprocess':fake,'time':SimpleNamespace(monotonic=lambda:next(ticks),sleep=lambda _:None),'sys':sys})
            if mode=='deadline':
                with self.assertRaises(TimeoutError):restore(h)
                proc.terminate.assert_called_once()
            else:
                restore(h);self.assertEqual(h.start_binding,BIND);h.guard_binding.assert_called_once();proc.terminate.assert_not_called()
            self.assertEqual(fake.Popen.call_count,1)
            self.assertEqual(fake.Popen.call_args.args[0],['systemctl','--user','start','deepseek-hosted.service'])
    def test_actual_unchanged_supervisor_one_start_zero_then_positive(self):self.run_supervisor('ok')
    def test_actual_unchanged_1250_deadline_and_owned_CLI_cleanup(self):self.run_supervisor('deadline')


class Factory(unittest.TestCase):
    def test_exact_owner_wrapper_preserves_other_methods(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'owner.py';p.write_text('class Base:\n def capture_pending_start(self,x): pass\n def restore_ds(self): pass\n def guard_binding(self): pass\n def native_snapshot(self,x): pass\n def unit_snapshot(self): pass\n def target_identity(self): return "unchanged"\n')
            ns={};exec(compile(p.read_text(),str(p),'exec'),ns)
            a=SimpleNamespace(__file__=str(p),ChunkProductionHost=ns['Base'],emit=Mock())
            with patch.object(s,'OWNER',p),patch.object(s,'OWNER_SHA',hashlib.sha256(p.read_bytes()).hexdigest()):
                cls=s.guarded_host(a);self.assertEqual(cls().target_identity(),'unchanged');self.assertIs(cls.restore_ds,a.ChunkProductionHost.restore_ds)
                p.write_text('changed')
                with self.assertRaises(ValueError):s.guarded_host(a)
    def test_foreign_module_refused_before_reading_owner(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('no read')):
            with self.assertRaises(ValueError):s.guarded_host(SimpleNamespace(__file__='/foreign.py'))


if __name__=='__main__':unittest.main()
