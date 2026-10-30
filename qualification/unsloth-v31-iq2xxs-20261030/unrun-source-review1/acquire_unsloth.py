"""Pinned parallel Unsloth download, with space reserved for pending Maya-S.

Uses the already reviewed byte-range transfer primitive in a private imported
module. No model, GPU, build, service, or production lock operation exists here.
"""
import argparse
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time

HERE = Path(__file__).resolve().parent
E = HERE.parents[1]
MAYA = E / 'decode-optimization-20261028/maya-s-comparison-v1'
ACQ = MAYA / 'acquisition-authorized-v2'
PRIMITIVE_SHA = '6a399f4eec7b9cb23b7ff7aa03d60deb490787825ae92e43ccde8d40065885b5'
PRIOR_Q_SHA = '3f89fe089d629bb65b5c517908ae76a731b9020fb0a8cb02a1b1ef58472596b0'
MANIFEST_SHA = '4fb4c0ff9c0b55f46afa15c2cbc84ee09372c85944efafb63e36a5ca6e73c73c'
AUTH_SHA = '3885bafb209d6eb86e76191da185163b9c342337bba56eb8df533e714abca648'
MAYA_MANIFEST_SHA = '22ecce3e7085e29520fadaa67d603beb8cc0905f834ff3563029f6038825034b'
REPO = 'unsloth/DeepSeek-V4.1-Flash-1017-GGUF'
REVISION = '8a6ec9cf118e785a362ea94ee123c61c70553be6'
TOTAL = 300475464795
MAYA_TOTAL = 347445667721
FLOOR = 144 * 2**30  # root132 + unchanged8GiB private cache /4GiB logs
CUSHION = 256 * 2**20  # two in-flight128MiB range writes
RATE = 16 * 2**20
WALL = 21600
ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1'}


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(2**20), b''): h.update(block)
    return h.hexdigest()


def manifest():
    require(sha(HERE / 'ASSET_MANIFEST.json') == MANIFEST_SHA and sha(HERE / 'AUTHORIZATION.json') == AUTH_SHA,
            'Exact new manifest/authorization required')
    m = json.loads((HERE / 'ASSET_MANIFEST.json').read_text())
    names = ['UD-IQ2_XXS/DeepSeek-V4.1-Flash-1017-UD-IQ2_XXS-%05d-of-00006.gguf' % i for i in range(1, 7)]
    require(m['repo'] == REPO and m['revision'] == REVISION and [s['path'] for s in m['files']] == names,
            'Exact six-shard v3.1 inventory required')
    require(m['total_bytes'] == TOTAL and sum(s['size'] for s in m['files']) == TOTAL
            and m['root_reserve_bytes'] == 132 * 2**30 and m['comparison_cache_log_reserve_bytes'] == 12 * 2**30
            and m['parallel_Maya_S_total_bytes'] == MAYA_TOTAL and m['rate_bytes_per_second'] == RATE
            and m['wall_seconds'] == WALL, 'Frozen combined budgets changed')
    for s in m['files']:
        require(set(s) == {'path', 'size', 'sha256'} and type(s['size']) is int and s['size'] > 0
                and re.fullmatch('[0-9a-f]{64}', s['sha256']) is not None, 'Typed checksum inventory required')
    return m


def combined_space(free, retained, maya_retained):
    require(type(free) is type(retained) is type(maya_retained) is int
            and free >= 0 and 0 <= retained <= TOTAL and 0 <= maya_retained <= MAYA_TOTAL, 'Typed parallel space counters required')
    wanted = FLOOR + CUSHION + (TOTAL - retained) + (MAYA_TOTAL - maya_retained)
    require(free >= wanted, 'Insufficient reserved space for BOTH complete downloads plus comparison reserves')
    return {'free_bytes': free, 'required_bytes': wanted, 'Unsloth_remaining_bytes': TOTAL - retained,
            'Maya_S_remaining_bytes': MAYA_TOTAL - maya_retained, 'root_plus_comparison_floor_bytes': FLOOR}


def concurrent_maya_retained(root, specs):
    """Budget snapshot only, tolerate the other owner's link/unlink publication.

    This never grants checksum/model custody. A missed concurrent leaf merely
    over-reserves that file's remaining space.
    """
    total = 0
    for s in specs:
        final = Path(root) / s['path']; partial = final.with_name(final.name + '.partial'); rows = []
        require(not any(p.is_symlink() for p in (final.parent, *final.parent.parents)),
                'Parallel Maya-S budget parent alias refused')
        for path in (final, partial):
            try: v = path.lstat()
            except FileNotFoundError: continue
            require(stat.S_ISREG(v.st_mode) and v.st_size <= s['size'] and v.st_nlink in (1, 2),
                    'Parallel Maya-S budget leaf invalid')
            rows.append(v)
        if len(rows) == 2:
            require((rows[0].st_dev, rows[0].st_ino, rows[0].st_size) ==
                    (rows[1].st_dev, rows[1].st_ino, rows[1].st_size), 'Ambiguous parallel Maya-S publication')
        total += max((v.st_size for v in rows), default=0)
    return total


