"""Separate offline completion consumer and bounded parent controls only.

No native/model/downloaded payload. Parent guards selected production before Linux CPU work.
Two new source-bound groups use separate bounded children; no failed proof is regraded.
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
E=HERE.parents[2]
SOURCES=('ms_compat_completion.py','test_ms_compat_completion.py','ms_compat_completion_dispatch.py','test_ms_compat_completion_dispatch.py','ms_completion_cpu.py')
GROUPS={'completion':('test_ms_compat_completion',),'supervision':('test_ms_compat_completion_dispatch',)}
REVIEW=HERE/'COMPLETION_SOURCE_ROOT_REVIEW.json'
MODEL_Q_SHA='a8d5ff19fa187f46adf70b53287b652241a5f4b256a61811643d750cd770c090'

ENV={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok,message):
    if not ok:raise ValueError(message)


def ids(group):
    result=[]
    for name in GROUPS[group]:
        tree=ast.parse((HERE/(name+'.py')).read_text())
        result += [name+'.'+c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef)
                   for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_')]
    return sorted(result)


def canonical_input(name):
    require(type(name) is str and name not in ('','.') and not Path(name).is_absolute() and '..' not in Path(name).parts,'Canonical relative input required')
    current=E
    require(not current.is_symlink(),'Evidence root alias')
    for part in Path(name).parts:
        current=current/part;require(not current.is_symlink(),'Input alias')
    require(current.is_file(),'Input missing')
    return current


def input_pins(review):
    qpath=HERE/'compatibility-qualification.json'
    require(sha(qpath)==MODEL_Q_SHA,'Original admitted source map changed')
    prior=HERE/'AUDIT_COMPAT_SOURCE_ROOT_REVIEW.json'
    prior_pin='1bf8ca7e06f0e9229611733a08d1f32d875e8d3cf0b4a9a56e1b6def23d8188d'
    require(sha(prior)==prior_pin,'Exact original auditor CPU source/input closure')
    old=json.loads(prior.read_text())
    required={str(qpath.relative_to(E)):MODEL_Q_SHA,str(prior.relative_to(E)):prior_pin}
    required.update(old['input_sha256'])
    required.update({str((HERE/n).relative_to(E)):h for n,h in old['source_sha256'].items()})
    # Original physical model/binary/stat pins remain action-time gates in the
    # original qualification, not imported or executed by synthetic CPU tests.
    supplied=review['input_sha256']
    require(supplied==required,'Exact unchanged original evidence closure required')
    actual={name:sha(canonical_input(name)) for name in supplied}
    require(actual==supplied,'Original source/input changed');return actual


def checked(pin,group):
    require(sha(REVIEW)==pin,'source review changed');r=json.loads(REVIEW.read_text())
    require(r['root_entire_source_and_tests_read'] is True and r['astra_entire_source_and_tests_read'] is True,'manual reviews required')
    sm={n:sha(HERE/n) for n in SOURCES};im=input_pins(r)
    require(group in GROUPS and sm==r['source_sha256'] and im==r['input_sha256'] and ids(group)==r['test_ids'][group],'source/input/IDs changed')
    return sm,im,ids(group)


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


def child(pin,out,group):
    before=checked(pin,group);require(all(os.environ.get(k)==v for k,v in ENV.items()),'CPU env')
    require(list(resource.getrlimit(resource.RLIMIT_CPU))==[30,30] and os.getpriority(os.PRIO_PROCESS,0)>=15,'actual CPU limits')
    if sys.platform=='linux':require(list(resource.getrlimit(resource.RLIMIT_AS))==[512*1024**2]*2,'actual AS bound')
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in GROUPS[group])
    def flatten(s):
        for t in s:
            if isinstance(t,unittest.TestSuite):yield from flatten(t)
            else:yield t.id()
    require(list(flatten(suite))==before[2],'discovered ordered IDs')
    result=unittest.TextTestRunner(verbosity=2).run(suite);require(checked(pin,group)==before,'post CPU source/input custody')
    receipt={'group':group,'candidate_pack_encoded':False,'passed':result.wasSuccessful(),'controls':result.testsRun,'test_ids':before[2],'source_sha256':before[0],'input_sha256':before[1],'CPU_seconds':list(resource.getrlimit(resource.RLIMIT_CPU)),'Linux_AS_bytes':list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform=='linux' else None,'nice':os.getpriority(os.PRIO_PROCESS,0),'environment':ENV,'CPU_only':True,'native_model_executed':False}
    with (out/'receipt.json').open('x') as f:json.dump(receipt,f,indent=2)
    return 0 if result.wasSuccessful() else 1


def main(pin,group):
    before=checked(pin,group);host='linux' if sys.platform=='linux' else 'darwin';require(sys.platform in ('linux','darwin'),'physical CPU platform')
    out=HERE/(group+'-CPU-COMPLETION-FIRST-'+host);out.mkdir();start=time.monotonic();p=None;error=None;errors=[];rc=None
    try:
        env=dict(os.environ,**ENV)
        with (out/'child.log').open('xb') as log:
            p=subprocess.Popen([sys.executable,'-B',str(HERE/'ms_completion_cpu.py'),'--review-sha',pin,'--child',str(out),'--group',group],cwd=HERE,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
            rc=p.wait(timeout=90)
    except BaseException as e:error=type(e).__name__+': '+str(e)
    finally:
        if p is not None:
            try:errors=cleanup(p)
            except BaseException as e:errors=['Unexpected owned cleanup '+type(e).__name__+': '+str(e)]
        try:require(checked(pin,group)==before,'parent post-input custody')
        except BaseException as e:errors.append('postcustody '+str(e))
        record={'pid':p.pid if p else None,'returncode':rc,'error':error,'cleanup_errors':errors,'wall_seconds':time.monotonic()-start,'CPU_limit_seconds':30,'Linux_AS_bytes':512*1024**2 if sys.platform=='linux' else None,'wall_limit_seconds':90,'nice_increment':15,'environment':ENV,'source_sha256':before[0],'input_sha256':before[1],'test_ids':before[2]}
        with (out/'child.json').open('x') as f:json.dump(record,f,indent=2)
    return 0 if rc==0 and error is None and not errors else 1


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--review-sha',required=True);a.add_argument('--child',type=Path);a.add_argument('--group',choices=list(GROUPS),required=True);args=a.parse_args()
    if args.child:
        require(args.child==HERE/(args.group+'-CPU-COMPLETION-FIRST-'+('linux' if sys.platform=='linux' else 'darwin')),'child output namespace')
        sys.exit(child(args.review_sha,args.child,args.group))
    sys.exit(main(args.review_sha,args.group))
