"""FIRST C++ policy compile/run; child CPU30, LinuxAS512MiB, wall90, CUDA hidden."""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import iq2s_build as c
from qualify_iq2s_build_cpu import source_pins, cleanup_child

HERE = Path(__file__).resolve().parent


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    os.nice(15)


def main():
    c.require(sys.platform in ('linux', 'darwin'), 'Physical Mac or Ubuntu only')
    review = json.loads((HERE / 'source-review-root.json').read_text())
    pins = source_pins(review)
    c.require(review.get('all_source_and_tests_read') is True and pins == review['source_sha256'],
              'Exact full source review absent')
    ids = review['policy_test_ids']
    c.require(type(ids) is list and ids and len(ids) == len(set(ids)), 'Exact policy IDs required')
    guard = None
    if sys.platform == 'linux':
        _, runtime, _, host, binding = c.support()
        guard = lambda: c.guard(runtime, host, binding)
        guard()
    out = HERE / ('policy-CPU-FIRST-' + sys.platform)
    c.fresh(out)
    compiler = Path('/usr/bin/c++')
    before_tool = {'path': str(compiler), 'resolved': str(compiler.resolve(strict=True)),
                   'sha256': c.sha(compiler)}
    if guard:
        guard()
    out.mkdir()
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1', MALLOC_ARENA_MAX='1', PYTHONDONTWRITEBYTECODE='1')
    jobs = [('compile', [str(compiler), '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
             str(HERE / 'candidate/tests/ds4_iq2s_persist_policy_test.cpp'),
             '-o', str(out / 'policy-test')]),
            ('run', [str(out / 'policy-test')])]
    children = []
    for name, command in jobs:
        if guard:
            guard()
        c.require(source_pins(review) == pins and c.sha(compiler) == before_tool['sha256']
                  and str(compiler.resolve(strict=True)) == before_tool['resolved'], 'Source/compiler changed')
        process = None
        primary = None
        code = None
        cleanup = []
        began = time.monotonic()
        with (out / (name + '.stdout')).open('x') as stdout, (out / (name + '.stderr')).open('x') as stderr:
            try:
                process = subprocess.Popen(command, env=env, preexec_fn=limits, start_new_session=True,
                                           stdout=stdout, stderr=stderr)
                while True:
                    if guard:
                        guard()
                    if time.monotonic() - began >= 90:
                        raise TimeoutError('Policy child wall90')
                    for ext in ('stdout', 'stderr'):
                        if (out / (name + '.' + ext)).stat().st_size > 2**20:
                            raise ValueError('Policy output1MiB')
                    code = process.poll()
                    if code is not None:
                        break
                    time.sleep(0.2)
            except BaseException as exc:
                primary = repr(exc)
                if process is not None:
                    cleanup = cleanup_child(process)
                    code = process.returncode
        row = {'argv': command, 'pid': process.pid if process else None, 'returncode': code,
               'CPU_s': 30, 'wall_s': 90, 'Linux_AS_MiB': 512 if sys.platform == 'linux' else None,
               'CUDA_hidden': True, 'nice': 15, 'error': primary, 'cleanup_errors': cleanup}
        c.emit_new(out / (name + '.json'), row)
        children.append(row)
        c.require(code == 0 and primary is None and not cleanup, 'FIRST policy child HOLD; no next/retry')
    expected = ''.join('PASS ' + test_id + '\n' for test_id in ids) + 'ALL ' + str(len(ids)) + ' policy checks passed\n'
    c.require((out / 'run.stdout').read_text() == expected, 'Policy counts/IDs/results differ')
    c.require(source_pins(review) == pins and c.sha(compiler) == before_tool['sha256'],
              'Post proof source/compiler custody differs')
    receipt = {'passed': True, 'controls': len(ids), 'test_ids': ids, 'source_sha256': pins,
               'children': children, 'compiler': before_tool, 'host': sys.platform,
               'GPU_execution': False, 'CUDA_compilation': False}
    c.emit_new(out / 'receipt.json', receipt)
    print(json.dumps({'passed': True, 'controls': len(ids), 'host': sys.platform}))


if __name__ == '__main__':
    main()

