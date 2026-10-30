"""FIRST bounded Q8 sharing kernel-controller CPU tests; all native/GPU actions mocked."""
import argparse
import ast
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import unittest

import build as c

HERE = Path(__file__).resolve().parent


def emit_new(path,value):
    with path.open('x') as stream:stream.write(json.dumps(value,indent=2,allow_nan=False)+'\n')

def source_pins(review):
    c.require(set(review['source_sha256'])=={'gpu_check.py','test_gpu_check.py'}, 'Exact owned source map required')
    c.require(c.sha(HERE/'qualify_gpu_cpu.py')==review['driver_sha256']
              and c.sha(HERE/'build.py')==review['build_support_sha256'], 'Driver/support changed')
    return {name: c.sha(HERE / name) for name in review['source_sha256']}


def test_ids():
    tree = ast.parse((HERE / 'test_gpu_check.py').read_text())
    return sorted('test_gpu_check.' + cls.name + '.' + fun.name
        for cls in tree.body if isinstance(cls, ast.ClassDef)
        for fun in cls.body if isinstance(fun, ast.FunctionDef) and fun.name.startswith('test_'))


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    os.nice(15)

def cleanup_child(process):
    errors = []
    for sig, seconds in ((signal.SIGTERM, 3), (signal.SIGKILL, 5)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except BaseException as exc:
            errors.append(repr(exc))
        try:
            process.wait(timeout=seconds)
        except BaseException as exc:
            errors.append(repr(exc))
        deadline = time.monotonic() + seconds
        while True:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return errors
            except BaseException as exc:
                errors.append(repr(exc))
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
    errors.append('Owned CPU process group still exists after cleanup')
    return errors


def main(child=False):
    guard = None
    if sys.platform == 'linux' and not child:
        inherited, _, runtime, _, host, binding = c.support()
        guard = lambda: inherited.guard(runtime, host, binding)
        guard()
    review = json.loads((HERE / 'gpu-source-review.json').read_text())
    pins = source_pins(review)
    ids = test_ids()
    c.require(review.get('all_source_and_tests_read') is True
              and review.get('source_sha256') == pins and review['test_ids'] == ids
              and c.sha(HERE / 'qualify_gpu_cpu.py') == review['driver_sha256']
              and c.sha(HERE / 'build.py') == review['build_support_sha256'],
              'Exact manual source/test review absent')
    out = HERE / ('gpu-CPU-' + sys.platform)
    if child:
        suite = unittest.defaultTestLoader.loadTestsFromName('test_gpu_check')
        def names(s):
            for item in s:
                if isinstance(item, unittest.TestSuite):
                    yield from names(item)
                else:
                    yield item.id()
        c.require(list(names(suite)) == ids, 'Actual test inventory differs')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        c.require(source_pins(review) == pins, 'Source changed during CPU proof')
        emit_new(out / 'receipt.json', {'passed': result.wasSuccessful(),
            'controls': result.testsRun, 'test_ids': ids, 'source_sha256': pins,
            'GPU_execution': False, 'compiler_execution': False, 'native_execution': False})
        return 0 if result.wasSuccessful() else 1
    c.require(sys.platform in ('darwin', 'linux'), 'Physical Mac or Ubuntu only')
    if out.exists() or out.is_symlink():raise ValueError('Existing proof; no replay')
    if guard:
        guard()
    out.mkdir()
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1', MALLOC_ARENA_MAX='1', PYTHONDONTWRITEBYTECODE='1')
    argv = [sys.executable, '-B', str(HERE / 'qualify_gpu_cpu.py'), '--child']
    process = None
    error = None
    code = None
    cleanup = []
    started = time.monotonic()
    with (out / 'child.log').open('x') as log:
        try:
            process = subprocess.Popen(argv, cwd=HERE, env=env, preexec_fn=limits,
                start_new_session=True, stdout=log, stderr=subprocess.STDOUT)
            while True:
                if guard:
                    guard()
                if time.monotonic() - started >= 90:
                    raise TimeoutError('CPU proof wall90')
                if (out / 'child.log').stat().st_size > 4 * 2**20:
                    raise ValueError('CPU proof output4MiB')
                code = process.poll()
                if code is not None:
                    break
                time.sleep(0.2)
        except BaseException as exc:
            error = repr(exc)
            if process is not None:
                cleanup = cleanup_child(process)
                code = process.returncode
    emit_new(out / 'child.json', {'argv': argv, 'pid': process.pid if process else None,
        'returncode': code, 'CPU_s': 30, 'wall_s': 90, 'nice': 15, 'CUDA_hidden': True,
        'Linux_AS_MiB': 512 if sys.platform == 'linux' else None, 'error': error,
        'cleanup_errors': cleanup})
    c.require(code == 0 and error is None and not cleanup, 'FIRST CPU proof HOLD, preserve raw')
    if guard:guard()
    c.require(source_pins(review) == pins, 'Source changed after CPU proof')
    print(json.dumps({'passed': True, 'controls': len(ids), 'host': sys.platform}))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    raise SystemExit(main(args.child))

