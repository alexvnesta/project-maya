"""CPU-only entry, qualifier and startup dependency composition controls."""
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import gpu_check as g
import gpu_entry as entry
import qualify_gpu_cpu as driver


class Entry(unittest.TestCase):
    def test_exact_entry_calls_only_guarded_phase(self):
        with patch.object(g, 'fixture_phase', return_value=0) as phase:
            self.assertEqual(entry.main(['--output','/owned/output','--proof','/owned/proof']),0)
        phase.assert_called_once_with(Path('/owned/output'),Path('/owned/proof'))

    def test_missing_proof_refused_before_phase(self):
        with patch.object(g,'fixture_phase') as phase:
            with self.assertRaises(SystemExit):entry.main(['--output','/owned/output'])
        phase.assert_not_called()

    def test_run_or_device_selector_is_not_entry_authority(self):
        for flag in ['--run','--device']:
            with patch.object(g,'fixture_phase') as phase:
                with self.assertRaises(SystemExit):entry.main(['--output','/o','--proof','/p',flag])
            phase.assert_not_called()

    def test_foreign_controller_import_refused(self):
        with patch.object(g,'__file__','/foreign/gpu_check.py'),patch.object(g,'fixture_phase') as phase:
            with self.assertRaises(ValueError):entry.main(['--output','/o','--proof','/p'])
        phase.assert_not_called()


class StartupComposition(unittest.TestCase):
    def test_adapter_source_changed_refused_before_import(self):
        with patch.object(g,'sha',return_value='0'*64),patch.object(g.importlib,'import_module') as load:
            with self.assertRaises(ValueError):g.startup_host(object())
        load.assert_not_called()

    def test_foreign_adapter_origin_refused(self):
        adapter=types.SimpleNamespace(__file__='/foreign/head_startup.py',guarded_host=Mock())
        with patch.object(g,'sha',return_value=g.STARTUP_SOURCES['head_startup.py']),patch.object(g.importlib,'import_module',return_value=adapter):
            with self.assertRaises(ValueError):g.startup_host(object())
        adapter.guarded_host.assert_not_called()

    def test_actual_adapter_capture_is_in_subclass_mro(self):
        # Production factory's original-owner custody was separately tested by r2.
        # Exercise the actual new capture through this controller's composed MRO.
        import head_startup
        class Base:
            pass
        class Guarded(Base):
            def capture_pending_start(self,old):
                return head_startup.capture(self,old,emit=g.emit)
        a=types.SimpleNamespace(ChunkProductionHost=Base)
        adapter=types.SimpleNamespace(__file__=str(g.P/'head_startup.py'),guarded_host=Mock(return_value=Guarded))
        with patch.object(g,'sha',return_value=g.STARTUP_SOURCES['head_startup.py']),patch.object(g.importlib,'import_module',return_value=adapter):
            host=g.host_class(a)()
        adapter.guarded_host.assert_called_once_with(a)
        self.assertIsInstance(host,Guarded)
        host.start_invocation=None;host.start_main_pid=None;host.start_binding=None
        host.unit_snapshot=Mock(return_value={'invocation':'a'*32,'main_pid':0,'state':'activating'})
        host.native_snapshot=Mock()
        host.capture_pending_start('b'*32)
        host.native_snapshot.assert_not_called()
        self.assertEqual(host.start_invocation,'a'*32)
        self.assertIsNone(host.start_binding)

    def test_entry_launch_requires_close_and_uses_canonical_window(self):
        class Base:
            pass
        with patch.object(g,'startup_host',return_value=Base):host=g.host_class(types.SimpleNamespace(ChunkProductionHost=Base))()
        host.launch_owned=Mock(return_value='owned')
        with self.assertRaises(ValueError):host.launch('prior','output','proof')
        host.launch_owned.assert_not_called()
        host.old_close_verified=True
        self.assertEqual(host.launch('prior','output','proof'),'owned')
        host.launch_owned.assert_called_once_with('prior',[str(g.R/'venv/bin/python3.14'),'-B',str(g.P/'gpu_entry.py'),'--output','output','--proof','proof'],1200)

    def test_owner_source_changed_refused_before_import(self):
        with patch.object(g,'sha',return_value='0'*64),patch.object(g.importlib,'import_module') as load:
            with self.assertRaises(ValueError):g.load_owner()
        load.assert_not_called()


