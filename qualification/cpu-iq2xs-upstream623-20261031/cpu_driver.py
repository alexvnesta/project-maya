"""One fresh portable qualification attempt. No build, native, GPU, or model mode."""
import argparse
import ast
import hashlib
import importlib
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
R = HERE.parents[2]
REMOTE = Path('/home/alex/strata-deepseek-test-20261024')
CPU_SECONDS = 30
AS_BYTES = 512 * 1024 * 1024
WALL_SECONDS = 90
RUN_SECONDS = 85  # leaves five seconds of the parent wall allowance for owned cleanup
ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
       'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1',
       'PYTHONDONTWRITEBYTECODE': '1'}
SOURCES = (
    'candidate/include/strata/kernels/cpu/iq_avx2.hpp',
    'candidate/include/strata/kernels/cpu/native_expert.hpp',
    'candidate/src/kernels/cpu/iq_avx2.cpp',
    'candidate/src/kernels/cpu/native_expert.cpp',
    'candidate.patch', 'source_contract.py', 'test_source_contract.py',
    'tests/iq2xs_exact.cpp', 'cpu_driver.py', 'test_cpu_driver.py',
)
TEST_MODULES = ('test_cpu_driver', 'test_source_contract')
# Filled literally from the physically corroborated source handoff, not imported code.
INPUTS = {'/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/adaptive-expert-cache-v1/SELECTED_CPU_LINK_OBSERVATION.json': '0a4d3f3fa2141afdab5f43f47eff11c014aa74558cb6d5a3c5d3765899164f0b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/adaptive-expert-cache-v1/SELECTED_CPU_SOURCE_BUILD_OBSERVATION.json': '7025fb879bc350998dc6de3aa3d58c5a490c1248046bf8c6eba580514d28e1ee',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/adaptive-expert-cache-v1/upstream-PR623-files-20261031T0438.json': 'c215f2fa974c7295635d99d7a3d893135263964740d1f56ff24d723e28aae62b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/SELECTED_MAIN_EXPERT_FORMATS_ROOT.json': '6f88898634629b9a7ec5fd5e7f54346e72f9bb8af1c11a76253463084c8113e6',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/base/include/strata/kernels/cpu/iq_avx2.hpp': '878cafbeef8144fd4e0b48f492f4812985ab4544dfb06c14523903a46821cd74',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/base/include/strata/kernels/cpu/native_expert.hpp': 'c22c92c0d18a6c045f9534d52b8cad51a8c8f25c58b2e138991d1708a9cdd050',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/base/src/ds4/ds4_iq_cpu.cpp': '7894f430fdfb48ba030ee9aff21414833e7f498052d322aeb33b53655da6118a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/base/src/kernels/cpu/iq_avx2.cpp': 'e4dddd81e6c657d677fff4f92c8a1167f0634ed323301ec2396bf30f231b81d4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/base/src/kernels/cpu/native_expert.cpp': '29c706324adaf639e553f266bda6ca1c0c6d755746622e1e80f0af0dbafa3de4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/inputs/selected-tensors.txt': 'bc5229fa509356053d07bbcc97e1245f05ac29934c9f92605b21659b4675c966',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/maya-s-comparison-v1/model-v1/selected-ds4_model.cu': 'dfe326d6a60d77354c8c92fb14ec423a92afff76b91f0810104f0a54a51a6350',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/selected-pack-quant-inventory-FIRST.json': '55a170d4e8c2dc758f19fb21f4b36836b91b43036ddc213599954b5378011f07'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and path.is_file() and
            not path.is_symlink() and path.stat().st_nlink == 1,
            'One regular pinned file required')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(REMOTE),
            'Canonical input path required')
    return R / path.relative_to(REMOTE)


def test_ids():
    ids = []
    for module in TEST_MODULES:
        tree = ast.parse((HERE / (module + '.py')).read_text())
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef):
                ids.extend(module + '.' + cls.name + '.' + f.name for f in cls.body
                           if isinstance(f, ast.FunctionDef) and f.name.startswith('test_'))
    require(ids and len(ids) == len(set(ids)), 'Literal nonempty unique controls required')
    return sorted(ids)


