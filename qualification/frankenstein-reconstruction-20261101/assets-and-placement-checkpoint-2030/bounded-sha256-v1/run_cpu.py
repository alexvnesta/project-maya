"""FIRST focused adapter controls only. No model/API/STATE execution in tests."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
DRIVER = HERE.parents[1] / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
NAMES = ('fork_hash.py', 'test_hash.py', 'run_cpu.py')
ENV = {'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
       'NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1',
       'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def sources(): return {n: sha(HERE/n) for n in NAMES}
def inputs():
    return {'qualified_supervisor': sha(DRIVER)}


def checked(pin):
    path = HERE/'ROOT_SOURCE_REVIEW.json'
    if sha(path) != pin or sha(DRIVER) != DRIVER_SHA: raise ValueError('Exact manual source/supervisor review')
    row = json.loads(path.read_text())
    if row.get('entire_source_tests_driver_manually_read') is not True or row.get('source_map') != sources() or row.get('input_map') != inputs():
        raise ValueError('Reviewed source/input drift')
    return row


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--child', action='store_true'); parser.add_argument('--parent', type=int)
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.dont_write_bytecode: raise ValueError('Use isolated Python -I -B')
    review = checked(args.review_sha256)
    spec = importlib.util.spec_from_file_location('essential_CPU_supervisor', DRIVER)
    d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
    if not args.child:
        folder = HERE/('CPU-FIRST-'+sys.platform); folder.mkdir()
        # Change only the injected child's environment, never qualified source.
        d.environment = lambda: dict(ENV)
        result = d.supervise([sys.executable,'-I','-B',str(HERE/'run_cpu.py'),'--review-sha256',args.review_sha256,
                              '--child','--parent',str(os.getpid())],folder)
        print(json.dumps(result),flush=True)
        return 0 if result['returncode'] == 0 and result['error'] is None and not result['cleanup'] else 1
    observed = d.observed(); d.bounds(observed,os.getpid(),args.parent)
    sys.path.insert(0,str(HERE))
    import fork_hash
    import test_hash
    if Path(fork_hash.__file__) != HERE/'fork_hash.py' or Path(test_hash.__file__) != HERE/'test_hash.py':
        raise ValueError('Foreign local test module')
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_hash); ids = d.flatten(suite)
    if ids != review['test_ids']: raise ValueError('Exact ordered focused controls')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(args.review_sha256) != review or d.observed() != observed: raise ValueError('CPU source/input/resource drift')
    receipt = {'passed':result.wasSuccessful(),'returncode':0 if result.wasSuccessful() else 1,
        'failures':len(result.failures),'errors':len(result.errors),'controls':result.testsRun,'test_ids':ids,
        'source_map':sources(),'input_map':inputs(),'observed':observed,'supervisor_pid':args.parent,
        'isolated':bool(sys.flags.isolated),'scope':'New pure adapter policy/custody only; no GPU/lifecycle/request qualification'}
    with (HERE/('CPU-FIRST-'+sys.platform+'.json')).open('x') as f: json.dump(receipt,f,indent=2); f.write('\n')
    return receipt['returncode']


if __name__ == '__main__': raise SystemExit(main())
