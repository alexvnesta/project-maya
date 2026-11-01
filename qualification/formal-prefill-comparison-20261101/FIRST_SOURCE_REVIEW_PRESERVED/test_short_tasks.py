"""Exact whole-case short selections; no old-panel completion or model execution."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import short_tasks as s
class Selection(unittest.TestCase):
    def test_all_four_arms_select_same_complete_original_cold_case(self):
        self.assertEqual(len(s.ARMS),4)
        for arm,f in s.ARMS.items():
            m=s.manifest(arm);self.assertEqual(len(m['cases']),1);c=m['cases'][0]
            self.assertEqual(c['id'],'ms-quality-cold-text');self.assertEqual(c['prompt_tokens'],8469)
            self.assertEqual(m['profile'],f['profile']);self.assertEqual(m['replicate'],f['replicate']);self.assertEqual(m['arm'],arm)
    def test_complete_parent_case_bytes_are_preserved(self):
        for profile in s.PROFILES:
            for task in ('prefill',):
                row,c,parent=s.source(profile,task);self.assertEqual(c,next(x for x in parent['cases'] if x['id']==row['case_id']));self.assertEqual(s.digest(c),row['case_sha256'])
    def test_full_model_capacity_and_request_limits(self):
        for arm in s.ARMS:
            m=s.manifest(arm);self.assertEqual(m['context'],1048576);self.assertEqual(m['default_output'],262144)
            q=m['cases'][0]['request'];self.assertEqual(q['max_tokens'],32768);self.assertEqual(q['reasoning_effort'],100);self.assertEqual(q['reasoning_budget_tokens'],0);self.assertEqual(q['seed'],1)
    def test_whole_original_cold_case_only_without_other_panel_completion(self):
        for arm in s.ARMS:
            m=s.manifest(arm);self.assertEqual(m['lifecycle_cases'],[]);self.assertEqual(len(m['cases'][0]['prompt_ids']),8469);self.assertFalse(m['source_whole_panel_claimed_complete'])
    def test_encoding_provenance_preserves_each_original_picker(self):
        for arm in s.ARMS:
            m=s.manifest(arm);t=m['effective_template'];self.assertEqual(t['pack_template_replaced'],m['profile']=='PROD')
            self.assertEqual(t['effective_template_sha256'],'06cada875e3a04665f9cf47deae9ef32e16ede2c6511205a4031c8b48140d01b' if m['profile']=='PROD' else '753420ada6b529bbdeefe3c24932f948696a71dd36f54491ec951cbc44f40c16')
    def test_no_runtime_bound_quality_or_deployment_admission(self):
        for arm in s.ARMS:
            m=s.manifest(arm)
            for key in ('long_input_runtime_bound_claim','general_quality_or_equivalence_claim','deployment_admitted','automatic_next_arm'):self.assertIs(m[key],False)
    def test_returned_requests_are_independent_copies(self):
        m=s.manifest('A1');m['cases'][0]['request']['max_tokens']=1
        self.assertEqual(s.manifest('A1')['cases'][0]['request']['max_tokens'],32768)
    def test_unknown_arm_task_profile_and_boolean_refused(self):
        for arm in ('CS1','FHGU','P-HGU-3','A1-extra','',True,None):
            with self.assertRaises(ValueError):s.factor(arm)
        for profile,task in [('TP2','prefill'),('PROD','shortened'),('MS2','quality')]:
            with self.assertRaises(ValueError):s.source(profile,task)
    def test_duplicate_or_nonfinite_json_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'x.json'
            for raw in ('{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}'):
                p.write_text(raw)
                with self.assertRaises(ValueError):s.read(p)
    def test_alias_and_oversize_source_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'x.json';p.write_text('{}');a=p.with_name('alias');a.symlink_to(p)
            with self.assertRaises(ValueError):s.read(a)
            with p.open('wb') as f:f.truncate(4*2**20)
            with self.assertRaises(ValueError):s.read(p)
    def test_changed_source_hash_blocks_before_case_use(self):
        with patch.object(s,'sha',return_value='0'*64):
            with self.assertRaises(ValueError):s.source('PROD','prefill')
    def test_source_registry_cannot_add_foreign_factor(self):
        original=s.read(s.P/'SHORT_SOURCES_FROZEN.json');original['OTHER-prefill']=copy.deepcopy(original['PROD-prefill'])
        with patch.object(s,'read',return_value=original):
            with self.assertRaises(ValueError):s.source('PROD','prefill')
if __name__=='__main__':unittest.main()