def checked(review_pin):
    require(isinstance(review_pin, str) and len(review_pin) == 64 and
            all(c in '0123456789abcdef' for c in review_pin), 'Exact review pin required')
    review_path = HERE / 'SOURCE_ROOT_REVIEW.json'
    require(digest(review_path) == review_pin, 'Manual review bytes changed')
    review = json.loads(review_path.read_text())
    require(review.get('root_entire_new_source_tests_and_candidate_delta_read') is True and
            review.get('astra_entire_new_source_tests_and_candidate_delta_read') is True, 'Both manual reads required')
    actual = {name: digest(HERE / name) for name in SOURCES}
    require(review.get('source_sha256') == actual, 'Exact source map required')
    require(INPUTS and review.get('input_sha256') == INPUTS, 'Exact literal input map required')
    require({key: digest(local(key)) for key in INPUTS} == INPUTS, 'Input bytes changed')
    ids = test_ids()
    require(review.get('test_ids') == ids, 'Exact current ordered controls required')
    return actual, dict(INPUTS), ids


def environment():
    env = dict(os.environ)
    for name in ('PYTHONPATH', 'PYTHONHOME'):
        env.pop(name, None)
    env.update(ENV)
    return env


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (AS_BYTES, AS_BYTES))
    nice = os.getpriority(os.PRIO_PROCESS, 0)
    require(nice <= 15, 'Unexpected inherited nice')
    os.nice(15 - nice)


def observed():
    return {'pid': os.getpid(), 'ppid': os.getppid(), 'pgid': os.getpgid(0),
            'cpu': list(resource.getrlimit(resource.RLIMIT_CPU)),
            'as': list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform == 'linux' else None,
            'nice': os.getpriority(os.PRIO_PROCESS, 0),
            'environment': {k: os.environ.get(k) for k in ENV}, 'platform': sys.platform,
            'dont_write_bytecode': sys.dont_write_bytecode}


