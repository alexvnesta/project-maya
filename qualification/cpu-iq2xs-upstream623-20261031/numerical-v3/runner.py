"""One finite CPU numerical sequence. No native model, GPU or service operation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
N = HERE.parent
D = N.parent
R = Path('/home/alex/strata-deepseek-test-20261024')
E = R / 'reliability-optimization-20261025'
EXPECTED = E / 'decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3'
BUILD = N / 'build-v3/build.py'
BUILD_SHA = 'a765195c6fc6fe65e2d780bce3d166d28f181de722d68d725f7bceb568dd7380'
FIXTURE = N / 'build-v3/build-FIRST/iq2xs_exact'
FIXTURE_SOURCE_SHA = '33ede583a7c299a9bac83520050a6ea48233ae596fe6bb0a0f8195dbb7dfd6e7'
CPU_RECEIPT_SHA = 'f24529205339ff74715ccdda452a65e799d2a750024289c9b786d2cdc2f1b52e'
SOFT = 1000
WALL = 1200
SCRUB = ('DS4_IQ_OWN', 'DS4_IQ_AVX2', 'DS4_IQ_GATHER', 'DS4_IQ_VERBOSE',
         'STRATA_NO_IQ256', 'STRATA_NO_IQ512', 'STRATA_NO_IQ4NL',
         'STRATA_GLM_CPU_MT', 'STRATA_GLM_CPU_1T')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(65536), b''):
            h.update(data)
    return h.hexdigest()


def exact_module(name, path, pin):
    require(path.is_absolute() and path.resolve() == path and path.is_file() and
            not path.is_symlink() and path.stat().st_nlink == 1 and sha(path) == pin,
            'Exact pinned module required')
    old = sys.modules.get(name)
    require(old is None or getattr(old, '__file__', None) == str(path), 'Foreign module origin')
    if old is None:
        spec = importlib.util.spec_from_file_location(name, path)
        old = importlib.util.module_from_spec(spec); sys.modules[name] = old
        spec.loader.exec_module(old)
    require(Path(old.__file__).resolve() == path and sha(path) == pin, 'Module changed')
    return old


def load_build():
    return exact_module('iq2xs_numerical_build_v3', BUILD, BUILD_SHA)


def jobs():
    result = []
    for n in (256, 2304, 5120):
        for mode in ('optimized', 'fallback'):
            result.append({'id': f'pure-{n}-{mode}', 'n': n, 'mode': mode, 'pair': None})
    for gu, down in ((22, 22), (22, 17), (22, 16), (17, 22), (17, 17),
                     (17, 16), (17, 18), (16, 22), (16, 17), (16, 16)):
        for n in (2304, 5120):
            for mode in ('optimized', 'fallback'):
                result.append({'id': f'mixed-{gu}-{down}-{n}-{mode}', 'n': n,
                               'mode': mode, 'pair': [gu, down]})
    return result


def command(job):
    require(type(job) is dict and any(type(job.get('n')) is int and job == v for v in jobs()),
            'Exact one of46 jobs required')
    # Canonical JSON also prevents bool/int equality from admitting malformed metadata.
    require(json.dumps(job, sort_keys=True) in [json.dumps(v, sort_keys=True) for v in jobs()],
            'Typed job differs')
    argv = [str(FIXTURE), '--n', str(job['n']), '--expect', job['mode']]
    if job['pair'] is not None: argv += ['--pair', ':'.join(map(str, job['pair']))]
    return argv


def child_environment(b, mode, temporary):
    require(mode in ('optimized', 'fallback'), 'Dispatch mode differs')
    env = b.environment()
    for name in SCRUB: env.pop(name, None)
    if mode == 'fallback': env['STRATA_NO_IQ256'] = '1'
    env['TMPDIR'] = str(temporary)
    return env


def child_preexec(b, folder, env):
    b.child_limits(30, 512 * 2**20, folder / 'observed.json', env)
    # This is a pre-exec Python witness, not an assertion that /proc/exe is the ELF.
    b.emit(folder / 'dispatch-environment.json', {'pid': os.getpid(), 'pgid': os.getpgid(0),
           'stage': 'PREEXEC_PYTHON', 'dispatch': {k: os.environ.get(k) for k in SCRUB}})


def child_budget(started, now):
    remaining = started + SOFT - now
    require(remaining > 5, 'Whole-sequence soft budget cannot admit child')
    wall = min(90.0, remaining)
    return wall - 5.0, min(now + wall, started + WALL)


def cpu_capability(text, allowed, expected):
    """Read-only Linux metadata, not a numerical or CPUID execution witness."""
    require(type(expected) is dict and set(expected) == {'vendor_id', 'cpu family', 'model', 'model name', 'stepping'}
            and all(type(v) is str and v for v in expected.values()), 'Pinned CPU identity required')
    require(type(allowed) is set and allowed and all(type(v) is int and v >= 0 for v in allowed),
            'Actual CPU affinity required')
    rows = {}
    for block in text.strip().split('\n\n'):
        values = {}
        for line in block.splitlines():
            key, sep, value = line.partition(':')
            require(sep and key.strip() not in values, 'Malformed CPU inventory')
            values[key.strip()] = value.strip()
        require(values.get('processor', '').isdigit(), 'CPU processor index missing')
        index = int(values['processor']); require(index not in rows, 'Duplicate CPU processor')
        rows[index] = values
    require(allowed <= set(rows), 'Allowed CPU absent from inventory')
    for index in allowed:
        row = rows[index]
        require({key: row.get(key) for key in expected} == expected, 'CPU identity differs')
        require({'avx', 'avx2', 'fma', 'f16c', 'xsave'} <= set(row.get('flags', '').split()), 'AVX2/FMA/F16C required')
    return {'identity': expected, 'allowed_processors': sorted(allowed),
            'required_flags': ['avx', 'avx2', 'fma', 'f16c', 'xsave'], 'source': '/proc/cpuinfo plus sched_getaffinity'}


def observed_cpu_capability(q):
    path = HERE / 'PHYSICAL_CPU_CAPABILITY.json'
    require(q['files'].get(str(path)) == CPU_RECEIPT_SHA and sha(path) == CPU_RECEIPT_SHA,
            'Physical CPU inventory custody differs')
    receipt = json.loads(path.read_text()); identity = receipt['identity']
    expected = {'vendor_id': identity['vendor_id'], 'cpu family': str(identity['cpu_family']),
                'model': str(identity['model']), 'model name': identity['model_name'], 'stepping': str(identity['stepping'])}
    allowed = set(os.sched_getaffinity(0))
    require(sorted(allowed) == receipt['allowed_processor_ids'], 'Actual CPU affinity differs from frozen inventory')
    return cpu_capability(Path('/proc/cpuinfo').read_text(), allowed, expected)


def fixture_identity(b, q):
    pin = q.get('fixture_sha256')
    require(type(pin) is str and len(pin) == 64 and all(c in '0123456789abcdef' for c in pin)
            and q['files'].get(str(FIXTURE)) == pin, 'Actual fixture digest required')
    b.regular(FIXTURE)
    require(sha(FIXTURE) == pin and os.access(FIXTURE, os.X_OK), 'Fixture identity/execute permission changed')
    with FIXTURE.open('rb') as stream: require(stream.read(4) == b'\x7fELF', 'Actual compiled ELF required')
    return pin


def child_proof(b, row, folder, env, parent_pid):
    actual = json.loads((folder / 'observed.json').read_text())
    dispatch = json.loads((folder / 'dispatch-environment.json').read_text())
    require(actual == {'pid': row['pid'], 'ppid': parent_pid, 'pgid': row['pid'],
            'cpu': [30, 30], 'as': [512 * 2**20] * 2, 'nice': 15,
            'environment': {k: env[k] for k in (*b.ENV, 'TMPDIR')}}, 'Actual child bounds/identity differ')
    require(dispatch == {'pid': row['pid'], 'pgid': row['pid'], 'stage': 'PREEXEC_PYTHON',
            'dispatch': {k: env.get(k) for k in SCRUB}}, 'Actual dispatch environment differs')


def run_one(b, parser, q, job, output, guard, owned, started, check_files):
    argv = command(job); name = job['id']; folder = output / name
    b.fresh(folder); guard(); check_files(); guard(); run_seconds, deadline = child_budget(started, time.monotonic())
    pin = fixture_identity(b, q); folder.mkdir(); temporary = folder / 'tmp'; temporary.mkdir()
    env = child_environment(b, job['mode'], temporary)
    process = None; primary = None; result = None; begin = time.monotonic()
    row = {'job': job, 'argv': argv, 'pid': None, 'returncode': None, 'error': None,
           'cleanup': [], 'fixture_sha256': pin, 'run_seconds': run_seconds,
           'deadline_monotonic': deadline, 'identity_scope': 'Pinned ELF argv plus Popen/exit/output proof; preexec Python identity only'}
    try:
        require(time.monotonic() < deadline - 5, 'Child admission budget expired')
        with (folder / 'stdout').open('xb') as out, (folder / 'stderr').open('xb') as err:
            owned.starting(name)
            process = subprocess.Popen(argv, cwd=folder, env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, start_new_session=True,
                preexec_fn=lambda: child_preexec(b, folder, env))
            owned.registered(process, name); row['pid'] = process.pid
            child_proof(b, row, folder, env, os.getpid())
            while process.poll() is None:
                guard()
                require(time.monotonic() < deadline - 5, 'Numerical child deadline')
                time.sleep(.1)
            row['returncode'] = process.returncode
            require(process.returncode == 0, 'Numerical child nonzero')
    except BaseException as exc:
        primary = exc; row['error'] = repr(exc)
    finally:
        if process is not None:
            try: b.cleanup(process, deadline)
            except BaseException as exc:
                row['cleanup'].append(repr(exc)); owned.cleanup_failed(name, exc)
                if primary is None: primary = exc
                else: primary.add_note('Owned cleanup: ' + repr(exc))
            row['returncode'] = process.poll()
        row['elapsed_seconds'] = time.monotonic() - begin
        try:
            if primary is None:
                guard(); check_files(); guard()
                require(time.monotonic() <= deadline, 'Child wall exhausted')
                require(fixture_identity(b, q) == pin, 'Fixture changed after child')
                for n in ('stdout', 'stderr'):
                    b.regular(folder / n); require((folder / n).stat().st_size <= parser.MAX_BYTES, 'Numerical output oversized')
                result = parser.parse((folder / 'stdout').read_bytes(), (folder / 'stderr').read_bytes(), job)
                row['output_sha256'] = {n: sha(folder / n) for n in ('stdout', 'stderr')}
        except BaseException as exc:
            if primary is None: primary = exc
            else: primary.add_note('Post-child verification: ' + repr(exc))
        row['error'] = None if primary is None else repr(primary)
        row['error_notes'] = [] if primary is None else list(getattr(primary, '__notes__', []))
        row['status'] = 'PASS' if primary is None else 'HOLD'
        try: b.emit(folder / 'child.json', row)
        except BaseException as exc:
            if primary is None: primary = exc
            else: primary.add_note('Child receipt: ' + repr(exc))
    if primary is not None: raise primary
    b.emit(folder / 'result.json', result)
    return {'job': job, 'pid': row['pid'], 'cases': result['cases'], 'child_sha256': sha(folder / 'child.json'),
            'result_sha256': sha(folder / 'result.json'), 'observed_sha256': sha(folder / 'observed.json'),
            'dispatch_sha256': sha(folder / 'dispatch-environment.json')}


def bootstrap(pin):
    path = HERE / 'qualification.json'
    require(sha(path) == pin, 'Qualification changed before bootstrap')
    q = json.loads(path.read_text())
    require(q['files'].get(str(BUILD)) == BUILD_SHA, 'Immutable build helper missing')
    b = load_build(); b.regular(path); b.coordination_contract(q)
    prior = D / 'model-v1/numerical-qualification.json'
    require(q['files'].get(str(prior)) == b.IMPORT_Q_SHA and sha(b.regular(prior)) == b.IMPORT_Q_SHA,
            'Original Python closure missing')
    required = {k: v for k, v in json.loads(prior.read_text())['files'].items() if k.endswith('.py')}
    required.update({str(D / 'iq2s-persistent-v1/iq2s_build.py'): b.SUPPORT_SHA,
                     str(D / 'prose-speed-v1/prose_measure.py'): b.CAS_SHA,
                     str(D / 'prose-speed-v1/transport.py'): b.TRANSPORT_SHA})
    require(all(q['files'].get(k) == v and sha(b.regular(k)) == v for k, v in required.items()),
            'Preimport Python custody differs')
    return b, q


def cpu_proofs(b, q):
    path = HERE / 'cpu_driver.py'; pin = q['source_sha256'].get('cpu_driver.py')
    require(q['files'].get(str(path)) == pin, 'New CPU driver absent')
    driver = exact_module('iq2xs_numerical_v3_cpu_driver', path, pin)
    before = driver.checked(q['source_review_sha256'])
    require((q['source_sha256'], q['input_sha256'], q['test_ids']) == before, 'New exact CPU maps differ')
    for name, value in before[0].items(): require(q['files'].get(str(HERE / name)) == value, 'New source absent')
    for name, value in before[1].items(): require(q['files'].get(name) == value, 'CPU input absent')
    require(q['files'].get(str(HERE / 'SOURCE_ROOT_REVIEW.json')) == q['source_review_sha256'], 'Manual review absent')
    for label in ('darwin', 'linux'):
        folder = HERE / ('CPU-FIRST-' + label)
        for name in ('attempt.json', 'observed.json', 'receipt.json', 'child.json', 'child.log', 'parent.json'):
            require(q['files'].get(str(folder / name)) == sha(b.regular(folder / name)), 'CPU raw proof absent')
        receipt = json.loads((folder / 'receipt.json').read_text()); child = json.loads((folder / 'child.json').read_text())
        actual = json.loads((folder / 'observed.json').read_text()); attempt = json.loads((folder / 'attempt.json').read_text())
        parent = json.loads((folder / 'parent.json').read_text())
        driver.bounds(actual, child['pid'], attempt['parent_pid'])
        require(actual['platform'] == label and child['returncode'] == 0 and child['error'] is None and
                child['cleanup'] == [] and child['elapsed_seconds'] <= 90 and receipt['status'] == 'PASS' and
                receipt['pid'] == child['pid'] and receipt['review_sha256'] == q['source_review_sha256'] and
                receipt['observed'] == actual and receipt['post_observed'] == actual and receipt['failures'] == 0 and
                receipt['errors'] == 0 and receipt['tests_run'] == len(before[2]) and receipt['test_ids'] == before[2] and
                receipt['source_sha256'] == before[0] and receipt['source_after_sha256'] == before[0] and
                receipt['input_sha256'] == before[1] and receipt['input_after_sha256'] == before[1], 'CPU receipt differs')
        driver.attempt_contract(attempt, q['source_review_sha256'], actual['ppid'], before)
        require(parent == {'status': 'PASS', 'pid': child['pid'], 'review_sha256': q['source_review_sha256'],
                'receipt_sha256': sha(folder / 'receipt.json'), 'child_sha256': sha(folder / 'child.json'),
                'log_sha256': sha(folder / 'child.log')}, 'CPU parent chain differs')


def verify_q(b, q, pin):
    require(q.get('mode') == 'numerical' and q.get('manual_source_reviewed') is True and
            q.get('CPU_both_hosts_passed') is True and q.get('actual_build_manually_reviewed') is True,
            'Numerical source/CPU/build review required')
    require(q.get('jobs') == jobs() and q.get('aggregate_budget') == {'soft_seconds': 1000, 'wall_seconds': 1200, 'cleanup_seconds': 200},
            'Frozen finite sequence/budget differs')
    first, second = b.observations(); observed = b.inventory(first, second)
    prep = N / 'build-v3/prepare-FIRST/receipt.json'
    require(q['files'].get(str(prep)) == sha(b.regular(prep)), 'Actual prepare absent')
    for name, row in json.loads(prep.read_text())['discovered_headers'].items(): observed[name] = row
    b.verify_files(q['files'], observed)
    cpu_proofs(b, q)
    built = N / 'build-v3/build-FIRST/receipt.json'
    require(q['files'].get(str(built)) == sha(b.regular(built)), 'Actual build receipt absent')
    result = json.loads(built.read_text())
    require(result['status'] == 'COMPILED_STOP_FOR_SEPARATE_NUMERICAL_QUALIFICATION' and result['passed'] is True
            and len(result['children']) == 7 and all(c['returncode'] == 0 and c['error'] is None and c['cleanup'] == [] for c in result['children']),
            'Actual complete seven-child build required')
    require(all(result.get(k) is False for k in ('native_execution', 'fixture_execution', 'GPU_execution', 'production_changed')),
            'Build-only execution boundary differs')
    for key in ('outputs', 'actual_inputs'):
        require(all(q['files'].get(k) == v for k, v in result[key].items()), 'Actual build closure omitted')
    require(result['outputs'].get(str(FIXTURE)) == q['fixture_sha256'], 'Fixture not actual build output')
    supervisor = N / 'build-v3/compile-supervision-FIRST/result.json'
    require(q['files'].get(str(supervisor)) == sha(b.regular(supervisor)), 'Compile supervision absent')
    s = json.loads(supervisor.read_text())
    require(s['status'] == 'PASS' and s['error'] is None and s['owned_groups_absence']['passed'] is True
            and s['own_claim_released'] is True and s['GPU_lease_mutated'] is False, 'Compile ownership closure differs')
    for name in ('COMPILE_ROOT_RESULT_REVIEW.json', 'COMPILE_RESULT_ASTRA_REVIEW.json'):
        path = N / 'build-v3' / name
        require(q['files'].get(str(path)) == sha(b.regular(path)), 'Actual independent build review missing')
        review = json.loads(path.read_text())
        require(review['outputs'] == result['outputs'], 'Reviewed build outputs differ')
        for relative, digest in review['raw_sha256'].items():
            raw = N / 'build-v3' / relative
            require(not Path(relative).is_absolute() and '..' not in Path(relative).parts and
                    q['files'].get(str(raw)) == digest and sha(b.regular(raw)) == digest,
                    'Reviewed actual build raw closure absent')
    source = N / 'numerical-v2/iq2xs_exact.cpp'
    require(q['files'].get(str(source)) == FIXTURE_SOURCE_SHA and sha(source) == FIXTURE_SOURCE_SHA, 'Frozen fixture source differs')
    fixture_identity(b, q)
    require(sha(HERE / 'qualification.json') == pin, 'Qualification changed')
    parser = exact_module('iq2xs_numerical_v3_parser', HERE / 'output_parser.py', q['source_sha256']['output_parser.py'])
    return observed, parser


def execute(b, parser, q, guard, owned, started, check_files):
    output = HERE / 'numerical-FIRST'; b.fresh(output); guard(); child_budget(started, time.monotonic()); output.mkdir()
    rows = []
    try:
        for job in jobs():
            guard(); child_budget(started, time.monotonic())
            rows.append(run_one(b, parser, q, job, output, guard, owned, started, check_files))
        require(len(rows) == 46 and sum(row['cases'] for row in rows) == 6336, 'Whole finite inventory incomplete')
        guard(); require(time.monotonic() < started + SOFT, 'Sequence soft deadline')
    except BaseException as exc:
        try: b.emit(output / 'partial.json', {'status': 'HOLD', 'completed': rows,
                    'unrun': jobs()[len(rows):], 'error': repr(exc), 'retry_authorized': False})
        except BaseException as note: exc.add_note('Partial receipt: ' + repr(note))
        raise
    value = {'status': 'ALL_46_FINITE_NUMERICAL_CHILDREN_COMPLETE_PENDING_SUPERVISION', 'passed': True,
             'rows': rows, 'case_rows': 6336, 'quality_or_speed_claim': False, 'model_or_GPU_execution': False}
    b.emit(output / 'receipt.json', value)
    return value


def main(pin):
    started = time.monotonic()
    require(sys.platform == 'linux' and HERE == EXPECTED and sys.dont_write_bytecode, 'Exact physical -B scope')
    b, q = bootstrap(pin)
    c = b.load_exact('iq2s_build', D / 'iq2s-persistent-v1/iq2s_build.py', b.SUPPORT_SHA)
    _, runtime, _, host, binding = c.support()
    require(binding == q['selected_binding'], 'Action-time selected owner differs')
    c.guard(runtime, host, binding); require(shutil.disk_usage('/').free >= 136 * 2**30, 'Root136 unavailable')
    first_gpu = b.observe_gpu_lease(host, binding)
    observed, parser = verify_q(b, q, pin); cas = b.load_cas()
    capability = observed_cpu_capability(q)
    record = None; latest_gpu = first_gpu
    def guard(claimed=False, lease=None):
        nonlocal latest_gpu
        if lease is not None: lease.check()
        require(time.monotonic() < started + SOFT, 'Whole sequence soft deadline')
        state = c.guard(runtime, host, binding, record if claimed else None)
        require(shutil.disk_usage('/').free >= 136 * 2**30, 'Root136 unavailable')
        require(sha(HERE / 'qualification.json') == pin, 'Qualification changed')
        latest_gpu = b.observe_gpu_lease(host, binding, first_gpu['identity'])
        require(time.monotonic() < started + SOFT, 'Guard exhausted soft deadline')
        return state
    guard()
    with b.CPULease(E / 'cpu-build.lock') as lease:
        state = guard(lease=lease); require(not state.get('active_cpu_build'), 'Existing claim; no automatic adoption')
        folder = HERE / 'numerical-supervision-FIRST'; b.fresh(folder); folder.mkdir()
        owned = b.OwnedChildren(folder / 'owned-children.jsonl')
        record = {'controller_pid': os.getpid(), 'controller_start_ticks': b.process_ticks(os.getpid()),
                  'nonce': uuid.uuid4().hex, 'mode': 'iq2xs-numerical-v3', 'qualification_sha256': pin,
                  'start_binding': binding, 'cpu_lease': dict(lease.identity)}
        b.emit(folder / 'attempt.json', {'record': record, 'GPU_lease': latest_gpu,
               'CPU_capability': capability,
               'global_state_CAS_atomic': False, 'single_coordinator_maintenance_freeze': True})
        primary = None; result = None; released = False; absence = None; claimed = False
        try:
            state = guard(lease=lease); raw = (E / 'STATE.json').read_bytes()
            require(json.loads(raw) == state and not state.get('active_cpu_build'), 'Coordination changed before claim')
            cas.cas_state(E / 'STATE.json', raw, dict(state, active_cpu_build=record)); claimed = True
            guard(True, lease)
            result = execute(b, parser, q, lambda: guard(True, lease), owned, started,
                             lambda: b.verify_files(q['files'], observed))
        except BaseException as exc:
            primary = exc
        finally:
            try:
                lease.check(); absence = owned.absence()
                require(absence['passed'], 'Owned children absence unproved; retain claim')
                current = (E / 'STATE.json').read_bytes(); value = json.loads(current); claim = value.get('active_cpu_build')
                if claim == record:
                    cas.cas_state(E / 'STATE.json', current, dict(value, active_cpu_build=False))
                    require(json.loads((E / 'STATE.json').read_text()).get('active_cpu_build') is False, 'Claim release failed')
                    released = True
                elif claim: raise ValueError('Own claim changed; preserve foreign state')
                else: require(not claimed and result is None and primary is not None, 'Own claim vanished')
            except BaseException as exc:
                if primary is None: primary = exc
                else: primary.add_note('Claim release: ' + repr(exc))
            try:
                latest_gpu = b.observe_gpu_lease(host, binding, first_gpu['identity'])
                require(time.monotonic() <= started + WALL, 'Whole sequence wall exhausted')
            except BaseException as exc:
                if primary is None: primary = exc
                else: primary.add_note('Final owner/wall: ' + repr(exc))
            deferred = primary is not None and str(primary) == 'DEFERRED_BUSY_UNTOUCHED_OR_CLEANUP_OWNED_COMPILER' and not getattr(primary, '__notes__', None) and released
            try:
                b.emit(folder / 'result.json', {'status': 'PASS' if primary is None else 'DEFERRED_BUSY_PARTIALS_RETAINED' if deferred else 'HOLD',
                    'record': record, 'error': None if primary is None else repr(primary),
                    'error_notes': [] if primary is None else list(getattr(primary, '__notes__', [])),
                    'owned_groups_absence': absence, 'own_claim_released': released,
                    'GPU_lease': latest_gpu, 'retry_authorized': False,
                    'elapsed_seconds': time.monotonic() - started})
            except BaseException as exc:
                if primary is None: primary = exc
                else: primary.add_note('Supervision receipt: ' + repr(exc))
        if primary is not None:
            if deferred and not getattr(primary, '__notes__', None): raise b.BuildDeferred('DEFERRED_BUSY_PARTIALS_RETAINED') from primary
            raise primary
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--qualification-sha256', required=True)
    args = parser.parse_args()
    try: print(json.dumps(main(args.qualification_sha256)))
    except Exception as exc:
        if str(exc) == 'DEFERRED_BUSY_PARTIALS_RETAINED':
            print(json.dumps({'status': str(exc), 'retry_authorized': False})); sys.exit(75)
        raise
