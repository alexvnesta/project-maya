"""Pin actual CMake closure and compare commands with the qualified toolchain."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
Q = HERE.parent
DC = HERE.parents[1]
sys.path.insert(0, str(DC / 'maya-s-comparison-v1'))
import acquire


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''): h.update(block)
    return h.hexdigest()


def main():
    gate = acquire.SelectedGate()
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20)); os.nice(15)
    q = json.loads((HERE / 'configure-r4-qualification.json').read_text())
    assert q['selected_binding'] == gate.host.start_binding
    s = importlib.util.spec_from_file_location('native_compile_meta', HERE / 'build_current.py')
    b = importlib.util.module_from_spec(s); s.loader.exec_module(b)
    for name, pin in q['files'].items(): assert sha(name) == pin, 'Configure input drift'
    oldroot = Q / 'placement-native-build-v1'
    old = json.loads((oldroot / 'compile-r4-qualification.json').read_text())
    build, previous = HERE / 'native-build-FIRST', oldroot / 'native-build-FIRST'
    old_commands = (previous / 'compile_commands.json').read_text()
    normalized = old_commands.replace(str(oldroot), str(HERE)).replace('6ecbd3c+s2plan-r1', '6ecbd3c+s2native-r2')
    commands = json.loads((build / 'compile_commands.json').read_text())
    assert json.loads(normalized) == commands, 'Compile commands differ beyond exact source path and declared build ID'
    generated = []
    copied = 0
    prefix = str(previous) + '/'
    for name, pin in old['files'].items():
        if not name.startswith(prefix): continue
        relative = Path(name).relative_to(previous); path = build / relative
        assert path.is_file() and not path.is_symlink(), 'Missing actual generated compile input'
        if str(relative).startswith('strata-ggml-cuda/'):
            assert sha(path) == pin, 'Previously qualified copied CUDA source changed'
            copied += 1
        q['files'][str(path)] = sha(path); generated.append(str(relative))
    assert len(commands) == 256 and len(generated) == 548 and copied == 284
    for name in ('child.json', 'supervision.json', 'result.json', 'observed.json',
                 'attempt.json', 'owned-children.jsonl', 'stdout.txt', 'stderr.txt'):
        p = HERE / 'configure-r4-FIRST' / name
        assert p.is_file(); q['files'][str(p)] = sha(p)
    q['files'][str(HERE / 'configure-r4-qualification.json')] = sha(HERE / 'configure-r4-qualification.json')
    q.update(stage='compile', command=b.plan('compile'), actual_configure_manually_reviewed=True,
             configure_qualification_sha256=sha(HERE / 'configure-r4-qualification.json'),
             generated_build_inputs=len(generated), compile_commands=len(commands),
             copied_cuda_unchanged_files=copied,
             generated_command_attestation='Exact previous command list after only old-to-new source/build paths and explicit s2native-r2 build ID; copied284CUDA sources byteidentical',
             scope='New selective-native CPU Maya build only, with exact qualified toolkit/CPU source and prospective arithmetic check. No model/GPU execution or activation.')
    b.configure_closed(q); gate()
    path = HERE / 'compile-r4-qualification.json'
    with path.open('x') as f: json.dump(q, f, indent=2); f.write('\n')
    print(json.dumps({'qualification_sha256': sha(path), 'files': len(q['files']),
                      'generated': len(generated), 'copied_CUDA_unchanged': copied}))


if __name__ == '__main__': main()
