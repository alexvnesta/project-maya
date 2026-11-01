"""Regression for stale failed-experiment bindings after successful recovery."""
import copy,json
from pathlib import Path
import unittest
import baseline_identity as b
HERE=Path(__file__).resolve().parent

def sample():return json.loads((HERE/'CURRENT_BASELINE_RECOVERY_SNAPSHOT.json').read_text())

class Resolver(unittest.TestCase):
    def test_actual_separate_recovery_not_old_HOLD_is_selected(self):
        s=sample();old=copy.deepcopy(s);v=b.selected_binding(s);self.assertEqual(v,s['maya145quality_recovery_current']['start_binding']);self.assertEqual(s,old);self.assertEqual(s['decode_optimization_current']['status'],'STOPPED_FOR_OFFLINE_DIAGNOSIS')
    def test_no_historical_fallback_or_unverified_recovery(self):
        for key,value in [('active',True),('error','fault'),('status','RUNNING')]:
            s=sample();s['maya145quality_recovery_current'][key]=value
            with self.assertRaises(ValueError):b.selected_binding(s)
        s=sample();s['maya145quality_recovery_current']['result']['verified']['passed']=False
        with self.assertRaises(ValueError):b.selected_binding(s)
    def test_native_pid_mismatch_and_boolean_refused(self):
        for v in (None,True,1347196,0):
            s=sample();s['current_native_pid']=v
            with self.assertRaises(ValueError):b.selected_binding(s)
    def test_stale_current_binding_refused(self):
        s=sample();s['decode_optimization_current']['selected_identity']['start_binding']['native_pid']=1347196
        with self.assertRaises(ValueError):b.selected_binding(s)
    def test_binding_result_and_bad_invocation_refused(self):
        for key,v in [('native_pid',True),('invocation','old')]:
            s=sample();s['maya145quality_recovery_current']['result']['verified']['selected_identity']['start_binding'][key]=v
            with self.assertRaises(ValueError):b.selected_binding(s)
    def test_changed_selected_policy_refused(self):
        for key,v in [('native_sha256','adff'),('config_sha256','other'),('context',262144),('output_default',32768),('DSpark',False),('images',False),('TP',2),('all_CPU_experts_RAM',False),('Q8',[0,0])]:
            s=sample();s['maya145quality_recovery_current']['result']['verified']['selected_identity'][key]=v
            with self.assertRaises(ValueError):b.selected_binding(s)
    def test_public_failure_or_single_chunk_assumption_not_accepted(self):
        for key,v in [('SSE_done',False),('known_answer_passed',False),('content','READ'),('finish','length'),('authenticated_models',401)]:
            s=sample();s['maya145quality_recovery_current']['result']['verified']['public'][key]=v
            with self.assertRaises(ValueError):b.selected_binding(s)
    def test_new_recovery_must_match_current_failed_controller(self):
        s=sample();s['maya145quality2_recovery_current']=copy.deepcopy(s['maya145quality_recovery_current']);s['maintenance_controller']='/new/controller';s['maya145quality2_recovery_current']['failed_controller']='/new/controller'
        self.assertEqual(b.selected_binding(s)['native_pid'],s['current_native_pid'])
        s['maya145quality2_recovery_current']['failed_controller']='/other/controller'
        with self.assertRaises(ValueError):b.selected_binding(s)
    def test_directio_recovery_matches_current_failed_controller(self):
        s=sample();s['maya145modelchoice_recovery_current']=copy.deepcopy(s['maya145quality_recovery_current']);s['maintenance_controller']='/io/controller';s['maya145modelchoice_recovery_current']['failed_controller']='/io/controller'
        self.assertEqual(b.selected_binding(s)['native_pid'],s['current_native_pid'])
        s['maya145modelchoice_recovery_current']['failed_controller']='/other/controller'
        with self.assertRaises(ValueError):b.selected_binding(s)
    def test_formal_recovery_requires_actual_failed_controller_binding(self):
        s=sample();s['maya145formalprefill_recovery_current']=copy.deepcopy(s['maya145quality_recovery_current']);s['maintenance_controller']='/formal/controller';s['maya145formalprefill_recovery_current']['failed_controller']='/formal/controller'
        self.assertEqual(b.selected_binding(s)['native_pid'],s['current_native_pid'])
        s['maya145formalprefill_recovery_current']['failed_controller']='/old/modeltask/controller'
        with self.assertRaises(ValueError):b.selected_binding(s)
    def test_new_clean_phase_verification_supersedes_dated_recovery(self):
        s=sample();s['decode_optimization_current']['verified']=copy.deepcopy(s['maya145quality_recovery_current']['result']['verified']);s['maya145quality_recovery_current']['active']=True
        self.assertEqual(b.selected_binding(s)['native_pid'],s['current_native_pid'])

if __name__=='__main__':unittest.main()
