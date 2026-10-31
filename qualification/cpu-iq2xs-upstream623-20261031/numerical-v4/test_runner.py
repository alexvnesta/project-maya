"""Portable custody/sequence controls. Numerical ELF execution is always mocked."""
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import runner as r
import output_parser as parser
from test_output_parser import sample

b = r.load_build()  # exact immutable source, imported only after the CPU driver checks its inputs


def dump(path, value):
    path.write_text(json.dumps(value))


class Contracts(unittest.TestCase):
    def test_exact_forty_six_jobs_and_canonical_argv(self):
        jobs = r.jobs(); self.assertEqual(len(jobs), 46); self.assertEqual(len({j['id'] for j in jobs}), 46)
        self.assertEqual(sum(72 if j['pair'] else 576 for j in jobs), 6336)
        for job in jobs:
            argv = r.command(job)
            self.assertEqual(argv[:5], [str(r.FIXTURE), '--n', str(job['n']), '--expect', job['mode']])
            self.assertEqual(argv[5:], [] if job['pair'] is None else ['--pair', ':'.join(map(str, job['pair']))])

    def test_unknown_job_or_bool_never_reaches_Popen(self):
        job = r.jobs()[0]
        for value in (dict(job,n=True), dict(job,n=512), dict(job,id='foreign'), dict(job,pair=[17,21]),dict(job,extra=1)):
            with self.assertRaises(ValueError): r.command(value)

    def test_parent_dispatch_overrides_do_not_leak(self):
        before = dict(os.environ)
        with patch.dict(os.environ, {k:'host-override' for k in r.SCRUB}):
            optimized = r.child_environment(b,'optimized',Path('/tmp/owned'))
            fallback = r.child_environment(b,'fallback',Path('/tmp/owned'))
            self.assertTrue(all(k not in optimized for k in r.SCRUB))
            self.assertEqual({k:fallback[k] for k in r.SCRUB if k in fallback}, {'STRATA_NO_IQ256':'1'})
            self.assertTrue(all(os.environ[k]=='host-override' for k in r.SCRUB))
            self.assertEqual(optimized['CUDA_VISIBLE_DEVICES'],''); self.assertEqual(optimized['OMP_NUM_THREADS'],'1')
        self.assertEqual(dict(os.environ),before)

    def test_unknown_dispatch_mode_refused(self):
        with self.assertRaisesRegex(ValueError,'mode'): r.child_environment(b,'auto',Path('/tmp'))

    def test_budget_caps_child_and_never_extends_sequence(self):
        self.assertEqual(r.child_budget(10,10),(85.0,100.0))
        self.assertEqual(r.child_budget(10,1000),(5.0,1010.0))
        for now in (1005,1010,1210):
            with self.assertRaisesRegex(ValueError,'soft budget'): r.child_budget(10,now)

    def test_cpu_identity_and_all_allowed_processors(self):
        expected={'vendor_id':'AuthenticAMD','cpu family':'23','model':'49','model name':'synthetic Zen2','stepping':'0'}
        block='vendor_id : AuthenticAMD\ncpu family : 23\nmodel : 49\nmodel name : synthetic Zen2\nstepping : 0\nflags : avx avx2 fma f16c xsave sse2\n'
        text='processor : 0\n'+block+'\nprocessor : 3\n'+block
        self.assertEqual(r.cpu_capability(text,{0,3},expected)['allowed_processors'],[0,3])
        for bad in (text.replace('fma','sse'),text.replace('model : 49','model : 50'),text+'\nprocessor : 0\n'+block):
            with self.assertRaises(ValueError): r.cpu_capability(bad,{0,3},expected)
        with self.assertRaisesRegex(ValueError,'absent'): r.cpu_capability(text,{1},expected)
        with self.assertRaises(ValueError): r.cpu_capability(text,{True},expected)


