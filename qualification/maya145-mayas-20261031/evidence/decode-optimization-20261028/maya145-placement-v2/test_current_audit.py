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
        argv=['/r/venv/bin/python3.14','-B','/p/current_compat.py','--phase','--mode','compatibility','--arm','DTP2','--output',str(out),'--proof',str(meta/'proof.json')]
        w={'command':argv,'continued_from':'prior','test_returncode':0,'maintenance_held':True,'maintenance_resume_allowed':True,'restored':False}
        return w,out,meta,r
    def result(self):
        m={'cases':[{'id':'literal'}]}
        v={'mode':'compatibility','arm':'DTP2','private_cleanup_passed':True,'not_a_promotion':True,
            'arm_results':{'complete':True,'native_request_count':1,'retry':False,'automatic_next_arm':False,
                'quality_or_performance_pass':False,'manual_review_required':True,'DSI1_leftovers':[],
                'rows':[{}],'scores':[{'id':'literal','passed':True,'status':'SHORT_LITERAL_SOURCE_AND_STATE_PASSED'}]}}
        return v,m
    def test_exact_window_exit0(self):a.window_contract(*self.window(),'DTP2')
    def test_wrong_or_unfinished_window_refused(self):
        for field,value in [('test_returncode',1),('test_returncode',False),('maintenance_held',False),('maintenance_resume_allowed',False),('restored',True)]:
            w,*rest=self.window();w[field]=value
            with self.assertRaises(ValueError):a.window_contract(w,*rest,'DTP2')
    def test_old_entry_or_other_arm_refused(self):
        w,*rest=self.window();w['command'][2]='/p/ms_compat.py'
        with self.assertRaises(ValueError):a.window_contract(w,*rest,'DTP2')
        with self.assertRaises(ValueError):a.window_contract(*self.window(),'DTP1')
    def test_complete_short_scope_only(self):
        v,m=self.result();self.assertTrue(a.complete_contract(v,m,'DTP2')['complete'])
    def test_cap_partial_UNRUN_retry_and_broader_claim_refused(self):
        for field,value in [('complete',False),('native_request_count',0),('native_request_count',True),('retry',True),
            ('automatic_next_arm',True),('quality_or_performance_pass',True),('DSI1_leftovers',['leak']),('unrun_ids',['x']),('reason','partial')]:
            v,m=self.result();v['arm_results'][field]=value
            with self.assertRaises(ValueError):a.complete_contract(v,m,'DTP2')
    def test_unreviewed_or_wrong_scoring_refused(self):
        v,m=self.result();v['arm_results']['scores'][0]['status']='UNRUN'
        with self.assertRaises(ValueError):a.complete_contract(v,m,'DTP2')
        v,m=self.result();v['arm']='DTP1'
        with self.assertRaises(ValueError):a.complete_contract(v,m,'DTP2')
    def test_private_cleanup_required(self):
        v,m=self.result();v['private_cleanup_passed']=False
        with self.assertRaises(ValueError):a.complete_contract(v,m,'DTP2')
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


class CurrentFenceAudit(unittest.TestCase):
    def fixture(self):
        unit={'InvocationID':'a'*32,'Transient':'yes','ControlGroup':'/owned','FragmentPath':'/owned/window.service','MemoryMax':'infinity','MemorySwapMax':'infinity'}
        initial={'memory_max':80*2**30,'swap_max':0,'events_before':{'oom':0,'oom_kill':0},'prior_properties':{'MemoryMax':'max','MemorySwapMax':'max'},'unit_before':copy.deepcopy(unit),'fragment':'/owned/window.service','owned_dropin_directory':'/owned/window.service.d'}
        terminal={'passed':True,'events_after':{'oom':0,'oom_kill':0},'events_delta':{'oom':0,'oom_kill':0}}
        restored={'passed':True,'same_invocation':True,'children_closed':True,'prior_properties':{'MemoryMax':'max','MemorySwapMax':'max'},'restored_properties':{'MemoryMax':'max','MemorySwapMax':'max'},'unit_after':copy.deepcopy(unit)}
        collected={**{k:True for k in ('passed','transient','unit_collected','fragment_absent','dropins_absent')},'original_invocation':'a'*32,'fragment':initial['fragment'],'owned_dropin_directory':initial['owned_dropin_directory']}
        initial.update(installed=True,mutation_attempted=True,initial_current=1024,unit_installed={**unit,'MemoryMax':str(80*2**30),'MemorySwapMax':'0'})
        return initial,terminal,restored,collected
    def test_actual80_resource_contract(self):self.assertEqual(a.fence_contract(*self.fixture())['memory_max'],80*2**30)
    def test_old76_and_unclean_or_foreign_resource_contract_refused(self):
        for slot,key,value in [(0,'memory_max',76*2**30),(0,'swap_max',1),(1,'events_after',{'oom':1,'oom_kill':0}),(2,'children_closed',False),(2,'same_invocation',False),(3,'unit_collected',False),(3,'original_invocation','b'*32)]:
            args=list(self.fixture());args[slot][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a.fence_contract(*args)

    def test_missing_failed_or_wrong_actual_install_refused(self):
        for key,value in [('installed',False),('mutation_attempted',False),('initial_current',True),('initial_current',80*2**30)]:
            args=list(self.fixture());args[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a.fence_contract(*args)
        for key,value in [('MemoryMax',str(76*2**30)),('MemorySwapMax','max'),('InvocationID','b'*32),('ControlGroup','/foreign')]:
            args=list(self.fixture());args[0]['unit_installed'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a.fence_contract(*args)

if __name__=='__main__':unittest.main()
