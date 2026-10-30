"""Serial bounded physical-Ubuntu dispatcher for saved Maya-S quality evidence.

No inference, service mutation, dump production, retries or phase advancement.
Each invocation owns exactly one metadata, single-file scan or assembly child.
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


def stage_contract(arm,stage,index):
    require(arm in ('QS0','QS1'),'Exact new quality arm')
    require(stage in ('metadata','scan','assemble'),'Exact audit stage')
    require((stage=='scan' and type(index) is int and 1<=index<=4) or
            (stage!='scan' and index is None),'Exact one-file scan index')
    name='scan-%d'%index if stage=='scan' else stage
    root=HERE/arm/'offline-audit-FIRST'
    target=HERE/arm/'terminal-audit.json' if stage=='assemble' else root/(name+'.json')
    return root,name,target


def base():
    path=HERE.parent/'model-v1/ms_audit_dispatch.py'
    require(sha(regular(path))==BASE_DISPATCH_SHA,'Exact qualified bootstrap parent')
    cached=sys.modules.get('ms_audit_dispatch')
    require(cached is None or Path(cached.__file__)==path,'Foreign cached bootstrap parent')
    sys.path.insert(0,str(path.parent));module=importlib.import_module('ms_audit_dispatch')
    require(Path(module.__file__)==path,'Bootstrap parent origin');return module


def bootstrap():return base().bootstrap()


def fresh_idle(expected=None):
    require(sys.platform=='linux' and HERE==R/'reliability-optimization-20261025/decode-optimization-20261028/maya-s-comparison-v1/quality-v2',
            'Physical Ubuntu new quality namespace only')
    return base().fresh_idle(expected)


def changed_source_proofs(q):
    for name in ('qv_dispatch.py','qv_audit.py','qv_runtime.py','qv_config.py','qv_controls.py','qv_owner.py'):
        digest=sha(regular(HERE/name))
        require(q['files'].get(str(HERE/name))==digest
                and any(g['source_sha256'].get(name)==digest for g in q['CPU_groups']),
                'Changed executing audit source omitted from CPU proof')
    for name in ('qv_audit','qv_dispatch'):
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
        or p in (R/'window.py',R/'windows/20261030T220002Z.json',R/'windows/20261030T220002Z.telemetry.jsonl')
        or p.is_relative_to(Path('/home/alex/deepseek-hosted-20261025')))


def qualification(pin):
    path=HERE/'quality-qualification.json'
    require(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin) and sha(regular(path))==pin,
            'Exact quality qualification required')
    q=json.loads(path.read_text())
    require(q['mode']=='quality' and q['root_manual_review'] is True and q['astra_manual_review'] is True,
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
    for name in ('qv_config','qv_runtime'):
        require(q['files'].get(str(HERE/(name+'.py')))==sha(regular(HERE/(name+'.py'))),
                'Audit support source omitted before import')
        loaded=sys.modules.get(name)
        require(loaded is None or Path(loaded.__file__)==HERE/(name+'.py'),'Foreign cached audit support')
    sys.path.insert(0,str(HERE));runtime=importlib.import_module('qv_runtime')
    require(Path(runtime.__file__)==HERE/'qv_runtime.py' and runtime.qualified('quality',pin)==q,
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
            and 15<=value['nice']<=19 and value['environment']==ENV and os.getpgrp()==value['pid'],'Observed child-only CPU/AS/nice/environment bound')
    return value


def child(arm,stage,index,pin):
    root,name,target=stage_contract(arm,stage,index)
    actual=observed();attempt=json.loads(regular(root/(name+'.dispatch-attempt.json')).read_text())
    require(attempt['arm']==arm and attempt['stage']==name and attempt['qualification_sha256']==pin
            and attempt['retry'] is False and attempt['parent_pid']==os.getppid(),'Exact original dispatch attempt required')
    binding=attempt['binding'];fresh_idle(binding);qualification(pin);fresh_idle(binding)
    require(not target.exists() and not target.is_symlink(),'Preserve original stage result')
    actual.update(arm=arm,stage=name,qualification_sha256=pin)
    write_new(root/(name+'.observed.json'),actual)
    argv=[str(HERE/'qv_audit.py'),'--arm',arm,'--stage',stage]
    if stage=='scan':argv+=['--index',str(index)]
    previous=sys.argv
    try:
        sys.argv=argv
        runpy.run_path(str(HERE/'qv_audit.py'),run_name='__main__')
    finally:sys.argv=previous
    require(observed()=={k:actual[k] for k in ('pid','CPU_seconds','Linux_AS_bytes','nice','environment')},
            'Child bounds changed during saved-evidence stage')
    fresh_idle(binding);qualification(pin)
    write_new(root/(name+'.finished.json'),{'pid':actual['pid'],'arm':arm,'stage':name,'qualification_sha256':pin,
              'target_sha256':sha(regular(target)),'observed_sha256':sha(root/(name+'.observed.json'))})
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
    require(type(c['returncode']) is int and c['returncode']==0 and type(c['pid']) is int and c['pid']>0
            and c['error'] is None and c['cleanup_errors']==[] and type(c['wall_seconds']) in (int,float)
            and math.isfinite(c['wall_seconds']) and 0<=c['wall_seconds']<=90,'Failed child cannot certify evidence')
    a=json.loads(regular(root/(name+'.observed.json')).read_text())
    require(a['pid']==c['pid'] and a['arm']==arm and a['stage']==name and a['qualification_sha256']==pin
            and a['CPU_seconds']==[30,30] and a['Linux_AS_bytes']==[AS,AS]
            and type(a['nice']) is int and 15<=a['nice']<=19 and a['environment']==ENV,
            'Actual bounded child observation differs')
    finished=json.loads(regular(root/(name+'.finished.json')).read_text())
    require(finished=={'pid':c['pid'],'arm':arm,'stage':name,'qualification_sha256':pin,
            'target_sha256':sha(regular(target)),'observed_sha256':sha(root/(name+'.observed.json'))},'Actual child completion/source custody differs')
    meta=root/'metadata.json';d=json.loads(regular(meta).read_text())
    require(d['arm']==arm and d['qualification_sha256']==pin and d['metadata_passed'] is True,
            'Stage has no successful exact metadata')
    sources={p:v for p,v in q['files'].items() if p.endswith('.py')}
    require(d['audit_source_sha256']==sources,'Actual audit source map differs')
    result=json.loads(regular(target).read_text())
    require(result.get('arm')==arm and result.get('qualification_sha256')==pin,'Result arm/source differs')
    if stage=='metadata':
        require(result.get('stage')=='METADATA' and result.get('metadata_passed') is True
                and result.get('passed') is False,'Only complete metadata-only publication')
    elif stage=='scan':
        require(result.get('stage')=='FINITE_SCAN' and result.get('passed') is True
                and type(result.get('index')) is int and result['index']==index
                and result.get('native_pid')==d['actual_native_pid'],'Only exact one-file finite publication')
    else:
        require(result.get('stage')=='COMPLETE' and result.get('passed') is True
                and result.get('finite_scans_in_separate_bounded_children') is True,'Only complete four-file assembly')
    require(all(result.get(k,False) is False for k in ('general_quality_claim','performance_claim','deployment_admitted',
                'cross_pack_numeric_equivalence','token_row_alignment_claimed','near_full_context_or_output_tested')),
            'No general quality/performance/deployment claim')

    return {'stage':name,'arm':arm,'qualification_sha256':pin,'metadata_sha256':sha(meta),
            'result_path':str(target),'result_sha256':sha(regular(target)),
            'audit_source_sha256':sources,'observed_child_sha256':sha(root/(name+'.observed.json')),'finished_child_sha256':sha(root/(name+'.finished.json')),'child':c}


def dispatch(arm,stage,index,pin):
    root,name,target=stage_contract(arm,stage,index)
    binding=fresh_idle()  # Before qualification hashing, directory creation or child.
    q=qualification(pin)
    fresh_idle(binding)
    if stage!='metadata':
        d=json.loads(regular(root/'metadata.json').read_text())
        require(d['qualification_sha256']==pin and d['selected_identity']['start_binding']==binding,'Selected owner changed since metadata')
    for p in (root,*root.parents):require(not p.is_symlink(),'Audit output ancestor alias')
    root.mkdir(parents=True,exist_ok=True)
    for suffix in ('.dispatch-attempt.json','.observed.json','.child.log','.child.json','.finished.json'):
        path=root/(name+suffix)
        require(not path.exists() and not path.is_symlink(),'Preserve first audit stage; no retry')
    require(not target.exists() and not target.is_symlink(),'Preserve existing stage result')
    write_new(root/(name+'.dispatch-attempt.json'),{'arm':arm,'stage':name,'qualification_sha256':pin,
              'binding':binding,'retry':False,'parent_pid':os.getpid()})
    command=[sys.executable,'-B',str(HERE/'qv_dispatch.py'),'--arm',arm,'--stage',stage,
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
