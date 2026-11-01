"""First bounded CPU proof of frozen existing direct-copy helpers, no model/GPU."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'maya145-mayas-v1/source-r2/src/ds4'
DRIVER=HERE.parent/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
NAMES=('direct_probe.cpp','run_cpu.py')
IDS=('aligned','unaligned','tiny','cross_page','exact_eof','numa_roles','scratch_reuse',
     'truncated','bad_fd_fallback','eintr_fallback','ioerror_fallback','zero_fallback',
     'zero_and_overflow','span_oracle','identity_replacement')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def checked(pin):
    review=HERE/'ROOT_SOURCE_REVIEW.json'
    if sha(review)!=pin or sha(DRIVER)!=DRIVER_SHA:raise ValueError('review/driver changed')
    r=json.loads(review.read_text())
    sources={n:sha(HERE/n) for n in NAMES}
    inputs={n:sha(SOURCE/n) for n in ('ds4_os.hpp','ds4_model.cu')}
    if r['source_sha256']!=sources or r['input_sha256']!=inputs or r['test_ids']!=list(IDS) or r['entire_source_tests_read'] is not True:
        raise ValueError('exact reviewed source/input/IDs changed')
    return r
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--review-sha256',required=True)
    ap.add_argument('--child',action='store_true');ap.add_argument('--parent',type=int);a=ap.parse_args()
    review=checked(a.review_sha256)
    spec=importlib.util.spec_from_file_location('bounded_direct_cpu',DRIVER);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
    folder=HERE/('CPU-FIRST-'+sys.platform)
    if not a.child:
        folder.mkdir()
        result=d.supervise([sys.executable,'-I','-B',str(Path(__file__).resolve()),'--review-sha256',a.review_sha256,'--child','--parent',str(os.getpid())],folder)
        print(json.dumps(result),flush=True)
        return 0 if result['returncode']==0 and result['error'] is None and result['cleanup']==[] else 1
    observed=d.observed();d.bounds(observed,os.getpid(),a.parent)
    header=(SOURCE/'ds4_os.hpp').read_text()
    begin=header.index('inline fd_t open_direct(');end=header.index('\n/// Windows: the file opened for unbuffered reads',begin)
    exact=header[begin:end]
    if hashlib.sha256(exact.encode()).hexdigest()!=review['exact_helper_sha256']:raise ValueError('exact helper extraction changed')
    (folder/'exact_helpers.inc').open('x').write(exact)
    binary=folder/'direct_probe'
    compiler='/usr/bin/clang++' if sys.platform=='darwin' else '/usr/bin/g++'
    build=subprocess.run([compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(folder),str(HERE/'direct_probe.cpp'),'-o',str(binary)],capture_output=True,text=True,timeout=30)
    (folder/'compile.log').open('x').write(build.stdout+build.stderr)
    if build.returncode:raise RuntimeError('CPU helper compilation failed; preserve first result')
    results=[]
    for control in IDS:
        result=subprocess.run([str(binary),control,str(folder/('fixture-'+control))],capture_output=True,text=True,timeout=5)
        print(result.stdout+result.stderr,end='',flush=True)
        if result.returncode!=0:raise RuntimeError('first CPU control failed: '+control)
        results.append({'id':control,'returncode':result.returncode,'stdout':result.stdout})
    if checked(a.review_sha256)!=review or d.observed()!=observed:raise ValueError('source/bounds drift')
    receipt={'passed':True,'controls':len(IDS),'test_ids':list(IDS),'source_sha256':review['source_sha256'],
        'input_sha256':review['input_sha256'],'observed':observed,'exact_helper_sha256':review['exact_helper_sha256'],
        'backend':'linux-real-O_DIRECT' if sys.platform=='linux' else 'darwin-buffered-algorithm-only',
        'compile_returncode':build.returncode,'compiler':compiler,'binary_sha256':sha(binary),'results':results,
        'native_executed':False,'device_executed':False,'whole_model_or_speed_proof':False}
    (folder/'receipt.json').open('x').write(json.dumps(receipt,indent=2)+'\n');return 0
if __name__=='__main__':raise SystemExit(main())
