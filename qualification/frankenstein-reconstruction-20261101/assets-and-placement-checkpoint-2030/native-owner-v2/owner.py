"""Two bounded CPU stages for actual selected original-expert materialization.

The source-verification stage freezes complete SHA/fingerprint receipts. A
separately pinned native stage composes the existing CPU lease and new payload
materializer. Neither stage creates a GPU owner or touches a service.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
Q = HERE.parent
E = Q.parents[1]
ROOT = Q / 'iq3s-source-acquisition-v1/assets/original'
BUILD = Q / 'placement-native-build-v1/build_current.py'
BUILD_SHA = '60022606724b5b447056c0d54e0ea8c0f163359673b640cea0cd659abce26916'
BULK = Q / 'iq3s-bulk-v1/bulk.py'
BULK_SHA = '1a71e6f1d13d81d326b99be6613b19ed1dc898ac52259fdcf870ca0550ec75fb'
SOURCES = ('owner.py', 'test_owner.py', 'run_cpu.py')
ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
       'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1',
       'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(2**20), b''): h.update(data)
    return h.hexdigest()


def emit(path, row):
    with Path(path).open('x') as f: json.dump(row, f, indent=2, allow_nan=False); f.write('\n')


def exact(name, path, pin):
    require(path.resolve() == path and not path.is_symlink() and sha(path) == pin, 'Exact qualified dependency')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def source_map(): return {n: sha(HERE / n) for n in SOURCES}


def cpu_contract(proofs, sources, ids):
    require(set(proofs) == {'darwin', 'linux'} and ids and len(ids) == len(set(ids)), 'Both exact physical CPU groups')
    inputs = proofs['darwin']['input_sha256']
    for platform, proof in proofs.items():
        require(proof.get('passed') is True and proof.get('returncode') == 0 and proof.get('controls') == len(ids)
                and proof.get('test_ids') == ids and proof.get('source_sha256') == sources and
                proof.get('input_sha256') == inputs and proof.get('failures') == proof.get('errors') == 0,
                'Complete matching new source/input/IDs')
        row = proof['observed']
        require(row['platform'] == platform and row['cpu'] == [30,30] and row['nice'] == 15 and
                row['as'] == ([512*2**20]*2 if platform == 'linux' else None) and
                row['pid'] == row['pgid'] and row['dont_write_bytecode'] is True and
                all(row['environment'].get(k) == v for k,v in ENV.items() if k not in ('PATH','LANG','LC_ALL')),
                'Actual CPU child identity/resources/environment')


def qualified(stage, pin):
    require(stage in ('verify','native'), 'Two fixed CPU stages only')
    path = HERE / (stage + '-qualification.json'); require(sha(path) == pin, 'Exact stage qualification')
    q = json.loads(path.read_text())
    require(q['stage'] == stage and q['selected_binding'] and q['entire_source_tests_driver_manually_read'] is True and
            q['source_sha256'] == source_map() and q['source_root'] == str(ROOT), 'Actual new CPU source/binding')
    proofs = {p: json.loads(Path(q['CPU_paths'][p]).read_text()) for p in ('darwin','linux')}
    cpu_contract(proofs, source_map(), q['test_ids'])
    for platform,proof in proofs.items():
        for field in ('CPU_paths','CPU_child_paths'):
            path=q[field][platform]
            require(q['files'].get(path)==sha(path),'Pinned raw physical CPU proof and supervisor closure')
        child=json.loads(Path(q['CPU_child_paths'][platform]).read_text())
        require(child['pid']==proof['observed']['pid'] and type(child['returncode']) is int and child['returncode']==0
                and child['error'] is None and child['cleanup']==[] and 0<=child['elapsed_seconds']<90,
                'Actual physical CPU child exit and owned cleanup')
    for name,pin in q['files'].items():
        path = Path(name)
        require(not path.is_relative_to(ROOT) and path.resolve() == path and not path.is_symlink() and sha(path) == pin,
                'Pinned metadata/source input; originals use bounded streaming verification')
    require(q['files'].get(str(BUILD)) == BUILD_SHA and q['files'].get(str(BULK)) == BULK_SHA and
            all(q['files'].get(str(HERE/n)) == pin for n,pin in source_map().items()), 'Required custody/source membership')
    ppath = Q / 'native-payload-v2/payload.py'
    require(q['files'].get(str(ppath)) == q['payload_source_sha256'], 'Qualified native component source')
    require(proofs['darwin']['input_sha256']=={
        'payload':q['payload_source_sha256'],'build_custody':BUILD_SHA,'bulk_verifier':BULK_SHA,
        'shared_driver':'3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71',
        'bounded_hash_helper':HASH_SHA},
        'CPU proofs cover the exact executing component/custody sources')
    payload = exact('native_owner_payload', ppath, q['payload_source_sha256'])
    plan = json.loads(Path(q['plan_path']).read_text()); payload.validate_plan(plan)
    require(q['files'].get(q['plan_path']) == q['plan_sha256'], 'Exact actual selection source map')
    terminal = json.loads((Q/'original-expert-acquisition-v2/acquisition-state.json').read_text())
    require(terminal['status'] == 'ALL_FORTY_TRUNK_EXPERT_SHARDS_VERIFIED_NO_MODEL_RUN' and terminal['returncode'] == 0,
            'Original acquisition must finish before CPU materialization')
    if stage == 'native':
        qp = Q/'native-payload-v2/qualification.json'
        require(q['files'].get(str(qp)) == q['native_qualification_sha256'], 'Pinned native component qualification')
        native_q, native_plan, _ = payload.qualification(qp, q['native_qualification_sha256'])
        require(native_plan == plan and native_q['selected_binding'] == q['selected_binding'], 'Same actual source/owner plan')
    return q, payload, plan


def clean_original_lock():
    import fcntl
    path = Q/'iq3s-source-acquisition-v1/acquisition.lock'
    require(path.is_file() and not path.is_symlink(), 'Original writer lock identity')
    with path.open('rb') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB); fcntl.flock(f,fcntl.LOCK_UN)


def verify_child(index, folder, q, plan, payload):
    resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20))
    require(sys.flags.isolated and sys.dont_write_bytecode and dict(os.environ) == ENV, 'Isolated clean source verifier')
    priority=os.getpriority(os.PRIO_PROCESS,0);require(priority<=15,'Child priority');os.nice(15-priority)
    names=sorted(plan['source_headers']);require(type(index) is int and 0<=index<len(names),'One actual original source')
    name=names[index];bulk=exact('native_source_stream',BULK,BULK_SHA)
    row={'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgrp(),'cpu':[30,30],
         'as':[512*2**20]*2,'nice':os.getpriority(os.PRIO_PROCESS,0),'environment':dict(os.environ),
         'isolated':bool(sys.flags.isolated),'dont_write_bytecode':sys.dont_write_bytecode}
    emit(folder/'observed.json',row)
    bulk.verify_sources(ROOT,plan['source_map_sha256'],
                        {name:plan['source_headers'][name]['source_file_sha256']},folder/'source.json')
    emit(folder/'DONE.json',{'complete':True,'index':index,'source':name})


def verify_one(index, folder, q, plan, payload, registry, custody, guard, deadline):
    folder.mkdir();started=time.monotonic();proc=None
    record={'index':index,'pid':None,'returncode':None,'error':None,'cleanup':[]}
    try:
        guard();require(started<deadline-95,'Source verification remaining budget')
        command=[str(Path(sys.executable).resolve()),'-I','-B',str(HERE/'owner.py'),'--child-index',str(index),
                 '--qualification-sha256',q['_pin'],'--output',str(folder)]
        with (folder/'child.log').open('x') as log:
            label='verify-'+str(index);registry.starting(label)
            proc=subprocess.Popen(command,cwd=HERE,env=ENV,stdin=subprocess.DEVNULL,stdout=log,
                                  stderr=subprocess.STDOUT,start_new_session=True)
            registry.registered(proc,label);record['pid']=proc.pid
            while proc.poll() is None:
                guard();require(time.monotonic()<min(started+75,deadline-20),'Bounded source child wall')
                try:proc.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
            require(proc.returncode==0,'Source verifier failed; no retry')
            actual=json.loads((folder/'observed.json').read_text())
            require(actual=={'pid':proc.pid,'ppid':os.getpid(),'pgid':proc.pid,'cpu':[30,30],
                 'as':[512*2**20]*2,'nice':15,'environment':ENV,'isolated':True,'dont_write_bytecode':True},
                 'Actual bounded source verifier identity')
            name=sorted(plan['source_headers'])[index]
            require(json.loads((folder/'DONE.json').read_text())=={'complete':True,'index':index,'source':name},'Actual source DONE')
    except BaseException as exc:record['error']=repr(exc)
    finally:
        if proc is not None:
            try:custody.cleanup(proc,min(started+90,deadline))
            except BaseException as exc:record['cleanup'].append(repr(exc));registry.cleanup_failed('verify-'+str(index),exc)
            record['returncode']=proc.poll()
        emit(folder/'child.json',record)
    require(record['returncode']==0 and record['error'] is None and not record['cleanup'],'Source verification HOLD')
    return json.loads((folder/'source.json').read_text())


def merge_sources(plan, parts):
    rows={}
    for part in parts:
        require(part['root']==str(ROOT) and part['plan_sha256']==plan['source_map_sha256'] and len(part['files'])==1,
                'Exact one-source verification part')
        for name,row in part['files'].items():
            require(name not in rows and name in plan['source_headers'] and row['full_sha_verified'] is True and
                    row['sha256']==plan['source_headers'][name]['source_file_sha256'],'Exact complete original SHA coverage')
            rows[name]=row
    require(set(rows)==set(plan['source_headers']),'All used original sources verified')
    return {'root':str(ROOT),'official_revision':plan['official_revision'],
            'source_map_sha256':plan['source_map_sha256'],'files':rows}


def release(cas, path, record, absence):
    require(absence.get('passed') is True,'All owned descendants must close before claim release')
    raw=path.read_bytes();state=json.loads(raw)
    require(state.get('active_cpu_build')==record,'Foreign CPU claim untouched')
    cas.cas_state(path,raw,dict(state,active_cpu_build=False))


def main(stage,pin):
    require(sys.platform=='linux' and sys.flags.isolated and sys.dont_write_bytecode and
            str(HERE)=='/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/s2-reconstruction-v1/native-owner-v2',
            'Exact isolated physical Ubuntu CPU owner')
    b=exact('native_payload_build_custody',BUILD,BUILD_SHA)
    early=b.exact('build_early');binding=early.early_guard();b.strict_idle()
    q,payload,plan=qualified(stage,pin);q['_pin']=pin;clean_original_lock()
    require(binding==q['selected_binding'],'Fresh selected owner binding')
    custody,support=b.exact('build_owner'),b.exact('build_support');healthy=b.exact('build_healthy_work')
    _,runtime,_,host,actual=support.support();require(actual==binding,'Actual selected owner')
    gpu=custody.observe_gpu_lease(host,binding);cas=custody.load_cas()
    record={'mode':'s2-original-native-'+stage+'-FIRST','controller_pid':os.getpid(),
            'controller_start_ticks':custody.process_ticks(os.getpid()),'nonce':uuid.uuid4().hex,
            'start_binding':binding,'qualification_sha256':pin}
    out=HERE/(stage+'-FIRST');require(not out.exists() and not out.is_symlink(),'Fresh stage; no replay')
    deadline=time.monotonic()+7200
    with custody.CPULease(E/'cpu-build.lock') as lease:
        claimed=False;cpu_started=False;primary=None;result=None
        def guard():
            lease.check();require(time.monotonic()<deadline-15,'CPU owner deadline')
            state=b.coordination_guard(support,healthy,runtime,host,binding,record if claimed else None,cpu_started=cpu_started)
            early.early_guard(record if claimed else None);b.cpu_headroom(Path('/proc/meminfo').read_text())
            custody.observe_gpu_lease(host,binding,gpu['identity'])
            require(sha(HERE/(stage+'-qualification.json'))==pin,'Stage qualification drift')
            require(__import__('shutil').disk_usage(HERE).free>=132*2**30,'Root132 maintained')
            return state
        state=guard();out.mkdir();registry=custody.OwnedChildren(out/'owned-children.jsonl');emit(out/'attempt.json',record)
        try:
            raw=(E/'STATE.json').read_bytes();require(json.loads(raw)==state and not state.get('active_cpu_build'),'CPU claim race')
            cas.cas_state(E/'STATE.json',raw,dict(state,active_cpu_build=record));claimed=True
            # Ordinary healthy inference can coexist only after this CPU lease
            # is held and the actual qualified child is about to be registered.
            cpu_started=True
            if stage=='verify':
                parts=[verify_one(i,out/('%02d'%i),q,plan,payload,registry,custody,guard,deadline)
                       for i in range(len(plan['source_headers']))]
                result=merge_sources(plan,parts);payload.source_contract(plan,result,ROOT)
                emit(out/'original-sources.json',result)
            else:
                result=payload.materialize(Q/'native-payload-v2/qualification.json',q['native_qualification_sha256'],
                      owner=custody,registry=registry,guard=guard,wall=max(120,int(deadline-time.monotonic()-20)))
            guard()
        except BaseException as exc:primary=exc
        finally:
            try:
                for name,proc,_ in list(registry.children):
                    try:custody.cleanup(proc,deadline)
                    except BaseException as exc:registry.cleanup_failed(name,exc)
                absence=registry.absence();emit(out/'absence.json',absence)
                if claimed:release(cas,E/'STATE.json',record,absence);claimed=False
                guard()
            except BaseException as exc:
                if primary is None:primary=exc
                else:primary.add_note('Native CPU custody closure: '+repr(exc))
            emit(out/'supervision.json',{'passed':primary is None,'owned_claim_released':not claimed,
                                        'error':repr(primary) if primary else None})
        if primary is not None:raise primary
        emit(out/'result.json',{'passed':True,'stage':stage,'qualification_sha256':pin,
                               'model_executed':False,'production_changed':False,'result':result})


HASH_HELPER=Q/'bounded-sha256-v1/fork_hash.py'
HASH_SHA='26ab3c1bb4330e1e933a11d739806f7cd2db8a890ac100d208f52a9d67b0cec2'


def bounded_hash(path):
    # Integration smoke uses only a tiny source in the already bounded child.
    # Actual native finalization additionally checks its full helper qualification.
    return exact('owner_bounded_hash_smoke',HASH_HELPER,HASH_SHA).file_sha256(Path(path),hop_bytes=11)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['verify','native'])
    parser.add_argument('--qualification-sha256',required=True);parser.add_argument('--child-index',type=int)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.child_index is not None:
        # Bounds precede metadata parsing/imports, and source payload bytes are
        # streamed only after exact parent qualification/plan checks.
        resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20))
        q,payload,plan=qualified('verify',args.qualification_sha256)
        require(args.output==HERE/'verify-FIRST'/('%02d'%args.child_index),'Exact owned source child output')
        verify_child(args.child_index,args.output,q,plan,payload)
    else:main(args.stage,args.qualification_sha256)