def bounds(actual, pid, parent):
    require(type(pid) is int and pid > 1 and actual.get('pid') == pid and
            actual.get('ppid') == parent and actual.get('pgid') == pid, 'Actual child identity/group required')
    require(actual.get('cpu') == [30, 30] and actual.get('nice') == 15 and
            actual.get('environment') == ENV and actual.get('dont_write_bytecode') is True,
            'Actual child bounds/environment required')
    require(actual.get('platform') in ('linux', 'darwin'), 'Physical supported host required')
    require(actual.get('as') == ([AS_BYTES, AS_BYTES] if actual['platform'] == 'linux' else None),
            'Actual address-space bound required')


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def cleanup(process, owned_pgid, deadline):
    """Only the new-session group created for this exact Popen handle is eligible."""
    require(type(owned_pgid) is int and owned_pgid > 1 and owned_pgid == process.pid and
            owned_pgid != os.getpgrp(), 'Owned group identity refused')
    if process.poll() is None:
        require(os.getpgid(process.pid) == owned_pgid, 'Live child changed group')
    if group_alive(owned_pgid):
        try:
            os.killpg(owned_pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=min(0.2, max(0.001, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            pass
    if group_alive(owned_pgid):
        try:
            os.killpg(owned_pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
    while group_alive(owned_pgid) and time.monotonic() < deadline:
        time.sleep(0.01)
    require(not group_alive(owned_pgid), 'Owned descendants survive cleanup')


def supervise(argv, folder, *, run_seconds=RUN_SECONDS, wall_seconds=WALL_SECONDS):
    require(0 < run_seconds < wall_seconds <= 90, 'Bounded run and cleanup budget required')
    folder = Path(folder)
    require(folder.is_dir() and not folder.is_symlink(), 'Owned attempt directory required')
    started = time.monotonic(); process = None
    result = {'argv': list(argv), 'pid': None, 'returncode': None, 'error': None, 'cleanup': []}
    try:
        with (folder / 'child.log').open('xb') as stream:
            process = subprocess.Popen(argv, cwd=HERE, env=environment(), stdin=subprocess.DEVNULL,
                                       stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
                                       preexec_fn=limits)
            result['pid'] = process.pid
            result['returncode'] = process.wait(timeout=run_seconds)
            require(result['returncode'] == 0, 'Child nonzero')
    except BaseException as exc:
        result['error'] = repr(exc)
    finally:
        if process is not None:
            try:
                cleanup(process, process.pid, started + wall_seconds)
            except BaseException as exc:
                result['cleanup'].append(repr(exc))
            result['returncode'] = process.poll()
        result['elapsed_seconds'] = time.monotonic() - started
        with (folder / 'child.json').open('x') as f:
            json.dump(result, f, indent=2); f.write('\n')
    return result


def flatten(suite):
    return [case.id() for item in suite for case in
            (flatten_cases(item) if isinstance(item, unittest.TestSuite) else [item])]


def flatten_cases(suite):
    out = []
    for item in suite:
        out.extend(flatten_cases(item) if isinstance(item, unittest.TestSuite) else [item])
    return out


def attempt_contract(value, review_pin, parent_pid, before):
    require(value == {'review_sha256': review_pin, 'parent_pid': parent_pid,
                      'source_sha256': before[0], 'input_sha256': before[1], 'test_ids': before[2]},
            'Exact parent attempt custody required')


def child(review_pin, folder, parent_pid):
    actual = observed()
    bounds(actual, os.getpid(), parent_pid)
    before = checked(review_pin)  # before any project/test import
    require(folder.parent == HERE and folder.name == 'CPU-FIRST-' + sys.platform and
            folder.is_dir() and not folder.is_symlink(), 'Exact first attempt required')
    digest(folder / 'attempt.json')
    attempt_contract(json.loads((folder / 'attempt.json').read_text()), review_pin, parent_pid, before)
    with (folder / 'observed.json').open('x') as f:
        json.dump(actual, f, indent=2); f.write('\n')
    sys.path.insert(0, str(HERE))
    suite = unittest.TestSuite()
    for name in TEST_MODULES:
        module = importlib.import_module(name)
        require(Path(module.__file__).resolve() == HERE / (name + '.py'), 'Test module origin changed')
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    require(flatten(suite) == before[2], 'Actual loader order differs from frozen IDs')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = checked(review_pin)
    require(after == before, 'Inputs changed during controls')
    post = observed(); bounds(post, actual['pid'], parent_pid)
    require(post == actual, 'Child bounds changed')
    receipt = {'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'pid': actual['pid'],
               'review_sha256': review_pin, 'source_sha256': before[0], 'input_sha256': before[1],
               'source_after_sha256': after[0], 'input_after_sha256': after[1],
               'test_ids': before[2], 'tests_run': result.testsRun, 'observed': actual,
               'post_observed': post, 'failures': len(result.failures), 'errors': len(result.errors)}
    with (folder / 'receipt.json').open('x') as f:
        json.dump(receipt, f, indent=2); f.write('\n')
    return 0 if result.wasSuccessful() else 1


def parent(review_pin):
    before = checked(review_pin)
    require(sys.platform in ('linux', 'darwin'), 'Physical supported host required')
    folder = HERE / ('CPU-FIRST-' + sys.platform)
    folder.mkdir()  # exclusive; failure/partial proof is never overwritten
    with (folder / 'attempt.json').open('x') as f:
        json.dump({'review_sha256': review_pin, 'parent_pid': os.getpid(),
                   'source_sha256': before[0], 'input_sha256': before[1], 'test_ids': before[2]}, f, indent=2)
    argv = [sys.executable, '-I', '-B', str(HERE / 'cpu_driver.py'), '--child',
            '--review-pin', review_pin, '--parent-pid', str(os.getpid())]
    result = supervise(argv, folder)
    require(result['returncode'] == 0 and result['error'] is None and not result['cleanup'] and
            result['elapsed_seconds'] <= 90, 'Actual child/cleanup failed; preserve first attempt')
    require(checked(review_pin) == before, 'Post-child input change')
    receipt = json.loads((folder / 'receipt.json').read_text())
    actual = json.loads((folder / 'observed.json').read_text())
    bounds(actual, result['pid'], os.getpid())
    require(receipt.get('status') == 'PASS' and receipt.get('pid') == result['pid'] and
            receipt.get('review_sha256') == review_pin and receipt.get('observed') == actual and
            receipt.get('post_observed') == actual and receipt.get('failures') == 0 and
            receipt.get('errors') == 0 and receipt.get('tests_run') == len(before[2]) and
            receipt.get('test_ids') == before[2] and receipt.get('source_sha256') == before[0] and
            receipt.get('source_after_sha256') == before[0] and receipt.get('input_sha256') == before[1] and
            receipt.get('input_after_sha256') == before[1], 'Exact successful child receipt required')
    with (folder / 'parent.json').open('x') as f:
        json.dump({'status': 'PASS', 'pid': result['pid'], 'review_sha256': review_pin,
                   'receipt_sha256': digest(folder / 'receipt.json'),
                   'child_sha256': digest(folder / 'child.json'),
                   'log_sha256': digest(folder / 'child.log')}, f, indent=2)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--review-pin', required=True)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--parent-pid', type=int)
    args = parser.parse_args()
    if args.child:
        require(args.parent_pid is not None, 'Parent identity required')
        sys.exit(child(args.review_pin, HERE / ('CPU-FIRST-' + sys.platform), args.parent_pid))
    require(args.parent_pid is None, 'Parent-only arguments refused')
    sys.exit(parent(args.review_pin))
