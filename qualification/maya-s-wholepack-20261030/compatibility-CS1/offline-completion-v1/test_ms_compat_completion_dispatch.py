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

import ms_compat_completion_dispatch as m


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
        super().setUp(); self.files = {}; self.groups = []
        for source, test in m.PAIRS:
            self.write(self.p/source, {}); (self.p/test).write_text('class T:\n def test_one(self): pass\n')
            sm = {n:m.sha(self.p/n) for n in (source,test)}
            self.files.update({str(self.p/n):h for n,h in sm.items()})
            self.groups.append({'source_sha256':sm,'test_ids':[Path(test).stem+'.T.test_one']})
        original = self.write(self.p/'compatibility-qualification.json', {})
        self.stack.enter_context(patch.object(m,'MODEL_Q_SHA',m.sha(original)))
        self.files[str(original)] = m.sha(original)
        self.model = {'files':{}}
        self.old = NS(qualification=Mock(return_value=self.model))
        self.loader = self.stack.enter_context(patch.object(m,'load',return_value=self.old))
        self.cpu = self.stack.enter_context(patch.object(m,'cpu_contract'))
        self.q = {'mode':'compatibility-offline-completion','root_manual_review':True,'astra_manual_review':True,
                  'model_qualification_sha256':m.MODEL_Q_SHA,'files':self.files,'CPU_groups':self.groups}
    def pin(self): return m.sha(self.write(self.p/'compatibility-completion-qualification.json',self.q))
    def test_new_map_and_original_admission_checked_separately(self):
        self.assertEqual(m.qualification(self.pin()),self.q); self.old.qualification.assert_called_once_with(m.MODEL_Q_SHA)
        self.cpu.assert_called_once_with(self.q)
    def test_missing_changed_source_refused_before_import(self):
        del self.files[str(self.p/'ms_compat_completion.py')]
        with self.assertRaises(ValueError):m.qualification(self.pin())
        self.loader.assert_not_called()
    def test_omitted_control_id_refused(self):
        self.groups[1]['test_ids']=[]
        with self.assertRaises(ValueError):m.qualification(self.pin())
        self.loader.assert_not_called()
    def test_original_admission_or_source_failure_not_suppressed(self):
        self.old.qualification.side_effect=ValueError('original source changed')
        with self.assertRaisesRegex(ValueError,'original source changed'):m.qualification(self.pin())
    def test_original_map_omission_refused(self):
        self.model['files']={'omitted':'a'*64}
        with self.assertRaises(ValueError):m.qualification(self.pin())
    def test_failed_new_cpu_proof_not_suppressed(self):
        self.cpu.side_effect=ValueError('new CPU fault')
        with self.assertRaisesRegex(ValueError,'new CPU fault'):m.qualification(self.pin())
        self.loader.assert_not_called()
    def test_wrong_mode_manual_or_original_pin_refused(self):
        for field,bad in [('mode','compatibility'),('astra_manual_review',False),('model_qualification_sha256','b'*64)]:
            old=self.q[field];self.q[field]=bad
            with self.assertRaises(ValueError):m.qualification(self.pin())
            self.q[field]=old
    def test_source_mutation_or_alias_refused_before_import(self):
        pin=self.pin();f=self.p/'ms_compat_completion.py';f.write_text('changed')
        with self.assertRaises(ValueError):m.qualification(pin)
        f.unlink();f.symlink_to(self.p/'ms_compat_completion_dispatch.py')
        with self.assertRaises(ValueError):m.qualification(pin)
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
        self.attempt=self.write(root/'attempt.json',{'stage':'compatibility-offline-completion','arm':'CS1','qualification_sha256':self.pin,'expected_binding':self.binding})
        self.apin=m.sha(self.attempt); self.doc=self.write(root/'dispatch-attempt.json',{'parent_pid':101,'qualification_sha256':self.pin,'attempt_sha256':self.apin,'retry':False}); self.dpin=m.sha(self.doc)
        self.stack.enter_context(patch.object(m.os,'getppid',return_value=101))
        self.stack.enter_context(patch.object(m.sys,'argv',m.command(self.pin,self.apin,self.dpin)[2:]))
        self.a={'pid':123,'CPU_seconds':[30,30],'Linux_AS_bytes':[m.AS,m.AS],'nice':15,'environment':dict(m.ENV)}
        self.observe=self.stack.enter_context(patch.object(m,'observed',side_effect=lambda:copy.deepcopy(self.a)))
        self.d=NS(fresh_idle=Mock(return_value=self.binding)); self.base=self.stack.enter_context(patch.object(m,'base',return_value=self.d))
        self.q={'files':{str(self.p/'ms_compat_completion.py'):'b'*64}}
        self.qual=self.stack.enter_context(patch.object(m,'qualification',return_value=self.q))
        self.write(self.p/'ms_compat_completion.py',{})
        self.complete=self.stack.enter_context(patch.object(m,'complete',return_value={'passed':True,'synthetic':True}))
    def test_child_observes_before_import_calls_exact_source_entry_once(self):
        def invoke(q,binding):
            self.assertEqual(q,self.q);self.assertEqual(binding,self.binding)
            self.assertTrue((m.paths()[0]/'child-observed.json').exists()); return {'passed':True}
        self.complete.side_effect=invoke
        self.assertEqual(m.child(self.pin,self.apin,self.dpin),0); self.assertEqual(self.observe.call_count,2)
        self.assertEqual(self.read(m.paths()[0]/'child-finished.json')['after'],self.a)
        self.complete.assert_called_once_with(self.q,self.binding)
    def test_resource_refusal_precedes_any_bootstrap_import(self):
        self.observe.side_effect=ValueError('bounds')
        with self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.base.assert_not_called(); self.qual.assert_not_called()
    def test_foreign_parent_or_command_cannot_enter_auditor(self):
        with patch.object(m.os,'getppid',return_value=102),self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.complete.assert_not_called()
        with patch.object(m.sys,'argv',['other']),self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.complete.assert_not_called()
    def test_changed_observed_bounds_keeps_raw_but_prevents_finished_proof(self):
        self.observe.side_effect=[self.a,{**self.a,'nice':14}]
        with self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.assertTrue((m.paths()[0]/'result.json').exists()); self.assertFalse((m.paths()[0]/'child-finished.json').exists())
    def test_post_auditor_busy_preserves_raw_without_finished_proof(self):
        self.d.fresh_idle.side_effect=[self.binding,self.binding,ValueError('busy')]
        with self.assertRaises(ValueError): m.child(self.pin,self.apin,self.dpin)
        self.assertTrue((m.paths()[0]/'result.json').exists()); self.assertFalse((m.paths()[0]/'child-finished.json').exists())
    def test_busy_after_complete_preserves_raw_without_any_post_audit_hash(self):
        events=[]; real_sha=m.sha
        def digest(path):
            events.append('hash:'+Path(path).name);return real_sha(path)
        def complete(q,binding):events.append('complete');return {'passed':True}
        calls=0
        def idle(binding):
            nonlocal calls
            calls+=1
            if calls==3:events.append('post-idle-refusal');raise ValueError('busy')
            return self.binding
        self.d.fresh_idle.side_effect=idle;self.complete.side_effect=complete
        with patch.object(m,'sha',side_effect=digest),self.assertRaisesRegex(ValueError,'busy'):
            m.child(self.pin,self.apin,self.dpin)
        self.assertEqual(events[events.index('complete')+1:],['post-idle-refusal'])
        self.assertTrue((m.paths()[0]/'result.json').exists())
        self.assertFalse((m.paths()[0]/'child-finished.json').exists())
    def test_audit_failure_keeps_observer_and_never_finishes(self):
        self.complete.side_effect=ValueError('evidence fault')
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
        for n in ('ms_compat_completion.py','ms_runtime.py'): self.write(self.p/n,{}); self.q['files'][str(self.p/n)]=m.sha(self.p/n)
        self.output=self.p/'results/maya-s-compatibility-CS1-20261030T000000Z'; self.meta=self.p/'maintenance';self.meta.mkdir()
        self.raw=self.write(self.output/'raw.json',{'saved':True})
        self.window=self.write(m.R/'windows/20261030T000001Z.json',{})
        self.stack.enter_context(patch.object(m,'load',return_value=NS(owned_paths=Mock(return_value=(self.output,self.meta)))))
        self.write(self.root/'audit-started.json',{'pid':123,'attempt_sha256':self.apin,'retry':False,'observed_before_project_imports':self.expected})
        self.r={'stage':'COMPATIBILITY_TERMINAL','mode':'compatibility','arm':'CS1','passed':True,'qualification_sha256':m.MODEL_Q_SHA,'completion_qualification_sha256':self.pin,
                'audit_source_sha256':self.q['files'][str(self.p/'ms_compat_completion.py')],'dispatch_attempt_sha256':self.apin,
                'audit_started_sha256':m.sha(self.root/'audit-started.json'),'parent_exit0_cleanup_and_wall90_proof_required':True,
                'selected_identity':{'start_binding':self.binding},'observed_before_project_imports':self.expected,
                'output':str(self.output),'window':str(self.window),'evidence_sha256':{str(self.raw):m.sha(self.raw)},
                'completion_scope':'EXISTING_CS1_PUBLIC_DEFAULT_OUTPUT_SCHEMA_COMPLETION_ONLY',
                'original_audit_regraded':False,'model_execution_performed':False}
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
    def test_regrade_or_new_execution_claim_refused(self):
        for key in ('original_audit_regraded','model_execution_performed'):
            self.r[key]=True;self.save_result()
            with self.assertRaises(ValueError):self.artifact()
            self.r[key]=False
    def test_auditor_claim_pid_and_attempt_are_bound(self):
        claim=self.read(self.root/'audit-started.json');claim['pid']=999;self.write(self.root/'audit-started.json',claim)
        self.r['audit_started_sha256']=m.sha(self.root/'audit-started.json');self.save_result()
        with self.assertRaises(ValueError):self.artifact()


