"""Two new pack profiles and saved native-format parser controls, CPU only."""
import copy
import json
from pathlib import Path
import unittest
import engine_profile as p

class Profile(unittest.TestCase):
    def base(self):return json.loads((Path(__file__).parent/'profile-base-config.json').read_text())
    def directory(self,v='HGU'):return p.E/('results/maya145-modelchoice-'+v+'-20261101T030000Z/native')
    def log(self):return (Path(__file__).parent/'recorded-startup-RTP2-failed/engine.log').read_text()
    def test_both_new_profiles_preserve_full_policy_and_original_base(self):
        base=self.base();before=copy.deepcopy(base)
        for variant in ('HGU','UNSLOTH'):
            c=p.profile(base,self.directory(variant),variant)
            self.assertEqual(base,before);self.assertEqual(c['args'][c['args'].index('--pack')+1],str(p.PACKS[variant]))
            for option in ('--max-context','--dspark','--cpu-threads','--mmap-experts','--prefill-chunk'):
                self.assertEqual(c['args'][c['args'].index(option)+1],base['args'][base['args'].index(option)+1])
            self.assertEqual(p.factor(variant)['output_allowance'],262144);self.assertIs(c['fit_max_tokens'],False);self.assertEqual(c['hosted_default_effort'],100)
            self.assertEqual(c['args'][c['args'].index('--tp')+1],'2');self.assertEqual(p.pack_variant(c),variant)
            self.assertEqual(c['tokenizer'],str(p.PACKS[variant]/'tokenizer'))
    def test_both_tp2_Q8_direct_and_diagnostic_flags(self):
        for v in ('HGU','UNSLOTH'):
            c=p.profile(self.base(),self.directory(v),v)
            for key in ('DS4_TP_GGUF_UNEVEN','DS4_TP_CHECK','DS4_AR2','DS4_COPY_DIRECT','DS4_Q8_CHECK','DS4_YOCO'):
                self.assertEqual(c['env'][key],'1')
            self.assertEqual(c['env']['DS4_SERVE_DUMP'],str(self.directory(v)/'logits'))
            self.assertEqual(c['env']['DS4_ROUND_LOG'],str(self.directory(v)/'rounds.tsv'))
    def test_all_private_state_paths_stay_in_the_new_candidate_namespace(self):
        for v in ('HGU','UNSLOTH'):
            c=p.profile(self.base(),self.directory(v),v)
            for key in ('STRATA_DS4_SLOT_DIR','DS4_LANE_CAL','DS4_LT_STORE'):self.assertTrue(c['env'][key].startswith(str(self.directory(v))+'/'))
    def test_source_capacity_and_unproven_fit_scope(self):
        self.assertEqual(p.factor('HGU')['asset_count'],9);self.assertEqual(p.factor('UNSLOTH')['asset_count'],8)
        for v in ('HGU','UNSLOTH'):
            f=p.factor(v);self.assertEqual(f['context_total'],1048576);self.assertEqual(f['output_allowance'],262144)
            self.assertFalse(f['runtime_fit_claim']);self.assertFalse(f['numerical_equivalence_claim']);self.assertFalse(f['exact_private_S2'])
    def test_wrong_variant_namespace_or_old_pack_refused(self):
        for v in ('TP2','TP1','MAYAS','',None):
            with self.assertRaises(ValueError):p.factor(v)
        with self.assertRaises(ValueError):p.profile(self.base(),self.directory('UNSLOTH'),'HGU')
        with self.assertRaises(ValueError):p.pack_variant({'args':['--pack','/other']})
    def test_changed_base_quality_or_capacity_refused(self):
        for key,value in [('max_tokens',32768),('hosted_default_effort',50),('tokenizer','/foreign')]:
            b=self.base();b[key]=value
            with self.assertRaises(ValueError):p.profile(b,self.directory(),'HGU')
    def test_profile_delta_is_exact_and_cannot_drop_drafter_or_flags(self):
        b=self.base();c=p.profile(b,self.directory(),'HGU');self.assertTrue(p.check_profile(b,c,self.directory(),'HGU'))
        for key,value in [('exe','/old'),('max_tokens',32768),('hosted_default_effort',50)]:
            bad=copy.deepcopy(c);bad[key]=value
            with self.assertRaises(ValueError):p.check_profile(b,bad,self.directory(),'HGU')
        bad=copy.deepcopy(c);del bad['env']['DS4_COPY_DIRECT']
        with self.assertRaises(ValueError):p.check_profile(b,bad,self.directory(),'HGU')
    def test_saved_real_source_format_is_parsed_without_new_model_claim(self):
        for v in ('HGU','UNSLOTH'):
            result=p.startup(self.log(),v);self.assertTrue(result['passed']);self.assertFalse(result['model_quality_or_speed_proof'])
            self.assertEqual([x['tp'] for x in result['placement']],[2,2])
    def test_wrong_Q8_projection_or_reduction_evidence_refused(self):
        for old,new in [('50976 int8','42784 int8'),('target blocks 40','target blocks 43'),('dim 5120','dim 4096'),('DS4_AR2=1:','DS4_AR2=2:'),('ds4: TP check passed (','ds4: TP check missing (')]:
            with self.assertRaises(ValueError):p.startup(self.log().replace(old,new),'HGU')
    def test_missing_actual_GPU_check_or_foreign_owner_row_refused(self):
        log=self.log();line=next(x for x in log.splitlines() if 'CUDA0 Q8 batch check:' in x)
        for bad in [log.replace(line+'\n',''),log+line+'\n',log+line.replace('CUDA0','CUDA2')+'\n']:
            with self.assertRaises(ValueError):p.startup(bad,'UNSLOTH')
