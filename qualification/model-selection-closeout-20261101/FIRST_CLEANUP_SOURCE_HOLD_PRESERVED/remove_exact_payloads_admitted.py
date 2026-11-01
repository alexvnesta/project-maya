"""One-shot explicit15file housekeeping operation; no service/model/native action.

Invoked only through the existing bounded CPU supervisor after pinned ROOT/Sol
review and action-time admission. Existing candidate controllers stay closed.
No glob deletion, no recursive deletion, no missing-file success or retry.
"""
from pathlib import Path
import argparse,datetime,hashlib,importlib.util,json,os,shutil,stat,subprocess,sys
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

def unlink_record(row,protected,append):
    p=checked_leaf(row,protected)
    parent_fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);fd=None
    try:
        fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent_fd)
        require(signature(os.fstat(fd))==row['signature'] and signature(os.stat(p.name,dir_fd=parent_fd,follow_symlinks=False))==row['signature'],'Leaf identity changed before unlink')
        append({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'path':str(p),'stage':'INTENT','signature':row['signature']})
        require(signature(os.stat(p.name,dir_fd=parent_fd,follow_symlinks=False))==row['signature'],'Leaf changed during durable intent; refuse replacement')
        os.unlink(p.name,dir_fd=parent_fd);os.fsync(parent_fd)
    finally:
        if fd is not None:os.close(fd)
        os.close(parent_fd)
    require(not p.exists() and not p.is_symlink(),'A replacement appeared; never delete it')
    return {'path':str(p),'bytes':row['signature']['size'],'previously_verified_sha256':row['previously_verified_sha256']}


def main(pin,parent):
    result=C/'PAYLOAD_REMOVAL_RESULT_FIRST.json';progress=C/'PAYLOAD_REMOVAL_FIRST.jsonl'
    require(not result.exists() and not progress.exists(),'One-shot cleanup; preserve prior evidence')
    driver=C.parent/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
    require(sha(driver)=='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71','Exact bounded child supervisor')
    spec=importlib.util.spec_from_file_location('existing_bounded_cpu',driver);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
    observed=d.observed();d.bounds(observed,os.getpid(),parent)
    admission=C/'CLEANUP_ADMISSION_ROOT.json';require(sha(admission)==pin,'Exact reviewed cleanup admission')
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
    state=read(E/'STATE.json');require(r.phase_free(state),'No private/build/pending restoration')
    binding=r.selected_binding(state);require(binding==plan['selected_binding']==admitted['selected_binding'],'Actual selected owner changed')
    a,*_=r.support();host=a.ChunkProductionHost();host.start_binding=binding
    require(host.idle(),'Actual defaultDeepSeek must be idle; no drain/restart to create a gap')
    host.guard_binding(binding['native_pid']);require(shutil.disk_usage(R).free>=132*2**30,'Root132 floor')
    require(sha(r.D/'bin/maya-ds4')==EXPECTED_NATIVE and sha(r.D/'config.json')==EXPECTED_CONFIG,'Selected artifacts changed')
    r.qualified('task','c7ae7445488b053b4e5b4ab160ca4f5f50b62c7ec9b433af746e8f94e94c1b03')
    identity=host.target_identity();require(identity['start_binding']==binding,'Selected actual config/exe/cgroup/flags/soleGPUowner')
    require(str(host.previous())==state['decode_optimization_current']['window'],'Previous owned window/kernel clean')
    protected={(v['dev'],v['ino']) for v in plan['protected_dependencies'].values()}
    def protected_unchanged():
        for path,row in plan['protected_dependencies'].items():
            t=Path(path).stat();require((t.st_dev,t.st_ino,t.st_size)==(row['dev'],row['ino'],row['size']),'Protected dependency changed')
    protected_unchanged()
    for row in rows:checked_leaf(row,protected)
    lsof=shutil.which('lsof');require(lsof is not None,'No open-file/mmap observer available')
    held=subprocess.run(['sudo','-n',lsof,'-nP','-F','pfn','--',*[row['path'] for row in rows]],capture_output=True,text=True,timeout=60)
    require(held.returncode==1 and held.stdout=='' and held.stderr=='','Some target is open/mapped or scan uncertain; do not unlink')
    references=[];prefixes=[str(root/name).encode() for name in ['maya-s-comparison-v1/assets/Maya-S','unsloth-v31-iq2xxs-download-v1/assets','s2-public-hybrid-v1/assets','s2-public-hybrid-v1/native-gu-FIRST/native-gu.bin']]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():continue
        try:argv=(proc/'cmdline').read_bytes()
        except (PermissionError,ProcessLookupError,FileNotFoundError):continue
        if any(prefix in argv for prefix in prefixes):references.append(int(proc.name))
    require(not references,'Active candidate/download/constructor process; do not unlink')
    require(host.idle(),'Work arrived before deletion; untouched')
    host.guard_binding(binding['native_pid'])
    completed=[];primary=None;free_before=shutil.disk_usage(R).free
    def append(value):
        with progress.open('a') as stream:stream.write(json.dumps(value,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())
    try:
        for row in rows:
            removed=unlink_record(row,protected,append);completed.append(removed)
            append({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'path':removed['path'],'stage':'REMOVED','bytes':removed['bytes']})
        protected_unchanged();host.guard_binding(binding['native_pid'])
        require(sha(r.D/'bin/maya-ds4')==EXPECTED_NATIVE and sha(r.D/'config.json')==EXPECTED_CONFIG,'Selected config/native changed')
        require(len(completed)==15 and all(not Path(row['path']).exists() for row in rows),'Every exact payload removed')
    except BaseException as exc:
        primary=repr(exc);raise
    finally:
        value={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':primary is None and len(completed)==15,'error':primary,'completed':completed,'removed_count':len(completed),'removed_bytes':sum(row['bytes'] for row in completed),'root_free_before':free_before,'root_free_after':shutil.disk_usage(R).free,'selected_binding':binding,'selected_config_sha256':EXPECTED_CONFIG,'selected_native_sha256':EXPECTED_NATIVE,'observed_child_limits':observed,'no_service_or_model_operation':True,'raw_source_failed_partial_and_cache_records_preserved':True,'retry':False}
        result.open('x').write(json.dumps(value,indent=2)+'\n')
    print(json.dumps({'passed':True,'removed_count':len(completed),'removed_bytes':sum(row['bytes'] for row in completed),'root_free_GiB':shutil.disk_usage(R).free/2**30}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--admission-sha256',required=True);parser.add_argument('--parent',type=int,required=True);args=parser.parse_args();main(args.admission_sha256,args.parent)
