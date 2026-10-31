"""Single bounded physical-Ubuntu dispatcher for saved whole-pack timing evidence.

No inference, service mutation, dump production, retries or phase advancement.
Each invocation owns exactly one saved-evidence child after selected restoration.
"""
import argparse
import ast
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import resource
import runpy
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
E=HERE.parents[2]
R=Path('/home/alex/strata-deepseek-test-20261024')
GATE=HERE.parent/'acquisition-authorized-v2/acquire.py'
GATE_SHA='6a399f4eec7b9cb23b7ff7aa03d60deb490787825ae92e43ccde8d40065885b5'
BOOTSTRAP=HERE.parent/'ACQUISITION_HELPER_CLOSURE_ASTRA.json'
BOOTSTRAP_SHA='17cb5bd6f5fedb59fa5505252cf01eff77fd95eba9a2ab64622f17ae5d1c7b53'
ENV={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
     'MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}
AS=512*2**20
BASE_DISPATCH_SHA='8858c1d2f70cd7e97d416fa1535cb1af18f1a2647731c2d88e7c36d66b0e5bad'


def require(ok,why):
    if not ok:raise ValueError(why)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()


def regular(path):
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts,'Canonical absolute evidence')
    require(all(not p.is_symlink() for p in (path,*path.parents)),'Evidence alias')
    require(path.is_file() and path.stat().st_nlink==1,'One regular evidence file')
    return path


def write_new(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def paths(mode,arm):
    require(mode in ('prose','coding') and arm in ('A1','B1','B2','A2'),'Exact timed family/arm')
    leaf=HERE/mode/arm
    return leaf/'offline-audit-FIRST',leaf/'terminal-audit.json'


def base():
    path=HERE.parent/'model-v1/ms_audit_dispatch.py'
    require(sha(regular(path))==BASE_DISPATCH_SHA,'Exact qualified bootstrap parent')
    cached=sys.modules.get('ms_audit_dispatch')
    require(cached is None or Path(cached.__file__)==path,'Foreign cached bootstrap parent')
    sys.path.insert(0,str(path.parent));module=importlib.import_module('ms_audit_dispatch')
    require(Path(module.__file__)==path,'Bootstrap parent origin');return module


def bootstrap():return base().bootstrap()


def fresh_idle(expected=None):
    require(sys.platform=='linux' and HERE==R/'reliability-optimization-20261025/decode-optimization-20261028/maya-s-comparison-v1/performance-v2',
            'Physical Ubuntu new quality namespace only')
    return base().fresh_idle(expected)


def changed_source_proofs(q):
    for name in ('pv_dispatch.py','pv_audit.py','pv_runtime.py','pv_config.py','pv_controls.py','pv_owner.py'):
        digest=sha(regular(HERE/name))
        require(q['files'].get(str(HERE/name))==digest
                and any(g['source_sha256'].get(name)==digest for g in q['CPU_groups']),
                'Changed executing audit source omitted from CPU proof')
    for name in ('pv_audit','pv_dispatch'):
        source=name+'.py';test='test_'+name+'.py';tree=ast.parse((HERE/test).read_text())
        ids=sorted('test_'+name+'.'+c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef)
                   for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'))
        require(ids and any(g['source_sha256'].get(source)==sha(regular(HERE/source))
                and g['source_sha256'].get(test)==sha(regular(HERE/test))
                and set(ids).issubset(g['test_ids']) for g in q['CPU_groups']),
                'Exact new auditor/parent tests omitted from both-host proof')


def allowed_input(p):
    p=Path(p)
    return p.is_absolute() and '..' not in p.parts and (p.is_relative_to(E)
        or p in (R/'window.py',R/'windows/20261030T220002Z.json',R/'windows/20261030T220002Z.telemetry.jsonl',R/'windows/20261030T225816Z.json',R/'windows/20261030T225816Z.telemetry.jsonl',R/'windows/20261030T232538Z.json',R/'windows/20261030T232538Z.telemetry.jsonl')
        or p.is_relative_to(Path('/home/alex/deepseek-hosted-20261025')))


def qualification(pin,mode):
    path=HERE/(mode+'-qualification.json')
    require(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin) and sha(regular(path))==pin,
            'Exact quality qualification required')
    q=json.loads(path.read_text())
    require(q['mode']==mode and q['root_manual_review'] is True and q['astra_manual_review'] is True,
            'Manual quality qualification absent')
    for name,digest in q['files'].items():
        p=Path(name)
        require(allowed_input(p),
                'Foreign audit qualification input')
        p=regular(p)
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest) and sha(p)==digest,
                'Qualification input changed')
    changed_source_proofs(q)
    require(q['files'].get(str(HERE.parent/'model-v1/ms_audit_dispatch.py'))==BASE_DISPATCH_SHA,'Qualified bootstrap parent omitted from full mode')
    require(q['files'].get(str(BOOTSTRAP))==BOOTSTRAP_SHA
            and q['files'].get(str(GATE))==GATE_SHA,'Bootstrap inventory/gate not pinned in full mode')
    for name,digest in json.loads(BOOTSTRAP.read_text())['paths_relative_to_E'].items():
        require(q['files'].get(str(E/name))==digest,'Bootstrap member omitted from full mode')
    require(sha(path)==pin,'Qualification changed during input verification')
    for name in ('pv_config','pv_runtime'):
        require(q['files'].get(str(HERE/(name+'.py')))==sha(regular(HERE/(name+'.py'))),
                'Audit support source omitted before import')
        loaded=sys.modules.get(name)
        require(loaded is None or Path(loaded.__file__)==HERE/(name+'.py'),'Foreign cached audit support')
    sys.path.insert(0,str(HERE));runtime=importlib.import_module('pv_runtime')
    require(Path(runtime.__file__)==HERE/'pv_runtime.py' and runtime.qualified(mode,pin)==q,
            'Exact full both-host mode/source/CPU/raw proof contract required')
    return q


