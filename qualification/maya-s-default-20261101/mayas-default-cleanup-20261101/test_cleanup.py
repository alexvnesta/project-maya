import copy,unittest
from pathlib import Path
import cleanup as c

class Contract(unittest.TestCase):
    def setUp(self):
        self.path=c.R/'models/ista-iq2-xs/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XS-00001-of-00004.gguf'
        self.plan={'schema':'mayas-selected-unused-weights-v1','selected_native':c.NATIVE,'selected_config':c.CONFIG,
                   'count':1,'bytes':3,'rows':[{'path':str(self.path),'signature':{'dev':1,'ino':2,'size':3}}],'protected':{}}
        self.binding={'native_pid':1};self.state={'decode_optimization_current':{'status':'MAYAS_TP2_DEFAULT_ACTIVE_VERIFIED','selected_identity':{'start_binding':self.binding}},'active_cpu_build':False}
    def test_only_explicit_unused_paths(self):self.assertTrue(c.allowed(self.path));c.plan_contract(self.plan)
    def test_selected_assets_and_caches_refused(self):
        for p in [c.DC/'s2-reconstruction-v1/base-acquisition-v1/assets/Maya-S/a.gguf',c.DC/'mayas-tp2-production-v4/pack-FIRST/tensors.txt',c.R/'models/shared/vision.bin',c.DC/'results/logits.3.f32',Path('/tmp/cache/x')]:
            with self.subTest(path=p):self.assertFalse(c.allowed(p))
    def test_near_named_paths_refused(self):
        for p in [str(self.path)+'.new',str(self.path).replace('00001-of','00005-of'),str(self.path).replace('ista-iq2-xs','other')]:self.assertFalse(c.allowed(p))
    def test_duplicate_rows_refused(self):
        self.plan['rows']*=2;self.plan.update(count=2,bytes=6)
        with self.assertRaises(ValueError):c.plan_contract(self.plan)
    def test_selected_inode_refused(self):
        self.plan['protected']={'selected':{'dev':1,'ino':2}}
        with self.assertRaises(ValueError):c.plan_contract(self.plan)
    def test_wrong_counts_bytes_or_selected_artifacts_refused(self):
        for k,v in [('count',2),('bytes',4),('selected_native','wrong'),('selected_config','wrong')]:
            p=copy.deepcopy(self.plan);p[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):c.plan_contract(p)
    def test_bound_state_and_owned_claim(self):
        c.state_contract(self.state,self.binding);claim={'pid':2};self.state['active_cpu_build']=claim;c.state_contract(self.state,self.binding,claim)
    def test_foreign_binding_claim_and_phase_refused(self):
        for change in [{'active_cpu_build':{'pid':3}},{'active_private_phase':True},{'production_verification_pending':'foreign'}]:
            with self.subTest(change=change),self.assertRaises(ValueError):c.state_contract({**self.state,**change},self.binding)
        with self.assertRaises(ValueError):c.state_contract(self.state,{'native_pid':9})
    def test_unverified_selection_refused(self):
        self.state['decode_optimization_current']['status']='pending'
        with self.assertRaises(ValueError):c.state_contract(self.state,self.binding)

if __name__=='__main__':unittest.main()
