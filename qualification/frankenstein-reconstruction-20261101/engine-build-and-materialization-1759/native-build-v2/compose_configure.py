"""Metadata only: new source/CPU closure on the unchanged qualified toolchain."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DC = HERE.parents[1]
Q = HERE.parent
sys.path.insert(0, str(DC / 'maya-s-comparison-v1'))
import acquire


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''): h.update(block)
    return h.hexdigest()


def main():
    gate = acquire.SelectedGate()  # Before metadata or heavy CPU; no service actions.
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    os.nice(15)
    oldroot = Q / 'placement-native-build-v1'
    old = json.loads((oldroot / 'configure-r4-qualification.json').read_text())
    excluded = (str(oldroot) + '/', str(Q / 'placement-engine-v1') + '/')
    files = {n: pin for n, pin in old['files'].items() if not n.startswith(excluded)}
    for n, pin in files.items():
        p = Path(n)
        assert p.resolve() == p and not p.is_symlink() and sha(p) == pin, 'Unchanged tool/dependency drift'
    for alias, resolved in old['tool_aliases'].items():
        assert str(Path(alias).resolve()) == resolved and resolved in files
    # Only the explicitly owned source/evidence directories are inventoried.
    for tree in [HERE / 'source-FIRST', HERE / 'CPU-BUILD-R4-FIRST-darwin',
                 HERE / 'CPU-BUILD-R4-FIRST-linux', Q / 'native-engine-v2']:
        for p in tree.rglob('*'):
            assert not p.is_symlink()
            if p.is_file(): files[str(p)] = sha(p)
    names = ['build_current.py', 'test_build_current.py', 'run_build_cpu.py',
             'CMakeLists.reviewed.txt', 'SOURCE_MANIFEST_FIRST.json', 'ROOT_BUILD_R4_SOURCE_REVIEW.json']
    for n in names: files[str(HERE / n)] = sha(HERE / n)
    review = json.loads((HERE / 'ROOT_BUILD_R4_SOURCE_REVIEW.json').read_text())
    cpu = {h: json.loads((HERE / ('CPU-BUILD-R4-FIRST-' + h) / 'receipt.json').read_text())
           for h in ('darwin', 'linux')}
    for proof in cpu.values():
        assert proof['passed'] and proof['controls'] == 34 and proof['source_sha256'] == review['source_sha256']
        assert proof['test_ids'] == review['test_ids']
    native = {h: json.loads((Q / 'native-engine-v2' / ('CPU-FIRST-' + h + '.json')).read_text())
              for h in ('mac', 'ubuntu')}
    assert all(v['passed'] and v['controls'] == 9 and v['returncode'] == 0 for v in native.values())
    assert native['mac']['test_ids'] == native['ubuntu']['test_ids']
    assert native['mac']['input_sha256'] == native['ubuntu']['input_sha256']
    spec = importlib.util.spec_from_file_location('new_native_build', HERE / 'build_current.py')
    b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
    b.verify_project_sources(HERE / 'source-FIRST')
    b.verify_native_source(HERE / 'source-FIRST', json.loads((HERE / 'SOURCE_MANIFEST_FIRST.json').read_text()))
    gate()
    q = {'stage': 'configure', 'upstream': b.UPSTREAM, 'root_manual_source_tests_read': True,
         'CPU_both_hosts_passed': True, 'source_sha256': review['source_sha256'],
         'test_ids': review['test_ids'], 'CPU': cpu, 'native_routing_CPU': native,
         'files': files, 'tool_aliases': old['tool_aliases'], 'selected_binding': gate.host.start_binding,
         'command': b.plan('configure'), 'scope': 'New static original-MXFP4 CPU path with sensitive-layer prompt offload and startup arithmetic check. Source/CPU configure admission only; no native execution/model/default claim.',
         'unchanged_dependency_qualification_sha256': sha(oldroot / 'configure-r4-qualification.json'),
         'toolchain_limitations': old['toolchain_limitations']}
    path = HERE / 'configure-r4-qualification.json'
    with path.open('x') as f: json.dump(q, f, indent=2); f.write('\n')
    print(json.dumps({'qualification_sha256': sha(path), 'files': len(files),
                      'binding': gate.host.start_binding, 'CPU_limit': [30, 30], 'nice': os.getpriority(os.PRIO_PROCESS, 0)}))


if __name__ == '__main__': main()