def limits():
    os.nice(15);resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(AS,AS))


def observed():
    value={'pid':os.getpid(),'CPU_seconds':list(resource.getrlimit(resource.RLIMIT_CPU)),
        'Linux_AS_bytes':list(resource.getrlimit(resource.RLIMIT_AS)),'nice':os.getpriority(os.PRIO_PROCESS,0),'environment':{k:os.environ.get(k) for k in ENV}}
    require(sys.platform=='linux' and value['CPU_seconds']==[30,30] and value['Linux_AS_bytes']==[AS,AS]
        and 15<=value['nice']<=19 and value['environment']==ENV and os.getpgrp()==value['pid'],'Actual child-only CPU/AS/nice/env')
    return value


def child(mode,arm,pin):
    root,target=paths(mode,arm);actual=observed();attempt=json.loads(regular(root/'dispatch-attempt.json').read_text())
    require(attempt['mode']==mode and attempt['arm']==arm and attempt['qualification_sha256']==pin
        and attempt['retry'] is False and attempt['parent_pid']==os.getppid(),'Exact original parent attempt')
    binding=attempt['binding'];fresh_idle(binding);qualification(pin,mode);fresh_idle(binding)
    require(not target.exists() and not target.is_symlink(),'Preserve original audit result')
    write_new(root/'observed.json',actual)
    previous=sys.argv
    try:
        sys.argv=[str(HERE/'pv_audit.py'),'--mode',mode,'--arm',arm]
        runpy.run_path(str(HERE/'pv_audit.py'),run_name='__main__')
    finally:sys.argv=previous
    require(observed()==actual,'Child bounds changed')
    fresh_idle(binding);qualification(pin,mode)
    write_new(root/'finished.json',{'pid':actual['pid'],'mode':mode,'arm':arm,'qualification_sha256':pin,
        'target_sha256':sha(regular(target)),'observed_sha256':sha(root/'observed.json')})
    return 0


def gone(pid):
    try:os.killpg(pid,0)
    except ProcessLookupError:return True
    return False


