"""Pinned Maya-S resume under explicit active-inference authorization; no GPU/service entry point."""
import contextlib
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import urllib.request

MANIFEST_SHA = '22ecce3e7085e29520fadaa67d603beb8cc0905f834ff3563029f6038825034b'
REPO = 'peasantsmith/DeepSeek-V4.1-Flash-1017-Maya-GGUF'
REVISION = 'd1fc01009f21e26157acb6858c315d0365483b72'
RESERVE = 132 * 2**30
CHUNK = 128 * 2**20
BLOCK = 2**20
RATE = 64 * 2**20
E = Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025')
HERE = Path(__file__).resolve().parent
SOURCE_NAMES = {'acquire.py', 'test_acquire.py', 'run_cpu.py', 'ASSET_MANIFEST.json', 'AUTHORIZATION.json'}
AUTHORIZATION_SHA = 'cb2698ff10b5bd42b029968f20f59aa78d3d6924b4b8a4b5548bc3b28e78ce5a'
RUNTIME_PINS = {'iq2s_model_runtime.py': '1516752104307ffc159fbb80afd972ccd43c5cb9a96cf3e47de126f62482d510',
                'iq2s_config.py': 'aa8d222d5f9d5885ee87993b0418f471f4fe44f4f79bfdfffc859f1c4fee88d7'}


class Deferred(Exception):
    pass


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(path):
    require(digest(path) == MANIFEST_SHA, 'Frozen acquisition manifest changed')
    d = json.loads(Path(path).read_text())
    names = ['Maya-S/DeepSeek-V4.1-Flash-1017-Maya-S-IQ2_XXS-%05d-of-00006.gguf' % i
             for i in range(1, 7)] + ['dspark/dspark.bin', 'dspark/dspark.json']
    require(d['repo'] == REPO and d['revision'] == REVISION, 'Foreign model revision')
    require([f['path'] for f in d['files']] == names, 'Exact eight named assets required')
    require(d['root_reserve_bytes'] == RESERVE, 'Root reserve changed')
    for f in d['files']:
        require(set(f) == {'path', 'size', 'sha256'} and type(f['size']) is int and f['size'] > 0
                and re.fullmatch('[0-9a-f]{64}', f['sha256']) is not None, 'Invalid asset contract')
    require(sum(f['size'] for f in d['files']) == d['total_bytes'] == 347445667721,
            'Model byte budget changed')
    return d


def real_directory(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'Absolute real directory required')
    for p in [*reversed(path.parents), path]:
        require(not p.is_symlink() and p.is_dir(), 'Directory alias or missing ancestor')


def safe_file(path):
    path = Path(path)
    real_directory(path.parent)
    require(not path.is_symlink(), 'File symlink refused')
    if path.exists():
        require(path.is_file() and path.stat().st_nlink == 1, 'Foreign file alias refused')


def emit(path, value):
    safe_file(path)
    tmp = path.with_name(path.name + '.tmp')
    require(not tmp.exists() and not tmp.is_symlink(), 'Receipt temporary residue')
    with tmp.open('x') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def response_contract(response, start, end, size):
    status = response.status
    want = end - start + 1
    require(response.headers.get('Content-Encoding', 'identity') == 'identity', 'Encoded asset body')
    require(response.headers.get('Content-Length') == str(want), 'Unexpected response length')
    if status == 206:
        require(response.headers.get('Content-Range') == 'bytes %d-%d/%d' % (start, end, size),
                'Foreign or incomplete byte range')
    else:
        require(status == 200 and start == 0 and end + 1 == size, 'Server ignored resume range')


