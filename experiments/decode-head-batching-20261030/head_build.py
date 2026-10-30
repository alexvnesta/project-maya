"""Fresh, separately qualified head batching prepare/compile. Never run a native.

Only ds4_model.cu is replaced in the selected native link. A control relink must
reproduce selected92 before CUDA compilation. Original objects remain read-only.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import shlex

HERE = Path(__file__).resolve().parent
P = HERE.parent
E = Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025')
EXPECTED = E / 'decode-optimization-20261028/head-batching-v1'
BASE = '92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
SUPPORT_SHA = 'e8dcd79bd3a80cba931885149438f107d6d840693e508f738fd616fd6885f9ff'
CAS_SHA = '8d10d003bbbd7ffbb87251bacdf53d91af9f074151d34f06c957fa179f3108cf'
IMPORT_Q_SHA = '6eb179b8b7edb7a87133c4e24bd99dc2f35863cfe6ef56f8385590bf50c6315b'
PREP = HERE / 'prepare-FIRST'
OUT = HERE / 'build-FIRST'

RECIPE = HERE / 'ACTUAL_MODEL_COMPILER_RECIPE_FIRST.json'
RECIPE_SHA = '6d7f0cba7b5a943e72e5582e4bfcac5b2f7632fb021f3f7cf57626391f3ff24a'
SELECTED_SOURCE = E.parent / 'maya-ablate469-v2'
SELECTED_MODEL_SHA = 'dfe326d6a60d77354c8c92fb14ec423a92afff76b91f0810104f0a54a51a6350'
SELECTED_MODEL_OBJECT_SHA = '9ebe2978ebcd97c1757670984cfd2a7985a102ff153018c95cb79c515fe7888c'
CORRECTION = E / 'ablation-pr469-v2/source-correction.json'
CORRECTION_SHA = 'afe2e805490202b4be4d13dc2efa67a4e90329208fa728eb21d0bfc34e466ec7'
TEMPLATE = P / 'q8-sharing-v1/build.py'
TEMPLATE_SHA = '6745bb5ac58d33e391b5cdf3557fef38e87a9163de75539258d0dc3d2100fd79'
CANDIDATE_NAMES = ('src/ds4/ds4_model.cu', 'src/ds4/ds4_head_batch_policy.hpp',
                   'tests/head_batch_policy_test.cpp', 'tests/head_batch_check.cu')


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


def compiler_recipe(b):
    """Expand only the actual selected MODEL recipe, not the old IQ template."""
    require(sha(RECIPE) == RECIPE_SHA, 'Actual model recipe receipt changed')
    receipt = json.loads(RECIPE.read_text())
    target = b.B / 'CMakeFiles/maya-ds4.dir'
    expected = [target / n for n in ('build.make', 'flags.make', 'includes_CUDA.rsp', 'link.txt')]
    expected += [b.B / 'CMakeFiles/ds4_gguf_test.dir/link.txt']
    require(set(receipt['input_sha256']) == {str(p) for p in expected}, 'Recipe input set differs')
    require(all(sha(p) == receipt['input_sha256'][str(p)] for p in expected), 'Actual recipe input changed')
    flags = (target / 'flags.make').read_text()
    require(flags == receipt['flags_make'] and
            (target / 'includes_CUDA.rsp').read_text() == receipt['includes_CUDA_rsp'], 'Recipe text differs')
    def variable(name):
        values = [line.split('=', 1)[1].strip() for line in flags.splitlines() if line.startswith(name + ' =')]
        require(len(values) == 1, 'Missing/duplicate model compiler variable')
        return shlex.split(values[0])
    defines, options = variable('CUDA_DEFINES'), variable('CUDA_FLAGS')
    require(defines == ['-DSTRATA_NATIVE_EXPERTS=1', '-DSTRATA_VERSION="0.1.27"'], 'Selected model defines differ')
    require(options == ['-O3', '-DNDEBUG', '-std=c++20',
                       '--generate-code=arch=compute_80,code=[compute_80,sm_80]'], 'Selected model arithmetic/SM flags differ')
    require(variable('CUDA_INCLUDES') == ['--options-file', 'CMakeFiles/maya-ds4.dir/includes_CUDA.rsp'],
            'Selected include response file differs')
    obj = 'CMakeFiles/maya-ds4.dir/src/ds4/ds4_model.cu.o'
    command = ('/usr/local/cuda/bin/nvcc -forward-unknown-to-host-compiler $(CUDA_DEFINES) '
               '$(CUDA_INCLUDES) $(CUDA_FLAGS) -MD -MT ' + obj + ' -MF ' + obj + '.d -x cu -c ' +
               str(b.S / 'src/ds4/ds4_model.cu') + ' -o ' + obj)
    actual = [line.strip() for line in (target / 'build.make').read_text().splitlines()
              if line.strip().startswith('/usr/local/cuda/bin/nvcc ') and (' -o ' + obj) in line]
    require(actual == [command] and command in [v.strip() for v in receipt['model_recipe_lines']],
            'Exact selected MODEL compile command absent or changed')
    # The extra includes locate unchanged sibling headers and our one new header.
    # Threads1/ptxas reporting are inherited supervision/diagnostic flags only.
    return ['/usr/local/cuda/bin/nvcc', '-forward-unknown-to-host-compiler'] + defines + [
        '-I' + str(HERE / 'candidate/src/ds4'), '-I' + str(b.S / 'src/ds4'),
        '--options-file', str(target / 'includes_CUDA.rsp')] + options + [
        '--threads', '1', '--ptxas-options=-v', '-x', 'cu', '-c']


def plans(b):
    common = compiler_recipe(b)
    native = (b.B / 'CMakeFiles/maya-ds4.dir/link.txt').read_text()
    fixture = (b.B / 'CMakeFiles/ds4_gguf_test.dir/link.txt').read_text()
    old = 'CMakeFiles/maya-ds4.dir/src/ds4/ds4_model.cu.o'
    source = HERE / 'candidate/src/ds4/ds4_model.cu'
    check = HERE / 'candidate/tests/head_batch_check.cu'
    def compile_command(src, target, deps=False):
        args = [v for v in common if not (deps and v == '--ptxas-options=-v')]
        if deps: args[args.index('-c')] = '-M'
        return args + [str(src), '-o', str(target)]
    original_objects = [v for v in shlex.split(native) if v.endswith('.o')]
    require(original_objects.count(old) == 1 and len(set(original_objects)) == len(original_objects),
            'Selected native MODEL object missing/duplicate')
    test_objects = [v for v in shlex.split(fixture) if v.endswith('.o')]
    test_main = 'CMakeFiles/ds4_gguf_test.dir/tests/ds4_gguf_test.cu.o'
    require(test_objects.count(test_main) == 1 and len(set(test_objects)) == len(test_objects),
            'Original fixture entry missing/duplicate')
    replacements = {}
    for value in test_objects:
        if value == test_main: replacements[value] = OUT / 'head_batch_check.cu.o'
        else:
            mapped = value.replace('ds4_gguf_test.dir/', 'maya-ds4.dir/')
            require(mapped in original_objects, 'Foreign fixture object outside selected native')
            replacements[value] = mapped
    prep = [('selected-relink', b.link_plan(native, 'maya-ds4', PREP / 'selected-relink', {})),
            ('deps-model', compile_command(source, PREP / 'model.headers.d', True)),
            ('deps-test', compile_command(check, PREP / 'test.headers.d', True))]
    comp = [('compile-model', compile_command(source, OUT / 'ds4_model.cu.o')),
            ('compile-test', compile_command(check, OUT / 'head_batch_check.cu.o')),
            ('candidate-link', b.link_plan(native, 'maya-ds4', OUT / 'maya-ds4-candidate',
                                         {old: OUT / 'ds4_model.cu.o'})),
            ('test-link', b.link_plan(fixture, 'ds4_gguf_test', OUT / 'head_batch_check', replacements))]
    for name, args in prep + comp:
        require(args[0] in ('/usr/bin/c++', '/usr/local/cuda/bin/nvcc') and args.count('-o') == 1,
                'Unexpected compiler command')
        output = Path(args[args.index('-o') + 1])
        require(output.parent == (PREP if name in ('selected-relink', 'deps-model', 'deps-test') else OUT),
                'Output escaped owned stage')
        require('--use_fast_math' not in args, 'Arithmetic compiler flag changed')
        if args[0].endswith('/nvcc'):
            require(args[args.index('--threads') + 1] == '1' and
                    '--generate-code=arch=compute_80,code=[compute_80,sm_80]' in args,
                    'CUDA architecture/concurrency changed')
    return prep, comp


def reconstruct_selected(candidate):
    """Reverse exactly the reviewed include and head-loop delta, no source execution."""
    include = '#include "ds4_head_batch_policy.hpp"\n'
    require(candidate.count(include) == 1, 'Head policy include changed')
    candidate = candidate.replace(include, '', 1)
    start = candidate.index('        // GGUF-only opt-in. The shared helper')
    end = candidate.index('        if (nm == 1 || !gather) return true;', start)
    old = ('        // (an EXL3 head: as many activations at a time as its split-K partials fit the scratch - 8 for a shared head, 4\n'
           "        // for a whole one, each pass reading the whole share; a GGUF's: 4 at a time, as before)\n"
           '        const int per = d.head.fmt != 0 ? 4 : std::max(1, x3::mv_cols(d.head));\n'
           '        for (int c = 0; c < rows; c += per)\n'
           '            if (!mv(d, {job(d.head, xn + (size_t) c * D, out + (size_t) c * ld, std::min(per, rows - c), D, ld)}, err))\n'
           '                return false;\n')
    restored = candidate[:start] + old + candidate[end:]
    require(hashlib.sha256(restored.encode()).hexdigest() == SELECTED_MODEL_SHA,
            'Head candidate does not reconstruct exact selected model source')
    return restored


def provenance(q):
    require(sha(RECIPE) == RECIPE_SHA and q['files'].get(str(RECIPE)) == RECIPE_SHA, 'Recipe receipt unpinned')
    recipe = json.loads(RECIPE.read_text())
    require(all(q['files'].get(n) == pin for n, pin in recipe['input_sha256'].items()), 'Original compiler recipe unpinned')
    require(sha(CORRECTION) == CORRECTION_SHA and q['files'].get(str(CORRECTION)) == CORRECTION_SHA,
            'Selected nine-file source provenance absent')
    source = json.loads(CORRECTION.read_text())['files']
    require(len(source) == 9 and source.get('src/ds4/ds4_model.cu') == SELECTED_MODEL_SHA,
            'Selected source correction inventory changed')
    require(all(q['files'].get(str(SELECTED_SOURCE / n)) == pin for n, pin in source.items()),
            'Selected original ablation/runtime source missing')
    model_object = E.parent / 'maya-build-sm80-ablate469-v2/CMakeFiles/maya-ds4.dir/src/ds4/ds4_model.cu.o'
    require(q['files'].get(str(model_object)) == SELECTED_MODEL_OBJECT_SHA, 'Selected original model object absent')
    require(q['files'].get(str(TEMPLATE)) == TEMPLATE_SHA, 'Qualified build template unpinned')
    reconstruct_selected((HERE / 'candidate/src/ds4/ds4_model.cu').read_text())


def verify_q(c, mode, digest):
    path = HERE / (mode + '-qualification.json')
    require(sha(path) == digest and not path.is_symlink(), 'Qualification changed')
    q = json.loads(path.read_text())
    require(q.get('mode') == mode and q.get('manual_source_reviewed') is True
            and q.get('CPU_both_hosts_passed') is True, 'Missing exact source/CPU qualification')
    required = q['source_sha256']
    require(set(required) == {'head_build.py', 'test_head_build.py', 'qualify_build_cpu.py'} |
            {'candidate/' + n for n in CANDIDATE_NAMES}, 'Exact seven source files absent/extra')
    require(required == {n: sha(HERE / n) for n in required}, 'New source differs')
    require(all(q['files'].get(str(HERE / n)) == pin for n, pin in required.items()),
            'Source not pinned in input closure')
    manifest_path = HERE / 'candidate-files.json'
    require(q['files'].get(str(manifest_path)) == sha(manifest_path), 'Candidate manifest unpinned')
    manifest = json.loads(manifest_path.read_text())
    require(type(manifest.get('files')) is dict and set(manifest['files']) == set(CANDIDATE_NAMES),
            'Exact candidate inventory absent')
    for n, pin in manifest['files'].items():
        rel = Path(n)
        require(not rel.is_absolute() and '..' not in rel.parts and len(rel.parts) > 1
                and required.get('candidate/' + n) == pin and sha(HERE / 'candidate' / rel) == pin, 'Candidate source absent/different')
    require(q.get('policy_test_ids') == manifest['policy_test_ids']
            and len(q['policy_test_ids']) == 91, 'Exact new policy IDs absent')
    provenance(q)
    for name, pin in q['source_input_sha256'].items():
        rel = Path(name)
        require(not rel.is_absolute() and '..' not in rel.parts and
                q['files'].get(str(E / rel)) == pin, 'CPU input map not bound in qualification')
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
            'model.headers.d' if name == 'deps-model' else 'test.headers.d')
        if name == 'selected-relink':
            require(sha(PREP / 'selected-relink') == BASE, 'Original control relink differs')
        found = b.dependencies(dep.read_text(), relative_to=b.B if name == 'selected-relink' else None)
        require(all(n in inputs or not n.endswith(('.o', '.a', '.so')) for n in found),
                'Foreign linked object/library outside selected input baseline')
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
    record = {'controller_pid': os.getpid(), 'mode': 'head-batching-' + mode,
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
