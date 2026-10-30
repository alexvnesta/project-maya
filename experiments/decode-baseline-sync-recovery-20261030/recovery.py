"""Post-fault baseline diagnosis only. No service start or experiment retry.

Build and entry are separate single-use actions. The caller must obtain reviewed
admission for a genuine canonical diagnostic window; this file cannot create one.
"""
import argparse,fcntl,hashlib,json,os,pathlib,resource,shlex,signal,subprocess,sys,time
HERE=pathlib.Path(__file__).resolve().parent
R=pathlib.Path('/home/alex/strata-deepseek-test-20261024');E=R/'reliability-optimization-20261025'
D=pathlib.Path('/home/alex/deepseek-hosted-20261025')
H=E/'decode-optimization-20261028/head-batching-v1'
B=R/'maya-build-sm80-ablate469-v2'
FAILED=R/'windows/20261030T095101Z.json'
CLEAN=R/'windows/20261030T024056Z.json'
QSHA='e8fa4acbcbaa9482f8a5b6695e562596400c91004329b2503220e13d3bc97e9e'
SOURCES=('recovery.py','health.cu','health_contract.hpp','test_contract.cpp','test_recovery.py','qualify_cpu.py')
def require(ok,why):
 if not ok:raise ValueError(why)
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for s in iter(lambda:f.read(65536),b''):h.update(s)
 return h.hexdigest()
def new(p,data):
 with pathlib.Path(p).open('x') as f:f.write(json.dumps(data,indent=2,allow_nan=False)+'\n')
def read(p):return json.loads(pathlib.Path(p).read_text())
def command(argv):return subprocess.run(argv,check=True,capture_output=True,text=True,timeout=30).stdout
def properties(text):
 pairs=[x.split('=',1) for x in text.splitlines()]
 require(all(len(x)==2 for x in pairs) and len({x[0] for x in pairs})==len(pairs),'unit properties')
 return dict(pairs)
def stopped_contract(s,unit,gpus,used,active):
 require(s.get('production_temporarily_stopped') is True and s.get('current_native_pid') is None,'canonical not stopped')
 require(s.get('decode_optimization_current',{}).get('status')=='STOPPED_FOR_OFFLINE_DIAGNOSIS','wrong diagnosis lineage')
 require(not any(s.get(k) for k in ('active_private_phase','active_GPU_phase','active_gpu_experiment','private_window','active_cpu_build','production_restore_in_progress','production_verification_pending')),'other phase')
 require(unit=={'ActiveState':'failed','InvocationID':'27f9b1951f494c47a5f6de81f7323ba6','MainPID':'0','Result':'exit-code'},'stopped unit changed')
 require(gpus==[] and len(used)==2 and all(type(x) is int and 0<=x<=10 for x in used),'GPU not empty')
 require(active==[],'competing units')
 return True
