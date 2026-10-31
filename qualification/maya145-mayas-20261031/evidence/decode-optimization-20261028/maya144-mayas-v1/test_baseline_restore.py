import copy
from pathlib import Path
import types
import unittest
from unittest.mock import Mock
import baseline_restore as r

class Restore(unittest.TestCase):
    def fixture(self):
        state={'maintenance_controller':str(r.E/'maintenance'/r.FAILED/'state.json'),
            'decode_optimization_current':{'status':'STOPPED_FOR_OFFLINE_DIAGNOSIS'},'current_native_pid':None,'production_temporarily_stopped':True}
        phase={'error':"ValueError('Native image contract changed')",'retry':False}
        close=[{'returncode':0,'closed':True}]
        cleanup={'passed':True,'server_returncode':0,'grace_timeout':False,'wait_error':None,'application_stopped':True,'native_close':close}
        window={'test_returncode':1,'maintenance_held':True,'maintenance_resume_allowed':False}
        kernel={'kernel_capture_returncode':0,'kernel_fault_lines':[]}
        collected={'passed':True,'unit_collected':True,'fragment_absent':True,'dropins_absent':True}
        return state,phase,cleanup,close,window,kernel,collected
    def host(self,*,pending=False):
        identity={'native_sha256':r.NATIVE,'config_sha256':r.CONFIG,'context':1048576,'output_default':262144,'DSpark':True}
        v={'selected_identity':identity,'pending_public_probe':pending,'passed':not pending}
        events=[]
        h=types.SimpleNamespace(restore_ds=Mock(side_effect=lambda:events.append('single-selected-start')),
            restore_router=Mock(side_effect=lambda:events.append('router')),verify=Mock(side_effect=lambda:(events.append('verify') or v)))
        return h,v,events
    def test_exact_clean_observer_failure_only(self):self.assertTrue(r.closed_contract(*self.fixture()))
    def test_native_or_API_failure_blocks(self):
        for kind in ('native','API'):
            f=list(self.fixture())
            if kind=='native':f[3][0]['returncode']=-9
            else:f[2]['server_returncode']=1
            with self.assertRaises(ValueError):r.closed_contract(*f)
    def test_another_phase_or_recovery_blocks(self):
        for key in r.rt.PHASE_KEYS:
            if key=='production_temporarily_stopped':continue
            f=list(self.fixture());f[0][key]=True
            with self.assertRaises(ValueError):r.closed_contract(*f)
        f=list(self.fixture());f[0]['maya144_baseline_recovery']={'active':True}
        with self.assertRaises(ValueError):r.closed_contract(*f)
    def test_other_failure_or_retry_blocks(self):
        for delta in ({'error':'native failed'},{'retry':True}):
            f=list(self.fixture());f[1].update(delta)
            with self.assertRaises(ValueError):r.closed_contract(*f)
    def test_kernel_fault_or_unclean_window_blocks(self):
        for delta in ({'kernel_capture_returncode':1},{'kernel_fault_lines':['Xid']}):
            f=list(self.fixture());f[5].update(delta)
            with self.assertRaises(ValueError):r.closed_contract(*f)
        f=list(self.fixture());f[4]['maintenance_resume_allowed']=True
        with self.assertRaises(ValueError):r.closed_contract(*f)
    def test_uncollected_transient_blocks(self):
        f=list(self.fixture());f[6]['dropins_absent']=False
        with self.assertRaises(ValueError):r.closed_contract(*f)
    def test_foreign_controller_or_live_native_blocks(self):
        for delta in ({'maintenance_controller':'foreign'},{'current_native_pid':1},{'production_temporarily_stopped':False}):
            f=list(self.fixture());f[0].update(delta)
            with self.assertRaises(ValueError):r.closed_contract(*f)
    def test_one_selected_start_then_router_verify_save(self):
        h,v,events=self.host();save=Mock(side_effect=lambda x:events.append('save'))
        self.assertEqual(r.restore_sequence(h,save),v);self.assertEqual(events,['single-selected-start','router','verify','save'])
        h.restore_ds.assert_called_once();save.assert_called_once_with(v)
    def test_selected_start_fault_never_retried(self):
        h,v,events=self.host();h.restore_ds.side_effect=RuntimeError('start');save=Mock()
        with self.assertRaises(RuntimeError):r.restore_sequence(h,save)
        h.restore_ds.assert_called_once();h.restore_router.assert_not_called();save.assert_not_called()
    def test_wrong_selected_model_policy_or_drafter_refused(self):
        for key,value in [('native_sha256','new'),('config_sha256','new'),('context',262144),('output_default',32768),('DSpark',False)]:
            h,v,events=self.host();v['selected_identity'][key]=value
            with self.assertRaises(ValueError):r.restore_sequence(h,Mock())
    def test_failed_verification_not_silently_accepted(self):
        h,v,events=self.host();v['passed']=False
        with self.assertRaises(ValueError):r.restore_sequence(h,Mock())
    def test_busy_public_probe_preserved_as_pending_without_restart(self):
        h,v,events=self.host(pending=True);save=Mock();self.assertTrue(r.restore_sequence(h,save)['pending_public_probe'])
        h.restore_ds.assert_called_once();save.assert_called_once()

if __name__=='__main__':unittest.main()
