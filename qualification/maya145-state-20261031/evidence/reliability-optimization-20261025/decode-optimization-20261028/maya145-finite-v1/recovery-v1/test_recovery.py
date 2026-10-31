"""Synthetic contracts and mocked actual wrapper paths; no old helpers imported/run."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import recovery as s
import run_cpu as cpu


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.r=self.root/'r';self.e=self.r/'e';self.q=self.e/'decode-optimization-20261028/maya145-finite-v1';self.here=self.q/'recovery-v1'
        for p in (self.here,self.e/'maintenance',self.e/'results',self.r/'windows'):p.mkdir(parents=True,exist_ok=True)
        self.ps=patch.multiple(s,R=self.r,E=self.e,Q=self.q,HERE=self.here);self.ps.start()
        self.binding={'invocation':'2'*32,'main_pid':11,'native_pid':22,'native_start_ticks':33}
        self.controller=self.e/'maintenance/maya145-finite-mayas-TP2-20300101T010000Z/state.json';self.controller.parent.mkdir()
        self.put(self.controller,{'status':'STOPPED_FOR_OFFLINE_DIAGNOSIS'})
        self.failed=self.r/'windows/20300101T010100Z.json';self.clean=self.r/'windows/20300101T000000Z.json'
        self.put(self.failed,{'test_returncode':1,'maintenance_resume_allowed':False})
        self.put(self.clean,{'test_returncode':0,'maintenance_resume_allowed':True})
        self.clean.with_suffix('.telemetry.jsonl').write_text('{}\n')
        self.close=self.controller.parent/'old-owner-close.json';self.put(self.close,{'binding':self.binding,'native_close':{'returncode':0},'before':{},'after':{}})
        self.d={'run_id':'20300101T020000Z','mode':'finite','arm':'FTP2','controller':str(self.controller),'controller_sha256':s.sha(self.controller),
            'failed_window':str(self.failed),'failed_window_sha256':s.sha(self.failed),'last_clean_window':str(self.clean),'last_clean_window_sha256':s.sha(self.clean),
            'last_clean_telemetry_sha256':s.sha(self.clean.with_suffix('.telemetry.jsonl')),'old_close':str(self.close),'old_close_sha256':s.sha(self.close),
            'stopped_unit':{'InvocationID':'1'*32,'MainPID':'0','ActiveState':'failed','Result':'exit-code'},'kernel_since':'2030-01-01 01:00:00 UTC','manual_diagnosis_complete':True,'failed_arm_remains_HOLD':True}
        self.dp=self.here/'diagnosis-20300101T020000Z.json';self.put(self.dp,self.d)
        self.a={'decision':'SINGLE_BASELINE_HEALTH_ONLY','baseline_only':True,'single_use':True,'manual_review':True,'run_id':self.d['run_id'],
            'binary_sha256':s.BINARY_SHA,'diagnosis':str(self.dp),'diagnosis_sha256':s.sha(self.dp),'qualification_sha256':'3'*64}
        self.ap=self.here/'admission-health.json';self.put(self.ap,self.a)
        self.state={'maintenance_controller':str(self.controller),'production_temporarily_stopped':True,'current_native_pid':None,'decode_optimization_current':{'keep':'unchanged'},'arm_result':{'HOLD':True}}
        self.put(self.e/'STATE.json',self.state)
        self.host=Mock();self.host.start_binding=None;self.host.restored_pid=None;self.host.start_invocation=None;self.host.start_main_pid=None
        self.g=Mock();self.g.selected_binding.side_effect=lambda state:state['decode_optimization_current']['selected_identity']['start_binding']
        self.lib=Mock();self.cas=Mock();self.cas.cas_state.side_effect=self.cas_write

    def tearDown(self):self.ps.stop();self.tmp.cleanup()
    def put(self,p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(s.packed(x))
    def cas_write(self,path,before,after):
        if path.read_bytes()!=before:raise ValueError('CAS changed')
        path.write_bytes(s.packed(after))
    def evidence_q(self):
        files={str(Path(self.d[k])):self.d[k+'_sha256'] for k in ('controller','failed_window','last_clean_window','old_close')}
        files[str(self.clean.with_suffix('.telemetry.jsonl'))]=self.d['last_clean_telemetry_sha256'];return {'files':files}
    def admission(self,operation='health'):
        a=copy.deepcopy(self.a)
        if operation=='restore':
            a['decision']='SINGLE_SELECTED_BASELINE_RESTORE_ONLY'
            a.update({k:'4'*64 for k in ('health_receipt_sha256','health_window_sha256','health_telemetry_sha256','independent_health_review_sha256')})
        self.put(self.ap,a);return a,s.sha(self.ap)
    def claim(self,operation='health'):
        a,pin=self.admission(operation)
        with patch.object(s,'process_ticks',return_value=123):record=s.claim(self.cas,self.d,a,operation,pin)
        return record
    def pending(self):
        a,pin=self.admission('restore');metadata,_=s.paths(self.d);(metadata/'restore').mkdir(parents=True)
        record={'run_id':self.d['run_id'],'status':'SELECTED_RUNNING_PUBLIC_VERIFY_PENDING','active':False,'operation':'restore','admission_sha256':pin,
            'qualification_sha256':a['qualification_sha256'],'diagnosis_sha256':a['diagnosis_sha256'],'start_binding':self.binding}
        state={**self.state,'production_temporarily_stopped':False,'current_native_pid':22,'maya145finite_recovery_current':record,'production_verification_pending':str(metadata/'restore/result.json')}
        self.put(self.e/'STATE.json',state);return a,pin,state


class Contracts(Fixture):
    def test_valid_new_family_diagnosis(self):self.assertEqual(s.diagnosis_contract(self.d),self.d)
    def test_closed_or_unknown_arm_refused(self):
        for mode,arm in [('quality','N0'),('coding','QS1'),('performance','A1')]:
            with self.subTest(mode=mode,arm=arm),self.assertRaises(ValueError):s.diagnosis_contract({**self.d,'mode':mode,'arm':arm})
    def test_same_failed_clean_refused(self):
        with self.assertRaises(ValueError):s.diagnosis_contract({**self.d,'last_clean_window':str(self.failed)})
    def test_foreign_nested_controller_refused(self):
        for p in (self.root/'state.json',self.controller.parent/'nested/state.json'):
            with self.subTest(path=p),self.assertRaises(ValueError):s.diagnosis_contract({**self.d,'controller':str(p)})
    def test_symlink_and_traversal_refused(self):
        link=self.here/'alias';link.symlink_to(self.controller)
        for p in (link,self.here/'../state.json'):
            with self.subTest(path=p),self.assertRaises(ValueError):s.real(p,self.here)
    def test_stopped_binding_and_manual_gate(self):
        for update in ({'stopped_unit':{**self.d['stopped_unit'],'MainPID':'11'}},{'manual_diagnosis_complete':False},{'failed_arm_remains_HOLD':False}):
            with self.subTest(update=update),self.assertRaises(ValueError):s.diagnosis_contract({**self.d,**update})
    def test_separate_admission_no_candidate(self):
        for change in ({'decision':'SINGLE_SELECTED_BASELINE_RESTORE_ONLY'},{'baseline_only':False},{'binary_sha256':'0'*64},{'single_use':False}):
            with self.subTest(change=change),self.assertRaises(ValueError):s.admission_contract({**self.a,**change},self.d,'health')
    def test_each_foreign_phase_blocks(self):
        for k in s.PHASES:
            with self.subTest(key=k),self.assertRaises(ValueError):s.state_contract({**self.state,k:{'foreign':True}},self.d,'health')
    def test_foreign_controller_and_live_native_block(self):
        for change in ({'maintenance_controller':'foreign'},{'current_native_pid':22},{'production_temporarily_stopped':False}):
            with self.subTest(change=change),self.assertRaises(ValueError):s.state_contract({**self.state,**change},self.d,'health')
    def test_no_health_replay_or_unreviewed_restore(self):
        with self.assertRaises(ValueError):s.state_contract({**self.state,'maya145finite_recovery_current':{'run_id':self.d['run_id']}},self.d,'health')
        with self.assertRaises(ValueError):s.state_contract(self.state,self.d,'restore')
    def test_lineage_actual_close_contract(self):
        self.assertEqual(s.lineage(self.d,self.evidence_q(),self.g),self.binding);self.g.close_contract.assert_called_once_with(self.binding,{'returncode':0},{},{})
    def test_lineage_changed_failed_or_omitted_pin(self):
        q=self.evidence_q();q['files'].pop(str(self.failed))
        with self.assertRaises(ValueError):s.lineage(self.d,q,self.g)
        self.put(self.failed,{'test_returncode':0,'maintenance_resume_allowed':True})
        with self.assertRaises(ValueError):s.lineage(self.d,self.evidence_q(),self.g)
        self.g.close_contract.assert_not_called()
    def test_close_failure_blocks(self):
        self.g.close_contract.side_effect=ValueError('API not closed')
        with self.assertRaisesRegex(ValueError,'API not closed'):s.lineage(self.d,self.evidence_q(),self.g)
    def test_helper_hash_checked_before_import(self):
        p=self.here/'helper.py';p.write_text('raise RuntimeError("must not import")\n')
        with patch.object(s.importlib.util,'spec_from_file_location') as imp,self.assertRaises(ValueError):s.module('helper',p,'0'*64)
        imp.assert_not_called()
    def test_foreign_cached_helper_refused(self):
        p=self.here/'helper.py';p.write_text('pass\n')
        with patch.dict(s.sys.modules,{'wrong':Mock(__file__=str(self.root/'foreign.py'))}),self.assertRaises(ValueError):s.module('wrong',p,s.sha(p))


class Custody(Fixture):
    def test_actual_claim_and_safe_release_preserve_failed_arm(self):
        record=self.claim();result={'status':'HEALTH_PENDING_INDEPENDENT_REVIEW'}
        s.release(self.cas,self.d,record,result,None,safe=True,host=self.host)
        state=s.read(self.e/'STATE.json');self.assertFalse(state['active_gpu_experiment']);self.assertFalse(state['maya145finite_recovery_current']['active']);self.assertEqual(state['arm_result'],self.state['arm_result']);self.assertEqual(state['decode_optimization_current'],self.state['decode_optimization_current'])
    def test_foreign_record_or_phase_never_cleared(self):
        record=self.claim()
        for key in ('maya145finite_recovery_current','active_gpu_experiment'):
            state=s.read(self.e/'STATE.json');changed={**state,key:{'foreign':True}};self.put(self.e/'STATE.json',changed)
            with self.subTest(key=key),self.assertRaises(ValueError):s.release(self.cas,self.d,record,None,'fault',safe=True,host=self.host)
            self.assertEqual(s.read(self.e/'STATE.json'),changed);self.put(self.e/'STATE.json',state)
    def test_unknown_cleanup_retains_owned_phase(self):
        record=self.claim();s.release(self.cas,self.d,record,None,'cleanup failed',safe=False,host=self.host)
        state=s.read(self.e/'STATE.json');self.assertEqual(state['active_gpu_experiment'],record);self.assertTrue(state['maya145finite_recovery_current']['active'])
    def test_restore_updates_only_after_verified_binding(self):
        self.put(self.e/'STATE.json',{**self.state,'maya145finite_recovery_current':{'run_id':self.d['run_id'],'status':'HEALTH_PENDING_INDEPENDENT_REVIEW'}})
        record=self.claim('restore');self.host.start_binding=self.binding;self.host.restored_pid=22
        result={'status':'SELECTED_BASELINE_RESTORED_FAILED_ARM_REMAINS_HOLD','verified':{'selected_identity':{'native_pid':22}}}
        s.release(self.cas,self.d,record,result,None,safe=True,host=self.host)
        state=s.read(self.e/'STATE.json');self.assertEqual(state['decode_optimization_current']['selected_identity']['start_binding'],self.binding);self.assertEqual(state['decode_optimization_current']['keep'],'unchanged');self.assertFalse(state['production_temporarily_stopped']);self.assertFalse(state['production_restore_in_progress'])
    def test_pending_wrong_binding_or_custody_refused(self):
        a,pin,state=self.pending()
        for change in ({'current_native_pid':23},{'production_verification_pending':'foreign'},{'maintenance_controller':'foreign'}):
            with self.subTest(change=change),self.assertRaises(ValueError):s.pending_contract({**state,**change},self.d,a,pin)


class Bodies(Fixture):
    def health_files(self):
        _,out=s.paths(self.d);out.mkdir();window=self.r/'windows/20300101T020100Z.json';self.put(window,{'test_returncode':0});window.with_suffix('.telemetry.jsonl').write_text('{}\n')
        self.put(out/'receipt.json',{'passed':True,'window':str(window),'binary_sha256':s.BINARY_SHA,'devices':[{'device':i,'cases':12,'exit':0} for i in (0,1)]})
        a,pin=self.admission('restore');review=self.here/'health-review.json';self.put(review,{'decision':'BASELINE_HEALTH_24_CASES_REVIEWED'})
        a.update(health_receipt_sha256=s.sha(out/'receipt.json'),health_window_sha256=s.sha(window),health_telemetry_sha256=s.sha(window.with_suffix('.telemetry.jsonl')),independent_health_review=str(review),independent_health_review_sha256=s.sha(review))
        self.host.previous.return_value=window;return out,window,a
    def test_health_launches_only_one_existing_window(self):
        _,out=s.paths(self.d);window=self.r/'windows/20300101T020100Z.json'
        def launched(*args):
            out.mkdir();self.put(out/'receipt.json',{'passed':True,'window':str(window)});return window
        self.host.launch_owned.side_effect=launched
        result=s.health_body(self.host,self.g,self.lib,self.d,self.a,self.ap,'4'*64)
        self.assertEqual(result['status'],'HEALTH_PENDING_INDEPENDENT_REVIEW');self.host.launch_owned.assert_called_once_with(self.clean,s.argv_for('entry',self.ap,'4'*64),1200);self.host.restore_ds.assert_not_called()
    def test_health_firstfault_never_restores(self):
        self.host.launch_owned.side_effect=ValueError('health failed')
        with self.assertRaisesRegex(ValueError,'health failed'):s.health_body(self.host,self.g,self.lib,self.d,self.a,self.ap,'4'*64)
        self.host.restore_ds.assert_not_called();self.assertEqual(self.host.launch_owned.call_count,1)
    def test_restore_one_start_and_public_verification(self):
        _,_,a=self.health_files();self.host.restored_pid=22;self.host.start_binding=self.binding;self.host.verify_target.return_value={'passed':True,'selected_identity':{'native_pid':22}}
        result=s.restore_body(self.host,self.d,a)
        self.assertEqual(result['native_restarts_requested'],1);self.host.restore_ds.assert_called_once();self.host.restore_router.assert_called_once();self.host.verify_target.assert_called_once_with(expected_pid=22)
    def test_restore_pending_is_not_completion_or_second_start(self):
        _,_,a=self.health_files();self.host.restored_pid=22;self.host.verify_target.return_value={'pending_public_probe':True}
        self.assertEqual(s.restore_body(self.host,self.d,a)['status'],'SELECTED_RUNNING_PUBLIC_VERIFY_PENDING');self.host.restore_ds.assert_called_once()
    def test_restore_changed_health_blocks_before_start(self):
        out,_,a=self.health_files();(out/'receipt.json').write_text('{}')
        with self.assertRaises(ValueError):s.restore_body(self.host,self.d,a)
        self.host.restore_ds.assert_not_called()
    def test_restore_latest_window_or_review_required(self):
        _,_,a=self.health_files();self.host.previous.return_value=self.failed
        with self.assertRaises(ValueError):s.restore_body(self.host,self.d,a)
        self.host.restore_ds.assert_not_called()
    def test_restore_start_failure_no_router(self):
        _,_,a=self.health_files();self.host.restore_ds.side_effect=ValueError('start failed')
        with self.assertRaisesRegex(ValueError,'start failed'):s.restore_body(self.host,self.d,a)
        self.host.restore_router.assert_not_called();self.host.restore_ds.assert_called_once()


class Supervisor(Fixture):
    def invoke(self,body=None,cas=None,**overrides):
        q={'files':{str(self.dp):s.sha(self.dp)}}
        patches={'stopped_guard':Mock(),'qualified':Mock(return_value=q),'support':Mock(return_value=(self.g,self.lib,self.cas,self.host)),
            'lineage':Mock(return_value=self.binding),'health_body':Mock(return_value={'status':'HEALTH_PENDING_INDEPENDENT_REVIEW'}),'process_ticks':Mock(return_value=123)}
        if body is not None:patches['health_body']=body
        patches.update(overrides)
        if cas:self.cas.cas_state.side_effect=cas
        with patch.multiple(s,**patches):return s.run('health',self.ap,s.sha(self.ap))
    def test_actual_main_success_custody_receipt(self):
        self.assertEqual(self.invoke()['status'],'HEALTH_PENDING_INDEPENDENT_REVIEW');state=s.read(self.e/'STATE.json')
        self.assertFalse(state['active_gpu_experiment']);self.assertTrue(state['production_temporarily_stopped']);self.assertEqual(s.read(s.paths(self.d)[0]/'health/result.json')['cleanup_errors'],[])
    def test_guard_failure_before_directory_or_claim(self):
        with self.assertRaisesRegex(ValueError,'busy'):self.invoke(stopped_guard=Mock(side_effect=ValueError('busy')))
        self.assertFalse(s.paths(self.d)[0].exists());self.cas.cas_state.assert_not_called()
    def test_partial_claim_readback_fault_owned_release(self):
        calls=[]
        def cas(path,before,after):
            self.cas_write(path,before,after);calls.append(1)
            if len(calls)==1:raise ValueError('readback fault')
        with self.assertRaisesRegex(ValueError,'readback fault'):self.invoke(cas=cas)
        state=s.read(self.e/'STATE.json');self.assertFalse(state['active_gpu_experiment']);self.assertEqual(state['maya145finite_recovery_current']['status'],'HOLD');self.assertEqual(len(calls),2)
    def test_primary_and_cleanup_failure_preserved(self):
        self.host.free.side_effect=[None,ValueError('not free')]
        with self.assertRaisesRegex(ValueError,'primary'):self.invoke(body=Mock(side_effect=ValueError('primary')))
        result=s.read(s.paths(self.d)[0]/'health/result.json');self.assertIn('primary',result['error']);self.assertIn('not free',str(result['cleanup_errors']));self.assertTrue(s.read(self.e/'STATE.json')['maya145finite_recovery_current']['active'])
    def test_foreign_custody_replacement_preserved(self):
        def body(*args):
            state=s.read(self.e/'STATE.json');state['active_gpu_experiment']={'foreign':True};self.put(self.e/'STATE.json',state);raise ValueError('body failed')
        with self.assertRaisesRegex(ValueError,'body failed'):self.invoke(body=Mock(side_effect=body))
        self.assertEqual(s.read(self.e/'STATE.json')['active_gpu_experiment'],{'foreign':True})
    def test_no_second_attempt_after_failure(self):
        with self.assertRaises(ValueError):self.invoke(body=Mock(side_effect=ValueError('fault')))
        with self.assertRaises(ValueError):self.invoke()
    def test_pending_busy_does_not_start_or_claim(self):
        _,pin,state=self.pending();self.host.idle.return_value=False
        with patch.object(s.sys,'platform','linux'),patch.object(s,'qualified',return_value={}),patch.object(s,'support',return_value=(self.g,self.lib,self.cas,self.host)):
            self.assertEqual(s.verify_pending(self.ap,pin,'20300101T030000Z')['status'],'DEFERRED_BUSY_PENDING_UNTOUCHED')
        self.assertEqual(s.read(self.e/'STATE.json'),state);self.cas.cas_state.assert_not_called();self.host.restore_ds.assert_not_called();self.host.verify_target.assert_not_called()
    def test_pending_actual_verify_never_restarts(self):
        _,pin,_=self.pending();self.host.idle.return_value=True;self.host.verify_target.return_value={'passed':True,'selected_identity':{'native_pid':22}}
        with patch.object(s.sys,'platform','linux'),patch.object(s,'qualified',return_value={}),patch.object(s,'support',return_value=(self.g,self.lib,self.cas,self.host)),patch.object(s,'process_ticks',return_value=123):
            self.assertEqual(s.verify_pending(self.ap,pin,'20300101T030000Z')['status'],'SELECTED_BASELINE_RESTORED_FAILED_ARM_REMAINS_HOLD')
        self.host.restore_ds.assert_not_called();self.host.restore_router.assert_not_called();self.host.verify_target.assert_called_once_with(expected_pid=22);self.assertFalse(s.read(self.e/'STATE.json')['production_verification_pending'])
    def invoke_restore(self,body):
        _,pin=self.admission('restore');metadata,out=s.paths(self.d);metadata.mkdir();out.mkdir();self.put(out/'receipt.json',{'window':str(self.clean)})
        self.put(self.e/'STATE.json',{**self.state,'maya145finite_recovery_current':{'run_id':self.d['run_id'],'status':'HEALTH_PENDING_INDEPENDENT_REVIEW'}})
        with patch.object(s,'stopped_guard'),patch.object(s,'qualified',return_value={'files':{str(self.dp):s.sha(self.dp)}}),patch.object(s,'support',return_value=(self.g,self.lib,self.cas,self.host)),patch.object(s,'lineage',return_value=self.binding),patch.object(s,'raw_health') as raw,patch.object(s,'restore_body',side_effect=body),patch.object(s,'process_ticks',return_value=123):
            result=s.run('restore',self.ap,pin);raw.assert_called_once_with(out,s.read(self.ap),self.lib);return result
    def test_actual_restore_wrapper_verified_binding(self):
        def body(*args):
            self.host.start_binding=self.binding;self.host.restored_pid=22
            return {'status':'SELECTED_BASELINE_RESTORED_FAILED_ARM_REMAINS_HOLD','verified':{'selected_identity':{'native_pid':22}}}
        self.invoke_restore(body);state=s.read(self.e/'STATE.json');self.assertFalse(state['production_restore_in_progress']);self.assertEqual(state['current_native_pid'],22);self.host.cleanup_owned_target.assert_not_called()
    def test_restore_primary_cleans_only_captured_owned_pid(self):
        def body(*args):
            self.host.start_binding=self.binding;self.host.restored_pid=22;raise ValueError('public fault')
        with self.assertRaisesRegex(ValueError,'public fault'):self.invoke_restore(body)
        self.host.cleanup_owned_target.assert_called_once_with(22);self.assertEqual(s.read(self.e/'STATE.json')['maya145finite_recovery_current']['status'],'HOLD')
    def test_restore_primary_and_owned_cleanup_fault_both_recorded(self):
        def body(*args):
            self.host.start_binding=self.binding;self.host.restored_pid=22;raise ValueError('primary')
        self.host.cleanup_owned_target.side_effect=ValueError('owned cleanup failed');self.host.free.side_effect=[None,ValueError('not free')]
        with self.assertRaisesRegex(ValueError,'primary'):self.invoke_restore(body)
        result=s.read(s.paths(self.d)[0]/'restore/result.json');self.assertIn('primary',result['error']);self.assertIn('owned cleanup failed',str(result['cleanup_errors']));self.assertTrue(s.read(self.e/'STATE.json')['maya145finite_recovery_current']['active'])


class StoppedGuard(Fixture):
    def guard(self,owner='',free=132*2**30):
        os.utime(self.clean,(10,10));os.utime(self.failed,(20,20))
        unit='\n'.join(k+'='+v for k,v in self.d['stopped_unit'].items())+'\n'
        def command(argv):
            if argv[0]=='systemctl':return unit
            if '--query-compute-apps=pid' in argv:return owner
            return '0\n0\n'
        with patch.object(s.sys,'platform','linux'),patch.object(s,'command',side_effect=command),patch.object(s.subprocess,'run',return_value=Mock(returncode=3)),patch.object(s.shutil,'disk_usage',return_value=Mock(free=free)):
            return s.stopped_guard(self.d,'health',self.failed)
    def test_actual_guard_empty_owner_current_stopped_unit(self):self.assertEqual(self.guard(),self.state)
    def test_owner_or_insufficient_root_refused(self):
        with self.assertRaises(ValueError):self.guard(owner='123\n')
        with self.assertRaises(ValueError):self.guard(free=132*2**30-1)
    def test_phase_refused_before_any_command(self):
        self.put(self.e/'STATE.json',{**self.state,'active_private_phase':'foreign'})
        with patch.object(s.sys,'platform','linux'),patch.object(s,'command') as cmd,self.assertRaises(ValueError):s.stopped_guard(self.d,'health',self.failed)
        cmd.assert_not_called()


class RawHealth(Fixture):
    def make(self):
        _,out=s.paths(self.d);out.mkdir();self.put(out/'receipt.json',{'passed':True})
        for i in (0,1):
            argv=[str(s.BINARY),'--baseline-health',str(i)]
            self.put(out/f'gpu{i}-exit.json',{'argv':argv,'error':None,'cleanup_errors':[],'pid':100+i,'CPU_s':120,'AS_MiB':None,'wall_s':120,'CUDA_hidden':False,'returncode':0})
            self.put(out/f'gpu{i}-start.json',{'pid':100+i,'argv':argv,'same_executable':True,'start_ticks':123,'cgroup':'0::/user.slice/strata-deepseek-window.service'})
            (out/f'gpu{i}.stdout').write_text('synthetic twelve exact passes');(out/f'gpu{i}.stderr').write_text('')
        return out,{'health_raw_sha256':{str(p):s.sha(p) for p in out.iterdir()}}
    def test_all_raw_identity_bounds_and_both_output_contracts(self):
        out,a=self.make();s.raw_health(out,a,self.lib);self.assertEqual(self.lib.result_contract.call_count,2)
    def test_missing_raw_or_wrong_child_bounds_refused(self):
        out,a=self.make();missing=copy.deepcopy(a);missing['health_raw_sha256'].pop(str(out/'gpu1.stderr'))
        with self.assertRaises(ValueError):s.raw_health(out,missing,self.lib)
        p=out/'gpu0-exit.json';self.put(p,{**s.read(p),'CPU_s':121});a['health_raw_sha256'][str(p)]=s.sha(p)
        with self.assertRaises(ValueError):s.raw_health(out,a,self.lib)
        self.lib.result_contract.assert_not_called()


class Qualification(Fixture):
    def fixture(self):
        w=self.root/'old';w.mkdir();old=w/'original.py';old.write_text('original\n');binary=w/'binary';binary.write_bytes(b'unchanged binary')
        oldmap=w/'GPU_INPUT_MAP.json';self.put(oldmap,{'files':{str(old):s.sha(old)}})
        for n in s.SOURCES:(self.here/n).write_text('class T:\n def test_a(self): pass\n' if n=='test_recovery.py' else '# synthetic\n')
        sources={n:s.sha(self.here/n) for n in s.SOURCES};ids=['test_recovery.T.test_a'];dep=self.e/'dependency.py';dep.write_text('dependency\n');inputs={'dependency.py':s.sha(dep)}
        files={str(old):s.sha(old),str(oldmap):s.sha(oldmap),str(binary):s.sha(binary),str(dep):s.sha(dep),**{str(self.here/n):v for n,v in sources.items()}}
        for host in ('darwin','linux'):
            folder=self.here/('CPU-FIRST-'+host);folder.mkdir()
            self.put(folder/'receipt.json',{'passed':True,'controls':1,'test_ids':ids,'source_sha256':sources,'input_sha256':inputs,'CPU_seconds':[30,30],'Linux_AS_bytes':[512*2**20]*2 if host=='linux' else None,'environment':cpu.ENV,'nice':15,'CPU_only':True,'health_or_service_executed':False})
            self.put(folder/'child.json',{'returncode':0,'error':None,'cleanup_errors':[],'CPU_limit_seconds':30,'wall_limit_seconds':90,'nice_increment':15,'Linux_AS_bytes':512*2**20 if host=='linux' else None,'environment':cpu.ENV})
            (folder/'child.log').write_text('synthetic proof\n')
            files.update({str(folder/n):s.sha(folder/n) for n in ('receipt.json','child.json','child.log')})
        review=self.here/'RECOVERY_SOURCE_ROOT_REVIEW.json';self.put(review,{'root_entire_source_and_tests_read':True,'sol_entire_source_and_tests_read':True,'source_sha256':sources,'test_ids':ids,'input_sha256':inputs});files[str(review)]=s.sha(review)
        q={'root_manual_read':True,'sol_manual_read':True,'files':files,'source_sha256':sources,'test_ids':ids,'input_sha256':inputs}
        self.patchq=patch.multiple(s,W=w,OLD_MAP_SHA=s.sha(oldmap),BINARY=binary,BINARY_SHA=s.sha(binary),HELPERS={});self.patchq.start();self.addCleanup(self.patchq.stop);return q
    def check(self,q):
        path=self.here/'RECOVERY_QUALIFICATION.json';self.put(path,q);return s.qualified(s.sha(path))
    def test_complete_exact_qualification(self):q=self.fixture();self.assertEqual(self.check(q),q)
    def test_missing_original_closure_refused(self):
        q=self.fixture();q['files'].pop(str(self.root/'old/original.py'))
        with self.assertRaises(ValueError):self.check(q)
    def test_raw_cpu_pin_required(self):
        q=self.fixture();q['files'].pop(str(self.here/'CPU-FIRST-linux/child.log'))
        with self.assertRaises(ValueError):self.check(q)
    def test_cpu_changed_ids_or_bounds_refused(self):
        q=self.fixture();p=self.here/'CPU-FIRST-linux/child.json';c=s.read(p);c['returncode']=False;self.put(p,c);q['files'][str(p)]=s.sha(p)
        with self.assertRaises(ValueError):self.check(q)
    def test_dependency_changed_refused(self):
        q=self.fixture();(self.e/'dependency.py').write_text('changed')
        with self.assertRaises(ValueError):self.check(q)


class HistoricalPaths(Fixture):
    def test_parent_component_same_inode_normalized(self):
        folder=self.root/'compiler';folder.mkdir();p=self.root/'header';p.write_text('bytes')
        self.assertEqual(s.canonical_health_files({str(folder/'../header'):'a'*64}),{str(p):'a'*64})
    def test_alias_conflicting_pins_refused(self):
        folder=self.root/'compiler';folder.mkdir();p=self.root/'header';p.write_text('bytes')
        with self.assertRaises(ValueError):s.canonical_health_files({str(folder/'../header'):'a'*64,str(p):'b'*64})
    def test_relative_or_different_resolution_refused(self):
        with self.assertRaises(ValueError):s.canonical_health_files({'relative':'a'*64})
        with patch.object(s.os.path,'samefile',return_value=False),self.assertRaises(ValueError):s.canonical_health_files({'/compiler/../header':'a'*64})


class Driver(Fixture):
    def test_limits_cpu_and_linux_as(self):
        with patch.object(cpu.os,'nice') as nice,patch.object(cpu.resource,'setrlimit') as limit,patch.object(cpu.sys,'platform','linux'):
            cpu.limits()
        nice.assert_called_once_with(15);self.assertEqual(limit.call_args_list[0].args,(cpu.resource.RLIMIT_CPU,(30,30)));self.assertEqual(limit.call_args_list[1].args,(cpu.resource.RLIMIT_AS,(512*2**20,512*2**20)))
    def test_cleanup_even_exited_parent_with_descendant(self):
        proc=Mock(pid=123);proc.poll.return_value=0
        with patch.object(cpu,'gone',side_effect=[False,True,True,True]),patch.object(cpu.os,'killpg') as kill:
            self.assertEqual(cpu.cleanup(proc),[])
        kill.assert_called_once_with(123,cpu.signal.SIGTERM);proc.wait.assert_called_once()
    def test_driver_timeout_has_owned_cleanup(self):
        proc=Mock(pid=123);proc.wait.side_effect=subprocess.TimeoutExpired('CPU',90)
        with patch.object(cpu,'HERE',self.here),patch.object(cpu,'checked',return_value=({}, {}, ['test'])),patch.object(cpu.subprocess,'Popen',return_value=proc),patch.object(cpu,'cleanup',return_value=[]) as clean:
            self.assertEqual(cpu.main('0'*64),1)
        clean.assert_called_once_with(proc);child=s.read(self.here/('CPU-FIRST-'+('linux' if cpu.sys.platform=='linux' else 'darwin'))/'child.json');self.assertIn('TimeoutExpired',child['error'])


class Entry(Fixture):
    def prepare(self):
        for n in s.SOURCES:(self.here/n).write_text('# synthetic source\n')
        qp=self.here/'RECOVERY_QUALIFICATION.json';self.put(qp,{'source_sha256':{n:s.sha(self.here/n) for n in s.SOURCES}})
        self.a['qualification_sha256']=s.sha(qp);self.put(self.ap,self.a);pin=s.sha(self.ap)
        record={'active':True,'operation':'health','run_id':self.d['run_id'],'diagnosis_sha256':self.a['diagnosis_sha256'],'qualification_sha256':self.a['qualification_sha256'],'admission_sha256':pin,'pid':77,'start_ticks':88}
        self.put(self.e/'STATE.json',{**self.state,'maya145finite_recovery_current':record,'active_gpu_experiment':record})
        self.window=self.r/'windows/20300101T020100Z.json';self.put(self.window,{'continued_from':str(self.clean),'mutation_started':True,'test_returncode':None,'admission_mode':'continued-explicit-deepseek-maintenance','command':s.argv_for('entry',self.ap,pin)})
        self.pin=pin;return pin
    def invoke(self,*,foreign_parent=False,foreign_cgroup=False,first_fault=False):
        original_bytes=Path.read_bytes;original_text=Path.read_text;original_sha=s.sha
        def read_bytes(p):
            if p==Path('/proc/self/cmdline'):return b'\0'.join(x.encode() for x in s.argv_for('entry',self.ap,self.pin))+b'\0'
            if p==Path('/proc/77/cmdline'):return b'foreign\0' if foreign_parent else b'\0'.join(x.encode() for x in s.argv_for('health',self.ap,self.pin))+b'\0'
            return original_bytes(p)
        def read_text(p,*args,**kw):
            if p==Path('/proc/self/cgroup'):return '0::/foreign.service\n' if foreign_cgroup else '0::/user.slice/strata-deepseek-window.service\n'
            return original_text(p,*args,**kw)
        def child(argv,out,label,*args):
            if first_fault:raise ValueError('first GPU fault')
            (out/(label+'.stdout')).write_text('synthetic exact output')
            self.assertEqual(args[:4],(120,None,120,False));args[4](101,argv)
            return {'returncode':0}
        self.lib.child.side_effect=child;self.lib.result_contract.side_effect=lambda text,rc,device:{'device':device,'cases':12,'exit':0}
        with patch.object(s.sys,'platform','linux'),patch.object(s,'process_ticks',return_value=88),patch.object(s,'sha',side_effect=lambda p:s.BINARY_SHA if Path(p)==s.BINARY else original_sha(p)),patch.object(s,'module',side_effect=[self.g,self.lib]),patch.dict(os.environ,{'STRATA_WINDOW_STATE':str(self.window)}),patch.object(Path,'read_bytes',read_bytes),patch.object(Path,'read_text',read_text):
            return s.entry(self.ap,self.pin)
    def test_actual_entry_two_serial_children_and_identity_callback(self):
        self.prepare();self.invoke();self.assertEqual(self.lib.child.call_count,2);self.assertEqual(self.g.child_identity.call_count,2)
        receipt=s.read(s.paths(self.d)[1]/'receipt.json');self.assertEqual(receipt['devices'],[{'device':i,'cases':12,'exit':0} for i in (0,1)]);self.assertFalse(receipt['model_execution'])
    def test_first_child_fault_no_second_or_success_receipt(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError,'first GPU fault'):self.invoke(first_fault=True)
        self.assertEqual(self.lib.child.call_count,1);self.assertFalse((s.paths(self.d)[1]/'receipt.json').exists())
    def test_foreign_parent_refused_before_child(self):
        self.prepare()
        with self.assertRaises(ValueError):self.invoke(foreign_parent=True)
        self.lib.child.assert_not_called()
    def test_foreign_cgroup_refused_before_child(self):
        self.prepare()
        with self.assertRaises(ValueError):self.invoke(foreign_cgroup=True)
        self.lib.child.assert_not_called()
    def test_wrong_continuation_or_completed_window_refused(self):
        self.prepare();w=s.read(self.window)
        for change in ({'continued_from':str(self.failed)},{'test_returncode':0},{'command':['foreign']},{'mutation_started':False}):
            self.put(self.window,{**w,**change})
            with self.subTest(change=change),self.assertRaises(ValueError):self.invoke()
        self.lib.child.assert_not_called()
    def test_changed_entry_source_or_lineage_refused(self):
        self.prepare();(self.here/'run_cpu.py').write_text('changed')
        with self.assertRaises(ValueError):self.invoke()
        self.lib.child.assert_not_called()
    def test_reused_output_namespace_refused(self):
        self.prepare();s.paths(self.d)[1].mkdir()
        with self.assertRaises(ValueError):self.invoke()
        self.lib.child.assert_not_called()


if __name__=='__main__':unittest.main()
