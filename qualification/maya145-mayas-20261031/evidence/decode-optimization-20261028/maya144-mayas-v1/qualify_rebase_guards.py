"""Bounded first CPU proof of the rebased fork's two retained native guards."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
DRIVER = HERE.parent / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
NAMES = ['src/ds4/ds4_model.cu', 'src/ds4/ds4_ablate.hpp',
         'include/strata/artifact/gguf_reader.hpp', 'tools/extract_prompt_copy_check.py',
         'tests/ds4_ablate_test.cpp', 'tests/ds4_prompt_copy_check_test.cpp']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def driver():
    if sha(DRIVER) != DRIVER_SHA:
        raise ValueError('Bounded supervisor source changed')
    spec = importlib.util.spec_from_file_location('bounded_guard_supervisor', DRIVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def source_map(root):
    return {name: sha(root / name) for name in NAMES} | {'qualify_rebase_guards.py': sha(__file__)}


def load_extractor(root):
    spec = importlib.util.spec_from_file_location('actual_copy_guard_extractor', root / NAMES[3])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def child(a, d, folder):
    observed = d.observed()
    d.bounds(observed, os.getpid(), a.parent)
    review = json.loads((HERE / 'ROOT_GUARD_SOURCE_REVIEW.json').read_text())
    before = source_map(a.root)
    if before != review['source_sha256'] or review['entire_changed_source_tests_read'] is not True:
        raise ValueError('Manual reviewed source map changed')
    job = a.child
    if job == 'extract':
        ex = load_extractor(a.root)
        source = (a.root / NAMES[0]).read_text()
        ex.check_startup(source)
        # Negative integration controls: late check, duplicate check, missing pin and ambiguous method.
        for bad in (source.replace('        tune_lane();', '        tune_lane();\n        if (!prompt_copy_check(err)) return false;'),
                    source.replace('        if (cp_pin_last()) cp_pin();', ''),
                    source.replace('        if (cp_pin_last()) cp_pin();', '        tune_lane();')):
            try:
                ex.check_startup(bad)
            except ValueError:
                pass
            else:
                raise ValueError('Startup mutation escaped')
        try:
            ex.extract(source + '\n    bool prompt_copy_check(')
        except ValueError:
            pass
        else:
            raise ValueError('Ambiguous method escaped')
        fragment = ex.extract(source)
        (folder.parent / 'ds4_prompt_copy_check.inc').open('x').write(fragment)
        print('PASS startup-order-and-four-negative-controls', flush=True)
    elif job.startswith('compile-'):
        name = job.removeprefix('compile-')
        compiler = ('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang'
                    if sys.platform == 'darwin' else '/usr/bin/x86_64-linux-gnu-g++-15')
        discovery = HERE.parent / 'unsloth-v31-runtime-v1' / (
            'HOST_TOOL_DARWIN_DISCOVERY.json' if sys.platform == 'darwin' else 'HOST_TOOL_LINUX_DISCOVERY_R2.json')
        tools = json.loads(discovery.read_text())['files']
        if sha(compiler) != tools[compiler]:
            raise ValueError('Compiler changed')
        argv = [compiler]
        if sys.platform == 'darwin':
            argv += ['--driver-mode=g++', '-isysroot', '/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk']
        argv += ['-std=c++17', '-O2', '-fno-fast-math', '-ffp-contract=off', '-I', str(a.root / 'include'),
                 '-I', str(folder.parent), '-MD', '-MF', str(folder / 'headers.d'),
                 str(a.root / ('tests/ds4_' + name + '_test.cpp')), '-o', str(folder.parent / name)]
        print(json.dumps({'compiler_argv': argv, 'compiler_sha256': sha(compiler)}), flush=True)
        subprocess.run(argv, check=True, timeout=75)
        print(json.dumps({'executable_sha256': sha(folder.parent / name)}), flush=True)
    else:
        name = job.removeprefix('run-')
        env = dict(os.environ)
        env['TMPDIR'] = str(folder)
        subprocess.run([str(folder.parent / name)], check=True, timeout=75, env=env)
    if source_map(a.root) != before or d.observed() != observed:
        raise ValueError('Source or child resource drift')
    (folder / 'proof.json').open('x').write(json.dumps({'job': job, 'source_sha256': before,
                                                     'observed': observed, 'passed': True}, indent=2) + '\n')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--child', choices=['extract', 'compile-ablate', 'compile-prompt_copy_check',
                                      'run-ablate', 'run-prompt_copy_check'])
    ap.add_argument('--parent', type=int)
    a = ap.parse_args()
    if not a.root.is_absolute() or a.root.resolve() != a.root:
        raise ValueError('Exact absolute source tree required')
    d = driver()
    base = HERE / ('CPU-GUARDS-FIRST-' + sys.platform)
    if a.child:
        return child(a, d, base / a.child)
    base.mkdir()
    for job in ['extract', 'compile-ablate', 'compile-prompt_copy_check', 'run-ablate', 'run-prompt_copy_check']:
        folder = base / job
        folder.mkdir()
        result = d.supervise([sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--root', str(a.root),
                              '--child', job, '--parent', str(os.getpid())], folder)
        print(json.dumps({'job': job, **result}), flush=True)
        if result['returncode'] != 0 or result['error'] or result['cleanup']:
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
