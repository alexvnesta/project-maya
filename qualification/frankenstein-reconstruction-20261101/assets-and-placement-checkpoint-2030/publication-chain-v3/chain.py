"""Validate existing publication receipts without rehashing model weights.

No endpoint, model, GPU, service, writer or cleanup entry point. Lock acquisition
is a nonblocking observation on an EXISTING writer lock, released on exit. Raw
source/CPU qualifications remain authoritative; this code does not regrade them.
Fingerprints captured after publication are custody evidence, not a fresh content
hash or proof against an unobserved replacement before the snapshot was made.
"""
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat

HERE = Path(__file__).resolve().parent
Q = HERE.parent
DC = Q.parent
E = DC.parent
R = E.parent
D = Path('/home/alex/deepseek-hosted-20261025')
BASE_MANIFEST = '22ecce3e7085e29520fadaa67d603beb8cc0905f834ff3563029f6038825034b'
RELEASE = 'cd146a86438054e664b6dfb953341fc65ecb34d9ab6d9d22851009c239713580'
PACK_STATE_A = '5ad3c46fd35167ab51b29b9e4f8af58005b2b3adf65691922e3f3de54885d195'
NATIVE92 = '92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
CONFIG43 = 'c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
LAUNCH_SHA = '51f1c6d189af715b0009ec997e1d66d77ff299bb8ade076d3bfaa70457daccf8'
SOURCES = ('chain.py', 'test_chain.py', 'run_cpu.py')
ENV = {'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
       'MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}
DATA_ENV = {k: ENV[k] for k in ('CUDA_VISIBLE_DEVICES','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS',
                               'MALLOC_ARENA_MAX','PYTHONDONTWRITEBYTECODE')}
DATA_ENV.update(PATH='/usr/bin:/bin',LANG='C',LC_ALL='C')


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(2**20),b''):h.update(block)
    return h.hexdigest()


def fingerprint(path):
    p=Path(path)
    require(p.is_absolute() and p.resolve()==p and not p.is_symlink(),'Real absolute publication path')
    s=p.stat();require(stat.S_ISREG(s.st_mode) and s.st_nlink==1,'One ordinary publication inode')
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def pinned(q,path):
    path=str(path)
    require(path in q['files'] and fingerprint(path)[2]<=512*2**20 and sha(path)==q['files'][path],
            'Pinned raw metadata/source/proof only: '+path)
    return Path(path)


def raw(q,path):return json.loads(pinned(q,path).read_text())


def absent(pid,group=False):
    require(type(pid) is int and pid>1,'Actual owned PID/PGID')
    try:
        if group:os.killpg(pid,0)
        else:os.kill(pid,0)
    except ProcessLookupError:return True
    return False


@contextlib.contextmanager
def writer_free(lock):
    path=Path(lock['path']);before=fingerprint(path)
    require(before==lock['fingerprint'],'Writer-lock inode changed')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        require([os.fstat(fd).st_dev,os.fstat(fd).st_ino]==before[:2],'Actual writer-lock FD')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Owned publication writer still holds lock') from None
        require(fingerprint(path)==before,'Writer lock replaced at acquisition')
        yield
        require(fingerprint(path)==before,'Writer lock replaced during observation')
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)


def clean_exit(row,pid):
    require(row.get('pid')==pid and type(row.get('returncode')) is int and row['returncode']==0 and
            row.get('error') is None and row.get('cleanup',[])==[],'Actual bound controller exit0/no cleanup error')


