"""Bounded offline conversion of the frozen 3840 original gate/up matrices.

No model inference, service action, networking or weight calibration. Each unit
is one complete matrix, using the already qualified lossless codec and encoder.
Completed parts remain immutable; a fault stops admission of additional units.
"""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
Q = HERE.parent
PLAN_SHA = '9351465edc3ea4b4a3763552438d0309bbdbf913d434a2623a45f55dba81e54b'
ARTIFACTS_SHA = 'e99ed17f0d5876211d058c9d4533a4798d8473e6ed2af170340d97c5c33cc68e'
SOURCE_LFS = dict(zip(
    ['model-%05d-of-00048.safetensors' % n for n in range(27, 32)],
    ['8e76de6a5cdc7ac0923526d1c1a2e6459c55bbfa692793b29cdfe07b4f9fbc52',
     '3c0e5ad6a4e8e811c1a55fd8f5b59c9fa329b241c671997c28fc7a01944d5a77',
     '392a950bcb062b89f683abc52d49a17e92c66f80cd1cb6fb92b71091da75319b',
     '0b44d1364e578fc26dc0cc86564e49a92871a51063fb7f2f3b51cb020de44ab0',
     'd3230ffc32e11c5a34505c5acaeaff642aed5c770b297695e1f7a94071d361ac']))
MATRIX_BYTES = 5068800
RESERVE = 132 * 2**30
ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
       'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
CLEAN_ENV = dict(ENV, PATH='/usr/bin:/bin', LANG='C', LC_ALL='C')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda: stream.read(2**20), b''):
            h.update(b)
    return h.hexdigest()


def fingerprint(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'Absolute source path')
    for p in [path, *path.parents]:
        require(not p.is_symlink(), 'No path aliases')
    st = path.stat()
    require(path.is_file() and st.st_nlink == 1, 'One ordinary source file')
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def read_plane(root, spec, pins):
    require(type(spec) is dict and set(spec) == {'file', 'offset', 'bytes'}, 'Exact source plane')
    require(Path(spec['file']).name == spec['file'] and spec['file'] in pins, 'Pinned source filename')
    path = Path(root) / spec['file']
    before = fingerprint(path)
    require(before == pins[spec['file']]['fingerprint'], 'Original source changed after full verification')
    a, n = spec['offset'], spec['bytes']
    require(type(a) is type(n) is int and 8 <= a <= before[2] - n and n > 0, 'Complete bounded source range')
    # The opened FD must be the very same inode checked above and below.
    with path.open('rb') as stream:
        st = os.fstat(stream.fileno())
        require([st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns] == before,
                'Source changed at open')
        stream.seek(a); data = stream.read(n)
        st = os.fstat(stream.fileno())
        require([st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns] == before,
                'Source changed while reading')
    require(len(data) == n and fingerprint(path) == before, 'Complete stable source read')
    return data


def encode(weight, scale, codec, encoder, runner=subprocess.run):
    require(len(weight) == 5898240 and len(scale) == 368640, 'Whole original gate/up matrix')
    args = ['--rows', '2304', '--k', '5120']
    first = runner([str(codec), *args], input=weight + scale, capture_output=True, timeout=30, env=CLEAN_ENV)
    require(first.returncode == 0 and len(first.stdout) == 6266880, 'Lossless codec failed; no retry')
    second = runner([str(encoder), *args], input=first.stdout, capture_output=True, timeout=30, env=CLEAN_ENV)
    require(second.returncode == 0 and len(second.stdout) == MATRIX_BYTES, 'IQ3_S encoder failed; no retry')
    return second.stdout


def write_part(path, data, record, input_shas):
    path = Path(path)
    require(not path.exists() and not path.is_symlink(), 'Preserve previous output')
    require(len(data) == MATRIX_BYTES, 'Whole encoded matrix')
    tmp = path.with_suffix('.partial')
    with tmp.open('xb') as out:
        out.write(data); out.flush(); os.fsync(out.fileno())
    require(not path.exists(), 'Output appeared')
    os.link(tmp, path); tmp.unlink()
    proof = {'record': record, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
             'source_planes_sha256': input_shas, 'codec_returncode': 0, 'encoder_returncode': 0}
    with path.with_suffix('.json').open('x') as out:
        json.dump(proof, out, indent=2); out.write('\n')
    return proof


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    os.nice(15)
    require(all(os.environ[k] == v for k, v in ENV.items()), 'Child-only environment')