def primitive():
    require(sha(ACQ / 'acquire.py') == PRIMITIVE_SHA and sha(ACQ / 'acquisition-qualification.json') == PRIOR_Q_SHA,
            'Qualified transfer/read-only owner source changed')
    old = json.loads((ACQ / 'acquisition-qualification.json').read_text())
    for name, pin in old['files'].items(): require(sha(name) == pin, 'Inherited exact source pin changed')
    spec = importlib.util.spec_from_file_location('_unsloth_byte_transfer_v1', ACQ / 'acquire.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.qualification(ACQ / 'acquisition-qualification.json', PRIOR_Q_SHA)
    # Private module instance only: the running Maya-S process/source is untouched.
    module.REPO = REPO; module.REVISION = REVISION; module.RATE = RATE
    return module


class Gate:
    def __init__(self, a, m):
        self.a, self.m = a, m
        self.selected = a.SelectedGate()
        require(sha(MAYA / 'ASSET_MANIFEST.json') == MAYA_MANIFEST_SHA, 'Parallel Maya-S inventory changed')
        self.maya_specs = json.loads((MAYA / 'ASSET_MANIFEST.json').read_text())['files']
        self.last_budget = None; self()

    def __call__(self):
        self.selected()  # exact current owner, healthy1M/images/default, no private/build/restoration
        pause = HERE / 'pause-for-comparison.json'
        if pause.exists():
            s = json.loads(pause.read_text()); require(s.get('authorization_sha256') == AUTH_SHA
                  and s.get('pause_before_private_phase') is True, 'Foreign pause policy')
            raise self.a.Deferred('Paused before separately admitted Maya-S private comparison; partials retained')
        own = HERE / 'assets'
        retained = self.a.retained_inventory(own, self.m['files']) if own.exists() else 0
        maya_retained = concurrent_maya_retained(MAYA / 'assets', self.maya_specs)
        self.last_budget = combined_space(shutil.disk_usage(HERE).free, retained, maya_retained)


def qualified(pin):
    path = HERE / 'qualification.json'; require(sha(path) == pin, 'New download qualification pin changed')
    q = json.loads(path.read_text())
    require(q['root_entire_source_and_tests_read'] is True and q['astra_entire_source_and_tests_read'] is True,
            'Both manual source/test reviews required')
    for name, digest in q['files'].items(): require(sha(name) == digest, 'New immutable source/input/proof changed')
    needed = {str(HERE / n): pin for n, pin in q['source_sha256'].items()}
    needed.update({str(E / n): pin for n, pin in q['input_sha256'].items()})
    require(all(q['files'].get(n) == pin for n, pin in needed.items()), 'Actual CPU source/input map omitted')
    for label in ('darwin', 'linux'):
        folder = HERE / ('CPU-FIRST-' + label)
        require(all(str(folder / n) in q['files'] for n in ('receipt.json', 'child.json', 'child.log')),
                'Raw bounded CPU pins missing')
        r = json.loads((HERE / ('CPU-FIRST-' + label) / 'receipt.json').read_text())
        c = json.loads((HERE / ('CPU-FIRST-' + label) / 'child.json').read_text())
        require(r['passed'] is True and r['test_ids'] == q['test_ids'] and r['controls'] == len(q['test_ids'])
                and r['source_sha256'] == q['source_sha256'] and r['input_sha256'] == q['input_sha256']
                and type(c['returncode']) is int and c['returncode'] == 0 and c['error'] is None
                and c['cleanup_errors'] == [] and c['CPU_limit_seconds'] == 30 and c['wall_limit_seconds'] == 90
                and c['nice_increment'] == 15 and r['CPU_seconds'] == [30, 30] and r['nice'] >= 15
                and r['Linux_AS_bytes'] == ([512 * 2**20] * 2 if label == 'linux' else None)
                and r['environment'] == c['environment'] == dict(ENV, PYTHONDONTWRITEBYTECODE='1'),
                'Exact bounded CPU proof missing')
    return q


def main(pin):
    q = qualified(pin); m = manifest(); a = primitive(); gate = Gate(a, m)
    require(gate.selected.host.start_binding == q['selected_binding'], 'Selected owner changed since separate download admission')
    require(HERE == Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/unsloth-v31-iq2xxs-download-v1'),
            'Physical Ubuntu acquisition namespace required')
    with (HERE / 'download.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); gate()
        root = HERE / 'assets'
        if not root.exists(): root.mkdir()
        a.real_directory(root)
        receipt = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'pid': os.getpid(),
            'status': 'PINNED_UNSLOTH_DOWNLOAD_RUNNING', 'manifest_sha256': MANIFEST_SHA,
            'authorization_sha256': AUTH_SHA, 'revision': REVISION, 'files': [], 'model_or_service_actions': 0,
            'combined_space_at_admission': gate.last_budget, 'rate_bytes_per_second': RATE, 'wall_seconds': WALL}
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        attempt = HERE / ('attempt-' + stamp + '-' + str(os.getpid()) + '.json')
        require(not attempt.exists(), 'Fresh acquisition attempt required'); a.emit(attempt, receipt)
        a.emit(HERE / 'STATE.json', receipt); code = 0
        try:
            deadline = time.monotonic() + WALL
            for s in m['files']:
                receipt['files'].append({'path': s['path'], **a.acquire_file(s, root, gate, deadline=deadline)})
                a.emit(HERE / 'STATE.json', receipt)
            receipt['status'] = 'ALL_SIX_UNSLOTH_ASSETS_VERIFIED_NO_MODEL_RUN'
        except (Exception, KeyboardInterrupt) as exc:
            receipt.update(status='DEFERRED_PARTIALS_RETAINED' if isinstance(exc, a.Deferred) else 'ACQUISITION_HOLD_PARTIALS_RETAINED',
                error_type=type(exc).__name__, reason=str(exc) if isinstance(exc, (a.Deferred, ValueError)) else 'Transport/OS failure; no automatic retry')
            code = 75 if isinstance(exc, a.Deferred) else 1
        receipt.update(returncode=code, updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        a.emit(HERE / 'STATE.json', receipt); a.emit(attempt, receipt); print(json.dumps(receipt), flush=True)
        return code


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--qualification-pin', required=True); args = p.parse_args()
    raise SystemExit(main(args.qualification_pin))
