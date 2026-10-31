"""Portable profile guards; never start a service, read weights, or send inference."""
import copy,hashlib,importlib.util,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]/'integrations/strata-hosted'
class HostedCapacity(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.deploy=Path(self.tmp.name)/'deploy';self.qual=Path(self.tmp.name)/'qualification';self.env=patch.dict(os.environ,{'MAYA_DEPLOY_ROOT':str(self.deploy),'MAYA_QUALIFICATION_ROOT':str(self.qual),'MAYA_DIRECTION_SHA256':'fixture-direction'});self.env.start();self.addCleanup(self.env.stop)
 def module(self,name):
  spec=importlib.util.spec_from_file_location('hosted_capacity_'+name,ROOT/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def config(self):
  replacements={'${DEPLOY_ROOT}':str(self.deploy),'${QUALIFICATION_ROOT}':str(self.qual),'${DIRECTION_SHA256}':'fixture-direction','${MODEL_PACK}':str(self.qual/'pack')}
  def expand(x):
   if isinstance(x,str):
    for old,new in replacements.items():x=x.replace(old,new)
    return x
   if isinstance(x,list):return [expand(v) for v in x]
   if isinstance(x,dict):return {k:expand(v) for k,v in x.items()}
   return x
  return expand(json.loads((ROOT/'config.example.json').read_text()))
 def test_expanded_1m_profile_and_output_default_are_admitted(self):
  m=self.module('hosting_preflight');c=self.config();m.validate_config(c);self.assertEqual(c['args'][c['args'].index('--max-context')+1],'1048576');self.assertEqual(json.loads((ROOT/'config.shared-settings.example.json').read_text())['max_tokens'],262144)
 def test_chunk_mode_cache_identity_and_hidden_factors_are_refused(self):
  m=self.module('hosting_preflight');good=self.config();self.assertEqual(good['args'][good['args'].index('--prefill-chunk')+1],'4096');self.assertEqual([good['env'][k]for k in ['DS4_YOCO','STRATA_DS4_PROMPT_SKIP']],['1','1'])
  for kind in ['chunk','duplicate','DS4_YOCO','STRATA_DS4_PROMPT_SKIP','cache','DS4_CHUNK','DS4_CHUNK_MIN','DS4_COPY_PIN']:
   c=self.config()
   if kind=='chunk':c['args'][c['args'].index('--prefill-chunk')+1]='2048'
   elif kind=='duplicate':c['args'].extend(['--prefill-chunk','4096'])
   elif kind=='cache':c['env']['STRATA_DS4_SLOT_DIR']=c['env']['STRATA_DS4_SLOT_DIR'].replace('-yoco1-chunk4096','')
   else:c['env'][kind]='0' if kind in ['DS4_YOCO','STRATA_DS4_PROMPT_SKIP'] else '1'
   with self.assertRaises(RuntimeError):m.validate_config(c)
 def test_old_context_and_old_cache_namespace_are_refused(self):
  m=self.module('hosting_preflight')
  for flag in ['context','cache']:
   c=self.config()
   if flag=='context':c['args'][c['args'].index('--max-context')+1]='524288'
   else:c['env']['STRATA_DS4_SLOT_DIR']=c['env']['STRATA_DS4_SLOT_DIR'].replace('s1-1m','s1-512k')
   with self.assertRaises(RuntimeError):m.validate_config(c)
 def test_quality_policy_or_Q8_changes_are_refused(self):
  m=self.module('hosting_preflight')
  for name in ['batch','check','TP','vision','fit']:
   c=self.config()
   if name=='batch':c['env']['STRATA_DS4_Q8_BATCH']='0'
   elif name=='check':c['env']['DS4_Q8_CHECK']='0'
   elif name=='TP':c['args'][c['args'].index('--tp')+1]='2'
   elif name=='vision':c['args'][c['args'].index('--vision')+1]='off'
   else:c['fit_max_tokens']=True
   with self.assertRaises(RuntimeError):m.validate_config(c)
 def test_Q8_ready_requires_exact_both_device_footer(self):
  m=self.module('hosting_ready');log=''.join("ds4: CUDA"+str(d)+" Q8 batch check: 8 jobs (k 32 .. 5120, rows 1 .. 16, strided, one input shared): 42784 int8 and 1337 scales the per-job launches' bit for bit, every guard intact (DS4_Q8_CHECK)\n" for d in [0,1]);self.assertTrue(m.q8_receipt(log)['passed'])
  for bad in [log.replace('CUDA1','CUDA0'),log.replace('42784','42783'),log.splitlines()[0]]:
   with self.assertRaises(RuntimeError):m.q8_receipt(bad)
 def test_client_gate_accepts_1m_and_preserves_explicit_other_backend_selection(self):
  m=self.module('model_ready_gate');h={'status':'ok','loaded':True,'max_context':1048576,'images':True,'switcher':{'fault':None,'default_model':'deepseek','active_model':'deepseek'}};models={'default_model':'deepseek-v4.1-flash-iq2-xs'};self.assertTrue(m.qualified(h,models));old=copy.deepcopy(h);old['max_context']=524288;self.assertFalse(m.qualified(old,models));other=copy.deepcopy(h);other['switcher']['active_model']='glm';other['max_context']=655360;self.assertTrue(m.qualified(other,models))
 def test_all_portable_source_pins_match(self):
  p=json.loads((ROOT/'PROVENANCE.json').read_text());self.assertEqual(p['profile']['context'],1048576);self.assertEqual(p['profile']['max_output_default'],262144)
  for name,pin in p['files'].items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),pin,name)
  for name in ['hosting_preflight.py','hosting_ready.py','switcher.py','model_ready_gate.py','config.example.json']:
   s=(ROOT/name).read_text();self.assertNotIn('/Users/alex/',s);self.assertNotIn('/home/alex/',s)
if __name__=='__main__':unittest.main()
