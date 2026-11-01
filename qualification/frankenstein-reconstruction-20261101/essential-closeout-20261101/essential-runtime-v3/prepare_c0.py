"""Metadata-only separate C0 admission proposal after qualified RAM-guard repair.
No model, arm registry, service, request or window action occurs here.
"""
import copy,importlib.util,json,os,resource,sys
from pathlib import Path
H=Path(__file__).resolve().parent;Q=H.parent;DC=Q.parent;E=DC.parent

def main():
 sys.dont_write_bytecode=True;sys.path.insert(0,str(DC/'maya-s-comparison-v1'));import acquire
 gate=acquire.SelectedGate();gate()
 resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(512*2**20,)*2);os.nice(15)
 spec=importlib.util.spec_from_file_location('essential3_metadata_runtime',H/'runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
 read=lambda p:json.loads(Path(p).read_text())
 before=Q/'essential-runtime-v2/qualification.json';assert rt.sha(before)=='74bf96a7ed72559d767519de0fc4371c047416281c9562167b27d01577f6b93f'
 q=read(before);q['publication_selected_binding']=copy.deepcopy(q['selected_binding']);q['selected_binding']=gate.host.start_binding
 def add(p,pin=None):
  p=Path(p);assert rt.fingerprint(p)[2]<=512*2**20,str(p);v=rt.sha(p)
  if pin is not None:assert v==pin,str(p)
  if str(p) in q['files']:assert q['files'][str(p)]==v,('Immutable prior pin changed',str(p))
  q['files'][str(p)]=v;return str(p)
 def folder(p):
  for f in sorted(Path(p).rglob('*')):
   if f.is_file() and '__pycache__' not in f.parts and f.name not in ('qualification.json','arms.json') and not f.name.endswith('-admission.json'):add(f)
 add(before);folder(H);folder(Q/'essential-fixtures-v4');folder(Q/'essential-audit-v3');folder(Q/'native-engine-v3')
 build=Q/'native-build-v3';bq=read(build/'compile-r4-qualification.json')
 for n,v in bq['files'].items():add(n,v)
 for n in ('compile-r4-qualification.json','FIRST_BUILD_COMPLETION.json'):add(build/n)
 folder(build/'configure-r4-FIRST');folder(build/'compile-r4-FIRST')
 for capture in ('capture-native3-configure-FIRST','capture-native3-compile-FIRST','capture-essential-B0-FIRST','capture-essential-recovery-health-FIRST','capture-essential-recovery-restore-FIRST'):
  folder(Q/'launch-custody-v1'/capture)
 buildproof=read(build/'FIRST_BUILD_COMPLETION.json');exe=build/'native-build-FIRST/maya-ds4';native_sha=rt.sha(exe)
 assert native_sha==buildproof['artifact_sha256'] and buildproof['compile_returncode']==buildproof['configure_returncode']==0
 add(exe,native_sha)
 # Original B0 is closed/HOLD, with actual outer1 and source-diagnosed native startup refusal.
 old=read(Q/'essential-runtime-v2/arms.json');assert set(old)=={'B0'} and old['B0']['attempted']
 outer=read(Q/'launch-custody-v1/capture-essential-B0-FIRST/controller-exit.json');assert outer['returncode']==1 and outer['actual_wait_observed'] and outer['cleanup']==[]
 add(Q/'essential-runtime-v2/arms.json');add(Q/'B0_RAM_GUARD_OFFLINE_FINDING_FIRST.json')
 failed=Path(old['B0']['output']);folder(failed.parent.parent/'maintenance'/failed.name)
 for n in ('candidate-config.json','private-memory-fence-restored.json','API-start.json'):
  p=failed/n
  if p.exists():add(p)
 for n in ('engine.log','server.log','server-cleanup.json','entry-audit.json'):add(failed/'native'/n)
 state=read(E/'STATE.json');recovery=state['s2essential_recovery_current'];assert recovery['status']=='SELECTED_BASELINE_RESTORED_FAILED_ARM_REMAINS_HOLD' and recovery['active'] is False
 assert recovery['result']['start_binding']==gate.host.start_binding and recovery['result']['verified']['passed']
 rroot=Q/'essential-recovery-v1';folder(rroot)
 metadata=E/'maintenance'/('s2essential-baseline-recovery-'+recovery['run_id']);folder(metadata)
 health=E/'results'/('s2essential-baseline-health-'+recovery['run_id']);folder(health)
 win=Path(recovery['result']['verified'].get('window',str(E.parent/'windows/20261101T213655Z.json')))
 assert read(win)['test_returncode']==0;add(win);add(win.with_suffix('.telemetry.jsonl'))
 # Retain immutable historical publication proof, but use the fresh qualified actual owner above.
 q.update(mode=rt.MODE,CPU_review=str(H/'ROOT_SOURCE_REVIEW.json'),
  CPU={p:{'receipt':str(H/('CPU-FIRST-'+p+'.json')),'child':str(H/('CPU-FIRST-'+p)/'child.json'),'log':str(H/('CPU-FIRST-'+p)/'child.log')} for p in ('darwin','linux')},
  original_B0_failed_and_not_regraded=True,new_native_memory_accounting_repair=True)
 profiles={'C0':copy.deepcopy(q['profiles']['B0']),'A1':copy.deepcopy(q['profiles']['A0'])}
 profiles['C0'].update(exe=str(exe),native_sha256=native_sha,manifest=str(Q/'essential-fixtures-v4/CPU-FIRST-linux/manifest-C0.json'))
 profiles['A1']['manifest']=str(Q/'essential-fixtures-v4/CPU-FIRST-linux/manifest-A1.json');q['profiles']=profiles
 # No old mutable proof/registry is replaced. All new request IDs and source maps are qualified separately.
 modules=rt.helpers(q)
 for arm in ('C0','A1'):rt.fixture_contract(read(profiles[arm]['manifest']),modules[-2],arm)
 target=H/'qualification.json';assert not target.exists()
 with target.open('x') as f:json.dump(q,f,indent=2,allow_nan=False);f.write('\n')
 pin=rt.sha(target);rt.qualified(pin,'C0')
 with (H/'qualification-C0-FIRST.json').open('x') as f:json.dump(q,f,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({'passed':True,'qualification_sha256':pin,'files':len(q['files']),'native_sha256':native_sha,'binding':gate.host.start_binding,'publication_binding_historical':q['publication_selected_binding'],'model_executed':False}))

if __name__=='__main__':main()