def acquire_file(spec, root, guard, *, opener=urllib.request.urlopen, free=None,
                 deadline=None, clock=time.monotonic, sleeper=time.sleep):
    """Verify the retained prefix and every incoming byte before atomic publication."""
    root = Path(root)
    real_directory(root)
    relative = Path(spec['path'])
    require(not relative.is_absolute() and '..' not in relative.parts
            and str(relative) == spec['path'], 'Unsafe relative asset')
    guard()
    parent = root / relative.parent
    if not parent.exists():
        parent.mkdir()  # manifest permits exactly one child directory
    real_directory(parent)
    final = root / relative
    partial = final.with_name(final.name + '.partial')
    safe_file(final)
    safe_file(partial)
    require(not (final.exists() and partial.exists()), 'Ambiguous final and partial files')
    path = final if final.exists() else partial
    offset = path.stat().st_size if path.exists() else 0
    require(offset <= spec['size'], 'Oversized retained asset')
    h = hashlib.sha256()
    checked = clock()
    def checkpoint(force=False):
        nonlocal checked
        now = clock()
        if force or now - checked >= 1:
            guard()
            checked = clock()
            now = checked
        if deadline is not None and now >= deadline:
            raise Deferred('Download wall budget reached')
    if offset:
        hashed = 0
        began_hash = clock()
        with path.open('rb') as stream:
            while True:
                checkpoint()
                block = stream.read(BLOCK)
                if not block:
                    break
                h.update(block)
                hashed += len(block)
                delay = hashed / RATE - (clock() - began_hash)
                if delay > 0: sleeper(min(delay, 1.0))
    if final.exists():
        checkpoint(force=True)
        require(offset == spec['size'] and h.hexdigest() == spec['sha256'], 'Existing final asset corrupt')
        return {'status': 'VERIFIED_EXISTING', 'bytes': offset, 'sha256': h.hexdigest()}
    free = (lambda: shutil.disk_usage(root).free) if free is None else free
    while offset < spec['size']:
        checkpoint(force=True)
        require(free() >= RESERVE + min(CHUNK, spec['size'] - offset), 'Root132 reserve unavailable')
        end = min(spec['size'] - 1, offset + CHUNK - 1)
        url = 'https://huggingface.co/%s/resolve/%s/%s' % (REPO, REVISION, spec['path'])
        request = urllib.request.Request(url, headers={'Range': 'bytes=%d-%d' % (offset, end),
                                                     'Accept-Encoding': 'identity'})
        with contextlib.closing(opener(request, timeout=5)) as response:
            response_contract(response, offset, end, spec['size'])
            remaining = end - offset + 1
            began = clock()
            received = 0
            mode = 'ab' if partial.exists() else 'xb'
            checkpoint(force=True)
            with partial.open(mode) as output:
                while remaining:
                    checkpoint()
                    require(free() >= RESERVE + BLOCK, 'Root132 reserve unavailable during transfer')
                    block = response.read1(min(BLOCK, remaining))
                    checkpoint()  # a stalled read may have crossed the deadline or user-busy boundary
                    require(bool(block) and len(block) <= min(BLOCK, remaining), 'Truncated or oversized body')
                    output.write(block)
                    h.update(block)
                    offset += len(block)
                    remaining -= len(block)
                    received += len(block)
                    delay = received / RATE - (clock() - began)
                    if delay > 0:
                        sleeper(min(delay, 1.0))
                require(response.read(1) == b'', 'Response overrun')
                output.flush()
                os.fsync(output.fileno())
    checkpoint(force=True)
    require(offset == spec['size'] and h.hexdigest() == spec['sha256'], 'Asset checksum mismatch; preserve partial')
    require(not final.exists(), 'Final path appeared during transfer')
    os.link(partial, final)  # exclusive publication: never overwrite a final that appeared concurrently
    partial.unlink()
    return {'status': 'DOWNLOADED_VERIFIED', 'bytes': offset, 'sha256': h.hexdigest()}


def authorized_serving(health, telemetry):
    """Active/queued requests are allowed; health, owner policy and typed counters remain mandatory."""
    switcher = health.get('switcher', {})
    work = telemetry.get('work', {})
    return (health.get('status') == 'ok' and health.get('loaded') is True
            and health.get('max_context') == 1048576 and health.get('images') is True
            and type(health.get('busy')) is bool
            and switcher.get('active_model') == switcher.get('default_model') == 'deepseek'
            and switcher.get('fault') is None
            and all(type(switcher.get(k)) is int and switcher[k] >= 0 for k in ['inflight', 'waiting'])
            and all(type(work.get(k)) is int and work[k] >= 0 for k in ['active', 'queued', 'admission_reserved']))