def guard(lock_held=False):
 require(sys.platform=='linux' and HERE==H/'postfault-baseline-recovery-v1/health-sync-v2','physical exact stage')
 s=read(E/'STATE.json')
 u=properties(command(['systemctl','--user','show','deepseek-hosted.service','-p','ActiveState,InvocationID,MainPID,Result']))
 active=[]
 for scope,name in [('user','glm53-b2.service'),('user','glm53-b2-watchdog.timer'),('system','glm-qwen-switcher.service'),('system','qwen-flash-vllm.service'),('user','strata-deepseek-window.service')]:
  args=['systemctl']+(['--user'] if scope=='user' else [])+['is-active','--quiet',name]
  r=subprocess.run(args,capture_output=True,timeout=15)
  require(r.returncode in (0,3,4),'unit status unavailable')
  if r.returncode==0:active.append(name)
 owners=command(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader']).split()
 used=[int(x) for x in command(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits']).split()]
 stopped_contract(s,u,owners,used,active)
 require(max((R/'windows').glob('*.json'),key=lambda p:p.stat().st_mtime)==FAILED,'latest failure changed')
 require(read(E/'STATE.json').get('postfault_baseline_recovery',{}).get('window')==str(FAILED),'latest failed custody changed')
 require(read(FAILED).get('test_returncode')==1 and read(FAILED).get('maintenance_resume_allowed') is False,'failed receipt changed')
 require(os.statvfs(R).f_bavail*os.statvfs(R).f_frsize>=132*2**30,'root132')
 if not lock_held:
  with (R/'experiment.lock').open('a') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 kernel=command(['sudo','-n','journalctl','-k','--since','2026-10-30 04:08:58 UTC','--no-pager'])
 require(not any(t in kernel for t in ('Xid','AER:','PCIe Bus Error')),'kernel fault')
 return {'canonical':s,'unit':u,'owners':owners,'used':used,'kernel':kernel}
def source_map():return {n:sha(HERE/n) for n in SOURCES}
def reviewed():
 r=read(HERE/'source-review.json')
 require(r.get('all_source_and_tests_read') is True and r['source_sha256']==source_map(),'manual source review missing')
 return r
def old_pins():
 p=H/'gpu-qualification.json';require(sha(p)==QSHA,'old qualified map changed')
 q=read(p)
 for name,pin in q['files'].items():require(sha(name)==pin,'old selected input changed: '+name)
 return q
def cpu_proofs():
 review=reviewed()
 for host in ('darwin','linux'):
  p=HERE/('CPU-FIRST-'+host);c=read(p/'child.json');r=read(p/'receipt.json')
  require(c.get('returncode')==0 and c.get('error') is None and c.get('cleanup_errors')==[],'CPU child fault')
  require(c.get('CPU_s')==30 and c.get('wall_s')==90 and c.get('nice')==15 and c.get('CUDA_hidden') is True and c.get('Linux_AS_MiB')==(512 if host=='linux' else None),'CPU bounds')
  require(r.get('passed') is True and r['source_sha256']==review['source_sha256'] and r['test_ids']==review['test_ids'] and r.get('input_sha256')==review['input_sha256'],'CPU map/IDs')
  require(type(r.get('controls')) is int and r['controls']==len(review['test_ids']) and r.get('CXX_controls')==19 and r.get('CXX_compile_returncode')==0 and r.get('CXX_run_returncode')==0 and all(r.get(k) is False for k in ('GPU_execution','CUDA_compilation','model_execution')),'CPU execution proof')
 return review
def build_plan():
 p=read(HERE.parents[1]/'prepare-FIRST/plan.json')['compile_plan_UNRUN'];compile=list(p[1][1]);link=list(p[-1][1]);out=HERE/'build-FIRST'
 compile=[x for x in compile if x!='-I'+str(H/'candidate/src/ds4')]
 compile[compile.index('-c')+1]=str(HERE/'health.cu');compile[compile.index('-o')+1]=str(out/'health.o')
 compile.insert(compile.index('--options-file'),'-I'+str(HERE))
 link=[str(out/'health.o') if x==str(H/'build-FIRST/head_batch_check.cu.o') else x for x in link]
 link=[('-Wl,--dependency-file='+str(out/'health.link.d')) if x.startswith('-Wl,--dependency-file=') else x for x in link]
 link[link.index('-o')+1]=str(out/'baseline-health')
 require(not any('candidate' in x or 'ds4_model' in x or 'head_batch_check' in x for x in compile+link),'candidate in health build')
 require('--use_fast_math' not in compile and compile[compile.index('--threads')+1]=='1','compiler semantics')
 deps=list(compile);deps.remove('--ptxas-options=-v');deps[deps.index('-c')]='-M';deps[deps.index('-o')+1]=str(out/'health.headers.d')
 return [('deps',deps),('compile',compile),('link',link)]
def limits(cpu,as_mb):
 resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu))
 if sys.platform=='linux' and as_mb is not None:resource.setrlimit(resource.RLIMIT_AS,(as_mb*2**20,as_mb*2**20))
 os.nice(15)
def group_gone(pid,timeout=5):
 end=time.monotonic()+timeout
 while True:
  try:os.killpg(pid,0)
  except ProcessLookupError:return True
  if time.monotonic()>=end:return False
  time.sleep(.05)
def child(argv,out,label,cpu,as_mb,wall,hidden=True,identity=None):
 env={k:v for k,v in os.environ.items() if not k.startswith(('DS4_','STRATA_DS4_','MAYA_DS4_'))}
 env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MALLOC_ARENA_MAX='1',PYTHONDONTWRITEBYTECODE='1')
 if hidden:env['CUDA_VISIBLE_DEVICES']=''
 else:env.update(STRATA_DS4_Q8_BATCH='1',DS4_Q8_BATCH='1',STRATA_DS4_Q8_CHECK='1',DS4_Q8_CHECK='1')
 process=None;error=None;cleanup=[];started=time.monotonic();code=None
 with (out/(label+'.stdout')).open('xb') as stdout,(out/(label+'.stderr')).open('xb') as stderr:
  try:
   # GPU fixture inherits canonical group. Compiler/CPU receives its own group.
   process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,cwd=B if label in ('deps','compile','link') else HERE,env=env,start_new_session=hidden,preexec_fn=lambda:limits(cpu,as_mb))
   if identity:new(out/(label+'-start.json'),identity(process.pid,argv))
   code=process.wait(timeout=wall)
  except BaseException as exc:error=repr(exc)
  finally:
   if process:
    for sig in (signal.SIGTERM,signal.SIGKILL):
     try:
      if hidden:os.killpg(process.pid,sig)
      elif process.poll() is None:process.send_signal(sig)
     except ProcessLookupError:pass
     except BaseException as exc:cleanup.append(repr(exc))
    try:process.wait(timeout=10)
    except BaseException as exc:cleanup.append(repr(exc))
    code=process.returncode
    if hidden:
     try:
      if not group_gone(process.pid):cleanup.append('Owned child group survived cleanup')
     except BaseException as exc:cleanup.append(repr(exc))
 result={'argv':argv,'pid':process.pid if process else None,'returncode':code,'error':error,'cleanup_errors':cleanup,'CPU_s':cpu,'AS_MiB':as_mb,'wall_s':wall,'nice':15,'CUDA_hidden':hidden,'elapsed_s':time.monotonic()-started,'retry':False}
 new(out/(label+'-exit.json'),result)
 require(code==0 and error is None and cleanup==[],'FIRST child fault; HOLD')
 return result
