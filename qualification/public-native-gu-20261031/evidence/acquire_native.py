"""Two complete, checksum-pinned official shards for a new public hybrid.

Acquisition only. The qualified transport is imported privately, with its own
source/CPU custody checked before its repository/rate constants are selected.
No model, pack, service, native build or GPU operation exists here.
"""
import argparse
import ast
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import time

HERE=Path(__file__).resolve().parent
E=HERE.parents[1]
DC=HERE.parent
TRANSPORT=DC/'maya-s-comparison-v1/acquisition-authorized-v2'
TRANSPORT_SHA='6a399f4eec7b9cb23b7ff7aa03d60deb490787825ae92e43ccde8d40065885b5'
TRANSPORT_Q='3f89fe089d629bb65b5c517908ae76a731b9020fb0a8cb02a1b1ef58472596b0'
MANIFEST_SHA='8fea071855665f114972f3b9581736af745fa4653e35043af275a71be88bff9a'
UNSLOTH=DC/'unsloth-v31-iq2xxs-download-v1'
UNSLOTH_MANIFEST_SHA='4fb4c0ff9c0b55f46afa15c2cbc84ee09372c85944efafb63e36a5ca6e73c73c'
REPO='deepseek-ai/DeepSeek-V4.1-Flash-1017'
REVISION='1bae0e1088993b9b82de08f59de5be5a34e42170'
TOTAL=14779522736
OTHER_TOTAL=300475464795
OVERLAY_BYTES=9625927680
FLOOR=144*2**30
CUSHION=256*2**20
RATE=64*2**20
WALL=21600
SOURCES=('acquire_native.py','test_acquire_native.py','run_acquire_cpu.py')

