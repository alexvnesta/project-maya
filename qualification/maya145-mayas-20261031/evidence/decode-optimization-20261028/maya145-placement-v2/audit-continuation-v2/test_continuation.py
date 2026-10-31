"""Pure controls of the narrow saved-receipt continuation. No native/service use."""
import copy
import json
from pathlib import Path
import types
import unittest
from unittest.mock import Mock
import continuation as c

class Continuation(unittest.TestCase):
    def test_exact_first_failure_preserved(self):
        c.failure_contract({'returncode':1,'error':"ValueError('Child nonzero')",'cleanup':[]},'current_audit.py rec.bytes(metadata / name) ValueError: One regular evidence file')
    def test_wrong_or_boolean_exit_and_unclean_failure_refused(self):
        for field,value in [('returncode',True),('returncode',0),('error',None),('cleanup',['fault'])]:
            row={'returncode':1,'error':"ValueError('Child nonzero')",'cleanup':[]};row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):c.failure_contract(row,'current_audit.py rec.bytes(metadata / name) ValueError: One regular evidence file')
    def test_undetected_native_or_other_fault_never_continued(self):
        for log in ('native CUDA error','current_audit.py different failure',''):
            with self.assertRaises(ValueError):c.failure_contract({'returncode':1,'error':"ValueError('Child nonzero')",'cleanup':[]},log)
    def test_current_producer_consumer_uses_selected_not_candidate(self):
        baseline=types.SimpleNamespace(BASE_NATIVE=c.SELECTED);r=types.SimpleNamespace(Q=Path('/q'),original_module=Mock(return_value=baseline));lc=types.SimpleNamespace(restoration_contract=Mock(return_value={'passed':True}));qa=types.SimpleNamespace(dependency=Mock(return_value=lc));saved=object();rec=object()
        self.assertEqual(c.restoration({},Path('/m'),None,r,saved,qa,{},rec),{'passed':True})
        self.assertIs(lc.restoration_contract.call_args.kwargs['config'],baseline);self.assertIs(lc.restoration_contract.call_args.kwargs['recorder'],rec);qa.dependency.assert_called_once_with('lc_audit',Path('/q/long-cold-v1/lc_audit.py'),{})
    def test_candidate_identity_cannot_be_used_for_baseline(self):
        r=types.SimpleNamespace(original_module=Mock(return_value=types.SimpleNamespace(BASE_NATIVE='adff')),Q=Path('/q'));qa=types.SimpleNamespace(dependency=Mock())
        with self.assertRaises(ValueError):c.restoration({},Path('/m'),None,r,None,qa,{},None)
        qa.dependency.assert_not_called()
    def test_original_producer_contract_no_max_tokens_override(self):
        import importlib.util
        path=c.HERE.parents[1]/'maya-s-comparison-v1/long-cold-v1/lc_audit.py';spec=importlib.util.spec_from_file_location('pure_actual_public_contract',path);lc=importlib.util.module_from_spec(spec);spec.loader.exec_module(lc)
        self.assertNotIn('max_tokens',lc.PUBLIC_DEFAULT_REQUEST);self.assertEqual(lc.PUBLIC_DEFAULT_REQUEST['reasoning_effort'],'none');self.assertEqual(lc.PUBLIC_DEFAULT_REQUEST['model'],'deepseek-v4.1-flash-iq2-xs')

    def test_downstream_window_is_bound_to_recorded_canonical_phase(self):
        runtime=types.SimpleNamespace(R=Path('/r'))
        self.assertEqual(c.window_path({'window':'/r/windows/20261031T182135Z.json'},runtime),Path('/r/windows/20261031T182135Z.json'))
        for path in ('/other/windows/20261031T182135Z.json','/r/windows/wrong.json'):
            with self.assertRaises(ValueError):c.window_path({'window':path},runtime)

if __name__=='__main__':unittest.main()