def outer_exit_contract(q,g,pid,source,start_ticks=None):
    if g['kind']=='base-acquisition-publication':
        observer=raw(q,g['outer_exit_observer'])
        ticks=observer.get('start_ticks')
        ticks_ok=(type(ticks) is int and ticks>0 and observer.get('start_ticks_status')=='RECORDED') or (
            ticks is None and observer.get('start_ticks_status')=='UNKNOWN_NOT_CAPTURED')
        require(observer.get('pid')==pid and observer.get('source_path')==str(source) and
            observer.get('source_sha256')==q['files'][str(source)] and observer.get('returncode') is None and
            observer.get('status')=='UNKNOWN' and ticks_ok and
            (start_ticks is None or observer['start_ticks']==start_ticks) and
            observer.get('limitation')=='Terminal reports intended returncode0 before print; actual outer exit unobserved' and
            absent(pid),'Only base publication may preserve explicitly unobserved outer exit')
        return
    # New assembly/native owners use the separately qualified captured launcher.
    start=raw(q,g['controller_start']);exit=raw(q,g['controller_exit'])
    clean_exit(exit,pid)
    launch=Q/'launch-custody-v1/launch.py';require(q['files'].get(str(launch))==LAUNCH_SHA,'Exact actual-wait captured-launch source')
    pinned(q,launch)
    tail=['run',q['files'][g['qualification']]] if g['kind']=='bounded-overlay-join' else [
        '--stage','native','--qualification-sha256',q['files'][g['owner_qualification']]]
    require(start['pid']==exit['pid']==pid and start['supervisor_pid']==exit['supervisor_pid'] and start['argv']==exit['argv'] and
        exit.get('actual_wait_observed') is True and exit.get('retry') is False and exit.get('target_signals_sent')==0 and
        len(exit['argv'])>=4 and exit['argv'][1:3]==['-I','-B'] and exit['argv'][3]==str(source) and exit['argv'][4:]==tail and
        absent(pid),'Genuine new captured outer wait0; unknown never substituted')


def hash_hops(rows,size,pid,parent):
    require(type(rows) is list and len(rows)==(size+4*2**30-1)//(4*2**30) and 1<=len(rows)<=64,
        'Exact default4GiB normal-SHA hop coverage')
    offset=0;expected_parent=parent;expected_pid=pid
    for index,row in enumerate(rows):
        o=row['observed'];end=min(size,offset+4*2**30)
        require(o['pid']==expected_pid and o['ppid']==expected_parent and o['pgid']==pid and
            o['cpu']==[30,30] and o['as']==[512*2**20]*2 and o['nice']==15 and o['isolated'] is True and
            o['dont_write_bytecode'] is True and o['CUDA_VISIBLE_DEVICES']=='' and row['offset']==offset and row['end']==end and
            all(type(row[k]) in (int,float) and math.isfinite(row[k]) and row[k]>=0 for k in ('own_user_seconds','own_system_seconds')),
            'Actual inherited-context PID/offset/per-processCPU30/AS512/same owned PGID')
        if index+1<len(rows):
            require(row['waited_child_returncode']==0 and row['waited_child_pid']==rows[index+1]['observed']['pid'],
                'Every direct descendant actually waited0')
            expected_parent=o['pid'];expected_pid=row['waited_child_pid']
        offset=end
    require(offset==size,'Complete original-order normal SHA; not Merkle or serialized state')


def absence_contract(row):
    require(row.get('passed') is True and row.get('pending_spawn') is None and row.get('cleanup_faults')==[] and
            type(row.get('children')) is list and row['children'],'Owned captured group list required')
    seen=set()
    for child in row['children']:
        pid=child['pid'];require(pid not in seen and child.get('pgid')==pid and child.get('returncode')==0 and
            child.get('group_absent') is True and absent(pid,True),'Every captured group closed0 and currently absent')
        seen.add(pid)
    return seen


def data_child(child,observed,parent):
    pid=child['pid']
    require(type(child.get('returncode')) is int and child['returncode']==0 and child.get('error') is None and
            child.get('cleanup')==[] and observed['pid']==observed['pgid']==pid and observed['ppid']==parent and
            observed['cpu']==[30,30] and observed['as']==[512*2**20]*2 and observed['nice']==15 and
            observed['environment']==DATA_ENV and observed['isolated'] is True and
            observed.get('dont_write_bytecode',True) is True and absent(pid,True),'Actual bounded data child0/owned group absent')
    if 'elapsed_seconds' in child:require(0<=child['elapsed_seconds']<=90,'Recorded data-child wall90')
    return pid


