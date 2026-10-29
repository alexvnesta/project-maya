"""Six read-only cuobjdump children. No compilation, native loading or GPU use.

The existing cooperative CPU reservation coordinates with other owned work; it
is not an OS lock. Raw disassembly is evidence, not a numerical acceptance test.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import selectors
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
R = Path('/home/alex/strata-deepseek-test-20261024')
E = R / 'reliability-optimization-20261025'
P = E / 'decode-optimization-20261028'
M = P / 'model-v1'
EXPECTED_HERE = M / 'static-diagnostic-v1'
TOOL = Path('/usr/local/cuda/bin/cuobjdump')
TOOL_REAL = Path('/usr/local/cuda-13.3/bin/cuobjdump')
TOOL_SHA = '2498659e83ab63ffd63b560caf3078e2c8d2839aa331780d2861cdf485070485'
NUMERIC_Q = '6eb179b8b7edb7a87133c4e24bd99dc2f35863cfe6ef56f8385590bf50c6315b'
RUNTIME_SHA = '157b7750a2da5d495c08ece100d19432d48fe52aeaac9e982a63762dd742425e'
CONFIG_SHA = '18691963f89027fd169877c0cd6307f54954de1353a577d4c8935c015ea84986'
OBJECTS = {
    'old': (R / 'maya-build-sm80-ablate469-v2/CMakeFiles/maya-ds4.dir/src/ds4/ds4_iq.cu.o',
            'b47a95712a6be578cc4afe3fc48db1e42db0c9bd8aad0b124029f91105202514'),
    'candidate': (P / 'build-FIRST/ds4_iq.cu.o',
                  '19800554edcd3031e1876e335530d00693dd591844a87fa136a1f3bec8e85cfe'),
}
CPU, WALL, ADDRESS_SPACE = 30, 90, 512 * 2**20
STREAM_LIMITS = {'stdout': 64 * 2**20, 'stderr': 2**20}
TOTAL_LIMIT = 384 * 2**20
SOURCES = ('static_diagnostic.py', 'test_static_diagnostic.py')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def real_directory(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'Canonical directory required')
    for item in [*reversed(path.parents), path]:
        require(not item.is_symlink() and item.is_dir(), 'Non-real directory ancestor')


def fresh_leaf(path):
    real_directory(path.parent)
    require(not path.is_symlink() and not path.exists(), 'Existing output or alias refused')


def emit_new(path, value):
    real_directory(path.parent)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def commands():
    return [(label + '-' + kind,
             [str(TOOL), '--gpu-architecture', 'sm_80', option, str(pair[0])])
            for label, pair in OBJECTS.items()
            for kind, option in [('sass', '--dump-sass'),
                                 ('resources', '--dump-resource-usage'),
                                 ('elf', '--dump-elf')]]


def check_inputs():
    require(TOOL.resolve(strict=True) == TOOL_REAL and TOOL.is_file()
            and sha(TOOL) == TOOL_SHA, 'Disassembler alias/content changed')
    for path, pin in OBJECTS.values():
        require(not path.is_symlink() and path.is_file() and sha(path) == pin,
                'Original/candidate object changed')


def qualification(expected_digest):
    """Check full proof after the minimal pinned guard has established fresh idle."""
    path = HERE / 'qualification.json'
    require(not path.is_symlink() and sha(path) == expected_digest, 'Qualification digest differs')
    q = json.loads(path.read_text())
    require(q.get('source_manually_reviewed') is True and q.get('CPU_both_hosts_passed') is True,
            'Both manual and bounded CPU proof required')
    sources = {name: sha(HERE / name) for name in SOURCES}
    ids = q['test_ids']
    require(q['source_sha256'] == sources and type(ids) is list and ids
            and all(type(x) is str for x in ids) and len(ids) == len(set(ids)), 'Exact source/test map absent')
    prior = M / 'numerical-qualification.json'
    require(sha(prior) == NUMERIC_Q, 'Inherited source qualification differs')
    inherited = json.loads(prior.read_text())['files']
    required = {k: v for k, v in inherited.items() if k.endswith('.py')}
    required.update({str(prior): NUMERIC_Q, str(M / 'imma_model_runtime.py'): RUNTIME_SHA,
                     str(M / 'imma_config.py'): CONFIG_SHA,
                     **{str(HERE / k): v for k, v in sources.items()}})
    tool_receipt = M / 'offline-sass-tool-FIRST/receipt.json'
    required[str(tool_receipt)] = sha(tool_receipt)
    for label in ('darwin', 'linux'):
        for name in ('receipt.json', 'child.json', 'child.log'):
            f = HERE / ('CPU-FIRST-' + label) / name
            required[str(f)] = sha(f)
    require(all(q['files'].get(k) == v for k, v in required.items()), 'Source/raw/import closure pin missing')
    for name, pin in q['files'].items():
        f = Path(name)
        require(f.is_absolute() and '..' not in f.parts and sha(f) == pin, 'Pinned qualification input changed')
    for label in ('darwin', 'linux'):
        folder = HERE / ('CPU-FIRST-' + label)
        receipt = json.loads((folder / 'receipt.json').read_text())
        child = json.loads((folder / 'child.json').read_text())
        require(receipt.get('passed') is True and receipt.get('source_sha256') == sources
                and receipt.get('test_ids') == ids and type(receipt.get('controls')) is int
                and receipt['controls'] == len(ids) and receipt.get('GPU_execution') is False
                and receipt.get('compiler_execution') is False, 'Exact CPU result mismatch')
        limits = {'returncode': 0, 'CPU_s': 30, 'wall_s': 90, 'nice': 15,
                  'CUDA_hidden': True, 'Linux_AS_MiB': 512 if label == 'linux' else None}
        require(all(type(child.get(k)) is type(v) and child[k] == v for k, v in limits.items()),
                'Bounded CPU child proof mismatch')
    require(sha(path) == expected_digest, 'Qualification changed during read')
    return q


def load_support():
    for name, pin in [('imma_model_runtime', RUNTIME_SHA), ('imma_config', CONFIG_SHA)]:
        path = M / (name + '.py')
        require(sha(path) == pin, 'Shared guard source changed')
        module = sys.modules.get(name)
        require(module is None or Path(module.__file__).resolve() == path, 'Foreign same-name module')
    sys.path.insert(0, str(M))
    runtime = importlib.import_module('imma_model_runtime')
    a, _ = runtime.support()
    state = json.loads((E / 'STATE.json').read_text())
    binding = runtime.current_binding(state)
    host = a.ChunkProductionHost()
    host.start_binding = dict(binding)
    return runtime, a, host, binding


def guard(runtime, host, binding, reservation=None):
    state = json.loads((E / 'STATE.json').read_text())
    for key in runtime.PHASE_KEYS:
        if key == 'active_cpu_build' and reservation is not None:
            require(state.get(key) == reservation, 'Owned CPU reservation changed')
        else:
            require(not state.get(key), 'Other active/pending/stopped phase')
    require(runtime.current_binding(state) == binding, 'Canonical selected owner changed')
    require(host.idle(), 'DEFERRED_BUSY_UNTOUCHED_OR_STOP_OWNED_CHILD')
    host.guard_binding()
    require(shutil.disk_usage('/').free >= 132 * 2**30, 'Root132 reserve unavailable')
    return state


def child_limits():
    resource.setrlimit(resource.RLIMIT_CPU, (CPU, CPU))
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_SPACE, ADDRESS_SPACE))
    os.nice(15)


def group_alive(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def cleanup(child):
    """Only the freshly spawned child's session/process group; retain all errors."""
    errors = []
    for sig, seconds in [(signal.SIGTERM, 3), (signal.SIGKILL, 5)]:
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            pass
        except BaseException as exc:
            errors.append({'stage': sig.name, 'error': repr(exc)})
        try:
            child.wait(timeout=seconds)
        except BaseException as exc:
            errors.append({'stage': 'wait_' + sig.name, 'error': repr(exc)})
        end = time.monotonic() + seconds
        while True:
            try:
                if not group_alive(child.pid):
                    return {'complete': True, 'errors': errors}
            except BaseException as exc:
                errors.append({'stage': 'group_check', 'error': repr(exc)})
                break
            if time.monotonic() >= end:
                break
            time.sleep(0.05)
    return {'complete': False, 'errors': errors}