class Identity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.elf=self.root/'fixture'
        self.elf.write_bytes(b'\x7fELFsynthetic-not-executed');self.elf.chmod(0o700)
        self.patch=patch.object(r,'FIXTURE',self.elf);self.patch.start();self.addCleanup(self.patch.stop)
        self.q={'fixture_sha256':r.sha(self.elf),'files':{str(self.elf):r.sha(self.elf)}}

    def test_exact_synthetic_ELF_identity_without_execution(self):
        self.assertEqual(r.fixture_identity(b,self.q),r.sha(self.elf))

    def test_missing_membership_changed_bytes_or_non_ELF_refused(self):
        with self.assertRaises(ValueError): r.fixture_identity(b,dict(self.q,files={}))
        self.elf.write_bytes(b'changed')
        with self.assertRaises(ValueError): r.fixture_identity(b,self.q)
        self.q={'fixture_sha256':r.sha(self.elf),'files':{str(self.elf):r.sha(self.elf)}}
        with self.assertRaisesRegex(ValueError,'ELF'): r.fixture_identity(b,self.q)

    def test_execute_permission_and_alias_refused(self):
        self.elf.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'permission'): r.fixture_identity(b,self.q)
        other=self.root/'other';self.elf.rename(other);self.elf.symlink_to(other)
        with self.assertRaises(ValueError): r.fixture_identity(b,self.q)

    def test_module_hash_and_foreign_origin_refused_before_import(self):
        path=self.root/'module.py';path.write_text('value=7\n')
        with self.assertRaisesRegex(ValueError,'pinned'): r.exact_module('numerical_synthetic_origin',path,'0'*64)
        with patch.dict(sys.modules,{'numerical_synthetic_origin':Mock(__file__='/foreign/module.py')}):
            with self.assertRaisesRegex(ValueError,'Foreign'): r.exact_module('numerical_synthetic_origin',path,r.sha(path))


