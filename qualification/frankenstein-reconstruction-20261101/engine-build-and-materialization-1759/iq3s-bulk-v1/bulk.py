"""One fresh CPU-only original-FP4 conversion, under existing owned CPU custody.

No inference, networking, service action or GPU ownership changes. First controls
do not admit the 3840-matrix run. An independently pinned qualification is needed.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

HERE = Path(__file__).resolve().parent
Q = HERE.parent
E = Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025')
EXPECTED = E / 'decode-optimization-20261028/s2-reconstruction-v1/iq3s-bulk-v1'
CONVERTER = Q / 'iq3s-conversion-v1/convert.py'
CONVERTER_SHA = '8bad9fd42a851bf5571f34f8727c19a88668e619f470cea046784b4a4a1bb574'
BUILD = Q / 'placement-native-build-v1/build_current.py'
BUILD_SHA = '60022606724b5b447056c0d54e0ea8c0f163359673b640cea0cd659abce26916'
MANIFEST_SHA = '22ecce3e7085e29520fadaa67d603beb8cc0905f834ff3563029f6038825034b'
ROOT = Q / 'iq3s-source-acquisition-v1/assets/original'
OUT = HERE / 'conversion-FIRST'
SOURCE_NAMES = ('bulk.py', 'test_bulk.py', 'run_cpu.py')
RESERVE = 132 * 2**30
MATRIX_BYTES, COUNT = 5068800, 3840
OVERLAY_BYTES = MATRIX_BYTES * COUNT
CLEAN_ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
             'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1',
             'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''):
            h.update(block)
    return h.hexdigest()


def emit(path, row):
    with Path(path).open('x') as stream:
        json.dump(row, stream, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.resolve() == path,
            'Real absolute path required')
    st = path.stat()
    require(path.is_file() and not path.is_symlink() and st.st_nlink == 1,
            'One ordinary pinned file required')
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def load_exact(name, path, pin):
    regular(path)
    require(sha(path) == pin, 'Imported source changed: ' + name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def conversion():
    c = load_exact('bulk_qualified_conversion', CONVERTER, CONVERTER_SHA)
    require(sha(c.HERE / 'SOURCE_PLAN.json') == c.PLAN_SHA and
            sha(c.HERE / 'PLATFORM_ARTIFACTS.json') == c.ARTIFACTS_SHA, 'Frozen composition inputs')
    return c


def acquisition_contract(receipt, manifest, asset_root, inspect=regular):
    require(receipt.get('status') == 'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN' and
            type(receipt.get('returncode')) is int and receipt['returncode'] == 0 and
            receipt.get('manifest_sha256') == MANIFEST_SHA and
            receipt.get('asset_root') == str(asset_root) and receipt.get('model_or_service_actions') == 0,
            'Completed ALL8 base acquisition required before CPU claim')
    specs, rows = manifest['files'], receipt['files']
    require(len(specs) == len(rows) == 8 and len({r['path'] for r in rows}) == 8,
            'Exactly eight verified base assets')
    by_name = {r['path']: r for r in rows}
    require(set(by_name) == {s['path'] for s in specs}, 'Exact base asset identities')
    for spec in specs:
        name = Path(spec['path'])
        require(not name.is_absolute() and '..' not in name.parts, 'Bounded base asset path')
        row = by_name[spec['path']]
        require(row.get('status') in ('VERIFIED_EXISTING', 'DOWNLOADED_VERIFIED') and
                row.get('sha256') == spec['sha256'] and row.get('bytes') == spec['size'] and
                inspect(asset_root / name)[2] == spec['size'], 'Actual verified base asset size/receipt')


def base_closed(pin):
    path = Q / 'base-acquisition-v2/acquisition-state.json'
    require(sha(path) == pin, 'Exact terminal acquisition receipt')
    manifest = Q / 'base-acquisition-v2/ASSET_MANIFEST.json'
    require(sha(manifest) == MANIFEST_SHA, 'Exact published base manifest')
    acquisition_contract(json.loads(path.read_text()), json.loads(manifest.read_text()),
                         Q / 'base-acquisition-v1/assets')
    # The terminal receipt can be written immediately before the downloader exits.
    # Prove its existing lock is free; never take a CPU claim while it still runs.
    lock = Q / 'base-acquisition-v1/acquisition.lock'
    regular(lock)
    with lock.open('rb') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(stream, fcntl.LOCK_UN)


def qualification(pin):
    path = HERE / 'qualification.json'
    require(sha(path) == pin, 'Pinned qualification required')
    q = json.loads(path.read_text())
    sources = {name: sha(HERE / name) for name in SOURCE_NAMES}
    require(q.get('entire_source_tests_driver_manually_read') is True and
            q.get('CPU_both_hosts_passed') is True and q.get('source_sha256') == sources and
            q.get('selected_binding') and q.get('source_root') == str(ROOT) and
            q.get('output_root') == str(OUT) and q.get('test_ids'), 'Current manual/both-host qualification')
    files = q['files']
    required = {str(HERE / n): p for n, p in sources.items()}
    required.update({str(CONVERTER): CONVERTER_SHA, str(BUILD): BUILD_SHA,
                     str(Q / 'base-acquisition-v2/ASSET_MANIFEST.json'): MANIFEST_SHA,
                     str(Q / 'base-acquisition-v2/acquisition-state.json'): q['base_terminal_sha256']})
    c = conversion()
    required.update({str(c.HERE / 'SOURCE_PLAN.json'): c.PLAN_SHA,
                     str(c.HERE / 'PLATFORM_ARTIFACTS.json'): c.ARTIFACTS_SHA})
    require(all(files.get(n) == p for n, p in required.items()), 'Required qualification inputs omitted')
    for name, digest in files.items():
        require(not Path(name).is_relative_to(ROOT) and
                not Path(name).is_relative_to(Q / 'base-acquisition-v1/assets'),
                'Weight files use separate receipt/streaming verification, not qualification rehash')
        regular(name); require(sha(name) == digest, 'Qualification input drift: ' + name)
    proofs = {}
    for platform in ('darwin', 'linux'):
        proof_path = q['CPU_paths'][platform]
        require(proof_path in files, 'Pinned physical CPU receipt required')
        proofs[platform] = json.loads(Path(proof_path).read_text())
    cpu_contract(q, sources, proofs)
    evidence = c.HERE / 'BOTH_HOST_CPU_FIRST.json'
    require(str(evidence) in files, 'Pinned qualified composition proof required')
    old = json.loads(evidence.read_text())
    require(old.get('both_physical_hosts_passed') is True and
            old['source_sha256']['convert.py'] == CONVERTER_SHA, 'Qualified composition proof changed')
    bins = json.loads((c.HERE / 'PLATFORM_ARTIFACTS.json').read_text())['linux']
    for name, digest in ((Q / 'native-codec-v2/mxpack-FIRST-linux', bins['codec_sha256']),
                         (Q / 'iq3s-encoder-v2/compile-FIRST-linux/encode-iq3s', bins['encoder_sha256'])):
        require(files.get(str(name)) == digest, 'Qualified conversion executable omitted')
    python = str(Path(sys.executable).resolve())
    require(python in files and q.get('python') == python, 'Exact controller/worker Python required')
    return q


def cpu_contract(q, sources, proofs):
    require(q.get('entire_source_tests_driver_manually_read') is True and
            q.get('CPU_both_hosts_passed') is True and q.get('source_sha256') == sources and
            q.get('test_ids'), 'Explicit manual/both-host CPU gate')
    require(set(proofs) == {'darwin', 'linux'}, 'Both physical CPU receipts')
    for platform, proof in proofs.items():
        require(proof.get('passed') is True and proof.get('source_sha256') == sources and
                proof.get('test_ids') == q['test_ids'] and proof.get('physical_platform') == platform and
                proof.get('controls') == len(q['test_ids']) and proof.get('returncode') == 0 and
                proof.get('failures') == proof.get('errors') == 0,
                'Matching physical CPU source/tests required')
        observed = proof.get('observed', {})
        require(observed.get('cpu') == [30, 30] and observed.get('nice') == 15 and
                observed.get('as') == ([512 * 2**20] * 2 if platform == 'linux' else None) and
                observed.get('platform') == platform and observed.get('dont_write_bytecode') is True and
                type(observed.get('pid')) is int and observed['pid'] > 1 and
                observed.get('pgid') == observed['pid'] and
                all(observed.get('environment', {}).get(k) == v for k, v in CLEAN_ENV.items()
                    if k not in ('PATH', 'LANG', 'LC_ALL')),
                'Actual portable CPU bounds required')


def verify_sources(root, plan_sha, files, destination):
    """One streaming full SHA per source, bound to the exact same open inode."""
    rows = {}
    for name, expected in files.items():
        require(Path(name).name == name, 'Source filename only')
        path = Path(root) / name
        before = regular(path)
        h = hashlib.sha256()
        with path.open('rb') as stream:
            require(stat_row(os.fstat(stream.fileno())) == before, 'Source changed at verifier open')
            for block in iter(lambda: stream.read(2**20), b''):
                h.update(block)
            require(stat_row(os.fstat(stream.fileno())) == before, 'Source changed during full SHA')
        require(regular(path) == before and h.hexdigest() == expected, 'Original full source SHA mismatch')
        rows[name] = {'sha256': expected, 'fingerprint': before, 'full_sha_verified': True}
    receipt = {'root': str(root), 'plan_sha256': plan_sha, 'files': rows}
    emit(destination, receipt)
    return receipt


def stat_row(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def join_parts(parts, records, destination, *, matrix_bytes=MATRIX_BYTES):
    """Validate every original-order part while copying; never replace an overlay."""
    destination = Path(destination)
    require(not destination.exists() and not destination.is_symlink(), 'Fresh overlay only')
    partial = destination.with_suffix('.partial')
    full, count = hashlib.sha256(), 0
    with partial.open('xb') as out:
        for index, record in enumerate(records):
            require(record['target_offset'] == index * matrix_bytes and record['target_bytes'] == matrix_bytes,
                    'Frozen contiguous overlay order')
            stem = Path(parts) / ('%04d' % index)
            regular(stem.with_suffix('.json')); regular(stem.with_suffix('.child.json'))
            proof = json.loads(stem.with_suffix('.json').read_text())
            child = json.loads(stem.with_suffix('.child.json').read_text())
            require(proof['record'] == record and proof['bytes'] == matrix_bytes and
                    proof['codec_returncode'] == proof['encoder_returncode'] == 0,
                    'Exact frozen part record and completed codec/encoder')
            require(type(child.get('returncode')) is int and child['returncode'] == 0 and
                    child.get('error') is None and child.get('timed_out') is False and
                    child.get('cleanup_errors') == [] and child.get('descendants_remaining') is False,
                    'Clean actual conversion child required')
            path = stem.with_suffix('.iq3s'); before = regular(path)
            require(before[2] == matrix_bytes, 'Complete matrix part')
            part = hashlib.sha256(); copied = 0
            with path.open('rb') as stream:
                require(stat_row(os.fstat(stream.fileno())) == before, 'Part changed at join open')
                for block in iter(lambda: stream.read(2**20), b''):
                    part.update(block); full.update(block); out.write(block); copied += len(block)
                require(stat_row(os.fstat(stream.fileno())) == before, 'Part changed during join')
            require(regular(path) == before and copied == matrix_bytes and
                    part.hexdigest() == proof['sha256'], 'Stable actual matrix hash')
            count += copied
        out.flush(); os.fsync(out.fileno())
    require(count == len(records) * matrix_bytes, 'Complete joined payload')
    os.link(partial, destination); partial.unlink()
    result = {'bytes': count, 'sha256': full.hexdigest(), 'parts': len(records),
              'model_executed': False, 'production_changed': False}
    emit(destination.with_suffix('.json'), result)
    return result


def actual_limits(row, pid, parent):
    require(type(pid) is int and pid > 1 and row == {
        'pid': pid, 'ppid': parent, 'pgid': pid, 'cpu': [30, 30],
        'as': [512 * 2**20, 512 * 2**20], 'nice': 15,
        'environment': CLEAN_ENV, 'isolated': True, 'dont_write_bytecode': True},
        'Actual data-child identity/resources required')


def observe_limits():
    return {'pid': os.getpid(), 'ppid': os.getppid(), 'pgid': os.getpgrp(),
            'cpu': list(resource.getrlimit(resource.RLIMIT_CPU)),
            'as': list(resource.getrlimit(resource.RLIMIT_AS)),
            'nice': os.getpriority(os.PRIO_PROCESS, 0), 'environment': dict(os.environ),
            'isolated': bool(sys.flags.isolated), 'dont_write_bytecode': sys.dont_write_bytecode}


def child_limits():
    require(sys.flags.isolated and sys.dont_write_bytecode and dict(os.environ) == CLEAN_ENV,
            'Isolated clean worker environment')
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    nice = os.getpriority(os.PRIO_PROCESS, 0)
    require(nice <= 15, 'Inherited nice priority'); os.nice(15 - nice)


class Children:
    """Serialize only handle registration; conversion itself still has four slots."""
    def __init__(self, owner):
        self.owner, self.lock = owner, threading.Lock()

    def popen(self, argv, **kwargs):
        with self.lock:
            name = 'child-' + str(len(self.owner.children))
            self.owner.starting(name)
            if len(argv) > 3 and argv[3] == str(CONVERTER):
                require(len(argv) == 10, 'Complete qualified matrix worker command')
                index = int(argv[5])
                expected = [sys.executable, '-I', '-B', str(CONVERTER), 'worker', str(index),
                            str(ROOT), str(OUT / 'parts'), str(OUT / 'verified-sources.json'), argv[-1]]
                require(argv == expected and 0 <= index < COUNT and kwargs.get('env') == CLEAN_ENV,
                        'Exact qualified bounded-unit worker argv')
                # Source remains unchanged. The local entry calls c.worker and
                # wraps only its limits() call to record actual child evidence.
                argv = [str(Path(sys.executable).resolve()), '-I', '-B', str(HERE / 'bulk.py'), 'child',
                        'matrix-' + str(index), argv[-1]]
            process = subprocess.Popen(argv, **kwargs)
            # Existing owner captures the handle before journal/identity checks.
            self.owner.registered(process, name)
            return process

    def absence(self):
        with self.lock:
            return self.owner.absence()

    def cleanup_all(self, owner, deadline):
        # Also covers a Popen whose handle was captured before journal failure.
        with self.lock:
            rows = list(self.owner.children)
        for name, process, _ in rows:
            try: owner.cleanup(process, deadline)
            except BaseException as exc:
                self.owner.cleanup_failed(name, exc)


class SubprocessProxy:
    def __init__(self, children): self.children = children
    def Popen(self, *args, **kwargs): return self.children.popen(*args, **kwargs)
    def __getattr__(self, name): return getattr(subprocess, name)


def owned_stage(mode, folder, children, owner, check, *, deadline, spawned):
    """All actual data children retain CPU30/AS512MiB/wall90."""
    folder.mkdir()
    started = time.monotonic(); process = None
    row = {'mode': mode, 'pid': None, 'returncode': None, 'error': None, 'cleanup': []}
    try:
        check()
        with (folder / 'stdout.log').open('xb') as out, (folder / 'stderr.log').open('xb') as err:
            process = children.popen([str(Path(sys.executable).resolve()), '-I', '-B', str(HERE / 'bulk.py'),
                'child', mode], cwd=HERE, env=CLEAN_ENV, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, start_new_session=True)
            row['pid'] = process.pid; spawned()
            end = min(deadline - 15, started + 75)
            while process.poll() is None:
                check(); require(time.monotonic() < end, 'Bounded streaming stage deadline')
                try: process.wait(timeout=1)
                except subprocess.TimeoutExpired: pass
            row['returncode'] = process.returncode
            require(process.returncode == 0, 'Streaming stage failed; no retry')
            observed = json.loads((folder / 'observed.json').read_text())
            actual_limits(observed, process.pid, os.getpid())
            require(json.loads((folder / 'DONE.json').read_text()) == {'mode': mode, 'complete': True},
                    'Actual streaming DONE required')
    except BaseException as exc:
        row['error'] = repr(exc)
    finally:
        if process is not None:
            try: owner.cleanup(process, min(deadline, started + 90))
            except BaseException as exc:
                row['cleanup'].append(repr(exc)); children.owner.cleanup_failed(mode, exc)
            row['returncode'] = process.poll()
        row['elapsed_seconds'] = time.monotonic() - started
        emit(folder / 'child.json', row)
    require(row['error'] is None and row['returncode'] == 0 and not row['cleanup'], 'Streaming stage HOLD')


def release_claim(cas, state_path, record, absence):
    require(absence['passed'] is True, 'Owned descendants unresolved; retain CPU claim')
    raw = state_path.read_bytes(); state = json.loads(raw)
    require(state.get('active_cpu_build') == record, 'Foreign claim unchanged')
    cas.cas_state(state_path, raw, dict(state, active_cpu_build=False))


def main(pin):
    deadline = time.monotonic() + 7200
    require(sys.platform == 'linux' and HERE == EXPECTED and sys.flags.isolated and sys.dont_write_bytecode,
            'Exact isolated Ubuntu controller only')
    require(os.getpriority(os.PRIO_PROCESS, 0) == 0, 'Controller baseline nice0; data children set nice15')
    build = load_exact('bulk_build_custody', BUILD, BUILD_SHA)
    early = build.exact('build_early'); binding = early.early_guard(); build.strict_idle()
    # No CPU lease/claim or output directory before actual ALL8 terminal closure.
    q = qualification(pin); base_closed(q['base_terminal_sha256'])
    require(binding == q['selected_binding'], 'Fresh selected binding required')
    owner, support = build.exact('build_owner'), build.exact('build_support')
    healthy = build.exact('build_healthy_work')
    _, runtime, _, host, actual = support.support()
    require(actual == binding, 'Selected owner changed')
    gpu = owner.observe_gpu_lease(host, binding); cas = owner.load_cas()
    require(not OUT.exists() and not OUT.is_symlink(), 'Fresh no-replay output root')
    require(shutil.disk_usage(HERE).free >= RESERVE + 2 * OVERLAY_BYTES, 'Parts plus overlay and root132')
    c = conversion()
    record = {'mode': 's2-iq3s-bulk-FIRST', 'controller_pid': os.getpid(),
              'controller_start_ticks': owner.process_ticks(os.getpid()), 'nonce': uuid.uuid4().hex,
              'start_binding': binding, 'qualification_sha256': pin}
    with owner.CPULease(E / 'cpu-build.lock') as lease:
        claimed, cpu_started, primary = False, False, None
        def spawned():
            nonlocal cpu_started
            cpu_started = True
        def check():
            lease.check(); require(time.monotonic() < deadline - 15, 'Total7200 CPU deadline')
            state = build.coordination_guard(support, healthy, runtime, host, binding,
                      record if claimed else None, cpu_started=cpu_started)
            build.cpu_headroom(Path('/proc/meminfo').read_text())
            early.early_guard(record if claimed else None)
            owner.observe_gpu_lease(host, binding, gpu['identity'])
            require(sha(HERE / 'qualification.json') == pin and sha(CONVERTER) == CONVERTER_SHA,
                    'Qualification/controller changed')
            require(shutil.disk_usage(HERE).free >= RESERVE, 'Root132 maintained')
            return state
        state = check(); base_closed(q['base_terminal_sha256'])
        OUT.mkdir(); parts = OUT / 'parts'; parts.mkdir()
        children = Children(owner.OwnedChildren(OUT / 'owned-children.jsonl'))
        emit(OUT / 'attempt.json', record)
        try:
            raw = (E / 'STATE.json').read_bytes()
            require(json.loads(raw) == state and not state.get('active_cpu_build'), 'CPU claim race')
            cas.cas_state(E / 'STATE.json', raw, dict(state, active_cpu_build=record)); claimed = True
            verified_rows = {}
            for index, name in enumerate(sorted(c.SOURCE_LFS)):
                mode = 'verify-' + str(index)
                owned_stage(mode, OUT / mode, children, owner, check, deadline=deadline, spawned=spawned)
                proof = json.loads((OUT / mode / 'source.json').read_text())
                require(proof['root'] == str(ROOT) and proof['plan_sha256'] == c.PLAN_SHA and
                        set(proof['files']) == {name} and proof['files'][name]['sha256'] == c.SOURCE_LFS[name] and
                        proof['files'][name]['full_sha_verified'] is True, 'Actual single-source verification')
                verified_rows.update(proof['files'])
            emit(OUT / 'verified-sources.json', {'root': str(ROOT), 'plan_sha256': c.PLAN_SHA,
                                               'files': verified_rows})
            verified = OUT / 'verified-sources.json'; verified_sha = sha(verified)
            c.subprocess = SubprocessProxy(children)
            def task(index):
                return c.bounded_unit(index, ROOT, parts, verified, verified_sha)
            # Reserve time for at most100s already admitted matrix work and the
            # final bounded join/cleanup. No replacement work past the cutoff.
            done = c.convert_queue(list(range(COUNT)), task, check, workers=4,
                                   wall=max(0, deadline - time.monotonic() - 210))
            require(done == list(range(COUNT)), 'Every frozen matrix completed exactly once')
            require(children.absence()['passed'], 'Conversion groups must close before join')
            owned_stage('join', OUT / 'join', children, owner, check, deadline=deadline, spawned=spawned)
            result = json.loads((OUT / 'overlay.json').read_text())
            require(result['bytes'] == OVERLAY_BYTES and result['parts'] == COUNT, 'Whole overlay receipt')
            for name, digest in q['files'].items():
                require(sha(name) == digest, 'Final qualification input drift')
        except BaseException as exc:
            primary = exc
        finally:
            try:
                # bounded_unit owns cleanup, while this registry independently
                # verifies all captured groups. No unknown PID is signalled.
                children.cleanup_all(owner, deadline)
                absence = children.absence(); emit(OUT / 'absence.json', absence)
                if claimed:
                    release_claim(cas, E / 'STATE.json', record, absence); claimed = False
                check()
                require(time.monotonic() <= deadline, 'Total7200 closure exceeded')
            except BaseException as exc:
                if primary is None: primary = exc
                else: primary.add_note('Bulk closure: ' + repr(exc))
            emit(OUT / 'supervision.json', {'passed': primary is None, 'owned_claim_released': not claimed,
                 'error': repr(primary) if primary else None, 'elapsed_within7200': time.monotonic() <= deadline})
        if primary is not None: raise primary
        emit(OUT / 'result.json', dict(result, passed=True, source_receipt_sha256=verified_sha,
                                     qualification_sha256=pin))


def child(mode, pins_sha=None):
    require(HERE == EXPECTED and sys.platform == 'linux', 'Actual streaming child location')
    require(sys.flags.isolated and sys.dont_write_bytecode and dict(os.environ) == CLEAN_ENV,
            'Isolated clean child entry')
    # Bounds precede dependency bootstrap. Matrix worker's existing limits()
    # applies nice15 once; streaming children set nice15 below.
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    c = conversion()
    if mode.startswith('matrix-'):
        index = int(mode.removeprefix('matrix-'))
        require(0 <= index < COUNT and pins_sha, 'Exact matrix child identity')
        original_limits = c.limits
        def captured_limits():
            original_limits()
            observed = observe_limits(); actual_limits(observed, os.getpid(), os.getppid())
            emit(OUT / 'parts' / ('%04d.observed.json' % index), observed)
        c.limits = captured_limits
        c.worker(index, ROOT, OUT / 'parts', OUT / 'verified-sources.json', pins_sha)
        emit(OUT / 'parts' / ('%04d.DONE.json' % index), {'index': index, 'complete': True})
        return
    child_limits()
    folder = OUT / mode
    emit(folder / 'observed.json', observe_limits())
    if mode.startswith('verify-'):
        index = int(mode.removeprefix('verify-'))
        names = sorted(c.SOURCE_LFS); require(0 <= index < len(names), 'One source index')
        name = names[index]
        verify_sources(ROOT, c.PLAN_SHA, {name: c.SOURCE_LFS[name]}, folder / 'source.json')
    elif mode == 'join':
        plan = json.loads((c.HERE / 'SOURCE_PLAN.json').read_text())
        require(len(plan['records']) == COUNT, 'Complete frozen join plan')
        controller = json.loads((OUT / 'attempt.json').read_text())['controller_pid']
        for index in range(COUNT):
            stem = OUT / 'parts' / ('%04d' % index)
            observed = json.loads(stem.with_suffix('.observed.json').read_text())
            unit = json.loads(stem.with_suffix('.child.json').read_text())
            actual_limits(observed, unit['pid'], controller)
            require(json.loads(stem.with_suffix('.DONE.json').read_text()) == {'index': index, 'complete': True},
                    'Actual matrix DONE required')
        join_parts(OUT / 'parts', plan['records'], OUT / 'overlay.iq3s')
    else:
        raise ValueError('Only verify/join streaming children')
    emit(folder / 'DONE.json', {'mode': mode, 'complete': True})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run', 'child'))
    parser.add_argument('value', help='run: qualification SHA; child: verify or join')
    parser.add_argument('pins_sha', nargs='?', help='Only matrix child: source receipt SHA')
    args = parser.parse_args()
    if args.mode == 'run': main(args.value)
    else: child(args.value, args.pins_sha)