def append_bounded(stream, data, kind, counts, aggregate):
    require(kind in STREAM_LIMITS, 'Unknown stream')
    room = min(STREAM_LIMITS[kind] - counts[kind], TOTAL_LIMIT - aggregate[0])
    allowed = min(len(data), max(0, room))
    if allowed:
        written = stream.write(data[:allowed])
        require(written == allowed, 'Short evidence write')
        counts[kind] += written
        aggregate[0] += written
    require(allowed == len(data), 'OUTPUT_OVERFLOW_HOLD_PARTIAL_RETAINED')


def run_child(name, argv, out, admission, aggregate):
    require((name, argv) in commands(), 'Command outside exact six-command plan')
    child = None
    failure = None
    clean = None
    code = None
    post_custody = 'NOT_SPAWNED'
    counts = {'stdout': 0, 'stderr': 0}
    handles = []
    selector = None
    try:
        admission()
        check_inputs()
        for kind in ('stdout', 'stderr'):
            handles.append((out / (name + '.' + kind)).open('xb'))
        env = {'PATH': '/usr/bin:/bin', 'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1',
               'OPENBLAS_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1', 'LC_ALL': 'C',
               'PYTHONDONTWRITEBYTECODE': '1'}
        child = subprocess.Popen(argv, cwd=out, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=True, preexec_fn=child_limits)
        selector = selectors.DefaultSelector()
        for kind, pipe, handle in zip(('stdout', 'stderr'), (child.stdout, child.stderr), handles):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, (kind, handle))
        end = time.monotonic() + WALL
        next_guard = 0.0
        while selector.get_map():
            now = time.monotonic()
            if now >= next_guard:
                admission()
                next_guard = now + 1.0
            require(now < end, 'WALL_TIMEOUT_HOLD')
            for key, _ in selector.select(timeout=min(0.2, end - now)):
                try:
                    data = os.read(key.fileobj.fileno(), 65536)
                except BlockingIOError:
                    continue
                if not data:
                    selector.unregister(key.fileobj)
                else:
                    kind, handle = key.data
                    append_bounded(handle, data, kind, counts, aggregate)
        while True:
            admission()
            remaining = end - time.monotonic()
            require(remaining > 0, 'WALL_TIMEOUT_HOLD')
            try:
                code = child.wait(timeout=min(1, remaining))
                break
            except subprocess.TimeoutExpired:
                pass
        require(code == 0, 'Disassembler failed; no next child')
        require(not group_alive(child.pid), 'Owned descendant survived disassembler')
        admission()
    except BaseException as exc:
        failure = exc
        if child is not None:
            try:
                clean = cleanup(child)
                code = child.poll()
            except BaseException as secondary:
                failure.add_note('Owned cleanup failed: ' + repr(secondary))
    finally:
        if child is not None:
            try:
                admission()
            except BaseException as exc:
                post_custody = 'POST_CUSTODY_UNVERIFIED_HOLD'
                if failure is None:
                    failure = exc
                failure.add_note('POST_CUSTODY_UNVERIFIED_HOLD: fresh admission refused; no input hashing: ' + repr(exc))
            else:
                try:
                    check_inputs()
                    post_custody = 'VERIFIED'
                except BaseException as exc:
                    post_custody = 'POST_CUSTODY_FAILED_HOLD'
                    if failure is None:
                        failure = exc
                    else:
                        failure.add_note('Post-child input custody failed: ' + repr(exc))
        for handle in ([selector] if selector else []) + handles + (
                [child.stdout, child.stderr] if child is not None else []):
            try:
                handle.close()
            except BaseException as exc:
                if failure is None:
                    failure = exc
                else:
                    failure.add_note('Evidence/pipe close failed: ' + repr(exc))
    receipt = {'argv': argv, 'pid': child.pid if child else None, 'returncode': code,
               'CPU_s': CPU, 'Linux_AS_MiB': 512, 'wall_s': WALL, 'nice': 15,
               'CUDA_hidden': True, 'bytes_written': counts, 'aggregate_bytes': aggregate[0],
               'error': repr(failure) if failure else None,
               'secondary_notes': list(getattr(failure, '__notes__', [])) if failure else [],
               'owned_cleanup': clean, 'post_input_custody': post_custody,
               'native_or_GPU_execution': False}
    try:
        emit_new(out / (name + '.json'), receipt)
    except BaseException as exc:
        if failure is None:
            raise
        failure.add_note('Terminal receipt write failed: ' + repr(exc))
    if failure is not None:
        raise failure
    return receipt


