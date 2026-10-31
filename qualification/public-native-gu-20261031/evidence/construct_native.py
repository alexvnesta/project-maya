"""One fresh lossless original-MXFP4 overlay and independently named Maya pack.

Offline long I/O only. No inference, service, GPU or inference-engine build.
All partials/failed attempts retained; no resume, retry or overwrite.
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
import resource
import signal
import stat
import struct
import subprocess
import sys
import time

import acquire_native as a
import hybrid_plan_r2 as h

HERE=Path(__file__).resolve().parent
OUT=HERE/'native-gu-FIRST'
PACK=HERE.parent/'maya-s-comparison-v1/pack-v1/pack-FIRST'
CODEC=HERE/'CODEC-CPU-FIRST-linux/mxpack'
CODEC_SHA='341ed4182032fffe9f290043e9094fab879dfda59d0ee5982f99c932d332fd14'
DRIVER=HERE.parent/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
SOURCES=('construct_native.py','test_construct_native.py','run_construct_cpu.py')
RATE=64*2**20
WALL=21600
ENV={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}

def require(ok,why):
    if not ok:raise ValueError(why)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def signature(p):
    p=Path(p);s=p.lstat()
    require(p.is_absolute() and p.resolve()==p and stat.S_ISREG(s.st_mode) and s.st_nlink==1,'One canonical regular source')
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def open_source(p):
    before=signature(p);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd);require([s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]==before,'Source open identity changed')
        return os.fdopen(fd,'rb'),before
    except BaseException:os.close(fd);raise

class Pace:
    def __init__(self,gate,deadline):self.gate=gate;self.deadline=deadline;self.started=time.monotonic();self.bytes=0
    def tick(self,count):
        require(type(count) is int and count>=0,'Nonnegative I/O count');self.bytes+=count
        self.gate();require(time.monotonic()<self.deadline,'Offline construction wall deadline')
        delay=self.started+self.bytes/RATE-time.monotonic()
        while delay>0:
            time.sleep(min(delay,1));self.gate();require(time.monotonic()<self.deadline,'Offline construction wall deadline');delay=self.started+self.bytes/RATE-time.monotonic()

def hash_stream(f,pace):
    f.seek(0);digest=hashlib.sha256();count=0
    while True:
        b=f.read(4*2**20)
        if not b:break
        digest.update(b);count+=len(b);pace.tick(len(b))
    return count,digest.hexdigest()

def exact_range(f,span):
    require(len(span)==2 and all(type(v) is int for v in span) and 0<=span[0]<span[1] and span[1]-span[0]<=h.WEIGHT_BYTES,'Bounded exact source plane')
    f.seek(span[0]);b=f.read(span[1]-span[0]);require(len(b)==span[1]-span[0],'Truncated source plane');return b

def child_limits():
    resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    if sys.platform=='linux':resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20))
    nice=os.getpriority(os.PRIO_PROCESS,0);require(nice<=15,'Inherited nice');os.nice(15-nice)

def convert(payload,exe,rows=h.ROWS,k=h.K,*,run_seconds=85):
    require(type(payload) is bytes and len(payload)==rows*k//2+rows*k//32,'Exact original weight plus scale bytes')
    require(type(rows) is type(k) is int and 0<rows<=2304 and 0<k<=5120 and k%32==0,'Bounded matrix')
    env=dict(os.environ);env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None);env.update(ENV)
    require(type(run_seconds) in (int,float) and 0<run_seconds<=85,'Codec wall cannot exceed original85s budget')
    p=None;started=time.monotonic()
    try:
        p=subprocess.Popen([str(exe),'--rows',str(rows),'--k',str(k)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,start_new_session=False,preexec_fn=child_limits)
        out,err=p.communicate(payload,timeout=run_seconds)
        require(p.returncode==0 and not err and len(out)==rows*k//32*17,'CPU codec nonzero/stderr/partial output')
        return out,{'pid':p.pid,'argv':[str(exe),'--rows',str(rows),'--k',str(k)],'returncode':p.returncode,'elapsed_seconds':time.monotonic()-started,'input_sha256':hashlib.sha256(payload).hexdigest(),'output_sha256':hashlib.sha256(out).hexdigest(),'configured_bounds':{'CPU':30,'AS_linux':512*2**20,'wall':90,'nice':15,'environment':ENV}}
    finally:
        # The pinned codec does not fork. Keep it in the caller's owned group:
        # outer supervisor cleanup still owns it if the Python caller is killed.
        # Local cleanup targets only the captured Popen PID, never its group.
        if p is not None and p.poll() is None:
            require(os.getpgid(p.pid)==os.getpgrp(),'Codec left inherited owner group')
            p.terminate()
            try:p.wait(timeout=.2)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=max(.01,90-(time.monotonic()-started)))
        if p is not None:
            require(p.poll() is not None,'Owned codec PID survives cleanup')
            for pipe in (p.stdin,p.stdout,p.stderr):
                if pipe is not None:pipe.close()

def construct(records,opened,partial,log,codec,pace):
    total=0;whole=hashlib.sha256()
    with Path(partial).open('xb') as output,Path(log).open('x') as receipt:
        for r in records:
            pace.tick(0);require(r['output_offset']==total and r['output_bytes']==h.MATRIX_BYTES,'Contiguous immutable output plan')
            f=opened[r['source']];w=exact_range(f,r['weight_range']);s=exact_range(f,r['scale_range']);pace.tick(len(w)+len(s))
            b,c=codec(w+s);require(type(b) is bytes and len(b)==h.MATRIX_BYTES and c['returncode']==0,'Complete CPU codec output')
            require(c['input_sha256']==hashlib.sha256(w+s).hexdigest() and c['output_sha256']==hashlib.sha256(b).hexdigest(),'Per-matrix byte custody')
            require(output.write(b)==len(b),'Complete overlay write');whole.update(b);total+=len(b);pace.tick(len(b))
            receipt.write(json.dumps({'name':r['name'],'source':r['source'],'weight_range':r['weight_range'],'scale_range':r['scale_range'],'output_offset':r['output_offset'],'output_bytes':len(b),'weight_sha256':hashlib.sha256(w).hexdigest(),'scale_sha256':hashlib.sha256(s).hexdigest(),'codec':c})+'\n');receipt.flush()
        output.flush();os.fsync(output.fileno());receipt.flush();os.fsync(receipt.fileno())
    require(total==h.TOTAL_BYTES and len(records)==1536,'Complete 1536 original gate/up matrices')
    with Path(partial).open('rb') as f:readback=hash_stream(f,pace)
    require(readback==(total,whole.hexdigest()),'Full overlay readback matches every output byte')
    return {'bytes':total,'sha256':whole.hexdigest(),'matrices':len(records)}

def publish(partial,final):
    require(Path(partial).parent==Path(final).parent and signature(partial)[2]>0,'Owned nonempty output')
    require(not Path(final).exists() and not Path(final).is_symlink(),'Never overwrite a final overlay')
    os.link(partial,final,follow_symlinks=False);Path(partial).unlink()
    fd=os.open(Path(final).parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    signature(final)

def input_paths():
    paths={'acquisition-source':HERE/'acquire_native.py','acquisition-qualified':HERE/'acquire-qualification.json','acquisition-state':HERE/'ACQUIRE_STATE.json','plan':HERE/'hybrid_plan_r2.py','plan-review':HERE/'PLAN_R2_SOURCE_ROOT_REVIEW.json','codec-source':HERE/'mxpack.cpp','codec-review':HERE/'CODEC_SOURCE_ROOT_REVIEW.json','CPU-supervisor':DRIVER,'manifest':HERE/'NATIVE_GU_SOURCE_MANIFEST.json','index':HERE/'official-1017-safetensors-index-FIRST.json'}
    for f in h.FILENAMES:paths['header-'+f]=HERE/('official-header-'+f+'.json')
    for mode in ('PLAN-R2','CODEC'):
        for host in ('darwin','linux'):
            for n in ('receipt.json','child.json','child.log'):paths[mode+'-'+host+'-'+n]=HERE/(mode+'-CPU-FIRST-'+host)/n
    for n in ('ds4.txt','tensors.txt','engram.bin','tokenizer/tokenizer.json','tokenizer/merges.txt','tokenizer/chat_template.jinja','tokenizer/token_type.json','tokenizer/vocab.json'):
        paths['base-'+n]=PACK/n
    for n in ('test_hybrid_plan_r2.py','run_plan_cpu_r2.py','test_mxpack.py','run_codec_cpu.py','CODEC-CPU-FIRST-linux/compile.json','CODEC-CPU-FIRST-linux/mxpack'):
        paths['prerequisite-'+n]=HERE/n
    return paths

def validate_receipt(r,c,host,source,inputs,ids):
    require(r['passed'] is True and r['source_sha256']==source and r['input_sha256']==inputs and r['test_ids']==ids and type(r['controls']) is int and r['controls']==len(ids) and ids,'Matching physical CPU proof')
    require(type(c['returncode']) is int and c['returncode']==0 and c['error'] is None and c['cleanup']==[] and 0<c['elapsed_seconds']<90,'CPU clean exit')
    v=r['observed'];require(v['platform']==host and v['cpu']==[30,30] and v['as']==([512*2**20]*2 if host=='linux' else None) and v['nice']==15 and type(v['pid']) is int and v['pid']>1 and v['pgid']==v['pid']==c['pid'] and v['environment']==ENV and v['dont_write_bytecode'] is True,'Actual CPU bounds')

def qualified(pin):
    p=HERE/'construct-qualification.json';require(sha(p)==pin,'Exact construction qualification')
    q=json.loads(p.read_text());require(q['root_source_read'] is True and q['sol_source_read'] is True,'Both source/test reads')
    for name,digest in q['files'].items():require(sha(name)==digest,'Frozen construction input changed: '+name)
    source={n:sha(HERE/n) for n in SOURCES};inputs={n:sha(p) for n,p in input_paths().items()}
    tree=ast.parse((HERE/'test_construct_native.py').read_text());ids=sorted('test_construct_native.'+c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'))
    require(source==q['source_sha256'] and inputs==q['input_sha256'] and ids==q['test_ids'] and ids,'Exact sources/inputs/IDs')
    require(all(q['files'].get(str(HERE/n))==v for n,v in source.items()) and all(q['files'].get(str(input_paths()[n]))==v for n,v in inputs.items()),'All executing inputs are pinned')
    review=HERE/'CONSTRUCT_SOURCE_ROOT_REVIEW.json';r=json.loads(review.read_text());require(q['files'].get(str(review))==sha(review) and r['source_sha256']==source and r['input_sha256']==inputs and r['test_ids']==ids and r['root_source_read'] is True and r['sol_source_read'] is True,'Source-bound manual review')
    for host in ('darwin','linux'):
        d=HERE/('CONSTRUCT-CPU-FIRST-'+host);r=json.loads((d/'receipt.json').read_text());c=json.loads((d/'child.json').read_text())
        validate_receipt(r,c,host,source,inputs,ids)
        require(all(q['files'].get(str(d/n))==sha(d/n) for n in ('receipt.json','child.json','child.log')),'Raw proof pins')
    for mode,reviewname,names in [('PLAN-R2','PLAN_R2_SOURCE_ROOT_REVIEW.json',('hybrid_plan_r2.py','test_hybrid_plan_r2.py','run_plan_cpu_r2.py')),('CODEC','CODEC_SOURCE_ROOT_REVIEW.json',('mxpack.cpp','test_mxpack.py','run_codec_cpu.py'))]:
        prior=json.loads((HERE/reviewname).read_text());prior_source={n:sha(HERE/n) for n in names}
        require(prior['source_sha256']==prior_source and prior['root_source_read'] is True and prior['sol_source_read'] is True,'Prerequisite source review unchanged')
        for host in ('darwin','linux'):
            d=HERE/(mode+'-CPU-FIRST-'+host);validate_receipt(json.loads((d/'receipt.json').read_text()),json.loads((d/'child.json').read_text()),host,prior_source,prior['input_sha256'],prior['test_ids'])
    return q

def main(pin):
    q=qualified(pin);require(a.physical_namespace(),'Physical Ubuntu namespace');m=a.manifest();transfer=a.transport();gate=a.Gate(transfer,m)
    require(gate.selected.host.start_binding==q['selected_binding'],'Current selected production owner')
    require(sha(CODEC)==CODEC_SHA and sha(DRIVER)==DRIVER_SHA,'Qualified byte codec/supervisor')
    state=json.loads((HERE/'ACQUIRE_STATE.json').read_text());require(state['status']=='BOTH_COMPLETE_OFFICIAL_SHARDS_SHA256_VERIFIED_NO_MODEL_RUN' and type(state['returncode']) is int and state['returncode']==0 and state['manifest_sha256']==a.MANIFEST_SHA,'Completed original source acquisition')
    transfer.safe_file(HERE/'download.lock')
    with (HERE/'download.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);gate();OUT.mkdir();deadline=time.monotonic()+WALL;pace=Pace(gate,deadline);opened={};signatures={};headers={};exe_sig=signature(CODEC);result={'status':'CONSTRUCTING_PUBLIC_NATIVE_GU_HYBRID','pid':os.getpid(),'qualification_sha256':pin,'exact_private_S2':False,'model_GPU_service_actions':0,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};transfer.emit(OUT/'state.json',result)
        try:
            for row in m['files']:
                p=HERE/'assets'/row['path'];f,sig=open_source(p);opened[row['path']]=f;signatures[row['path']]=sig
                require(hash_stream(f,pace)==(row['size'],row['sha256']),'Complete official source SHA256')
                f.seek(0);n=struct.unpack('<Q',f.read(8))[0];require(0<n<=8*2**20,'Bounded source header');raw=f.read(n)
                require(raw==(HERE/('official-header-'+row['path']+'.json')).read_bytes(),'Actual downloaded header matches frozen source plan');headers[row['path']]=h.header(raw,row['size'])
            index=json.loads((HERE/'official-1017-safetensors-index-FIRST.json').read_text());plan=h.make_plan(index,headers);transfer.emit(OUT/'plan.json',plan)
            result['overlay']=construct(plan,opened,OUT/'native-gu.bin.partial',OUT/'matrices.jsonl',lambda payload:convert(payload,CODEC),pace)
            require(signature(CODEC)==exe_sig and all(signature(HERE/'assets'/n)==sig for n,sig in signatures.items()),'Source/codec drift during construction');gate()
            publish(OUT/'native-gu.bin.partial',OUT/'native-gu.bin')
            ds4,tensors=h.pack_metadata((PACK/'ds4.txt').read_text(),(PACK/'tensors.txt').read_text(),plan,str(HERE.parent),str(OUT/'native-gu.bin'))
            pack=OUT/'pack';pack.mkdir();(pack/'ds4.txt').open('x').write(ds4);(pack/'tensors.txt').open('x').write(tensors)
            (pack/'tokenizer').mkdir()
            for n in ('engram.bin','tokenizer/tokenizer.json','tokenizer/merges.txt','tokenizer/chat_template.jinja','tokenizer/token_type.json','tokenizer/vocab.json'):
                b=(PACK/n).read_bytes();(pack/n).open('xb').write(b);require(sha(pack/n)==sha(PACK/n),'Unchanged base tokenizer/engram metadata')
            require(qualified(pin)==q,'Final construction source/CPU/input qualification drift');gate();result.update(status='PUBLIC_NATIVE_GU_PACK_CONSTRUCTED_NOT_MODEL_QUALIFIED',returncode=0,source_signatures=signatures,codec_signature=exe_sig,pack_files={str(p.relative_to(pack)):sha(p) for p in sorted(pack.rglob('*')) if p.is_file()})
        except BaseException as exc:
            result.update(status='CONSTRUCTION_DEFERRED_PARTIALS_RETAINED' if isinstance(exc,transfer.Deferred) else 'CONSTRUCTION_HOLD_PARTIALS_RETAINED',returncode=75 if isinstance(exc,transfer.Deferred) else 1,error_type=type(exc).__name__,reason=str(exc) if isinstance(exc,(ValueError,transfer.Deferred)) else 'Offline construction failed; preserve evidence, no automatic retry')
        finally:
            for f in opened.values():f.close()
            result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();transfer.emit(OUT/'state.json',result)
        return result['returncode']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--qualification-pin',required=True);args=parser.parse_args();raise SystemExit(main(args.qualification_pin))
