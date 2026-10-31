"""Synthetic finite-mode safety checks. No actual child limits, native or GPU."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
import current_compat as c
import current_controls as ctrl
import current_runtime as r
from test_current_mode import sample,warm_sample,answer
NATIVE_SOURCE_ROOT=None


def storage():
    path=r.P.parent/'model-v1/imma_storage.py'
    spec=importlib.util.spec_from_file_location('finite_storage_readonly',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Pair(unittest.TestCase):
    def issue(self,case,*args):
        response,proof=answer();proof['native']['reused']=0 if case['expected_reuse']=='zero' else 43
        return response,proof
    def test_cold_then_warm_exact_cache_and_no_claim(self):
        fn=Mock(side_effect=self.issue);v=c.run_pair([sample(),warm_sample()],'.',7,1000,issue=fn)
        self.assertTrue(v['complete']);self.assertTrue(v['unmeasured_numerical']);self.assertEqual(len(v['rows']),2)
        self.assertEqual(v['rows'][1]['native']['reused'],43);self.assertFalse(v['quality_or_performance_pass'])
        self.assertEqual([x.args[0]['id'] for x in fn.call_args_list],['finite44-cold','finite44-warm'])
    def test_wrong_capped_partial_deadline_keeps_warm_UNRUN(self):
        for delta in ({'content':'wrong'},{'finish_reason':'length'},{'done':False},{'intentional_budget_stop':True}):
            response,proof=answer();response.update(delta);fn=Mock(return_value=(response,proof))
            v=c.run_pair([sample(),warm_sample()],'.',7,1000,issue=fn)
            self.assertFalse(v['complete']);self.assertEqual(v['scores'][1]['status'],'UNRUN');fn.assert_called_once();self.assertFalse(v['retry'])
        fn=Mock(side_effect=ctrl.Incomplete('deadline'));v=c.run_pair([sample(),warm_sample()],'.',7,1000,issue=fn)
        self.assertFalse(v['complete']);self.assertEqual(v['scores'][1]['status'],'UNRUN');fn.assert_called_once()
    def test_order_policy_and_dependency_refused_before_issue(self):
        cases=[sample(),warm_sample()]
        for changed in (list(reversed(cases)),[cases[0],{**cases[1],'dependency':'foreign'}],[cases[0],{**cases[1],'prompt_ids':[1]}]):
            fn=Mock()
            with self.assertRaises(ValueError):c.run_pair(changed,'.',7,1000,issue=fn)
            fn.assert_not_called()
    def test_wrong_warm_reuse_blocks(self):
        fn=Mock(return_value=answer());v=c.run_pair([sample(),warm_sample()],'.',7,1000,issue=fn)
        self.assertFalse(v['complete']);self.assertFalse(v['scores'][1]['passed']);self.assertEqual(fn.call_count,2)
    def test_fault_raises_without_retry_or_warm(self):
        fn=Mock(side_effect=RuntimeError('native'));rows=[]
        with self.assertRaises(RuntimeError):c.run_pair([sample(),warm_sample()],'.',7,1000,issue=fn,save_progress=lambda v:rows.append(copy.deepcopy(v)))
        fn.assert_called_once();self.assertEqual(rows[-1]['scores'][0]['status'],'FAULT_HOLD');self.assertEqual(rows[-1]['scores'][1]['status'],'UNRUN')
    def test_measured_cold_path_strict(self):
        good={'emitted_token_contract':{'count':186,'ordered_ids_sha256':ctrl.COLD_REFERENCE_SHA}}
        self.assertTrue(ctrl.cold_reference(good)['same_measured_cold_token_path'])
        for key,value in [('count',185),('ordered_ids_sha256','0'*64)]:
            v=copy.deepcopy(good);v['emitted_token_contract'][key]=value
            with self.assertRaises(ctrl.Incomplete):ctrl.cold_reference(v)


class Storage(unittest.TestCase):
    def meta(self):return json.loads((r.P/'PACK_STATE_SOURCE.json').read_text())
    def test_actual_corrected19_check_geometry_below512(self):
        s=storage();g,b=ctrl.corrected_file_bound(self.meta(),s)
        self.assertEqual(b['retained_checks_upper'],19);self.assertEqual(b['picture_count_bytes'],8)
        self.assertEqual(b['corrected_bounds']['slot'],s.slot_bytes(g,44768,2**20)+16*s.check_bytes(g)+8)
        self.assertEqual(b['corrected_bounds']['meta'],s.meta_bytes(44768,2**20)+136)
        self.assertLess(max(b['corrected_bounds'].values()),512*2**20)
        with self.assertRaises(ValueError):s.slot_bytes(g,44768,2**20,checkpoints=19)
    def test_wrong_geometry_and_oversize_rejected(self):
        s=storage();v=self.meta();v['storage_geometry']['layers']=40
        with self.assertRaises(ValueError):ctrl.corrected_file_bound(v,s)
        with patch.object(s,'slot_bytes',return_value=512*2**20):
            with self.assertRaises(ValueError):ctrl.corrected_file_bound(self.meta(),s)
    def test_actual_source_identity_marks_and_dump_prefix(self):
        root=NATIVE_SOURCE_ROOT
        cm=(root/'CMakeLists.txt').read_text();main=(root/'src/ds4/ds4_main.cpp').read_text();model=(root/'src/ds4/ds4_model.cu').read_text();marks=(root/'src/ds4/ds4_marks.hpp').read_text()
        out=ctrl.storage_source_contract(self.meta(),cm,main,model,marks)
        self.assertEqual(out['retained_checks_upper'],19);self.assertFalse(out['per_token_row_alignment_claimed'])
        for args in [(cm.replace('VERSION 0.1.27','VERSION 1.1.45'),main,model,marks),(cm,main,model,marks.replace('kMarksMax = 16','kMarksMax = 32')),(cm,main,model.replace('n += 8 + n_pics * 24;','n += n_pics * 24;'),marks)]:
            with self.assertRaises(ValueError):ctrl.storage_source_contract(self.meta(),*args)
    def rig(self,folder):
        s=storage();callback=Mock();s.native_fsize_preexec=Mock(return_value=callback)
        proc=types.SimpleNamespace(pid=77,poll=Mock(return_value=None),terminate=Mock(),wait=Mock(),kill=Mock())
        original=Mock(return_value=proc);server=types.SimpleNamespace(popen=original);server.original=original;argv=['exe','--serve','']
        self.enterContext(patch.object(ctrl.config,'expected_native_argv',return_value=argv))
        self.enterContext(patch.object(ctrl.resource,'getrlimit',return_value=(-1,-1)))
        ctrl.install_dump_limit(server,{},folder,s)
        return server,s,callback,proc,argv[:-1]
    def test_native_only_one_exact_hook_composes_without_parent_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);server,s,callback,proc,argv=self.rig(folder);before=Mock()
            value=server.popen('the Strata engine',argv,role='engine',preexec_fn=before)
            self.assertIs(value,proc);callback.assert_not_called();before.assert_not_called()
            # Invoke only MOCK preexec callbacks. No actual resource.setrlimit call.
            server.original.call_args.kwargs['preexec_fn']();before.assert_called_once();callback.assert_called_once()
            self.assertEqual(json.loads((folder/'native-file-bound.json').read_text())['native_pid'],77)
            with self.assertRaises(ValueError):server.popen('the Strata engine',argv,role='engine')
            s.native_fsize_preexec.assert_called_once()
    def test_foreign_child_never_spawned(self):
        with tempfile.TemporaryDirectory() as tmp:
            server,s,callback,proc,argv=self.rig(Path(tmp))
            with self.assertRaises(ValueError):server.popen('other',argv)
            proc.terminate.assert_not_called();callback.assert_not_called()
    def test_receipt_failure_closes_captured_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            server,s,callback,proc,argv=self.rig(Path(tmp))
            with patch.object(r,'emit',side_effect=OSError('receipt')):
                with self.assertRaises(OSError):server.popen('the Strata engine',argv)
            proc.terminate.assert_called_once();proc.wait.assert_called_once();callback.assert_not_called()
    def test_actual_native_limits_and_foreign_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d=root/'77';d.mkdir();f=d/'limits';f.write_text('Max file size             536870912            536870912            bytes\n')
            self.assertEqual(ctrl.native_limit_read(77,proc=root)['file_limit_bytes'],512*2**20)
            f.write_text('Max file size             unlimited            unlimited            bytes\n')
            with self.assertRaises(ValueError):ctrl.native_limit_read(77,proc=root)
    def test_exact2_complete_dumps_no_legacy4_completion(self):
        helper=types.SimpleNamespace(dump_snapshot=Mock(return_value={'status':'WITHIN_BUDGET','count':2}),dump_size=Mock(return_value={'bytes':517120,'rows':1}))
        self.assertEqual(ctrl.finish_dump_pair(Path('/owned'),helper)['count'],2);helper.dump_snapshot.assert_called_once_with(Path('/owned'),complete=False)
        for policy in ({'status':'WITHIN_BUDGET','count':1},{'status':'WITHIN_BUDGET','count':4},{'status':'INCOMPLETE_HOLD','count':2}):
            helper.dump_snapshot.return_value=policy
            with self.assertRaises(ctrl.Incomplete):ctrl.finish_dump_pair(Path('/owned'),helper)
        helper.dump_snapshot.return_value={'status':'WITHIN_BUDGET','count':2};helper.dump_size.side_effect=ValueError('partial')
        with self.assertRaises(ValueError):ctrl.finish_dump_pair(Path('/owned'),helper)
