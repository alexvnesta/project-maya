"""Portable fixture-only build controls. No compiler, ELF or model is executed."""
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import build as r

b = r.load_build()  # immutable input, only after the driver checks source/input maps


def dump(path, value):
    path.write_text(json.dumps(value))


class Fixture(unittest.TestCase):
    def test_actual_fixture_is_exact_one_line_change(self):
        old = (r.N / 'numerical-v2/iq2xs_exact.cpp').read_bytes()
        new = (r.HERE / 'iq2xs_exact.cpp').read_bytes()
        r.fixture_contract(old, new)
        self.assertEqual(len(new.splitlines()), len(old.splitlines()))

    def test_omitted_or_additional_change_refused(self):
        old = (r.N / 'numerical-v2/iq2xs_exact.cpp').read_bytes()
        for new in (old, old.replace(r.BEFORE, r.AFTER) + b'\n', old.replace(r.BEFORE, r.AFTER).replace(b'0x3c', b'0x3d')):
            with self.assertRaisesRegex(ValueError, 'one initializer'): r.fixture_contract(old, new)

    def test_foreign_original_refused(self):
        with self.assertRaisesRegex(ValueError, 'original fixture'): r.fixture_contract(b'foreign', b'foreign')

    @staticmethod
    def zero_partial_write(destination):
        # Explicit stand-in for the observed zero branch. This does not execute ggml.
        destination[:260] = bytes(260)

    def test_unequal_initialization_fails_complete_byte_comparison(self):
        reference = bytearray([0x3c] * 292); selected = bytearray(292)
        self.zero_partial_write(reference); self.zero_partial_write(selected)
        self.assertNotEqual(reference, selected)
        self.assertEqual([i for i in range(292) if reference[i] != selected[i]], list(range(260, 292)))

    def test_equal_initialization_preserves_full_comparison_and_outer_canaries(self):
        outer = bytearray([0x3c] * 356); selected = bytearray([0x3c] * 292)
        self.zero_partial_write(memoryview(outer)[32:324]); self.zero_partial_write(selected)
        self.assertEqual(outer[32:324], selected)
        self.assertEqual(outer[:32] + outer[324:], bytes([0x3c] * 64))

    def test_written_byte_mutation_still_rejects(self):
        reference = bytearray([0x3c] * 292); selected = reference.copy()
        self.zero_partial_write(reference); self.zero_partial_write(selected); selected[10] = 1
        self.assertNotEqual(reference, selected)


class Commands(unittest.TestCase):
    def setUp(self):
        self.first = json.loads((r.N / 'build-v1/DEPENDENCY_OBSERVATION.json').read_text())
        self.folder = r.HERE / 'build-FIRST'

    def test_exact_two_commands_use_original_flags_existing_archive_only(self):
        jobs = r.commands(b, self.first, self.folder)
        self.assertEqual([j[0] for j in jobs], ['fixture-compile', 'fixture-link'])
        self.assertEqual(r.command_contract(b, self.first, self.folder, jobs[0]), ('compile', 120, 4*2**30, 300))
        self.assertEqual(r.command_contract(b, self.first, self.folder, jobs[1]), ('link', 30, 4*2**30, 90))
        self.assertIn(str(r.HERE/'iq2xs_exact.cpp'), jobs[0][1])
        self.assertIn(str(r.N/'build-v3/build-FIRST/libstrata_kernels_cpu.a'), jobs[1][1])
        self.assertNotIn('-mavx2', jobs[0][1])  # Preserve actual fixture flags, not IQ object flags.
        self.assertFalse(any('maya-ds4-candidate' in value for job in jobs for value in job[1]))

    def test_altered_flags_source_output_archive_or_command_refused(self):
        jobs = r.commands(b, self.first, self.folder)
        for i, position, replacement in ((0, 0, '/bin/sh'), (0, -1, 'foreign.cpp'),
                                         (0, 1, '-ffast-math'), (1, -1, '/tmp/foreign')):
            job = list(jobs[i]); job[1] = list(job[1]); job[1][position] = replacement
            with self.assertRaisesRegex(ValueError, 'exact two'): r.command_contract(b, self.first, self.folder, tuple(job))
        with self.assertRaisesRegex(ValueError, 'namespace'): r.commands(b, self.first, self.folder.parent/'elsewhere')

    def test_wrong_resource_class_and_bool_refused(self):
        job = r.commands(b, self.first, self.folder)[0]
        with patch.object(b, 'resource_class', return_value=('compile', 30, 512*2**20, 90)):
            with self.assertRaisesRegex(ValueError, 'resource class'): r.command_contract(b, self.first, self.folder, job)
        altered = list(job); altered[2] = 1
        with self.assertRaisesRegex(ValueError, 'resource class'): r.command_contract(b, self.first, self.folder, tuple(altered))

    def test_full_child_wall_must_fit_remaining_soft_budget(self):
        r.child_admission(0, 0, 300); r.child_admission(0, 309, 90)
        for now, wall in ((100, 300), (310, 90), (0, 301), (0, True), (-1, 90)):
            with self.assertRaises(ValueError): r.child_admission(0, now, wall)