def authorization(q):
    path = HERE / 'AUTHORIZATION.json'
    require(digest(path) == AUTHORIZATION_SHA and q.get('authorization_sha256') == AUTHORIZATION_SHA
            and q.get('active_inference_authorized') is True, 'Explicit active-inference authorization required')
    data = json.loads(path.read_text())
    require(data.get('active_inference_may_continue_during_download') is True
            and data.get('interruption_of_active_deepseek_inference_authorized') is True
            and data.get('no_phase_or_owner_bypass') is True, 'Foreign authorization policy')


class SelectedGate:
    def __init__(self):
        support = E / 'decode-optimization-20261028/iq2s-persistent-v1/model-v1'
        for name, expected in RUNTIME_PINS.items():
            require(digest(support / name) == expected, 'Existing read-only support changed')
        sys.path.insert(0, str(support))
        import iq2s_model_runtime as runtime
        require(Path(runtime.__file__) == support / 'iq2s_model_runtime.py', 'Foreign support origin')
        self.runtime = runtime
        state = json.loads((E / 'STATE.json').read_text())
        if not runtime.phase_keys_free(state):
            raise Deferred('Private phase, build or restoration active')
        a, _ = runtime.support()
        self.host = a.ChunkProductionHost()
        self.host.start_binding = runtime.current_binding(state)
        self()
        self.host.guard_binding(self.host.start_binding['native_pid'])

    def __call__(self):
        state = json.loads((E / 'STATE.json').read_text())
        if not self.runtime.phase_keys_free(state):
            raise Deferred('Private phase, build or restoration active')
        require(self.runtime.current_binding(state) == self.host.start_binding, 'Selected owner binding changed')
        require(authorized_serving(self.host.get('/health'), self.host.get('/v1/telemetry')),
                'Selected serving health/policy invalid; preserve partials')


def qualification(path, expected):
    require(re.fullmatch('[0-9a-f]{64}', expected or '') is not None and digest(path) == expected,
            'Explicit immutable acquisition qualification pin required')
    q = json.loads(Path(path).read_text())
    require(q['both_hosts_passed'] is True and q['manual_review_passed'] is True, 'Acquisition qualification absent')
    require(set(q['sources']) == SOURCE_NAMES, 'Exact acquisition source map required')
    for name, pin in q['sources'].items():
        require(digest(HERE / name) == pin, 'Acquisition source changed')
    authorization(q)
    proofs = []
    for label in ['mac', 'ubuntu']:
        proof_path = HERE / ('CPU-FIRST-' + label + '.json')
        require(digest(proof_path) == q['proofs'][label], 'CPU receipt changed')
        proof = json.loads(proof_path.read_text())
        require(proof['passed'] is True and proof['returncode'] == 0 and proof['source_map'] == q['sources']
                and proof['test_ids'] == q['test_ids'] and proof['tests_run'] == len(q['test_ids'])
                and proof['failures'] == proof['errors'] == 0 and proof['physical_host'] == label,
                'Incomplete exact CPU receipt')
        require(proof['child_controls'] == {'CPU_seconds': 30, 'wall_seconds': 90, 'nice_increment': 15,
                'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
                'MALLOC_ARENA_MAX': '1', 'Linux_AS_bytes': 512 * 2**20}, 'CPU bounds changed')
        require(proof['actual_child_CPU_limit'] == [30, 30] and 15 <= proof['actual_child_nice'] <= 19,
                'CPU child limits not observed')
        require(proof['actual_child_Linux_AS_limit'] == ([512 * 2**20, 512 * 2**20] if label == 'ubuntu' else None),
                'CPU child address-space limit not observed')
        proofs.append(proof)
    require(bool(q['test_ids']) and len(set(q['test_ids'])) == len(q['test_ids']), 'Unique CPU IDs required')
    return q


