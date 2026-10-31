"""Isolated IQ2_XS CPU archive build. No native/fixture execution or service action.

Prepare reproduces selected92 and discovers headers. Compile requires a second
qualification of actual prepare inputs. All writes stay in fresh owned stages.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shlex
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
N = HERE.parent
D = N.parent
R = Path('/home/alex/strata-deepseek-test-20261024')
E = R / 'reliability-optimization-20261025'
S = R / 'maya-ablate469-v2'
B = R / 'maya-build-sm80-ablate469-v2'
EXPECTED = E / 'decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1'
BASE = '92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
ARCHIVE = '60821a6dbe824a757723926b71a7d6092cc902c449c4d0cb0c9503c07d438ebd'
SUPPORT_SHA = 'e8dcd79bd3a80cba931885149438f107d6d840693e508f738fd616fd6885f9ff'
CAS_SHA = '8d10d003bbbd7ffbb87251bacdf53d91af9f074151d34f06c957fa179f3108cf'
IMPORT_Q_SHA = '6eb179b8b7edb7a87133c4e24bd99dc2f35863cfe6ef56f8385590bf50c6315b'
ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
       'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1',
       'PYTHONDONTWRITEBYTECODE': '1', 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
MEMBERS = ('expert.cpp.o', 'pool.cpp.o', 'expert_layout.cpp.o', 'q2_avx2.cpp.o',
           'exl3_ref.cpp.o', 'exl3_cpu.cpp.o', 'native_expert.cpp.o', 'iq_avx512.cpp.o',
           'iq_avx2.cpp.o', 'kq_avx512.cpp.o', 'iq_avx512_one.cpp.o')
REPLACED = ('iq_avx2.cpp.o', 'native_expert.cpp.o')


class BuildDeferred(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def regular(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and path.is_file() and
            not path.is_symlink() and path.stat().st_nlink == 1, 'Owned regular file required')
    return path


def fresh(path):
    require(path.parent.is_dir() and path.parent.resolve() == path.parent and
            not path.exists() and not path.is_symlink(), 'Fresh owned namespace required')


def emit(path, value):
    require(path.parent.resolve() == path.parent, 'Output ancestor alias')
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False); f.write('\n')


def dependencies(text, relative_to):
    """Compiler/ld Make rules including empty phony rules; no shell evaluation."""
    result = set(); saw = False
    for line in text.replace('\\\n', ' ').splitlines():
        if not line.strip():
            continue
        require(':' in line, 'Dependency target absent')
        target, body = line.split(':', 1)
        require(target.strip() and ':' not in body, 'Malformed dependency rule')
        saw = True
        for value in shlex.split(body):
            p = Path(value)
            result.add(str(p if p.is_absolute() else relative_to / p))
    require(saw and result, 'Empty dependencies')
    return sorted(result)


def observations():
    return (json.loads((HERE / 'DEPENDENCY_OBSERVATION.json').read_text()),
            json.loads((HERE / 'LINK_TOOL_CLOSURE_OBSERVATION.json').read_text()))


def inventory(first, second):
    result = {}
    for observation in (first, second):
        for name, row in observation['files'].items():
            require(Path(name).is_absolute() and len(row['sha256']) == 64, 'Bad observed input')
            prior = result.get(name)
            require(prior is None or prior['sha256'] == row['sha256'], 'Conflicting observed input')
            result[name] = dict(row) if prior is None else dict(prior, **row)
    return result


def verify_files(files, observed):
    for name, pin in files.items():
        path = Path(name)
        require(path.is_absolute(), 'Absolute input required')
        row = observed.get(name)
        if row is None:
            regular(path)
            require(path.is_relative_to(R) or path.is_relative_to(Path('/home/alex/deepseek-hosted-20261025')),
                    'Unobserved external input')
        else:
            require(row['sha256'] == pin and path.is_file(), 'Observed input differs')
            if 'resolved' in row:
                require(str(path.resolve()) == row['resolved'], 'Observed tool/library target changed')
        require(sha(path) == pin, 'Pinned input changed: ' + name)


def variable(text, name):
    rows = [v.split('=', 1)[1].strip() for v in text.splitlines() if v.startswith(name + ' =')]
    require(len(rows) == 1, 'Missing/duplicate compiler variable')
    return shlex.split(rows[0])


def compiler(first):
    target = str(B / 'CMakeFiles/strata_kernels_cpu.dir/flags.make')
    flags = first['files'][target]['text']
    defines = variable(flags, 'CXX_DEFINES')
    includes = variable(flags, 'CXX_INCLUDES')
    options = variable(flags, 'CXX_FLAGS')
    require(defines == ['-DSTRATA_NATIVE_EXPERTS=1', '-DSTRATA_VERSION="0.1.27"'] and
            options == ['-O3', '-DNDEBUG', '-std=c++20'], 'Selected arithmetic/version flags changed')
    require(includes == ['-I' + str(S / 'include'), '-I' + str(S / 'third_party/ggml'),
                         '-I' + str(R / 'llama.cpp/ggml/src/../include')], 'Selected include recipe changed')
    for name in ('iq_avx2.cpp', 'native_expert.cpp'):
        obj = 'CMakeFiles/strata_kernels_cpu.dir/src/kernels/cpu/' + name + '.o'
        extra = ' -mavx2 -mfma -mf16c -ffp-contract=off' if name == 'iq_avx2.cpp' else ''
        expected = ('/usr/bin/c++ $(CXX_DEFINES) $(CXX_INCLUDES) $(CXX_FLAGS)' + extra +
                    ' -MD -MT ' + obj + ' -MF ' + obj + '.d -o ' + obj + ' -c ' + str(S / 'src/kernels/cpu' / name))
        require([v.strip() for v in first['recipes'][name]] == [expected], 'Actual compile recipe changed')
    return ['/usr/bin/c++'] + defines + ['-I' + str(N / 'candidate/include')] + includes + options


def native_link(first, folder, *, candidate=False):
    raw = first['files'][str(B / 'CMakeFiles/maya-ds4.dir/link.txt')]['text']
    argv = shlex.split(raw)
    require(argv[:3] == ['/usr/bin/c++', '-O3', '-DNDEBUG'] and argv.count('-o') == 1,
            'Selected native link recipe differs')
    objects = [x for x in argv if x.endswith('.o')]
    require(len(objects) == 10 and len(set(objects)) == 10 and
            all(x.startswith('CMakeFiles/maya-ds4.dir/src/ds4/') for x in objects), 'Original native object inventory differs')
    require(argv.count('libstrata_kernels_cpu.a') == 1 and argv[argv.index('-o') + 1] == 'maya-ds4',
            'Original CPU archive/output missing')
    output = folder / ('maya-ds4-candidate' if candidate else 'selected-relink')
    result = []; deps = 0
    for i, value in enumerate(argv):
        if i == argv.index('-o') + 1:
            result.append(str(output))
        elif value.startswith('-Wl,--dependency-file='):
            deps += 1; result.append('-Wl,--dependency-file=' + str(output) + '.link.d')
        elif value == 'libstrata_kernels_cpu.a' and candidate:
            result.append(str(folder / 'libstrata_kernels_cpu.a'))
        elif not value.startswith('-') and value.endswith(('.o', '.a', '.so')):
            result.append(value if Path(value).is_absolute() else str(B / value))
        else:
            result.append(value)
    require(deps == 1, 'Exactly one redirected native dependency output required')
    return result


def compile_command(first, name, folder, *, scan=False):
    common = compiler(first)
    source = N / 'candidate/src/kernels/cpu' / name
    if name == 'iq2xs_exact.cpp':
        source = N / 'numerical-v2' / name
        common += ['-I' + str(S / 'src/ds4')]
    elif name == 'iq_avx2.cpp':
        common += ['-mavx2', '-mfma', '-mf16c', '-ffp-contract=off']
    else:
        require(name == 'native_expert.cpp', 'Unexpected compile source')
    output = folder / (name + ('.headers.d' if scan else '.o'))
    return common + (['-M', '-MT', name + '.o', '-o', str(output), str(source)] if scan else
                     ['-MD', '-MT', name + '.o', '-MF', str(output) + '.d', '-o', str(output), '-c', str(source)])


def fixture_link(folder):
    return ['/usr/bin/c++', '-O3', '-DNDEBUG', '-Wl,--dependency-file=' + str(folder / 'iq2xs_exact.link.d'),
            str(folder / 'iq2xs_exact.cpp.o'), str(B / 'CMakeFiles/maya-ds4.dir/src/ds4/ds4_iq_cpu.cpp.o'),
            str(folder / 'libstrata_kernels_cpu.a'), str(B / 'libstrata_core.a'),
            str(B / 'ggml/src/libggml-cpu.a'), str(B / 'ggml/src/libggml-base.a'),
            '-lm', '-lpthread', '-ldl', '-o', str(folder / 'iq2xs_exact')]


def archive_members(data):
    """Read GNU ar contents without extracting or executing members. Symbol indexes excluded."""
    require(data[:8] == b'!<arch>\n', 'Regular GNU archive required')
    offset = 8; names = None; result = []
    while offset < len(data):
        require(offset + 60 <= len(data), 'Truncated archive header')
        header = data[offset:offset + 60]; offset += 60
        require(header[58:] == b'`\n', 'Bad archive header')
        name = header[:16].decode('ascii').strip()
        size = int(header[48:58]); require(size >= 0 and offset + size <= len(data), 'Archive member bounds')
        body = data[offset:offset + size]; offset += size + size % 2
        if name == '//':
            require(names is None, 'Duplicate archive name table'); names = body; continue
        if name in ('/', '/SYM64/'):
            continue
        if name.startswith('/'):
            require(names is not None and name[1:].isdigit(), 'Unknown archive name encoding')
            at = int(name[1:]); require(at < len(names), 'Archive longname bounds')
            end = names.find(b'/\n', at); require(end >= at, 'Archive longname terminator')
            name = names[at:end].decode('ascii')
        else:
            require(name.endswith('/'), 'Archive shortname terminator'); name = name[:-1]
        require(name and '/' not in name and name not in [x[0] for x in result], 'Duplicate/foreign archive member')
        result.append((name, hashlib.sha256(body).hexdigest()))
    require(offset == len(data), 'Archive trailing/truncated padding')
    return result


def archive_contract(original, candidate, replacements):
    before = archive_members(original); after = archive_members(candidate)
    require(tuple(x[0] for x in before) == MEMBERS and tuple(x[0] for x in after) == MEMBERS,
            'Archive member order/inventory changed')
    require(set(replacements) == set(REPLACED), 'Exactly two replacement members required')
    require(dict(after) == dict(dict(before), **replacements), 'Unchanged archive member changed')


def environment():
    env = dict(os.environ)
    for k in ('PYTHONPATH', 'PYTHONHOME', 'CPATH', 'CPLUS_INCLUDE_PATH', 'C_INCLUDE_PATH',
              'LIBRARY_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'LD_PRELOAD', 'LD_LIBRARY_PATH',
              'DEPENDENCIES_OUTPUT', 'SUNPRO_DEPENDENCIES', 'COLLECT_GCC_OPTIONS', 'GCC_COMPARE_DEBUG',
              'SOURCE_DATE_EPOCH', 'TMP', 'TEMP', 'TMPDIR'):
        env.pop(k, None)
    env.update(ENV)
    return env


def resource_class(argv, compiler_child):
    require(argv[0] in ('/usr/bin/c++', '/usr/bin/ar', '/usr/bin/ranlib'), 'Only pinned build tools allowed')
    require(compiler_child == ('-c' in argv), 'Compiler resource class differs')
    if argv[0] == '/usr/bin/c++':
        require(argv.count('-o') == 1 and not ('-M' in argv and '-c' in argv), 'Explicit compiler/link output required')
        if compiler_child: return 'compile', 120, 4 * 2**30, 300
        if '-M' in argv: return 'scan', 30, 512 * 2**20, 90
        return 'link', 30, 4 * 2**30, 90
    return 'archive', 30, 512 * 2**20, 90


def child_limits(cpu, memory, observed_path, environment_for_child):
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu)); resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    nice = os.getpriority(os.PRIO_PROCESS, 0); require(nice <= 15, 'Inherited nice differs'); os.nice(15 - nice)
    os.environ.clear(); os.environ.update(environment_for_child)
    emit(observed_path, {'pid': os.getpid(), 'ppid': os.getppid(), 'pgid': os.getpgid(0),
                         'cpu': list(resource.getrlimit(resource.RLIMIT_CPU)),
                         'as': list(resource.getrlimit(resource.RLIMIT_AS)), 'nice': os.getpriority(os.PRIO_PROCESS, 0),
                         'environment': {k: os.environ.get(k) for k in (*ENV, 'TMPDIR')}})


def group_alive(pid):
    try:
        os.killpg(pid, 0); return True
    except ProcessLookupError:
        return False


def cleanup(process, deadline):
    require(process.pid > 1 and process.pid != os.getpgrp(), 'Foreign process group')
    if process.poll() is None:
        require(os.getpgid(process.pid) == process.pid, 'Owned child group changed')
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if group_alive(process.pid):
            try: os.killpg(process.pid, sig)
            except ProcessLookupError: pass
        try: process.wait(timeout=min(.2, max(.001, deadline - time.monotonic())))
        except subprocess.TimeoutExpired: pass
    while group_alive(process.pid) and time.monotonic() < deadline:
        time.sleep(.01)
    require(not group_alive(process.pid), 'Owned descendants survive')


def run_child(argv, name, folder, guard, *, compiler_child=False):
    role, cpu, memory, wall = resource_class(argv, compiler_child)
    started = time.monotonic(); process = None
    row = {'argv': argv, 'pid': None, 'returncode': None, 'error': None, 'cleanup': [],
           'role': role, 'CPU_s': cpu, 'AS_bytes': memory,
           'wall_s': wall, 'cwd': str(folder)}
    try:
        guard()
        require(time.monotonic() - started < wall - 5, 'Initial guard exhausted deadline')
        temporary = folder / (name + '.tmp'); fresh(temporary); temporary.mkdir()
        child_env = dict(environment(), TMPDIR=str(temporary))
        with (folder / (name + '.stdout')).open('xb') as out, (folder / (name + '.stderr')).open('xb') as err:
            process = subprocess.Popen(argv, cwd=folder, env=child_env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, start_new_session=True,
                preexec_fn=lambda: child_limits(cpu, memory, folder / (name + '.observed.json'), child_env))
            row['pid'] = process.pid
            while process.poll() is None:
                require(time.monotonic() - started < wall - 5, 'Build child deadline')
                guard()  # between <=1s waits; guard duration consumes the same wall budget
                require(time.monotonic() - started < wall - 5, 'Build guard exhausted deadline')
                try: process.wait(timeout=min(1, max(.001, wall - 5 - (time.monotonic() - started))))
                except subprocess.TimeoutExpired: pass
            require(process.returncode == 0, 'Build child nonzero')
            actual = json.loads(regular(folder / (name + '.observed.json')).read_text())
            require(actual == {'pid': process.pid, 'ppid': os.getpid(), 'pgid': process.pid,
                    'cpu': [row['CPU_s']] * 2, 'as': [row['AS_bytes']] * 2,
                    'nice': 15, 'environment': dict(ENV, TMPDIR=str(temporary))}, 'Observed child identity/bounds differ')
            guard()
    except BaseException as exc:
        row['error'] = repr(exc)
    finally:
        if process is not None:
            try: cleanup(process, started + wall)
            except BaseException as exc: row['cleanup'].append(repr(exc))
            row['returncode'] = process.poll()
        row['elapsed_seconds'] = time.monotonic() - started
        row['status'] = ('DEFERRED_BUSY_PARTIALS_RETAINED' if row['error'] and
                         'DEFERRED_BUSY_UNTOUCHED_OR_CLEANUP_OWNED_COMPILER' in row['error'] and not row['cleanup']
                         else 'PASS' if row['returncode'] == 0 and row['error'] is None and not row['cleanup'] and
                         row['elapsed_seconds'] <= wall else 'HOLD')
        emit(folder / (name + '.json'), row)
    if row['error'] and 'DEFERRED_BUSY_UNTOUCHED_OR_CLEANUP_OWNED_COMPILER' in row['error'] and not row['cleanup']:
        raise BuildDeferred('DEFERRED_BUSY_PARTIALS_RETAINED')
    require(row['returncode'] == 0 and row['error'] is None and not row['cleanup'] and
            row['elapsed_seconds'] <= wall, 'Build child/cleanup failed; preserve attempt')
    return row


def load_exact(name, path, pin):
    require(sha(regular(path)) == pin, 'Support changed before import')
    old = sys.modules.get(name)
    require(old is None or Path(old.__file__).resolve() == path, 'Foreign support origin')
    if old is None:
        spec = importlib.util.spec_from_file_location(name, path)
        old = importlib.util.module_from_spec(spec); sys.modules[name] = old; spec.loader.exec_module(old)
    require(Path(old.__file__).resolve() == path and sha(path) == pin, 'Support origin/content changed')
    return old


def verify_q(mode, pin):
    path = HERE / (mode + '-qualification.json')
    require(sha(regular(path)) == pin, 'Qualification pin changed')
    q = json.loads(path.read_text())
    require(q.get('mode') == mode and q.get('manual_source_reviewed') is True and
            q.get('CPU_both_hosts_passed') is True, 'Exact mode/manual/CPU qualification required')
    first, second = observations(); observed = inventory(first, second)
    for name in ('DEPENDENCY_OBSERVATION.json', 'LINK_TOOL_CLOSURE_OBSERVATION.json'):
        require(q['files'].get(str(HERE / name)) == sha(HERE / name), 'Observed recipe unpinned')
    require(all(q['files'].get(k) == v['sha256'] for k, v in observed.items()), 'Original input/tool closure missing')
    prior = D / 'model-v1/numerical-qualification.json'
    require(q['files'].get(str(prior)) == IMPORT_Q_SHA and sha(prior) == IMPORT_Q_SHA, 'Inherited import closure absent')
    require(all(q['files'].get(n) == p for n, p in json.loads(prior.read_text())['files'].items() if n.endswith('.py')),
            'Inherited Python closure omitted')
    for name, value in ((D / 'iq2s-persistent-v1/iq2s_build.py', SUPPORT_SHA),
                        (D / 'prose-speed-v1/prose_measure.py', CAS_SHA)):
        require(q['files'].get(str(name)) == value, 'Build support/CAS missing')
    if mode == 'compile':
        prepared = HERE / 'prepare-FIRST/receipt.json'
        require(q.get('actual_inputs_manually_reviewed') is True and
                q['files'].get(str(prepared)) == sha(regular(prepared)), 'Actual input review missing')
        for name, row in json.loads(prepared.read_text())['discovered_headers'].items():
            require(q['files'].get(name) == row['sha256'], 'Discovered header unpinned')
            require(name not in observed or observed[name]['sha256'] == row['sha256'], 'Header conflict')
            observed[name] = row
    verify_files(q['files'], observed)  # before project imports
    driver_path = HERE / 'cpu_driver.py'
    require(q['source_sha256'].get('cpu_driver.py') == sha(driver_path), 'New driver unpinned')
    driver = load_exact('iq2xs_build_cpu_driver', driver_path, sha(driver_path))
    before = driver.checked(q['source_review_sha256'])
    require(q['source_sha256'] == before[0] and q['input_sha256'] == before[1] and q['test_ids'] == before[2],
            'Exact new controller proof map required')
    for n, p in before[0].items():
        require(q['files'].get(str(HERE / n)) == p, 'New source absent from q')
    for n, p in before[1].items():
        require(q['files'].get(n) == p, 'CPU input absent from q')
    require(q['files'].get(str(HERE / 'SOURCE_ROOT_REVIEW.json')) == q['source_review_sha256'], 'Manual review absent from q')
    for label in ('darwin', 'linux'):
        folder = HERE / ('CPU-FIRST-' + label)
        for name in ('attempt.json', 'observed.json', 'receipt.json', 'child.json', 'child.log', 'parent.json'):
            require(q['files'].get(str(folder / name)) == sha(regular(folder / name)), 'CPU raw proof absent')
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
    require(q.get('selected_binding') == first['binding'] == second['binding'], 'Frozen selected owner differs')
    require(sha(path) == pin, 'Qualification changed during verification')
    return q, observed


def discover_header(name):
    p = Path(name)
    allowed = (S / 'include', S / 'third_party/ggml', S / 'src/ds4',
               R / 'llama.cpp/ggml', Path('/usr/include'), Path('/usr/lib/gcc'))
    require(p.is_absolute() and any(p.resolve().is_relative_to(root.resolve()) for root in allowed) and
            p.is_file() and p.suffix not in ('.o', '.a', '.so', '.cpp', '.cu', '.py', '.bin'),
            'Unknown non-header dependency')
    return {'sha256': sha(p), 'resolved': str(p.resolve()), 'bytes': p.stat().st_size}


def actual_dependencies(path, cwd, allowed):
    names = dependencies(regular(path).read_text(), cwd)
    require(all(n in allowed for n in names), 'Unknown dependency; stop for review')
    result = {n: sha(n) for n in names}
    require(all(allowed[n] == p for n, p in result.items()), 'Actual dependency bytes changed')
    return result


def execute(mode, q, observed, guard):
    first, _ = observations()
    folder = HERE / ('prepare-FIRST' if mode == 'prepare' else 'build-FIRST')
    fresh(folder); guard()
    require(sha(B / 'maya-ds4') == BASE and sha(B / 'libstrata_kernels_cpu.a') == ARCHIVE,
            'Original selected executable/archive changed')
    produced = {}; children = []; actual = {}; discovered = {}
    def check():
        guard(); verify_files(q['files'], observed); verify_files(actual, observed)
        for name, pin in produced.items():
            require(sha(regular(name)) == pin, 'Produced artifact changed')
    check()
    if mode == 'compile':
        prep = HERE / 'prepare-FIRST/receipt.json'
        require(q.get('actual_inputs_manually_reviewed') is True and q['files'].get(str(prep)) == sha(prep),
                'Actual prepare review required')
        previous = json.loads(prep.read_text())
        require(previous['status'] == 'PREPARED_STOP_FOR_ACTUAL_INPUT_REVIEW' and previous['control_sha256'] == BASE and
                sha(HERE / 'prepare-FIRST/selected-relink') == BASE and
                all(q['files'].get(n) == p for n, p in previous['actual_inputs'].items()), 'Actual prepare custody differs')
    folder.mkdir()
    def job(name, argv, *, compiled=False, output=None, dependency=None, mutates=None):
        check(); children.append(run_child(argv, name, folder, guard, compiler_child=compiled))
        if mutates is not None:
            require(name in ('archive-replace', 'archive-index') and mutates == folder / 'libstrata_kernels_cpu.a',
                    'Unexpected mutable output')
            produced[str(mutates)] = sha(regular(mutates))
        check()
        if output is not None:
            produced[str(output)] = sha(regular(output))
        if dependency is not None:
            allowed = dict(q['files'], **produced)
            if mode == 'prepare' and name.startswith('deps-'):
                for path in dependencies(regular(dependency).read_text(), folder):
                    if path not in allowed:
                        row = discover_header(path)
                        discovered[path] = row; observed[path] = row; allowed[path] = row['sha256']
            found = actual_dependencies(dependency, folder, allowed)
            actual.update(found); emit(folder / (name + '-inputs.json'), found)
        check()
    if mode == 'prepare':
        output = folder / 'selected-relink'
        job('control-link', native_link(first, folder), output=output, dependency=Path(str(output) + '.link.d'))
        require(produced[str(output)] == BASE, 'Control relink does not reproduce selected92')
        for name in ('iq_avx2.cpp', 'native_expert.cpp', 'iq2xs_exact.cpp'):
            job('deps-' + name, compile_command(first, name, folder, scan=True),
                dependency=folder / (name + '.headers.d'))
        status = 'PREPARED_STOP_FOR_ACTUAL_INPUT_REVIEW'
    else:
        for name in ('iq_avx2.cpp', 'native_expert.cpp', 'iq2xs_exact.cpp'):
            output = folder / (name + '.o')
            job('compile-' + name, compile_command(first, name, folder), compiled=True,
                output=output, dependency=Path(str(output) + '.d'))
        target = folder / 'libstrata_kernels_cpu.a'
        check(); shutil.copyfile(B / 'libstrata_kernels_cpu.a', target)
        require(sha(regular(target)) == ARCHIVE, 'Archive copy differs')
        produced[str(target)] = ARCHIVE
        # Only this owned archive may change during these two tools.
        job('archive-replace', ['/usr/bin/ar', 'r', str(target)] + [str(folder / n) for n in REPLACED], mutates=target)
        archive_contract((B / 'libstrata_kernels_cpu.a').read_bytes(), regular(target).read_bytes(),
                         {n: produced[str(folder / n)] for n in REPLACED})
        job('archive-index', ['/usr/bin/ranlib', str(target)], mutates=target)
        archive_contract((B / 'libstrata_kernels_cpu.a').read_bytes(), regular(target).read_bytes(),
                         {n: produced[str(folder / n)] for n in REPLACED})
        produced[str(target)] = sha(target)
        output = folder / 'maya-ds4-candidate'
        job('candidate-link', native_link(first, folder, candidate=True), output=output, dependency=Path(str(output) + '.link.d'))
        output = folder / 'iq2xs_exact'
        job('fixture-link', fixture_link(folder), output=output, dependency=Path(str(output) + '.link.d'))
        status = 'COMPILED_STOP_FOR_SEPARATE_NUMERICAL_QUALIFICATION'
    check()
    value = {'status': status, 'passed': True, 'control_sha256': BASE if mode == 'prepare' else None,
             'actual_inputs': actual, 'discovered_headers': discovered, 'outputs': produced, 'children': children,
             'native_execution': False, 'fixture_execution': False, 'GPU_execution': False, 'production_changed': False}
    emit(folder / 'receipt.json', value)
    return value


def bootstrap(mode, pin):
    """Verify the declared Python closure before importing the read-only idle guard."""
    path = HERE / (mode + '-qualification.json')
    require(sha(regular(path)) == pin, 'Qualification pin changed before bootstrap')
    q = json.loads(path.read_text())
    prior = D / 'model-v1/numerical-qualification.json'
    require(q['files'].get(str(prior)) == IMPORT_Q_SHA and sha(regular(prior)) == IMPORT_Q_SHA,
            'Bootstrap inherited closure absent')
    required = {n: p for n, p in json.loads(prior.read_text())['files'].items() if n.endswith('.py')}
    required.update({str(D / 'iq2s-persistent-v1/iq2s_build.py'): SUPPORT_SHA,
                     str(D / 'prose-speed-v1/prose_measure.py'): CAS_SHA})
    require(required and all(q['files'].get(n) == p and sha(regular(n)) == p for n, p in required.items()),
            'Bootstrap Python closure changed')
    return q


def main(mode, pin):
    require(mode in ('prepare', 'compile') and sys.platform == 'linux' and HERE == EXPECTED, 'Exact physical build scope')
    require(sys.dont_write_bytecode is True, 'Explicit Python -B required')
    preliminary = bootstrap(mode, pin)
    c = load_exact('iq2s_build', D / 'iq2s-persistent-v1/iq2s_build.py', SUPPORT_SHA)
    _, runtime, _, host, binding = c.support()
    require(binding == preliminary['selected_binding'], 'Action-time owner differs')
    c.guard(runtime, host, binding)  # genuine idle before large input hashing
    require(shutil.disk_usage('/').free >= 136 * 2**30, 'Root136 unavailable')
    q, observed = verify_q(mode, pin)
    cas = load_exact('prose_measure', D / 'prose-speed-v1/prose_measure.py', CAS_SHA)
    record = {'controller_pid': os.getpid(), 'mode': 'iq2xs-cpu-' + mode, 'qualification_sha256': pin,
              'start_binding': binding}
    def guard(claimed=False):
        state = c.guard(runtime, host, binding, record if claimed else None)
        require(shutil.disk_usage('/').free >= 136 * 2**30, 'Root136 unavailable')
        require(sha(HERE / (mode + '-qualification.json')) == pin, 'Qualification changed')
        return state
    guard(); lockpath = regular(R / 'experiment.lock')
    with lockpath.open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = guard(); raw = (E / 'STATE.json').read_bytes()
        require(json.loads(raw) == state, 'Coordination changed before claim')
        primary = None; result = None
        try:
            cas.cas_state(E / 'STATE.json', raw, dict(state, active_cpu_build=record))
            result = execute(mode, q, observed, lambda: guard(True))
        except BaseException as exc:
            primary = exc
        finally:
            try:
                current = (E / 'STATE.json').read_bytes(); value = json.loads(current)
                require(value.get('active_cpu_build') == record, 'Own build claim changed; preserve foreign state')
                cas.cas_state(E / 'STATE.json', current, dict(value, active_cpu_build=False))
                require(json.loads((E / 'STATE.json').read_text()).get('active_cpu_build') is False, 'Build claim release failed')
            except BaseException as exc:
                if primary is None: primary = exc
                else: primary.add_note('Build release: ' + repr(exc))
            try: host.guard_binding()
            except BaseException as exc:
                if primary is None: primary = exc
                else: primary.add_note('Selected owner: ' + repr(exc))
        if primary is not None:
            if isinstance(primary, BuildDeferred) and getattr(primary, '__notes__', None):
                raise RuntimeError('Busy deferral also has cleanup/owner fault; HOLD') from primary
            raise primary
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'compile'))
    parser.add_argument('--qualification-sha256', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(main(args.mode, args.qualification_sha256)))
    except BuildDeferred as exc:
        print(json.dumps({'status': str(exc), 'retry_authorized': False})); sys.exit(75)
