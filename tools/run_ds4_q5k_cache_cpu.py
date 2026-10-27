"""Bounded CPU controls for cache admission and the actual mapped-input guard.

Never imports CUDA, executes a native engine, or changes serving state.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess

def extract_tick(source):
    start=source.index('    void tick_flush() {')
    opened=source.index('{',start);depth=1;end=opened+1
    while depth:
        if source[end]=='{':depth+=1
        elif source[end]=='}':depth-=1
        end+=1
    return source[start:end]+'\n'

def run(root,output,fragment=None):
    output.mkdir(parents=True,exist_ok=False)
    text=Path(fragment).read_text() if fragment else extract_tick((root/'src/ds4/ds4_model.cu').read_text())
    if text!=extract_tick(text):raise ValueError('Fragment is not exactly one production method')
    (output/'native_tick_flush.inc').write_text(text)
    files=[root/'src/ds4/ds4_cache_admission.hpp',root/'tests/ds4_q5k_cache_cpu_test.cpp',
           root/'tests/ds4_cache_publication_cpu_test.cpp']
    pins={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    pins['native_tick_flush.inc']=hashlib.sha256(text.encode()).hexdigest()
    linux=platform.system()=='Linux'
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU,(30,30))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        if linux:resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20))
        os.nice(15)
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
             MALLOC_ARENA_MAX='1',PYTHONDONTWRITEBYTECODE='1')
    receipts=[]
    for name in ['ds4_q5k_cache_cpu_test','ds4_cache_publication_cpu_test']:
        commands=[('/usr/bin/c++','-std=c++17','-O1','-Wall','-Wextra','-Werror','-pthread',
                   '-I',str(output),str(root/'tests'/(name+'.cpp')),'-o',str(output/name)),
                  (str(output/name),)]
        for phase,cmd in zip(['compile','run'],commands):
            with (output/(name+'-'+phase+'.log')).open('x') as log:
                child=subprocess.run(cmd,cwd=root,env=env,preexec_fn=limits,timeout=90,
                                     stdout=log,stderr=subprocess.STDOUT)
            row=dict(test=name,phase=phase,returncode=child.returncode,CPU_s=30,wall_s=90,
                     Linux_AS_MiB=512 if linux else None,nice=15,CUDA_hidden=True)
            receipts.append(row)
            (output/'children.json').write_text(json.dumps(receipts,indent=2)+'\n')
            if child.returncode:
                raise RuntimeError((output/(name+'-'+phase+'.log')).read_text())
    ids=[]
    for name in ['ds4_q5k_cache_cpu_test','ds4_cache_publication_cpu_test']:
        ids += [x[5:] for x in (output/(name+'-run.log')).read_text().splitlines() if x.startswith('PASS ')]
    if len(ids)!=19 or len(set(ids))!=19:raise ValueError('Unexpected control inventory')
    receipt=dict(passed=True,controls=19,IDs=ids,source_sha256=pins,CPU_only=True,
                 native_or_CUDA_executed=False,scope='Policy/integer layout and actual tick_flush with CPU delayed reads; no CUDA/native proof')
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--tick-fragment',type=Path)
    a=p.parse_args();run(a.source_root.resolve(),a.output.resolve(),a.tick_fragment)
