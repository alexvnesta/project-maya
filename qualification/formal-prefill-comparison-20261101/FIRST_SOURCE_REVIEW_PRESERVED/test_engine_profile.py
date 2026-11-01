"""Source-specific selected92 and MayaS TP2 profiles, full policy and instrumentation-free timed paths."""
import copy,json,unittest
from pathlib import Path
import engine_profile as p
import short_tasks as t
class Profile(unittest.TestCase):
    def base(self):return json.loads((Path(__file__).parent/'profile-base-config.json').read_text())
    def directory(self,arm):return p.E/('results/maya145-formal-prefill-'+arm+'-20261101T050000Z/native')
    def test_each_full_profile_preserves_base_capacity_drafter_and_quality(self):
        b=self.base();original=copy.deepcopy(b)
        for arm,a in t.ARMS.items():
            c=p.profile(b,self.directory(arm),a['profile'],arm);self.assertEqual(b,original)
            for key in ('--max-context','--dspark','--dspark-conf','--cpu-threads','--mmap-experts','--prefill-chunk','--ablate','--ablate-scale'):
                self.assertEqual(c['args'][c['args'].index(key)+1],b['args'][b['args'].index(key)+1])
            self.assertEqual(c['hosted_default_effort'],100);self.assertFalse(c['fit_max_tokens']);self.assertEqual(p.factor(a['profile'])['output_allowance'],262144)
    def test_TP1_and_uneven_TP2_are_explicit(self):
        for arm,a in t.ARMS.items():
            c=p.profile(self.base(),self.directory(arm),a['profile'],arm);tp=1 if a['profile']=='PROD' else 2
            self.assertEqual(c['args'][c['args'].index('--tp')+1],str(tp))
            for key in ('DS4_TP_GGUF_UNEVEN','DS4_TP_CHECK','DS4_AR2'):
                if tp==2:self.assertEqual(c['env'][key],'1')
                else:self.assertNotIn(key,c['env'])
    def test_no_numerical_dump_roundlog_or_profiling_in_any_task(self):
        for arm,a in t.ARMS.items():
            c=p.profile(self.base(),self.directory(arm),a['profile'],arm)
            for key in ('DS4_SERVE_DUMP','DS4_ROUND_LOG','DS4_PROF'):self.assertNotIn(key,c['env'])
            if a['profile']=='PROD':self.assertNotIn('DS4_COPY_DIRECT',c['env']);self.assertEqual(c['exe'],self.base()['exe'])
            else:self.assertEqual(c['env']['DS4_COPY_DIRECT'],'1');self.assertEqual(c['exe'],str(p.NATIVE))
    def test_all_private_state_stays_in_arm_namespace(self):
        for arm,a in t.ARMS.items():
            d=self.directory(arm);c=p.profile(self.base(),d,a['profile'],arm)
            for key in ('STRATA_DS4_SLOT_DIR','DS4_LANE_CAL','DS4_LT_STORE'):self.assertTrue(c['env'][key].startswith(str(d)+'/'))
    def test_pack_and_TP_disambiguate_both_MayaS_profiles(self):
        for arm,a in t.ARMS.items():
            c=p.profile(self.base(),self.directory(arm),a['profile'],arm);self.assertEqual(p.pack_variant(c),a['profile'])
    def test_wrong_arm_profile_or_namespace_refused(self):
        with self.assertRaises(ValueError):p.profile(self.base(),self.directory('A1'),'MS2','A1')
        with self.assertRaises(ValueError):p.profile(self.base(),self.directory('B1'),'PROD','A1')
        with self.assertRaises(ValueError):p.factor('TP2')
    def test_base_or_profile_policy_mutation_refused(self):
        for key,value in [('hosted_default_effort',50),('fit_max_tokens',True),('tokenizer','/other')]:
            b=self.base();b[key]=value
            with self.assertRaises(ValueError):p.profile(b,self.directory('B1'),'MS2','B1')
        b=self.base();c=p.profile(b,self.directory('B1'),'MS2','B1');c['env']['DS4_SERVE_DUMP']='/extra'
        with self.assertRaises(ValueError):p.check_profile(b,c,self.directory('B1'),'MS2','B1')
    def test_real_saved_TP2_parser_format_has_no_newmodel_claim(self):
        log=(Path(__file__).parent/'recorded-startup-RTP2-failed/engine.log').read_text()
        for variant in ('HGU','UNSLOTH','MS2'):
            r=p.startup(log,variant);self.assertTrue(r['passed']);self.assertFalse(r['model_quality_or_speed_proof'])
    def test_real_saved_TP1_parser_and_lead_drafter_placement(self):
        log=(Path(__file__).parent/'recorded-startup-MSTP1/engine.log').read_text();r=p.startup(log,'MS1')
        self.assertTrue(r['passed']);self.assertFalse(r['model_quality_or_speed_proof']);self.assertTrue(all(x['tp']==1 for x in r['placement']))
    def test_missing_Q8_or_wrong_projection_refused(self):
        log=(Path(__file__).parent/'recorded-startup-RTP2-failed/engine.log').read_text()
        for old,new in [('50976 int8','42784 int8'),('target blocks 40','target blocks 43'),('DS4_AR2=1:','DS4_AR2=2:')]:
            with self.assertRaises(ValueError):p.startup(log.replace(old,new),'HGU')
    def test_exact_full_profile_includes_every_requested_factor(self):
        arm='B1';v=p.factor('MS2');self.assertEqual(v['tp'],2);self.assertEqual(v['context_total'],1048576);self.assertEqual(v['prefill_chunk'],4096);self.assertEqual(v['effort'],100)
        b=self.base();c=p.profile(b,self.directory(arm),'MS2',arm);self.assertTrue(p.check_profile(b,c,self.directory(arm),'MS2',arm))
if __name__=='__main__':unittest.main()