def worker(index, root, output, pins_path, pins_sha):
    limits()
    require(sha(HERE / 'SOURCE_PLAN.json') == PLAN_SHA, 'Frozen plan changed')
    plan = json.loads((HERE / 'SOURCE_PLAN.json').read_text())
    require(type(index) is int and 0 <= index < 3840 and len(plan['records']) == 3840, 'One frozen task')
    row = plan['records'][index]
    require(row['target_offset'] == index * MATRIX_BYTES and row['target_bytes'] == MATRIX_BYTES,
            'Exact output order and geometry')
    require(sha(pins_path) == pins_sha, 'Exact admitted source-verification receipt')
    p = json.loads(Path(pins_path).read_text())
    require(p['root'] == str(Path(root)) and p['plan_sha256'] == PLAN_SHA,
            'Verification receipt root and frozen plan')
    require(set(p['files']) == set(SOURCE_LFS) and
            all(v['sha256'] == SOURCE_LFS[n] and v['full_sha_verified'] is True
                for n, v in p['files'].items()), 'Full original source LFS provenance')
    out_root = Path(output)
    require(out_root.is_absolute() and out_root.is_dir() and '..' not in out_root.parts,
            'Owned absolute output directory')
    for path in [out_root, *out_root.parents]:
        require(not path.is_symlink(), 'No output directory alias')
    weight = read_plane(root, row['source_ranges']['weight'], p['files'])
    scale = read_plane(root, row['source_ranges']['scale'], p['files'])
    require(sha(HERE / 'PLATFORM_ARTIFACTS.json') == ARTIFACTS_SHA, 'Immutable qualified binary map')
    bins = json.loads((HERE / 'PLATFORM_ARTIFACTS.json').read_text())[sys.platform]
    codec = Q / ('native-codec-v2/mxpack-FIRST-' + sys.platform)
    encoder = Q / ('iq3s-encoder-v2/compile-FIRST-' + sys.platform + '/encode-iq3s')
    require(sha(codec) == bins['codec_sha256'] and sha(encoder) == bins['encoder_sha256'],
            'Qualified binary identity')
    data = encode(weight, scale, codec, encoder)
    write_part(Path(output) / ('%04d.iq3s' % index), data, row,
               {'weight': hashlib.sha256(weight).hexdigest(), 'scale': hashlib.sha256(scale).hexdigest()})


def bounded_unit(index, root, output, pins, pins_sha):
    log = Path(output) / ('%04d.log' % index)
    with log.open('x') as out:
        p = subprocess.Popen([sys.executable, '-I', '-B', str(HERE / 'convert.py'), 'worker', str(index),
                              str(root), str(output), str(pins), pins_sha], env=CLEAN_ENV,
                             stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                             start_new_session=True)
        timed_out, error, rc, cleanup = False, None, None, []
        try:
            rc = p.wait(timeout=90)
        except BaseException as exc:
            timed_out = isinstance(exc, subprocess.TimeoutExpired)
            error = repr(exc)
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            except OSError as kill_error: cleanup.append(repr(kill_error))
            try: rc = p.wait(timeout=10)
            except BaseException as wait_error: cleanup.append(repr(wait_error))
        finally:
            remaining = False
            try:
                os.killpg(p.pid, 0); remaining = True
            except ProcessLookupError: pass
            except OSError as group_error: cleanup.append(repr(group_error))
            if remaining:
                cleanup.append('Descendants remained after child termination')
                try: os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                except OSError as kill_error: cleanup.append(repr(kill_error))
            with (Path(output) / ('%04d.child.json' % index)).open('x') as receipt:
                json.dump({'pid': p.pid, 'returncode': rc, 'timed_out': timed_out, 'error': error,
                           'cleanup_errors': cleanup, 'descendants_remaining': remaining,
                           'CPU_seconds': 30, 'wall_seconds': 90, 'Linux_AS_bytes': 512 * 2**20}, receipt)
    require(rc == 0 and error is None and not cleanup, 'Conversion unit failed; preserve outputs and HOLD')
    proof = json.loads((Path(output) / ('%04d.json' % index)).read_text())
    part = Path(output) / ('%04d.iq3s' % index)
    require(part.stat().st_size == MATRIX_BYTES and sha(part) == proof['sha256'], 'Actual part verification')
    return index


def convert_queue(indices, task, guard, *, workers=4, clock=time.monotonic, wall=7200):
    require(type(workers) is int and 1 <= workers <= 4, 'At most four CPU workers')
    require(len(indices) == len(set(indices)) and all(type(n) is int and 0 <= n < 3840 for n in indices),
            'Unique frozen task IDs')
    deadline = clock() + wall
    todo, done, pending = iter(indices), [], {}
    lock, stopped = threading.Lock(), threading.Event()
    def admitted_task(i):
        with lock:
            require(not stopped.is_set(), 'UNRUN after another task fault')
        try:
            return task(i)
        except BaseException:
            with lock: stopped.set()
            raise
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        try:
            while True:
                while len(pending) < workers:
                    require(clock() < deadline, 'Conversion controller wall budget exhausted')
                    guard()
                    i = next(todo, None)
                    if i is None: break
                    with lock:
                        require(not stopped.is_set(), 'Stop admission after first conversion fault')
                        pending[pool.submit(admitted_task, i)] = i
                if not pending: break
                ready, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                # Read every ready result BEFORE admitting any replacement work.
                for future in ready:
                    i = pending.pop(future)
                    require(future.result() == i, 'Wrong completed task ID')
                    done.append(i)
        finally:
            with lock: stopped.set()
            for future in pending: future.cancel()
            # Executor joins every running child/task even after a deferral/fault.
    return sorted(done)


if __name__ == '__main__':
    require(len(sys.argv) == 7 and sys.argv[1] == 'worker', 'Only explicit bounded worker entry')
    worker(int(sys.argv[2]), *sys.argv[3:])
