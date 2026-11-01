"""FIRST exact acquisition controls in a bounded CUDA-hidden child on each physical host."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
CONTROLS = {'CPU_seconds':30,'wall_seconds':90,'nice_increment':15,'CUDA_VISIBLE_DEVICES':'',
            'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','Linux_AS_bytes':512*2**20}


def source_map():
    return {n:hashlib.sha256((HERE/n).read_bytes()).hexdigest()
            for n in ['acquire.py','test_acquire.py','run_cpu.py','ASSET_MANIFEST.json']}


def child(label):
    resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    if sys.platform.startswith('linux'): resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20))
    os.nice(15)
    assert all(os.environ[k]==CONTROLS[k] for k in ['CUDA_VISIBLE_DEVICES','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MALLOC_ARENA_MAX'])
    import test_acquire
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_acquire)
    def flatten(s):
        for t in s:
            if isinstance(t,unittest.TestSuite):yield from flatten(t)
            else:yield t.id()
    ids=list(flatten(suite))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    receipt={'physical_host':label,'passed':result.wasSuccessful(),'returncode':0 if result.wasSuccessful() else 1,
             'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'test_ids':ids,'source_map':source_map(),'child_controls':CONTROLS,
             'actual_child_CPU_limit':list(resource.getrlimit(resource.RLIMIT_CPU)),
             'actual_child_Linux_AS_limit':list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform.startswith('linux') else None,
             'actual_child_nice':os.getpriority(os.PRIO_PROCESS,0)}
    path=HERE/('CPU-FIRST-'+label+'.json')
    with path.open('x') as f:f.write(json.dumps(receipt,indent=2)+'\n')
    raise SystemExit(receipt['returncode'])


if __name__=='__main__':
    if sys.argv[1]=='child':child(sys.argv[2])
    label=sys.argv[1]
    assert label in ['mac','ubuntu'] and ((sys.platform=='darwin') if label=='mac' else sys.platform.startswith('linux'))
    assert not (HERE/('CPU-FIRST-'+label+'.json')).exists(), 'FIRST CPU receipt already exists'
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MALLOC_ARENA_MAX='1',PYTHONDONTWRITEBYTECODE='1')
    log=HERE/('CPU-FIRST-'+label+'.log')
    with log.open('x') as out:
        result=subprocess.run([sys.executable,'-B',str(Path(__file__)),'child',label],cwd=HERE,env=env,
                              stdout=out,stderr=subprocess.STDOUT,timeout=90)
    raise SystemExit(result.returncode)
