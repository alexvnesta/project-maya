"""Exact whole-case short selections; no old-panel completion or model execution."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import short_tasks as s
class Selection(unittest.TestCase):
    def test_all_sixteen_arms_select_one_original_main(self):
        self.assertEqual(len(s.ARMS),16)
        for arm,f in s.ARMS.items():
            m=s.manifest(arm);self.assertEqual(len(m['cases']),1);c=m['cases'][0]
            self.assertEqual(c['id'],'ms-'+f['task']+'-main');self.assertEqual(c['prompt_tokens'],169 if f['task']=='prose' else 140)
            self.assertEqual(m['profile'],f['profile']);self.assertEqual(m['replicate'],f['replicate']);self.assertEqual(m['arm'],arm)
    def test_complete_parent_case_bytes_are_preserved(self):
        for profile in s.PROFILES:
            for task in ('prose','coding'):
                row,c,parent=s.source(profile,task);self.assertEqual(c,next(x for x in parent['cases'] if x['id']==row['case_id']));self.assertEqual(s.digest(c),row['case_sha256'])
    def test_full_model_capacity_and_request_limits(self):
        for arm in s.ARMS:
            m=s.manifest(arm);self.assertEqual(m['context'],1048576);self.assertEqual(m['default_output'],262144)
            q=m['cases'][0]['request'];self.assertEqual(q['max_tokens'],32768);self.assertEqual(q['reasoning_effort'],100);self.assertEqual(q['reasoning_budget_tokens'],0);self.assertEqual(q['seed'],1)
    def test_long_preludes_and_lifecycle_not_in_short_observation(self):
        for arm in s.ARMS:
            m=s.manifest(arm);self.assertEqual(m['lifecycle_cases'],[]);self.assertLess(len(m['cases'][0]['prompt_ids']),200);self.assertFalse(m['source_whole_panel_claimed_complete'])
    def test_encoding_provenance_is_original_not_replaced(self):
        for arm in s.ARMS:
            m=s.manifest(arm);self.assertFalse(m['effective_template']['pack_template_replaced']);self.assertEqual(m['effective_template']['effective_template_sha256'],m['tokenizer_source_sha256']['chat_template.jinja'])
    def test_no_runtime_bound_quality_or_deployment_admission(self):
        for arm in s.ARMS:
            m=s.manifest(arm)
            for key in ('cold_bound_previously_measured_for_this_profile','long_input_runtime_bound_claim','general_quality_or_equivalence_claim','deployment_admitted','automatic_next_arm'):self.assertIs(m[key],False)
    def test_returned_requests_are_independent_copies(self):
        m=s.manifest('P-HGU-1');m['cases'][0]['request']['max_tokens']=1
        self.assertEqual(s.manifest('P-HGU-1')['cases'][0]['request']['max_tokens'],32768)
    def test_unknown_arm_task_profile_and_boolean_refused(self):
        for arm in ('B1','FHGU','P-HGU-3','P-HGU-1-extra','',True,None):
            with self.assertRaises(ValueError):s.factor(arm)
        for profile,task in [('TP2','prose'),('HGU','shortened'),('HGU','quality')]:
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
            with self.assertRaises(ValueError):s.source('HGU','prose')
    def test_source_registry_cannot_add_foreign_factor(self):
        original=s.read(s.P/'SHORT_SOURCES_FROZEN.json');original['OTHER-prose']=copy.deepcopy(original['HGU-prose'])
        with patch.object(s,'read',return_value=original):
            with self.assertRaises(ValueError):s.source('HGU','prose')
if __name__=='__main__':unittest.main()
