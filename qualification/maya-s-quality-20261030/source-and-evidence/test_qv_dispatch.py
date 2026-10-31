"""CPU-only negative and boundary controls for serial saved-evidence dispatch."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch
import qv_dispatch as d


class Dispatch(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name).resolve();self.here=self.root/'mode';self.here.mkdir()
        for key,value in (('HERE',self.here),('E',self.root)):
            p=patch.object(d,key,value);p.start();self.addCleanup(p.stop)
        self.pin='a'*64;self.q={'files':{str(self.here/'qv_dispatch.py'):'b'*64}}
        self.sources=copy.deepcopy(self.q['files'])
        self.actual={'pid':4242,'CPU_seconds':[30,30],'Linux_AS_bytes':[d.AS,d.AS],
                     'nice':15,'environment':dict(d.ENV)}
        self.binding={'native_pid':99}

    def fake_completed(self,stage='metadata',index=None):
        root,name,target=d.stage_contract('QS0',stage,index)
        root.mkdir(parents=True,exist_ok=True)
        meta={'arm':'QS0','stage':'METADATA','passed':False,'actual_native_pid':123,'qualification_sha256':self.pin,'metadata_passed':True,
              'audit_source_sha256':self.sources,'selected_identity':{'start_binding':self.binding}}
        if not (root/'metadata.json').exists():d.write_new(root/'metadata.json',meta)
        if target!=root/'metadata.json':d.write_new(target,{'stage':'FINITE_SCAN' if stage=='scan' else 'COMPLETE','arm':'QS0',
            'qualification_sha256':self.pin,'passed':True,'index':index,'native_pid':123,'finite_scans_in_separate_bounded_children':True})
        d.write_new(root/(name+'.observed.json'),{**self.actual,'arm':'QS0','stage':name,'qualification_sha256':self.pin})
        d.write_new(root/(name+'.finished.json'),{'pid':self.actual['pid'],'arm':'QS0','stage':name,'qualification_sha256':self.pin,
                    'target_sha256':d.sha(target),'observed_sha256':d.sha(root/(name+'.observed.json'))})
        return Mock(pid=4242,wait=Mock(return_value=0))

    def run_dispatch(self,popen=None,stage='metadata',index=None):
        if stage!='metadata':
            root,_,_=d.stage_contract('QS0',stage,index);root.mkdir(parents=True,exist_ok=True)
            meta=root/'metadata.json'
            if not meta.exists():d.write_new(meta,{'arm':'QS0','stage':'METADATA','passed':False,'actual_native_pid':123,'qualification_sha256':self.pin,'metadata_passed':True,
                'audit_source_sha256':self.sources,'selected_identity':{'start_binding':self.binding}})
        if popen is None:popen=lambda *a,**k:self.fake_completed(stage,index)
        with patch.object(d,'fresh_idle',return_value=self.binding),patch.object(d,'qualification',return_value=self.q),\
             patch.object(d.subprocess,'Popen',side_effect=popen) as launch,patch.object(d,'cleanup',return_value=[]):
            rc=d.dispatch('QS0',stage,index,self.pin)
        return rc,launch

    def test_exact_metadata_scan_and_assembly_names(self):
        self.assertEqual(d.stage_contract('QS0','metadata',None)[1],'metadata')
        self.assertEqual(d.stage_contract('QS1','scan',4)[1],'scan-4')
        self.assertEqual(d.stage_contract('QS0','assemble',None)[2],self.here/'QS0/terminal-audit.json')

    def test_invalid_arm_stage_bool_or_index_rejected(self):
        for args in (('N0','metadata',None),('QS0','all',None),('QS0','scan',True),
                     ('QS0','scan',0),('QS0','scan',5),('QS0','metadata',1)):
            with self.subTest(args=args),self.assertRaises(ValueError):d.stage_contract(*args)

    def test_busy_guard_precedes_hash_output_and_child(self):
        with patch.object(d,'fresh_idle',side_effect=ValueError('busy')),patch.object(d,'qualification') as q,\
             patch.object(d.subprocess,'Popen') as launch:
            with self.assertRaisesRegex(ValueError,'busy'):d.dispatch('QS0','metadata',None,self.pin)
        q.assert_not_called();launch.assert_not_called();self.assertFalse((self.here/'QS0').exists())

    def test_changed_qualification_precedes_outputs_and_child(self):
        with patch.object(d,'fresh_idle',return_value=self.binding),patch.object(d,'qualification',side_effect=ValueError('changed')),\
             patch.object(d.subprocess,'Popen') as launch:
            with self.assertRaisesRegex(ValueError,'changed'):d.dispatch('QS0','metadata',None,self.pin)
        launch.assert_not_called();self.assertFalse((self.here/'QS0').exists())

    def test_success_pins_actual_child_and_result(self):
        rc,launch=self.run_dispatch();self.assertEqual(rc,0)
        root,_,_=d.stage_contract('QS0','metadata',None);r=json.loads((root/'metadata.child.json').read_text())
        self.assertEqual(r['child']['pid'],4242);self.assertEqual(r['result_sha256'],d.sha(root/'metadata.json'))
        self.assertEqual(r['observed_child_sha256'],d.sha(root/'metadata.observed.json'))
        self.assertEqual(r['audit_source_sha256'],self.sources)
        kwargs=launch.call_args.kwargs;self.assertIs(kwargs['preexec_fn'],d.limits)
        self.assertTrue(kwargs['start_new_session']);self.assertEqual({k:kwargs['env'][k] for k in d.ENV},d.ENV)
        self.assertEqual(kwargs['stdin'],subprocess.DEVNULL)

    def test_scan_selects_one_file_no_multi_scan_switch(self):
        rc,launch=self.run_dispatch(stage='scan',index=3);self.assertEqual(rc,0)
        argv=launch.call_args.args[0];self.assertEqual(argv[-2:],['--index','3'])
        self.assertEqual(argv.count('--stage'),1);self.assertEqual(argv[argv.index('--stage')+1],'scan')

    def test_existing_attempt_blocks_replay(self):
        root,name,_=d.stage_contract('QS0','metadata',None);root.mkdir(parents=True)
        (root/(name+'.dispatch-attempt.json')).write_text('{}')
        with self.assertRaisesRegex(ValueError,'no retry'):self.run_dispatch()

    def test_existing_result_never_adopted(self):
        root,_,target=d.stage_contract('QS0','metadata',None);root.mkdir(parents=True);target.write_text('{}')
        with self.assertRaisesRegex(ValueError,'existing stage'):self.run_dispatch()

    def test_output_ancestor_symlink_rejected(self):
        (self.here/'QS0').symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'alias'):self.run_dispatch()

    def test_timeout_preserved_as_failed_child(self):
        p=Mock(pid=4242,wait=Mock(side_effect=subprocess.TimeoutExpired('saved-audit',90)))
        rc,_=self.run_dispatch(popen=lambda *a,**k:p);self.assertEqual(rc,1)
        root,_,_=d.stage_contract('QS0','metadata',None);r=json.loads((root/'metadata.child.json').read_text())
        self.assertIn('TimeoutExpired',r['child']['error']);self.assertIsNone(r['child']['returncode'])
        self.assertFalse(r['passed']);self.assertTrue((root/'metadata.dispatch-attempt.json').exists())

    def test_launch_exception_preserves_attempt(self):
        def fail(*a,**k):raise OSError('cannot launch')
        rc,_=self.run_dispatch(popen=fail);self.assertEqual(rc,1)
        root,_,_=d.stage_contract('QS0','metadata',None);r=json.loads((root/'metadata.child.json').read_text())
        self.assertIsNone(r['child']['pid']);self.assertIn('OSError',r['child']['error'])

    def test_nonzero_child_cannot_certify_existing_output(self):
        def failed(*a,**k):
            p=self.fake_completed();p.wait.return_value=1;return p
        rc,_=self.run_dispatch(popen=failed);self.assertEqual(rc,1)
        root,_,_=d.stage_contract('QS0','metadata',None);r=json.loads((root/'metadata.child.json').read_text())
        self.assertFalse(r['passed']);self.assertEqual(r['child']['returncode'],1)

    def test_actual_observed_limits_are_required(self):
        for key,value in (('pid',4040),('CPU_seconds',[31,31]),('Linux_AS_bytes',[d.AS+1]*2),
                          ('nice',0),('environment',{})):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                with patch.object(d,'HERE',Path(tmp).resolve()):
                    before=self.actual;self.actual={**before,key:value}
                    try:rc,_=self.run_dispatch();self.assertEqual(rc,1)
                    finally:self.actual=before

    def test_post_stage_map_drift_blocks_success(self):
        def changed(*a,**k):
            p=self.fake_completed();root,_,_=d.stage_contract('QS0','metadata',None)
            x=json.loads((root/'metadata.json').read_text());x['audit_source_sha256']={};(root/'metadata.json').write_text(json.dumps(x))
            return p
        rc,_=self.run_dispatch(popen=changed);self.assertEqual(rc,1)

    def test_child_records_observation_before_exact_auditor_entry(self):
        root,_,target=d.stage_contract('QS0','metadata',None);root.mkdir(parents=True)
        d.write_new(root/'metadata.dispatch-attempt.json',{'arm':'QS0','stage':'metadata','qualification_sha256':self.pin,'binding':self.binding,'retry':False,'parent_pid':os.getppid()})
        def run(path,run_name):
            self.assertTrue((root/'metadata.observed.json').is_file())
            self.assertEqual(Path(path),self.here/'qv_audit.py');self.assertEqual(run_name,'__main__')
            self.assertEqual(d.sys.argv,[str(path),'--arm','QS0','--stage','metadata'])
            target.write_text('{}')
        with patch.object(d,'observed',side_effect=lambda:copy.deepcopy(self.actual)),patch.object(d,'fresh_idle',return_value=self.binding),\
             patch.object(d,'qualification',return_value=self.q),patch.object(d.runpy,'run_path',side_effect=run):
            self.assertEqual(d.child('QS0','metadata',None,self.pin),0)

    def test_child_failure_keeps_its_observation(self):
        root,_,_=d.stage_contract('QS0','metadata',None);root.mkdir(parents=True)
        d.write_new(root/'metadata.dispatch-attempt.json',{'arm':'QS0','stage':'metadata','qualification_sha256':self.pin,'binding':self.binding,'retry':False,'parent_pid':os.getppid()})
        with patch.object(d,'observed',side_effect=lambda:copy.deepcopy(self.actual)),patch.object(d,'fresh_idle',return_value=self.binding),\
             patch.object(d,'qualification',return_value=self.q),patch.object(d.runpy,'run_path',side_effect=ValueError('bad finite evidence')):
            with self.assertRaisesRegex(ValueError,'bad finite'):d.child('QS0','metadata',None,self.pin)
        self.assertTrue((root/'metadata.observed.json').is_file())

    def test_missing_actual_child_attempt_refused(self):
        root,_,_=d.stage_contract('QS0','metadata',None);root.mkdir(parents=True)
        with patch.object(d,'observed',return_value=self.actual),patch.object(d.runpy,'run_path') as run:
            with self.assertRaises(ValueError):d.child('QS0','metadata',None,self.pin)
        run.assert_not_called()

    def test_postchild_busy_preserves_result_without_posthash(self):
        with patch.object(d,'fresh_idle',side_effect=[self.binding,self.binding,ValueError('busy')]),\
             patch.object(d,'qualification',return_value=self.q) as q,\
             patch.object(d.subprocess,'Popen',side_effect=lambda *a,**k:self.fake_completed()),\
             patch.object(d,'cleanup',return_value=[]):
            self.assertEqual(d.dispatch('QS0','metadata',None,self.pin),1)
        q.assert_called_once_with(self.pin)
        root,_,_=d.stage_contract('QS0','metadata',None)
        self.assertTrue((root/'metadata.json').is_file())
        self.assertIn('busy',json.loads((root/'metadata.child.json').read_text())['child']['error'])

    def test_busy_after_initial_hash_prevents_child_and_outputs(self):
        with patch.object(d,'fresh_idle',side_effect=[self.binding,ValueError('busy')]),\
             patch.object(d,'qualification',return_value=self.q),patch.object(d.subprocess,'Popen') as launch:
            with self.assertRaisesRegex(ValueError,'busy'):d.dispatch('QS0','metadata',None,self.pin)
        launch.assert_not_called();self.assertFalse((self.here/'QS0').exists())

    def test_cleanup_exception_preserves_terminal_failed_receipt(self):
        with patch.object(d,'fresh_idle',return_value=self.binding),patch.object(d,'qualification',return_value=self.q),\
             patch.object(d.subprocess,'Popen',side_effect=lambda *a,**k:self.fake_completed()),\
             patch.object(d,'cleanup',side_effect=OSError('cleanup observation failed')):
            self.assertEqual(d.dispatch('QS0','metadata',None,self.pin),1)
        root,_,_=d.stage_contract('QS0','metadata',None);r=json.loads((root/'metadata.child.json').read_text())
        self.assertIn('cleanup observation failed',r['child']['cleanup_errors'][0]);self.assertFalse(r['passed'])

    def proof_fixture(self,omit=None):
        names=('qv_dispatch.py','qv_audit.py','qv_runtime.py','qv_config.py','qv_controls.py','qv_owner.py')
        for name in names:(self.here/name).write_text('# synthetic source\n')
        ids=[]
        for mod in ('qv_audit','qv_dispatch'):
            name='test_'+mod+'.py';(self.here/name).write_text('class T:\n def test_one(self): pass\n');ids.append('test_'+mod+'.T.test_one')
        sm={p.name:d.sha(p) for p in self.here.iterdir() if p.is_file()}
        return {'files':{str(self.here/n):h for n,h in sm.items() if n!=omit},
                'CPU_groups':[{'source_sha256':sm,'test_ids':ids}]}

    def test_changed_dispatch_source_needs_cpu_group_membership(self):
        q=self.proof_fixture();d.changed_source_proofs(q)
        for name in ('qv_dispatch.py','qv_audit.py','qv_runtime.py','qv_config.py','qv_controls.py','qv_owner.py'):
            altered=copy.deepcopy(q);altered['CPU_groups'][0]['source_sha256'].pop(name)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'CPU proof'):d.changed_source_proofs(altered)

    def test_every_new_supplied_auditor_control_required(self):
        q=self.proof_fixture();q['CPU_groups'][0]['test_ids']=[]
        with self.assertRaisesRegex(ValueError,'tests omitted'):d.changed_source_proofs(q)

    def test_observer_rejects_real_unbounded_context(self):
        with patch.object(d.sys,'platform','linux'),patch.object(d.resource,'getrlimit',return_value=(-1,-1)):
            with self.assertRaisesRegex(ValueError,'Observed'):d.observed()

    def test_cpu_limits_set_only_child(self):
        with patch.object(d.os,'nice') as nice,patch.object(d.resource,'setrlimit') as limit:
            d.limits()
        nice.assert_called_once_with(15)
        self.assertEqual(limit.call_args_list[0].args,(d.resource.RLIMIT_CPU,(30,30)))
        self.assertEqual(limit.call_args_list[1].args,(d.resource.RLIMIT_AS,(d.AS,d.AS)))

    def test_cleanup_only_owned_group_after_timeout(self):
        p=Mock(pid=4242)
        with patch.object(d,'gone',side_effect=[False,True,True,True]),patch.object(d.os,'killpg') as kill:
            self.assertEqual(d.cleanup(p),[])
        kill.assert_called_once_with(4242,d.signal.SIGTERM)

    def test_regular_symlink_or_hardlink_refused(self):
        f=self.root/'a';f.write_text('x');s=self.root/'s';s.symlink_to(f)
        with self.assertRaises(ValueError):d.regular(s)
        h=self.root/'h';h.hardlink_to(f)
        with self.assertRaises(ValueError):d.regular(f)

    def test_bootstrap_delegates_only_exact_original_parent(self):
        path=self.here.parent/'model-v1/ms_audit_dispatch.py';path.parent.mkdir();path.write_text('# synthetic parent\n')
        module=Mock(__file__=str(path));module.bootstrap.return_value={'verified':38}
        with patch.object(d,'BASE_DISPATCH_SHA',d.sha(path)),patch.dict(d.sys.modules,{'ms_audit_dispatch':None}),patch.object(d.importlib,'import_module',return_value=module):
            self.assertEqual(d.bootstrap(),{'verified':38})
        with patch.object(d,'BASE_DISPATCH_SHA','0'*64),patch.object(d.importlib,'import_module') as load:
            with self.assertRaisesRegex(ValueError,'Exact qualified'):d.bootstrap()
        load.assert_not_called()

    def test_missing_config_pin_blocks_before_support_import(self):
        q=self.proof_fixture(omit='qv_config.py')
        parent=self.here.parent/'model-v1/ms_audit_dispatch.py';parent.parent.mkdir();parent.write_text('# parent\n')
        inventory=self.root/'bootstrap.json';d.write_new(inventory,{'paths_relative_to_E':{}})
        gate=self.root/'gate.py';gate.write_text('# gate\n')
        q['files'].update({str(inventory):d.sha(inventory),str(gate):d.sha(gate),str(parent):d.sha(parent)})
        q.update(mode='quality',root_manual_review=True,astra_manual_review=True)
        qp=self.here/'quality-qualification.json';d.write_new(qp,q)
        with patch.object(d,'BOOTSTRAP',inventory),patch.object(d,'BOOTSTRAP_SHA',d.sha(inventory)),patch.object(d,'GATE',gate),patch.object(d,'GATE_SHA',d.sha(gate)),patch.object(d,'BASE_DISPATCH_SHA',d.sha(parent)),patch.object(d.importlib,'import_module') as load:
            with self.assertRaises(ValueError):d.qualification(d.sha(qp))
        load.assert_not_called()

    def test_selected_owner_change_since_metadata_refused_before_child(self):
        root,_,_=d.stage_contract('QS0','scan',1);root.mkdir(parents=True)
        d.write_new(root/'metadata.json',{'qualification_sha256':self.pin,'selected_identity':{'start_binding':{'native_pid':100}}})
        with patch.object(d,'fresh_idle',return_value=self.binding),patch.object(d,'qualification',return_value=self.q),patch.object(d.subprocess,'Popen') as launch:
            with self.assertRaisesRegex(ValueError,'Selected owner changed'):d.dispatch('QS0','scan',1,self.pin)
        launch.assert_not_called()

    def test_missing_or_changed_actual_finished_witness_blocks_artifact(self):
        self.fake_completed();root,_,_=d.stage_contract('QS0','metadata',None)
        p=root/'metadata.finished.json';p.unlink()
        c={'pid':4242,'returncode':0,'error':None,'cleanup_errors':[],'wall_seconds':.1}
        with self.assertRaises(ValueError):d.artifact('QS0','metadata',None,self.pin,self.q,c)

    def test_consistent_raw_pass_label_cannot_publish_partial_or_overclaim(self):
        def fake(*args,**kwargs):
            p=self.fake_completed();root,_,target=d.stage_contract('QS0','metadata',None)
            value=json.loads(target.read_text());value['performance_claim']=True;target.write_text(json.dumps(value))
            f=root/'metadata.finished.json';v=json.loads(f.read_text());v['target_sha256']=d.sha(target);f.write_text(json.dumps(v))
            return p
        rc,_=self.run_dispatch(popen=fake);self.assertEqual(rc,1)

    def test_only_two_exact_historical_window_inputs_allowed(self):
        with patch.object(d,'R',self.root/'R'),patch.object(d,'E',self.root/'R/reliability-optimization-20261025'):
            self.assertTrue(d.allowed_input(d.R/'window.py'))
            self.assertTrue(d.allowed_input(d.R/'windows/20261030T220002Z.json'))
            self.assertTrue(d.allowed_input(d.R/'windows/20261030T220002Z.telemetry.jsonl'))
            for path in (d.R/'windows/20261030T220003Z.json',d.R/'windows/secret',d.R/'windows/../window.py'):
                self.assertFalse(d.allowed_input(path))

    def test_child_parent_identity_required_before_auditor(self):
        root,_,_=d.stage_contract('QS0','metadata',None);root.mkdir(parents=True)
        d.write_new(root/'metadata.dispatch-attempt.json',{'arm':'QS0','stage':'metadata','qualification_sha256':self.pin,'binding':self.binding,'retry':False,'parent_pid':os.getppid()+1})
        with patch.object(d,'observed',return_value=self.actual),patch.object(d.runpy,'run_path') as run:
            with self.assertRaisesRegex(ValueError,'Exact original'):d.child('QS0','metadata',None,self.pin)
        run.assert_not_called()


if __name__=='__main__':unittest.main()
