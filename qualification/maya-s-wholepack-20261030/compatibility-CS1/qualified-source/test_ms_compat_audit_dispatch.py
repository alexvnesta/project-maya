"""Saved synthetic metadata and mocked process/idle edges; no live actions."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
from contextlib import ExitStack

import ms_compat_audit_dispatch as m


class Temporary:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = Path(self.tmp.name).resolve(); self.addCleanup(self.tmp.cleanup)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(m, 'HERE', self.p)); self.stack.enter_context(patch.object(m, 'E', self.p))
        self.stack.enter_context(patch.object(m, 'R', self.p/'R'))
    def write(self, path, value):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value)); return path
    def read(self, path): return json.loads(Path(path).read_text())


class Qualification(Temporary, unittest.TestCase):
    def setUp(self):
        super().setUp(); pins = {}; files = {}
        self.stack.enter_context(patch.dict(m.sys.modules, {'ms_config':None,'ms_fixtures':None,'ms_runtime':None}))
        for i in range(38):
            name='bootstrap/%d.py'%i; path=self.write(self.p/name,{}); pins[name]=m.sha(path); files[str(path)]=m.sha(path)
        boot=self.write(self.p/'bootstrap.json',{'paths_relative_to_E':pins}); gate=self.write(self.p/'gate.py',{})
        dfile=self.write(self.p/'ms_audit_dispatch.py',{}); self.stack.enter_context(patch.object(m,'D_SHA',m.sha(dfile)))
        d=NS(bootstrap=Mock(return_value=pins),BOOTSTRAP=boot,BOOTSTRAP_SHA=m.sha(boot),GATE=gate,GATE_SHA=m.sha(gate))
        self.stack.enter_context(patch.object(m,'base',return_value=d))
        for f in (boot,gate,dfile): files[str(f)]=m.sha(f)
        groups=[]
        for source,test in m.PAIRS:
            self.write(self.p/source,{}); (self.p/test).write_text('class T:\n def test_one(self): pass\n')
            sm={n:m.sha(self.p/n) for n in (source,test)}; files.update({str(self.p/n):v for n,v in sm.items()})
            groups.append({'source_sha256':sm,'test_ids':[Path(test).stem+'.T.test_one']})
        for n in ('ms_config.py','ms_fixtures.py','ms_runtime.py'): self.write(self.p/n,{}); files[str(self.p/n)]=m.sha(self.p/n)
        self.q={'mode':'compatibility','root_manual_review':True,'astra_manual_review':True,'files':files,'CPU_groups':groups}
        self.runtime=NS(qualified=Mock(side_effect=lambda mode,pin: self.q)); self.loader=self.stack.enter_context(patch.object(m,'load',return_value=self.runtime))
    def pin(self): return m.sha(self.write(self.p/'compatibility-qualification.json',self.q))
    def test_full_q_membership_then_delegated_actual_both_host_contract(self):
        pin=self.pin(); self.assertEqual(m.qualification(pin),self.q)
        self.runtime.qualified.assert_called_once_with('compatibility',pin)
    def test_missing_new_auditor_or_dispatcher_source_refused_before_import(self):
        del self.q['files'][str(self.p/'ms_compat_audit.py')]
        with self.assertRaises(ValueError): m.qualification(self.pin())
        self.loader.assert_not_called()
    def test_omitted_ordered_control_ID_refused(self):
        self.q['CPU_groups'][1]['test_ids']=[]
        with self.assertRaises(ValueError): m.qualification(self.pin())
        self.loader.assert_not_called()
    def test_bootstrap_member_omission_refused(self):
        del self.q['files'][str(self.p/'bootstrap/0.py')]
        with self.assertRaises(ValueError): m.qualification(self.pin())
        self.loader.assert_not_called()
    def test_missing_config_prevents_runtime_import(self):
        del self.q['files'][str(self.p/'ms_config.py')]
        with self.assertRaises(ValueError): m.qualification(self.pin())
        self.loader.assert_not_called()
    def test_failed_existing_runtime_CPU_contract_not_accepted(self):
        self.runtime.qualified.side_effect=ValueError('raw child failure')
        with self.assertRaisesRegex(ValueError,'raw child failure'): m.qualification(self.pin())
    def test_wrong_mode_or_missing_manual_review_refused(self):
        self.q['astra_manual_review']=False
        with self.assertRaises(ValueError): m.qualification(self.pin())
        self.loader.assert_not_called()
    def test_source_change_and_leaf_alias_refused(self):
        pin=self.pin(); (self.p/'ms_config.py').write_text('changed')
        with self.assertRaises(ValueError): m.qualification(pin)
        path=self.p/'ms_config.py'; path.unlink(); path.symlink_to(self.p/'ms_runtime.py')
        with self.assertRaises(ValueError): m.qualification(pin)
        self.loader.assert_not_called()


class Supervisor(Temporary, unittest.TestCase):
    def setUp(self):
        super().setUp(); self.binding={'invocation':'a'*32,'main_pid':101,'native_pid':102,'native_start_ticks':10}
        self.d=NS(fresh_idle=Mock(return_value=self.binding),limits=Mock(),cleanup=Mock(return_value=[]))
        self.stack.enter_context(patch.object(m,'base',return_value=self.d))
        self.qual=self.stack.enter_context(patch.object(m,'qualification',return_value={'files':{}}))
        self.result={'passed':True,'scope':'synthetic audit adapter'}
        self.art=self.stack.enter_context(patch.object(m,'artifact',return_value=self.result))
        self.proc=Mock(pid=123); self.proc.wait.side_effect=self.finish
        self.popen=self.stack.enter_context(patch.object(m.subprocess,'Popen',return_value=self.proc))
    def finish(self,timeout):
        self.assertEqual(timeout,90); root,target=m.paths()
        for name in ('child-observed.json','child-finished.json','result.json'): self.write(root/name,self.result)
        return 0
    def supervision(self): return self.read(m.paths()[0]/'supervision.json')
    def test_success_one_isolated_child_then_supervision_then_publication(self):
        self.assertEqual(m.dispatch('a'*64),0); self.popen.assert_called_once(); self.d.cleanup.assert_called_once_with(self.proc)
        kw=self.popen.call_args.kwargs
        self.assertIs(kw['preexec_fn'],self.d.limits); self.assertTrue(kw['start_new_session'])
        self.assertEqual(kw['stdin'],subprocess.DEVNULL); self.assertEqual(kw['stderr'],subprocess.STDOUT)
        self.assertEqual({k:kw['env'][k] for k in m.ENV},m.ENV)
        terminal=self.read(m.paths()[1]); self.assertEqual(terminal['bounded_child']['pid'],123)
        self.assertEqual(terminal['parent_supervision_sha256'],m.sha(m.paths()[0]/'supervision.json'))
        self.assertTrue(self.supervision()['passed']); self.assertEqual(self.d.fresh_idle.call_count,4)
    def test_existing_attempt_never_starts_second_child(self):
        self.assertEqual(m.dispatch('a'*64),0)
        with self.assertRaises(ValueError): m.dispatch('a'*64)
        self.popen.assert_called_once()
    def test_busy_blocks_hashes_directories_and_child(self):
        self.d.fresh_idle.side_effect=ValueError('busy')
        with self.assertRaises(ValueError): m.dispatch('a'*64)
        self.qual.assert_not_called(); self.popen.assert_not_called(); self.assertFalse(m.paths()[0].exists())
    def test_post_child_busy_preserves_raw_without_posthash_or_publish(self):
        self.d.fresh_idle.side_effect=[self.binding,self.binding,ValueError('busy')]
        self.assertEqual(m.dispatch('a'*64),1); self.assertEqual(self.qual.call_count,1); self.art.assert_not_called()
        self.assertTrue((m.paths()[0]/'result.json').exists()); self.assertFalse(m.paths()[1].exists())
    def test_nonzero_child_never_certifies_success(self):
        self.proc.wait.return_value=1; self.proc.wait.side_effect=None
        self.assertEqual(m.dispatch('a'*64),1); self.d.cleanup.assert_called_once(); self.art.assert_not_called()
        self.assertEqual(self.supervision()['child']['returncode'],1); self.assertFalse(m.paths()[1].exists())
    def test_timeout_and_cleanup_failure_both_preserved(self):
        self.proc.wait.side_effect=subprocess.TimeoutExpired('child',90); self.d.cleanup.return_value=['descendant survived']
        self.assertEqual(m.dispatch('a'*64),1); c=self.supervision()['child']
        self.assertIn('TimeoutExpired',c['error']); self.assertEqual(c['cleanup_errors'],['descendant survived'])
        self.assertFalse(m.paths()[1].exists()); self.art.assert_not_called()
    def test_exited_child_still_has_owned_group_cleanup(self):
        self.d.cleanup.side_effect=RuntimeError('cleanup fault')
        self.assertEqual(m.dispatch('a'*64),1); self.assertIn('cleanup fault',self.supervision()['child']['cleanup_errors'][0])
        self.art.assert_not_called(); self.assertFalse(m.paths()[1].exists())
    def test_popen_failure_keeps_attempt_without_cleanup_foreign_process(self):
        self.popen.side_effect=OSError('start refused')
        self.assertEqual(m.dispatch('a'*64),1); self.d.cleanup.assert_not_called()
        self.assertTrue((m.paths()[0]/'attempt.json').exists()); self.assertIsNone(self.supervision()['child']['pid'])
    def test_partial_parent_receipt_failure_prevents_child(self):
        original=m.write_new
        def write(path,value):
            if Path(path).name=='dispatch-attempt.json': raise OSError('receipt fault')
            return original(path,value)
        with patch.object(m,'write_new',side_effect=write): self.assertEqual(m.dispatch('a'*64),1)
        self.popen.assert_not_called(); self.assertIn('receipt fault',self.supervision()['child']['error'])
    def test_post_child_custody_failure_keeps_raw_unpublished(self):
        self.art.side_effect=ValueError('raw changed')
        self.assertEqual(m.dispatch('a'*64),1); self.assertTrue((m.paths()[0]/'result.json').exists())
        self.assertIn('raw changed',self.supervision()['child']['error']); self.assertFalse(m.paths()[1].exists())
    def test_terminal_write_failure_never_rewrites_supervision_or_raw(self):
        original=m.write_new
        def write(path,value):
            if Path(path)==m.paths()[1]: raise OSError('publication fault')
            return original(path,value)
        with patch.object(m,'write_new',side_effect=write),self.assertRaisesRegex(OSError,'publication fault'): m.dispatch('a'*64)
        self.assertEqual(self.supervision()['terminal_publication'],'NOT_YET_ATTEMPTED')
        self.assertTrue((m.paths()[0]/'result.json').exists()); self.assertFalse(m.paths()[1].exists())


class Child(Temporary, unittest.TestCase):
    def setUp(self):
        super().setUp(); self.pin='a'*64; self.binding={'native_pid':321}; root,_=m.paths()
        self.attempt=self.write(root/'attempt.json',{'stage':'compatibility-terminal','arm':'CS1','qualification_sha256':self.pin,'expected_binding':self.binding})
        self.apin=m.sha(self.attempt); self.doc=self.write(root/'dispatch-attempt.json',{'parent_pid':101,'qualification_sha256':self.pin,'attempt_sha256':self.apin,'retry':False}); self.dpin=m.sha(self.doc)
        self.stack.enter_context(patch.object(m.os,'getppid',return_value=101))
        self.stack.enter_context(patch.object(m.sys,'argv',m.command(self.pin,self.apin,self.dpin)[2:]))
        self.a={'pid':123,'CPU_seconds':[30,30],'Linux_AS_bytes':[m.AS,m.AS],'nice':15,'environment':dict(m.ENV)}
        self.observe=self.stack.enter_context(patch.object(m,'observed',side_effect=lambda:copy.deepcopy(self.a)))
        self.d=NS(fresh_idle=Mock(return_value=self.binding)); self.base=self.stack.enter_context(patch.object(m,'base',return_value=self.d))
        self.q={'files':{str(self.p/'ms_compat_audit.py'):'b'*64}}
        self.qual=self.stack.enter_context(patch.object(m,'qualification',return_value=self.q))
        self.audit=NS(run=Mock(return_value={'passed':True,'synthetic':True}))
        self.loader=self.stack.enter_context(patch.object(m,'load',return_value=self.audit))
    def test_child_observes_before_import_calls_exact_source_entry_once(self):
        def invoke(context):
            self.assertEqual(context,{'qualification_sha256':self.pin,'expected_binding':self.binding,'attempt_sha256':self.apin})
            self.assertTrue((m.paths()[0]/'child-observed.json').exists()); return {'passed':True}
        self.audit.run.side_effect=invoke
        self.assertEqual(m.child(self.pin,self.apin,self.dpin),0); self.assertEqual(self.observe.call_count,2)
        self.assertEqual(self.read(m.paths()[0]/'child-finished.json')['after'],self.a)
        self.audit.run.assert_called_once()
    def test_resource_refusal_precedes_any_bootstrap_import(self):
        self.observe.side_effect=ValueError('bounds')
        with self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.base.assert_not_called(); self.qual.assert_not_called()
    def test_foreign_parent_or_command_cannot_enter_auditor(self):
        with patch.object(m.os,'getppid',return_value=102),self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.audit.run.assert_not_called()
        with patch.object(m.sys,'argv',['other']),self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.audit.run.assert_not_called()
    def test_changed_observed_bounds_keeps_raw_but_prevents_finished_proof(self):
        self.observe.side_effect=[self.a,{**self.a,'nice':14}]
        with self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.assertTrue((m.paths()[0]/'result.json').exists()); self.assertFalse((m.paths()[0]/'child-finished.json').exists())
    def test_post_auditor_busy_preserves_raw_without_finished_proof(self):
        self.d.fresh_idle.side_effect=[self.binding,self.binding,ValueError('busy')]
        with self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.assertTrue((m.paths()[0]/'result.json').exists()); self.assertFalse((m.paths()[0]/'child-finished.json').exists())
    def test_audit_failure_keeps_observer_and_never_finishes(self):
        self.audit.run.side_effect=ValueError('evidence fault')
        with self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.assertTrue((m.paths()[0]/'child-observed.json').exists()); self.assertFalse((m.paths()[0]/'child-finished.json').exists())
    def test_real_observer_requires_own_group_and_actual_environment(self):
        # Call the source function captured from the module before this mock.
        with patch.object(m.sys,'platform','linux'),patch.object(m.os,'getpid',return_value=123),patch.object(m.os,'getpgrp',return_value=124),patch.object(m.os,'getpriority',return_value=15),patch.dict(m.os.environ,m.ENV),patch.object(m.resource,'getrlimit',side_effect=lambda k:(30,30) if k==m.resource.RLIMIT_CPU else (m.AS,m.AS)):
            with self.assertRaises(ValueError): REAL_OBSERVED()
            with patch.object(m.os,'getpgrp',return_value=123):
                self.assertEqual(REAL_OBSERVED()['pid'],123)
                m.os.environ['CUDA_VISIBLE_DEVICES']='0'
                with self.assertRaises(ValueError): REAL_OBSERVED()


REAL_OBSERVED = m.observed


class Artifacts(Temporary, unittest.TestCase):
    def setUp(self):
        super().setUp(); self.pin='a'*64; self.binding={'native_pid':321}; self.root,_=m.paths()
        self.apin=m.sha(self.write(self.root/'attempt.json',{})); self.dpin=m.sha(self.write(self.root/'dispatch-attempt.json',{}))
        self.a={'pid':123,'CPU_seconds':[30,30],'Linux_AS_bytes':[m.AS,m.AS],'nice':15,'environment':dict(m.ENV)}
        self.expected={'CPU':self.a['CPU_seconds'],'AS':self.a['Linux_AS_bytes'],'nice':15,'environment':dict(m.ENV)}
        self.q={'files':{}}
        for n in ('ms_compat_audit.py','ms_runtime.py'): self.write(self.p/n,{}); self.q['files'][str(self.p/n)]=m.sha(self.p/n)
        self.output=self.p/'results/maya-s-compatibility-CS1-20261030T000000Z'; self.meta=self.p/'maintenance';self.meta.mkdir()
        self.raw=self.write(self.output/'raw.json',{'saved':True})
        self.window=self.write(m.R/'windows/20261030T000001Z.json',{})
        self.stack.enter_context(patch.object(m,'load',return_value=NS(owned_paths=Mock(return_value=(self.output,self.meta)))))
        self.write(self.root/'audit-started.json',{'pid':123,'attempt_sha256':self.apin,'retry':False,'observed_before_project_imports':self.expected})
        self.r={'stage':'COMPATIBILITY_TERMINAL','mode':'compatibility','arm':'CS1','passed':True,'qualification_sha256':self.pin,
                'audit_source_sha256':self.q['files'][str(self.p/'ms_compat_audit.py')],'dispatch_attempt_sha256':self.apin,
                'audit_started_sha256':m.sha(self.root/'audit-started.json'),'parent_exit0_cleanup_and_wall90_proof_required':True,
                'selected_identity':{'start_binding':self.binding},'observed_before_project_imports':self.expected,
                'output':str(self.output),'window':str(self.window),'evidence_sha256':{str(self.raw):m.sha(self.raw)}}
        self.r.update(dict.fromkeys(('retry','automatic_next_arm','performance_claim','general_quality_claim','cross_pack_numeric_equivalence','finite_logits_checked','near_full_context_or_output_tested','deployment_admitted'),False))
        self.common={'qualification_sha256':self.pin,'attempt_sha256':self.apin,'dispatch_sha256':self.dpin}
        self.write(self.root/'child-observed.json',{'before':self.a,**self.common}); self.save_result()
        self.c={'pid':123,'returncode':0,'error':None,'cleanup_errors':[],'wall_seconds':.2}
    def save_result(self):
        self.write(self.root/'result.json',self.r); self.write(self.root/'child-finished.json',{'after':self.a,**self.common,'result_sha256':m.sha(self.root/'result.json')})
    def artifact(self):return m.artifact(self.pin,self.q,self.binding,self.apin,self.dpin,self.c)
    def test_matching_real_saved_hashes_and_actual_child_observations(self): self.assertEqual(self.artifact(),self.r)
    def test_pass_label_cannot_override_nonzero_or_cleanup_error(self):
        self.c['returncode']=1
        with self.assertRaises(ValueError):self.artifact()
        self.c['returncode']=0; self.c['cleanup_errors']=['survived']
        with self.assertRaises(ValueError):self.artifact()
    def test_wrong_actual_pid_or_missing_limits_refused(self):
        self.a['pid']=124;self.write(self.root/'child-observed.json',{'before':self.a,**self.common});self.save_result()
        with self.assertRaises(ValueError):self.artifact()
    def test_raw_evidence_mutation_refused(self):
        self.raw.write_text('{}')
        with self.assertRaises(ValueError):self.artifact()
    def test_foreign_evidence_path_refused_before_payload_hash(self):
        path=self.write(self.p/'unrelated.json',{});self.r['evidence_sha256']={str(path):m.sha(path)};self.save_result()
        with self.assertRaises(ValueError):self.artifact()
    def test_performance_or_advance_claim_refused_even_with_matching_bytes(self):
        self.r['automatic_next_arm']=True;self.save_result()
        with self.assertRaises(ValueError):self.artifact()
    def test_auditor_claim_pid_and_attempt_are_bound(self):
        claim=self.read(self.root/'audit-started.json');claim['pid']=999;self.write(self.root/'audit-started.json',claim)
        self.r['audit_started_sha256']=m.sha(self.root/'audit-started.json');self.save_result()
        with self.assertRaises(ValueError):self.artifact()
