"""Fresh, separately qualified Q8 sharing prepare/compile. Never run a native.

Only ds4_gguf.cu is replaced in the selected native link. A control relink must
reproduce selected92 before CUDA compilation. Original objects remain read-only.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
P = HERE.parent
E = Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025')
EXPECTED = E / 'decode-optimization-20261028/q8-sharing-v1'
BASE = '92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
SUPPORT_SHA = 'e8dcd79bd3a80cba931885149438f107d6d840693e508f738fd616fd6885f9ff'
CAS_SHA = '8d10d003bbbd7ffbb87251bacdf53d91af9f074151d34f06c957fa179f3108cf'
IMPORT_Q_SHA = '6eb179b8b7edb7a87133c4e24bd99dc2f35863cfe6ef56f8385590bf50c6315b'
PREP = HERE / 'prepare-FIRST'
OUT = HERE / 'build-FIRST'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def support():
    path = P / 'iq2s-persistent-v1/iq2s_build.py'
    require(sha(path) == SUPPORT_SHA, 'Qualified build support changed')
    previous = sys.modules.get('iq2s_build')
    require(previous is None or Path(previous.__file__).resolve() == path, 'Foreign support import')
    sys.path.insert(0, str(path.parent))
    c = importlib.import_module('iq2s_build')
    b, runtime, a, host, binding = c.support()
    return c, b, runtime, a, host, binding


def plans(b):
    """Use the original link lines, compiler flags and original unmodified objects."""
    native = (b.B / 'CMakeFiles/maya-ds4.dir/link.txt').read_text()
    fixture = (b.B / 'CMakeFiles/ds4_gguf_test.dir/link.txt').read_text()
    old = 'CMakeFiles/maya-ds4.dir/src/ds4/ds4_gguf.cu.o'
    # The qualified existing command builder supplies the selected nvcc flags.
    template = b.commands(native, fixture, OUT, HERE / 'candidate')[3][1]
    common = template[:-3] if template[-2] == '-o' else []
    require(common and common[-1] == '-c', 'Original CUDA command shape changed')
    source = HERE / 'candidate/src/ds4/ds4_gguf.cu'
    check = HERE / 'candidate/tests/q8_share_check.cu'
    # Includes local candidate headers first, then the selected source headers.
    common = common[:1] + ['-I' + str(source.parent)] + common[1:]
    def compile_command(src, target, deps=False):
        args = [v for v in common if not (deps and v == '--ptxas-options=-v')]
        if deps:
            args[args.index('-c')] = '-M'
        return args + [str(src), '-o', str(target)]
    test_objects = [v for v in __import__('shlex').split(fixture) if v.endswith('.o')]
    replacements = {}
    for value in test_objects:
        if value.endswith('/tests/ds4_gguf_test.cu.o'):
            replacements[value] = OUT / 'q8_share_check.cu.o'
        elif value.endswith('/src/ds4/ds4_gguf.cu.o'):
            replacements[value] = OUT / 'ds4_gguf.cu.o'
        else:
            replacements[value] = value.replace('ds4_gguf_test.dir/', 'maya-ds4.dir/')
    require(old in __import__('shlex').split(native), 'Selected GGUF object absent')
    require(any(v.endswith('/tests/ds4_gguf_test.cu.o') for v in test_objects), 'Original test object absent')
    prep = [('selected-relink', b.link_plan(native, 'maya-ds4', PREP / 'selected-relink', {})),
            ('deps-gguf', compile_command(source, PREP / 'gguf.headers.d', True)),
            ('deps-test', compile_command(check, PREP / 'test.headers.d', True))]
    comp = [('compile-gguf', compile_command(source, OUT / 'ds4_gguf.cu.o')),
            ('compile-test', compile_command(check, OUT / 'q8_share_check.cu.o')),
            ('candidate-link', b.link_plan(native, 'maya-ds4', OUT / 'maya-ds4-candidate',
                                         {old: OUT / 'ds4_gguf.cu.o'})),
            ('test-link', b.link_plan(fixture, 'ds4_gguf_test', OUT / 'q8_share_check', replacements))]
    for name, args in prep + comp:
        require(args[0] in ('/usr/bin/c++', '/usr/local/cuda/bin/nvcc') and args.count('-o') == 1,
                'Unexpected compiler command')
        output = Path(args[args.index('-o') + 1])
        require(output.parent == (PREP if name in ('selected-relink', 'deps-gguf', 'deps-test') else OUT),
                'Output escaped owned stage')
        require('--use_fast_math' not in args, 'Arithmetic compiler flag changed')
        if args[0].endswith('/nvcc'):
            require(args[args.index('--threads') + 1] == '1' and
                    '--generate-code=arch=compute_80,code=[compute_80,sm_80]' in args,
                    'CUDA architecture/concurrency changed')
    return prep, comp


def verify_q(c, mode, digest):
    path = HERE / (mode + '-qualification.json')
    require(sha(path) == digest and not path.is_symlink(), 'Qualification changed')
    q = json.loads(path.read_text())
    require(q.get('mode') == mode and q.get('manual_source_reviewed') is True
            and q.get('CPU_both_hosts_passed') is True, 'Missing exact source/CPU qualification')
    required = q['source_sha256']
    require({'build.py', 'test_build.py', 'test_driver.py', 'qualify_cpu.py'} <= set(required), 'Build sources/driver absent')
    require(required == {n: sha(HERE / n) for n in required}, 'New source differs')
    require(all(q['files'].get(str(HERE / n)) == pin for n, pin in required.items()),
            'Source not pinned in input closure')
    manifest_path = HERE / 'candidate-files.json'
    require(q['files'].get(str(manifest_path)) == sha(manifest_path), 'Candidate manifest unpinned')
    manifest = json.loads(manifest_path.read_text())
    require(type(manifest.get('files')) is dict and len(manifest['files']) == 5,
            'Exact candidate inventory absent')
    for n, pin in manifest['files'].items():
        rel = Path(n)
        require(not rel.is_absolute() and '..' not in rel.parts and rel.parts[0] == 'candidate'
                and required.get(n) == pin and sha(HERE / rel) == pin, 'Candidate source absent/different')
    require(q.get('policy_test_ids') == manifest['policy_test_ids']
            and len(q['policy_test_ids']) == 46, 'Exact new policy IDs absent')
    oldq = P / 'model-v1/numerical-qualification.json'
    require(sha(oldq) == IMPORT_Q_SHA and q['files'].get(str(oldq)) == IMPORT_Q_SHA,
            'Inherited import closure qualification absent')
    old_files = json.loads(oldq.read_text())['files']
    require(all(q['files'].get(n) == pin for n, pin in old_files.items() if n.endswith('.py')),
            'Inherited Python import closure missing')
    require(q['files'].get(str(P / 'prose-speed-v1/prose_measure.py')) == CAS_SHA,
            'CAS helper unpinned')
    for n, pin in q['files'].items():
        p = Path(n)
        require(p.is_absolute() and sha(p) == pin, 'Actual qualification input changed')
    for label in ('darwin', 'linux'):
        folder = HERE / ('build-CPU-FIRST-' + label)
        child = json.loads((folder / 'child.json').read_text())
        receipt = json.loads((folder / 'receipt.json').read_text())
        expected = {'returncode': 0, 'CPU_s': 30, 'wall_s': 90, 'nice': 15,
                    'CUDA_hidden': True, 'Linux_AS_MiB': 512 if label == 'linux' else None}
        require(all(type(child.get(k)) is type(v) and child[k] == v for k, v in expected.items())
                and child.get('error') is None and child.get('cleanup_errors') == [], 'CPU supervision incomplete')
        require(receipt.get('passed') is True and receipt.get('source_sha256') == required
                and receipt.get('test_ids') == q['test_ids']
                and receipt.get('source_input_sha256') == q['source_input_sha256']
                and type(receipt.get('controls')) is int and receipt['controls'] == len(q['test_ids'])
                and all(receipt.get(k) is False for k in ('GPU_execution', 'native_execution', 'compiler_execution')),
                'Exact source/maps/IDs differ')
        for name in ('receipt.json', 'child.json', 'child.log'):
            require(q['files'].get(str(folder / name)) == sha(folder / name), 'CPU raw proof unpinned')
        policy = HERE / ('policy-CPU-FIRST-' + label)
        for name in ('receipt.json', 'compile.json', 'run.json', 'compile.stdout',
                     'compile.stderr', 'run.stdout', 'run.stderr'):
            require(q['files'].get(str(policy / name)) == sha(policy / name), 'Policy raw proof absent')
        proof = json.loads((policy / 'receipt.json').read_text())
        require(proof.get('passed') is True and proof.get('source_sha256') == required
                and proof.get('test_ids') == q['policy_test_ids']
                and type(proof.get('controls')) is int and proof['controls'] == len(q['policy_test_ids'])
                and proof.get('GPU_execution') is False and proof.get('CUDA_compilation') is False
                and len(proof.get('children', [])) == 2, 'Policy CPU proof differs')
        for child in proof['children']:
            require(all(type(child.get(k)) is type(v) and child[k] == v for k, v in expected.items())
                    and child.get('error') is None and child.get('cleanup_errors') == [], 'Policy child bounds differ')
    require(q['files'].get(str(P / 'iq2s-persistent-v1/iq2s_build.py')) == SUPPORT_SHA,
            'Qualified support closure absent')
    if mode == 'compile':
        require(q.get('actual_inputs_manually_reviewed') is True and
                q['files'].get(str(PREP / 'receipt.json')) == sha(PREP / 'receipt.json'),
                'Actual preparation unreviewed')
    require(sha(path) == digest, 'Qualification changed during verification')
    return q


def prepare(c, b, q, admission):
    c.fresh(PREP)
    evidence = P / 'prepare-r2/prepare-inputs.json'
    require(q['files'].get(str(evidence)) == sha(evidence), 'Actual tool baseline absent')
    prior = json.loads(evidence.read_text())
    b.check_tools(prior['tools'])
    require(sha(b.B / 'maya-ds4') == BASE, 'Selected original executable changed')
    jobs, comp = plans(b)
    inputs = {n: pin for n, pin in prior['input_sha256'].items()
              if not Path(n).is_relative_to(P)}
    b.check_files(inputs)
    admission()
    PREP.mkdir()
    c.emit_new(PREP / 'plan.json', {'commands': jobs, 'compile_plan_UNRUN': comp})
    children = []
    for name, args in jobs:
        admission(); b.check_files(q['files']); b.check_files(inputs); b.check_tools(prior['tools'])
        children.append(b.run_child(args, name, PREP, admission))
        admission()
        dep = (PREP / 'selected-relink.link.d') if name == 'selected-relink' else PREP / (
            'gguf.headers.d' if name == 'deps-gguf' else 'test.headers.d')
        if name == 'selected-relink':
            require(sha(PREP / 'selected-relink') == BASE, 'Original control relink differs')
        found = b.dependencies(dep.read_text(), relative_to=b.B if name == 'selected-relink' else None)
        current = {n: sha(n) for n in found}
        require(all(n not in inputs or inputs[n] == pin for n, pin in current.items()), 'Dependency changed')
        inputs.update(current)
        c.emit_new(PREP / (name + '-inputs.json'), current)
    admission(); b.check_files(inputs); b.check_tools(prior['tools']); b.check_files(q['files'])
    value = {'passed': True, 'status': 'PREPARED_STOP_FOR_ACTUAL_INPUT_REVIEW',
             'original_relink_sha256': sha(PREP / 'selected-relink'), 'input_sha256': inputs,
             'tools': prior['tools'], 'children': children, 'CUDA_compilation': False, 'GPU_execution': False}
    c.emit_new(PREP / 'receipt.json', value)
    return value


def compile_candidate(c, b, q, admission):
    c.fresh(OUT)
    value = json.loads((PREP / 'receipt.json').read_text())
    require(value.get('passed') is True and value.get('status') == 'PREPARED_STOP_FOR_ACTUAL_INPUT_REVIEW'
            and value['original_relink_sha256'] == BASE and sha(PREP / 'selected-relink') == BASE,
            'Actual control relink missing')
    require(all(q['files'].get(n) == pin for n, pin in value['input_sha256'].items()), 'Unpinned actual input')
    _, jobs = plans(b)
    produced = {}
    def check():
        admission(); b.check_files(q['files']); b.check_files(value['input_sha256'])
        b.check_tools(value['tools']); b.check_files(produced)
    check(); OUT.mkdir(); c.emit_new(OUT / 'plan.json', {'commands': jobs})
    children = []
    for name, args in jobs:
        check(); children.append(b.run_child(args, name, OUT, admission)); admission()
        artifact = Path(args[args.index('-o') + 1])
        require(artifact.is_file() and not artifact.is_symlink(), 'Fresh output absent')
        produced[str(artifact)] = sha(artifact)
        if name.endswith('-link'):
            actual = b.dependencies(Path(str(artifact) + '.link.d').read_text(), relative_to=b.B)
            unknown = set(actual) - set(value['input_sha256']) - set(produced)
            c.emit_new(OUT / (name + '-inputs.json'), {'files': {n: sha(n) for n in actual},
                                                    'unknown': sorted(unknown)})
            require(not unknown, 'New actual input; HOLD')
        check()
    result = {'passed': True, 'status': 'COMPILED_STOP_FOR_KERNEL_QUALIFICATION',
              'outputs': produced, 'children': children, 'GPU_execution': False,
              'model_execution': False, 'production_changed': False}
    c.emit_new(OUT / 'receipt.json', result)
    return result


def main(mode, digest):
    require(mode in ('prepare', 'compile') and sys.platform == 'linux' and HERE == EXPECTED,
            'Exact Ubuntu stage only')
    c, b, runtime, a, host, binding = support()
    state = c.guard(runtime, host, binding)
    q = verify_q(c, mode, digest)
    c.fresh(PREP if mode == 'prepare' else OUT)
    c.guard(runtime, host, binding)
    record = {'controller_pid': os.getpid(), 'mode': 'q8-sharing-' + mode,
              'start_binding': binding}
    # Reuse the qualified CAS writer and close partial claims in finally too.
    cas_path = P / 'prose-speed-v1/prose_measure.py'
    require(sha(cas_path) == CAS_SHA, 'State custody helper changed before import')
    previous = sys.modules.get('prose_measure')
    require(previous is None or Path(previous.__file__).resolve() == cas_path, 'Foreign CAS module')
    sys.path.insert(0, str(cas_path.parent))
    m = importlib.import_module('prose_measure')
    require(Path(m.__file__).resolve() == cas_path and sha(cas_path) == CAS_SHA,
            'State custody helper origin/content differs')
    before = (E / 'STATE.json').read_bytes()
    require(json.loads(before) == state, 'Coordination changed before claim')
    primary = None
    def admission():
        c.guard(runtime, host, binding, record)
        require(sha(HERE / (mode + '-qualification.json')) == digest, 'Qualification changed')
    try:
        m.cas_state(E / 'STATE.json', before, dict(state, active_cpu_build=record))
        return (prepare if mode == 'prepare' else compile_candidate)(c, b, q, admission)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            raw = (E / 'STATE.json').read_bytes(); current = json.loads(raw)
            require(current.get('active_cpu_build') == record, 'Own CPU reservation changed; foreign preserved')
            m.cas_state(E / 'STATE.json', raw, dict(current, active_cpu_build=False))
            require(not json.loads((E / 'STATE.json').read_text()).get('active_cpu_build'), 'CPU release absent')
        except BaseException as exc:
            if primary is None:
                primary = exc
            else:
                primary.add_note('Owned CPU release fault: ' + repr(exc))
        try:
            host.guard_binding()
        except BaseException as exc:
            if primary is None:
                primary = exc
            else:
                primary.add_note('Owned CPU owner fault: ' + repr(exc))
        if primary is not None:
            raise primary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'compile'))
    parser.add_argument('--qualification-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(main(args.mode, args.qualification_sha256)))