def input_paths():
    return {'manifest':HERE/'NATIVE_GU_SOURCE_MANIFEST.json',
            'transport':TRANSPORT/'acquire.py','transport-qualification':TRANSPORT/'acquisition-qualification.json',
            'other-manifest':UNSLOTH/'ASSET_MANIFEST.json',
            'selected-runtime':DC/'iq2s-persistent-v1/model-v1/iq2s_model_runtime.py',
            'selected-config':DC/'iq2s-persistent-v1/model-v1/iq2s_config.py',
            'CPU-supervisor':DC/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'}

def require(ok,why):
    if not ok:raise ValueError(why)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def manifest():
    p=HERE/'NATIVE_GU_SOURCE_MANIFEST.json'
    require(sha(p)==MANIFEST_SHA,'Frozen original-checkpoint shard manifest')
    m=json.loads(p.read_text())
    require(m['repo']==REPO and m['revision']==REVISION and m['total_bytes']==TOTAL
            and [r['path'] for r in m['files']]==['model-00028-of-00048.safetensors','model-00029-of-00048.safetensors']
            and sum(r['size'] for r in m['files'])==TOTAL,'Exact two complete source shards')
    require(m['output_overlay_bytes']==OVERLAY_BYTES and m['context_total']==1048576
            and m['output_allowance']==262144 and m['exact_private_S2'] is False,'Public hybrid scope/policy')
    return m

def transport():
    require(sha(TRANSPORT/'acquire.py')==TRANSPORT_SHA,'Qualified transfer changed')
    spec=importlib.util.spec_from_file_location('_public_hybrid_transfer',TRANSPORT/'acquire.py')
    a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
    a.qualification(TRANSPORT/'acquisition-qualification.json',TRANSPORT_Q)
    a.REPO=REPO;a.REVISION=REVISION;a.RATE=RATE;a.RESERVE=FLOOR
    return a

def retained_flat(root,specs,a):
    if not root.exists():return 0
    a.real_directory(root);allowed={r['path']:r for r in specs};total=0
    for leaf in root.iterdir():
        name=leaf.name[:-8] if leaf.name.endswith('.partial') else leaf.name
        require(name in allowed,'Foreign retained native source asset')
        a.safe_file(leaf);require(leaf.stat().st_size<=allowed[name]['size'],'Oversized retained native source')
        other=root/(name if leaf.name.endswith('.partial') else name+'.partial')
        require(not other.exists() and not other.is_symlink(),'Ambiguous native publication')
        total+=leaf.stat().st_size
    return total

def concurrent_other(root,specs):
    """Budget only: tolerate the other downloader's exclusive link/unlink publish."""
    total=0
    for r in specs:
        final=root/r['path'];partial=final.with_name(final.name+'.partial');rows=[]
        require(not any(p.is_symlink() for p in (final.parent,*final.parent.parents)),'Other asset parent alias')
        for p in (final,partial):
            try:s=p.lstat()
            except FileNotFoundError:continue
            require(stat.S_ISREG(s.st_mode) and s.st_size<=r['size'] and s.st_nlink in (1,2),'Other retained leaf')
            rows.append(s)
        if len(rows)==2:require((rows[0].st_dev,rows[0].st_ino,rows[0].st_size)==(rows[1].st_dev,rows[1].st_ino,rows[1].st_size),'Other ambiguous publication')
        total+=max((s.st_size for s in rows),default=0)
    return total

def budget(free,own,other):
    require(type(free) is type(own) is type(other) is int and free>=0 and 0<=own<=TOTAL and 0<=other<=OTHER_TOTAL,'Typed combined budget')
    needed=FLOOR+CUSHION+OVERLAY_BYTES+(TOTAL-own)+(OTHER_TOTAL-other)
    require(free>=needed,'Reserve both remaining downloads, future overlay and root/cache/log floor')
    return {'free':free,'required':needed,'own_remaining':TOTAL-own,'other_remaining':OTHER_TOTAL-other,'future_overlay':OVERLAY_BYTES,'floor':FLOOR}

class Gate:
    def __init__(self,a,m):
        self.a,self.m=a,m;self.selected=a.SelectedGate()
        p=UNSLOTH/'ASSET_MANIFEST.json';require(sha(p)==UNSLOTH_MANIFEST_SHA,'Other frozen inventory')
        self.other=json.loads(p.read_text())['files'];self.last_budget=None;self()
    def __call__(self):
        self.selected()
        p=HERE/'pause-for-comparison.json';self.a.safe_file(p)
        if p.exists():
            d=json.loads(p.read_text());require(d.get('manifest_sha256')==MANIFEST_SHA and d.get('pause_before_private_phase') is True,'Exact owned pause')
            raise self.a.Deferred('Paused for separately admitted private work; all source bytes retained')
        self.last_budget=budget(shutil.disk_usage(HERE).free,retained_flat(HERE/'assets',self.m['files'],self.a),concurrent_other(UNSLOTH/'assets',self.other))

def qualified(pin):
    p=HERE/'acquire-qualification.json';require(sha(p)==pin,'Exact acquisition qualification')
    q=json.loads(p.read_text());require(q['root_source_read'] is True and q['sol_source_read'] is True,'Manual source/test review')
    for name,digest in q['files'].items():require(sha(name)==digest,'Immutable acquisition input changed: '+name)
    source={n:sha(HERE/n) for n in SOURCES}
    tree=ast.parse((HERE/'test_acquire_native.py').read_text())
    ids=sorted('test_acquire_native.'+c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'))
    require(source==q['source_sha256'] and ids==q['test_ids'] and ids,'Exact nonempty source/IDs')
    inputs={n:sha(p) for n,p in input_paths().items()}
    require(inputs==q['input_sha256'] and all(q['files'].get(str(input_paths()[n]))==v for n,v in inputs.items()),'Actual input map membership')
    review=HERE/'ACQUIRE_SOURCE_ROOT_REVIEW.json';r=json.loads(review.read_text())
    require(q['files'].get(str(review))==sha(review) and r['root_source_read'] is True and r['sol_source_read'] is True and r['source_sha256']==source and r['input_sha256']==inputs and r['test_ids']==ids,'Source-bound manual review')
    for host in ('darwin','linux'):
        d=HERE/('ACQUIRE-CPU-FIRST-'+host);r=json.loads((d/'receipt.json').read_text());c=json.loads((d/'child.json').read_text())
        require(r['passed'] is True and r['source_sha256']==source and r['input_sha256']==q['input_sha256'] and r['test_ids']==ids and r['controls']==len(ids),'Matching physical CPU proof')
        require(c['returncode']==0 and type(c['returncode']) is int and c['error'] is None and c['cleanup']==[] and 0<c['elapsed_seconds']<90,'Bounded clean CPU exit')
        v=r['observed'];require(v['platform']==host and v['cpu']==[30,30] and v['as']==([512*2**20]*2 if host=='linux' else None) and v['nice']==15 and v['pgid']==v['pid']==c['pid'] and v['dont_write_bytecode'] is True,'Actual child-only resource bounds')
        require(v['environment']=={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'},'CPU environment')
        require(all(q['files'].get(str(d/n))==sha(d/n) for n in ('receipt.json','child.json','child.log')),'All raw CPU proof pins')
    require(all(q['files'].get(str(HERE/n))==v for n,v in source.items()),'Executing sources pinned')
    return q

def physical_namespace():
    return HERE==Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/s2-public-hybrid-v1')

def main(pin):
    q=qualified(pin);m=manifest();a=transport();g=Gate(a,m)
    require(physical_namespace() and g.selected.host.start_binding==q['selected_binding'],'Physical namespace/current selected owner')
    a.safe_file(HERE/'download.lock')
    with (HERE/'download.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);g();root=HERE/'assets'
        if not root.exists():root.mkdir()
        a.real_directory(root)
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        attempt=HERE/('acquire-attempt-'+stamp+'.json');require(not attempt.exists(),'Fresh acquisition attempt')
        state={'utc':stamp,'pid':os.getpid(),'status':'PINNED_NATIVE_SOURCES_RUNNING','files':[],'qualification_sha256':pin,'manifest_sha256':MANIFEST_SHA,'budget':g.last_budget,'model_service_GPU_actions':0,'rate':RATE,'wall':WALL};a.emit(attempt,state);a.emit(HERE/'ACQUIRE_STATE.json',state);rc=0
        try:
            deadline=time.monotonic()+WALL
            for r in m['files']:
                state['files'].append({'path':r['path'],**a.acquire_file(r,root,g,deadline=deadline)});a.emit(HERE/'ACQUIRE_STATE.json',state)
            state['status']='BOTH_COMPLETE_OFFICIAL_SHARDS_SHA256_VERIFIED_NO_MODEL_RUN'
        except (Exception,KeyboardInterrupt) as exc:
            state.update(status='DEFERRED_PARTIALS_RETAINED' if isinstance(exc,a.Deferred) else 'ACQUISITION_HOLD',reason=str(exc) if isinstance(exc,(a.Deferred,ValueError)) else 'Transport/OS failure; no automatic retry',error_type=type(exc).__name__);rc=75 if isinstance(exc,a.Deferred) else 1
        state.update(returncode=rc,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());a.emit(attempt,state);a.emit(HERE/'ACQUIRE_STATE.json',state);return rc

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--qualification-pin',required=True);args=p.parse_args();raise SystemExit(main(args.qualification_pin))