def source_qualification(q,g):
    """Only the already-qualified pure qualification function, never its gate/main."""
    source,qualification=Path(g['source']),Path(g['qualification'])
    expected={'base-acquisition-publication':Q/'base-acquisition-v2/acquire.py',
              'bounded-overlay-join':Q/'iq3s-assembly-v3/assembly.py',
              'bounded-native-finalize':Q/'native-payload-v2/payload.py'}[g['kind']]
    require(source==expected and str(source) in g['raw_paths'] and str(qualification) in g['raw_paths'],
            'Exact original qualified source and qualification')
    pinned(q,source);pinned(q,qualification)
    spec=importlib.util.spec_from_file_location('publication_original_'+source.parent.name.replace('-','_'),source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if g['kind']=='bounded-overlay-join':
        require(qualification==source.parent/'qualification.json','Actual assembly-v3 qualification path')
        actual,records=module.qualification(q['files'][str(qualification)])
        review=raw(q,actual['CPU_review']);require(len(review['test_ids'])==10,'Exact new ten assembly controls')
        bulk_path=Q/'iq3s-bulk-v1/bulk.py';pinned(q,bulk_path)
        bulk=module.exact('publication_original_bulk',bulk_path,module.BULK_SHA)
        bulk.qualification(actual['original_bulk_qualification_sha256'])
        return module,actual,records
    if g['kind']=='bounded-native-finalize':
        actual,plan,receipt=module.qualification(qualification,q['files'][str(qualification)])
        require(len(actual['test_ids'])==15,'Exact new fifteen payload controls')
        owner_path=Q/'native-owner-v2/owner.py';require(g['owner_source']==str(owner_path),'Exact native owner-v2')
        pinned(q,owner_path);pinned(q,g['owner_qualification'])
        spec=importlib.util.spec_from_file_location('publication_native_owner2',owner_path)
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
        oq,_,op=owner.qualified('native',q['files'][g['owner_qualification']])
        require(Path(g['owner_qualification'])==owner_path.parent/'native-qualification.json' and len(oq['test_ids'])==7 and op==plan,
            'Exact source/actual both-host seven owner controls and same native plan')
        return module,actual,plan,owner,oq
    module.qualification(qualification,q['files'][str(qualification)])


def snapshot(q,g,result_path):
    row=raw(q,g['publication_snapshot'])
    require(row.get('schema')=='s2-publication-fingerprints-v1' and row.get('kind')==g['kind'] and
            row.get('source_result_path')==result_path and row.get('source_result_sha256')==q['files'][result_path] and
            type(row.get('files')) is dict and row['files'],'Exact postpublication snapshot bound to raw result')
    for name,value in row['files'].items():
        require(value['fingerprint']==fingerprint(name) and value['published_inode']==value['fingerprint'][:3],
                'Stable postpublication inode/size/times')
    return row


def constructor_contract(q,g,constructor):
    root=Q/'candidate-pack-v1'
    pinned(q,root/'construct_pack.py');review=raw(q,str(root/'ROOT_SOURCE_REVIEW.json'))
    require(review['entire_source_tests_driver_manually_read'] is True and
        constructor['source_sha256']==review['source_sha256'],'Actual constructor source/manual review')
    for name,h in review['source_sha256'].items():require(q['files'].get(str(root/name))==h and sha(pinned(q,root/name))==h,'Exact constructor source')
    for name,h in review['input_sha256'].items():
        path=Q/name.removeprefix('shared/') if name.startswith('shared/') else root/name
        require(q['files'].get(str(path))==h and sha(pinned(q,path))==h,'Exact constructor frozen input')
    ids=None
    for label in ('mac','ubuntu'):
        proof=raw(q,str(root/('CPU-FIRST-'+label+'.json')));child=raw(q,str(root/('child-FIRST-'+label+'.json')))
        if ids is None:ids=proof['test_ids']
        require(proof.get('passed') is True and proof.get('returncode')==0 and proof.get('failures')==proof.get('errors')==0 and
            proof['physical_host']==label and proof['controls']==len(ids)==6 and proof['test_ids']==ids and
            proof['source_sha256']==child['source_sha256']==review['source_sha256'] and
            proof['input_sha256']==review['input_sha256'] and proof['CPU_seconds']==[30,30] and proof['nice']==15 and
            proof['Linux_AS_bytes']==([512*2**20]*2 if label=='ubuntu' else None) and
            proof['pid']==child['pid'] and child.get('returncode')==0 and child.get('timed_out') is False and
            child.get('wall_seconds')==90 and child.get('cleanup_errors')==[],'Actual original six constructor controls/child0 each host')
    require(constructor['CPU_test_ids']==ids,'Constructor uses exact qualified controls')


def base_group(q,g):
    manifest=raw(q,g['manifest']);terminal=raw(q,g['terminal']);attempt=raw(q,g['attempt'])
    require(Path(g['manifest'])==Q/'base-acquisition-v2/ASSET_MANIFEST.json' and
            q['files'][g['manifest']]==BASE_MANIFEST and
            Path(g['terminal'])==Q/'base-acquisition-v2/acquisition-state.json' and terminal==attempt and
            manifest['repo']=='peasantsmith/DeepSeek-V4.1-Flash-1017-Maya-GGUF' and
            manifest['revision']=='d1fc01009f21e26157acb6858c315d0365483b72' and
            manifest['total_bytes']==sum(x['size'] for x in manifest['files'])==347445667721 and
            len(manifest['files'])==len(terminal['files'])==8 and
            terminal.get('status')=='ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN' and terminal.get('returncode')==0 and
            terminal['manifest_sha256']==BASE_MANIFEST and terminal['asset_root']==str(Q/'base-acquisition-v1/assets') and
            terminal.get('model_or_service_actions')==0,'Actual final ALL8 acquisition publication chain')
    outer_exit_contract(q,g,terminal['pid'],Path(g['source']))
    snap=snapshot(q,g,g['terminal'])
    require(snap['writer_lock']['path']==str(Q/'base-acquisition-v1/acquisition.lock'),'Exact original acquisition writer lock')
    expected={}
    for result,spec in zip(terminal['files'],manifest['files']):
        require(result['path']==spec['path'] and result['status'] in ('DOWNLOADED_VERIFIED','VERIFIED_EXISTING') and
                result['bytes']==spec['size'] and result['sha256']==spec['sha256'],'Exact streamed published file SHA/size')
        name=str(Q/'base-acquisition-v1/assets'/spec['path']);expected[name]=spec['sha256']
        require(snap['files'][name]['fingerprint'][2]==spec['size'],'Actual base file size')
    require(set(snap['files'])==set(expected),'Exact ALL8 postpublication closure')
    with writer_free(snap['writer_lock']):
        require(all(fingerprint(n)==snap['files'][n]['fingerprint'] for n in expected),'Base changed under free writer lock')
    # Metadata construction is independently pinned and source-qualified; it
    # references precisely this actual ALL8 terminal and all output metadata.
    constructor=raw(q,g['constructor'])
    constructor_contract(q,g,constructor)
    require(constructor.get('metadata_only') is True and constructor.get('weights_ready') is False and
            constructor.get('all8_base_terminal_sha256')==q['files'][g['terminal']] and constructor.get('outputs'),
            'Actual metadata constructor belongs to this ALL8 publication')
    for rel,value in constructor['outputs'].items():
        p=Path(g['constructed_pack'])/rel
        require(pinned(q,p).stat().st_size==value['bytes'] and q['files'][str(p)]==value['sha256'],
                'Actual constructed pack metadata output')
    return snap,expected


def overlay_group(q,g,context):
    module,aq,records=context;folder=Q/'iq3s-assembly-v3/assembly-FIRST'
    artifact=Q/'iq3s-bulk-v1/conversion-FIRST/overlay.iq3s'
    require(g['result']==str(folder/'result.json') and g['artifact']==str(artifact),
        'New assembly-v3 provenance at the already-qualified intended logical resource path')
    result=raw(q,g['result']);attempt=raw(q,str(folder/'attempt.json'));supervision=raw(q,str(folder/'supervision.json'))
    groups=absence_contract(raw(q,str(folder/'absence.json')));pid=attempt['controller_pid']
    require(len(groups)==31 and result.get('passed') is True and result.get('complete') is True and result['bytes']==19464192000 and
        result['parts']==3840 and result['full_SHA_passes']==1 and result['aggregate_CPU_can_exceed30_each_process_CPU30'] is True and
        result['artifact_path']==str(artifact) and result['producer_source']==g['source'] and
        result['producer_qualification_sha256']==result['qualification_sha256']==q['files'][g['qualification']] and
        result['original_outer_exit_status']==attempt['original_outer_exit_status']=='UNKNOWN' and
        result['known_original_join_exit']==attempt['known_original_join_exit']==-9 and result['original_failure_regraded'] is False and
        result['separate_artifact_acceptance_required'] is True and result['model_executed'] is False and result['production_changed'] is False and
        supervision['passed'] is True and supervision['error'] is None and supervision['owned_claim_released'] is True,
        'New31-group assembly closure; failed original producer is never regraded')
    require(module.original_failure(aq)==aq['original_controller_pid'],
        'Originaljoin-9/outerUNKNOWN/causeUNDETERMINED and failed bytes or qualified archive custody preserved')
    # Reuse metadata proof validation only; never rehash original part payloads.
    loader=module.proof_loader(aq,records,aq['original_controller_pid']);seen=[];child_pids=[]
    for index,(begin,end) in enumerate(module.ranges()):
        child=raw(q,str(folder/(str(index)+'.child.json')));observed=raw(q,str(folder/(str(index)+'.observed.json')))
        child_pids.append(data_child(child,observed,pid));done=raw(q,str(folder/(str(index)+'.DONE.json')))
        require(done['range']==[begin,end] and done['output_identity']==attempt['output_identity'] and
            [row['index'] for row in done['parts']]==list(range(begin,end)) and child['mode']==index,
            'Every exact128-matrix disjoint copy DONE')
        require(child['wait4_usage'] is not None,'Actual captured copy child usage')
        for row in done['parts']:
            n=row['index'];proof,_,_=loader(n)
            require(row['record']==records[n] and row['sha256']==proof['sha256'] and
                row['source_fingerprint']==fingerprint(Q/'iq3s-bulk-v1/conversion-FIRST/parts'/('%04d.iq3s'%n)),
                'Exact original matrix record/SHA and stable source; qualified copy source checks output readback before DONE')
            seen.append(n)
    require(seen==list(range(3840)),'Exact ordered3840 coverage, no omitted/duplicate copied interval')
    child=raw(q,str(folder/'finalize.child.json'));observed=raw(q,str(folder/'finalize.observed.json'))
    final_pid=data_child(child,observed,pid);done=raw(q,str(folder/'finalize.DONE.json'))
    require(child['mode']=='finalize' and child['wait4_usage'] is not None and all(result.get(k)==v for k,v in done.items()) and
        done['source_inode']==attempt['output_identity'] and set(child_pids+[final_pid])==groups,
        'Exact finalizer/full normal SHA and all31 actual groups')
    hash_hops(done['bounded_hash_hops'],19464192000,final_pid,pid)
    outer_exit_contract(q,g,pid,Path(g['source']))
    snap=snapshot(q,g,g['result']);require(set(snap['files'])=={str(artifact)} and
        snap['files'][str(artifact)]['fingerprint']==result['fingerprint'] and
        snap['files'][str(artifact)]['published_inode']==attempt['output_identity'] and
        result['fingerprint'][2]==19464192000,'Exact currently published new-builder artifact inode/size')
    return snap,{str(artifact):result['sha256']}


def native_group(q,g,context):
    payload,pq,plan,owner,oq=context;folder=Q/'native-payload-v2/native-FIRST';owner_folder=Q/'native-owner-v2/native-FIRST'
    require(g['result']==str(folder/'result.json') and g['artifact']==str(folder/'native.cpu'),'Exact native payload output')
    result=raw(q,g['result']);done=raw(q,str(folder/'FINAL-DONE.json'));attempt=raw(q,str(folder/'attempt.json'))
    child=raw(q,str(folder/'finalize.child.json'));observed=raw(q,str(folder/'finalize.observed.json'))
    pid=data_child(child,observed,attempt['controller_pid']);groups=absence_contract(raw(q,str(folder/'absence.json')))
    supervision=raw(q,str(folder/'supervision.json'));outer=raw(q,str(owner_folder/'supervision.json'))
    owner_result=raw(q,str(owner_folder/'result.json'));owner_attempt=raw(q,str(owner_folder/'attempt.json'))
    owner_groups=absence_contract(raw(q,str(owner_folder/'absence.json')))
    require(pid in groups and len(groups)==1871 and groups==owner_groups and result.get('passed') is True and
            result['artifact_path']==g['artifact'] and
            all(result.get(k)==v for k,v in done.items()) and done.get('complete') is True and
            done['bytes']==35157299200 and done['original_native_experts']==1870 and done['roles_per_expert']==3 and
            done['no_lowbit_upconversion'] is True and done['model_executed'] is False and
            supervision.get('passed') is True and supervision.get('error') is None and
            supervision.get('CPU_claim_owned_by_outer_controller') is True and
            owner_attempt['controller_pid']==attempt['controller_pid'] and outer.get('owned_claim_released') is True and
            outer.get('passed') is True and outer.get('error') is None and owner_result.get('passed') is True and owner_result['stage']=='native' and
            owner_result['result']==done and owner_result['qualification_sha256']==q['files'][g['owner_qualification']] and
            owner_result['model_executed'] is False and owner_result['production_changed'] is False,
            'Actual native final fullSHA/all3roles and outer CPU closure')
    payload.completion_contract(plan,folder)  # actual1870 DONE, full3role records/codec0/observed children
    actual_ids={pid}
    for index in range(1870):
        part=raw(q,str(folder/('%04d.DONE.json'%index)));unit=raw(q,str(folder/('%04d.child.json'%index)))
        observed_worker=raw(q,str(folder/('%04d.observed.json'%index)))
        payload.actual_limits(observed_worker,unit['pid'],attempt['controller_pid'])
        actual_ids.add(unit['pid'])
        require(len(part['roles'])==3 and all(r['record']==plan['records'][index*3+j] and
            re.fullmatch('[0-9a-f]{64}',r['sha256']) for j,r in enumerate(part['roles'])),
            'Actual all-three-role original-native source-map coverage')
    require(actual_ids==groups and done['source_map_sha256']==plan['source_map_sha256'] and
        done['plan_sha256']==pq['plan']['sha256'] and done['source_receipt_sha256']==pq['source_receipt']['sha256'] and
        done['aggregate_CPU_can_exceed30_each_process_CPU30'] is True,'Exact native identities/map/source verification chain')
    hash_hops(done['bounded_hash_hops'],35157299200,pid,attempt['controller_pid'])
    outer_exit_contract(q,g,attempt['controller_pid'],Path(g['owner_source']))
    snap=snapshot(q,g,g['result']);require(set(snap['files'])=={g['artifact']} and
        snap['files'][g['artifact']]['published_inode']==attempt['output_identity'],'Native published same inode/size as actual writers')
    return snap,{g['artifact']:done['artifact_sha256']}


def selected_inventory(metadata):
    names=['DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XS-%05d-of-00004.gguf'%i for i in range(1,5)]
    names+=['../shared/DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf','../shared/dspark-DeepSeek-V4.1-Flash-1017-Q8_0.gguf',
            '../../reliability-optimization-20261025/vision-assets-1017/vision.bin']
    require(metadata['pack_files']==names and metadata['model_dir']==str(R/'models/ista-iq2-xs') and
            metadata['pack']==str(E/'pack-native-vision-v1') and metadata['storage_geometry']['layers']==43 and
            metadata['storage_geometry']['experts_per_layer_profile']==384,'Exact selected seven-file source inventory/topology')
    return [os.path.normpath(str(Path(metadata['model_dir'])/n)) for n in names]


def public_READY(rawbytes):
    text='';finish=None;done=False
    for line in rawbytes.decode().splitlines():
        if not line.startswith('data:'):continue
        value=line[5:].strip()
        if value=='[DONE]':require(not done,'One actual public DONE');done=True;continue
        require(not done,'No data after public DONE');event=json.loads(value)
        require('error' not in event,'No public READY error')
        for c in event.get('choices',[]):
            text+=c.get('delta',{}).get('content') or '';finish=c.get('finish_reason') or finish
    require(done and finish=='stop' and text.strip()=='READY','Actual public READY-stop-DONE raw SSE')


def selected_group(q,g):
    release=raw(q,g['release']);require(q['files'][g['release']]==RELEASE and
        release['files'].get(str(D/'bin/maya-ds4'))==NATIVE92,'Actual qualified selected92 release source/binary map')
    restoration=raw(q,g['restoration']);verified=restoration['verified'];identity=verified['selected_identity']
    public=verified['public'];binding=identity['start_binding']
    require(restoration.get('status') in ('S2_PLACEMENT_SELECTED4096_RESTORED','S2_ESSENTIAL_SELECTED4096_RESTORED') and
        restoration.get('window')==g['window'] and
        type(binding) is dict and set(binding)=={'invocation','main_pid','native_pid','native_start_ticks'} and
        re.fullmatch('[0-9a-f]{32}',binding['invocation']) and
        all(type(binding[k]) is int and binding[k]>1 for k in ('main_pid','native_pid','native_start_ticks')) and
        identity.get('native_pid')==binding['native_pid'] and
        verified.get('passed') is True and identity.get('native_sha256')==NATIVE92 and
        identity.get('config_sha256')==CONFIG43 and identity.get('context')==1048576 and identity.get('output_default')==262144 and
        identity.get('prefill_chunk')==4096 and identity.get('Q8')==[1,1] and identity.get('DSpark') is True and
        identity.get('images') is True and identity.get('TP')==1 and identity.get('all_CPU_experts_RAM') is True and
        binding==q['selected_binding'] and public.get('unauthenticated_models')==401 and public.get('authenticated_models')==200 and
        public.get('content')=='READY' and public.get('finish')=='stop' and public.get('SSE_done') is True and
        public.get('known_answer_passed') is True,'Actual selected1M/262144/native92/c43 restoration, not generic passed')
    closed=raw(q,g['window']);last=json.loads(pinned(q,g['window_telemetry']).read_text().splitlines()[-1])
    require(closed.get('test_returncode')==0 and closed.get('maintenance_held') is True and
        closed.get('maintenance_resume_allowed') is True and closed.get('maintenance_root_window')=='20261025T032914Z.json' and
        last.get('kernel_capture_returncode')==0 and last.get('kernel_fault_lines')==[],'Raw original private window clean0 before selected restoration')
    public_READY(pinned(q,g['public_sse']).read_bytes())
    require(q['files'][g['pack_state']]==PACK_STATE_A,'Exact original selected seven-file metadata/topology source')
    metadata=raw(q,g['pack_state']);names=selected_inventory(metadata)
    pack=Path(metadata['pack'])
    require(q['files'].get(str(pack/'ds4.txt'))==metadata['ds4_txt_sha256'] and
            q['files'].get(str(pack/'tensors.txt'))==metadata['tensors_txt_sha256'],'Exact current selected pack metadata')
    snap=snapshot(q,g,g['restoration']);require(snap.get('selected_binding')==binding and set(snap['files'])==set(names),
        'Fresh restoration-bound selected seven-file captured fingerprints')
    # No new SHA claim for these already qualified, still identical source files.
    return snap,{name:None for name in names}


def validate_groups(q, *, source_check=source_qualification):
    assets,chains=q['large_verified'],q['artifact_chains'];answer={}
    for key,g in chains.items():
        require(g['raw_paths'] and len(set(g['raw_paths']))==len(g['raw_paths']),'Exact nonduplicate raw group')
        if g['kind']=='base-acquisition-publication':
            needed=[g[n] for n in ('source','qualification','manifest','terminal','attempt','outer_exit_observer',
                                   'constructor','publication_snapshot')]
            root=Q/'candidate-pack-v1'
            needed += [str(root/n) for n in ('construct_pack.py','ROOT_SOURCE_REVIEW.json','CPU-FIRST-mac.json',
                'CPU-FIRST-ubuntu.json','child-FIRST-mac.json','child-FIRST-ubuntu.json')]
        elif g['kind']=='selected-publication':
            needed=[g[n] for n in ('release','restoration','window','window_telemetry','public_sse','pack_state','publication_snapshot')]
        elif g['kind']=='bounded-overlay-join':
            folder=Q/'iq3s-assembly-v3/assembly-FIRST'
            needed=[g[n] for n in ('source','qualification','result','controller_start','controller_exit','publication_snapshot')]
            needed+=[str(folder/n) for n in ('attempt.json','supervision.json','absence.json','finalize.child.json',
                                             'finalize.observed.json','finalize.DONE.json')]
            needed+=[str(folder/(str(i)+suffix)) for i in range(30) for suffix in ('.child.json','.observed.json','.DONE.json')]
        elif g['kind']=='bounded-native-finalize':
            folder=Q/'native-payload-v2/native-FIRST';owner_folder=Q/'native-owner-v2/native-FIRST'
            needed=[g[n] for n in ('source','qualification','owner_source','owner_qualification','result',
                                   'controller_start','controller_exit','publication_snapshot')]
            needed+=[str(folder/n) for n in ('FINAL-DONE.json','attempt.json','finalize.child.json',
                                            'finalize.observed.json','absence.json','supervision.json')]
            needed+=[str(folder/('%04d'%i+suffix)) for i in range(1870) for suffix in ('.child.json','.observed.json','.DONE.json')]
            needed+=[str(owner_folder/n) for n in ('attempt.json','supervision.json','absence.json','result.json')]
        else:raise ValueError('Only four explicit publication chain kinds')
        require(set(needed)<=set(g['raw_paths']),'Missing exact raw publication/build group member')
        for p in g['raw_paths']:pinned(q,p)
        if g['kind']=='selected-publication':snap,hashes=selected_group(q,g)
        else:
            context=source_check(q,g)
            if g['kind']=='base-acquisition-publication':snap,hashes=base_group(q,g)
            elif g['kind']=='bounded-overlay-join':snap,hashes=overlay_group(q,g,context)
            elif g['kind']=='bounded-native-finalize':snap,hashes=native_group(q,g,context)
            else:raise ValueError('Only four explicit publication chain kinds')
        for name,h in hashes.items():
            require(name not in answer and name in assets and assets[name]['chain']==key and
                assets[name]['sha256']==h and assets[name]['fingerprint']==snap['files'][name]['fingerprint'] and
                (h is None if g['kind']=='selected-publication' else type(h) is str and re.fullmatch('[0-9a-f]{64}',h)),
                'Exact source-chain SHA/fingerprint; unknown allowed only selected publication')
            answer[name]={'chain':key,'sha256':h,'fingerprint':assets[name]['fingerprint'],
                          'raw_paths':g['raw_paths'],'owned_writer_lock_free':True}
    require(set(answer)==set(assets),'No omitted or extra published artifact')
    return answer


def own_qualification(q):
    contract=q['artifact_chain_validator'];path=Path(contract['qualification_path'])
    require(path==HERE/'qualification.json','Exact independently qualified publication helper')
    proof=raw(q,path);review=raw(q,proof['source_review'])
    sources={n:sha(HERE/n) for n in SOURCES}
    require(proof['sources']==review['source_map']==sources and review['entire_source_tests_driver_manually_read'] is True and
        proof['test_ids']==review['test_ids'] and len(set(proof['test_ids']))==len(proof['test_ids'])>0 and
        proof['inputs']==review['input_map']=={'qualified_supervisor':DRIVER_SHA,'captured_launch':LAUNCH_SHA} and set(proof['CPU'])=={'darwin','linux'},
        'Actual own manual/source/exact-ID both-host qualification')
    require(all(q['files'].get(str(HERE/n))==h for n,h in sources.items()),'Actual helper sources pinned in caller')
    require(q['files'].get(str(DC/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'))==DRIVER_SHA,
        'Exact qualified CPU supervisor source pinned')
    for platform,chain in proof['CPU'].items():
        receipt=raw(q,chain['receipt']);child=raw(q,chain['child']);pinned(q,chain['log'])
        cpu_contract(receipt,child,review,platform)


def cpu_contract(proof,child,review,platform):
    observed=proof['observed']
    require(proof.get('passed') is True and proof.get('returncode')==0 and proof.get('failures')==proof.get('errors')==0 and
        proof.get('source_map')==review['source_map'] and proof.get('input_map')==review['input_map'] and
        proof.get('test_ids')==review['test_ids'] and proof.get('controls')==len(review['test_ids']) and proof.get('isolated') is True and
        child.get('pid')==observed['pid']==observed['pgid'] and observed['ppid']==proof['supervisor_pid'] and
        child.get('returncode')==0 and child.get('error') is None and child.get('cleanup')==[] and 0<=child['elapsed_seconds']<=90 and
        observed['platform']==platform and observed['cpu']==[30,30] and observed['nice']==15 and
        observed['as']==([512*2**20]*2 if platform=='linux' else None) and observed['environment']==ENV and
        observed['dont_write_bytecode'] is True,'Complete actual bounded source-qualified physical CPU proof')


def validate_publications(q):
    own_qualification(q)
    return validate_groups(q)