def dependencies(text, relative_to=None):
    """Read compiler/ld make dependency rules, including empty phony rules."""
    result=set(); saw_rule=False
    for line in text.replace(chr(92)+chr(10),' ').splitlines():
        if not line.strip(): continue
        if ':' not in line: raise ValueError('Dependency target absent')
        target, rhs=line.split(':',1)
        if not target.strip(): raise ValueError('Dependency target empty')
        saw_rule=True
        for name in shlex.split(rhs):
            path=pathlib.Path(name)
            if not path.is_absolute():
                if relative_to is None: raise ValueError('Dependency paths must be absolute')
                path=relative_to/path
            result.add(str(path.absolute()))
    if not saw_rule or not result: raise ValueError('Empty dependency list')
    return sorted(result)

def dependency_pins(dep,q,owned):
 names=dependencies(dep.read_text(),relative_to=B);pins={}
 for n in names:
  require(bool(n) and not n.endswith(':'),'malformed dependency')
  path=pathlib.Path(n);path=path if path.is_absolute() else B/path
  require(path.is_file(),'missing actual input: '+str(path))
  if str(path) in owned:require(not path.is_symlink(),'owned input symlink')
  pin=sha(path);pins[str(path)]=pin
  require(owned.get(str(path),q['files'].get(str(path)))==pin,'new/unpinned actual input: '+str(path))
 require(bool(pins),'actual dependency set empty');return pins
def pin_check(pins):
 for p,pin in pins.items():require(sha(p)==pin,'input changed: '+p)
