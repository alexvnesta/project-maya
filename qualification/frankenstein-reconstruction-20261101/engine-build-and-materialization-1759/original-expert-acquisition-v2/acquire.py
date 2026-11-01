"""Passive acquisition of the index-derived40 original trunk-expert shards.

This is a conservative dependency closure, not a frozen1870-expert selection or
the full original model. No inference, services, GPU ownership or CPU claims.
Only a separately pinned, live qualified bulk conversion may coexist after idle
admission. Existing51-control transport is reused without replaying its tests.
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
import sys
import time

HERE = Path(__file__).resolve().parent
Q = HERE.parent
E = Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025')
EXPECTED = E / 'decode-optimization-20261028/s2-reconstruction-v1/original-expert-acquisition-v2'
LEGACY = Q / 'iq3s-source-acquisition-v1'
LEGACY_SHA = '5a1b1041ea0e1dc3488dc2259302eb5bbe610a5297a1ca000c3cc1f4a6d1d4b7'
LEGACY_Q_SHA = '1b6065d122dcbfebbd6ae36e7cccf39e9da9a25fe9fdf7ed0f19f88a7097e95e'
HEALTH_SHA = '4f40c04a69701cf86e478bdf4f13a021de05f18fae1b943fcd7b88aee19295fd'
OWNER = HERE.parents[1] / 'cpu-iq2xs-upstream623-v1/build-v3/build.py'
OWNER_SHA = 'a765195c6fc6fe65e2d780bce3d166d28f181de722d68d725f7bceb568dd7380'
INDEX = Q / 'source-plan-v1/inputs/official-index-FIRST.json'
METADATA = Q / 'source-plan-v1/inputs/official-HF-metadata-FIRST.json'
INDEX_SHA = '74b0686a3d2891980d5e303251b075a3bccae2c2ff650747db2620a649b98fa8'
METADATA_SHA = 'f4f8d13ede75d7ad4918c602d6b5f3e0c6981f2afa4f8e7bc685d4292d51045a'
MANIFEST_SHA = '68503758fd9ca619be1a165ce506809dd45e3bc23cd754f9c1220b9e82132df4'
REVISION = '1bae0e1088993b9b82de08f59de5be5a34e42170'
REPO = 'deepseek-ai/DeepSeek-V4.1-Flash-1017'
RESERVE = 132 * 2**30
NATIVE_BYTES, OVERLAY_BYTES = 35157299200, 2 * 19464192000
RATE, CHUNK = 128 * 2**20, 128 * 2**20
TOTAL_BYTES = 295672271408
PHASE_KEYS = ('active_private_phase', 'active_GPU_phase', 'active_gpu_experiment', 'private_window',
              'active_cpu_build', 'production_restore_in_progress', 'production_verification_pending',
              'production_temporarily_stopped')
SOURCES = ('acquire.py', 'test_acquire.py', 'run_cpu.py', 'ASSET_MANIFEST.json')


class Deferred(Exception): pass


def require(ok, reason):
    if not ok: raise ValueError(reason)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_exact(name, path, pin):
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink() and
            path.is_file() and sha(path) == pin, 'Pinned source changed: ' + name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def transport():
    old = load_exact('original_expert_qualified_transport', LEGACY / 'acquire.py', LEGACY_SHA)
    # The only transport-policy change: one sequential128MiB/s stream, with the
    # qualified128MiB range/5s timeout, checksum/resume and exclusive publication.
    old.RATE = RATE
    require(old.CHUNK == CHUNK and old.RESERVE == RESERVE and old.REVISION == REVISION,
            'Qualified transport geometry changed')
    return old


def derive_closure(index, metadata, *, layers=40, experts=384):
    require(metadata.get('id') == REPO and metadata.get('sha') == REVISION, 'Exact original metadata revision')
    weights = index['weight_map']; files = set()
    # Every original routed weight and its scale is an explicit dependency.
    for layer in range(layers):
        for expert in range(experts):
            for role in ('w1', 'w3', 'w2'):
                for kind in ('weight', 'scale'):
                    key = 'layers.%d.ffn.experts.%d.%s.%s' % (layer, expert, role, kind)
                    require(key in weights, 'Incomplete routed expert/scale coverage: ' + key)
                    name = weights[key]
                    require(re.fullmatch(r'model-\d{5}-of-00048\.safetensors', name), 'Canonical source shard')
                    files.add(name)
    siblings = {}
    for row in metadata['siblings']:
        name = row['rfilename']
        require(name not in siblings, 'Duplicate metadata filename')
        siblings[name] = row
    result = []
    for name in sorted(files):
        row = siblings[name]; lfs = row['lfs']
        require(type(row['size']) is int and row['size'] > 0 and lfs['size'] == row['size'] and
                re.fullmatch('[0-9a-f]{64}', lfs['sha256']), 'Exact published LFS size/SHA required')
        result.append({'path': 'original/' + name, 'size': row['size'], 'sha256': lfs['sha256']})
    return result


def manifest():
    require(sha(HERE / 'ASSET_MANIFEST.json') == MANIFEST_SHA and sha(INDEX) == INDEX_SHA and
            sha(METADATA) == METADATA_SHA, 'Exact frozen manifest/index/metadata')
    value = json.loads((HERE / 'ASSET_MANIFEST.json').read_text())
    derived = derive_closure(json.loads(INDEX.read_text()), json.loads(METADATA.read_text()))
    expected_names = ['original/model-%05d-of-00048.safetensors' % i for i in range(3, 43)]
    require(value['repo'] == REPO and value['revision'] == REVISION and value['files'] == derived and
            [r['path'] for r in derived] == expected_names and len(derived) == 40 and
            sum(r['size'] for r in derived) == value['total_bytes'] == TOTAL_BYTES and
            value['root_reserve_bytes'] == RESERVE and value['additional_native_bytes'] == NATIVE_BYTES and
            value['additional_overlay_bytes'] == OVERLAY_BYTES and value['index_sha256'] == INDEX_SHA and
            value['metadata_sha256'] == METADATA_SHA, 'Exact40 trunk-only dependency closure and byte budget')
    return value


def input_map():
    return {'index': sha(INDEX), 'metadata': sha(METADATA), 'legacy_transport': sha(LEGACY / 'acquire.py'),
            'legacy_qualification': sha(LEGACY / 'acquisition-qualification.json'),
            'legacy_health': sha(LEGACY / 'healthy_guard.py'), 'lease_owner': sha(OWNER)}


def source_map(): return {name: sha(HERE / name) for name in SOURCES}


def cpu_proof_contract(proof, label, sources, inputs, ids):
    require(proof.get('passed') is True and proof.get('physical_host') == label and
            proof.get('source_map') == sources and proof.get('input_map') == inputs and
            proof.get('test_ids') == ids and proof.get('tests_run') == len(ids) and
            proof.get('returncode') == 0 and proof.get('failures') == proof.get('errors') == 0,
            'Matching complete physical controls required')
    platform = {'mac': 'darwin', 'ubuntu': 'linux'}[label]
    row = proof.get('observed', {})
    env = row.get('environment', {})
    require(row.get('platform') == platform and row.get('cpu') == [30, 30] and row.get('nice') == 15 and
            row.get('as') == ([512 * 2**20] * 2 if platform == 'linux' else None) and
            row.get('dont_write_bytecode') is True and type(row.get('pid')) is int and
            row['pid'] > 1 and row.get('pgid') == row['pid'] and
            all(env.get(k) == v for k, v in {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1',
                'OPENBLAS_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1'}.items()),
            'Actual portable data-control bounds required')


def qualification(pin):
    path = HERE / 'acquisition-qualification.json'
    require(re.fullmatch('[0-9a-f]{64}', pin or '') and sha(path) == pin, 'Exact new acquisition qualification')
    q = json.loads(path.read_text())
    require(q.get('manual_review_passed') is True and q.get('both_hosts_passed') is True and
            q.get('sources') == source_map() and q.get('inputs') == input_map() and
            q.get('selected_binding') and q.get('test_ids'), 'Current manual/source/both-host qualification')
    require(re.fullmatch('[0-9a-f]{64}', q.get('future_bulk_qualification_sha256', '')) and
            sha(Q / 'iq3s-bulk-v1/qualification.json') == q['future_bulk_qualification_sha256'],
            'Exact newly qualified bulk conversion; no other CPU build allowance')
    for label in ('mac', 'ubuntu'):
        proof_path = HERE / ('CPU-FIRST-' + label + '.json')
        require(sha(proof_path) == q['proofs'][label], 'Exact physical FIRST receipt')
        proof = json.loads(proof_path.read_text())
        cpu_proof_contract(proof, label, q['sources'], q['inputs'], q['test_ids'])
    return q


def binding_of(state):
    identity = state.get('decode_optimization_current', {}).get('selected_identity')
    if identity is None: identity = state['chunk4096_activation']['selected_identity']
    return identity['start_binding']


def bulk_contract(record, binding, pin):
    require(type(record) is dict and record.get('mode') == 's2-iq3s-bulk-FIRST' and
            record.get('qualification_sha256') == pin and record.get('start_binding') == binding and
            type(record.get('controller_pid')) is int and record['controller_pid'] > 1 and
            type(record.get('controller_start_ticks')) is int and record['controller_start_ticks'] > 0,
            'Only exact qualified selected-owner bulk conversion may coexist')


def verify_live_bulk(record, binding, pin, owner):
    bulk_contract(record, binding, pin)
    path = Q / 'iq3s-bulk-v1/qualification.json'
    require(sha(path) == pin, 'Bulk qualification changed')
    qualified = json.loads(path.read_text())
    require(qualified.get('selected_binding') == binding and qualified.get('CPU_both_hosts_passed') is True and
            qualified.get('entire_source_tests_driver_manually_read') is True, 'Live bulk qualification/binding')
    pid = record['controller_pid']; ticks = record['controller_start_ticks']
    require(owner.process_ticks(pid) == ticks, 'Bulk controller identity is not live')
    lock_path = E / 'cpu-build.lock'
    fd = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        identity = owner.lock_identity(fd, lock_path)
        # Existing qualified parser checks exact FLOCK writer PID, inode and no
        # blocked waiter. This is the CPU lock, not production experiment.lock.
        owner.gpu_lock_row(Path('/proc/locks').read_text(), identity, pid)
        require(owner.lock_identity(fd, lock_path) == identity and owner.process_ticks(pid) == ticks,
                'Bulk CPU lease/controller changed across observation')
    finally: os.close(fd)


def phase_view(state, binding, *, admitted, bulk_pin, verify):
    for key in PHASE_KEYS:
        if key != 'active_cpu_build' and state.get(key):
            raise Deferred('Private phase or restoration active before hosting observation')
    require(binding_of(state) == binding, 'Selected binding changed before hosting observation')
    record = state.get('active_cpu_build')
    if record:
        if not admitted: raise Deferred('Initial acquisition admission requires no CPU build')
        try: verify(record, binding, bulk_pin)
        except Exception as exc:
            raise Deferred('CPU build is not the exact live qualified conversion') from exc
    # Normalize only the verified CPU conversion. Unrelated STATE progress,
    # including acquisition/conversion counters, is intentionally irrelevant.
    return {'binding': binding, 'phases': {key: False for key in PHASE_KEYS}}


class SelectedGate:
    def __init__(self, q, old):
        self.q, self.old, self.admitted = q, old, False
        self.binding = q['selected_binding']
        self.owner = load_exact('original_expert_lease_owner', OWNER, OWNER_SHA)
        # Reject private/build/restoration state before importing endpoint support.
        self.view()
        support = E / 'decode-optimization-20261028/iq2s-persistent-v1/model-v1'
        for name, pin in old.RUNTIME_PINS.items():
            require(sha(support / name) == pin, 'Existing passive support changed')
        sys.path.insert(0, str(support))
        import iq2s_model_runtime as runtime
        require(Path(runtime.__file__) == support / 'iq2s_model_runtime.py', 'Exact passive runtime origin')
        require(tuple(runtime.PHASE_KEYS) == PHASE_KEYS, 'Meaningful phase keys changed')
        a, _ = runtime.support(); self.host = a.ChunkProductionHost(); self.host.start_binding = self.binding
        self.healthy = load_exact('original_expert_healthy', LEGACY / 'healthy_guard.py', HEALTH_SHA)
        self()
        self.admitted = True

    def view(self):
        state = json.loads((E / 'STATE.json').read_text())
        def evaluate(value):
            return phase_view(value, self.binding, admitted=self.admitted,
                bulk_pin=self.q['future_bulk_qualification_sha256'],
                verify=lambda r, b, p: verify_live_bulk(r, b, p, self.owner))
        try: return evaluate(state)
        except Deferred:
            # A normal exact bulk completion can release its CPU claim/lock
            # between our STATE and /proc reads. Re-read once only when the
            # recorded claim actually changed; validate every meaningful phase
            # again. This is no endpoint/transport retry or foreign-build bypass.
            current = json.loads((E / 'STATE.json').read_text())
            if state.get('active_cpu_build') and current.get('active_cpu_build') != state.get('active_cpu_build'):
                return evaluate(current)
            raise

    def __call__(self):
        before = self.view()  # all private/foreign-build refusals precede endpoints
        if not self.admitted and not self.host.idle():
            raise Deferred('Initial source acquisition requires idle')
        self.healthy.health_contract(self.host.get('/health'), self.host.get('/v1/telemetry'))
        self.host.guard_binding(self.binding['native_pid'])
        require(self.view() == before, 'Meaningful phase or binding changed across observation')


def disk_admission(free, total, retained):
    require(type(retained) is int and 0 <= retained <= total, 'Bounded retained source bytes')
    # Base assets already consume free space and are not charged again. Keep the
    # full additional native and two-overlay allowance conservatively; this code
    # never guesses that an unverified existing output satisfies that allowance.
    need = RESERVE + (total - retained) + NATIVE_BYTES + OVERLAY_BYTES
    require(free >= need, 'Full remaining source plus native/two overlays/root132 unavailable')
    return need


def main(pin):
    require(HERE == EXPECTED and sys.platform == 'linux' and sys.flags.isolated and sys.dont_write_bytecode,
            'Exact isolated Ubuntu passive acquisition only')
    d = manifest(); q = qualification(pin); old = transport()
    old.qualification(LEGACY / 'acquisition-qualification.json', LEGACY_Q_SHA)  # inspect existing51 proof; no rerun
    gate = SelectedGate(q, old)
    deadline = time.monotonic() + 4 * 3600
    old.real_directory(LEGACY); old.safe_file(LEGACY / 'acquisition.lock')
    with (LEGACY / 'acquisition.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # same original writer exclusion
        gate(); root = LEGACY / 'assets'; old.real_directory(root)
        retained = old.retained_inventory(root, d['files'])
        required = disk_admission(shutil.disk_usage(root).free, d['total_bytes'], retained)
        receipt = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'pid': os.getpid(),
            'status': 'PASSIVE_TRUNK_EXPERT_DOWNLOAD_RUNNING', 'manifest_sha256': MANIFEST_SHA,
            'binding': gate.binding, 'files': [], 'asset_root': str(root), 'model_or_service_actions': 0,
            'conservative_trunk_dependency_files': 40, 'actual1870_selection_frozen': False,
            'initial_retained_bytes': retained, 'initial_required_free_bytes': required,
            'rate_bytes_per_second': RATE, 'native_additional_bytes': NATIVE_BYTES,
            'two_overlay_additional_bytes': OVERLAY_BYTES,
            'allowed_bulk_qualification_sha256': q['future_bulk_qualification_sha256']}
        attempt = HERE / ('acquisition-attempt-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                          + '-' + str(os.getpid()) + '.json')
        require(not attempt.exists(), 'Fresh acquisition attempt')
        old.emit(attempt, receipt); old.emit(HERE / 'acquisition-state.json', receipt)
        code = 0
        try:
            for spec in d['files']:
                # Sequential transport means aggregate rate is the one stream's
                #128MiB/s ceiling. No transport retry is added here.
                try: result = old.acquire_file(spec, root, gate, deadline=deadline)
                except old.Deferred as exc: raise Deferred(str(exc)) from exc
                receipt['files'].append({'path': spec['path'], **result})
                old.emit(HERE / 'acquisition-state.json', receipt)
            receipt['status'] = 'ALL_FORTY_TRUNK_EXPERT_SHARDS_VERIFIED_NO_MODEL_RUN'
        except (Exception, KeyboardInterrupt) as exc:
            receipt['status'] = 'DEFERRED_PARTIALS_RETAINED' if isinstance(exc, Deferred) else 'ACQUISITION_HOLD_PARTIALS_RETAINED'
            receipt['error_type'] = type(exc).__name__
            receipt['reason'] = str(exc) if isinstance(exc, (Deferred, ValueError)) else 'Transport/OS failure; no automatic retry'
            code = 75 if isinstance(exc, Deferred) else 1
        receipt['updated_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat(); receipt['returncode'] = code
        old.emit(HERE / 'acquisition-state.json', receipt); old.emit(attempt, receipt)
        print(json.dumps(receipt)); return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--qualification-pin', required=True)
    args = parser.parse_args()
    try: raise SystemExit(main(args.qualification_pin))
    except Deferred as exc:
        print(json.dumps({'status': 'DEFERRED_BEFORE_ACQUISITION', 'reason': str(exc)})); raise SystemExit(75)
