"""One-shot explicit15file housekeeping operation; no service/model/native action.

Invoked only through the existing bounded CPU supervisor after pinned ROOT/Sol
review and action-time admission. Existing candidate controllers stay closed.
No glob deletion, no recursive deletion, no missing-file success or retry.
"""
from pathlib import Path
import argparse,datetime,fcntl,hashlib,importlib.util,json,os,re,shutil,stat,subprocess,sys
C=Path(__file__).resolve().parent
E=C.parents[1]
R=Path('/home/alex/strata-deepseek-test-20261024')
F=C.parent/'maya145-formal-prefill-v1'
EXPECTED_PLAN='8904383c06184dd2c55ccebf5b11755f25fc918f1132461005a37d2764487378'
EXPECTED_NATIVE='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
EXPECTED_CONFIG='c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'

def require(ok,why):
    if not ok:raise ValueError(why)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def read(p):return json.loads(Path(p).read_text())

def signature(t):
    return {'dev':t.st_dev,'ino':t.st_ino,'size':t.st_size,'mtime_ns':t.st_mtime_ns,'ctime_ns':t.st_ctime_ns,
            'nlink':t.st_nlink,'uid':t.st_uid,'mode':stat.S_IMODE(t.st_mode),'allocated_bytes':t.st_blocks*512}

def expected_paths(root):
    paths={root/'maya-s-comparison-v1/assets/Maya-S'/('DeepSeek-V4.1-Flash-1017-Maya-S-IQ2_XXS-%05d-of-00006.gguf'%n) for n in range(1,7)}
    paths.update(root/'unsloth-v31-iq2xxs-download-v1/assets/UD-IQ2_XXS'/('DeepSeek-V4.1-Flash-1017-UD-IQ2_XXS-%05d-of-00006.gguf'%n) for n in range(1,7))
    paths.update([root/'s2-public-hybrid-v1/assets/model-00028-of-00048.safetensors',root/'s2-public-hybrid-v1/assets/model-00029-of-00048.safetensors',root/'s2-public-hybrid-v1/native-gu-FIRST/native-gu.bin'])
    return paths

def checked_leaf(row,protected):
    p=Path(row['path']);require(p.is_absolute() and p.resolve()==p,'Exact real payload path')
    for parent in p.parents:
        require(not parent.is_symlink() and parent.is_dir(),'Real existing payload ancestors')
    t=p.lstat();require(stat.S_ISREG(t.st_mode) and t.st_nlink==1 and t.st_uid==os.getuid(),'Only own unaliased regular payload')
    require(signature(t)==row['signature'],'Payload identity changed; refuse rather than ignore')
    require((t.st_dev,t.st_ino) not in protected,'Selected/shared dependency inode; never unlink')
    return p

def exclusive_attempt(path,value):
    # Persistent O_EXCL marker is never removed/reused, including after failure.
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        stream.write(json.dumps(value,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())
    parent_fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(parent_fd)
    finally:os.close(parent_fd)


def unlink_record(row,protected,append,on_unlink=lambda value:None):
    p=checked_leaf(row,protected);notice=None
    parent_fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);fd=None
    try:
        fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent_fd)
        require(signature(os.fstat(fd))==row['signature'] and signature(os.stat(p.name,dir_fd=parent_fd,follow_symlinks=False))==row['signature'],'Leaf identity changed before unlink')
        append({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'path':str(p),'stage':'INTENT','signature':row['signature']})
        require(signature(os.stat(p.name,dir_fd=parent_fd,follow_symlinks=False))==row['signature'],'Leaf changed during durable intent; refuse replacement')
        os.unlink(p.name,dir_fd=parent_fd)
        notice={'path':str(p),'bytes':row['signature']['size'],'previously_verified_sha256':row['previously_verified_sha256'],
                'unlink_returned_success':True,'parent_fsync_passed':False,'postcheck_passed':False}
        on_unlink(notice)  # caller records syscall success BEFORE any later failure
        os.fsync(parent_fd);notice['parent_fsync_passed']=True
    finally:
        if fd is not None:os.close(fd)
        os.close(parent_fd)
    require(not p.exists() and not p.is_symlink(),'A replacement appeared; never delete it')
    notice['postcheck_passed']=True
    return notice


