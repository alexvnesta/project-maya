import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
import current_audit as a

class Audit(unittest.TestCase):
    def window(self):
        r=types.SimpleNamespace(R=Path('/r'),P=Path('/p'));out=Path('/e/results/new');meta=Path('/e/maintenance/new')
        argv=['/r/venv/bin/python3.14','-B','/p/current_compat.py','--phase','--mode','compatibility','--arm','CTP2','--output',str(out),'--proof',str(meta/'proof.json')]
        w={'command':argv,'continued_from':'prior','test_returncode':0,'maintenance_held':True,'maintenance_resume_allowed':True,'restored':False}
        return w,out,meta,r
    def result(self):
        m={'cases':[{'id':'literal'}]}
        v={'mode':'compatibility','arm':'CTP2','private_cleanup_passed':True,'not_a_promotion':True,
            'arm_results':{'complete':True,'native_request_count':1,'retry':False,'automatic_next_arm':False,
                'quality_or_performance_pass':False,'manual_review_required':True,'DSI1_leftovers':[],
                'rows':[{}],'scores':[{'id':'literal','passed':True,'status':'SHORT_LITERAL_SOURCE_AND_STATE_PASSED'}]}}
        return v,m
    def test_exact_window_exit0(self):a.window_contract(*self.window(),'CTP2')
    def test_wrong_or_unfinished_window_refused(self):
        for field,value in [('test_returncode',1),('test_returncode',False),('maintenance_held',False),('maintenance_resume_allowed',False),('restored',True)]:
            w,*rest=self.window();w[field]=value
            with self.assertRaises(ValueError):a.window_contract(w,*rest,'CTP2')
    def test_old_entry_or_other_arm_refused(self):
        w,*rest=self.window();w['command'][2]='/p/ms_compat.py'
        with self.assertRaises(ValueError):a.window_contract(w,*rest,'CTP2')
        with self.assertRaises(ValueError):a.window_contract(*self.window(),'CTP1')
    def test_complete_short_scope_only(self):
        v,m=self.result();self.assertTrue(a.complete_contract(v,m,'CTP2')['complete'])
    def test_cap_partial_UNRUN_retry_and_broader_claim_refused(self):
        for field,value in [('complete',False),('native_request_count',0),('native_request_count',True),('retry',True),
            ('automatic_next_arm',True),('quality_or_performance_pass',True),('DSI1_leftovers',['leak']),('unrun_ids',['x']),('reason','partial')]:
            v,m=self.result();v['arm_results'][field]=value
            with self.assertRaises(ValueError):a.complete_contract(v,m,'CTP2')
    def test_unreviewed_or_wrong_scoring_refused(self):
        v,m=self.result();v['arm_results']['scores'][0]['status']='UNRUN'
        with self.assertRaises(ValueError):a.complete_contract(v,m,'CTP2')
        v,m=self.result();v['arm']='CTP1'
        with self.assertRaises(ValueError):a.complete_contract(v,m,'CTP2')
    def test_private_cleanup_required(self):
        v,m=self.result();v['private_cleanup_passed']=False
        with self.assertRaises(ValueError):a.complete_contract(v,m,'CTP2')
    def test_duplicate_and_nonfinite_saved_JSON_refused(self):
        for data in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'):
            with self.assertRaises(ValueError):a.parse(data)
    def test_recorder_hashes_exact_small_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'r.json';p.write_text('{"x":1}');r=a.Recorder();self.assertEqual(r.json(p),{'x':1});self.assertEqual(r.pins[str(p)],a.sha(p))
            p.write_text('{"x":2}')
            with self.assertRaises(ValueError):r.json(p)
    def test_recorder_refuses_alias_and_large_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'r';p.write_text('x');q=p.with_name('alias');q.symlink_to(p)
            with self.assertRaises(ValueError):a.Recorder().bytes(q)
            with p.open('wb') as f:f.truncate(a.MAX_EVIDENCE_BYTES+1)
            with self.assertRaises(ValueError):a.Recorder().bytes(p)
    def test_exact_comparison_preserves_types(self):
        self.assertFalse(a.same({'x':1},{'x':True}));self.assertFalse(a.same({'x':1},{'x':1.0}))

if __name__=='__main__':unittest.main()