def execute(expected_digest, runtime, a, host, binding):
    """Caller has qualified source; reserve existing STATE slot, never drain."""
    out = HERE / 'output-FIRST'
    state_path = E / 'STATE.json'
    state = guard(runtime, host, binding)
    fresh_leaf(out)
    check_inputs()
    require(sha(HERE / 'qualification.json') == expected_digest, 'Qualification changed before reservation')
    require(json.loads(state_path.read_text()) == state, 'Coordination changed before reservation')
    reservation = {'controller_pid': os.getpid(), 'mode': 'STATIC_IQ_DISASSEMBLY_ONLY',
                   'output': str(out), 'qualification_sha256': expected_digest}
    original = dict(state)
    state['active_cpu_build'] = reservation
    primary = None
    result = None
    out_owned = False
    try:
        a.emit(state_path, state)
        def admission():
            guard(runtime, host, binding, reservation)
            require(sha(HERE / 'qualification.json') == expected_digest, 'Qualification changed')
        admission()
        fresh_leaf(out)
        out.mkdir()
        out_owned = True
        emit_new(out / 'plan.json', {'commands': commands(), 'objects': {k: [str(v[0]), v[1]] for k, v in OBJECTS.items()},
                                   'tool': {'invoked': str(TOOL), 'resolved': str(TOOL_REAL), 'sha256': TOOL_SHA},
                                   'selected_binding': binding, 'qualification_sha256': expected_digest})
        rows = []
        aggregate = [0]
        for name, argv in commands():
            require(sha(HERE / 'qualification.json') == expected_digest, 'Qualification changed')
            rows.append(run_child(name, argv, out, admission, aggregate))
        admission()
        check_inputs()
        require(sha(HERE / 'qualification.json') == expected_digest, 'Qualification changed')
        result = {'status': 'SIX_STATIC_CHILDREN_COMPLETE_UNINTERPRETED', 'children': rows,
                  'qualification_sha256': expected_digest, 'total_log_bytes': aggregate[0],
                  'selected_binding': binding, 'numerical_gate': 'HOLD_TOKEN_PATH_DIFFERS',
                  'GPU_execution': False, 'compiler_execution': False, 'performance_admitted': False}
    except BaseException as exc:
        primary = exc
    finally:
        try:
            latest = json.loads(state_path.read_text())
            if latest.get('active_cpu_build') == reservation:
                if 'active_cpu_build' in original:
                    latest['active_cpu_build'] = original['active_cpu_build']
                else:
                    latest.pop('active_cpu_build', None)
                a.emit(state_path, latest)
                require(json.loads(state_path.read_text()).get('active_cpu_build') != reservation,
                        'Own reservation release not observed')
            else:
                raise ValueError('Reservation ownership changed; foreign state preserved')
        except BaseException as exc:
            if primary is None:
                primary = exc
            else:
                primary.add_note('Own reservation release failed: ' + repr(exc))
    if out_owned and out.is_dir() and not out.is_symlink():
        terminal = result if primary is None else {'status': 'HOLD', 'error': repr(primary),
                    'secondary_notes': list(getattr(primary, '__notes__', [])), 'retry': False}
        try:
            emit_new(out / 'receipt.json', terminal)
        except BaseException as exc:
            if primary is None:
                raise
            primary.add_note('Final receipt write failed: ' + repr(exc))
    if primary is not None:
        raise primary
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qualification-sha256', required=True)
    args = parser.parse_args()
    require(sys.platform == 'linux' and HERE == EXPECTED_HERE, 'Physical exact owned diagnostic only')
    real_directory(HERE)
    runtime, a, host, binding = load_support()
    guard(runtime, host, binding)
    qualification(args.qualification_sha256)
    guard(runtime, host, binding)
    execute(args.qualification_sha256, runtime, a, host, binding)


if __name__ == '__main__':
    main()