class CPUProof(Temporary, unittest.TestCase):
    def setUp(self):
        super().setUp(); src=self.write(self.p/'ms_compat_completion.py',{}); inp=self.write(self.p/'input.json',{})
        self.g={'source_sha256':{src.name:m.sha(src)},'input_sha256':{inp.name:m.sha(inp)},'test_ids':['test_new.T.test_one'],'proof_directories':{}}
        self.q={'files':{str(src):m.sha(src),str(inp):m.sha(inp)},'CPU_groups':[self.g]}
        self.docs={}
        for host in ('darwin','linux'):
            root=self.p/('cpu-'+host);self.g['proof_directories'][host]=str(root)
            common={'source_sha256':self.g['source_sha256'],'input_sha256':self.g['input_sha256'],'test_ids':self.g['test_ids'],'environment':dict(m.ENV)}
            r={**common,'passed':True,'controls':1,'CPU_seconds':[30,30],'Linux_AS_bytes':[m.AS,m.AS] if host=='linux' else None,'nice':15}
            c={**common,'pid':123,'returncode':0,'error':None,'cleanup_errors':[],'wall_seconds':.2,'CPU_limit_seconds':30,'Linux_AS_bytes':m.AS if host=='linux' else None,'wall_limit_seconds':90,'nice_increment':15}
            self.docs[host]=(root,r,c);self.save(host)
    def save(self,host):
        root,r,c=self.docs[host]
        for name,doc in (('receipt.json',r),('child.json',c)):
            p=self.write(root/name,doc);self.q['files'][str(p)]=m.sha(p)
        p=root/'child.log';p.write_text('synthetic bounded CPU controls\n');self.q['files'][str(p)]=m.sha(p)
    def test_exact_matching_both_host_raw_proofs(self):m.cpu_contract(self.q)
    def test_nonzero_error_or_cleanup_refused(self):
        root,r,c=self.docs['linux']
        for key,value in [('returncode',1),('error','fault'),('cleanup_errors',['survivor'])]:
            old=c[key];c[key]=value;self.save('linux')
            with self.assertRaises(ValueError):m.cpu_contract(self.q)
            c[key]=old
    def test_observed_CPU_AS_nice_environment_required(self):
        root,r,c=self.docs['linux']
        for key,value in [('CPU_seconds',[31,31]),('Linux_AS_bytes',[m.AS*2,m.AS*2]),('nice',0),('environment',{**m.ENV,'CUDA_VISIBLE_DEVICES':'0'})]:
            old=r[key];r[key]=value;self.save('linux')
            with self.assertRaises(ValueError):m.cpu_contract(self.q)
            r[key]=old
    def test_parent_wall_resource_contract_required(self):
        root,r,c=self.docs['linux']
        for key,value in [('wall_seconds',91),('CPU_limit_seconds',31),('Linux_AS_bytes',m.AS*2),('wall_limit_seconds',91),('nice_increment',0)]:
            old=c[key];c[key]=value;self.save('linux')
            with self.assertRaises(ValueError):m.cpu_contract(self.q)
            c[key]=old
    def test_ids_counts_and_source_maps_must_match(self):
        root,r,c=self.docs['darwin']
        for key,value in [('test_ids',['other']),('controls',0),('source_sha256',{})]:
            old=r[key];r[key]=value;self.save('darwin')
            with self.assertRaises(ValueError):m.cpu_contract(self.q)
            r[key]=old
    def test_missing_raw_membership_refused(self):
        root,_,_=self.docs['linux'];del self.q['files'][str(root/'child.log')]
        with self.assertRaises(ValueError):m.cpu_contract(self.q)
    def test_cpu_input_map_omission_refused(self):
        del self.q['files'][str(self.p/'input.json')]
        with self.assertRaises(ValueError):m.cpu_contract(self.q)


