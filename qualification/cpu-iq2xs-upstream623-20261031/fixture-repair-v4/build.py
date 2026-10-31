"""Two-child fixture-only repair build; no numerical or model execution."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
N = HERE.parent
D = N.parent
R = Path('/home/alex/strata-deepseek-test-20261024')
E = R / 'reliability-optimization-20261025'
EXPECTED = E / 'decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4'
BUILD = N / 'build-v3/build.py'
BUILD_SHA = 'a765195c6fc6fe65e2d780bce3d166d28f181de722d68d725f7bceb568dd7380'
OLD_FIXTURE_SHA = '33ede583a7c299a9bac83520050a6ea48233ae596fe6bb0a0f8195dbb7dfd6e7'
OLD_Q_SHA = '067bdfbd0caad55ac0715215e110734cb4659f7b4f448e61e791e5ae7e35bf8d'
BEFORE = b'std::vector<uint8_t> quantized_via_selected(ab);'
AFTER = b'std::vector<uint8_t> quantized_via_selected(ab, 0x3c);'
SOFT = 400
WALL = 600
OUTPUT_PINS = {
 'maya-ds4-candidate': 'cab346ccefedad1d2b80384db215325a445f474729812ea288a829d843007da4',
 'libstrata_kernels_cpu.a': '514b8346a1df0663f2868c1de6b9bc1adbdd82a1c5422abc33cc6875dad67448',
 'iq_avx2.cpp.o': '82a3228e873a435efa60e17b0ea9f3747914f2256e751700c921696fa12897a2',
 'native_expert.cpp.o': '52013e05368020780d3373fa1818b8e8ba3976018d9e8bd1db814a99e9ef1fb5'}
FAILURE_PINS = {
 'FIRST_FAULT_ASTRA_REVIEW.json': '9b680d35d25ab8459d23918cc74bc2fe57dedbf8ae51b0ee5566983bc35258ba',
 'PROSPECTIVE_FIXTURE_REPAIR_ARCHITECTURE_ASTRA.json': '7914ac948088fcf6667db97c9782e9427d288a94b28186e0d8ebd03eb3d14a81',
 'FIRST_FAULT_ROOT_REVIEW.json': '1fe3b4858745259cf45819ca37bc692089f517416c841a9b1d6633a44ddce2ff'}



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
    return exact_module('iq2xs_fixture_repair_build_v3', BUILD, BUILD_SHA)


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
    driver = exact_module('iq2xs_fixture_repair_v4_cpu_driver', path, pin)
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


def fixture_contract(old, new):
    require(hashlib.sha256(old).hexdigest() == OLD_FIXTURE_SHA and old.count(BEFORE) == 1,
            'Exact original fixture required')
    require(new == old.replace(BEFORE, AFTER), 'Only the one initializer line may change')


def commands(b, first, folder):
    require(folder == HERE / 'build-FIRST', 'Only fresh fixture output namespace allowed')
    obj = folder / 'iq2xs_exact.cpp.o'
    compile_argv = b.compiler(first) + ['-I' + str(b.S / 'src/ds4'), '-MD', '-MT', 'iq2xs_exact.cpp.o',
        '-MF', str(obj) + '.d', '-o', str(obj), '-c', str(HERE / 'iq2xs_exact.cpp')]
    link_argv = ['/usr/bin/c++', '-O3', '-DNDEBUG',
        '-Wl,--dependency-file=' + str(folder / 'iq2xs_exact.link.d'), str(obj),
        str(b.B / 'CMakeFiles/maya-ds4.dir/src/ds4/ds4_iq_cpu.cpp.o'),
        str(N / 'build-v3/build-FIRST/libstrata_kernels_cpu.a'), str(b.B / 'libstrata_core.a'),
        str(b.B / 'ggml/src/libggml-cpu.a'), str(b.B / 'ggml/src/libggml-base.a'),
        '-lm', '-lpthread', '-ldl', '-o', str(folder / 'iq2xs_exact')]
    return [('fixture-compile', compile_argv, True, obj, Path(str(obj) + '.d')),
            ('fixture-link', link_argv, False, folder / 'iq2xs_exact', folder / 'iq2xs_exact.link.d')]


def command_contract(b, first, folder, job):
    require(type(job) is tuple and job in commands(b, first, folder), 'Only exact two fixture commands allowed')
    name, argv, compiled, _, _ = job
    expected = ('compile', 120, 4 * 2**30, 300) if name == 'fixture-compile' else ('link', 30, 4 * 2**30, 90)
    require(type(compiled) is bool and b.resource_class(argv, compiled) == expected, 'Fixture resource class differs')
    return expected


def child_admission(started, now, wall):
    require(type(wall) is int and wall in (300, 90), 'Exact compiler or linker wall required')
    # Reuse unchanged run_child. Reserve its full wall inside the remaining soft
    # budget; do not begin a child that would require extending either budget.
    require(now >= started and now + wall + 1 <= started + SOFT,
            'Whole-build soft budget cannot reserve full child wall')


def prior_contract(b, q):
    prior = N / 'numerical-v3/qualification.json'
    require(q['files'].get(str(prior)) == OLD_Q_SHA and sha(b.regular(prior)) == OLD_Q_SHA,
            'Original failed qualification custody required')
    old = json.loads(prior.read_text())
    require(all(q['files'].get(k) == v for k, v in old['files'].items()), 'Original qualification input omitted')
    for name, pin in OUTPUT_PINS.items():
        path = N / 'build-v3/build-FIRST' / name
        require(q['files'].get(str(path)) == pin and sha(b.regular(path)) == pin, 'Unchanged candidate output differs')
    for name, pin in FAILURE_PINS.items():
        path = N / 'numerical-v3' / name
        require(q['files'].get(str(path)) == pin and sha(b.regular(path)) == pin, 'Failure or diagnosis custody missing')
    review = json.loads((N / 'numerical-v3/FIRST_FAULT_ASTRA_REVIEW.json').read_text())
    for rel, pin in review['raw_sha256'].items():
        require(not Path(rel).is_absolute() and '..' not in Path(rel).parts, 'Foreign failure evidence path')
        path = N / 'numerical-v3' / rel
        require(q['files'].get(str(path)) == pin and sha(b.regular(path)) == pin, 'Original failed raw omitted')


def verify_q(b, q, pin):
    require(q.get('mode') == 'fixture-build' and q.get('manual_source_reviewed') is True and
            q.get('CPU_both_hosts_passed') is True and q.get('actual_build_manually_reviewed') is True,
            'Fixture source, CPU and previous actual build review required')
    require(q.get('aggregate_budget') == {'soft_seconds': 400, 'wall_seconds': 600, 'cleanup_seconds': 200}
            and q.get('children') == ['fixture-compile', 'fixture-link'], 'Exact two-child budget required')
    first, second = b.observations(); observed = b.inventory(first, second)
    prep = N / 'build-v3/prepare-FIRST/receipt.json'
    require(q['files'].get(str(prep)) == sha(b.regular(prep)), 'Actual prepared header custody required')
    for name, row in json.loads(prep.read_text())['discovered_headers'].items():
        require(name not in observed or observed[name]['sha256'] == row['sha256'], 'Header conflict')
        observed[name] = row
    b.verify_files(q['files'], observed)
    prior_contract(b, q); cpu_proofs(b, q)
    old = N / 'numerical-v2/iq2xs_exact.cpp'; new = HERE / 'iq2xs_exact.cpp'
    require(q['files'].get(str(old)) == OLD_FIXTURE_SHA and
            q['files'].get(str(new)) == q['source_sha256'].get('iq2xs_exact.cpp') == sha(b.regular(new)),
            'Fixture source membership missing')
    fixture_contract(b.regular(old).read_bytes(), new.read_bytes())
    built = N / 'build-v3/build-FIRST/receipt.json'
    require(q['files'].get(str(built)) == sha(b.regular(built)), 'Actual build receipt absent')
    result = json.loads(built.read_text())
    require(result['status'] == 'COMPILED_STOP_FOR_SEPARATE_NUMERICAL_QUALIFICATION' and result['passed'] is True
            and len(result['children']) == 7 and all(c['returncode'] == 0 and c['error'] is None and c['cleanup'] == [] for c in result['children']),
            'Actual original seven-child build required')
    require(all(result.get(k) is False for k in ('native_execution', 'fixture_execution', 'GPU_execution', 'production_changed')),
            'Original build scope changed')
    for key in ('outputs', 'actual_inputs'):
        require(all(q['files'].get(k) == v for k, v in result[key].items()), 'Actual build input or output omitted')
    supervisor = N / 'build-v3/compile-supervision-FIRST/result.json'
    require(q['files'].get(str(supervisor)) == sha(b.regular(supervisor)), 'Compile supervision absent')
    s = json.loads(supervisor.read_text())
    require(s['status'] == 'PASS' and s['error'] is None and s['owned_groups_absence']['passed'] is True
            and s['own_claim_released'] is True and s['GPU_lease_mutated'] is False, 'Compile ownership closure differs')
    for name in ('COMPILE_ROOT_RESULT_REVIEW.json', 'COMPILE_RESULT_ASTRA_REVIEW.json'):
        path = N / 'build-v3' / name
        require(q['files'].get(str(path)) == sha(b.regular(path)), 'Actual build review absent')
        review = json.loads(path.read_text()); require(review['outputs'] == result['outputs'], 'Reviewed outputs differ')
        for rel, value in review['raw_sha256'].items():
            require(not Path(rel).is_absolute() and '..' not in Path(rel).parts, 'Foreign build evidence path')
            raw = N / 'build-v3' / rel
            require(q['files'].get(str(raw)) == value and sha(b.regular(raw)) == value, 'Reviewed build raw missing')
    require(sha(HERE / 'qualification.json') == pin, 'Qualification changed')
    return observed


def execute(b, q, guard, owned, started, check_files):
    folder = HERE / 'build-FIRST'; b.fresh(folder); guard()
    first, _ = b.observations(); planned = commands(b, first, folder)
    child_admission(started, time.monotonic(), 300)
    outputs = {}; actual = {}; children = []; attempted = []
    def check():
        guard(); check_files()
        for name, value in outputs.items(): require(sha(b.regular(name)) == value, 'New fixture artifact changed')
        guard(); require(time.monotonic() < started + SOFT, 'Whole build soft deadline')
    check(); folder.mkdir()
    try:
        for job in planned:
            name, argv, compiled, output, dep = job
            role, cpu, memory, wall = command_contract(b, first, folder, job)
            check(); child_admission(started, time.monotonic(), wall)
            attempted.append(name)
            row = b.run_child(argv, name, folder, guard, compiler_child=compiled, owned=owned)
            require(row['argv'] == argv and row['status'] == 'PASS' and row['returncode'] == 0 and
                    row['error'] is None and row['cleanup'] == [] and type(row['pid']) is int and row['pid'] > 1 and
                    (row['role'], row['CPU_s'], row['AS_bytes'], row['wall_s']) == (role, cpu, memory, wall)
                    and row['elapsed_seconds'] <= wall, 'Actual compiler or linker receipt differs')
            check(); outputs[str(output)] = sha(b.regular(output))
            found = b.actual_dependencies(dep, folder, dict(q['files'], **outputs))
            actual.update(found); b.emit(folder / (name + '-inputs.json'), found)
            children.append(row); check()
        require(len(children) == 2 and len(outputs) == 2, 'Both fixture build children required')
        value = {'status': 'FIXTURE_REBUILT_STOP_FOR_NEW_NUMERICAL_QUALIFICATION', 'passed': True,
                 'outputs': outputs, 'actual_inputs': actual, 'children': children,
                 'candidate_rebuilt': False, 'native_execution': False, 'fixture_execution': False,
                 'GPU_execution': False, 'production_changed': False}
        b.emit(folder / 'receipt.json', value)
        return value
    except BaseException as exc:
        try:
            b.emit(folder / 'partial.json', {'status': 'HOLD', 'completed': [j['argv'] for j in children],
                   'attempted': attempted, 'not_admitted': [j[0] for j in planned if j[0] not in attempted],
                   'error': repr(exc), 'retry_authorized': False})
        except BaseException as note: exc.add_note('Partial receipt: ' + repr(note))
        raise


def main(pin):
    started = time.monotonic()
    require(sys.platform == 'linux' and HERE == EXPECTED and sys.dont_write_bytecode, 'Exact physical -B scope')
    b, q = bootstrap(pin)
    c = b.load_exact('iq2s_build', D / 'iq2s-persistent-v1/iq2s_build.py', b.SUPPORT_SHA)
    _, runtime, _, host, binding = c.support()
    require(binding == q['selected_binding'], 'Action-time selected owner differs')
    c.guard(runtime, host, binding); require(shutil.disk_usage('/').free >= 136 * 2**30, 'Root136 unavailable')
    first_gpu = b.observe_gpu_lease(host, binding)
    observed = verify_q(b, q, pin); cas = b.load_cas()
    record = None; latest_gpu = first_gpu
    def guard(claimed=False, lease=None):
        nonlocal latest_gpu
        if lease is not None: lease.check()
        require(time.monotonic() < started + SOFT, 'Whole build soft deadline')
        state = c.guard(runtime, host, binding, record if claimed else None)
        require(shutil.disk_usage('/').free >= 136 * 2**30, 'Root136 unavailable')
        require(sha(HERE / 'qualification.json') == pin, 'Qualification changed')
        latest_gpu = b.observe_gpu_lease(host, binding, first_gpu['identity'])
        require(time.monotonic() < started + SOFT, 'Guard exhausted soft deadline')
        return state
    guard()
    with b.CPULease(E / 'cpu-build.lock') as lease:
        state = guard(lease=lease); require(not state.get('active_cpu_build'), 'Existing claim; no automatic adoption')
        folder = HERE / 'build-supervision-FIRST'; b.fresh(folder); folder.mkdir()
        owned = b.OwnedChildren(folder / 'owned-children.jsonl')
        record = {'controller_pid': os.getpid(), 'controller_start_ticks': b.process_ticks(os.getpid()),
                  'nonce': uuid.uuid4().hex, 'mode': 'iq2xs-fixture-repair-v4', 'qualification_sha256': pin,
                  'start_binding': binding, 'cpu_lease': dict(lease.identity)}
        b.emit(folder / 'attempt.json', {'record': record, 'GPU_lease': latest_gpu,
               'global_state_CAS_atomic': False, 'single_coordinator_maintenance_freeze': True})
        primary = None; result = None; released = False; absence = None; claimed = False
        try:
            state = guard(lease=lease); raw = (E / 'STATE.json').read_bytes()
            require(json.loads(raw) == state and not state.get('active_cpu_build'), 'Coordination changed before claim')
            cas.cas_state(E / 'STATE.json', raw, dict(state, active_cpu_build=record)); claimed = True
            guard(True, lease)
            result = execute(b, q, lambda: guard(True, lease), owned, started,
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
                require(time.monotonic() <= started + WALL, 'Whole build wall exhausted')
            except BaseException as exc:
                if primary is None: primary = exc
                else: primary.add_note('Final owner/wall: ' + repr(exc))
            deferred = primary is not None and str(primary) in ('DEFERRED_BUSY_UNTOUCHED_OR_CLEANUP_OWNED_COMPILER', 'DEFERRED_BUSY_PARTIALS_RETAINED') and not getattr(primary, '__notes__', None) and released
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