class Child(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.job,self.raw=sample(256)
        self.process=Mock(pid=54321,returncode=0);self.process.poll.return_value=0
        self.owned=b.OwnedChildren(self.root/'owned.jsonl');self.guard=Mock();self.files=Mock()
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(r.time,'monotonic',return_value=1))
        self.identity=self.stack.enter_context(patch.object(r,'fixture_identity',return_value='a'*64))
        self.cleanup=self.stack.enter_context(patch.object(b,'cleanup'))
        self.popen=self.stack.enter_context(patch.object(r.subprocess,'Popen',side_effect=self.spawn))

    def spawn(self,argv,**kwargs):
        folder=kwargs['cwd'];env=kwargs['env'];kwargs['stdout'].write(self.raw);kwargs['stdout'].flush()
        actual={'pid':54321,'ppid':os.getpid(),'pgid':54321,'cpu':[30,30],'as':[512*2**20]*2,'nice':15,
                'environment':{k:env[k] for k in (*b.ENV,'TMPDIR')}}
        dump(folder/'observed.json',actual)
        dump(folder/'dispatch-environment.json',{'pid':54321,'pgid':54321,'stage':'PREEXEC_PYTHON',
                                               'dispatch':{k:env.get(k) for k in r.SCRUB}})
        return self.process

    def call(self):
        return r.run_one(b,parser,{},self.job,self.root,self.guard,self.owned,0,self.files)

    def test_success_binds_actual_parent_resources_parser_and_cleanup(self):
        result=self.call();self.assertEqual(result['cases'],576);self.assertEqual(result['pid'],54321)
        self.assertEqual(self.popen.call_args.args[0],r.command(self.job))
        self.assertTrue(self.popen.call_args.kwargs['start_new_session'])
        self.assertEqual(self.files.call_count,2);self.cleanup.assert_called_once_with(self.process,91.0)
        row=json.loads((self.root/self.job['id']/'child.json').read_text())
        self.assertEqual((row['returncode'],row['status'],row['error'],row['cleanup']),(0,'PASS',None,[]))
        self.assertEqual(len(self.owned.children),1)

    def test_initial_busy_or_file_mutation_prevents_any_child(self):
        self.guard.side_effect=ValueError('busy')
        with self.assertRaisesRegex(ValueError,'busy'):self.call()
        self.popen.assert_not_called();self.assertFalse((self.root/self.job['id']).exists())
        self.guard.side_effect=None;self.files.side_effect=ValueError('source changed')
        with self.assertRaisesRegex(ValueError,'source changed'):self.call()
        self.popen.assert_not_called()

    def test_nonzero_keeps_raw_and_stops_posthash(self):
        self.process.returncode=7;self.process.poll.return_value=7
        with self.assertRaisesRegex(ValueError,'nonzero'):self.call()
        self.assertEqual(self.files.call_count,1);self.cleanup.assert_called_once()
        row=json.loads((self.root/self.job['id']/'child.json').read_text())
        self.assertEqual(row['returncode'],7);self.assertEqual(row['status'],'HOLD')
        self.assertFalse((self.root/self.job['id']/'result.json').exists())

    def test_wrong_observed_PID_refuses_and_cleans(self):
        def spawn(*args,**kwargs):
            process=self.spawn(*args,**kwargs);path=kwargs['cwd']/'observed.json';value=json.loads(path.read_text());value['pid']=54322;dump(path,value);return process
        self.popen.side_effect=spawn
        with self.assertRaisesRegex(ValueError,'bounds/identity'):self.call()
        self.cleanup.assert_called_once();self.assertEqual(self.files.call_count,1)

    def test_dispatch_override_witness_refuses(self):
        def spawn(*args,**kwargs):
            process=self.spawn(*args,**kwargs);path=kwargs['cwd']/'dispatch-environment.json';value=json.loads(path.read_text());value['dispatch']['DS4_IQ_OWN']='1';dump(path,value);return process
        self.popen.side_effect=spawn
        with self.assertRaisesRegex(ValueError,'dispatch environment'):self.call()
        self.cleanup.assert_called_once()

    def test_busy_during_child_cleans_group_without_posthash(self):
        self.process.poll.return_value=None
        calls=0
        def guard():
            nonlocal calls
            calls+=1
            if calls==3:raise ValueError('DEFERRED_BUSY_UNTOUCHED_OR_CLEANUP_OWNED_COMPILER')
        self.guard.side_effect=guard
        self.cleanup.side_effect=lambda *args:setattr(self.process.poll,'return_value',-15)
        with self.assertRaisesRegex(ValueError,'DEFERRED_BUSY'):self.call()
        self.cleanup.assert_called_once();self.assertEqual(self.files.call_count,1)

    def test_child_deadline_cleanup_preserves_partial(self):
        self.process.poll.return_value=None
        self.stack.enter_context(patch.object(r.time,'monotonic',side_effect=[1,1,1,87,88]))
        self.cleanup.side_effect=lambda *args:setattr(self.process.poll,'return_value',-15)
        with self.assertRaisesRegex(ValueError,'deadline'):self.call()
        self.cleanup.assert_called_once()

    def test_cleanup_fault_retained_even_after_successful_process(self):
        self.cleanup.side_effect=ValueError('surviving group')
        with self.assertRaisesRegex(ValueError,'surviving group'):self.call()
        self.assertTrue(self.owned.cleanup_faults);self.assertEqual(self.files.call_count,1)

    def test_primary_error_survives_cleanup_and_receipt_fault(self):
        self.process.returncode=7;self.process.poll.return_value=7;self.cleanup.side_effect=ValueError('cleanup failure')
        with patch.object(b,'emit',side_effect=OSError('receipt failure')):
            with self.assertRaisesRegex(ValueError,'nonzero') as caught:self.call()
        self.assertEqual(len(caught.exception.__notes__),2)

    def test_start_failure_retains_pending_spawn_and_no_fake_PID(self):
        self.popen.side_effect=OSError('start failed')
        with self.assertRaisesRegex(OSError,'start failed'):self.call()
        self.cleanup.assert_not_called();self.assertIsNotNone(self.owned.pending)
        row=json.loads((self.root/self.job['id']/'child.json').read_text());self.assertIsNone(row['pid'])

    def test_journal_failure_still_has_handle_for_cleanup(self):
        with patch.object(b.OwnedChildren,'registered',side_effect=lambda process,name: (self.owned.children.append((name,process,process.pid)), (_ for _ in ()).throw(OSError('journal')))):
            with self.assertRaisesRegex(OSError,'journal'):self.call()
        self.cleanup.assert_called_once()

    def test_postchild_source_change_prevents_pass(self):
        self.files.side_effect=[None,ValueError('changed source')]
        with self.assertRaisesRegex(ValueError,'changed source'):self.call()
        self.assertFalse((self.root/self.job['id']/'result.json').exists())

    def test_malformed_numerical_output_cannot_be_satisfied_by_exit_zero(self):
        self.raw=self.raw.replace(b'PASS gu=',b'FAIL gu=',1)
        with self.assertRaisesRegex(ValueError,'inventory'):self.call()
        self.assertFalse((self.root/self.job['id']/'result.json').exists())


