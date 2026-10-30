"""Serial bounded physical-Ubuntu dispatcher for saved Maya-S quality evidence.

No inference, service mutation, dump production, retries or phase advancement.
Each invocation owns exactly one metadata, single-file scan or assembly child.
"""
import argparse
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


def stage_contract(arm,stage,index):
    require(arm in ('QS0','QS1'),'Exact new quality arm')
    require(stage in ('metadata','scan','assemble'),'Exact audit stage')
    require((stage=='scan' and type(index) is int and 1<=index<=4) or
            (stage!='scan' and index is None),'Exact one-file scan index')
    name='scan-%d'%index if stage=='scan' else stage
    root=HERE/arm/'offline-audit-FIRST'
    target=HERE/arm/'terminal-audit.json' if stage=='assemble' else root/(name+'.json')
    return root,name,target


def bootstrap():
    require(sha(regular(BOOTSTRAP))==BOOTSTRAP_SHA,'Qualified bootstrap inventory changed')
    pins=json.loads(BOOTSTRAP.read_text())['paths_relative_to_E']
    require(len(pins)==38,'Exact bootstrap import closure required')
    for name,digest in pins.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
                and sha(regular(E/name))==digest,'Bootstrap source changed before import')
    require(sha(regular(GATE))==GATE_SHA,'Qualified serving gate changed')
    return pins


def fresh_idle(expected=None):
    require(sys.platform=='linux' and HERE==R/'reliability-optimization-20261025/decode-optimization-20261028/maya-s-comparison-v1/model-v1',
            'Physical Ubuntu saved-evidence namespace only')
    bootstrap()
    loaded=sys.modules.get('acquire')
    require(loaded is None or Path(loaded.__file__)==GATE,'Foreign cached serving gate')
    sys.path.insert(0,str(GATE.parent));import acquire
    require(Path(acquire.__file__)==GATE,'Serving gate origin differs')
    gate=acquire.SelectedGate()
    require(gate.host.idle(),'Offline audit deferred: user work active')
    gate.host.guard_binding(gate.host.start_binding['native_pid'])
    require(expected is None or gate.host.start_binding==expected,'Selected owner changed during offline stage')
    return dict(gate.host.start_binding)


def changed_source_proofs(q):
    for name in ('ms_audit_dispatch.py','ms_quality_audit.py','ms_audit.py','ms_runtime.py'):
        digest=sha(regular(HERE/name))
        require(q['files'].get(str(HERE/name))==digest
                and any(g['source_sha256'].get(name)==digest for g in q['CPU_groups']),
                'Changed executing audit source omitted from CPU proof')


def qualification(pin):
    path=HERE/'quality-qualification.json'
    require(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin) and sha(regular(path))==pin,
            'Exact quality qualification required')
    q=json.loads(path.read_text())
    require(q['mode']=='quality' and q['root_manual_review'] is True and q['astra_manual_review'] is True,
            'Manual quality qualification absent')
    for name,digest in q['files'].items():
        p=regular(name)
        require(p.is_relative_to(E) or p==R/'window.py' or p.is_relative_to(Path('/home/alex/deepseek-hosted-20261025')),
                'Foreign audit qualification input')
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest) and sha(p)==digest,
                'Qualification input changed')
    changed_source_proofs(q)
    require(q['files'].get(str(BOOTSTRAP))==BOOTSTRAP_SHA
            and q['files'].get(str(GATE))==GATE_SHA,'Bootstrap inventory/gate not pinned in full mode')
    for name,digest in json.loads(BOOTSTRAP.read_text())['paths_relative_to_E'].items():
        require(q['files'].get(str(E/name))==digest,'Bootstrap member omitted from full mode')
    require(sha(path)==pin,'Qualification changed during input verification')
    for name in ('ms_config','ms_fixtures','ms_runtime'):
        require(q['files'].get(str(HERE/(name+'.py')))==sha(regular(HERE/(name+'.py'))),
                'Audit support source omitted before import')
        loaded=sys.modules.get(name)
        require(loaded is None or Path(loaded.__file__)==HERE/(name+'.py'),'Foreign cached audit support')
    sys.path.insert(0,str(HERE));runtime=importlib.import_module('ms_runtime')
    require(Path(runtime.__file__)==HERE/'ms_runtime.py' and runtime.qualified('quality',pin)==q,
            'Exact full both-host mode/source/CPU/raw proof contract required')
    return q


def limits():
    os.nice(15);resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    resource.setrlimit(resource.RLIMIT_AS,(AS,AS))


def observed():
    value={'pid':os.getpid(),'CPU_seconds':list(resource.getrlimit(resource.RLIMIT_CPU)),
           'Linux_AS_bytes':list(resource.getrlimit(resource.RLIMIT_AS)),
           'nice':os.getpriority(os.PRIO_PROCESS,0),'environment':{k:os.environ.get(k) for k in ENV}}
    require(sys.platform=='linux' and value['CPU_seconds']==[30,30] and value['Linux_AS_bytes']==[AS,AS]
            and 15<=value['nice']<=19 and value['environment']==ENV,'Observed child-only CPU/AS/nice/environment bound')
    return value


