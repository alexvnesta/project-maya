"""FIRST exact bounded controls; CUDA hidden, no native/model execution."""
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

HERE = Path(__file__).resolve().parent
MODULES = ('test_head_build',)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pins(review):
    values = {}
    for name, pin in review['source_sha256'].items():
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Source outside exact owned tree')
        values[name] = sha(HERE / rel)
        if values[name] != pin: raise ValueError('Reviewed source changed')
    inputs = {}
    for name, pin in review['source_input_sha256'].items():
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts: raise ValueError('Input outside frozen evidence root')
        path = HERE.parents[1] / rel
        inputs[name] = sha(path)
        if inputs[name] != pin: raise ValueError('Frozen helper input changed')
    return values, inputs


def ids():
    result = []
    for module in MODULES:
        tree = ast.parse((HERE / (module + '.py')).read_text())
        result.extend(sorted(module + '.' + cls.name + '.' + fn.name
            for cls in tree.body if isinstance(cls, ast.ClassDef)
            for fn in cls.body if isinstance(fn, ast.FunctionDef) and fn.name.startswith('test_')))
    return result


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    if sys.platform == 'linux': resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    os.nice(15)


def cleanup(process):
    errors = []
    for sig, seconds in ((signal.SIGTERM, 3), (signal.SIGKILL, 5)):
        try: os.killpg(process.pid, sig)
        except ProcessLookupError: pass
        except BaseException as exc: errors.append(repr(exc))
        try: process.wait(timeout=seconds)
        except BaseException as exc: errors.append(repr(exc))
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try: os.killpg(process.pid, 0)
            except ProcessLookupError: return errors
            time.sleep(.05)
    return errors + ['Owned CPU process group still exists']


def emit(path, value):
    with path.open('x') as f: f.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def policy_output(text, expected):
    lines = text.splitlines()
    actual = [line[5:] for line in lines if line.startswith('PASS ')]
    if actual != expected or lines[-1:] != ['ALL ' + str(len(expected)) + ' HEAD_BATCH policy checks passed']:
        raise ValueError('Exact policy controls/summary differ')


def policy(review, sources, guard):
    manifest = json.loads((HERE / 'candidate-files.json').read_text())
    expected = manifest['policy_test_ids']
    out = HERE / ('policy-CPU-FIRST-' + sys.platform)
    if guard: guard()
    if out.exists() or out.is_symlink(): raise ValueError('Existing policy proof; no replay')
    out.mkdir()
    commands = [('compile', ['/usr/bin/c++', '-std=c++17', '-O2',
        str(HERE / 'candidate/tests/head_batch_policy_test.cpp'), '-o', str(out / 'policy-check')]),
        ('run', [str(out / 'policy-check')])]
    children = []
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               MALLOC_ARENA_MAX='1', PYTHONDONTWRITEBYTECODE='1')
    for name, command in commands:
        if guard: guard()
        process = None; code = None; error = None; errors = []
        with (out / (name + '.stdout')).open('xb') as stdout, (out / (name + '.stderr')).open('xb') as stderr:
            try:
                process = subprocess.Popen(command, cwd=HERE, env=env, preexec_fn=limits,
                    start_new_session=True, stdout=stdout, stderr=stderr)
                start = time.monotonic()
                while True:
                    if guard: guard()
                    if time.monotonic() - start > 90: raise TimeoutError('Policy wall90')
                    if sum((out / (name + suffix)).stat().st_size for suffix in ('.stdout', '.stderr')) > 4 * 2**20:
                        raise ValueError('Policy log4MiB')
                    code = process.poll()
                    if code is not None: break
                    time.sleep(.1)
            except BaseException as exc:
                error = repr(exc)
                if process is not None: errors = cleanup(process); code = process.returncode
        row = {'argv': command, 'pid': process.pid if process else None, 'returncode': code,
               'CPU_s': 30, 'wall_s': 90, 'nice': 15, 'CUDA_hidden': True,
               'Linux_AS_MiB': 512 if sys.platform == 'linux' else None, 'error': error, 'cleanup_errors': errors}
        emit(out / (name + '.json'), row); children.append(row)
        if code != 0 or error is not None or errors: raise ValueError('FIRST policy proof HOLD; preserve raw')
        if pins(review)[0] != sources: raise ValueError('Source changed during policy proof')
    policy_output((out / 'run.stdout').read_text(), expected)
    if (out / 'compile.stderr').read_bytes() or (out / 'run.stderr').read_bytes():
        raise ValueError('Policy compiler/run stderr requires review')
    emit(out / 'receipt.json', {'passed': True, 'controls': len(expected), 'test_ids': expected,
        'source_sha256': sources, 'children': children, 'GPU_execution': False, 'CUDA_compilation': False})


