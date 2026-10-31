"""Fresh full Maya build, using existing CPU lease/cleanup and selected-owner guards.

Configure and compile are separate admitted stages. No model or GPU execution.
All project CPU archives are rebuilt from current source; production is read-only.
CPU-only compilation does not read model weights. Shared coordination can defer
an acquisition while this build owns its lease; never restart it during the build.
Model/GPU timing requires acquisition worker exit, not unrelated model completion.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid
import urllib.request

HERE = Path(__file__).resolve().parent
R = Path('/home/alex/strata-deepseek-test-20261024')
E = R / 'reliability-optimization-20261025'
EXPECTED = E / 'decode-optimization-20261028/maya145-mayas-v1'
UPSTREAM = '6ecbd3cbc5330b57f70cd5cf8a5c42eb8ef950cc'
IMPORTS = {
    'build_owner': ('cpu-iq2xs-upstream623-v1/build-v3/build.py', 'a765195c6fc6fe65e2d780bce3d166d28f181de722d68d725f7bceb568dd7380'),
    'build_support': ('iq2s-persistent-v1/iq2s_build.py', 'e8dcd79bd3a80cba931885149438f107d6d840693e508f738fd616fd6885f9ff'),
    'build_early': ('cpu-iq2xs-upstream623-v1/model-v1/cpu_model_audit_runner.py', '5818f60d4267a246d8deebb7c98d4e21a31e5393ec38d68a9003d3256ab2171a'),
    'build_healthy_work': ('cpu-iq2xs-upstream623-v1/model-v1/cpu_guard.py', '4f40c04a69701cf86e478bdf4f13a021de05f18fae1b943fcd7b88aee19295fd'),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(65536), b''):
            h.update(part)
    return h.hexdigest()


def emit(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def exact(name):
    relative, pin = IMPORTS[name]
    path = HERE.parent / relative
    require(sha(path) == pin, 'Shared infrastructure changed: ' + name)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plan(stage, home=EXPECTED):
    require(stage in ('configure', 'compile'), 'Two fixed build stages only')
    source, build = home / 'source-r2', home / 'native-build-r2-FIRST'
    if stage == 'configure':
        return ['/usr/bin/cmake', '-S', str(source), '-B', str(build), '-G', 'Unix Makefiles',
                '-DCMAKE_BUILD_TYPE=Release', '-DSTRATA_ENABLE_CUDA=ON', '-DSTRATA_ENABLE_HIP=OFF',
                '-DSTRATA_BUILD_TESTS=OFF', '-DCMAKE_CUDA_ARCHITECTURES=80',
                '-DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc', '-DCMAKE_CXX_COMPILER=/usr/bin/c++',
                '-DCMAKE_C_COMPILER=/usr/bin/cc', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                '-DSTRATA_GGML_DIR=' + str(R / 'llama.cpp'), '-DFETCHCONTENT_FULLY_DISCONNECTED=ON',
                '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF', '-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF']
    return ['/usr/bin/cmake', '--build', str(build), '--target', 'maya-ds4', '--', '-j1']


def verify_files(files):
    require(type(files) is dict and bool(files), 'Nonempty exact input map required')
    for name, pin in files.items():
        path = Path(name)
        require(path.is_absolute() and '..' not in path.parts and path.resolve() == path
                and path.is_file() and not path.is_symlink() and sha(path) == pin,
                'Pinned input changed: ' + name)


def literal_build_sources(text):
    # Conservative literal-reference preflight, not a CMake interpreter. Targets
    # can be declared even with STRATA_BUILD_TESTS=OFF. Variables are left to CMake.
    text = re.sub(r'#[^\n]*', '', text)
    return sorted(set(re.findall(r'(?<![A-Za-z0-9_])((?:src|tests|bench|tools|include|cmake)/'
        r'[A-Za-z0-9_./+\-]+\.(?:cpp|cu|c|hpp|h|cmake))(?=[\s)";])', text)))


def verify_project_sources(root):
    text = (root / 'CMakeLists.txt').read_text(encoding='utf-8-sig')
    names = literal_build_sources(text)
    require(names, 'Literal CMake source inventory missing')
    # These four bench sources are absent from the public tree. Their targets
    # are explicitly behind STRATA_BUILD_TESTS AND EXISTS. The fixed plan sets
    # tests OFF. Require the exact source-reviewed EXISTS guard before exemption.
    optional = {n for n in ('bench/micro/graph_registry_test.cu', 'bench/micro/hit_cpu_order_parity.cu',
                           'bench/micro/native_mmvq_multi.cpp', 'bench/micro/pinned_capture.cu')
                if 'EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/' + n + '"' in text}
    missing = [n for n in names if n not in optional and ('..' in Path(n).parts or not (root / n).is_file()
               or (root / n).is_symlink())]
    require(not missing, 'Source bundle incomplete before configure: ' + ', '.join(missing))
    return names


def qualified(stage, pin):
    path = HERE / (stage + '-r4-qualification.json')
    require(sha(path) == pin, 'Qualification changed')
    q = json.loads(path.read_text())
    require(q.get('stage') == stage and q.get('upstream') == UPSTREAM
            and q.get('root_manual_source_tests_read') is True and q.get('CPU_both_hosts_passed') is True,
            'Current source/manual/CPU qualification required')
    require(q.get('selected_binding') and q.get('command') == plan(stage), 'Exact binding/command required')
    verify_files(q['files'])
    for alias, resolved in q['tool_aliases'].items():
        require(str(Path(alias).resolve()) == resolved and resolved in q['files'], 'Tool alias changed')
    for platform in ('darwin', 'linux'):
        proof = q['CPU'][platform]
        require(proof['passed'] is True and proof['source_sha256'] == q['source_sha256']
                and proof['test_ids'] == q['test_ids'] and proof['test_ids'], 'Matching both-host CPU source/IDs')
    require(all(q['files'].get(str(HERE / n)) == p for n, p in q['source_sha256'].items()), 'Controller map omitted')
    return q


def idle_contract(health, telemetry):
    require(health.get('status') == 'ok' and health.get('loaded') is True and health.get('busy') is False
            and health.get('model') == 'deepseek-v4.1-flash-iq2-xs'
            and type(health.get('max_context')) is int and health['max_context'] == 1048576,
            'Exact selected idle service required')
    switcher, work = health['switcher'], telemetry['work']
    require(switcher.get('active_model') == switcher.get('default_model') == 'deepseek'
            and 'fault' in switcher and switcher['fault'] is None, 'Default DeepSeek without fault required')
    for obj, keys in ((switcher, ('inflight', 'waiting')), (work, ('active', 'queued', 'admission_reserved'))):
        require(all(type(obj.get(k)) is int and obj[k] == 0 for k in keys), 'Hosted work: untouched')


def strict_idle():
    rows = []
    for endpoint in ('/health', '/v1/telemetry'):
        with urllib.request.urlopen('http://127.0.0.1:8012' + endpoint, timeout=5) as response:
            raw = response.read(1024 * 1024 + 1)
            require(len(raw) <= 1024 * 1024, 'Oversized lightweight observation')
            rows.append(json.loads(raw))
    idle_contract(*rows)


def coordination_guard(support, healthy_work, runtime, host, binding, reservation, *, cpu_started):
    if cpu_started:
        return healthy_work.guard(runtime, host, binding, E / 'STATE.json', reservation)
    state = support.guard(runtime, host, binding, reservation)
    strict_idle()
    return state


def cpu_headroom(text):
    rows = [line.split() for line in text.splitlines() if line.startswith('MemAvailable:')]
    require(len(rows) == 1 and len(rows[0]) == 3 and rows[0][1].isdecimal() and rows[0][2] == 'kB',
            'Actual available memory observation required')
    available = int(rows[0][1]) * 1024
    require(available >= 20 * 2**30, 'CPU compiler group physical memory headroom unavailable')
    return available


def download_complete(value, manifest, pid_present):
    require(value.get('status') == 'ALL_SIX_UNSLOTH_ASSETS_VERIFIED_NO_MODEL_RUN'
            and type(value.get('returncode')) is int and value['returncode'] == 0
            and type(value.get('pid')) is int and value['pid'] > 1 and not pid_present(value['pid'])
            and type(value.get('model_or_service_actions')) is int and value['model_or_service_actions'] == 0,
            'Completed acquisition/worker absence required')
    require(len(value.get('files', [])) == len(manifest['files']) == 6, 'Six completed assets required')
    for row, expected in zip(value['files'], manifest['files']):
        require(row.get('path') == expected['path'] and row.get('sha256') == expected['sha256']
                and type(row.get('bytes')) is int and row['bytes'] == expected['size']
                and row.get('status') in ('VERIFIED_EXISTING', 'DOWNLOADED_VERIFIED'), 'Unverified download row')


def acquisition(q):
    folder = HERE.parent / 'unsloth-v31-iq2xxs-download-v1'
    path = Path(q['download_receipt'])
    require(q['files'].get(str(path)) == sha(path), 'Acquisition receipt omitted')
    manifest_path = folder / 'ASSET_MANIFEST.json'
    require(q['files'].get(str(manifest_path)) == '4fb4c0ff9c0b55f46afa15c2cbc84ee09372c85944efafb63e36a5ca6e73c73c'
            and sha(manifest_path) == q['files'][str(manifest_path)], 'Acquisition manifest changed')
    value = json.loads(path.read_text())
    require(value.get('manifest_sha256') == q['files'][str(manifest_path)]
            and value.get('revision') == '8a6ec9cf118e785a362ea94ee123c61c70553be6', 'Acquisition revision changed')
    download_complete(value, json.loads(manifest_path.read_text()), lambda pid: (Path('/proc') / str(pid)).exists())


def configure_closed(q):
    folder = HERE / 'configure-r4-FIRST'
    rows = {}
    for name in ('result.json', 'supervision.json', 'child.json'):
        path = folder / name
        require(q['files'].get(str(path)) == sha(path), 'Complete configure closure must be pinned')
        rows[name] = json.loads(path.read_text())
    result, supervision, child = (rows[n] for n in ('result.json', 'supervision.json', 'child.json'))
    require(result.get('passed') is True and result.get('stage') == 'configure'
            and result.get('child') == child and result.get('model_executed') is False,
            'Accepted actual configure result required')
    require(supervision.get('passed') is True and supervision.get('owned_claim_released') is True
            and supervision.get('error') is None, 'Configure owned closure failed')
    require(child.get('argv') == plan('configure') and type(child.get('returncode')) is int
            and child['returncode'] == 0 and child.get('error') is None and child.get('cleanup') == [],
            'Actual configure child failed')


def run_owned(argv, folder, b, owned, check, *, spawned=lambda: None):
    # CMake drives serial tools. CPU120/AS4GiB apply separately to every inherited process.
    # Aggregate wall900 includes cleanup; all compiler tools remain in this owned group.
    started = time.monotonic()
    process = None
    row = {'argv': argv, 'pid': None, 'returncode': None, 'error': None, 'cleanup': []}
    try:
        temporary = folder / 'tmp'
        temporary.mkdir()
        env = dict(b.ENV, TMPDIR=str(temporary))  # fixed allowlist: no inherited compiler/CMake/loader injection
        with (folder / 'stdout.txt').open('xb') as out, (folder / 'stderr.txt').open('xb') as err:
            check()  # immediately before spawn, after all qualification/tool scans
            owned.starting('cmake')
            process = subprocess.Popen(argv, cwd=HERE, env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, start_new_session=True,
                preexec_fn=lambda: b.child_limits(120, 4 * 2**30, folder / 'observed.json', env))
            row['pid'] = process.pid
            owned.registered(process, 'cmake')
            spawned()
            while process.poll() is None:
                check()
                require(time.monotonic() - started < 870, 'Aggregate build soft deadline')
                require(sum(p.stat().st_size for p in (folder / 'stdout.txt', folder / 'stderr.txt')) < 4 * 2**30,
                        'Build log budget')
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            row['returncode'] = process.returncode
            require(process.returncode == 0, 'Native build failed; preserve first attempt')
            observed = json.loads((folder / 'observed.json').read_text())
            require(observed == {'pid': process.pid, 'ppid': os.getpid(), 'pgid': process.pid,
                    'cpu': [120, 120], 'as': [4 * 2**30, 4 * 2**30], 'nice': 15,
                    'environment': dict(b.ENV, TMPDIR=str(temporary))}, 'Observed CMake bounds changed')
            check()
    except BaseException as exc:
        row['error'] = repr(exc)
    finally:
        if process is not None:
            try:
                b.cleanup(process, started + 900)
            except BaseException as exc:
                row['cleanup'].append(repr(exc))
                owned.cleanup_failed('cmake', exc)
            row['returncode'] = process.poll()
        row['elapsed_seconds'] = time.monotonic() - started
        emit(folder / 'child.json', row)
    require(row['error'] is None and row['returncode'] == 0 and not row['cleanup'], 'Build/owned cleanup HOLD')
    return row


def main(stage, pin):
    require(sys.platform == 'linux' and HERE == EXPECTED and sys.dont_write_bytecode and sys.flags.isolated,
            'Exact isolated physical Ubuntu entrypoint required')
    early = exact('build_early')
    binding = early.early_guard()  # phase/identity/resource guard; strict idle is checked separately below
    strict_idle()
    q = qualified(stage, pin)
    require(binding == q['selected_binding'], 'Current selected owner needs new admission')
    b, support = exact('build_owner'), exact('build_support')
    healthy_work = exact('build_healthy_work')
    _, runtime, _, host, actual = support.support()
    require(actual == binding, 'Actual owner changed')
    gpu = b.observe_gpu_lease(host, binding)
    cas = b.load_cas()
    record = {'mode': 'maya145-full-r4-' + stage, 'controller_pid': os.getpid(),
              'controller_start_ticks': b.process_ticks(os.getpid()), 'nonce': uuid.uuid4().hex,
              'start_binding': binding, 'qualification_sha256': pin}
    verify_project_sources(HERE / 'source-r2')
    folder = HERE / (stage + '-r4-FIRST')
    require(not folder.exists() and not folder.is_symlink(), 'Fresh stage only; no replay')
    if stage == 'configure':
        require(not (HERE / 'native-build-r2-FIRST').exists(), 'Fresh build directory required')
    else:
        configure_closed(q)
    with b.CPULease(E / 'cpu-build.lock') as lease:
        claimed = False
        primary = None
        result = None
        cpu_started = [False]
        def spawned():
            cpu_started[0] = True
        def check():
            lease.check()
            # Admit idle. Once this CPU-only child owns its group, ordinary
            # inference may resume without killing a correct compiler. Private
            # phases, owner changes, faults and resource loss still stop it.
            state = coordination_guard(support, healthy_work, runtime, host, binding,
                                       record if claimed else None, cpu_started=cpu_started[0])
            cpu_headroom(Path('/proc/meminfo').read_text())
            early.early_guard(record if claimed else None)
            b.observe_gpu_lease(host, binding, gpu['identity'])
            require(sha(HERE / (stage + '-r4-qualification.json')) == pin, 'Qualification changed during build')
            return state
        state = check()
        folder.mkdir()
        owned = b.OwnedChildren(folder / 'owned-children.jsonl')
        emit(folder / 'attempt.json', record)
        try:
            verify_files(q['files'])
            state = check()
            raw = (E / 'STATE.json').read_bytes()
            require(json.loads(raw) == state and not state.get('active_cpu_build'), 'CPU claim race')
            cas.cas_state(E / 'STATE.json', raw, dict(state, active_cpu_build=record))
            claimed = True
            result = run_owned(plan(stage), folder, b, owned, check, spawned=spawned)
            verify_files(q['files'])
        except BaseException as exc:
            primary = exc
        finally:
            try:
                absence = owned.absence()
                require(absence['passed'], 'Owned compiler descendants remain; retain claim')
                if claimed:
                    raw = (E / 'STATE.json').read_bytes()
                    state = json.loads(raw)
                    require(state.get('active_cpu_build') == record, 'Own CPU claim changed; leave foreign state')
                    cas.cas_state(E / 'STATE.json', raw, dict(state, active_cpu_build=False))
                    claimed = False
                check()
            except BaseException as exc:
                if primary is None:
                    primary = exc
                else:
                    primary.add_note('Build closure: ' + repr(exc))
            emit(folder / 'supervision.json', {'passed': primary is None, 'owned_claim_released': not claimed,
                                              'error': repr(primary) if primary else None})
        if primary is not None:
            raise primary
        require(result is not None and not claimed, 'Full build closure required')
        emit(folder / 'result.json', {'passed': True, 'stage': stage, 'child': result,
                                     'model_executed': False, 'production_changed': False})


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage', choices=['configure', 'compile'], required=True)
    ap.add_argument('--qualification-sha256', required=True)
    args = ap.parse_args()
    main(args.stage, args.qualification_sha256)