def child(arm,stage,index,pin):
    root,name,target=stage_contract(arm,stage,index)
    actual=observed();attempt=json.loads(regular(root/(name+'.dispatch-attempt.json')).read_text())
    require(attempt['arm']==arm and attempt['stage']==name and attempt['qualification_sha256']==pin
            and attempt['retry'] is False,'Exact original dispatch attempt required')
    binding=attempt['binding'];fresh_idle(binding);qualification(pin);fresh_idle(binding)
    require(not target.exists() and not target.is_symlink(),'Preserve original stage result')
    actual.update(arm=arm,stage=name,qualification_sha256=pin)
    write_new(root/(name+'.observed.json'),actual)
    argv=[str(HERE/'ms_quality_audit.py'),'--arm',arm,'--stage',stage]
    if stage=='scan':argv+=['--index',str(index)]
    previous=sys.argv
    try:
        sys.argv=argv
        runpy.run_path(str(HERE/'ms_quality_audit.py'),run_name='__main__')
    finally:sys.argv=previous
    require(observed()=={k:actual[k] for k in ('pid','CPU_seconds','Linux_AS_bytes','nice','environment')},
            'Child bounds changed during saved-evidence stage')
    fresh_idle(binding);qualification(pin)
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
    if not gone(p.pid):errors.append('Owned audit process group survived')
    try:p.wait(timeout=1)
    except BaseException as e:errors.append(type(e).__name__)
    return errors


def artifact(arm,stage,index,pin,q,c):
    root,name,target=stage_contract(arm,stage,index)
    require(c['returncode']==0 and c['error'] is None and c['cleanup_errors']==[],'Failed child cannot certify evidence')
    a=json.loads(regular(root/(name+'.observed.json')).read_text())
    require(a['pid']==c['pid'] and a['arm']==arm and a['stage']==name and a['qualification_sha256']==pin
            and a['CPU_seconds']==[30,30] and a['Linux_AS_bytes']==[AS,AS]
            and type(a['nice']) is int and 15<=a['nice']<=19 and a['environment']==ENV,
            'Actual bounded child observation differs')
    meta=root/'metadata.json';d=json.loads(regular(meta).read_text())
    require(d['arm']==arm and d['qualification_sha256']==pin and d['metadata_passed'] is True,
            'Stage has no successful exact metadata')
    sources={p:v for p,v in q['files'].items() if p.endswith('.py')}
    require(d['audit_source_sha256']==sources,'Actual audit source map differs')
    return {'stage':name,'arm':arm,'qualification_sha256':pin,'metadata_sha256':sha(meta),
            'result_path':str(target),'result_sha256':sha(regular(target)),
            'audit_source_sha256':sources,'observed_child_sha256':sha(root/(name+'.observed.json')),'child':c}


def dispatch(arm,stage,index,pin):
    root,name,target=stage_contract(arm,stage,index)
    binding=fresh_idle()  # Before qualification hashing, directory creation or child.
    q=qualification(pin)
    fresh_idle(binding)
    for p in (root,*root.parents):require(not p.is_symlink(),'Audit output ancestor alias')
    root.mkdir(parents=True,exist_ok=True)
    for suffix in ('.dispatch-attempt.json','.observed.json','.child.log','.child.json'):
        path=root/(name+suffix)
        require(not path.exists() and not path.is_symlink(),'Preserve first audit stage; no retry')
    require(not target.exists() and not target.is_symlink(),'Preserve existing stage result')
    write_new(root/(name+'.dispatch-attempt.json'),{'arm':arm,'stage':name,'qualification_sha256':pin,
              'binding':binding,'retry':False})
    command=[sys.executable,'-B',str(HERE/'ms_audit_dispatch.py'),'--arm',arm,'--stage',stage,
             '--qualification-sha',pin,'--child']
    if stage=='scan':command+=['--index',str(index)]
    start=time.monotonic();p=None;rc=None;error=None;errors=[]
    try:
        with (root/(name+'.child.log')).open('xb') as log:
            p=subprocess.Popen(command,cwd=HERE,env=dict(os.environ,**ENV),stdin=subprocess.DEVNULL,
                               stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
            rc=p.wait(timeout=90)
    except BaseException as e:error=type(e).__name__+': '+str(e)
    finally:
        if p is not None:
            try:errors=cleanup(p)
            except BaseException as e:errors=['Unexpected owned cleanup '+type(e).__name__+': '+str(e)]
    c={'pid':p.pid if p else None,'returncode':rc,'error':error,'cleanup_errors':errors,
       'wall_seconds':time.monotonic()-start,'CPU_limit_seconds':30,'Linux_AS_bytes':AS,
       'wall_limit_seconds':90,'nice_increment':15,'environment':dict(ENV),'command':command}
    if rc==0 and error is None and not errors:
        try:
            require(math.isfinite(c['wall_seconds']) and 0<=c['wall_seconds']<=90,'Stage exceeded bounded wall')
            fresh_idle(binding)
            qualification(pin)
            result=artifact(arm,stage,index,pin,q,c)
        except BaseException as e:
            c['error']='Post-stage custody '+type(e).__name__+': '+str(e)
            result={'stage':name,'arm':arm,'qualification_sha256':pin,'child':c,'passed':False}
    else:result={'stage':name,'arm':arm,'qualification_sha256':pin,'child':c,'passed':False}
    write_new(root/(name+'.child.json'),result)
    return 0 if c['returncode']==0 and c['error'] is None and not c['cleanup_errors'] else 1


def main():
    a=argparse.ArgumentParser();a.add_argument('--arm',choices=['QS0','QS1'],required=True)
    a.add_argument('--stage',choices=['metadata','scan','assemble'],required=True);a.add_argument('--index',type=int)
    a.add_argument('--qualification-sha',required=True);a.add_argument('--child',action='store_true');args=a.parse_args()
    action=child if args.child else dispatch
    return action(args.arm,args.stage,args.index,args.qualification_sha)


if __name__=='__main__':sys.exit(main())
