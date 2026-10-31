"""Bounded parent custody controls, synthetic files and captured children only."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch
import ae_dispatch as m

class Temporary(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name).resolve();self.addCleanup(self.tmp.cleanup)
    def write(self,name,value):
        p=self.p/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value));return p

class Paths(Temporary):
    def test_exact_two_namespaces(self):
        with patch.object(m,'HERE',self.p):
            for mode in ('prose',):
                for arm in ('A1','B1'):
                    root,target=m.paths(mode,arm);self.assertEqual(root,self.p/mode/arm/'offline-audit-FIRST');self.assertEqual(target,self.p/mode/arm/'terminal-audit.json')
    def test_wrong_mode_arm_traversal_rejected(self):
        for mode,arm in [('quality','QS1'),('prose','A3'),('prose','../A1'),('../coding','B1'),('coding','A1'),('prose','A2'),('prose','B2')]:
            with self.subTest(mode=mode,arm=arm),self.assertRaises(ValueError):m.paths(mode,arm)
    def test_regular_no_alias_hardlink_or_relative(self):
        p=self.write('x',{});s=self.p/'link';s.symlink_to(p)
        with self.assertRaises(ValueError):m.regular(s)
        s.unlink();s.hardlink_to(p)
        with self.assertRaises(ValueError):m.regular(p)
        with self.assertRaises(ValueError):m.regular(Path('relative'))
    def test_unknown_external_window_refused_before_stat(self):
        self.assertFalse(m.allowed_input(m.R/'windows/20261031T000000Z.json'))
        self.assertFalse(m.allowed_input(Path('/unrelated/secret')))
        self.assertTrue(m.allowed_input(m.R/'window.py'))
        self.assertTrue(m.allowed_input(m.R/'windows/20261030T232538Z.json'))
    def test_write_new_preserves_first_bytes(self):
        p=self.p/'first';m.write_new(p,{'x':1})
        with self.assertRaises(FileExistsError):m.write_new(p,{'x':2})
        self.assertEqual(json.loads(p.read_text()),{'x':1})
    def test_foreign_cached_bootstrap_refused(self):
        path=self.p/'maya-s-comparison-v1/model-v1/ms_audit_dispatch.py';path.parent.mkdir(parents=True);path.write_text('source')
        fake=NS(__file__='/foreign.py')
        with patch.object(m,'HERE',self.p/'adaptive-expert-cache-v1/performance-v1'),patch.object(m,'BASE_DISPATCH_SHA',m.sha(path)),patch.dict(m.sys.modules,{'ms_audit_dispatch':fake}),self.assertRaises(ValueError):m.base()

class Bounds(Temporary):
    def proof(self):
        root=self.p/'audit';root.mkdir();target=self.write('terminal',{'passed':True})
        observed={'pid':123,'CPU_seconds':[30,30],'Linux_AS_bytes':[m.AS,m.AS],'nice':15,'environment':m.ENV}
        (root/'observed.json').write_text(json.dumps(observed));finished={'pid':123,'mode':'prose','arm':'A1','qualification_sha256':'a'*64,'target_sha256':m.sha(target),'observed_sha256':m.sha(root/'observed.json')}
        (root/'finished.json').write_text(json.dumps(finished));return root,target,observed,finished
    def test_saved_actual_finished_chain(self):
        root,target,o,f=self.proof();self.assertEqual(m.finished_contract(root,target,'prose','A1','a'*64,123),(o,f))
    def test_changed_result_or_wrong_PID_refused(self):
        root,target,o,f=self.proof()
        with self.assertRaises(ValueError):m.finished_contract(root,target,'prose','A1','a'*64,124)
        target.write_text('{}')
        with self.assertRaises(ValueError):m.finished_contract(root,target,'prose','A1','a'*64,123)
    def test_missing_observed_and_finished_refuse(self):
        root,target,o,f=self.proof();(root/'finished.json').unlink()
        with self.assertRaisesRegex(ValueError,'One regular evidence file'):m.finished_contract(root,target,'prose','A1','a'*64,123)
    def test_actual_bounds_cannot_be_invented(self):
        root,target,o,f=self.proof()
        for key,value in [('CPU_seconds',[120,120]),('Linux_AS_bytes',None),('nice',0),('environment',{})]:
            wrong=copy.deepcopy(o);wrong[key]=value;(root/'observed.json').write_text(json.dumps(wrong));f['observed_sha256']=m.sha(root/'observed.json');(root/'finished.json').write_text(json.dumps(f))
            with self.subTest(key=key),self.assertRaises(ValueError):m.finished_contract(root,target,'prose','A1','a'*64,123)
    def test_fresh_actual_observation_requires_process_group(self):
        with patch.object(m.sys,'platform','linux'),patch.object(m.resource,'getrlimit',side_effect=lambda k:(30,30) if k==m.resource.RLIMIT_CPU else (m.AS,m.AS)),patch.object(m.os,'getpriority',return_value=15),patch.dict(m.os.environ,m.ENV),patch.object(m.os,'getpgrp',return_value=m.os.getpid()+1),self.assertRaises(ValueError):m.observed()
    def test_child_env_failure_before_imports(self):
        with patch.object(m,'observed',side_effect=ValueError('bounds')),patch.object(m.runpy,'run_path') as run,self.assertRaises(ValueError):m.child('prose','A1','a'*64)
        run.assert_not_called()

class Parent(Temporary):
    def setup_parent(self,rc=0,error=None):
        self.stack=[]
        self.addCleanup(lambda:[p.stop() for p in reversed(self.stack)])
        def apply(obj,key,value):
            p=patch.object(obj,key,value);self.stack.append(p);p.start();return value
        apply(m,'HERE',self.p);apply(m,'fresh_idle',Mock(return_value={'native_pid':321}));apply(m,'qualification',Mock(return_value={'files':{}}));apply(m,'cleanup',Mock(return_value=[]))
        proc=NS(pid=123,wait=Mock(side_effect=error,return_value=rc))
        apply(m.subprocess,'Popen',Mock(return_value=proc));return proc
    def test_busy_prevents_directory_hash_or_child(self):
        self.setup_parent();m.fresh_idle.side_effect=ValueError('busy')
        with self.assertRaises(ValueError):m.dispatch('prose','A1','a'*64)
        m.qualification.assert_not_called();m.subprocess.Popen.assert_not_called();self.assertFalse((self.p/'prose').exists())
    def test_source_failure_before_first_attempt(self):
        self.setup_parent();m.qualification.side_effect=ValueError('source')
        with self.assertRaises(ValueError):m.dispatch('prose','A1','a'*64)
        m.subprocess.Popen.assert_not_called();self.assertFalse((self.p/'prose').exists())
    def test_prior_attempt_prevents_replay(self):
        self.setup_parent();root,target=m.paths('prose','A1');root.mkdir(parents=True)
        with self.assertRaises(ValueError):m.dispatch('prose','A1','a'*64)
        m.subprocess.Popen.assert_not_called()
    def test_failed_child_is_preserved_and_never_passes(self):
        p=self.setup_parent(rc=1);self.assertEqual(m.dispatch('prose','A1','a'*64),1)
        root,target=m.paths('prose','A1');c=json.loads((root/'child.json').read_text());self.assertEqual(c['child']['returncode'],1);self.assertIsNone(c['result_sha256']);p.wait.assert_called_once_with(timeout=90)
    def test_timeout_retains_cleanup_and_original_error(self):
        self.setup_parent(error=TimeoutError('wall'));self.assertEqual(m.dispatch('prose','A1','a'*64),1)
        root,target=m.paths('prose','A1');c=json.loads((root/'child.json').read_text());self.assertIn('TimeoutError',c['child']['error']);m.cleanup.assert_called_once()
    def test_child0_missing_finished_is_parent_refusal(self):
        self.setup_parent();self.assertEqual(m.dispatch('prose','A1','a'*64),1)
        root,target=m.paths('prose','A1');c=json.loads((root/'child.json').read_text());self.assertEqual(c['child']['returncode'],0);self.assertTrue(c['child']['cleanup_errors'])
    def positive_files(self,command,**kwargs):
        root,target=m.paths('prose','A1');target.write_text('{"passed":true}')
        observed={'pid':123,'CPU_seconds':[30,30],'Linux_AS_bytes':[m.AS,m.AS],'nice':15,'environment':m.ENV}
        (root/'observed.json').write_text(json.dumps(observed))
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        (root/'finished.json').write_text(json.dumps({'pid':123,'mode':'prose','arm':'A1','qualification_sha256':'a'*64,'target_sha256':digest(target),'observed_sha256':digest(root/'observed.json')}))
        self.assertTrue(kwargs['start_new_session']);self.assertIs(kwargs['preexec_fn'],m.limits)
        self.assertEqual(kwargs['env']['CUDA_VISIBLE_DEVICES'],'')
        return NS(pid=123,wait=Mock(return_value=0))
    def test_successful_dispatch_requires_real_finished_source_and_result_files(self):
        self.setup_parent();m.subprocess.Popen.side_effect=self.positive_files
        self.assertEqual(m.dispatch('prose','A1','a'*64),0)
        root,target=m.paths('prose','A1');record=json.loads((root/'child.json').read_text())
        self.assertEqual(record['result_sha256'],m.sha(target));self.assertEqual(record['child']['cleanup_errors'],[])
        self.assertEqual(record['child']['returncode'],0);self.assertIsNotNone(record['finished_sha256'])
    def test_busy_after_child_does_not_hash_result_or_claim_success(self):
        self.setup_parent();m.subprocess.Popen.side_effect=self.positive_files;m.fresh_idle.side_effect=[{'native_pid':321},None,ValueError('busy')]
        with patch.object(m,'sha',side_effect=AssertionError('No hashing after guard refusal')) as hashed:
            self.assertEqual(m.dispatch('prose','A1','a'*64),1)
        hashed.assert_not_called();root,target=m.paths('prose','A1');self.assertTrue(target.exists())
        record=json.loads((root/'child.json').read_text());self.assertIsNone(record['result_sha256']);self.assertIn('busy',record['child']['cleanup_errors'][0])
    def test_source_membership_rejects_missing_changed_auditor(self):
        with patch.object(m,'HERE',self.p):
            for n in ('ae_dispatch.py','ae_audit.py','ae_runtime.py','ae_config.py','ae_controls.py','ae_owner.py'):(self.p/n).write_text('source')
            with self.assertRaises(ValueError):m.changed_source_proofs({'files':{},'CPU_groups':[]})

class ChildFlow(Temporary):
    def prepare(self):
        self.actual={'pid':123,'CPU_seconds':[30,30],'Linux_AS_bytes':[m.AS,m.AS],'nice':15,'environment':m.ENV}
        root=self.p/'prose/A1/offline-audit-FIRST';root.mkdir(parents=True)
        self.target=self.p/'prose/A1/terminal-audit.json';self.root=root
        self.write('prose/A1/offline-audit-FIRST/dispatch-attempt.json',{'mode':'prose','arm':'A1','qualification_sha256':'a'*64,'retry':False,'parent_pid':os.getppid(),'binding':{'native_pid':321}})
    def test_child_observes_limits_before_project_then_finishes_after_guard(self):
        self.prepare();events=[]
        def run(*a,**kw):
            self.assertTrue((self.root/'observed.json').exists());events.append('project');self.target.write_text('{"passed":true}')
        with patch.object(m,'HERE',self.p),patch.object(m,'observed',side_effect=lambda:(events.append('observed') or self.actual)),patch.object(m,'fresh_idle',side_effect=lambda *a:events.append('idle')),patch.object(m,'qualification',side_effect=lambda *a:events.append('qualification')),patch.object(m.runpy,'run_path',side_effect=run):
            self.assertEqual(m.child('prose','A1','a'*64),0)
        self.assertEqual(events,['observed','idle','qualification','idle','project','observed','idle','qualification'])
        self.assertEqual(json.loads((self.root/'finished.json').read_text())['target_sha256'],m.sha(self.target))
    def test_foreign_parent_refuses_before_project(self):
        self.prepare();p=self.root/'dispatch-attempt.json';value=json.loads(p.read_text());value['parent_pid']+=1;p.write_text(json.dumps(value))
        with patch.object(m,'HERE',self.p),patch.object(m,'observed',return_value=self.actual),patch.object(m.runpy,'run_path') as run,self.assertRaises(ValueError):m.child('prose','A1','a'*64)
        run.assert_not_called();self.assertFalse((self.root/'observed.json').exists())
    def test_busy_after_project_preserves_raw_result_without_finished_hash(self):
        self.prepare()
        with patch.object(m,'HERE',self.p),patch.object(m,'observed',return_value=self.actual),patch.object(m,'fresh_idle',side_effect=[None,None,ValueError('busy')]),patch.object(m,'qualification'),patch.object(m.runpy,'run_path',side_effect=lambda *a,**kw:self.target.write_text('{}')),patch.object(m,'sha') as hashed:
            with self.assertRaises(ValueError):m.child('prose','A1','a'*64)
        hashed.assert_not_called();self.assertTrue(self.target.exists());self.assertFalse((self.root/'finished.json').exists())

if __name__=='__main__':unittest.main()
