"""New bounded assembly of unchanged qualified3840 parts, not a conversion replay.

The original failed join/partial and unknown outer exit remain unchanged. One
fresh output allocation,30 serial disjoint128-matrix copies, then one full SHA.
No model, GPU, service or networking action. Actual run requires separate source/
both-host qualification, captured outer launch, fully closed original40 source
acquisition and the existing owned CPU lease/CAS/healthy-serving guards.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import stat
import subprocess
import sys
import time
import uuid

HERE=Path(__file__).resolve().parent
Q=HERE.parent
E=Q.parent.parent
EXPECTED=Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/s2-reconstruction-v1/iq3s-assembly-v3')
BULK=Q/'iq3s-bulk-v1/bulk.py'
BULK_SHA='1a71e6f1d13d81d326b99be6613b19ed1dc898ac52259fdcf870ca0550ec75fb'
BUILD=Q/'placement-native-build-v1/build_current.py'
BUILD_SHA='60022606724b5b447056c0d54e0ea8c0f163359673b640cea0cd659abce26916'
PLAN=Q/'iq3s-conversion-v1/SOURCE_PLAN.json'
PLAN_SHA='9351465edc3ea4b4a3763552438d0309bbdbf913d434a2623a45f55dba81e54b'
ORIGINAL=Q/'iq3s-bulk-v1/conversion-FIRST'
OUT=HERE/'assembly-FIRST'
ARTIFACT=ORIGINAL/'overlay.iq3s'  # Intended logical model resource; NEW producer/raw receipts remain HERE.
COUNT,MATRIX_BYTES,PARTITION=3840,5068800,128
BYTES=COUNT*MATRIX_BYTES
RESERVE=132*2**30
NATIVE_RESERVE=35157299200
TOTAL_WALL=900
SOURCES=('assembly.py','test_assembly.py','run_cpu.py')
ENV={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1',
     'PYTHONDONTWRITEBYTECODE':'1','PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}
DRIVER_SHA='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'


def require(ok,why):
    if not ok:raise ValueError(why)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()


def regular(path):
    p=Path(path);require(p.is_absolute() and p.resolve()==p and not p.is_symlink(),'Real absolute file')
    s=p.stat();require(stat.S_ISREG(s.st_mode) and s.st_nlink==1,'One ordinary unaliased file')
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def emit(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())


def exact(name,path,pin):
    regular(path);require(sha(path)==pin,'Exact qualified helper source')
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def pinned(q,path):
    path=str(path);regular(path);require(Path(path).stat().st_size<=512*2**20 and q['files'].get(path)==sha(path),'Pinned metadata/source receipt')
    return Path(path)


def raw(q,path):return json.loads(pinned(q,path).read_text())


def ranges(count=COUNT,width=PARTITION):
    require(type(count) is int and count>0 and type(width) is int and width>0,'Positive partition geometry')
    return [(i,min(count,i+width)) for i in range(0,count,width)]


def disk_admission(free):
    require(type(free) is int and free>=RESERVE+BYTES+NATIVE_RESERVE,
        'After original40 completion retain root132 plus one new overlay plus future native; old parts/failed partial remain')
    return RESERVE+BYTES+NATIVE_RESERVE


def records_contract(records,count=COUNT,matrix_bytes=MATRIX_BYTES):
    require(len(records)==count,'Every original matrix exactly once')
    for i,row in enumerate(records):
        require(row['target_offset']==i*matrix_bytes and row['target_bytes']==matrix_bytes,'Exact contiguous original overlay map')


def pwrite_all(fd,data,offset,write=os.pwrite):
    done=0
    while done<len(data):
        n=write(fd,memoryview(data)[done:],offset+done)
        require(type(n) is int and 0<n<=len(data)-done,'Short/invalid explicit-offset output write');done+=n


def pread_exact(fd,size,offset):
    chunks=[];done=0
    while done<size:
        part=os.pread(fd,size-done,offset+done);require(part,'Short output readback');chunks.append(part);done+=len(part)
    return b''.join(chunks)


def proof_contract(record,proof,child,index,done,matrix_bytes=MATRIX_BYTES):
    require(proof['record']==record and proof['bytes']==matrix_bytes and
        proof['codec_returncode']==proof['encoder_returncode']==0 and
        type(child.get('returncode')) is int and child['returncode']==0 and child.get('error') is None and
        child.get('timed_out') is False and child.get('cleanup_errors')==[] and child.get('descendants_remaining') is False and
        done=={'index':index,'complete':True},'Unchanged actual matrix/codec/encoder/DONE and child0')


def copy_partition(records,begin,end,parts,fd,identity,proof_loader,*,matrix_bytes=MATRIX_BYTES):
    records_contract(records,len(records),matrix_bytes);s=os.fstat(fd)
    require(0<=begin<end<=len(records) and [s.st_dev,s.st_ino]==identity[:2] and s.st_size==identity[2]==len(records)*matrix_bytes,
        'Owned output FD and bounded disjoint partition')
    hashes=[]
    for index in range(begin,end):
        record=records[index];proof,child,done=proof_loader(index)
        proof_contract(record,proof,child,index,done,matrix_bytes)
        path=Path(parts)/('%04d.iq3s'%index);before=regular(path)
        require(before[2]==matrix_bytes,'Complete immutable source part')
        h=hashlib.sha256();offset=0
        with path.open('rb') as f:
            require([os.fstat(f.fileno()).st_dev,os.fstat(f.fileno()).st_ino]==before[:2],'Same original part inode at open')
            while offset<matrix_bytes:
                block=f.read(min(2**20,matrix_bytes-offset));require(block,'Short immutable matrix source')
                h.update(block);pwrite_all(fd,block,record['target_offset']+offset);offset+=len(block)
            require(not f.read(1),'Source grew past its immutable matrix interval')
        require(offset==matrix_bytes and regular(path)==before and h.hexdigest()==proof['sha256'],'Exact source part SHA/size/stability')
        back=hashlib.sha256();offset=0
        while offset<matrix_bytes:
            block=pread_exact(fd,min(2**20,matrix_bytes-offset),record['target_offset']+offset)
            back.update(block);offset+=len(block)
        require(back.hexdigest()==proof['sha256'],'Exact disjoint output readback SHA')
        hashes.append({'index':index,'record':record,'sha256':h.hexdigest(),'source_fingerprint':before})
    os.fsync(fd)
    return hashes


def full_hash(path,expected_bytes,receipt=None):
    before=regular(path);require(before[2]==expected_bytes,'Exact complete new overlay size')
    result=hash_helper().file_sha256(Path(path))
    require(result['fingerprint']==regular(path)==before,'New overlay changed during inherited-context full SHA')
    if receipt is not None:receipt.update(result)
    return result['sha256'],before


def absent(pid):
    require(type(pid) is int and pid>1,'Actual recorded PID/PGID')
    try:os.killpg(pid,0)
    except ProcessLookupError:return True
    return False


def failed_partial_contract(q):
    old=ORIGINAL/'overlay.partial';expected=q['failed_partial_fingerprint']
    require(expected[2]==17583667200,'Exact preserved original failed byte count')
    if old.exists():
        require(regular(old)==expected,'Original failed partial changed');return
    # Archive implementation/admission is a separate future source-qualified
    # action. This assembler never copies, deletes or repairs old evidence.
    gate=q['failed_partial_archive_gate']
    for key in ('source','qualification','receipt'):pinned(q,gate[key])
    module=exact('assembly_failed_evidence_archive',Path(gate['source']),q['files'][gate['source']])
    result=module.validate_archive(gate['receipt'],str(old),expected,gate['qualification'],q['files'][gate['qualification']])
    archived=Path('/data2/deepseek-frankenstein-evidence-20261101/iq3s-bulk-FIRST/overlay.partial')
    require(result['source_path']==str(old) and result['source_fingerprint']==expected and result['source_unlinked'] is True and
        result['archive_path']==str(archived) and result['archive_fingerprint']==regular(archived) and
        result['archive_fingerprint'][2]==expected[2] and type(result['sha256']) is str and len(result['sha256'])==64 and
        result['copy_child_exit']==result['independent_verify_child_exit']==0 and result['owned_groups_absent'] is True,
        'Entire failed evidence retained under separately qualified archive custody')


def original_failure(q):
    require(not (ORIGINAL/'result.json').exists(),'Original outcome changed; no implicit regrade')
    join=raw(q,ORIGINAL/'join/child.json');sup=raw(q,ORIGINAL/'supervision.json');absence=raw(q,ORIGINAL/'absence.json')
    observed=raw(q,ORIGINAL/'join/observed.json');attempt=raw(q,ORIGINAL/'attempt.json')
    require(join['pid']==observed['pid']==observed['pgid'] and join['returncode']==-9 and join['error'] is not None and
        join['cleanup']==[] and observed['cpu']==[30,30] and observed['as']==[512*2**20]*2 and observed['nice']==15 and
        sup['passed'] is False and sup['owned_claim_released'] is True and sup['error'] is not None and
        absence['passed'] is True and absence['pending_spawn'] is None and absence['cleanup_faults']==[] and
        len(absence['children'])==3846,'Preserve actual failed join and original captured closure')
    bad=[]
    for row in absence['children']:
        require(row['pgid']==row['pid'] and row['group_absent'] is True and absent(row['pid']),'Original captured group currently absent')
        if row['returncode']!=0:bad.append((row['pid'],row['returncode']))
    require(bad==[(join['pid'],-9)] and
        q['original_outer_exit_status']=='UNKNOWN' and q['failure_cause']=='UNDETERMINED',
        'Known original join failure; unknown outer exit/cause remain unchanged')
    failed_partial_contract(q)
    try:os.kill(attempt['controller_pid'],0)
    except ProcessLookupError:pass
    else:raise ValueError('Original bulk controller still live')
    return attempt['controller_pid']


def source40_closed(q):
    folder=Q/'original-expert-acquisition-v2';manifest=raw(q,folder/'ASSET_MANIFEST.json');terminal=raw(q,folder/'acquisition-state.json')
    require(q['files'][str(folder/'ASSET_MANIFEST.json')]=='68503758fd9ca619be1a165ce506809dd45e3bc23cd754f9c1220b9e82132df4' and
        terminal['status']=='ALL_FORTY_TRUNK_EXPERT_SHARDS_VERIFIED_NO_MODEL_RUN' and terminal['returncode']==0 and
        len(terminal['files'])==len(manifest['files'])==40 and terminal['manifest_sha256']==q['files'][str(folder/'ASSET_MANIFEST.json')],
        'Wait for complete original40 acquisition before any CPU claim/endpoints')
    root=Q/'iq3s-source-acquisition-v1/assets'
    require(terminal['asset_root']==str(root),'Exact original acquisition root')
    for row,spec in zip(terminal['files'],manifest['files']):
        require(row['path']==spec['path'] and row['bytes']==spec['size'] and row['sha256']==spec['sha256'] and
            row['status'] in ('DOWNLOADED_VERIFIED','VERIFIED_EXISTING') and regular(root/spec['path'])[2]==spec['size'],
            'Exact already-published original40 source receipts/sizes')
    # Source terminal is an intended rc0, not an observed outer exit. No new
    # full-source rehash or claim about that missing outer status is made.
    try:os.kill(terminal['pid'],0)
    except ProcessLookupError:pass
    else:raise ValueError('Original source producer still live')
    lock=Q/'iq3s-source-acquisition-v1/acquisition.lock';regular(lock)
    with lock.open('rb') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(f,fcntl.LOCK_UN)


def cpu_contract(proof,child,review,platform):
    o=proof['observed']
    env={k:v for k,v in ENV.items() if k not in ('PATH','LANG','LC_ALL')};env.update(MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    require(proof.get('passed') is True and proof.get('returncode')==0 and proof.get('failures')==proof.get('errors')==0 and
        proof['source_map']==review['source_map'] and proof['input_map']==review['input_map'] and proof['test_ids']==review['test_ids'] and
        proof['controls']==len(review['test_ids']) and proof['isolated'] is True and o['pid']==o['pgid']==child['pid'] and
        o['ppid']==proof['supervisor_pid'] and o['cpu']==[30,30] and o['nice']==15 and o['platform']==platform and
        o['as']==([512*2**20]*2 if platform=='linux' else None) and o['environment']==env and o['dont_write_bytecode'] is True and
        child['returncode']==0 and child.get('error') is None and child.get('cleanup')==[] and 0<=child['elapsed_seconds']<=90,
        'Actual complete bounded both-host focused CPU qualification')


def qualification(pin):
    path=HERE/'qualification.json';require(sha(path)==pin,'Separately frozen new assembly qualification')
    q=json.loads(path.read_text());sources={n:sha(HERE/n) for n in SOURCES}
    require(q['sources']==sources and q['root_entire_source_tests_driver_read'] is True and
        q['mode']=='s2-iq3s-assembly-v3-FIRST' and q['output_root']==str(OUT) and
        q['captured_outer_launch_required'] is True and q['outer_exit_capture_qualification'] in q['files'],
        'New source/manual/captured-launch qualification, never original-run replay')
    for n in q['files']:pinned(q,n)
    require(all(q['files'].get(str(HERE/n))==h for n,h in sources.items()) and q['files'].get(str(PLAN))==PLAN_SHA and
        q['files'].get(str(BULK))==BULK_SHA and q['files'].get(str(BUILD))==BUILD_SHA,'Exact unchanged source/plan/helper inputs')
    review=raw(q,q['CPU_review']);require(review['entire_source_tests_driver_manually_read'] is True and review['source_map']==sources and
        review['input_map']==input_map() and
        set(q['CPU'])=={'darwin','linux'} and len(set(review['test_ids']))==len(review['test_ids'])>0,'Exact manual/physical controls')
    for platform,paths in q['CPU'].items():cpu_contract(raw(q,paths['receipt']),raw(q,paths['child']),review,platform);pinned(q,paths['log'])
    plan=json.loads(PLAN.read_text());records_contract(plan['records'])
    require(len(q['part_proof_sha256'])==COUNT,'Every original part raw proof pinned')
    hash_helper(q)
    return q,plan['records']


def input_map():
    converter=Q/'iq3s-conversion-v1/convert.py'
    require(sha(BULK)==BULK_SHA and sha(BUILD)==BUILD_SHA and sha(PLAN)==PLAN_SHA and
        sha(converter)=='8bad9fd42a851bf5571f34f8727c19a88668e619f470cea046784b4a4a1bb574','Unchanged qualified assembly dependencies')
    require(sha(HASH_HELPER)==HASH_SHA,'Exact bounded SHA helper input')
    return {'bounded_hash_helper':HASH_SHA,'bulk':BULK_SHA,'build_custody':BUILD_SHA,'original_plan':PLAN_SHA,'converter_queue':sha(converter),
            'qualified_supervisor':DRIVER_SHA}


def proof_loader(q,records,original_pid):
    bulk=exact('assembly_original_bulk_limits',BULK,BULK_SHA)
    def load(index):
        stem=ORIGINAL/'parts'/('%04d'%index);pins=q['part_proof_sha256'][str(index)]
        for suffix,pin in pins.items():
            require(suffix in ('.json','.child.json','.DONE.json','.observed.json') and sha(stem.with_suffix(suffix))==pin,
                'Original raw matrix proof changed')
        require(set(pins)=={'.json','.child.json','.DONE.json','.observed.json'},'Complete original matrix evidence')
        proof=json.loads(stem.with_suffix('.json').read_text());child=json.loads(stem.with_suffix('.child.json').read_text())
        done=json.loads(stem.with_suffix('.DONE.json').read_text())
        bulk.actual_limits(json.loads(stem.with_suffix('.observed.json').read_text()),child['pid'],original_pid)
        proof_contract(records[index],proof,child,index,done)
        return proof,child,done
    return load


def child(mode,pin):
    require(sys.platform=='linux' and HERE==EXPECTED and sys.flags.isolated and sys.dont_write_bytecode and dict(os.environ)==ENV,
        'Exact isolated clean actual data child')
    resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20))
    require(os.getpriority(os.PRIO_PROCESS,0)<=15,'Inherited nice');os.nice(15-os.getpriority(os.PRIO_PROCESS,0))
    name=str(mode);emit(OUT/(name+'.observed.json'),{'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgrp(),
        'cpu':list(resource.getrlimit(resource.RLIMIT_CPU)),'as':list(resource.getrlimit(resource.RLIMIT_AS)),
        'nice':os.getpriority(os.PRIO_PROCESS,0),'environment':dict(os.environ),'isolated':bool(sys.flags.isolated)})
    q,records=qualification(pin);attempt=json.loads((OUT/'attempt.json').read_text())
    path=OUT/'overlay.partial';require(regular(path)[:3]==attempt['output_identity'],'Exact new shared output inode/size')
    if mode=='finalize':
        for i,(begin,end) in enumerate(ranges()):
            done=json.loads((OUT/(str(i)+'.DONE.json')).read_text());unit=json.loads((OUT/(str(i)+'.child.json')).read_text())
            require(unit['returncode']==0 and unit['error'] is None and unit['cleanup']==[] and absent(unit['pid']) and
                done['range']==[begin,end] and done['output_identity']==attempt['output_identity'] and
                [row['index'] for row in done['parts']]==list(range(begin,end)) and
                all(row['record']==records[row['index']] for row in done['parts']),'Complete disjoint actual copy coverage')
        hashing={};digest,before=full_hash(path,BYTES,hashing)
        emit(OUT/'finalize.DONE.json',{'sha256':digest,'bytes':BYTES,'source_inode':before[:3],
            'complete':True,'parts':COUNT,'full_SHA_passes':1,'bounded_hash_hops':hashing['hops'],
            'aggregate_CPU_can_exceed30_each_process_CPU30':True})
    else:
        index=int(mode);require(str(index)==mode and 0<=index<len(ranges()),'One exact partition')
        begin,end=ranges()[index];fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:rows=copy_partition(records,begin,end,ORIGINAL/'parts',fd,attempt['output_identity'],proof_loader(q,records,q['original_controller_pid']))
        finally:os.close(fd)
        emit(OUT/(name+'.DONE.json'),{'range':[begin,end],'parts':rows,'output_identity':attempt['output_identity']})


def run_child(mode,pin,children,owner,check,deadline,on_spawn=lambda:None):
    name=str(mode);start=time.monotonic();p=None;usage=None
    row={'mode':mode,'pid':None,'returncode':None,'error':None,'cleanup':[],'wait4_usage':None}
    try:
        check()
        with (OUT/(name+'.stdout')).open('xb') as out,(OUT/(name+'.stderr')).open('xb') as err:
            p=children.popen([str(Path(sys.executable).resolve()),'-I','-B',str(HERE/'assembly.py'),'child',name,pin],
                cwd=HERE,env=ENV,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
            row['pid']=p.pid
            on_spawn()
            while True:
                pid,status,actual=os.wait4(p.pid,os.WNOHANG)
                if pid:
                    p.returncode=os.waitstatus_to_exitcode(status);usage=actual;break
                check();require(time.monotonic()<min(deadline-15,start+75),'Unchanged bounded child deadline')
                time.sleep(.05)
            row['returncode']=p.returncode
            row['wait4_usage']={'user_seconds':usage.ru_utime,'system_seconds':usage.ru_stime,'max_RSS_KiB':usage.ru_maxrss}
            require(p.returncode==0,'New assembly child failed; preserve first failure')
            o=json.loads((OUT/(name+'.observed.json')).read_text())
            require(o=={'pid':p.pid,'ppid':os.getpid(),'pgid':p.pid,'cpu':[30,30],'as':[512*2**20]*2,
                'nice':15,'environment':ENV,'isolated':True},'Actual data-child limits/identity')
            require((OUT/(name+'.DONE.json')).is_file(),'Actual child DONE')
    except BaseException as exc:row['error']=repr(exc)
    finally:
        if p is not None:
            try:owner.cleanup(p,min(deadline,start+90))
            except BaseException as exc:row['cleanup'].append(repr(exc));children.owner.cleanup_failed(name,exc)
            row['returncode']=p.poll()
        row['elapsed_seconds']=time.monotonic()-start
        emit(OUT/(name+'.child.json'),row)
    require(row['returncode']==0 and row['error'] is None and not row['cleanup'] and row['wait4_usage'] is not None and row['elapsed_seconds']<=90,
        'New bounded assembly HOLD; no retry or larger limits')


def publish_new_artifact(working,artifact,identity):
    require(working==OUT/'overlay.partial' and artifact==ARTIFACT and working!=ORIGINAL/'overlay.partial' and
        regular(working)[:3]==identity,'Only the exact new assembly allocation may be published')
    require(not artifact.exists() and not artifact.is_symlink(),'Previously absent intended artifact only')
    os.link(working,artifact);working.unlink()
    for directory in (artifact.parent,working.parent):
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    result=regular(artifact);require(result[:3]==identity,'Same new artifact inode/size after exclusive publication')
    return result


def main(pin):
    require(sys.platform=='linux' and HERE==EXPECTED and sys.flags.isolated and sys.dont_write_bytecode,'Actual isolated controller only')
    deadline=time.monotonic()+TOTAL_WALL;q,records=qualification(pin)
    source40_closed(q)  # Must precede endpoint admission and the existing CPU lease.
    original_pid=original_failure(q);require(original_pid==q['original_controller_pid'],'Original failed controller identity')
    bulk=exact('assembly_bulk',BULK,BULK_SHA);bulk.qualification(q['original_bulk_qualification_sha256'])
    build=exact('assembly_custody',BUILD,BUILD_SHA);early=build.exact('build_early')
    binding=early.early_guard();build.strict_idle();require(binding==q['selected_binding'],'Fresh selected owner')
    owner,support=build.exact('build_owner'),build.exact('build_support');healthy=build.exact('build_healthy_work')
    _,runtime,_,host,actual=support.support();require(actual==binding,'Selected owner changed')
    gpu=owner.observe_gpu_lease(host,binding);cas=owner.load_cas()
    require(not OUT.exists() and not OUT.is_symlink() and not ARTIFACT.exists() and not ARTIFACT.is_symlink(),'Fresh new output and previously absent intended artifact; original failed partial retained')
    disk_admission(shutil.disk_usage(HERE).free)
    record={'mode':'s2-iq3s-assembly-v3-FIRST','controller_pid':os.getpid(),'controller_start_ticks':owner.process_ticks(os.getpid()),
        'nonce':uuid.uuid4().hex,'start_binding':binding,'qualification_sha256':pin}
    with owner.CPULease(E/'cpu-build.lock') as lease:
        claimed=False;started=False;failure=None;children=None;result=None
        def check():
            lease.check();require(time.monotonic()<deadline-15,'New total900 wall bound')
            state=build.coordination_guard(support,healthy,runtime,host,binding,record if claimed else None,cpu_started=started)
            early.early_guard(record if claimed else None);owner.observe_gpu_lease(host,binding,gpu['identity'])
            build.cpu_headroom(Path('/proc/meminfo').read_text());require(sha(HERE/'qualification.json')==pin,'Qualification changed')
            require(shutil.disk_usage(HERE).free>=RESERVE+NATIVE_RESERVE,'Root132 plus future native retained');return state
        state=check();source40_closed(q);OUT.mkdir()
        children=bulk.Children(owner.OwnedChildren(OUT/'owned-children.jsonl'))
        try:
            raw_state=(E/'STATE.json').read_bytes();require(json.loads(raw_state)==state and not state.get('active_cpu_build'),'CPU claim race')
            cas.cas_state(E/'STATE.json',raw_state,dict(state,active_cpu_build=record));claimed=True
            fd=os.open(OUT/'overlay.partial',os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600)
            try:os.ftruncate(fd,BYTES);identity=regular(OUT/'overlay.partial')[:3]
            finally:os.close(fd)
            emit(OUT/'attempt.json',dict(record,output_identity=identity,original_outer_exit_status='UNKNOWN',known_original_join_exit=-9))
            # The qualified fail-stop queue is reused unchanged; serial copies
            # keep each child's band small and actual wait4 usage attributable.
            conversion=bulk.conversion()
            def spawned():
                nonlocal started
                started=True
            def task(index):
                run_child(index,pin,children,owner,check,deadline,on_spawn=spawned);return index
            done=conversion.convert_queue(list(range(len(ranges()))),task,check,workers=1,
                wall=max(0,deadline-time.monotonic()-105))
            require(done==list(range(len(ranges()))) and children.absence()['passed'],'All copy groups closed before finalizer')
            started=True;run_child('finalize',pin,children,owner,check,deadline)
            final=json.loads((OUT/'finalize.DONE.json').read_text());require(final['source_inode']==identity and final['bytes']==BYTES,'Final complete artifact')
            require(children.absence()['passed'],'All new groups absent before exclusive publication')
            published=publish_new_artifact(OUT/'overlay.partial',ARTIFACT,identity)
            result=dict(final,artifact_path=str(ARTIFACT),fingerprint=published,
                producer_source=str(HERE/'assembly.py'),producer_qualification_sha256=pin,
                original_outer_exit_status='UNKNOWN',known_original_join_exit=-9,original_failure_regraded=False,
                separate_artifact_acceptance_required=True,model_executed=False,production_changed=False)
        except BaseException as exc:failure=exc
        finally:
            try:
                if children is not None:
                    children.cleanup_all(owner,deadline);absence=children.absence();emit(OUT/'absence.json',absence)
                    require(absence['passed'],'All captured new groups must close before claim release')
                    if claimed:bulk.release_claim(cas,E/'STATE.json',record,absence);claimed=False
                check()
            except BaseException as exc:
                if failure is None:failure=exc
                else:failure.add_note('Assembly closure: '+repr(exc))
            emit(OUT/'supervision.json',{'passed':failure is None,'error':repr(failure) if failure else None,'owned_claim_released':not claimed})
        if failure is not None:raise failure
        emit(OUT/'result.json',dict(result,qualification_sha256=pin,passed=True));return 0



HASH_HELPER=Q/'bounded-sha256-v1/fork_hash.py'
HASH_SHA='26ab3c1bb4330e1e933a11d739806f7cd2db8a890ac100d208f52a9d67b0cec2'


def hash_helper(q=None):
    """Exact helper; actual runs also require all original raw five-control proofs."""
    module=exact('integrated_bounded_sha256',HASH_HELPER,HASH_SHA)
    if q is None:return module  # CPU smoke tests still enforce helper.bounds().
    files=q['files']
    def checked(path):
        path=Path(path);regular(path)
        require(path.stat().st_size<=512*2**20 and files.get(str(path))==sha(path),'Pinned bounded-hash raw qualification member')
        return path
    qualification=json.loads(checked(q['bounded_hash_qualification']).read_text())
    review=json.loads(checked(qualification['CPUReview']).read_text())
    names=('fork_hash.py','test_hash.py','run_cpu.py')
    sources={n:sha(checked(HASH_HELPER.parent/n)) for n in names}
    require(sources['fork_hash.py']==HASH_SHA and qualification['source_map']==review['source_map']==sources and
        qualification['input_map']==review['input_map']=={'qualified_supervisor':'3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'} and
        qualification['test_ids']==review['test_ids'] and len(set(review['test_ids']))==len(review['test_ids'])==5 and
        review['entire_source_tests_driver_manually_read'] is True and set(qualification['CPU'])=={'darwin','linux'},
        'Actual identical helper source/input/five IDs/manual/both-host qualification')
    supervisor=Q.parent/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
    require(sha(checked(supervisor))==qualification['input_map']['qualified_supervisor'],'Exact helper supervisor')
    for platform,paths in qualification['CPU'].items():
        require(set(paths)=={'receipt','child','log'},'All raw helper CPU proof paths')
        proof=json.loads(checked(paths['receipt']).read_text());child=json.loads(checked(paths['child']).read_text());checked(paths['log'])
        observed=proof['observed'];environment={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
            'MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}
        require(proof.get('passed') is True and proof.get('returncode')==0 and proof.get('failures')==proof.get('errors')==0 and
            proof['source_map']==sources and proof['input_map']==qualification['input_map'] and proof['test_ids']==review['test_ids'] and
            proof['controls']==5 and proof['isolated'] is True and observed['platform']==platform and
            observed['pid']==observed['pgid']==child['pid'] and observed['ppid']==proof['supervisor_pid'] and
            observed['cpu']==[30,30] and observed['nice']==15 and observed['as']==([512*2**20]*2 if platform=='linux' else None) and
            observed['environment']==environment and observed['dont_write_bytecode'] is True and
            child['returncode']==0 and child.get('error') is None and child.get('cleanup')==[] and 0<=child['elapsed_seconds']<=90,
            'Actual clean bounded physical helper child and nested-group supervision')
    return module


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['run','child']);parser.add_argument('value');parser.add_argument('pin',nargs='?')
    args=parser.parse_args()
    if args.mode=='run':raise SystemExit(main(args.value))
    child(args.value,args.pin)
