"""Lossless three-role MXFP4 CPU codec proof only, in one bounded child per physical host."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
NAMES = ('mxpack.cpp', 'test_codec.py', 'run_cpu.py')
ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
       'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1'}


def pins():
    return {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in NAMES}


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test.id()


def child(label):
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    os.nice(15)
    assert all(os.environ[k] == v for k, v in ENV.items())
    import test_codec
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_codec)
    ids = list(flatten(suite))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    proof = {'physical_host': label, 'passed': result.wasSuccessful(),
             'returncode': 0 if result.wasSuccessful() else 1,
             'controls': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
             'test_ids': ids, 'source_sha256': pins(), 'environment': ENV,
             'CPU_seconds': list(resource.getrlimit(resource.RLIMIT_CPU)),
             'Linux_AS_bytes': list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform.startswith('linux') else None,
             'nice': os.getpriority(os.PRIO_PROCESS, 0), 'pid': os.getpid(),
             'scope': 'Lossless CPU byte-layout codec only; no native inference/GPU/model quality or speed proof'}
    with (HERE / ('CPU-FIRST-' + label + '.json')).open('x') as f:
        json.dump(proof, f, indent=2); f.write('\n')
    return proof['returncode']


if __name__ == '__main__':
    if sys.argv[1] == 'child':
        raise SystemExit(child(sys.argv[2]))
    label = sys.argv[1]
    assert label in ('mac', 'ubuntu')
    assert (sys.platform == 'darwin') if label == 'mac' else sys.platform.startswith('linux')
    for name in ('CPU-FIRST-' + label + '.json', 'CPU-FIRST-' + label + '.log', 'child-FIRST-' + label + '.json'):
        assert not (HERE / name).exists(), 'Preserve FIRST evidence'
    review = json.loads((HERE / 'ROOT_SOURCE_REVIEW.json').read_text())
    assert review['entire_source_tests_driver_manually_read'] is True
    assert review['source_sha256'] == pins(), 'Manual source review must match before FIRST child'
    env = dict(os.environ, **ENV)
    with (HERE / ('CPU-FIRST-' + label + '.log')).open('x') as out:
        process = subprocess.Popen([sys.executable, '-B', str(Path(__file__)), 'child', label],
                                   cwd=HERE, env=env, stdin=subprocess.DEVNULL,
                                   stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            rc = process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            rc = process.wait()
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    cleanup = []
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        pass
    else:
        os.killpg(process.pid, signal.SIGKILL)
        cleanup.append('Descendant process group remained after CPU child exit')
    with (HERE / ('child-FIRST-' + label + '.json')).open('x') as f:
        json.dump({'pid': process.pid, 'returncode': rc, 'timed_out': timed_out,
                   'wall_seconds': 90, 'source_sha256': pins(), 'cleanup_errors': cleanup}, f, indent=2)
        f.write('\n')
    raise SystemExit(124 if timed_out else 1 if cleanup else rc)