def retained_inventory(root, specs):
    real_directory(root)
    allowed = {Path(s['path']) for s in specs}
    parents = {p.parent.name for p in allowed}
    total = 0
    for parent in root.iterdir():
        require(parent.name in parents, 'Foreign asset directory')
        real_directory(parent)
        for leaf in parent.iterdir():
            rel = leaf.relative_to(root)
            canonical = rel.with_name(rel.name[:-8]) if rel.name.endswith('.partial') else rel
            require(canonical in allowed, 'Foreign retained asset')
            safe_file(leaf)
            require(leaf.is_file(), 'Foreign retained directory')
            expected = next(s for s in specs if s['path'] == str(canonical))['size']
            require(leaf.stat().st_size <= expected, 'Oversized retained asset')
            other = root / (str(canonical) if rel.name.endswith('.partial') else str(canonical)+'.partial')
            require(not other.exists() and not other.is_symlink(), 'Ambiguous final and partial files')
            total += leaf.stat().st_size
    return total


def main(qualification_pin):
    require(HERE == E / 'decode-optimization-20261028/maya-s-comparison-v1/acquisition-authorized-v2',
            'Physical Ubuntu authorized-resume namespace only')
    d = manifest(HERE / 'ASSET_MANIFEST.json')
    qualification(HERE / 'acquisition-qualification.json', qualification_pin)
    gate = SelectedGate()  # before lock, output-directory creation or model writes
    deadline = time.monotonic() + 4 * 3600
    real_directory(HERE)
    # Production intentionally holds experiment.lock for its entire lifetime. Acquisition never touches it.
    safe_file(HERE.parent / 'acquisition.lock')
    with (HERE.parent / 'acquisition.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gate()
        root = HERE.parent / 'assets'  # exact retained assets; source and attempt receipts are version-isolated
        if not root.exists():
            root.mkdir()
        real_directory(root)
        retained = retained_inventory(root, d['files'])
        require(shutil.disk_usage(root).free >= RESERVE + max(0, d['total_bytes'] - retained),
                'Insufficient full-download disk budget')
        receipt = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'pid': os.getpid(),
                   'status': 'PASSIVE_DOWNLOAD_RUNNING', 'manifest_sha256': MANIFEST_SHA,
                   'authorization_sha256': AUTHORIZATION_SHA, 'active_inference_authorized': True,
                   'binding': gate.host.start_binding, 'files': [], 'model_or_service_actions': 0}
        attempt = HERE / ('acquisition-attempt-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                          + '-' + str(os.getpid()) + '.json')
        require(not attempt.exists(), 'Fresh attempt receipt required')
        emit(attempt, receipt)
        emit(HERE / 'acquisition-state.json', receipt)
        code = 0
        try:
            for spec in d['files']:
                result = acquire_file(spec, root, gate, deadline=deadline)
                receipt['files'].append({'path': spec['path'], **result})
                emit(HERE / 'acquisition-state.json', receipt)
            receipt['status'] = 'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN'
        except (Exception, KeyboardInterrupt) as exc:
            receipt['status'] = 'DEFERRED_PARTIALS_RETAINED' if isinstance(exc, Deferred) else 'ACQUISITION_HOLD_PARTIALS_RETAINED'
            receipt['error_type'] = type(exc).__name__
            # No redirect URL, response body, environment, credentials or user data in receipts.
            receipt['reason'] = str(exc) if isinstance(exc, (Deferred, ValueError)) else 'Transport/OS failure; no automatic retry'
            code = 75 if isinstance(exc, Deferred) else 1
        receipt['updated_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        receipt['returncode'] = code
        emit(HERE / 'acquisition-state.json', receipt)
        emit(attempt, receipt)
        print(json.dumps(receipt))
        return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--qualification-pin', required=True)
    args = parser.parse_args()
    try:
        raise SystemExit(main(args.qualification_pin))
    except Deferred as exc:
        print(json.dumps({'status': 'DEFERRED_BEFORE_ACQUISITION', 'reason': str(exc)}))
        raise SystemExit(75)
