"""One-shot IQ2_S-only prepare/compile, never execute a native or allocate a GPU.

Preparation discovers actual headers around a reviewed candidate. Compilation
requires a separately pinned review of those receipts. Existing objects and
production are read-only. The inherited compiler runner retains CPU120s,
AS4GiB, wall300s per compiler child; CPU controls use CPU30/AS512/wall90.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
P = HERE.parent
R = Path('/home/alex/strata-deepseek-test-20261024')
E = R / 'reliability-optimization-20261025'
EXPECTED = E / 'decode-optimization-20261028/iq2s-persistent-v1'
BUILD_SHA = 'b72f16217878714132fa4e161de52208567e23a7189c1e5781dc3375ec9c6491'
RUNTIME_SHA = '157b7750a2da5d495c08ece100d19432d48fe52aeaac9e982a63762dd742425e'
CONFIG_SHA = '18691963f89027fd169877c0cd6307f54954de1353a577d4c8935c015ea84986'
BASE = '92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
PREP = HERE / 'prepare-FIRST'
OUT = HERE / 'build-FIRST'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    import hashlib
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def load_exact(name, path, pin):
    require(sha(path) == pin, 'Imported source differs: ' + name)
    module = sys.modules.get(name)
    require(module is None or Path(module.__file__).resolve() == path, 'Foreign import origin')
    sys.path.insert(0, str(path.parent))
    return importlib.import_module(name)


def support():
    b = load_exact('selected_build', P / 'selected_build.py', BUILD_SHA)
    load_exact('imma_config', P / 'model-v1/imma_config.py', CONFIG_SHA)
    runtime = load_exact('imma_model_runtime', P / 'model-v1/imma_model_runtime.py', RUNTIME_SHA)
    a, _ = runtime.support()
    state = json.loads((E / 'STATE.json').read_text())
    binding = runtime.current_binding(state)
    host = a.ChunkProductionHost()
    host.start_binding = dict(binding)
    return b, runtime, a, host, binding


def guard(runtime, host, binding, reservation=None):
    import shutil
    state = json.loads((E / 'STATE.json').read_text())
    for key in runtime.PHASE_KEYS:
        if key == 'active_cpu_build' and reservation is not None:
            require(state.get(key) == reservation, 'CPU reservation changed')
        else:
            require(not state.get(key), 'Active phase/build/pending restoration')
    require(runtime.current_binding(state) == binding, 'Selected owner changed')
    require(host.idle(), 'DEFERRED_BUSY_UNTOUCHED_OR_CLEANUP_OWNED_COMPILER')
    host.guard_binding()
    require(shutil.disk_usage('/').free >= 132 * 2**30, 'Root132 unavailable')
    return state


def real_directory(path):
    require(path.is_absolute() and '..' not in path.parts, 'Canonical directory required')
    for parent in [*reversed(path.parents), path]:
        require(parent.is_dir() and not parent.is_symlink(), 'Directory alias refused')


def fresh(path):
    real_directory(path.parent)
    require(not path.exists() and not path.is_symlink(), 'Existing attempt refused')


def emit_new(path, data):
    real_directory(path.parent)
    with path.open('x') as stream:
        stream.write(json.dumps(data, indent=2, allow_nan=False) + '\n')


def verify_q(path, digest):
    require(path.parent == HERE and path.name in ('prepare-qualification.json', 'compile-qualification.json'),
            'Exact qualification path required')
    require(not path.is_symlink() and sha(path) == digest, 'Qualification identity differs')
    q = json.loads(path.read_text())
    require(q.get('mode') == path.name.removesuffix('-qualification.json'), 'Wrong stage qualification')
    require(q.get('manual_source_reviewed') is True and q.get('CPU_both_hosts_passed') is True,
            'Manual and both-host CPU proof required')
    required = {str(HERE / n): pin for n, pin in q['source_sha256'].items()}
    require(required and all(q['files'].get(n) == pin for n, pin in required.items()),
            'Source map not in file closure')
    require(str(HERE / 'iq2s_build.py') in required and str(HERE / 'test_iq2s_build.py') in required,
            'Controller/test pins absent')
    manifest = HERE / 'candidate-files.json'
    require(q['files'].get(str(manifest)) == sha(manifest), 'Candidate manifest unpinned')
    candidate_names = json.loads(manifest.read_text())['files']
    require(type(candidate_names) is list and candidate_names and len(candidate_names) == len(set(candidate_names)),
            'Candidate file inventory differs')
    for name in candidate_names:
        part = Path(name)
        require(not part.is_absolute() and '..' not in part.parts, 'Candidate path escapes')
        full = HERE / 'candidate' / part
        require(str(full) in required and required[str(full)] == sha(full), 'Candidate source not CPU-pinned')
    prior = P / 'model-v1/numerical-qualification.json'
    require(q['files'].get(str(prior)) ==
            '6eb179b8b7edb7a87133c4e24bd99dc2f35863cfe6ef56f8385590bf50c6315b',
            'Inherited import-closure qualification absent')
    inherited = json.loads(prior.read_text())['files']
    require(all(q['files'].get(n) == pin for n, pin in inherited.items() if n.endswith('.py')),
            'Inherited Python import closure incomplete')
    # Linker/compiler dependency rules legitimately retain lexical ../ aliases.
    # Admit those exact raw names only from the newly reviewed preparation receipt.
    raw_inputs = {}
    if q['mode'] == 'compile':
        prepared = PREP / 'receipt.json'
        require(q['files'].get(str(prepared)) == sha(prepared)
                and q.get('actual_inputs_manually_reviewed') is True, 'Reviewed raw-input receipt absent')
        raw_inputs = json.loads(prepared.read_text())['input_sha256']
    for name, pin in q['files'].items():
        path_in = Path(name)
        require(path_in.is_absolute() and ('..' not in path_in.parts or raw_inputs.get(name) == pin)
                and sha(path_in) == pin,
                'Pinned input changed')
    ids = q['test_ids']
    require(type(ids) is list and ids and len(ids) == len(set(ids)), 'Exact case IDs absent')
    policy_ids = q['policy_test_ids']
    require(type(policy_ids) is list and policy_ids and len(policy_ids) == len(set(policy_ids)),
            'Exact policy case IDs absent')
    for label in ('darwin', 'linux'):
        folder = HERE / ('build-CPU-FIRST-' + label)
        for name in ('receipt.json', 'child.json', 'child.log'):
            require(q['files'].get(str(folder / name)) == sha(folder / name), 'CPU raw receipt unpinned')
        receipt = json.loads((folder / 'receipt.json').read_text())
        child = json.loads((folder / 'child.json').read_text())
        require(receipt.get('passed') is True and receipt.get('test_ids') == ids
                and receipt.get('source_sha256') == q['source_sha256']
                and type(receipt.get('controls')) is int and receipt['controls'] == len(ids)
                and receipt.get('GPU_execution') is False and receipt.get('compiler_execution') is False,
                'Exact both-host CPU proof differs')
        expected = {'returncode': 0, 'CPU_s': 30, 'wall_s': 90, 'nice': 15,
                    'CUDA_hidden': True, 'Linux_AS_MiB': 512 if label == 'linux' else None}
        require(all(type(child.get(k)) is type(v) and child[k] == v for k, v in expected.items()),
                'CPU child bounds differ')
        require(child.get('error') is None and child.get('cleanup_errors') == [],
                'CPU child supervision incomplete')
        policy = HERE / ('policy-CPU-FIRST-' + label)
        for name in ('receipt.json', 'compile.json', 'run.json', 'compile.stdout',
                     'compile.stderr', 'run.stdout', 'run.stderr'):
            require(q['files'].get(str(policy / name)) == sha(policy / name), 'Policy raw proof absent')
        proof = json.loads((policy / 'receipt.json').read_text())
        require(proof.get('passed') is True and proof.get('source_sha256') == q['source_sha256']
                and proof.get('test_ids') == q['policy_test_ids']
                and type(proof.get('controls')) is int
                and proof['controls'] == len(q['policy_test_ids'])
                and proof.get('GPU_execution') is False and proof.get('CUDA_compilation') is False,
                'Exact portable policy proof differs')
        require(len(proof['children']) == 2, 'Policy compile/run child evidence absent')
        for row in proof['children']:
            require(all(type(row.get(k)) is type(v) and row[k] == v for k, v in expected.items())
                    and row.get('error') is None and row.get('cleanup_errors') == [],
                    'Policy CPU bounds or supervision differ')
    require(sha(path) == digest, 'Qualification changed during read')
    return q


def plans(b):
    native = (b.B / 'CMakeFiles/maya-ds4.dir/link.txt').read_text()
    fixture = (b.B / 'CMakeFiles/ds4_gguf_test.dir/link.txt').read_text()
    prep = b.commands(native, fixture, PREP, HERE / 'candidate')[:3]
    compile_jobs = b.commands(native, fixture, OUT, HERE / 'candidate')[3:]
    require([n for n, _ in prep] == ['selected-relink', 'deps-iq', 'deps-test']
            and [n for n, _ in compile_jobs] ==
            ['compile-iq', 'compile-test', 'candidate-link', 'test-link'], 'Exact compiler plan differs')
    for name, argv in prep + compile_jobs:
        require(argv[0] in ('/usr/bin/c++', '/usr/local/cuda/bin/nvcc')
                and argv.count('-o') == 1, 'Unexpected command or output')
        target = Path(argv[argv.index('-o') + 1])
        require(target.parent == (PREP if name in ('selected-relink', 'deps-iq', 'deps-test') else OUT),
                'Foreign output')
        require('--use_fast_math' not in argv and
                ('--threads' not in argv or argv[argv.index('--threads') + 1] == '1'),
                'Compiler arithmetic/concurrency changed')
    return prep, compile_jobs


def prepare(b, q, admission):
    fresh(PREP)
    evidence_path = P / 'prepare-r2/prepare-inputs.json'
    old = json.loads(evidence_path.read_text())
    require(q['files'].get(str(evidence_path)) == sha(evidence_path), 'Tool/input receipt unpinned')
    b.check_tools(old['tools'])
    require(sha(b.B / 'maya-ds4') == BASE, 'Original selected executable changed')
    jobs, full = plans(b)
    admission()
    PREP.mkdir()
    emit_new(PREP / 'plan.json', {'commands': jobs, 'compile_plan_unrun': full})
    inputs = {n: pin for n, pin in old['input_sha256'].items()
              if not Path(n).is_relative_to(P)}
    # Old candidate inputs are excluded; current candidate headers are discovered
    # prospectively below, and separately reviewed before compilation.
    b.check_files(inputs)
    rows, discovered = [], {}
    for name, argv in jobs:
        admission()
        b.check_files(q['files'])
        b.check_files(inputs)
        b.check_tools(old['tools'])
        row = b.run_child(argv, name, PREP, admission)
        rows.append(row)
        admission()
        b.check_files(q['files'])
        if name == 'selected-relink':
            require(sha(PREP / 'selected-relink') == BASE, 'Control relink differs')
            dep = PREP / 'selected-relink.link.d'
            relative = b.B
        else:
            dep = PREP / ('iq.headers.d' if name == 'deps-iq' else 'test.headers.d')
            relative = None
        found = b.dependencies(dep.read_text(), relative_to=relative)
        discovered[name] = {n: sha(n) for n in found}
        for n, pin in discovered[name].items():
            require(n not in inputs or inputs[n] == pin, 'Input changed during discovery')
            inputs[n] = pin
        b.check_files(inputs)
        emit_new(PREP / (name + '-inputs.json'), discovered[name])
    admission()
    b.check_files(inputs)
    b.check_tools(old['tools'])
    receipt = {'passed': True, 'status': 'PREPARED_STOP_FOR_ACTUAL_INPUT_REVIEW',
               'original_relink_sha256': sha(PREP / 'selected-relink'),
               'input_sha256': inputs, 'discovered': discovered, 'tools': old['tools'],
               'children': rows, 'GPU_execution': False, 'CUDA_compilation': False}
    emit_new(PREP / 'receipt.json', receipt)
    return receipt


def compile_candidate(b, q, admission):
    fresh(OUT)
    path = PREP / 'receipt.json'
    require(q['files'].get(str(path)) == sha(path), 'Actual preparation receipt not pinned')
    evidence = json.loads(path.read_text())
    require(evidence.get('passed') is True and evidence.get('status') ==
            'PREPARED_STOP_FOR_ACTUAL_INPUT_REVIEW' and
            evidence['original_relink_sha256'] == BASE and sha(PREP / 'selected-relink') == BASE,
            'Actual selected control absent')
    require(q.get('actual_inputs_manually_reviewed') is True, 'Actual input review absent')
    for n, pin in evidence['input_sha256'].items():
        require(q['files'].get(n) == pin, 'Actual input closure unpinned')
    _, jobs = plans(b)
    produced = {}
    def check():
        admission()
        b.check_files(q['files'])
        b.check_files(evidence['input_sha256'])
        b.check_tools(evidence['tools'])
        b.check_files(produced)
    check()
    OUT.mkdir()
    emit_new(OUT / 'plan.json', {'commands': jobs})
    rows = []
    for name, argv in jobs:
        check()
        rows.append(b.run_child(argv, name, OUT, admission))
        admission()
        artifact = Path(argv[argv.index('-o') + 1])
        require(not artifact.is_symlink() and artifact.is_file(), 'Missing fresh artifact')
        produced[str(artifact)] = sha(artifact)
        check()
        if name.endswith('-link'):
            actual = b.dependencies(Path(str(artifact) + '.link.d').read_text(), relative_to=b.B)
            unknown = set(actual) - set(evidence['input_sha256']) - set(produced)
            emit_new(OUT / (name + '-inputs.json'), {'files': {n: sha(n) for n in actual},
                                                    'unknown': sorted(unknown)})
            require(not unknown, 'New actual link input; HOLD before next child')
    receipt = {'passed': True, 'status': 'COMPILED_STOP_FOR_KERNEL_QUALIFICATION',
               'outputs': produced, 'children': rows, 'GPU_execution': False,
               'model_execution': False, 'production_changed': False}
    emit_new(OUT / 'receipt.json', receipt)
    return receipt


def main(mode, digest):
    require(mode in ('prepare', 'compile'), 'Exact build stage required')
    require(sys.platform == 'linux' and HERE == EXPECTED, 'Exact physical Ubuntu scope only')
    b, runtime, a, host, binding = support()
    state = guard(runtime, host, binding)
    qp = HERE / (mode + '-qualification.json')
    q = verify_q(qp, digest)
    fresh(PREP if mode == 'prepare' else OUT)
    guard(runtime, host, binding)
    require(json.loads((E / 'STATE.json').read_text()) == state, 'Coordination changed before claim')
    reservation = {'controller_pid': os.getpid(), 'mode': 'iq2s-persistent-' + mode + '-only'}
    claimed = dict(state, active_cpu_build=reservation)
    def admission():
        guard(runtime, host, binding, reservation)
        require(sha(qp) == digest, 'Qualification changed')
    primary = None
    try:
        a.emit(E / 'STATE.json', claimed)
        return (prepare if mode == 'prepare' else compile_candidate)(b, q, admission)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            now = json.loads((E / 'STATE.json').read_text())
            require(now.get('active_cpu_build') == reservation,
                    'Own CPU reservation lost; foreign state preserved, HOLD')
            now['active_cpu_build'] = False
            a.emit(E / 'STATE.json', now)
            released = json.loads((E / 'STATE.json').read_text())
            require(released.get('active_cpu_build') is False, 'Own CPU release not persisted; HOLD')
        except BaseException as exc:
            if primary is None:
                raise
            primary.add_note('Owned CPU release fault: ' + repr(exc))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'compile'))
    parser.add_argument('--qualification-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(main(args.mode, args.qualification_sha256)))

