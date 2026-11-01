"""One-shot small metadata assembly. No runtime/test/model mutation or payload read."""
import datetime,hashlib,importlib.util,json,pathlib,shlex,subprocess
E=pathlib.Path('/Users/alex/strata-deepseek-qualification-20261024/reliability-optimization-20261025')
DC=E/'decode-optimization-20261028';P=DC/'maya145-modelchoice-v1';OLD=DC/'maya145-directstate-v1'
UBUNTU='/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def remote(p):return UBUNTU+'/'+str(p.relative_to(E))
def read(p):return json.loads(p.read_text())
def add(files,p):
 n=remote(p);h=sha(p);assert n not in files or files[n]==h;files[n]=h

def main():
 q=read(OLD/'directstate-qualification.json');rq=read(P/'recovery-v1/RECOVERY_QUALIFICATION.json')
 q.update(mode='modelstate',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
  admission_scope='Separate new-pack44cold/warm finite literal screens only. FHGU considered first; no timing/quality/promotion/automatic next arm.',
  pack_custody={'dossier':remote(DC/'model-choice-v1/PACK_CUSTODY_FROZEN.json'),'scope':'Closed constructor and frozen stat continuity; no fresh tensor rehash/exact private S2'},
  actual_adapter_CPU_each_host={'controller':108,'profile':10,'auditor':15,'recovery':63,'inherited_helper':15,'fixture':11},
  selected_binding_snapshot={'invocation':'95ff5e796eab4d86b0e78d1611b9ada4','main_pid':828763,'native_pid':828819,'native_start_ticks':176859041},
  prospective_recovery_wrapper=remote(P/'recovery-v1/recovery.py'),prospective_recovery_qualification_sha256=sha(P/'recovery-v1/RECOVERY_QUALIFICATION.json'),
  previous_qualification_sha256=sha(OLD/'directstate-qualification.json'),GPU_arm_registry=remote(P/'modelstate-arms.json'),CPU_groups=[])
 q['preserved_failures']+=['New profile FIRST Mac9of10 test expected nonexistent config.max_tokens; preserved original plus separately reviewed R3 test-only proof, runtime unchanged.','Ubuntu map refused missing reviewer receipt before child or directory; receipt staged before FIRST108.']
 for k in ('rejected_first_metadata_sha256','qualification_metadata_correction','root_alias_metadata_delta_reviewed'):q.pop(k,None)
 spec=importlib.util.spec_from_file_location('maps_only',P/'run_current_cpu.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 sets=[m.input_paths(DC/'maya145-mayas-v1/source-r2'),
  {**{n:DC/'maya145-mayas-v1/source-r2'/n for n in ('src/ds4/ds4_model.cu','src/ds4/ds4_gguf.cu')},'prior-startup-parser':OLD/'engine_profile.py',**{'saved-startup/'+n:P/'recorded-startup-RTP2-failed'/n for n in ('engine.log','native-ready.json','startup-health.json','startup-models.json')}},
  {'direct_io.py':P/'direct_io.py'}]
 for review,folder,inputs in zip(['ROOT_CURRENT_SOURCE_REVIEW.json','ROOT_PROFILE_R3_SOURCE_REVIEW.json','ROOT_CURRENT_AUDIT_R2_SOURCE_REVIEW.json'],['CPU-MODEL-FIRST-','CPU-PROFILE-R3-FIRST-','CPU-CURRENT-AUDIT-R2-FIRST-'],sets):
  r=read(P/review);g={k:r[k] for k in ('source_sha256','input_sha256','test_ids')};g.update(input_paths={n:remote(p) for n,p in inputs.items()},proofs={})
  assert {n:sha(p) for n,p in inputs.items()}==g['input_sha256']
  for n in g['source_sha256']:add(q['files'],P/n)
  for p in inputs.values():add(q['files'],p)
  add(q['files'],P/review)
  for host in ('darwin','linux'):
   g['proofs'][host]={k:remote(P/(folder+host)/n) for k,n in [('receipt','receipt.json'),('child','child.json'),('log','child.log')]}
   for path in g['proofs'][host].values():add(q['files'],E/path[len(UBUNTU)+1:])
  q['CPU_groups'].append(g)
 for n,h in rq['files'].items():
  assert n not in q['files'] or q['files'][n]==h;q['files'][n]=h
 add(q['files'],P/'recovery-v1/RECOVERY_QUALIFICATION.json')
 fixture=DC/'model-choice-v1/fixtures-v1';fr=read(fixture/'ROOT_SOURCE_REVIEW_R2.json');q['candidate_fixture_CPU']={k:fr[k] for k in ('source_sha256','input_sha256','test_ids')}
 for n in fr['source_sha256']:add(q['files'],fixture/n)
 for n in ['SOL_MODELCHOICE_FINAL_SOURCE_REVIEW.json','SOL_MODELCHOICE_CPU_REVIEW.json','PROFILE_FIRST_SOURCE_PRESERVED/DIAGNOSIS.json']:add(q['files'],P/n)
 script='import sys,json,pathlib;rows=json.load(sys.stdin);print(json.dumps({n:str(pathlib.Path(n).resolve(strict=True)) for n in rows}))'
 r=subprocess.run(['ssh','alex@ubuntuserver.local','python3','-c',shlex.quote(script)],input=json.dumps(list(q['files'])),capture_output=True,text=True);assert r.returncode==0,r.stderr[-3000:]
 aliases=json.loads(r.stdout);files={}
 for n,h in q['files'].items():
  target=aliases[n];assert target not in files or files[target]==h;files[target]=h
 q['files']=files;q['physical_alias_map']={n:t for n,t in aliases.items() if n!=t};q['qualification_alias_scope']='Existing strict physical paths, same byte hashes; metadata only'
 f=P/'modelstate-qualification.json';f.open('x').write(json.dumps(q,indent=2)+'\n')
 print(json.dumps({'qualification_sha256':sha(f),'file_pins':len(files),'aliases':len(q['physical_alias_map']),'recovery_sha256':sha(P/'recovery-v1/RECOVERY_QUALIFICATION.json')}))
if __name__=='__main__':main()