class Execute(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(r, 'HERE', self.root))
        self.stack.enter_context(patch.object(r.time, 'monotonic', return_value=1))
        self.files = Mock(); self.guard = Mock(); self.owned = b.OwnedChildren()
        self.deps = self.stack.enter_context(patch.object(b, 'actual_dependencies', return_value={}))
        self.run = self.stack.enter_context(patch.object(b, 'run_child', side_effect=self.child))

    def child(self, argv, name, folder, guard, *, compiler_child, owned):
        self.assertIs(owned, self.owned)
        guard()
        output = Path(argv[argv.index('-o')+1]); output.write_bytes(b'synthetic object or ELF, never executed')
        if compiler_child: Path(argv[argv.index('-MF')+1]).write_text('fixture.o: synthetic.h\n')
        else: (folder/'iq2xs_exact.link.d').write_text('fixture: synthetic.o\n')
        role,cpu,memory,wall=b.resource_class(argv,compiler_child)
        return {'argv':argv,'status':'PASS','returncode':0,'error':None,'cleanup':[], 'pid':12345,
                'role':role,'CPU_s':cpu,'AS_bytes':memory,'wall_s':wall,'elapsed_seconds':.1}

    def call(self): return r.execute(b, {'files':{}}, self.guard, self.owned, 0, self.files)

    def test_actual_two_step_orchestration_success_and_no_execution_claim(self):
        result=self.call(); self.assertEqual(self.run.call_count,2); self.assertEqual(self.deps.call_count,2)
        self.assertEqual(len(result['outputs']),2); self.assertFalse(result['fixture_execution'])
        self.assertFalse(result['candidate_rebuilt']); self.assertTrue((self.root/'build-FIRST/receipt.json').is_file())

    def test_first_child_failure_stops_link_and_preserves_partial(self):
        self.run.side_effect=ValueError('compile failed')
        with self.assertRaisesRegex(ValueError,'compile failed'):self.call()
        self.assertEqual(self.run.call_count,1)
        partial=json.loads((self.root/'build-FIRST/partial.json').read_text())
        self.assertEqual(partial['attempted'],['fixture-compile']);self.assertEqual(partial['not_admitted'],['fixture-link'])
        self.assertFalse(partial['retry_authorized'])

    def test_unknown_dependency_stops_link(self):
        self.deps.side_effect=ValueError('unknown header')
        with self.assertRaisesRegex(ValueError,'unknown header'):self.call()
        self.assertEqual(self.run.call_count,1)

    def test_link_failure_keeps_compile_evidence_without_success(self):
        def run(*args,**kwargs):
            if args[1]=='fixture-link':raise ValueError('link failed')
            return self.child(*args,**kwargs)
        self.run.side_effect=run
        with self.assertRaisesRegex(ValueError,'link failed'):self.call()
        self.assertEqual(self.run.call_count,2);self.assertTrue((self.root/'build-FIRST/fixture-compile-inputs.json').is_file())
        self.assertFalse((self.root/'build-FIRST/receipt.json').exists())

    def test_wrong_pid_bounds_cleanup_or_status_cannot_pass(self):
        def run(*args,**kwargs):
            result=self.child(*args,**kwargs);result['pid']=True;return result
        self.run.side_effect=run
        with self.assertRaisesRegex(ValueError,'receipt differs'):self.call()
        self.assertEqual(self.run.call_count,1)

    def test_busy_or_source_change_before_write_prevents_child(self):
        self.guard.side_effect=ValueError('busy')
        with self.assertRaisesRegex(ValueError,'busy'):self.call()
        self.run.assert_not_called();self.assertFalse((self.root/'build-FIRST').exists())

    def test_source_change_before_second_step_stops(self):
        def checked():
            if self.run.call_count:raise ValueError('source changed')
        self.files.side_effect=checked
        with self.assertRaisesRegex(ValueError,'source changed'):self.call()
        self.assertEqual(self.run.call_count,1)

    def test_new_object_tampering_cannot_reach_link(self):
        def dependencies(*args):
            (self.root/'build-FIRST/iq2xs_exact.cpp.o').write_bytes(b'changed')
            return {}
        self.deps.side_effect=dependencies
        with self.assertRaisesRegex(ValueError,'artifact changed'):self.call()
        self.assertEqual(self.run.call_count,1)

    def test_insufficient_initial_budget_creates_no_output(self):
        with patch.object(r.time,'monotonic',return_value=100):
            with self.assertRaisesRegex(ValueError,'soft budget'):self.call()
        self.run.assert_not_called();self.assertFalse((self.root/'build-FIRST').exists())

    def test_insufficient_remaining_budget_does_not_start_link(self):
        with patch.object(r.time,'monotonic',return_value=1) as clock:
            def run(*args,**kwargs):
                result=self.child(*args,**kwargs);clock.return_value=310;return result
            self.run.side_effect=run
            with self.assertRaisesRegex(ValueError,'soft budget'):self.call()
        self.assertEqual(self.run.call_count,1)

    def test_existing_namespace_never_reused(self):
        (self.root/'build-FIRST').mkdir()
        with self.assertRaisesRegex(ValueError,'Fresh'):self.call()
        self.run.assert_not_called()