def lock_contract(raw,dev,ino,pid):
    require(all(type(x) is int and x>0 for x in (dev,ino,pid)),'Typed canonical lock identity')
    matches=[]
    for line in raw.splitlines():
        fields=line.split();keys=[x for x in fields if re.fullmatch(r'[0-9a-fA-F]+:[0-9a-fA-F]+:[0-9]+',x)]
        for key in keys:
            major,minor,inode=key.split(':')
            if (int(major,16),int(minor,16),int(inode))==(os.major(dev),os.minor(dev),ino):matches.append(fields)
    require(len(matches)==1,'Exactly one canonical lock record; no missing/duplicate/waiter')
    f=matches[0]
    require(len(f)==8 and re.fullmatch(r'[0-9]+:',f[0]) and f[1:4]==['FLOCK','ADVISORY','WRITE']
            and f[4]==str(pid) and f[6:]==['0','EOF'],'Exact current whole-file exclusiveflock owner; foreign/shared/OFD/POSIX refused')
    return {'holder_pid':pid,'dev':dev,'ino':ino,'whole_file_exclusive_flock':True}


def fdinfo_contract(raw,dev,ino,pid):
    lines=raw.splitlines();inodes=[line.split(':',1)[1].strip() for line in lines if line.startswith('ino:')]
    require(inodes==[str(ino)],'Canonical lock FD inode')
    locks=[line.split(':',1)[1].strip() for line in lines if line.startswith('lock:')]
    return lock_contract('\n'.join(locks),dev,ino,pid)


def canonical_lock_guard(lock,pid):
    path=R/'experiment.lock';t=os.fstat(lock.fileno());actual=path.lstat()
    require(not path.is_symlink() and path.resolve()==path and stat.S_ISREG(actual.st_mode)
            and (actual.st_dev,actual.st_ino)==(t.st_dev,t.st_ino),'Unchanged canonical lock file description')
    witness=lock_contract(Path('/proc/locks').read_text(),t.st_dev,t.st_ino,pid)
    descriptors=[]
    for fd in (Path('/proc')/str(pid)/'fd').iterdir():
        try:other=fd.stat()
        except FileNotFoundError:continue
        if (other.st_dev,other.st_ino)==(t.st_dev,t.st_ino):descriptors.append(fd.name)
    require(len(descriptors)==1,'Exactly one canonical held FD for current lock owner')
    fdinfo_contract((Path('/proc')/str(pid)/'fdinfo'/descriptors[0]).read_text(),t.st_dev,t.st_ino,pid)
    return {**witness,'holder_fd':int(descriptors[0])}


def bound_observer(a,binding,audit_dir):
    audit_dir=Path(audit_dir)
    require(audit_dir.is_dir() and not audit_dir.is_symlink() and audit_dir.resolve()==audit_dir,'Real own observer receipt sink')
    host=a.ChunkProductionHost();host.start_binding=dict(binding);host.audit_dir=audit_dir
    return host


def owned_claim_guard(r,binding,claim):
    current=read(E/'STATE.json')
    require(current.get('active_cpu_build')==claim and r.selected_binding(current)==binding,'Exact canonical cleanup claim/selected owner')
    require(not any(current.get(k) for k in r.PHASE_KEYS if k!='active_cpu_build'),'Another phase/restoration appeared')
    return current


