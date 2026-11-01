"""Closed prior numerical source/format gates, without rereading model/logit payloads."""
import copy,json,unittest
from unittest.mock import patch
import numeric_lineage as n
class Lineage(unittest.TestCase):
    def frozen(self):return json.loads((n.P/'NUMERICAL_LINEAGE_FROZEN.json').read_text())
    def sample(self,profile='HGU'):
        row=self.frozen()[profile]
        return row,json.loads((n.E/row['files']['registry']['relative_to_E']).read_text()),json.loads((n.E/row['files']['audit']['relative_to_E']).read_text())
    def qualification(self):
        files={str(n.P/'NUMERICAL_LINEAGE_FROZEN.json'):n.sha(n.P/'NUMERICAL_LINEAGE_FROZEN.json')}
        for r in self.frozen().values():
            for entry in r['files'].values():files[str(n.E/entry['relative_to_E'])]=entry['sha256']
        return {'files':files}
    def test_all_four_actual_closed_finite_diagnostics(self):
        for profile in ('HGU','UNSLOTH','MS2','MS1'):self.assertTrue(n.contract(profile,*self.sample(profile)))
        self.assertTrue(n.guard(self.qualification()))
    def test_unreviewed_or_failed_previous_arm_refused(self):
        for key in ('attempted','fully_reviewed','accepted'):
            row,reg,audit=self.sample();reg[row['arm']][key]=False
            with self.assertRaises(ValueError):n.contract('HGU',row,reg,audit)
    def test_wrong_native_pack_TP_or_quality_policy_refused(self):
        for key,value in [('native_sha256','0'*64),('pack','/foreign'),('tp',1),('context_total',262144),('output_allowance',32768),('effort',50)]:
            row,reg,audit=self.sample();audit['whole_pack_factor'][key]=value
            with self.assertRaises(ValueError):n.contract('HGU',row,reg,audit)
        row,reg,audit=self.sample('MS1');audit['whole_pack_factor']['tp']=True
        with self.assertRaises(ValueError):n.contract('MS1',row,reg,audit)
    def test_partial_nonfinite_or_wrong_raw_bytes_refused(self):
        for key,value in [('rows',True),('bytes',1),('all_finite',False),('sha256','bad'),('token_row_alignment_claimed',True)]:
            row,reg,audit=self.sample();audit['finite_dumps'][0][key]=value
            with self.assertRaises(ValueError):n.contract('HGU',row,reg,audit)
        row,reg,audit=self.sample();audit['finite_dumps'].pop()
        with self.assertRaises(ValueError):n.contract('HGU',row,reg,audit)
    def test_failed_cleanup_or_wrong_resource_fence_refused(self):
        for key,value in [('passed',False),('memory_max',76*2**30),('swap_max',False),('prior_properties_restored',False),('transient_collected',False)]:
            row,reg,audit=self.sample();audit['private_fence'][key]=value
            with self.assertRaises(ValueError):n.contract('HGU',row,reg,audit)
    def test_previous_scope_cannot_become_quality_timing_or_retry(self):
        for key in ('general_quality_claim','performance_claim','deployment_admitted','retry'):
            row,reg,audit=self.sample();audit[key]=True
            with self.assertRaises(ValueError):n.contract('HGU',row,reg,audit)
    def test_missing_or_changed_membership_refused(self):
        q=self.qualification();q['files'].pop(next(iter(q['files'])))
        with self.assertRaises(ValueError):n.guard(q)
        q=self.qualification();key=next(k for k in q['files'] if k.endswith('terminal-audit.json'));q['files'][key]='0'*64
        with self.assertRaises(ValueError):n.guard(q)
    def test_changed_small_evidence_blocks_before_reuse(self):
        with patch.object(n,'sha',return_value='0'*64):
            with self.assertRaises(ValueError):n.guard(self.qualification())
if __name__=='__main__':unittest.main()