def build_locked():
 guard(True);review=cpu_proofs();q=old_pins();out=HERE/'build-FIRST';sources={str(HERE/n):v for n,v in review['source_sha256'].items()};produced={}
 require(not out.exists() and not out.is_symlink(),'build namespace used')
 out.mkdir();new(out/'plan.json',build_plan());results=[]
 for label,argv in build_plan():
  guard(True);old_pins();pin_check(sources);pin_check(produced)
  results.append(child(argv,out,label,120,4096,300));guard(True)
  old_pins();pin_check(sources);pin_check(produced)
  artifact=pathlib.Path(argv[argv.index('-o')+1]);require(artifact.is_file() and not artifact.is_symlink(),'fresh output absent')
  produced[str(artifact)]=sha(artifact)
  # Preserve actual inputs for independent review. Never silently extend pins.
  dep=out/('health.headers.d' if label=='deps' else 'health.link.d')
  if label in ('deps','link'):
   pins=dependency_pins(dep,q,{**sources,**produced});new(out/(label+'-inputs.json'),pins)
  if label=='compile':pin_check(read(out/'deps-inputs.json'))
 new(out/'receipt.json',{'passed':True,'children':results,'binary_sha256':sha(out/'baseline-health'),'GPU_execution':False,'model_execution':False})
def build():
 guard()
 with (R/'experiment.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);build_locked()
def expected_lines(device):return [f'PASS baseline-k5120-n129280-r{r}-pad{p}-pattern{t}' for r in (1,2,4) for p in (0,1) for t in (0,1)]+[f'ALL 12 BASELINE_HEALTH checks passed device {device}']
def result_contract(stdout,code,device):
 require(type(device) is int and device in (0,1) and type(code) is int and code==0,'device or exit')
 require(stdout.splitlines()==expected_lines(device),'missing/extra/partial health cases')
 return {'device':device,'cases':12,'exit':0}
def entry_contract(w,actual,admission_pin):
 expected=[str(R/'venv/bin/python3.14'),'-B',str(HERE/'recovery.py'),'entry','--admission-pin',admission_pin]
 require(w.get('continued_from')==str(CLEAN) and w.get('mutation_started') is True and w.get('test_returncode') is None,'window not admitted')
 require(w.get('admission_mode')=='continued-explicit-deepseek-maintenance' and w.get('command')==expected and actual==expected,'wrong actual entry command')
def entry(admission_pin):
 require(sys.platform=='linux' and HERE==H/'postfault-baseline-recovery-v1/health-sync-v2','physical stage')
 require(sha(HERE/'GPU_ADMISSION.json')==admission_pin,'admission changed')
 a=read(HERE/'GPU_ADMISSION.json');require(a['source_sha256']==source_map() and a.get('baseline_only') is True and a.get('single_window') is True,'wrong admission')
 window=pathlib.Path(os.environ.get('STRATA_WINDOW_STATE',''))
 require(window.parent==R/'windows' and window.is_file() and window!=FAILED and window!=CLEAN,'canonical new window required')
 w=read(window);actual=pathlib.Path('/proc/self/cmdline').read_bytes().rstrip(b'\0').decode().split('\0');entry_contract(w,actual,admission_pin)
 cgroup=pathlib.Path('/proc/self/cgroup').read_text();require('/strata-deepseek-window.service' in cgroup,'not canonical cgroup')
 require(sha(FAILED)==a['failed_window_sha256'] and sha(CLEAN)==a['clean_window_sha256'],'lineage changed')
 binary=HERE/'build-FIRST/baseline-health';require(sha(binary)==a['binary_sha256'],'health binary changed')
 # Original qualified PID/exe/argv/startticks/cgroup observer, no old fixture call.
 require(sha(H/'gpu_check.py')==a['identity_observer_sha256'],'PID observer changed')
 sys.path.insert(0,str(H));import gpu_check as g
 require(pathlib.Path(g.__file__).resolve()==H/'gpu_check.py','foreign PID observer import')
 out=HERE/'GPU-FIRST';require(not out.exists() and not out.is_symlink(),'health attempt already exists');out.mkdir()
 results=[]
 for d in (0,1):
  argv=[str(binary),'--baseline-health',str(d)]
  result=child(argv,out,'gpu'+str(d),120,None,120,False,lambda pid,args:g.child_identity(pid,binary,args))
  results.append(result_contract((out/('gpu'+str(d)+'.stdout')).read_text(),result['returncode'],d))
 new(out/'receipt.json',{'passed':True,'devices':results,'window':str(window),'binary_sha256':sha(binary),'baseline_only':True,'model_execution':False,'private_API':'N/A no private API','speed_claim':False})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','entry']);p.add_argument('--admission-pin');args=p.parse_args()
 if args.mode=='build':build()
 else:entry(args.admission_pin)
