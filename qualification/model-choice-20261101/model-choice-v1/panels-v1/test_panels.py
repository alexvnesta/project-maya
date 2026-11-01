"""Actual preserved-template panel encodings and independent mutation negatives."""
import copy,unittest
from unittest.mock import patch
import panels as p
MANIFESTS={}
class Panels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ('HGU','UNSLOTH'):
            for mode in ('quality','prose','coding','lifecycle'):MANIFESTS[name+'-'+mode]=p.encode(name,mode)
    def sample(self):return copy.deepcopy(MANIFESTS['HGU-quality'])
    def helper(self):return p.prior().helper()
    def test_all_actual_panels_preserve_complete_work(self):
        self.assertEqual(set(MANIFESTS),{n+'-'+m for n in ('HGU','UNSLOTH') for m in ('quality','prose','coding','lifecycle')})
        for key,m in MANIFESTS.items():self.assertTrue(p.contract(m,self.helper()));self.assertIn(m['candidate'],key)
    def test_both_actual_original_templates_remain_distinct(self):
        for name,pin in [('HGU','753420ada6b529bbdeefe3c24932f948696a71dd36f54491ec951cbc44f40c16'),('UNSLOTH','06cada875e3a04665f9cf47deae9ef32e16ede2c6511205a4031c8b48140d01b')]:
            for mode in ('quality','prose','coding','lifecycle'):
                m=MANIFESTS[name+'-'+mode];self.assertEqual(m['effective_template']['effective_template_sha256'],pin);self.assertFalse(m['effective_template']['pack_template_replaced'])
    def test_actual_image_spans_cross_retained_tail(self):
        for name in ('HGU','UNSLOTH'):
            c=MANIFESTS[name+'-quality']['cases'][2];spans=c['image_spans'];cut=c['prompt_tokens']-2668
            self.assertEqual(len(spans),2);self.assertLessEqual(spans[0]['start']+spans[0]['length'],cut);self.assertGreaterEqual(spans[1]['start'],cut)
    def test_actual_warm_and_return_paths_are_identical(self):
        for name in ('HGU','UNSLOTH'):
            for mode in ('quality','prose','coding'):
                c=MANIFESTS[name+'-'+mode]['cases'];self.assertEqual(c[0]['prompt_ids'],c[1]['prompt_ids'])
                if mode=='quality':self.assertEqual(c[0]['prompt_ids'],c[3]['prompt_ids'])
    def test_actual_tool_and_cancel_work_preserved(self):
        f=self.helper()
        for name in ('HGU','UNSLOTH'):
            c=MANIFESTS[name+'-lifecycle']['cases'];self.assertEqual([x['id'] for x in c],list(f.LIFECYCLE_IDS));self.assertEqual(c[0]['request'],f.TOOL_REQUEST);self.assertEqual(c[-1]['expected'],'RECOVERED_Q8_LITERAL')
    def test_actual_short_prose_and_coding_full_requests(self):
        f=self.helper()
        for name in ('HGU','UNSLOTH'):
            self.assertEqual(MANIFESTS[name+'-prose']['cases'][-1]['request'],f.PROSE_CASES[0]['request']);self.assertEqual(MANIFESTS[name+'-coding']['cases'][-1]['request'],f.CODE_REQUEST)
    def test_capacity_or_effort_reduction_refused(self):
        for key,value in [('context',262144),('default_output',32768),('policy',{})]:
            m=self.sample();m[key]=value
            with self.assertRaises(ValueError):p.contract(m,self.helper())
    def test_visible_prompt_or_output_cap_changes_refused(self):
        for key,value in [('messages',[{'role':'user','content':'shorter'}]),('max_tokens',1024),('reasoning_effort',50)]:
            m=self.sample();m['cases'][0]['request'][key]=value
            with self.assertRaises(ValueError):p.contract(m,self.helper())
    def test_omitted_or_reordered_case_refused(self):
        for action in ('drop','reverse'):
            m=self.sample()
            if action=='drop':m['cases'].pop()
            else:m['cases'].reverse()
            with self.assertRaises(ValueError):p.contract(m,self.helper())
    def test_changed_encoding_or_image_span_refused(self):
        for key,value in [('prompt_tokens',1),('prompt_ids_sha256','0'*64),('image_spans',[])]:
            m=self.sample();index=2 if key=='image_spans' else 0;m['cases'][index][key]=value
            with self.assertRaises(ValueError):p.contract(m,self.helper())
    def test_changed_pack_or_template_provenance_refused(self):
        for key,value in [('pack_relative_to_E','foreign'),('tokenizer_source_sha256',{}),('request_source_sha256',{}),('effective_template',{})]:
            m=self.sample();m[key]=value
            with self.assertRaises(ValueError):p.contract(m,self.helper())
    def test_encoding_never_grants_GPU_or_quality_admission(self):
        for key in ('GPU_launch_ready','quality_or_performance_pass','automatic_next_arm'):
            m=self.sample();m[key]=True
            with self.assertRaises(ValueError):p.contract(m,self.helper())
    def test_unknown_panel_or_candidate_refused(self):
        for mode in ('shortened','',None):
            with self.assertRaises(ValueError):p.requests(self.helper(),mode)
        m=self.sample();m['candidate']='TP2'
        with self.assertRaises(ValueError):p.contract(m,self.helper())
    def test_source_helper_drift_refused_before_import(self):
        with patch.object(p,'sha',return_value='0'*64):
            with self.assertRaises(ValueError):p.prior()
if __name__=='__main__':unittest.main()