class StartupProof(unittest.TestCase):
    def check(self,change=None):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory).resolve()
            ids=['startup-'+str(i) for i in range(22)]
            files={str(p/name):pin for name,pin in g.STARTUP_SOURCES.items()}
            files.update({str(p/'qualify_startup_cpu.py'):g.STARTUP_DRIVER_SHA,
                          str(p/'STARTUP_CPU_RESULT_ASTRA_REVIEW_r2.json'):g.STARTUP_RESULT_SHA,
                          str(g.F/'activate_chunk4096.py'):g.OWNER_SHA})
            review={'all_source_and_tests_read':True,'source_sha256':g.STARTUP_SOURCES,
                    'test_ids':ids,'driver_sha256':g.STARTUP_DRIVER_SHA}
            (p/'startup-source-review.json').write_text(json.dumps(review))
            files[str(p/'startup-source-review.json')]=g.sha(p/'startup-source-review.json')
            for label in ['darwin','linux']:
                out=p/('startup-CPU-r2-'+label);out.mkdir()
                proof={'passed':True,'controls':22,'test_ids':ids,'source_sha256':g.STARTUP_SOURCES,
                       'original_owner_sha256':g.OWNER_SHA,'GPU_execution':False,
                       'compiler_execution':False,'native_execution':False}
                child={'returncode':0,'CPU_s':30,'wall_s':90,'nice':15,'CUDA_hidden':True,
                       'Linux_AS_MiB':512 if label=='linux' else None,'error':None,'cleanup_errors':[]}
                if change=='failed' and label=='linux':proof['passed']=False
                if change=='ids' and label=='linux':proof['test_ids']=ids[::-1]
                if change=='old_owner' and label=='linux':proof['original_owner_sha256']='0'*64
                if change=='limits' and label=='linux':child['Linux_AS_MiB']=513
                if change=='cleanup' and label=='linux':child['cleanup_errors']=['owned PG alive']
                if change=='bool_exit' and label=='linux':child['returncode']=False
                (out/'receipt.json').write_text(json.dumps(proof));(out/'child.json').write_text(json.dumps(child));(out/'child.log').write_text('raw')
                files.update({str(out/name):g.sha(out/name) for name in ['receipt.json','child.json','child.log']})
            if change=='raw_missing':del files[str(p/'startup-CPU-r2-linux/child.log')]
            if change=='adapter':files[str(p/'head_startup.py')]='0'*64
            with patch.object(g,'P',p):
                if change is None:g.startup_proof({'files':files})
                else:
                    with self.assertRaises(ValueError):g.startup_proof({'files':files})

    def test_complete_corrected_r2_proof(self):self.check()
    def test_old_failed_proof_not_accepted(self):self.check('failed')
    def test_changed_adapter_pin_refused(self):self.check('adapter')
    def test_missing_raw_pin_refused(self):self.check('raw_missing')
    def test_wrong_ordered_ids_refused(self):self.check('ids')
    def test_wrong_original_owner_refused(self):self.check('old_owner')
    def test_changed_limits_refused(self):self.check('limits')
    def test_cleanup_error_refused(self):self.check('cleanup')
    def test_boolean_exit_refused(self):self.check('bool_exit')


class Driver(unittest.TestCase):
    def test_unknown_source_rejected_before_hash(self):
        with patch.object(driver.c,'sha') as digest:
            with self.assertRaises(ValueError):driver.source_pins({'source_sha256':{'foreign.py':'0'*64}})
        digest.assert_not_called()

    def test_dependency_changed_refused(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(driver,'SOURCE_E',Path(directory).resolve()):
            (driver.SOURCE_E/'input.py').write_text('changed')
            with self.assertRaises(ValueError):driver.input_pins({'source_input_sha256':{'input.py':'0'*64}})

    def test_absolute_or_parent_input_refused_before_read(self):
        for name in ['/foreign.py','../foreign.py']:
            with patch.object(driver.c,'sha') as digest:
                with self.assertRaises(ValueError):driver.input_pins({'source_input_sha256':{name:'0'*64}})
            digest.assert_not_called()

    def test_owned_input_pin_preserved(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(driver,'SOURCE_E',Path(directory).resolve()):
            path=driver.SOURCE_E/'input.py';path.write_text('only source')
            pins={'input.py':driver.c.sha(path)}
            self.assertEqual(driver.input_pins({'source_input_sha256':pins}),pins)

    def test_linux_limits_child_only(self):
        with patch.object(driver.sys,'platform','linux'),patch.object(driver.resource,'setrlimit') as limit,patch.object(driver.os,'nice') as nice:
            driver.limits()
        self.assertEqual([c.args for c in limit.call_args_list],[(driver.resource.RLIMIT_CPU,(30,30)),(driver.resource.RLIMIT_AS,(512*2**20,512*2**20))])
        nice.assert_called_once_with(15)

    def test_mac_does_not_set_linux_AS(self):
        with patch.object(driver.sys,'platform','darwin'),patch.object(driver.resource,'setrlimit') as limit,patch.object(driver.os,'nice'):
            driver.limits()
        self.assertEqual(limit.call_count,1)

    def test_cleanup_checks_owned_group_after_leader_exits(self):
        process=Mock(pid=123)
        with patch.object(driver.os,'killpg',side_effect=[None,ProcessLookupError()]):
            self.assertEqual(driver.cleanup_child(process),[])
        process.wait.assert_called_once_with(timeout=3)

    def test_cleanup_escalates_only_owned_group(self):
        process=Mock(pid=123)
        with patch.object(driver.os,'killpg',side_effect=[None,None,None,ProcessLookupError()]) as kill,patch.object(driver.time,'monotonic',side_effect=[0,4,5]):
            self.assertEqual(driver.cleanup_child(process),[])
        self.assertEqual([call.args for call in kill.call_args_list],[(123,driver.signal.SIGTERM),(123,0),(123,driver.signal.SIGKILL),(123,0)])


if __name__=='__main__':unittest.main()
