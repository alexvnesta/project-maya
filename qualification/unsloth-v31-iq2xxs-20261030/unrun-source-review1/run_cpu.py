"""FIRST synthetic parallel Unsloth acquisition controls only; caller must first admit fresh CPU work.

No serving imports, downloaded asset reads, weight hashes, tokenizer model calls,
pack production run, or networking. Linux host guards are the parent controller's
responsibility; this driver is only the bounded source-bound CPU child.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import unittest

HERE=Path(__file__).resolve().parent
E=HERE.parents[1]
SOURCES=('acquire_unsloth.py','test_acquire_unsloth.py','run_cpu.py')
INPUTS=('decode-optimization-20261028/maya-s-comparison-v1/acquisition-authorized-v2/acquire.py','decode-optimization-20261028/maya-s-comparison-v1/acquisition-authorized-v2/acquisition-qualification.json','decode-optimization-20261028/unsloth-v31-iq2xxs-download-v1/ASSET_MANIFEST.json','decode-optimization-20261028/unsloth-v31-iq2xxs-download-v1/AUTHORIZATION.json')
REVIEW=HERE/'CPU_SOURCE_ROOT_REVIEW.json'
ENV={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok,message):
    if not ok:raise ValueError(message)


def ids():
    tree=ast.parse((HERE/'test_acquire_unsloth.py').read_text())
    return sorted('test_acquire_unsloth.'+c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'))


def checked(pin):
    require(sha(REVIEW)==pin,'source review changed');r=json.loads(REVIEW.read_text())
    require(r['root_entire_source_and_tests_read'] is True and r['astra_entire_source_and_tests_read'] is True,'manual reviews required')
    sm={n:sha(HERE/n) for n in SOURCES};im={n:sha(E/n) for n in INPUTS}
    require(sm==r['source_sha256'] and im==r['input_sha256'] and ids()==r['test_ids'],'source/input/IDs changed')
    return sm,im,ids()


def limits():
    os.nice(15);resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    if sys.platform=='linux':resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))


def gone(pid):
    try:os.killpg(pid,0)
    except ProcessLookupError:return True
    return False


def cleanup(p):
    errors=[]
    if gone(p.pid):return errors
    for sig,wait in ((signal.SIGTERM,2),(signal.SIGKILL,2)):
        try:os.killpg(p.pid,sig)
        except ProcessLookupError:pass
        except BaseException as e:errors.append(type(e).__name__)
        until=time.monotonic()+wait
        while not gone(p.pid) and time.monotonic()<until:
            p.poll();time.sleep(.02)
        if gone(p.pid):break
    if not gone(p.pid):errors.append('owned process group survived')
    try:p.wait(timeout=1)
    except BaseException as e:errors.append(type(e).__name__)
    return errors


def child(pin,out):
    before=checked(pin);require(all(os.environ.get(k)==v for k,v in ENV.items()),'CPU env')
    require(list(resource.getrlimit(resource.RLIMIT_CPU))==[30,30] and os.getpriority(os.PRIO_PROCESS,0)>=15,'actual CPU limits')
    if sys.platform=='linux':require(list(resource.getrlimit(resource.RLIMIT_AS))==[512*1024**2]*2,'actual AS bound')
    suite=unittest.defaultTestLoader.loadTestsFromName('test_acquire_unsloth')
    def flatten(s):
        for t in s:
            if isinstance(t,unittest.TestSuite):yield from flatten(t)
            else:yield t.id()
    require(list(flatten(suite))==before[2],'discovered ordered IDs')
    result=unittest.TextTestRunner(verbosity=2).run(suite);require(checked(pin)==before,'post CPU source/input custody')
    receipt={'passed':result.wasSuccessful(),'controls':result.testsRun,'test_ids':before[2],'source_sha256':before[0],'input_sha256':before[1],'CPU_seconds':list(resource.getrlimit(resource.RLIMIT_CPU)),'Linux_AS_bytes':list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform=='linux' else None,'nice':os.getpriority(os.PRIO_PROCESS,0),'environment':ENV,'CPU_only':True,'production_pack_or_model_executed':False}
    with (out/'receipt.json').open('x') as f:json.dump(receipt,f,indent=2)
    return 0 if result.wasSuccessful() else 1


def main(pin):
    before=checked(pin);host='linux' if sys.platform=='linux' else 'darwin';require(sys.platform in ('linux','darwin'),'physical CPU platform')
    out=HERE/('CPU-FIRST-'+host);out.mkdir();start=time.monotonic();p=None;error=None;errors=[];rc=None
    try:
        env=dict(os.environ,**ENV)
        with (out/'child.log').open('xb') as log:
            p=subprocess.Popen([sys.executable,'-B',str(HERE/'run_cpu.py'),'--review-sha',pin,'--child',str(out)],cwd=HERE,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
            rc=p.wait(timeout=90)
    except BaseException as e:error=type(e).__name__+': '+str(e)
    finally:
        if p is not None:errors=cleanup(p)
        try:require(checked(pin)==before,'parent post-input custody')
        except BaseException as e:errors.append('postcustody '+str(e))
        record={'pid':p.pid if p else None,'returncode':rc,'error':error,'cleanup_errors':errors,'wall_seconds':time.monotonic()-start,'CPU_limit_seconds':30,'Linux_AS_bytes':512*1024**2 if sys.platform=='linux' else None,'wall_limit_seconds':90,'nice_increment':15,'environment':ENV,'source_sha256':before[0],'input_sha256':before[1],'test_ids':before[2]}
        with (out/'child.json').open('x') as f:json.dump(record,f,indent=2)
    return 0 if rc==0 and error is None and not errors else 1


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--review-sha',required=True);a.add_argument('--child',type=Path);args=a.parse_args()
    if args.child:
        require(args.child==HERE/('CPU-FIRST-linux' if sys.platform=='linux' else 'CPU-FIRST-darwin'),'child output namespace')
        sys.exit(child(args.review_sha,args.child))
    sys.exit(main(args.review_sha))
