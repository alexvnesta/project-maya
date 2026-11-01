"""Saved failed-window facts plus strict source-placement and span negatives."""
import copy
import json
from pathlib import Path
import unittest
import current_skip as c
HERE=Path(__file__).resolve().parent

def actual():return json.loads((HERE/'saved-QTP2/startup-audit.json').read_text())
def log(device=0,rows=(5801,5988)):return '\n'.join(f'ds4: prompt skip: layers 20-39 from CUDA{device}, {n} early rows KV-only, 2668 kept' for n in rows)
def tp1(cut):
    s=actual();rows=s['current_engine']['placement'];rows[0].update(tp=1,first_layer=0,last_layer=42,member=None,head=False);rows[1].update(tp=1,first_layer=cut,last_layer=39,member=None,head=True);return s

class Actual(unittest.TestCase):
    def test_saved_TP2_exact_source_and_both_cold_counts(self):
        s=actual();text=(HERE/'saved-QTP2/engine.log').read_text();r=c.activation(text,s,'TP2',[5801,5988],complete=True)
        self.assertEqual(r['source_device'],0);self.assertEqual(r['activation_early_rows'],[5801,5988]);self.assertEqual(r['retained_rows'],2668);self.assertTrue(r['complete_evidence']);self.assertIn('NO_PHASE_LIFECYCLE',r['scope'])
        failure=json.loads((HERE/'saved-QTP2/phase-error.json').read_text());self.assertIn('Unexpected skip source',failure['error'])
    def test_saved_four_rows_remain_observation_not_phase_success(self):
        v=json.loads((HERE/'saved-QTP2/case-progress.json').read_text());self.assertTrue(v['complete']);self.assertEqual(len(v['scores']),4);self.assertTrue(all(x['passed'] for x in v['scores']));self.assertFalse(v['quality_or_performance_pass'])
        self.assertEqual([x['native']['reused'] for x in v['rows']],[0,8468,0,8468])
    def test_TP1_auto_cut19_sources_CUDA1(self):self.assertEqual(c.activation(log(1),tp1(19),'TP1',[5801,5988],complete=True)['source_device'],1)
    def test_TP1_auto_cut21_sources_CUDA0(self):self.assertEqual(c.activation(log(0),tp1(21),'TP1',[5801,5988],complete=True)['source_device'],0)
    def test_TP1_layer20_boundary_is_later_segment(self):self.assertEqual(c.source_device(tp1(20),'TP1'),1)
    def test_TP2_member_order_comes_from_actual_rows(self):
        s=actual();s['current_engine']['placement'].reverse();self.assertEqual(c.source_device(s,'TP2'),0)
    def test_partial_prefix_remains_explicitly_incomplete(self):
        r=c.activation(log(rows=(5801,)),actual(),'TP2',[5801,5988],complete=False);self.assertFalse(r['complete_evidence'])
        with self.assertRaises(ValueError):c.activation(log(rows=(5801,)),actual(),'TP2',[5801,5988],complete=True)
    def test_no_marker_cannot_pass_complete_cold_suite(self):
        with self.assertRaises(ValueError):c.activation('',actual(),'TP2',[5801,5988],complete=True)
        self.assertEqual(c.activation('',actual(),'TP2',[5801,5988],complete=False)['activation_early_rows'],[])
    def test_warm_only_expectation_cannot_accept_activation(self):
        self.assertEqual(c.activation('',actual(),'TP2',[],complete=True)['activation_early_rows'],[])
        with self.assertRaises(ValueError):c.activation(log(),actual(),'TP2',[],complete=True)

class Negatives(unittest.TestCase):
    def test_legacy_CUDA1_marker_refused_for_actual_TP2(self):
        with self.assertRaises(ValueError):c.activation(log(1),actual(),'TP2',[5801,5988],complete=True)
    def test_wrong_source_span_retention_device_or_marker_refused(self):
        for old,new in [('20-39','19-39'),('20-39','20-40'),('2668 kept','2667 kept'),('CUDA0','CUDA2'),('5801 early','0 early'),('5801 early','-1 early'),('5801 early','5801.0 early'),('2668 kept','2668 kept extra'),('prompt skip:','prompt skip :')]:
            with self.assertRaises(ValueError):c.activation(log().replace(old,new),actual(),'TP2',[5801,5988],complete=True)
    def test_wrong_order_duplicate_extra_and_missing_rows_refused(self):
        for rows in [(5988,5801),(5801,5801),(5801,5988,5988),(5801,),()]:
            with self.assertRaises(ValueError):c.activation(log(rows=rows),actual(),'TP2',[5801,5988],complete=True)
    def test_partial_cannot_hide_wrong_or_extra_rows(self):
        for rows in [(5988,),(5801,5988,5988)]:
            with self.assertRaises(ValueError):c.activation(log(rows=rows),actual(),'TP2',[5801,5988],complete=False)
    def test_untyped_or_unfrozen_expectations_refused(self):
        for expected,complete in [([True,5988],True),([0,5988],True),(['5801',5988],True),((5801,5988),True),([5801,5988],1)]:
            with self.assertRaises(ValueError):c.activation(log(),actual(),'TP2',expected,complete=complete)
    def test_unverified_or_inconsistent_actual_PID_refused(self):
        for change in ('passed','pid','env','exe'):
            s=actual()
            if change=='passed':s['passed']=False
            if change=='pid':s['actual_process']['native_pid']+=1
            if change=='env':s['actual_process']['controlled_env']['DS4_YOCO']='0'
            if change=='exe':s['actual_process']['same_executable']=False
            with self.assertRaises(ValueError):c.source_device(s,'TP2')
    def test_foreign_native_source_cannot_borrow_placement_booleans(self):
        s=actual();s['actual_process']['native_sha256']='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
        with self.assertRaises(ValueError):c.source_device(s,'TP2')
    def test_wrong_mode_or_missing_startup_checks_refused(self):
        for change in ('variant','Q8','projection','engine','boolean_device'):
            s=actual()
            if change=='Q8':s['current_engine']['Q8_devices']=[0]
            if change=='projection':s['current_engine']['projection_devices']=[1]
            if change=='engine':s['current_engine']['passed']=False
            if change=='boolean_device':s['current_engine']['Q8_devices']=[False,True]
            with self.assertRaises(ValueError):c.source_device(s,'TP1' if change=='variant' else 'TP2')
    def test_duplicate_device_member_or_boolean_dimensions_refused(self):
        for change in ('device','member','bool','span'):
            s=actual();r=s['current_engine']['placement'][1]
            if change=='device':r['device']=0
            if change=='member':r['member']=0
            if change=='bool':r['first_layer']=False
            if change=='span':r['last_layer']=19
            with self.assertRaises(ValueError):c.source_device(s,'TP2')
    def test_invalid_TP1_trunk_boundary_refused(self):
        for cut in (0,40,True):
            with self.assertRaises(ValueError):c.source_device(tp1(cut),'TP1')

if __name__=='__main__':unittest.main()
