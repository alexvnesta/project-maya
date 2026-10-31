"""Compile and test a lossless CPU byte-layout converter; no model or GPU action."""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
NAMES = ('mxpack.cpp','test_mxpack.py','run_codec_cpu.py')
DRIVER = HERE.parent / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_paths(root):
    return {'upstream-lossless-format-reference':HERE.parent/'maya145-mayas-v1/source-r2/tools/ds4/drafter_pack.py','CPU-supervisor':DRIVER}


def checked(pin, root):
    path = HERE / 'CODEC_SOURCE_ROOT_REVIEW.json'
    if sha(path) != pin or sha(DRIVER) != DRIVER_SHA:
        raise ValueError('Manual review or supervisor changed')
    review = json.loads(path.read_text())
    rows = {n: sha(HERE / n) for n in NAMES}
    inputs = {n: sha(p) for n,p in input_paths(root).items()}
    if rows != review['source_sha256'] or inputs != review['input_sha256'] or review['root_source_read'] is not True or review['sol_source_read'] is not True:
        raise ValueError('Reviewed source/config/native schema changed')
    return review


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--review-sha256', required=True)
    ap.add_argument('--input-root', type=Path, required=True)
    ap.add_argument('--child', action='store_true')
    ap.add_argument('--parent', type=int)
    a = ap.parse_args()
    if not a.input_root.is_absolute() or a.input_root.resolve() != a.input_root:
        raise ValueError('Exact source root required')
    review = checked(a.review_sha256, a.input_root)
    spec = importlib.util.spec_from_file_location('bounded_profile_supervisor', DRIVER)
    d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
    folder = HERE / ('CODEC-CPU-FIRST-' + sys.platform)
    if not a.child:
        folder.mkdir()
        result = d.supervise([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
            '--review-sha256', a.review_sha256, '--input-root', str(a.input_root),
            '--child', '--parent', str(os.getpid())], folder)
        print(json.dumps(result), flush=True)
        return 0 if result['returncode'] == 0 and result['error'] is None and not result['cleanup'] else 1
    observed = d.observed(); d.bounds(observed, os.getpid(), a.parent)
    sys.path.insert(0, str(HERE))
    import test_mxpack as tests
    if Path(tests.__file__).resolve() != HERE / 'test_mxpack.py':
        raise ValueError('Actual profile/test import origin changed')
    compiler=Path(shutil.which('c++')).resolve()
    exe=folder/'mxpack'
    if exe.exists() or exe.is_symlink():raise ValueError('Preserve previous converter artifact')
    argv=[str(compiler),'-std=c++17','-O2',str(HERE/'mxpack.cpp'),'-o',str(exe)]
    with (folder/'compile.stdout').open('xb') as out,(folder/'compile.stderr').open('xb') as err:
        built=subprocess.run(argv,stdout=out,stderr=err,timeout=30,check=False)
    if built.returncode!=0 or not exe.is_file() or exe.is_symlink():raise ValueError('Actual converter compile failed')
    version=subprocess.run([str(compiler),'--version'],capture_output=True,text=True,timeout=5,check=True).stdout
    artifact={'compiler':str(compiler),'compiler_sha256':sha(compiler),'compiler_version':version,'argv':argv,'returncode':built.returncode,'executable':str(exe),'sha256':sha(exe),'source_sha256':sha(HERE/'mxpack.cpp')}
    (folder/'compile.json').open('x').write(json.dumps(artifact,indent=2)+'\n')
    os.environ['MXPACK_CPU_BINARY']=str(exe)
    suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
    ids = d.flatten(suite)
    if ids != review['test_ids']:
        raise ValueError('Actual ordered controls changed')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(a.review_sha256, a.input_root) != review or d.observed() != observed:
        raise ValueError('Source or resource drift')
    receipt = {'passed': result.wasSuccessful(), 'controls': result.testsRun, 'test_ids': ids,
        'source_sha256': review['source_sha256'], 'input_sha256': review['input_sha256'], 'observed': observed,
        'inference_native_executed': False, 'CPU_converter_executed': True, 'device_executed': False, 'model_quality_or_speed_proof': False,'converter':artifact}
    (folder / 'receipt.json').open('x').write(json.dumps(receipt, indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