class Sequence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(r,'HERE',self.root));self.stack.enter_context(patch.object(r.time,'monotonic',return_value=1))
        self.run=self.stack.enter_context(patch.object(r,'run_one',side_effect=lambda b,p,q,j,*args:{'job':j,'cases':72 if j['pair'] else 576}))

    def test_all46_complete_in_fixed_order_without_model_claim(self):
        result=r.execute(b,parser,{},Mock(),Mock(),0,Mock())
        self.assertEqual(result['case_rows'],6336);self.assertFalse(result['model_or_GPU_execution'])
        self.assertEqual([c.args[3] for c in self.run.call_args_list],r.jobs())

    def test_first_fault_preserves_completed_and_all_unrun_no_retry(self):
        def run(b,p,q,j,*args):
            if j==r.jobs()[2]:raise ValueError('first numerical fault')
            return {'job':j,'cases':576}
        self.run.side_effect=run
        with self.assertRaisesRegex(ValueError,'first numerical fault'):r.execute(b,parser,{},Mock(),Mock(),0,Mock())
        value=json.loads((self.root/'numerical-FIRST/partial.json').read_text())
        self.assertEqual(len(value['completed']),2);self.assertEqual(value['unrun'],r.jobs()[2:]);self.assertFalse(value['retry_authorized'])
        self.assertEqual(self.run.call_count,3)

    def test_existing_attempt_refused_without_child(self):
        (self.root/'numerical-FIRST').mkdir()
        with self.assertRaises(ValueError):r.execute(b,parser,{},Mock(),Mock(),0,Mock())
        self.run.assert_not_called()

    def test_aggregate_budget_refuses_before_first_child(self):
        with patch.object(r.time,'monotonic',return_value=996):
            with self.assertRaisesRegex(ValueError,'soft budget'):r.execute(b,parser,{},Mock(),Mock(),0,Mock())
        self.run.assert_not_called();self.assertFalse((self.root/'numerical-FIRST').exists())


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.here=self.root/'numerical';self.here.mkdir();self.e=self.root/'E';self.e.mkdir();self.state=self.e/'STATE.json'
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
        self.verify=self.stack.enter_context(patch.object(r,'verify_q',return_value=({},parser)))
        self.capability=self.stack.enter_context(patch.object(r,'observed_cpu_capability',return_value={'synthetic':True}))
        self.stack.enter_context(patch.object(b,'process_ticks',return_value=567))
        self.stack.enter_context(patch.object(b,'load_exact',return_value=self.c));self.stack.enter_context(patch.object(b,'load_cas',return_value=self.cas))
        self.gpu=self.stack.enter_context(patch.object(b,'observe_gpu_lease',return_value={'identity':{'inode':10},'main_pid':122}))
        self.space=self.stack.enter_context(patch.object(r.shutil,'disk_usage',return_value=Mock(free=140*2**30)))
        self.execute=self.stack.enter_context(patch.object(r,'execute',return_value={'passed':True}))

    def result(self):return json.loads((self.here/'numerical-supervision-FIRST/result.json').read_text())

    def test_success_releases_only_own_claim_and_preserves_other_state(self):
        self.assertEqual(r.main(self.pin),{'passed':True});self.assertEqual(json.loads(self.state.read_text()),{'active_cpu_build':False,'other':'retained'})
        self.assertTrue(self.result()['owned_groups_absence']['passed']);self.assertTrue(self.result()['own_claim_released'])
        self.assertEqual(self.cas.cas_state.call_count,2);self.host.restore_ds.assert_not_called()

    def test_busy_before_hash_does_not_claim(self):
        self.c.guard.side_effect=ValueError('busy')
        with self.assertRaisesRegex(ValueError,'busy'):r.main(self.pin)
        self.verify.assert_not_called();self.execute.assert_not_called();self.assertFalse((self.e/'cpu-build.lock').exists())

    def test_wrong_owner_root_or_GPU_lease_refuses_before_hash(self):
        self.q['selected_binding']={}
        with self.assertRaisesRegex(ValueError,'owner'):r.main(self.pin)
        self.q['selected_binding']=self.binding;self.space.return_value=Mock(free=135*2**30)
        with self.assertRaisesRegex(ValueError,'Root136'):r.main(self.pin)
        self.space.return_value=Mock(free=140*2**30);self.gpu.side_effect=ValueError('GPU lease')
        with self.assertRaisesRegex(ValueError,'GPU lease'):r.main(self.pin)
        self.verify.assert_not_called();self.execute.assert_not_called()

    def test_CPU_capability_refusal_precedes_lease_and_claim(self):
        self.capability.side_effect=ValueError('AVX2 required')
        with self.assertRaisesRegex(ValueError,'AVX2'):r.main(self.pin)
        self.assertFalse((self.e/'cpu-build.lock').exists());self.cas.cas_state.assert_not_called()

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
        def fail(*args):args[4].starting('pending');raise OSError('spawn failed')
        self.execute.side_effect=fail
        with self.assertRaisesRegex(OSError,'spawn failed'):r.main(self.pin)
        self.assertTrue(json.loads(self.state.read_text())['active_cpu_build']);self.assertFalse(self.result()['owned_groups_absence']['passed'])

    def test_cleanup_fault_prevents_release_even_without_live_process(self):
        def fail(*args):args[4].cleanup_failed('job',ValueError('cleanup'));raise ValueError('numerical fault')
        self.execute.side_effect=fail
        with self.assertRaisesRegex(ValueError,'numerical fault'):r.main(self.pin)
        self.assertFalse(self.result()['own_claim_released']);self.assertTrue(json.loads(self.state.read_text())['active_cpu_build'])

    def test_surviving_group_retains_claim_no_automatic_second_cleanup(self):
        process=Mock(pid=54321);process.poll.return_value=0
        def fail(*args):args[4].starting('job');args[4].registered(process,'job');raise ValueError('partial')
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
            def finish(*args):clock.return_value=1201;return {'passed':True}
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