class EntryBinding(Temporary, unittest.TestCase):
    def test_complete_passes_original_admission_and_exact_helpers(self):
        p=self.write(self.p/'compatibility-qualification.json',{'files':{}})
        model=self.read(p);self.stack.enter_context(patch.object(m,'MODEL_Q_SHA',m.sha(p)))
        for name in ('ms_runtime','ms_config','ms_fixtures','ms_audit','ms_quality_audit','ms_compat_audit'):
            model['files'][str(self.p/(name+'.py'))]='b'*64
        self.write(p,model);self.stack.enter_context(patch.object(m,'MODEL_Q_SHA',m.sha(p)))
        modules={name:NS(label=name) for name in ('ms_runtime','ms_config','ms_fixtures','ms_audit','ms_quality_audit','ms_compat_audit')}
        new=NS(audit_saved=Mock(return_value={'passed':True}));q={'files':{str(self.p/'ms_compat_completion.py'):'c'*64}}
        def load(name,path,pin):return new if name=='ms_compat_completion' else modules[name]
        with patch.object(m,'load',side_effect=load):self.assertEqual(m.complete(q,{'native_pid':321}),{'passed':True})
        args=new.audit_saved.call_args
        self.assertEqual(args.args[:5],tuple(modules[k] for k in ('ms_runtime','ms_config','ms_fixtures','ms_audit','ms_quality_audit')))
        self.assertEqual(args.args[5:],(model,m.MODEL_Q_SHA,{'native_pid':321}))
        self.assertIs(args.kwargs['original'],modules['ms_compat_audit'])