def main(child=False):
    guard = None
    if sys.platform == 'linux' and not child:
        import head_build
        c, b, runtime, a, host, binding = head_build.support()
        guard = lambda: c.guard(runtime, host, binding)
        guard()
    review = json.loads((HERE / 'BUILD_CPU_SOURCE_REVIEW.json').read_text())
    sources, inputs = pins(review); ordered = ids()
    if review.get('all_source_and_tests_read') is not True or review['test_ids'] != ordered:
        raise ValueError('Exact manual review absent')
    out = HERE / ('build-CPU-FIRST-' + sys.platform)
    if child:
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(module) for module in MODULES)
        def names(items):
            for item in items:
                if isinstance(item, unittest.TestSuite): yield from names(item)
                else: yield item.id()
        if list(names(suite)) != ordered: raise ValueError('Actual test IDs differ')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if pins(review) != (sources, inputs): raise ValueError('Source changed during proof')
        emit(out / 'receipt.json', {'passed': result.wasSuccessful(), 'controls': result.testsRun,
            'test_ids': ordered, 'source_sha256': sources, 'source_input_sha256': inputs,
            'GPU_execution': False, 'native_execution': False, 'compiler_execution': False})
        return 0 if result.wasSuccessful() else 1
    if sys.platform not in ('darwin', 'linux'): raise ValueError('Physical Mac/Ubuntu only')
    if guard: guard()
    if out.exists() or out.is_symlink(): raise ValueError('Existing proof; no replay')
    out.mkdir()
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               MALLOC_ARENA_MAX='1', PYTHONDONTWRITEBYTECODE='1')
    process = None; code = None; error = None; errors = []
    with (out / 'child.log').open('x') as log:
        try:
            if guard: guard()
            process = subprocess.Popen([sys.executable, '-B', str(HERE / 'qualify_build_cpu.py'), '--child'],
                cwd=HERE, env=env, preexec_fn=limits, start_new_session=True, stdout=log, stderr=subprocess.STDOUT)
            start = time.monotonic()
            while True:
                if guard: guard()
                if time.monotonic() - start > 90: raise TimeoutError('CPU wall90')
                if (out / 'child.log').stat().st_size > 4 * 2**20: raise ValueError('CPU log4MiB')
                code = process.poll()
                if code is not None: break
                time.sleep(.2)
        except BaseException as exc:
            error = repr(exc)
            if process is not None: errors = cleanup(process); code = process.returncode
    emit(out / 'child.json', {'pid': process.pid if process else None, 'returncode': code,
        'CPU_s': 30, 'wall_s': 90, 'nice': 15, 'CUDA_hidden': True,
        'Linux_AS_MiB': 512 if sys.platform == 'linux' else None, 'error': error, 'cleanup_errors': errors})
    if code != 0 or error is not None or errors: raise ValueError('FIRST CPU proof HOLD; preserve raw')
    if guard: guard()
    if pins(review) != (sources, inputs): raise ValueError('Source changed after proof')
    policy(review, sources, guard)
    print(json.dumps({'passed': True, 'controls': len(ordered), 'host': sys.platform}))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--child', action='store_true')
    args = parser.parse_args(); raise SystemExit(main(args.child))