class BuildCustody(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.here=self.root/'numerical-v3';self.here.mkdir();self.build=self.root/'build-v3';self.build.mkdir()
        self.prep=self.build/'prepare-FIRST';self.prep.mkdir();dump(self.prep/'receipt.json',{'discovered_headers':{}})
        self.output=self.build/'build-FIRST';self.output.mkdir();self.elf=self.output/'iq2xs_exact'
        self.elf.write_bytes(b'\x7fELFnot-executed');self.elf.chmod(0o700)
        self.supervisor=self.build/'compile-supervision-FIRST';self.supervisor.mkdir()
        self.source=self.root/'numerical-v2';self.source.mkdir();(self.source/'iq2xs_exact.cpp').write_text('synthetic source')
        self.result={'status':'COMPILED_STOP_FOR_SEPARATE_NUMERICAL_QUALIFICATION','passed':True,
            'children':[{'returncode':0,'error':None,'cleanup':[]} for _ in range(7)],
            'actual_inputs':{},'outputs':{str(self.elf):r.sha(self.elf)},
            'native_execution':False,'fixture_execution':False,'GPU_execution':False,'production_changed':False}
        self.supervision={'status':'PASS','error':None,'owned_groups_absence':{'passed':True},'own_claim_released':True,'GPU_lease_mutated':False}
        self.raw=self.build/'raw.json';dump(self.raw,{'actual':'synthetic raw'})
        self.review={'outputs':self.result['outputs'],'raw_sha256':{'raw.json':r.sha(self.raw)}}
        self.q={'mode':'numerical','manual_source_reviewed':True,'CPU_both_hosts_passed':True,'actual_build_manually_reviewed':True,
            'jobs':r.jobs(),'aggregate_budget':{'soft_seconds':1000,'wall_seconds':1200,'cleanup_seconds':200},
            'fixture_sha256':r.sha(self.elf),'source_sha256':{'output_parser.py':'a'*64}}
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name,value in {'HERE':self.here,'N':self.root,'FIXTURE':self.elf,'OLD_FIXTURE':self.elf,'FIXTURE_SOURCE_SHA':r.sha(self.source/'iq2xs_exact.cpp')}.items():self.stack.enter_context(patch.object(r,name,value))
        self.stack.enter_context(patch.object(b,'observations',return_value=({},{})))
        self.stack.enter_context(patch.object(b,'inventory',return_value={}))
        self.files=self.stack.enter_context(patch.object(b,'verify_files'))
        self.cpu=self.stack.enter_context(patch.object(r,'cpu_proofs'))
        self.module=self.stack.enter_context(patch.object(r,'exact_module',return_value=parser))
        self.repair=self.stack.enter_context(patch.object(r,'repaired_build_proof'))

    def freeze(self):
        dump(self.output/'receipt.json',self.result);dump(self.supervisor/'result.json',self.supervision)
        for name in ('COMPILE_ROOT_RESULT_REVIEW.json','COMPILE_RESULT_ASTRA_REVIEW.json'):dump(self.build/name,self.review)
        self.q['files']={str(path):r.sha(path) for path in (self.prep/'receipt.json',self.output/'receipt.json',self.supervisor/'result.json',
            self.build/'COMPILE_ROOT_RESULT_REVIEW.json',self.build/'COMPILE_RESULT_ASTRA_REVIEW.json',self.elf,self.raw,self.source/'iq2xs_exact.cpp')}
        dump(self.here/'qualification.json',self.q);return r.sha(self.here/'qualification.json')

    def call(self):return r.verify_q(b,self.q,self.freeze())

    def test_complete_synthetic_actual_build_custody(self):
        observed,p=r.verify_q(b,self.q,self.freeze());self.assertIs(p,parser);self.files.assert_called_once();self.cpu.assert_called_once()

    def test_review_flags_and_job_budget_mutation_refused_before_scan(self):
        for key in ('manual_source_reviewed','CPU_both_hosts_passed','actual_build_manually_reviewed'):
            self.q[key]=False
            with self.assertRaises(ValueError):self.call()
            self.q[key]=True
        self.q['aggregate_budget']['soft_seconds']=1200
        with self.assertRaisesRegex(ValueError,'budget'):self.call()
        self.files.assert_not_called()

    def test_missing_failed_or_cleanup_uncertain_build_refused(self):
        for key,val in (('returncode',1),('error','error'),('cleanup',['uncertain'])):
            self.result['children'][0][key]=val
            with self.assertRaisesRegex(ValueError,'seven-child'):self.call()
            self.result['children'][0][key]={'returncode':0,'error':None,'cleanup':[]}[key]
        self.result['children'].pop()
        with self.assertRaisesRegex(ValueError,'seven-child'):self.call()

    def test_actual_input_omission_refuses(self):
        self.result['actual_inputs']['/outside/omitted']='b'*64
        with self.assertRaisesRegex(ValueError,'closure omitted'):self.call()

    def test_build_execution_scope_cannot_be_widened(self):
        self.result['fixture_execution']=True
        with self.assertRaisesRegex(ValueError,'Build-only'):self.call()

    def test_supervision_failure_or_claim_retained_refuses(self):
        for key,val in (('own_claim_released',False),('GPU_lease_mutated',True),('status','HOLD')):
            prior=self.supervision[key];self.supervision[key]=val
            with self.assertRaisesRegex(ValueError,'ownership closure'):self.call()
            self.supervision[key]=prior

    def test_reviewed_output_disagreement_refuses(self):
        self.review['outputs']={}
        with self.assertRaisesRegex(ValueError,'Reviewed build outputs'):self.call()

    def test_missing_review_raw_membership_and_escape_refused(self):
        pin=self.freeze();self.q['files'].pop(str(self.raw))
        with self.assertRaisesRegex(ValueError,'raw closure'):r.verify_q(b,self.q,pin)
        self.review['raw_sha256']={'../outside': 'a'*64}
        with self.assertRaisesRegex(ValueError,'raw closure'):self.call()

    def test_fixture_not_compiled_output_refuses(self):
        self.result['outputs']={};self.review['outputs']={}
        with self.assertRaisesRegex(ValueError,'not actual build output'):self.call()

    def test_qualification_mutation_after_checks_refuses_parser_import(self):
        pin=self.freeze();(self.here/'qualification.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Qualification changed'):r.verify_q(b,self.q,pin)
        self.module.assert_not_called()


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


class PortableEnvironment(unittest.TestCase):
    def test_real_small_python_children_prove_scrub_without_ELF_or_Mac_AS_claim(self):
        import cpu_driver as d
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            for mode in ('optimized','fallback'):
                folder=root/mode;folder.mkdir()
                with patch.dict(os.environ,{key:'inherited-override' for key in r.SCRUB}):
                    env=r.child_environment(b,mode,folder)
                code='import json,os; print(json.dumps({k:os.environ.get(k) for k in '+repr(r.SCRUB)+'}))'
                with patch.object(d,'environment',return_value=env):
                    result=d.supervise([sys.executable,'-I','-B','-c',code],folder,run_seconds=5,wall_seconds=7)
                self.assertEqual((result['returncode'],result['error'],result['cleanup']),(0,None,[]))
                self.assertEqual(json.loads((folder/'child.log').read_text()),{key:('1' if key=='STRATA_NO_IQ256' and mode=='fallback' else None) for key in r.SCRUB})
                self.assertFalse(d.group_alive(result['pid']))


class ActualCPUInventory(unittest.TestCase):
    def setUp(self):
        self.path=r.HERE/'PHYSICAL_CPU_CAPABILITY.json';self.receipt=json.loads(self.path.read_text())
        self.q={'files':{str(self.path):r.CPU_RECEIPT_SHA}}
        self.text='\n\n'.join('\n'.join(['processor : '+str(row['processor']),
            'vendor_id : '+row['vendor_id'],'cpu family : '+str(row['cpu_family']),
            'model : '+str(row['model']),'stepping : '+str(row['stepping']),'model name : '+row['model_name'],
            'flags : '+' '.join(k for k,v in row['required_flags'].items() if v is True)]) for row in self.receipt['processors'])
        original=Path.read_text
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(Path,'read_text',autospec=True,side_effect=lambda path,*a,**kw:self.text if str(path)=='/proc/cpuinfo' else original(path,*a,**kw)))
        self.affinity=self.stack.enter_context(patch.object(r.os,'sched_getaffinity',return_value=set(self.receipt['allowed_processor_ids']),create=True))

    def test_actual_saved_64_cpu_source_metadata_and_identity(self):
        self.assertEqual(r.sha(self.path),r.CPU_RECEIPT_SHA)
        value=r.observed_cpu_capability(self.q)
        self.assertEqual(value['allowed_processors'],list(range(64)))
        self.assertEqual(value['identity'],{'vendor_id':'AuthenticAMD','cpu family':'23','model':'49','stepping':'0',
                                          'model name':'AMD Ryzen Threadripper 3970X 32-Core Processor'})

    def test_affinity_change_or_missing_receipt_membership_refuses(self):
        self.affinity.return_value={0}
        with self.assertRaisesRegex(ValueError,'affinity differs'):r.observed_cpu_capability(self.q)
        self.affinity.return_value=set(range(64))
        with self.assertRaisesRegex(ValueError,'custody'):r.observed_cpu_capability({'files':{}})

    def test_one_allowed_CPU_losing_AVX2_cannot_be_hidden(self):
        self.text=self.text.replace('flags : avx avx2','flags : avx',1)
        with self.assertRaisesRegex(ValueError,'AVX2'):r.observed_cpu_capability(self.q)


