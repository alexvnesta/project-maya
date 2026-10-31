"""Prospective, separately admitted baseline health and restoration, never an arm retry.

No action occurs on import. A future concrete diagnosis, exact CPU qualification,
and separate health/restore admissions are required. The old successful binary
and lifecycle implementations are reused without editing or rebuilding them.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
R=Path('/home/alex/strata-deepseek-test-20261024')
E=R/'reliability-optimization-20261025'
P=E/'decode-optimization-20261028'
Q=P/'maya145-finite-v1'
H=P/'head-batching-v1'
W=H/'postfault-baseline-recovery-v1/health-sync-v2'
F=E/'autonomous-optimization-12h-20261028/chunk4096-v1/activation-v1'
BINARY=W/'build-FIRST/baseline-health'
BINARY_SHA='250157320079ca4a263e152ecd09dd7b7c8f2a9504e583a0f64e6c53a7a67b4c'
OLD_MAP_SHA='9855deb4e3ece337a778a9995836a316fb4a3754d8c1d8ad616562ed7473d449'
HELPERS={str(W/'recovery.py'):'5c0037d71f6ba61ae36b1ac02d9404cba748fb77db1d04b4ab45b6d40bd59084',
 str(H/'gpu_check.py'):'7869ca8561c85f8770321a07a87c2b55bbbe7382b4cafe5f7a2613b715ad9d7e',
 str(H/'head_startup.py'):'53988e95be7c1883f7aeeb7ae2b87081da74d64b3f38eb43b6a274d93d1ff4f4',
 str(F/'activate_chunk4096.py'):'b2bb7676969661f98bf77d9969a840a4fcb44367f9644ab6f05ac19d70709056',
 str(P/'prose-speed-v1/prose_measure.py'):'8d10d003bbbd7ffbb87251bacdf53d91af9f074151d34f06c957fa179f3108cf'}
SOURCES=('recovery.py','test_recovery.py','run_cpu.py')
CPU_ENV={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}
PHASES=('active_private_phase','active_GPU_phase','active_gpu_experiment','private_window',
        'active_cpu_build','production_restore_in_progress','production_verification_pending')
MODES={'finite':('FTP2',)}

def require(ok,why):
    if not ok:raise ValueError(why)
def packed(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(65536),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def new(p,x):
    with Path(p).open('x') as f:f.write(json.dumps(x,indent=2,allow_nan=False)+'\n')
def real(p,root):
    p=Path(p);require(p.is_absolute() and '..' not in p.parts and p.is_relative_to(root),'Foreign or aliased path')
    for n in (p,*p.parents):require(not n.is_symlink(),'Path alias')
    return p
def digest(pin):require(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin),'Exact digest required')
def stamp(value):require(type(value) is str and re.fullmatch('[0-9]{8}T[0-9]{6}Z',value),'Exact unique UTC namespace')

def diagnosis_contract(d):
    stamp(d['run_id']);mode=d['mode'];arm=d['arm']
    require(mode in MODES and arm in MODES[mode],'Only a new Maya-S failed arm')
    controller=real(d['controller'],E/'maintenance')
    require(controller.name=='state.json' and re.fullmatch(r'maya145-finite-mayas-TP2-[0-9]{8}T[0-9]{6}Z',controller.parent.name),'Exact failed controller')
    require(controller.parent.parent==E/'maintenance','No nested controller')
    for key in ('failed_window','last_clean_window'):
        w=real(d[key],R/'windows');require(w.parent==R/'windows' and re.fullmatch('[0-9]{8}T[0-9]{6}Z.json',w.name),'Canonical window')
        digest(d[key+'_sha256'])
    require(d['failed_window']!=d['last_clean_window'],'Failure cannot be its own clean parent')
    require(real(d['old_close'],controller.parent)==controller.parent/'old-owner-close.json','Exact prospectively captured close receipt')
    for key in ('controller_sha256','old_close_sha256','last_clean_telemetry_sha256'):digest(d[key])
    u=d['stopped_unit'];require(set(u)=={'InvocationID','MainPID','ActiveState','Result'} and u['MainPID']=='0' and
        re.fullmatch('[0-9a-f]{32}',u['InvocationID']) and u['ActiveState'] in ('inactive','failed') and type(u['Result']) is str,'Frozen stopped unit')
    require(type(d['kernel_since']) is str and re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC',d['kernel_since']),'Explicit kernel interval')
    require(d.get('manual_diagnosis_complete') is True and d.get('failed_arm_remains_HOLD') is True,'No automatic recovery or regrade')
    return d

def paths(d):
    diagnosis_contract(d)
    return real(E/'maintenance'/('maya145finite-baseline-recovery-'+d['run_id']),E/'maintenance'),real(E/'results'/('maya145finite-baseline-health-'+d['run_id']),E/'results')

def state_contract(state,d,operation):
    require(state.get('maintenance_controller')==d['controller'],'Foreign controller custody')
    require(not any(state.get(k) for k in PHASES),'Other phase/pending verification')
    require(state.get('production_temporarily_stopped') is True and state.get('current_native_pid') is None,'Baseline must actually be stopped')
    previous=state.get('maya145finite_recovery_current') or {}
    require(not previous.get('active'),'Other recovery active')
    if operation=='health':
        require(previous.get('run_id')!=d['run_id'],'No repeat health attempt')
    else:
        require(operation=='restore' and previous.get('run_id')==d['run_id'] and previous.get('status')=='HEALTH_PENDING_INDEPENDENT_REVIEW','No reviewed health continuation')
    return True

def admission_contract(a,d,operation):
    require(operation in ('health','restore') and a.get('decision')==('SINGLE_BASELINE_HEALTH_ONLY' if operation=='health' else 'SINGLE_SELECTED_BASELINE_RESTORE_ONLY'),'Separate exact admission')
    require(a.get('baseline_only') is True and a.get('single_use') is True and a.get('manual_review') is True,'No candidate/automatic admission')
    require(a.get('run_id')==d['run_id'] and a.get('binary_sha256')==BINARY_SHA,'Exact existing healthy binary and namespace')
    for key in ('diagnosis_sha256','qualification_sha256'):digest(a[key])
    if operation=='restore':
        for key in ('health_receipt_sha256','health_window_sha256','health_telemetry_sha256','independent_health_review_sha256'):digest(a[key])
    return True

def command(argv):return subprocess.run(argv,check=True,capture_output=True,text=True,timeout=30).stdout
def stopped_guard(d,operation,latest):
    require(sys.platform=='linux' and HERE==Q/'recovery-v1','Physical exact wrapper namespace')
    diagnosis_contract(d);state=read(E/'STATE.json');state_contract(state,d,operation)
    text=command(['systemctl','--user','show','deepseek-hosted.service','-p','InvocationID,MainPID,ActiveState,Result'])
    rows=[x.split('=',1) for x in text.splitlines()]
    require(all(len(x)==2 for x in rows) and len({x[0] for x in rows})==len(rows) and dict(rows)==d['stopped_unit'],'Stopped unit changed; never adopt or stop a foreign owner')
    require(command(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader']).split()==[],'GPU owner present')
    used=[int(x) for x in command(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits']).split()]
    require(len(used)==2 and all(0<=x<=10 for x in used),'Both GPUs must be free')
    for user,name in [(True,'strata-deepseek-window.service'),(True,'glm53-b2.service'),(True,'glm53-b2-watchdog.timer'),(False,'qwen-flash-vllm.service'),(False,'glm-qwen-switcher.service')]:
        p=subprocess.run(['systemctl']+(['--user'] if user else [])+['is-active','--quiet',name],capture_output=True,timeout=15)
        require(p.returncode in (3,4),'Another active unit or unavailable status')
    require(max((R/'windows').glob('*.json'),key=lambda p:p.stat().st_mtime)==Path(latest),'Latest window changed')
    require(shutil.disk_usage('/').free>=132*2**30,'Root132 required')
    return state

def canonical_health_files(files):
    normalized={}
    for name,pin in files.items():
        require(Path(name).is_absolute(),'Absolute historical health input required')
        target=os.path.normpath(name)
        require(os.path.samefile(name,target),'Historical compiler path resolves differently')
        require(target not in normalized or normalized[target]==pin,'Conflicting historical file pins')
        normalized[target]=pin
    return normalized

def qualified(pin):
    path=HERE/'RECOVERY_QUALIFICATION.json';digest(pin);require(sha(path)==pin,'Qualification changed');q=read(path)
    require(q.get('root_manual_read') is True and q.get('sol_manual_read') is True,'Both manual source reads')
    oldmap=W/'GPU_INPUT_MAP.json';require(sha(oldmap)==OLD_MAP_SHA,'Successful unchanged health provenance changed')
    required={**canonical_health_files(read(oldmap)['files']),str(oldmap):OLD_MAP_SHA,**HELPERS,str(BINARY):BINARY_SHA}
    for n in SOURCES:required[str(HERE/n)]=sha(HERE/n)
    for name,pin in required.items():require(q['files'].get(name)==pin,'Required unchanged health/source closure omitted: '+name)
    for name,pin in q['files'].items():
        require(Path(name).is_absolute() and '..' not in Path(name).parts,'Canonical qualified input')
        require(sha(name)==pin,'Qualified input changed: '+name)
    sources={n:sha(HERE/n) for n in SOURCES};tree=ast.parse((HERE/'test_recovery.py').read_text())
    ids=sorted('test_recovery.'+c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'))
    require(q['source_sha256']==sources and q['test_ids']==ids and ids,'Exact current wrapper sources/tests')
    review=HERE/'RECOVERY_SOURCE_ROOT_REVIEW.json';require(str(review) in q['files'],'New source review omitted');review=read(review)
    require(review.get('root_entire_source_and_tests_read') is True and review.get('sol_entire_source_and_tests_read') is True and review.get('source_sha256')==sources and review.get('input_sha256')==q['input_sha256'] and review.get('test_ids')==ids,'Exact manual source review')
    for host in ('darwin','linux'):
        folder=HERE/('CPU-FIRST-'+host)
        for n in ('receipt.json','child.json','child.log'):require(str(folder/n) in q['files'],'New raw CPU proof omitted')
        r=read(folder/'receipt.json');c=read(folder/'child.json')
        require(r.get('passed') is True and type(r.get('controls')) is int and r['controls']==len(ids) and r.get('test_ids')==ids and r.get('source_sha256')==sources and r.get('input_sha256')==q['input_sha256'],'Both exact new CPU proofs')
        bounds={'returncode':0,'CPU_limit_seconds':30,'wall_limit_seconds':90,'nice_increment':15,'Linux_AS_bytes':512*2**20 if host=='linux' else None}
        require(all(type(c.get(k)) is type(v) and c[k]==v for k,v in bounds.items()) and c.get('error') is None and c.get('cleanup_errors')==[] and c.get('environment')==CPU_ENV and r.get('CPU_seconds')==[30,30] and r.get('Linux_AS_bytes')==([512*2**20]*2 if host=='linux' else None) and type(r.get('nice')) is int and r['nice']>=15 and r.get('environment')==CPU_ENV and r.get('CPU_only') is True and r.get('health_or_service_executed') is False,'Bounded physical CPU proofs')
    for name,pin in q['input_sha256'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts and q['files'].get(str(E/name))==pin,'CPU dependency omitted or aliased')
    return q

def module(name,path,pin):
    require(sha(path)==pin,'Helper changed before import')
    cached=sys.modules.get(name);require(cached is None or Path(cached.__file__).resolve()==path,'Foreign cached helper')
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    require(Path(m.__file__).resolve()==path,'Helper origin');return m
def support(q):
    sys.path[:0]=[str(H),str(P/'prose-speed-v1')]
    g=module('maya_s_recovery_observer',H/'gpu_check.py',HELPERS[str(H/'gpu_check.py')])
    r=module('maya_s_baseline_health_library',W/'recovery.py',HELPERS[str(W/'recovery.py')])
    m=module('maya_s_recovery_cas',P/'prose-speed-v1/prose_measure.py',HELPERS[str(P/'prose-speed-v1/prose_measure.py')])
    g.startup_proof(q);a=g.load_owner();return g,r,m,g.host_class(a)()

def lineage(d,q,g):
    for key in ('controller','failed_window','last_clean_window','old_close'):
        p=Path(d[key]);require(sha(p)==d[key+'_sha256'] and q['files'].get(str(p))==d[key+'_sha256'],'Diagnosis evidence changed/omitted')
    require(read(d['controller']).get('status')=='STOPPED_FOR_OFFLINE_DIAGNOSIS','Failed arm must remain stopped/HOLD')
    failed=read(d['failed_window']);require(type(failed.get('test_returncode')) is int and failed['test_returncode']!=0 and failed.get('maintenance_resume_allowed') is False,'Genuine failed window required')
    clean=Path(d['last_clean_window']);telemetry=clean.with_suffix('.telemetry.jsonl')
    require(sha(telemetry)==d['last_clean_telemetry_sha256'] and q['files'].get(str(telemetry))==d['last_clean_telemetry_sha256'],'Clean telemetry custody')
    row=read(d['old_close']);g.close_contract(row['binding'],row['native_close'],row['before'],row['after'])
    return row['binding']

def argv_for(operation,admission_path,pin):
    return [str(R/'venv/bin/python3.14'),'-B',str(HERE/'recovery.py'),operation,'--admission',str(admission_path),'--pin',pin]
def process_ticks(pid):return int(Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()[19])
def claim(m,d,a,operation,admission_pin):
    path=E/'STATE.json';before=path.read_bytes();state=json.loads(before);state_contract(state,d,operation)
    record={'run_id':d['run_id'],'operation':operation,'pid':os.getpid(),'start_ticks':process_ticks(os.getpid()),'active':True,'diagnosis_sha256':a['diagnosis_sha256'],'qualification_sha256':a['qualification_sha256'],'admission_sha256':admission_pin,'status':'RUNNING','failed_controller':d['controller']}
    key='active_gpu_experiment' if operation=='health' else 'production_restore_in_progress'
    m.cas_state(path,before,{**state,'maya145finite_recovery_current':record,key:record})
    return record

def release(m,d,record,result,error,*,safe,host):
    path=E/'STATE.json';before=path.read_bytes();state=json.loads(before)
    require(state.get('maya145finite_recovery_current')==record,'Foreign recovery replacement preserved')
    key='active_gpu_experiment' if record['operation']=='health' else 'production_restore_in_progress'
    require(state.get(key)==record,'Foreign phase replacement preserved')
    final={**record,'active':not safe,'status':'HOLD' if error else result['status'],'error':error,'result':result,'start_binding':getattr(host,'start_binding',None)}
    state.update(maya145finite_recovery_current=final);state[key]=False if safe else record
    if result and result.get('status') in ('SELECTED_BASELINE_RESTORED_FAILED_ARM_REMAINS_HOLD','SELECTED_RUNNING_PUBLIC_VERIFY_PENDING'):
        state.update(current_native_pid=host.restored_pid,production_temporarily_stopped=False)
        if result['status']=='SELECTED_RUNNING_PUBLIC_VERIFY_PENDING':
            state['production_verification_pending']=str(paths(d)[0]/'restore/result.json')
    if result and result.get('status')=='SELECTED_BASELINE_RESTORED_FAILED_ARM_REMAINS_HOLD':
        identity={**result['verified']['selected_identity'],'start_binding':host.start_binding}
        state['decode_optimization_current']={**state.get('decode_optimization_current',{}),'selected_identity':identity}
        state.update(current_native_pid=host.restored_pid,production_temporarily_stopped=False,production_verification_pending=False)
    m.cas_state(path,before,state)

def health_body(host,g,r,d,a,admission_path,admission_pin):
    metadata,out=paths(d);require(not out.exists(),'No health replay')
    command=argv_for('entry',admission_path,admission_pin)
    window=Path(host.launch_owned(Path(d['last_clean_window']),command,1200));host.free();host.kernel(d['kernel_since'])
    result=read(out/'receipt.json');require(result.get('passed') is True and result.get('window')==str(window),'Actual complete health result required')
    return {'status':'HEALTH_PENDING_INDEPENDENT_REVIEW','window':str(window),'output':str(out),'receipt_sha256':sha(out/'receipt.json'),'failed_arm_remains_HOLD':True}

def raw_health(out,a,r):
    required={out/'receipt.json'}|{out/(f'gpu{device}'+tail) for device in (0,1) for tail in ('.stdout','.stderr','-start.json','-exit.json')}
    pins=a['health_raw_sha256'];require(set(pins)=={str(p) for p in required},'Exact raw health closure required')
    for p in required:real(p,out);require(sha(p)==pins[str(p)],'Health raw changed')
    for device in (0,1):
        exit=read(out/f'gpu{device}-exit.json');start=read(out/f'gpu{device}-start.json');argv=[str(BINARY),'--baseline-health',str(device)]
        require(exit.get('argv')==argv and type(exit.get('returncode')) is int and exit['returncode']==0 and exit.get('error') is None and exit.get('cleanup_errors')==[] and type(exit.get('pid')) is int and exit['pid']>0 and exit.get('CPU_s')==120 and exit.get('AS_MiB') is None and exit.get('wall_s')==120 and exit.get('CUDA_hidden') is False,'Health child/bounds')
        require(start.get('pid')==exit['pid'] and start.get('argv')==argv and start.get('same_executable') is True and type(start.get('start_ticks')) is int and start['start_ticks']>0 and 'strata-deepseek-window.service' in start.get('cgroup','').strip().split('/'),'Actual child identity receipt')
        r.result_contract((out/f'gpu{device}.stdout').read_text(),exit['returncode'],device)

def restore_body(host,d,a):
    _,out=paths(d);receipt=out/'receipt.json';require(sha(receipt)==a['health_receipt_sha256'],'New health receipt changed')
    r=read(receipt);window=real(r['window'],R/'windows');require(window.parent==R/'windows' and re.fullmatch('[0-9]{8}T[0-9]{6}Z.json',window.name) and str(window) not in (d['failed_window'],d['last_clean_window']),'New canonical health window only')
    require(sha(window)==a['health_window_sha256'] and sha(window.with_suffix('.telemetry.jsonl'))==a['health_telemetry_sha256'],'New clean window changed')
    review=real(a['independent_health_review'],HERE);require(review.parent==HERE and sha(review)==a['independent_health_review_sha256'],'Independent terminal review changed')
    require(read(review).get('decision')=='BASELINE_HEALTH_24_CASES_REVIEWED','Concrete health review required')
    require(r.get('passed') is True and r.get('binary_sha256')==BINARY_SHA and r.get('devices')==[{'device':i,'cases':12,'exit':0} for i in (0,1)],'Two-device health proof')
    require(host.previous()==window,'Actual latest clean window required')
    host.restore_ds();host.guard_binding(host.restored_pid);host.restore_router()
    verified=host.verify_target(expected_pid=host.restored_pid)
    if verified.get('pending_public_probe'):
        return {'status':'SELECTED_RUNNING_PUBLIC_VERIFY_PENDING','verified':verified,'start_binding':host.start_binding,'native_restarts_requested':1}
    require(verified.get('passed') is True,'Full public restoration required; pending is not completion')
    return {'status':'SELECTED_BASELINE_RESTORED_FAILED_ARM_REMAINS_HOLD','verified':verified,'start_binding':host.start_binding,'native_restarts_requested':1}

def run(operation,admission_path,pin):
    require(operation in ('health','restore'),'Explicit operation only');admission_path=real(admission_path,HERE)
    require(admission_path.parent==HERE and admission_path.name.startswith('admission-'),'Frozen local admission only');require(sha(admission_path)==pin,'Admission changed')
    a=read(admission_path);dp=real(a['diagnosis'],HERE);require(dp.parent==HERE and dp.name.startswith('diagnosis-') and sha(dp)==a['diagnosis_sha256'],'Frozen diagnosis')
    d=diagnosis_contract(read(dp));admission_contract(a,d,operation)
    latest=d['failed_window'] if operation=='health' else read(paths(d)[1]/'receipt.json')['window']
    stopped_guard(d,operation,latest);q=qualified(a['qualification_sha256']);require(q['files'].get(str(dp))==a['diagnosis_sha256'],'Diagnosis not qualified')
    g,r,m,host=support(q);binding=lineage(d,q,g);metadata,_=paths(d)
    host.baseline_binding=binding;host.old_close_verified=True;host.since=d['kernel_since'];host.free();host.kernel(host.since)
    stopped_guard(d,operation,latest);require(not metadata.exists() if operation=='health' else metadata.is_dir(),'Fresh health / existing restore metadata')
    if operation=='health':metadata.mkdir()
    audit=metadata/operation;audit.mkdir();host.audit_dir=audit
    record=None;result=None;primary=None;cleanup=[];safe=False
    try:
        record=claim(m,d,a,operation,pin)
        if operation=='restore':raw_health(paths(d)[1],a,r)
        result=health_body(host,g,r,d,a,admission_path,pin) if operation=='health' else restore_body(host,d,a)
        safe=True
    except BaseException as exc:
        primary=exc
        if operation=='restore' and getattr(host,'start_binding',None) is not None:
            try:host.cleanup_owned_target(host.restored_pid)
            except BaseException as err:cleanup.append(repr(err))
        try:host.free();safe=True
        except BaseException as err:cleanup.append('Not safely released: '+repr(err))
    finally:
        # Capture a partial CAS claim even when its readback raised.
        try:
            current=read(E/'STATE.json').get('maya145finite_recovery_current') or {}
            if record is None and current.get('pid')==os.getpid() and current.get('run_id')==d['run_id'] and current.get('operation')==operation and current.get('diagnosis_sha256')==a['diagnosis_sha256'] and current.get('qualification_sha256')==a['qualification_sha256'] and current.get('admission_sha256')==pin:record=current
            if record is not None:release(m,d,record,result,repr(primary) if primary else None,safe=safe,host=host)
        except BaseException as err:cleanup.append('Custody release: '+repr(err))
        try:new(audit/'result.json',{'result':result,'error':repr(primary) if primary else None,'cleanup_errors':cleanup,'start_binding':getattr(host,'start_binding',None),'start_invocation':getattr(host,'start_invocation',None),'start_main_pid':getattr(host,'start_main_pid',None),'failed_arm_remains_HOLD':True,'retry':False})
        except BaseException as err:cleanup.append('Result write: '+repr(err))
        if primary and cleanup:primary.add_note('Secondary recovery faults: '+repr(cleanup))
    if primary:raise primary
    require(not cleanup,'Cleanup/custody fault');return result

def pending_contract(state,d,a,pin):
    metadata,_=paths(d);record=state.get('maya145finite_recovery_current') or {}
    require(record.get('run_id')==d['run_id'] and record.get('status')=='SELECTED_RUNNING_PUBLIC_VERIFY_PENDING' and record.get('active') is False and record.get('admission_sha256')==pin and record.get('qualification_sha256')==a['qualification_sha256'] and record.get('diagnosis_sha256')==a['diagnosis_sha256'],'Exact owned pending continuation')
    require(state.get('maintenance_controller')==d['controller'] and state.get('production_verification_pending')==str(metadata/'restore/result.json'),'Pending custody changed')
    require(not any(state.get(k) for k in PHASES if k!='production_verification_pending'),'Another phase')
    require(state.get('production_temporarily_stopped') is False and state.get('current_native_pid')==record.get('start_binding',{}).get('native_pid'),'Same pending selected owner')
    return record

def verify_pending(admission_path,pin,verification_id):
    """Explicit public-only continuation: no health replay or second unit start."""
    require(sys.platform=='linux' and HERE==Q/'recovery-v1','Physical wrapper only');stamp(verification_id)
    admission_path=real(admission_path,HERE);require(admission_path.parent==HERE and sha(admission_path)==pin,'Pending admission changed')
    a=read(admission_path);dp=real(a['diagnosis'],HERE);require(dp.parent==HERE and sha(dp)==a['diagnosis_sha256'],'Pending diagnosis changed')
    d=diagnosis_contract(read(dp));admission_contract(a,d,'restore');state=read(E/'STATE.json');old=pending_contract(state,d,a,pin)
    q=qualified(a['qualification_sha256']);g,r,m,host=support(q)
    binding=g.selected_binding({'decode_optimization_current':{'selected_identity':{'start_binding':old['start_binding']}}})
    host.start_binding=binding;host.restored_pid=binding['native_pid'];host.since=d['kernel_since'];host.guard_binding(host.restored_pid)
    if not host.idle():return {'status':'DEFERRED_BUSY_PENDING_UNTOUCHED'}
    before=(E/'STATE.json').read_bytes();require(json.loads(before)==state,'Pending custody changed before claim')
    metadata,_=paths(d);audit=metadata/('verify-'+verification_id);require(not audit.exists(),'No repeated public verification attempt');audit.mkdir();host.audit_dir=audit
    record={**old,'operation':'verify','verification_id':verification_id,'active':True,'pid':os.getpid(),'start_ticks':process_ticks(os.getpid()),'status':'RUNNING'}
    result=None;error=None;cleanup=[];claimed=False;safe=False
    try:
        m.cas_state(E/'STATE.json',before,{**state,'maya145finite_recovery_current':record,'production_restore_in_progress':record});claimed=True
        host.guard_binding(host.restored_pid);verified=host.verify_target(expected_pid=host.restored_pid)
        require(verified.get('passed') is True or verified.get('pending_public_probe'),'Pending public verification failed')
        result={'status':'SELECTED_RUNNING_PUBLIC_VERIFY_PENDING' if verified.get('pending_public_probe') else 'SELECTED_BASELINE_RESTORED_FAILED_ARM_REMAINS_HOLD','verified':verified,'start_binding':binding,'native_restarts_requested':0};safe=True
    except BaseException as exc:
        error=exc
        try:host.guard_binding(host.restored_pid);safe=True
        except BaseException as check:cleanup.append('Owner changed: '+repr(check))
    finally:
        try:
            current=read(E/'STATE.json').get('maya145finite_recovery_current')
            if claimed or current==record:release(m,d,record,result,repr(error) if error else None,safe=safe,host=host)
        except BaseException as check:cleanup.append('Pending custody release: '+repr(check))
        try:new(audit/'result.json',{'result':result,'error':repr(error) if error else None,'cleanup_errors':cleanup,'retry':False,'native_starts':0})
        except BaseException as check:cleanup.append('Pending result write: '+repr(check))
        if error and cleanup:error.add_note('Secondary pending faults: '+repr(cleanup))
    if error:raise error
    require(not cleanup,'Pending cleanup/custody fault');return result

def entry(admission_path,pin):
    require(sys.platform=='linux' and HERE==Q/'recovery-v1','Physical entry only')
    admission_path=real(admission_path,HERE);require(admission_path.parent==HERE and sha(admission_path)==pin,'Admission changed')
    a=read(admission_path);dp=real(a['diagnosis'],HERE);require(dp.parent==HERE and sha(dp)==a['diagnosis_sha256'],'Diagnosis changed')
    d=diagnosis_contract(read(dp));admission_contract(a,d,'health');metadata,out=paths(d)
    state=read(E/'STATE.json');record=state.get('maya145finite_recovery_current') or {}
    require(state.get('production_temporarily_stopped') is True and state.get('current_native_pid') is None and not any(state.get(k) for k in PHASES if k!='active_gpu_experiment'),'Only own health phase while production is stopped')
    require(record.get('active') is True and record.get('operation')=='health' and record.get('run_id')==d['run_id'] and record.get('diagnosis_sha256')==a['diagnosis_sha256'] and record.get('qualification_sha256')==a['qualification_sha256'] and record.get('admission_sha256')==pin and state.get('active_gpu_experiment')==record and state.get('maintenance_controller')==d['controller'],'Exact active recovery custody')
    require(type(record.get('pid')) is int and record['pid']>0 and process_ticks(record['pid'])==record.get('start_ticks'),'Live parent process binding')
    require(Path('/proc',str(record['pid']),'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')==argv_for('health',admission_path,pin),'Actual owning parent argv')
    qpath=HERE/'RECOVERY_QUALIFICATION.json';require(sha(qpath)==a['qualification_sha256'],'Entry qualification changed');q=read(qpath)
    require(q['source_sha256']=={n:sha(HERE/n) for n in SOURCES},'Entry source changed')
    require(sha(Path(d['failed_window']))==d['failed_window_sha256'] and sha(Path(d['last_clean_window']))==d['last_clean_window_sha256'],'Failed/clean lineage changed before entry')
    window=real(os.environ.get('STRATA_WINDOW_STATE',''),R/'windows');require(window.parent==R/'windows' and str(window) not in (d['failed_window'],d['last_clean_window']),'New canonical health window')
    w=read(window);expected=argv_for('entry',admission_path,pin)
    require(w.get('continued_from')==d['last_clean_window'] and w.get('mutation_started') is True and w.get('test_returncode') is None and w.get('admission_mode')=='continued-explicit-deepseek-maintenance' and w.get('command')==expected,'Canonical admitted command/lineage')
    require(Path('/proc/self/cmdline').read_bytes().rstrip(b'\0').decode().split('\0')==expected and 'strata-deepseek-window.service' in Path('/proc/self/cgroup').read_text().strip().split('/'),'Actual entry argv/cgroup')
    require(sha(BINARY)==BINARY_SHA,'Existing successful binary changed')
    g=module('maya_s_entry_observer',H/'gpu_check.py',HELPERS[str(H/'gpu_check.py')]);r=module('maya_s_entry_health',W/'recovery.py',HELPERS[str(W/'recovery.py')])
    require(not out.exists(),'Health attempt already used');out.mkdir();devices=[]
    for device in (0,1):
        argv=[str(BINARY),'--baseline-health',str(device)]
        result=r.child(argv,out,'gpu'+str(device),120,None,120,False,lambda pid,args:g.child_identity(pid,BINARY,args))
        devices.append(r.result_contract((out/('gpu'+str(device)+'.stdout')).read_text(),result['returncode'],device))
    new(out/'receipt.json',{'passed':True,'devices':devices,'window':str(window),'binary_sha256':BINARY_SHA,'baseline_only':True,'model_execution':False,'speed_claim':False})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['health','entry','restore','verify']);p.add_argument('--admission',type=Path,required=True);p.add_argument('--pin',required=True);p.add_argument('--verification-id');args=p.parse_args()
    require(args.operation=='verify' or args.verification_id is None,'Verification namespace only for pending verification')
    if args.operation=='entry':entry(args.admission,args.pin)
    elif args.operation=='verify':print(json.dumps(verify_pending(args.admission,args.pin,args.verification_id)))
    else:print(json.dumps(run(args.operation,args.admission,args.pin)))