def cleanup(p):
    errors=[]
    if gone(p.pid):return errors
    for sig,delay in ((signal.SIGTERM,2),(signal.SIGKILL,2)):
        try:os.killpg(p.pid,sig)
        except ProcessLookupError:pass
        except BaseException as e:errors.append(type(e).__name__)
        until=time.monotonic()+delay
        while not gone(p.pid) and time.monotonic()<until:p.poll();time.sleep(.02)
        if gone(p.pid):break
    if not gone(p.pid):errors.append('Owned child process group survived')
    try:p.wait(timeout=1)
    except BaseException as e:errors.append(type(e).__name__)
    return errors


def finished_contract(root,target,mode,arm,pin,pid):
    actual=json.loads(regular(root/'observed.json').read_text());finished=json.loads(regular(root/'finished.json').read_text())
    require(actual['pid']==finished['pid']==pid and finished['mode']==mode and finished['arm']==arm
        and finished['qualification_sha256']==pin and finished['target_sha256']==sha(regular(target))
        and finished['observed_sha256']==sha(root/'observed.json'),'Observed/finished/source/result custody differs')
    require(actual['CPU_seconds']==[30,30] and actual['Linux_AS_bytes']==[AS,AS] and 15<=actual['nice']<=19
        and actual['environment']==ENV,'Saved actual child limits absent')
    return actual,finished


def dispatch(mode,arm,pin):
    root,target=paths(mode,arm);binding=fresh_idle();q=qualification(pin,mode);fresh_idle(binding)
    require(not root.exists() and not target.exists(),'Preserve FIRST audit; no retry')
    root.mkdir(parents=True);write_new(root/'dispatch-attempt.json',{'mode':mode,'arm':arm,'qualification_sha256':pin,
        'binding':binding,'parent_pid':os.getpid(),'retry':False})
    p=None;rc=None;error=None;errors=[];began=time.monotonic();actual=finished=None
    command=[sys.executable,'-B',str(HERE/'pv_dispatch.py'),'--mode',mode,'--arm',arm,'--qualification-sha',pin,'--child']
    try:
        with (root/'child.log').open('xb') as log:
            p=subprocess.Popen(command,cwd=HERE,env=dict(os.environ,**ENV),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
            rc=p.wait(timeout=90)
    except BaseException as e:error=type(e).__name__+': '+str(e)
    finally:
        if p is not None:
            try:errors+=cleanup(p)
            except BaseException as e:errors.append('cleanup '+repr(e))
        try:
            fresh_idle(binding);require(qualification(pin,mode)==q,'Parent source/input custody changed')
            if rc==0 and error is None:actual,finished=finished_contract(root,target,mode,arm,pin,p.pid)
        except BaseException as e:errors.append('postcustody '+repr(e))
        record={'mode':mode,'arm':arm,'qualification_sha256':pin,'result_path':str(target),
            'result_sha256':finished['target_sha256'] if finished else None,
            'audit_source_sha256':{n:h for n,h in q['files'].items() if n.endswith('.py')},
            'observed_sha256':sha(root/'observed.json') if actual else None,'finished_sha256':sha(root/'finished.json') if finished else None,
            'child':{'pid':p.pid if p else None,'returncode':rc,'error':error,'cleanup_errors':errors,'wall_seconds':time.monotonic()-began,
                'CPU_limit_seconds':30,'Linux_AS_bytes':AS,'wall_limit_seconds':90,'nice_increment':15,'environment':ENV,'command':command}}
        write_new(root/'child.json',record)
    return 0 if rc==0 and error is None and not errors else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('prose','coding'),required=True);p.add_argument('--arm',choices=('A1','B1','B2','A2'),required=True);p.add_argument('--qualification-sha',required=True);p.add_argument('--child',action='store_true');a=p.parse_args()
    sys.exit(child(a.mode,a.arm,a.qualification_sha) if a.child else dispatch(a.mode,a.arm,a.qualification_sha))
