"""FIRST new Maya-S input controls and baseline CPU encodings only.

No native/model/downloaded assets. Parent admits Linux CPU work before this
source-bound driver; candidate pack encoding is a later separately qualified input operation.
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
SOURCES=('ms_config.py','ms_fixtures.py','test_ms_inputs.py','ms_inputs_cpu.py')
PRIOR='decode-optimization-20261028/prose-speed-v1/prose-CPU-v2-source-review.json'
PRIOR_SHA='829413a7f31bcd60a31297472283244c3a38b7956f7a64b9c51b8ecbc79442a6'
REVIEW=HERE/'INPUTS_SOURCE_ROOT_REVIEW_v2.json'
BASE_CONFIG='decode-optimization-20261028/model-v1/base-config.json'

ENV={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok,message):
    if not ok:raise ValueError(message)


def ids():
    tree=ast.parse((HERE/'test_ms_inputs.py').read_text())
    return sorted('test_ms_inputs.'+c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'))


def canonical_input(name):
    require(type(name) is str and name not in ('','.') and not Path(name).is_absolute() and '..' not in Path(name).parts,'Canonical relative input required')
    current=E
    require(not current.is_symlink(),'Evidence root alias')
    for part in Path(name).parts:
        current=current/part;require(not current.is_symlink(),'Input alias')
    require(current.is_file(),'Input missing')
    return current


def input_pins(review):
    require(sha(E/PRIOR)==PRIOR_SHA,'Inherited source inventory changed')
    old=json.loads((E/PRIOR).read_text())['source_input_sha256'];required={PRIOR:PRIOR_SHA}
    for name,pin in old.items():
        path=Path(os.path.normpath(str(E/name)))
        require(not Path(name).is_absolute() and path.is_relative_to(E),'Inherited input escapes evidence root')
        key=str(path.relative_to(E))
        require(key not in required or required[key]==pin,'Inherited alias digest collision');required[key]=pin
    # Parse literal source pin dictionaries without importing the new fixture module.
    tree=ast.parse((HERE/'ms_fixtures.py').read_text())
    literals={a.targets[0].id:ast.literal_eval(a.value) for a in tree.body if isinstance(a,ast.Assign)
              and isinstance(a.targets[0],ast.Name) and a.targets[0].id in ('SUPPORT_PINS','BASE_TOKENIZER_PINS')}
    # Frozen request pins are explicit below; no fixture import before custody.
    required[BASE_CONFIG]='c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'
    for name,pin in literals['SUPPORT_PINS'].items():required[name]=pin
    for name,pin in literals['BASE_TOKENIZER_PINS'].items():required['native-vision-v2/tokenizer/'+name]=pin
    required.update({'prefill-cache-improvements-20261027/numerical-fixtures/manifest.json':'251f89c1949f43308994a2a08805195ff7069eb4f11642920ed442168db10061',
        'decode-optimization-20261028/prose-speed-v1/prose-fixtures.json':'8039ba7415335710ab481c5cd29f3c2c1bffb19b223d83ec586baf759a336faf',
        'prefill-v2/frozen/manifest.json':'d3e557d528aeea5e3765f73f6454ddd657b204fb8be6aa3351618cfb739ecdb1'})
    supplied=review['input_sha256'];require(all(supplied.get(k)==v for k,v in required.items()),'Inherited/explicit input closure incomplete')
    actual={name:sha(canonical_input(name)) for name in supplied}
    require(actual==supplied,'Input source changed');return actual


def checked(pin):
    require(sha(REVIEW)==pin,'source review changed');r=json.loads(REVIEW.read_text())
    require(r['root_entire_source_and_tests_read'] is True and r['astra_entire_source_and_tests_read'] is True,'manual reviews required')
    sm={n:sha(HERE/n) for n in SOURCES};im=input_pins(r)
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
    suite=unittest.defaultTestLoader.loadTestsFromName('test_ms_inputs')
    def flatten(s):
        for t in s:
            if isinstance(t,unittest.TestSuite):yield from flatten(t)
            else:yield t.id()
    require(list(flatten(suite))==before[2],'discovered ordered IDs')
    result=unittest.TextTestRunner(verbosity=2).run(suite);require(checked(pin)==before,'post CPU source/input custody')
    import test_ms_inputs as tests
    manifests=tests.ACTUAL_MANIFESTS
    if result.wasSuccessful():require(set(manifests)=={'quality','prose','coding'},'Sole actual baseline encodings missing')
    encoded=json.dumps(manifests,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    with (out/'encoded-baseline-fixtures.json').open('xb') as f:f.write(encoded)
    receipt={'encoded_baseline_fixtures_sha256':hashlib.sha256(encoded).hexdigest(),'candidate_pack_encoded':False,'passed':result.wasSuccessful(),'controls':result.testsRun,'test_ids':before[2],'source_sha256':before[0],'input_sha256':before[1],'CPU_seconds':list(resource.getrlimit(resource.RLIMIT_CPU)),'Linux_AS_bytes':list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform=='linux' else None,'nice':os.getpriority(os.PRIO_PROCESS,0),'environment':ENV,'CPU_only':True,'native_model_executed':False}
    with (out/'receipt.json').open('x') as f:json.dump(receipt,f,indent=2)
    return 0 if result.wasSuccessful() else 1


def main(pin):
    before=checked(pin);host='linux' if sys.platform=='linux' else 'darwin';require(sys.platform in ('linux','darwin'),'physical CPU platform')
    out=HERE/('inputs-CPU-v2-'+host);out.mkdir();start=time.monotonic();p=None;error=None;errors=[];rc=None
    try:
        env=dict(os.environ,**ENV)
        with (out/'child.log').open('xb') as log:
            p=subprocess.Popen([sys.executable,'-B',str(HERE/'ms_inputs_cpu.py'),'--review-sha',pin,'--child',str(out)],cwd=HERE,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
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
        require(args.child==HERE/('inputs-CPU-v2-linux' if sys.platform=='linux' else 'inputs-CPU-v2-darwin'),'child output namespace')
        sys.exit(child(args.review_sha,args.child))
    sys.exit(main(args.review_sha))