class Main(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.here=self.root/'repair';self.here.mkdir();self.e=self.root/'E';self.e.mkdir();self.state=self.e/'STATE.json'
        dump(self.state,{'active_cpu_build':False,'other':'retained'});dump(self.here/'qualification.json',{})
        self.pin=r.sha(self.here/'qualification.json');self.binding={'main_pid':122,'native_pid':123};self.q={'selected_binding':self.binding,'files':{}}
        self.c=Mock();self.host=Mock();self.runtime=Mock();self.cas=Mock()
        self.c.support.return_value=(None,self.runtime,None,self.host,self.binding)
        self.c.guard.side_effect=lambda *args:json.loads(self.state.read_text())
        def cas(path,raw,value):
            if path.read_bytes()!=raw:raise ValueError('CAS race')
            dump(path,value)
        self.cas.cas_state.side_effect=cas
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name,value in {'HERE':self.here,'EXPECTED':self.here,'E':self.e}.items():self.stack.enter_context(patch.object(r,name,value))
        self.stack.enter_context(patch.object(r.sys,'platform','linux'));self.stack.enter_context(patch.object(r.sys,'dont_write_bytecode',True))
        self.stack.enter_context(patch.object(r,'bootstrap',return_value=(b,self.q)))
        self.verify=self.stack.enter_context(patch.object(r,'verify_q',return_value={}))
        self.stack.enter_context(patch.object(b,'process_ticks',return_value=567))
        self.stack.enter_context(patch.object(b,'load_exact',return_value=self.c));self.stack.enter_context(patch.object(b,'load_cas',return_value=self.cas))
        self.gpu=self.stack.enter_context(patch.object(b,'observe_gpu_lease',return_value={'identity':{'inode':10},'main_pid':122}))
        self.space=self.stack.enter_context(patch.object(r.shutil,'disk_usage',return_value=Mock(free=140*2**30)))
        self.execute=self.stack.enter_context(patch.object(r,'execute',return_value={'passed':True}))

    def result(self):return json.loads((self.here/'build-supervision-FIRST/result.json').read_text())

    def test_success_releases_only_own_claim_and_preserves_other_state(self):
        self.assertEqual(r.main(self.pin),{'passed':True});self.assertEqual(json.loads(self.state.read_text()),{'active_cpu_build':False,'other':'retained'})
        self.assertTrue(self.result()['owned_groups_absence']['passed']);self.assertTrue(self.result()['own_claim_released'])
        self.assertEqual(self.cas.cas_state.call_count,2);self.host.restore_ds.assert_not_called()

    def test_busy_before_hash_does_not_claim(self):
        self.c.guard.side_effect=ValueError('busy')
        with self.assertRaisesRegex(ValueError,'busy'):r.main(self.pin)
        self.verify.assert_not_called();self.execute.assert_not_called();self.assertFalse((self.e/'cpu-build.lock').exists())

    def test_actual_CAS_import_failure_cannot_claim_or_start_compiler(self):
        with patch.object(b,'load_cas',side_effect=ModuleNotFoundError('transport')):
            with self.assertRaisesRegex(ModuleNotFoundError,'transport'):r.main(self.pin)
        self.execute.assert_not_called();self.assertFalse((self.e/'cpu-build.lock').exists())

    def test_wrong_owner_root_or_GPU_lease_refuses_before_hash(self):
        self.q['selected_binding']={}
        with self.assertRaisesRegex(ValueError,'owner'):r.main(self.pin)
        self.q['selected_binding']=self.binding;self.space.return_value=Mock(free=135*2**30)
        with self.assertRaisesRegex(ValueError,'Root136'):r.main(self.pin)
        self.space.return_value=Mock(free=140*2**30);self.gpu.side_effect=ValueError('GPU lease')
        with self.assertRaisesRegex(ValueError,'GPU lease'):r.main(self.pin)
        self.verify.assert_not_called();self.execute.assert_not_called()

    def test_stale_claim_not_adopted_or_cleared(self):
        dump(self.state,{'active_cpu_build':{'foreign':1}})
        with self.assertRaisesRegex(ValueError,'Existing claim'):r.main(self.pin)
        self.execute.assert_not_called();self.cas.cas_state.assert_not_called()

    def test_busy_after_claim_is_controlled_deferral_after_absence(self):
        self.execute.side_effect=ValueError('DEFERRED_BUSY_UNTOUCHED_OR_CLEANUP_OWNED_COMPILER')
        with self.assertRaises(b.BuildDeferred):r.main(self.pin)
        self.assertEqual(self.result()['status'],'DEFERRED_BUSY_PARTIALS_RETAINED');self.assertTrue(self.result()['own_claim_released'])

    def test_primary_failure_and_foreign_claim_preserved(self):
        def fail(*args):dump(self.state,{'active_cpu_build':{'foreign':True}});raise ValueError('primary numerical')
        self.execute.side_effect=fail
        with self.assertRaisesRegex(ValueError,'primary numerical') as caught:r.main(self.pin)
        self.assertTrue(caught.exception.__notes__);self.assertEqual(json.loads(self.state.read_text())['active_cpu_build'],{'foreign':True})
        self.assertFalse(self.result()['own_claim_released'])

    def test_pending_spawn_prevents_release(self):
        def fail(*args):args[3].starting('pending');raise OSError('spawn failed')
        self.execute.side_effect=fail
        with self.assertRaisesRegex(OSError,'spawn failed'):r.main(self.pin)
        self.assertTrue(json.loads(self.state.read_text())['active_cpu_build']);self.assertFalse(self.result()['owned_groups_absence']['passed'])

    def test_cleanup_fault_prevents_release_even_without_live_process(self):
        def fail(*args):args[3].cleanup_failed('job',ValueError('cleanup'));raise ValueError('numerical fault')
        self.execute.side_effect=fail
        with self.assertRaisesRegex(ValueError,'numerical fault'):r.main(self.pin)
        self.assertFalse(self.result()['own_claim_released']);self.assertTrue(json.loads(self.state.read_text())['active_cpu_build'])

    def test_surviving_group_retains_claim_no_automatic_second_cleanup(self):
        process=Mock(pid=54321);process.poll.return_value=0
        def fail(*args):args[3].starting('job');args[3].registered(process,'job');raise ValueError('partial')
        self.execute.side_effect=fail
        with patch.object(b,'group_alive',return_value=True),patch.object(b,'cleanup') as cleanup:
            with self.assertRaisesRegex(ValueError,'partial'):r.main(self.pin)
        cleanup.assert_not_called();self.assertFalse(self.result()['own_claim_released'])

    def test_CAS_conflict_never_launches_or_clears_foreign_state(self):
        self.cas.cas_state.side_effect=ValueError('CAS race')
        with self.assertRaisesRegex(ValueError,'CAS race'):r.main(self.pin)
        self.execute.assert_not_called();self.assertEqual(self.cas.cas_state.call_count,1)

    def test_success_cannot_hide_vanished_claim(self):
        def finish(*args):dump(self.state,{'active_cpu_build':False});return {'passed':True}
        self.execute.side_effect=finish
        with self.assertRaisesRegex(ValueError,'vanished'):r.main(self.pin)
        self.assertEqual(self.result()['status'],'HOLD')

    def test_global_deadline_checked_after_execute(self):
        with patch.object(r.time,'monotonic',return_value=0) as clock:
            def finish(*args):clock.return_value=601;return {'passed':True}
            self.execute.side_effect=finish
            with self.assertRaisesRegex(ValueError,'wall exhausted'):r.main(self.pin)
        self.assertTrue(self.result()['own_claim_released']);self.assertEqual(self.result()['status'],'HOLD')

    def test_primary_preserved_if_terminal_receipt_write_fails(self):
        original=b.emit
        def emit(path,value):
            if path.name=='result.json':raise OSError('receipt write')
            original(path,value)
        self.execute.side_effect=ValueError('primary')
        with patch.object(b,'emit',side_effect=emit):
            with self.assertRaisesRegex(ValueError,'primary') as caught:r.main(self.pin)
        self.assertIn('Supervision receipt',caught.exception.__notes__[-1])


class CPUProofs(unittest.TestCase):
    def setUp(self):
        import cpu_driver as d
        self.d=d;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.stack.enter_context(patch.object(r,'HERE',self.root))
        (self.root/'cpu_driver.py').write_text('#synthetic driver');(self.root/'SOURCE_ROOT_REVIEW.json').write_text('{}')
        self.reviewpin=r.sha(self.root/'SOURCE_ROOT_REVIEW.json');self.source={'cpu_driver.py':r.sha(self.root/'cpu_driver.py')}
        self.inputs={'/synthetic/input':'a'*64};self.ids=['test_synthetic.A.test_one'];self.before=(self.source,self.inputs,self.ids)
        self.driver=Mock();self.driver.checked.return_value=self.before;self.driver.bounds=d.bounds;self.driver.attempt_contract=d.attempt_contract
        self.stack.enter_context(patch.object(r,'exact_module',return_value=self.driver))
        self.q={'source_sha256':self.source,'input_sha256':self.inputs,'test_ids':self.ids,'source_review_sha256':self.reviewpin,
                'files':dict(self.inputs,**{str(self.root/'cpu_driver.py'):self.source['cpu_driver.py'],str(self.root/'SOURCE_ROOT_REVIEW.json'):self.reviewpin})}
        for host in ('darwin','linux'):
            folder=self.root/('CPU-FIRST-'+host);folder.mkdir();pid=456 if host=='darwin' else 789
            observed={'pid':pid,'ppid':123,'pgid':pid,'cpu':[30,30],'as':[d.AS_BYTES]*2 if host=='linux' else None,
                      'nice':15,'environment':d.ENV,'platform':host,'dont_write_bytecode':True}
            receipt={'status':'PASS','pid':pid,'review_sha256':self.reviewpin,'observed':observed,'post_observed':observed,
                'failures':0,'errors':0,'tests_run':1,'test_ids':self.ids,'source_sha256':self.source,'source_after_sha256':self.source,
                'input_sha256':self.inputs,'input_after_sha256':self.inputs}
            child={'pid':pid,'returncode':0,'error':None,'cleanup':[],'elapsed_seconds':.2}
            dump(folder/'attempt.json',{'review_sha256':self.reviewpin,'parent_pid':123,'source_sha256':self.source,'input_sha256':self.inputs,'test_ids':self.ids})
            dump(folder/'observed.json',observed);dump(folder/'receipt.json',receipt);dump(folder/'child.json',child);(folder/'child.log').write_text('synthetic OK\n')
            dump(folder/'parent.json',{'status':'PASS','pid':pid,'review_sha256':self.reviewpin,'receipt_sha256':r.sha(folder/'receipt.json'),
                                     'child_sha256':r.sha(folder/'child.json'),'log_sha256':r.sha(folder/'child.log')})
            for path in folder.iterdir():self.q['files'][str(path)]=r.sha(path)

    def mutate(self,relative,key,value):
        path=self.root/relative;row=json.loads(path.read_text());row[key]=value;dump(path,row);self.q['files'][str(path)]=r.sha(path)

    def test_both_host_exact_positive_chain(self):r.cpu_proofs(b,self.q)

    def test_raw_log_membership_omission_refuses(self):
        self.q['files'].pop(str(self.root/'CPU-FIRST-linux/child.log'))
        with self.assertRaisesRegex(ValueError,'raw proof'):r.cpu_proofs(b,self.q)

    def test_wrong_Linux_AS_or_parent_PID_refuses(self):
        self.mutate('CPU-FIRST-linux/observed.json','as',None)
        with self.assertRaisesRegex(ValueError,'address-space'):r.cpu_proofs(b,self.q)

    def test_failed_child_or_missing_complete_IDs_refuses(self):
        self.mutate('CPU-FIRST-linux/child.json','returncode',1)
        with self.assertRaisesRegex(ValueError,'receipt differs'):r.cpu_proofs(b,self.q)

    def test_stale_parent_receipt_hash_refuses(self):
        self.mutate('CPU-FIRST-linux/parent.json','receipt_sha256','b'*64)
        with self.assertRaisesRegex(ValueError,'parent chain'):r.cpu_proofs(b,self.q)

    def test_source_or_input_membership_omission_refuses(self):
        self.q['files'].pop('/synthetic/input')
        with self.assertRaisesRegex(ValueError,'input absent'):r.cpu_proofs(b,self.q)


class Bootstrap(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.here=self.root/'numerical';self.here.mkdir();self.d=self.root/'decode';self.d.mkdir()
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(r,'HERE',self.here));self.stack.enter_context(patch.object(r,'D',self.d))
        self.load=self.stack.enter_context(patch.object(r,'load_build',return_value=b))
        self.prior=self.d/'model-v1/numerical-qualification.json';self.prior.parent.mkdir()
        paths=[self.d/'iq2s-persistent-v1/iq2s_build.py',self.d/'prose-speed-v1/prose_measure.py',self.d/'prose-speed-v1/transport.py']
        for path in paths:path.parent.mkdir(exist_ok=True);path.write_text('#synthetic inert input '+path.name)
        dump(self.prior,{'files':{str(p):r.sha(p) for p in paths}})
        for key,path in zip(('SUPPORT_SHA','CAS_SHA','TRANSPORT_SHA'),paths):self.stack.enter_context(patch.object(b,key,r.sha(path)))
        self.stack.enter_context(patch.object(b,'IMPORT_Q_SHA',r.sha(self.prior)))
        self.q={'files':{str(p):r.sha(p) for p in [self.prior,*paths]},'single_coordinator_maintenance_freeze':True,
            'state_CAS_is_global_atomic':False,'GPU_lease_untouched':True,'cpu_lock_path':str(b.E/'cpu-build.lock')}
        self.q['files'][str(r.BUILD)]=r.BUILD_SHA

    def freeze(self):dump(self.here/'qualification.json',self.q);return r.sha(self.here/'qualification.json')

    def test_preimport_closure_positive_no_support_import(self):
        with patch.object(b,'load_exact') as imp:
            result=r.bootstrap(self.freeze());self.assertIs(result[0],b);imp.assert_not_called()

    def test_missing_build_pin_refuses_before_loading_build(self):
        self.q['files'].pop(str(r.BUILD))
        with self.assertRaisesRegex(ValueError,'helper missing'):r.bootstrap(self.freeze())
        self.load.assert_not_called()

    def test_missing_transport_membership_refuses_before_support(self):
        self.q['files'].pop(str(self.d/'prose-speed-v1/transport.py'))
        with patch.object(b,'load_exact') as imp:
            with self.assertRaisesRegex(ValueError,'Python custody'):r.bootstrap(self.freeze())
        imp.assert_not_called()

    def test_cooperative_boundary_must_be_explicit(self):
        self.q['single_coordinator_maintenance_freeze']=False
        with self.assertRaisesRegex(ValueError,'cooperative'):r.bootstrap(self.freeze())


class PriorCustody(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.stack.enter_context(patch.object(r,'N',self.root))
        self.num=self.root/'numerical-v3';self.num.mkdir();self.out=self.root/'build-v3/build-FIRST';self.out.mkdir(parents=True)
        self.raw=self.num/'failed.json';dump(self.raw,{'status':'HOLD'})
        self.prior=self.num/'qualification.json';dump(self.prior,{'files':{str(self.raw):r.sha(self.raw)}})
        outputs={}
        for name in ('maya-ds4-candidate','libstrata_kernels_cpu.a','iq_avx2.cpp.o','native_expert.cpp.o'):
            path=self.out/name;path.write_bytes(b'inert '+name.encode());outputs[name]=r.sha(path)
        self.review=self.num/'FIRST_FAULT_ASTRA_REVIEW.json'
        dump(self.review,{'raw_sha256':{'failed.json':r.sha(self.raw)}})
        self.stack.enter_context(patch.object(r,'OLD_Q_SHA',r.sha(self.prior)))
        self.stack.enter_context(patch.object(r,'OUTPUT_PINS',outputs))
        self.stack.enter_context(patch.object(r,'FAILURE_PINS',{'FIRST_FAULT_ASTRA_REVIEW.json':r.sha(self.review)}))
        self.q={'files':{str(p):r.sha(p) for p in [self.raw,self.prior,self.review,*self.out.iterdir()]}}

    def test_positive_full_failed_evidence_and_candidate_membership(self):r.prior_contract(b,self.q)

    def test_prior_qualification_omission_refused(self):
        self.q['files'].pop(str(self.prior))
        with self.assertRaisesRegex(ValueError,'failed qualification'):r.prior_contract(b,self.q)

    def test_original_raw_omission_refused(self):
        self.q['files'].pop(str(self.raw))
        with self.assertRaisesRegex(ValueError,'input omitted'):r.prior_contract(b,self.q)

    def test_existing_candidate_archive_mutation_refused(self):
        (self.out/'libstrata_kernels_cpu.a').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'candidate output'):r.prior_contract(b,self.q)

    def test_diagnosis_membership_omission_refused(self):
        self.q['files'].pop(str(self.review))
        with self.assertRaisesRegex(ValueError,'diagnosis custody'):r.prior_contract(b,self.q)

    def test_failure_review_cannot_escape_namespace(self):
        dump(self.review,{'raw_sha256':{'../elsewhere':'a'*64}})
        self.q['files'][str(self.review)]=r.sha(self.review)
        with patch.object(r,'FAILURE_PINS',{'FIRST_FAULT_ASTRA_REVIEW.json':r.sha(self.review)}):
            with self.assertRaisesRegex(ValueError,'Foreign failure'):r.prior_contract(b,self.q)


class BuildCustody(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.here=self.root/'repair';self.here.mkdir();self.build=self.root/'build-v3';self.build.mkdir()
        self.prep=self.build/'prepare-FIRST';self.prep.mkdir();dump(self.prep/'receipt.json',{'discovered_headers':{}})
        self.output=self.build/'build-FIRST';self.output.mkdir();self.elf=self.output/'old-fixture'
        self.elf.write_bytes(b'inert old object')
        self.supervisor=self.build/'compile-supervision-FIRST';self.supervisor.mkdir()
        self.source=self.root/'numerical-v2';self.source.mkdir()
        original=(r.N/'numerical-v2/iq2xs_exact.cpp').read_bytes()
        (self.source/'iq2xs_exact.cpp').write_bytes(original);(self.here/'iq2xs_exact.cpp').write_bytes(original.replace(r.BEFORE,r.AFTER))
        self.result={'status':'COMPILED_STOP_FOR_SEPARATE_NUMERICAL_QUALIFICATION','passed':True,
            'children':[{'returncode':0,'error':None,'cleanup':[]} for _ in range(7)],
            'actual_inputs':{},'outputs':{str(self.elf):r.sha(self.elf)},
            'native_execution':False,'fixture_execution':False,'GPU_execution':False,'production_changed':False}
        self.supervision={'status':'PASS','error':None,'owned_groups_absence':{'passed':True},'own_claim_released':True,'GPU_lease_mutated':False}
        self.raw=self.build/'raw.json';dump(self.raw,{'actual':'synthetic raw'})
        self.review={'outputs':self.result['outputs'],'raw_sha256':{'raw.json':r.sha(self.raw)}}
        self.q={'mode':'fixture-build','manual_source_reviewed':True,'CPU_both_hosts_passed':True,'actual_build_manually_reviewed':True,
            'children':['fixture-compile','fixture-link'],'aggregate_budget':{'soft_seconds':400,'wall_seconds':600,'cleanup_seconds':200},
            'source_sha256':{'iq2xs_exact.cpp':r.sha(self.here/'iq2xs_exact.cpp')}}
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(r,'HERE',self.here));self.stack.enter_context(patch.object(r,'N',self.root))
        self.stack.enter_context(patch.object(b,'observations',return_value=({},{})))
        self.stack.enter_context(patch.object(b,'inventory',return_value={}))
        self.files=self.stack.enter_context(patch.object(b,'verify_files'))
        self.cpu=self.stack.enter_context(patch.object(r,'cpu_proofs'))
        self.prior=self.stack.enter_context(patch.object(r,'prior_contract'))

    def freeze(self):
        dump(self.output/'receipt.json',self.result);dump(self.supervisor/'result.json',self.supervision)
        for name in ('COMPILE_ROOT_RESULT_REVIEW.json','COMPILE_RESULT_ASTRA_REVIEW.json'):dump(self.build/name,self.review)
        self.q['files']={str(path):r.sha(path) for path in (self.prep/'receipt.json',self.output/'receipt.json',self.supervisor/'result.json',
            self.build/'COMPILE_ROOT_RESULT_REVIEW.json',self.build/'COMPILE_RESULT_ASTRA_REVIEW.json',self.elf,self.raw,
            self.source/'iq2xs_exact.cpp',self.here/'iq2xs_exact.cpp')}
        dump(self.here/'qualification.json',self.q);return r.sha(self.here/'qualification.json')

    def call(self):return r.verify_q(b,self.q,self.freeze())

    def test_positive_exact_build_and_fixture_chain(self):
        self.assertEqual(self.call(),{});self.files.assert_called_once();self.cpu.assert_called_once();self.prior.assert_called_once()

    def test_review_budget_or_third_child_refused_before_hash(self):
        for key in ('manual_source_reviewed','CPU_both_hosts_passed','actual_build_manually_reviewed'):
            self.q[key]=False
            with self.assertRaises(ValueError):self.call()
            self.q[key]=True
        self.q['children'].append('candidate-rebuild')
        with self.assertRaisesRegex(ValueError,'two-child budget'):self.call()
        self.files.assert_not_called()

    def test_changed_fixture_bytes_fail_even_with_updated_source_pin(self):
        path=self.here/'iq2xs_exact.cpp';path.write_bytes(path.read_bytes()+b'\n')
        self.q['source_sha256']['iq2xs_exact.cpp']=r.sha(path)
        with self.assertRaisesRegex(ValueError,'one initializer'):self.call()

    def test_new_fixture_membership_missing_refuses(self):
        pin=self.freeze();self.q['files'].pop(str(self.here/'iq2xs_exact.cpp'))
        with self.assertRaisesRegex(ValueError,'source membership'):r.verify_q(b,self.q,pin)

    def test_original_build_failed_or_cleanup_uncertain_refuses(self):
        for key,val in (('returncode',1),('error','error'),('cleanup',['uncertain'])):
            self.result['children'][0][key]=val
            with self.assertRaisesRegex(ValueError,'seven-child'):self.call()
            self.result['children'][0][key]={'returncode':0,'error':None,'cleanup':[]}[key]

    def test_actual_input_omission_refuses(self):
        self.result['actual_inputs']['/outside/omitted']='b'*64
        with self.assertRaisesRegex(ValueError,'input or output omitted'):self.call()

    def test_original_build_execution_scope_cannot_be_widened(self):
        self.result['fixture_execution']=True
        with self.assertRaisesRegex(ValueError,'scope changed'):self.call()

    def test_claim_or_gpu_lease_mutation_refuses(self):
        self.supervision['own_claim_released']=False
        with self.assertRaisesRegex(ValueError,'ownership closure'):self.call()

    def test_reviewed_output_disagreement_refuses(self):
        self.review['outputs']={}
        with self.assertRaisesRegex(ValueError,'Reviewed outputs'):self.call()

    def test_reviewed_raw_omission_or_escape_refuses(self):
        pin=self.freeze();self.q['files'].pop(str(self.raw))
        with self.assertRaisesRegex(ValueError,'raw missing'):r.verify_q(b,self.q,pin)
        self.review['raw_sha256']={'../outside':'a'*64}
        with self.assertRaisesRegex(ValueError,'Foreign build'):self.call()

    def test_final_qualification_mutation_refuses(self):
        pin=self.freeze();(self.here/'qualification.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Qualification changed'):r.verify_q(b,self.q,pin)


class Imports(unittest.TestCase):
    def test_hash_and_foreign_origin_refused_before_import(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td).resolve()/'inert.py';path.write_text('VALUE = 1\n')
            with patch.object(r.importlib.util,'spec_from_file_location') as spec:
                with self.assertRaisesRegex(ValueError,'Exact pinned'):r.exact_module('repair_inert',path,'0'*64)
                with patch.dict(sys.modules,{'repair_inert':Mock(__file__='/foreign/file.py')}):
                    with self.assertRaisesRegex(ValueError,'Foreign module'):r.exact_module('repair_inert',path,r.sha(path))
                spec.assert_not_called()

    def test_load_build_uses_exact_immutable_path_and_pin(self):
        with patch.object(r,'exact_module',return_value=b) as load:
            self.assertIs(r.load_build(),b)
        self.assertEqual(load.call_args.args[1:],(r.BUILD,r.BUILD_SHA))


class ComposedSupervisor(unittest.TestCase):
    """New execute -> immutable run_child composition; compiler process is synthetic."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(r,'HERE',self.root))
        self.clock=self.stack.enter_context(patch.object(r.time,'monotonic',return_value=1))
        self.stack.enter_context(patch.object(b,'actual_dependencies',return_value={}))
        self.clean=self.stack.enter_context(patch.object(b,'cleanup'))
        self.popen=self.stack.enter_context(patch.object(b.subprocess,'Popen',side_effect=self.spawn))
        self.owned=b.OwnedChildren();self.processes=[];self.mutation=None;self.guard=Mock()

    def spawn(self,argv,**kw):
        pid=50001+len(self.processes);process=Mock(pid=pid,returncode=0);process.poll.return_value=0
        self.processes.append(process)
        name='fixture-compile' if '-c' in argv else 'fixture-link'
        role,cpu,memory,wall=b.resource_class(argv,'-c' in argv)
        actual={'pid':pid,'ppid':os.getpid(),'pgid':pid,'cpu':[cpu,cpu],'as':[memory,memory],
                'nice':15,'environment':dict(b.ENV,TMPDIR=str(kw['cwd']/(name+'.tmp')))}
        if self.mutation:self.mutation(actual,process)
        b.emit(kw['cwd']/(name+'.observed.json'),actual)
        Path(argv[argv.index('-o')+1]).write_bytes(b'inert compiler output')
        self.assertTrue(kw['start_new_session']);self.assertEqual(kw['env']['CUDA_VISIBLE_DEVICES'],'')
        self.assertEqual(kw['env']['OMP_NUM_THREADS'],'1')
        return process

    def call(self):return r.execute(b,{'files':{}},self.guard,self.owned,0,Mock())

    def test_both_steps_use_real_qualified_supervisor_and_record_owned_PIDs(self):
        value=self.call();self.assertEqual([v['pid'] for v in value['children']],[50001,50002])
        self.assertEqual(len(self.owned.children),2);self.assertEqual(self.clean.call_count,2)
        self.assertEqual([v['CPU_s'] for v in value['children']],[120,30])
        self.assertEqual([v['AS_bytes'] for v in value['children']],[4*2**30]*2)
        self.assertTrue(all((self.root/'build-FIRST'/(name+'.json')).is_file() for name in ('fixture-compile','fixture-link')))

    def test_wrong_observed_PID_prevents_link_and_cleans_only_owned_child(self):
        self.mutation=lambda actual,process:actual.update(pid=123)
        with self.assertRaisesRegex(ValueError,'child/cleanup failed'):self.call()
        self.assertEqual(self.popen.call_count,1);self.assertEqual(self.clean.call_args.args[0].pid,50001)
        row=json.loads((self.root/'build-FIRST/fixture-compile.json').read_text())
        self.assertIn('identity/bounds',row['error'])

    def test_wrong_observed_memory_prevents_link(self):
        self.mutation=lambda actual,process:actual.update({'as':[512*2**20]*2})
        with self.assertRaisesRegex(ValueError,'child/cleanup failed'):self.call()
        self.assertEqual(self.popen.call_count,1);self.clean.assert_called_once()

    def test_cleanup_fault_is_registered_and_never_hidden_by_exit_zero(self):
        self.clean.side_effect=ValueError('owned cleanup fault')
        with self.assertRaisesRegex(ValueError,'child/cleanup failed'):self.call()
        self.assertEqual(self.popen.call_count,1);self.assertEqual(len(self.owned.cleanup_faults),1)

    def test_nonzero_compile_never_starts_link(self):
        def mutate(actual,process):process.returncode=1;process.poll.return_value=1
        self.mutation=mutate
        with self.assertRaisesRegex(ValueError,'child/cleanup failed'):self.call()
        self.assertEqual(self.popen.call_count,1);self.clean.assert_called_once()

    def test_deadline_after_spawn_cleans_and_stops_link(self):
        def mutate(actual,process):
            process.poll.side_effect=[None,0];self.clock.return_value=397
        self.mutation=mutate
        with self.assertRaisesRegex(ValueError,'child/cleanup failed'):self.call()
        self.assertEqual(self.popen.call_count,1);self.clean.assert_called_once()
        row=json.loads((self.root/'build-FIRST/fixture-compile.json').read_text())
        self.assertIn('deadline',row['error'])