def execute(r,host,binding,claim,plan,observed,lock_guard):
    result=C/'PAYLOAD_REMOVAL_TARGET_R3_RESULT_FIRST.json';progress=C/'PAYLOAD_REMOVAL_TARGET_R3_FIRST.jsonl'
    rows=plan['rows'];completed=[];intents=[];primary=None;free_before=shutil.disk_usage(R).free
    def append(value):
        with progress.open('a') as stream:stream.write(json.dumps(value,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())
    def unlink_observed(value):
        completed.append(value)  # remains counted if the following log/fsync fails
        append({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'path':value['path'],'stage':'UNLINK_RETURNED_SUCCESS','bytes':value['bytes']})
    protected={(v['dev'],v['ino']) for v in plan['protected_dependencies'].values()}
    def protected_unchanged():
        for path,row in plan['protected_dependencies'].items():
            t=Path(path).stat();require((t.st_dev,t.st_ino,t.st_size)==(row['dev'],row['ino'],row['size']),'Protected dependency changed')
    try:
        owned_claim_guard(r,binding,claim);lock_guard();require(host.idle(),'DefaultDeepSeek must remain idle, no drain/restart')
        host.guard_binding(binding['native_pid']);require(free_before>=132*2**30,'Root132 floor')
        require(sha(r.D/'bin/maya-ds4')==EXPECTED_NATIVE and sha(r.D/'config.json')==EXPECTED_CONFIG,'Selected artifacts changed')
        r.qualified('task','c7ae7445488b053b4e5b4ab160ca4f5f50b62c7ec9b433af746e8f94e94c1b03')
        identity=host.target_identity();require(identity['start_binding']==binding,'Selected actual config/exe/cgroup/flags/soleGPUowner')
        state=owned_claim_guard(r,binding,claim);require(str(host.previous())==state['decode_optimization_current']['window'],'Previous owned window/kernel clean')
        protected_unchanged()
        for row in rows:checked_leaf(row,protected)
        lsof=shutil.which('lsof');require(lsof is not None,'No open-file/mmap observer available')
        held=subprocess.run(['sudo','-n',lsof,'-nP','-F','pfn','--',*[row['path'] for row in rows]],capture_output=True,text=True,timeout=60)
        require(held.returncode==1 and held.stdout=='' and held.stderr=='','Target open/mapped or scan uncertain; no unlink')
        roots=[str(R/'reliability-optimization-20261025/decode-optimization-20261028'/name).encode() for name in ['maya-s-comparison-v1/assets/Maya-S','unsloth-v31-iq2xxs-download-v1/assets','s2-public-hybrid-v1/assets','s2-public-hybrid-v1/native-gu-FIRST/native-gu.bin']]
        references=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdecimal():continue
            try:argv=(proc/'cmdline').read_bytes()
            except (PermissionError,ProcessLookupError,FileNotFoundError):continue
            if any(prefix in argv for prefix in roots):references.append(int(proc.name))
        require(not references,'Active candidate/download/constructor process')
        require(host.idle(),'Work arrived before deletion; untouched');host.guard_binding(binding['native_pid'])
        for row in rows:
            owned_claim_guard(r,binding,claim);lock_guard();intents.append(row['path'])
            removed=unlink_record(row,protected,append,unlink_observed)
            append({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'path':removed['path'],'stage':'DURABLE_REMOVAL_CONFIRMED','bytes':removed['bytes']})
        protected_unchanged();host.guard_binding(binding['native_pid']);owned_claim_guard(r,binding,claim);lock_guard()
        require(sha(r.D/'bin/maya-ds4')==EXPECTED_NATIVE and sha(r.D/'config.json')==EXPECTED_CONFIG,'Selected config/native changed')
        require(len(completed)==15 and all(x['parent_fsync_passed'] and x['postcheck_passed'] for x in completed) and all(not Path(row['path']).exists() for row in rows),'Every exact payload durably removed')
    except BaseException as exc:
        primary=repr(exc);raise
    finally:
        unconfirmed=[path for path in intents if path not in {x['path'] for x in completed}]
        value={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':primary is None and len(completed)==15,'error':primary,
               'status':'COMPLETE' if primary is None and len(completed)==15 else 'PARTIAL_OR_PREDELETION_HOLD','completed':completed,
               'removed_count_confirmed_unlink':len(completed),'removed_bytes_confirmed_unlink':sum(row['bytes'] for row in completed),
               'unconfirmed_attempted_paths':unconfirmed,'unconfirmed_is_not_zero_or_success':True,
               'root_free_before':free_before,'root_free_after':shutil.disk_usage(R).free,'selected_binding':binding,
               'selected_config_sha256':EXPECTED_CONFIG,'selected_native_sha256':EXPECTED_NATIVE,'observed_child_limits':observed,
               'canonical_lock_policy':claim['canonical_lock_policy'],'selected_host_lock_not_released':True,'no_service_or_model_operation':True,'raw_source_failed_partial_and_cache_records_preserved':True,'retry':False}
        result.open('x').write(json.dumps(value,indent=2)+'\n')
    print(json.dumps({'passed':True,'removed_count_confirmed_unlink':len(completed),'removed_bytes_confirmed_unlink':sum(row['bytes'] for row in completed),'root_free_GiB':shutil.disk_usage(R).free/2**30}),flush=True)


def main(pin,parent):
    result=C/'PAYLOAD_REMOVAL_TARGET_R3_RESULT_FIRST.json';progress=C/'PAYLOAD_REMOVAL_TARGET_R3_FIRST.jsonl'
    require(not result.exists() and not progress.exists(),'One-shot cleanup; preserve prior evidence')
    driver=C.parent/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
    require(sha(driver)=='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71','Exact bounded child supervisor')
    spec=importlib.util.spec_from_file_location('existing_bounded_cpu',driver);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
    observed=d.observed();d.bounds(observed,os.getpid(),parent)
    admission=C/'CLEANUP_ADMISSION_ROOT_TARGET_R3.json';require(sha(admission)==pin,'Exact reviewed cleanup admission')
    admitted=read(admission)
    require(admitted['single_cleanup_only'] is True and admitted['automatic_retry'] is False,'Explicit housekeeping scope')
    for name,digest in admitted['source_and_input_pins'].items():require(sha(name)==digest,'Reviewed operation/input changed')
    require(sha(C/'CLEANUP_PLAN.json')==EXPECTED_PLAN,'Exact allowlisted payload plan')
    plan=read(C/'CLEANUP_PLAN.json');rows=plan['rows'];root=R/'reliability-optimization-20261025/decode-optimization-20261028'
    require(C==root/'model-selection-closeout-20261101' and E==R/'reliability-optimization-20261025','Canonical own closeout namespace')
    require(plan['schema']=='exclusive-unselected-payload-removal-v1' and plan['root_scope']==str(root),'Exact closed experiment payload scope')
    require(len(rows)==plan['count']==15 and {Path(row['path']) for row in rows}==expected_paths(root),'Exact15named completed payloads, no broader scope')
    require(sum(row['signature']['size'] for row in rows)==plan['bytes']==664358869199,'Exact byte total')
    require(plan['selected_native_sha256']==EXPECTED_NATIVE and plan['selected_config_sha256']==EXPECTED_CONFIG,'Selected model is protected')
    sys.path.insert(0,str(F));import current_runtime as r
    # Use the SAME canonical experiment lock. No second lock/service/GPU owner.
    with (R/'experiment.lock').open('a') as lock:
        state=read(E/'STATE.json');require(r.phase_free(state),'No private/build/pending restoration')
        binding=r.selected_binding(state);require(binding==plan['selected_binding']==admitted['selected_binding'],'Actual selected owner changed')
        a,*_=r.support();audit_dir=C/'SELECTED-TARGET-AUDIT-R3-FIRST';audit_dir.mkdir()
        host=bound_observer(a,binding,audit_dir)
        require(host.idle(),'Busy before cleanup attempt; untouched');host.guard_binding(binding['native_pid'])
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);holder=os.getpid();policy='cleanup_owns_existing_canonical_flock'
        except BlockingIOError:
            # Normal hosted API inherits this exact maintenance flock. Never
            # unlock/kill/restart it: verify its bound PID+kernel+FD lock instead.
            holder=binding['main_pid'];policy='exact_bound_selected_API_already_holds_canonical_flock'
        guard=lambda:canonical_lock_guard(lock,holder)
        witness=guard();host.guard_binding(binding['native_pid'])
        claim={'kind':'exact15payload-cleanup-target-r3','pid':os.getpid(),'start_ticks':int((Path('/proc')/str(os.getpid())/'stat').read_text().rsplit(') ',1)[1].split()[19]),'admission_sha256':pin,'plan_sha256':EXPECTED_PLAN,'attempt':str(C/'CLEANUP_ATTEMPT_TARGET_R3_FIRST.json'),'canonical_lock_policy':policy,'canonical_lock_witness':witness}
        exclusive_attempt(C/'CLEANUP_ATTEMPT_TARGET_R3_FIRST.json',claim)
        require(read(E/'STATE.json')==state,'Canonical state changed before claim')
        state['active_cpu_build']=claim;r.emit(E/'STATE.json',state)
        failure=None
        try:execute(r,host,binding,claim,plan,observed,guard)
        except BaseException as exc:failure=repr(exc);raise
        finally:
            latest=owned_claim_guard(r,binding,claim)
            latest['active_cpu_build']=False
            latest['model_payload_cleanup']={'status':'COMPLETE' if failure is None else 'HOLD','operation':str(C),'attempt':claim,'result':str(C/'PAYLOAD_REMOVAL_TARGET_R3_RESULT_FIRST.json'),'error':failure}
            r.emit(E/'STATE.json',latest)
        # Persistent attempt marker stays; a second invocation always refuses.


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--admission-sha256',required=True);parser.add_argument('--parent',type=int,required=True);args=parser.parse_args();main(args.admission_sha256,args.parent)