class RepairedBuildCustody(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.repair=self.root/'fixture-repair-v4';self.repair.mkdir();self.output=self.repair/'build-FIRST';self.output.mkdir()
        self.supervisor=self.repair/'build-supervision-FIRST';self.supervisor.mkdir()
        self.old=self.root/'numerical-v2';self.old.mkdir();(self.old/'iq2xs_exact.cpp').write_text('old synthetic')
        (self.repair/'iq2xs_exact.cpp').write_text('new synthetic');(self.repair/'build.py').write_text('# inert')
        self.elf=self.output/'iq2xs_exact';self.elf.write_bytes(b'\x7fELFsynthetic');self.obj=self.output/'iq2xs_exact.cpp.o';self.obj.write_bytes(b'synthetic object')
        self.helper=Mock();self.helper.commands.return_value=[('fixture-compile',['synthetic-compile'],True,self.obj,Path('/dep1')),('fixture-link',['synthetic-link'],False,self.elf,Path('/dep2'))]
        self.helper.command_contract.side_effect=lambda b,f,d,j:('compile',120,4*2**30,300) if j[0]=='fixture-compile' else ('link',30,4*2**30,90)
        self.rows=[{'argv':['synthetic-compile'],'returncode':0,'error':None,'cleanup':[],'role':'compile','CPU_s':120,'AS_bytes':4*2**30,'wall_s':300},
                   {'argv':['synthetic-link'],'returncode':0,'error':None,'cleanup':[],'role':'link','CPU_s':30,'AS_bytes':4*2**30,'wall_s':90}]
        self.built={'status':'FIXTURE_REBUILT_STOP_FOR_NEW_NUMERICAL_QUALIFICATION','passed':True,'children':self.rows,
          'candidate_rebuilt':False,'native_execution':False,'fixture_execution':False,'GPU_execution':False,'production_changed':False,
          'outputs':{str(self.elf):r.sha(self.elf),str(self.obj):r.sha(self.obj)},'actual_inputs':{}}
        self.supervision={'status':'PASS','error':None,'owned_groups_absence':{'passed':True},'own_claim_released':True}
        self.raw=self.repair/'raw.json';dump(self.raw,{'test':'synthetic'})
        self.review={'outputs':dict(self.built['outputs']),'raw_sha256':{'raw.json':r.sha(self.raw)}}
        self.q={'fixture_sha256':r.sha(self.elf),'files':{}}
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for key,val in {'N':self.root,'REPAIR':self.repair,'FIXTURE':self.elf,'REPAIR_BUILD_SHA':r.sha(self.repair/'build.py')}.items():self.stack.enter_context(patch.object(r,key,val))
        self.module=self.stack.enter_context(patch.object(r,'exact_module',return_value=self.helper))
        self.stack.enter_context(patch.object(b,'observations',return_value=({},{})))

    def freeze(self):
        dump(self.output/'receipt.json',self.built);dump(self.supervisor/'result.json',self.supervision)
        for name in ('BUILD_ROOT_RESULT_REVIEW.json','BUILD_RESULT_ASTRA_REVIEW.json'):dump(self.repair/name,self.review)
        self.q['files']={str(x):r.sha(x) for x in self.repair.rglob('*') if x.is_file()}

    def call(self):self.freeze();r.repaired_build_proof(b,self.q)

    def test_only_exact_two_child_repaired_build_is_accepted(self):
        self.call();self.helper.prior_contract.assert_called_once_with(b,self.q)
        self.helper.fixture_contract.assert_called_once_with(b'old synthetic',b'new synthetic')

    def test_missing_helper_membership_refuses_before_import(self):
        self.freeze();self.q['files'].pop(str(self.repair/'build.py'))
        with self.assertRaisesRegex(ValueError,'helper absent'):r.repaired_build_proof(b,self.q)
        self.module.assert_not_called()

    def test_original_failure_or_candidate_custody_refusal_is_not_masked(self):
        self.helper.prior_contract.side_effect=ValueError('old HOLD raw changed')
        with self.assertRaisesRegex(ValueError,'HOLD raw'):self.call()
        self.helper.fixture_contract.assert_not_called()

    def test_one_line_contract_refusal_cannot_be_bypassed(self):
        self.helper.fixture_contract.side_effect=ValueError('extra source change')
        with self.assertRaisesRegex(ValueError,'extra source'):self.call()

    def test_failed_partial_or_extra_build_child_refuses(self):
        self.built['children']=self.rows[:1]
        with self.assertRaisesRegex(ValueError,'two-child'):self.call()
        self.built['children']=self.rows;self.rows[0]['returncode']=1
        with self.assertRaisesRegex(ValueError,'command/resource/exit'):self.call()

    def test_changed_command_limits_or_uncertain_cleanup_refuses(self):
        for key,val in (('argv',['foreign']),('CPU_s',121),('AS_bytes',8*2**30),('wall_s',301),('cleanup',['uncertain'])):
            old=self.rows[0][key];self.rows[0][key]=val
            with self.assertRaisesRegex(ValueError,'command/resource/exit'):self.call()
            self.rows[0][key]=old

    def test_any_execution_scope_widening_refuses(self):
        for key in ('candidate_rebuilt','native_execution','fixture_execution','GPU_execution','production_changed'):
            self.built[key]=True
            with self.assertRaisesRegex(ValueError,'scope differs'):self.call()
            self.built[key]=False

    def test_unpinned_actual_input_or_extra_output_refuses(self):
        self.built['actual_inputs']['/foreign/input']='a'*64
        with self.assertRaisesRegex(ValueError,'closure omitted'):self.call()
        self.built['actual_inputs']={};self.built['outputs'][str(self.raw)]=r.sha(self.raw)
        with self.assertRaisesRegex(ValueError,'output differs'):self.call()

    def test_failed_supervision_or_retained_claim_refuses(self):
        for key,val in (('status','HOLD'),('own_claim_released',False),('owned_groups_absence',{'passed':False})):
            old=self.supervision[key];self.supervision[key]=val
            with self.assertRaisesRegex(ValueError,'ownership closure'):self.call()
            self.supervision[key]=old

    def test_reviewed_output_disagreement_refuses(self):
        self.review['outputs']={}
        with self.assertRaisesRegex(ValueError,'Reviewed repaired outputs'):self.call()

    def test_empty_missing_or_escaping_review_raw_map_refuses(self):
        self.review['raw_sha256']={}
        with self.assertRaisesRegex(ValueError,'raw map empty'):self.call()
        self.review['raw_sha256']={'../escape':'a'*64}
        with self.assertRaisesRegex(ValueError,'raw closure'):self.call()
        self.review['raw_sha256']={'raw.json':r.sha(self.raw)};self.freeze();self.q['files'].pop(str(self.raw))
        with self.assertRaisesRegex(ValueError,'raw closure'):r.repaired_build_proof(b,self.q)
