"""One metadata-only pack construction inside an explicitly bounded CPU child.

No inference, service command, package change, weight copy, or payload rehash.
The completed acquisition and its shared lock provide immutable asset custody.
"""
import argparse
import ast
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import time

import pack_guard as g

HERE = Path(__file__).resolve().parent
Q = HERE.parent
TARGET = g.TARGET
E = Q.parents[1]
ACQ = Q / 'acquisition-authorized-v2'
ACQ_SHA = '6a399f4eec7b9cb23b7ff7aa03d60deb490787825ae92e43ccde8d40065885b5'
ACQ_Q_SHA = '3f89fe089d629bb65b5c517908ae76a731b9020fb0a8cb02a1b1ef58472596b0'
CHILD_ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
             'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1'}


def emit(path, value):
    g.canonical(path); g.require(not path.exists(), 'Preserve first metadata attempt')
    with path.open('x') as f: f.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def checked_files(files, *, allowed_external=None):
    g.require(type(files) is dict and files, 'Exact source/input map required')
    for name, pin in files.items():
        path = g.canonical(Path(name))
        g.require((path.is_relative_to(E) or (allowed_external or {}).get(name) == pin)
                  and g.sha(path, limit=2**30 if (allowed_external or {}).get(name) == pin else g.MAX_METADATA) == pin,
                  'Source/input changed: ' + name)


def acquisition_inventory():
    path = ACQ / 'acquisition-qualification.json'
    g.require(g.sha(path) == ACQ_Q_SHA, 'Exact inherited acquisition inventory required')
    return g.read_json(path)['files']


def acquisition_module():
    # All transitive inputs are checked by the outer construction qualification
    # before importing serving support. No old admission is borrowed for a model.
    g.require(g.sha(ACQ / 'acquire.py') == ACQ_SHA
              and g.sha(ACQ / 'acquisition-qualification.json') == ACQ_Q_SHA, 'Acquisition source/qualification changed')
    q = g.read_json(ACQ / 'acquisition-qualification.json')
    checked_files(q['files'], allowed_external=acquisition_inventory())
    spec = importlib.util.spec_from_file_location('ms_acquisition_readonly_gate', ACQ / 'acquire.py')
    a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
    a.qualification(ACQ / 'acquisition-qualification.json', ACQ_Q_SHA)
    return a


def completed_receipt(path):
    path = g.canonical(Path(path))
    g.require(path.parent == ACQ and path.name.startswith('acquisition-attempt-') and path.suffix == '.json',
              'Immutable terminal acquisition attempt required')
    receipt = g.read_json(path); g.receipt_contract(receipt, g.manifest(), Q / 'assets')
    return receipt


def contract(path):
    completed_receipt(path)
    vision = E / 'vision-assets-1017'
    return {'profile': g.PROFILE, 'assets_root': str(Q / 'assets'), 'output': str(TARGET),
            'vision_dir': str(vision), 'vision_pins': {str(vision / n): pin for n, pin in g.VISION_PINS.items()},
            'selected_vision_bin_sha256': g.VISION_PINS['vision.bin'], 'acquisition_receipt': str(path),
            'acquisition_receipt_sha256': g.sha(Path(path)),
            'asset_stats': g.path_inventory(Q / 'assets', g.manifest()),
            'vision_stats': {str(vision / n): list(g.regular(vision / n)) for n in g.VISION_PINS}}


def qualified(path, pin):
    g.require(g.sha(path) == pin, 'Explicit metadata construction qualification changed')
    q = g.read_json(path); checked_files(q['files'], allowed_external=acquisition_inventory())
    g.require(q.get('root_manual_review') is True and q.get('astra_manual_review') is True
              and q.get('pack_guard_both_physical_hosts_passed') is True
              and q.get('construct_controller_both_physical_hosts_passed') is True,
              'Exact source/CPU construction qualification required')
    specs = {'pack_guard': ('pack_guard.py', 'test_pack_guard.py', 'run_cpu.py'),
             'construct_controller': ('pack_guard.py', 'construct_pack.py', 'test_construct_pack.py', 'construct_cpu.py')}
    g.require(len(q['CPU_groups']) == 2 and {v['name'] for v in q['CPU_groups']} == set(specs),
              'Distinct unchanged pack guard and new controller proofs required')
    for group in q['CPU_groups']:
        sources = {n: g.sha(HERE / n) for n in specs[group['name']]}
        test_name = 'test_pack_guard' if group['name'] == 'pack_guard' else 'test_construct_pack'
        tree = ast.parse((HERE / (test_name + '.py')).read_text())
        ids = sorted(test_name + '.' + cls.name + '.' + f.name for cls in tree.body if isinstance(cls, ast.ClassDef)
                     for f in cls.body if isinstance(f, ast.FunctionDef) and f.name.startswith('test_'))
        g.require(group['source_sha256'] == sources and group['test_ids'] == ids,
                  'CPU group not tied to actual current sources/IDs')
        needed = {str(HERE / n): pin for n, pin in sources.items()}
        needed.update({str(E / n): pin for n, pin in group['input_sha256'].items()})
        g.require(all(q['files'].get(n) == pin for n, pin in needed.items()), 'CPU sources/inputs omitted from immutable map')
        g.require(set(group['proofs']) == {'darwin', 'linux'} and group['test_ids']
                  and len(set(group['test_ids'])) == len(group['test_ids']), 'Both physical exact test lists required')
        for label, paths in group['proofs'].items():
            g.require(set(paths) == {'receipt', 'child', 'log'} and all(n in q['files'] for n in paths.values()),
                      'Exact raw CPU receipt/child/log pins required')
            receipt = g.read_json(Path(paths['receipt'])); child = g.read_json(Path(paths['child']))
            g.require(receipt.get('passed') is True and receipt.get('controls') == len(group['test_ids'])
                      and receipt.get('test_ids') == group['test_ids']
                      and receipt.get('source_sha256') == group['source_sha256']
                      and receipt.get('input_sha256') == group['input_sha256'], 'Changed/missing exact CPU proof')
            g.require(type(child.get('returncode')) is int and child['returncode'] == 0
                      and child.get('error') is None and child.get('cleanup_errors') == []
                      and child.get('CPU_limit_seconds') == 30 and child.get('wall_limit_seconds') == 90
                      and child.get('nice_increment') == 15 and receipt.get('CPU_seconds') == [30, 30]
                      and type(receipt.get('nice')) is int and 15 <= receipt['nice'] <= 19
                      and receipt.get('environment') == child.get('environment') == CHILD_ENV
                      and receipt.get('Linux_AS_bytes') == ([512 * 2**20] * 2 if label == 'linux' else None),
                      'Actual bounded CPU child proof required')
    return q


def gone(pid):
    try: os.killpg(pid, 0)
    except ProcessLookupError: return True
    return False


def cleanup(proc):
    errors = []
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if gone(proc.pid): break
        try: os.killpg(proc.pid, sig)
        except ProcessLookupError: pass
        except BaseException as exc: errors.append(repr(exc))
        end = time.monotonic() + 2
        while not gone(proc.pid) and time.monotonic() < end:
            proc.poll(); time.sleep(.02)
    if not gone(proc.pid): errors.append('Owned process group survived')
    try: proc.wait(timeout=1)
    except BaseException as exc: errors.append(repr(exc))
    return errors


def supervise(command, out, env):
    def limits():
        os.nice(15); resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20,) * 2)
    began = time.monotonic(); result = {'command': command, 'returncode': None, 'error': None, 'cleanup_errors': [],
        'CPU_limit_seconds': 30, 'wall_limit_seconds': 90, 'nice_increment': 15,
        'Linux_AS_bytes': 512 * 2**20, 'environment': CHILD_ENV, 'GPU_or_service_actions': 0}
    proc = None
    try:
        with (out / 'child.log').open('x') as log:
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                    env=env, preexec_fn=limits, start_new_session=True)
            result['pid'] = proc.pid; result['returncode'] = proc.wait(timeout=90)
    except BaseException as exc: result['error'] = repr(exc)
    finally:
        if proc is not None:
            result['cleanup_errors'] = cleanup(proc)
            result['returncode'] = proc.poll()
        result['seconds'] = time.monotonic() - began; emit(out / 'child.json', result)
    return result


def child(cpath, qpath, qpin, output):
    g.require(cpath == HERE / 'construct-contract-FIRST.json' and output == HERE / 'construct-CPU-FIRST',
              'Exact metadata child contract/output paths required')
    q = qualified(qpath, qpin); a = acquisition_module(); gate = a.SelectedGate()
    g.require(all(os.environ.get(k) == v for k, v in CHILD_ENV.items()), 'Child-only environment missing')
    g.require(resource.getrlimit(resource.RLIMIT_CPU) == (30, 30) and os.nice(0) >= 15,
              'Actual metadata CPU/nice limits missing')
    g.require(platform.system() == 'Linux' and resource.getrlimit(resource.RLIMIT_AS) == (512 * 2**20,) * 2,
              'Physical Ubuntu metadata AS bound missing')
    value = g.read_json(cpath)
    g.require(g.sha(cpath) == q['actual_contract_sha256'], 'Exact actual custody contract changed')
    result = g.construct(value, gate, run=True)
    emit(output / 'pack-result.json', result)
    return 0


def run(qpath, qpin):
    # Actual contract is frozen only after completion. No partial assets parsed.
    q = qualified(qpath, qpin); a = acquisition_module(); gate = a.SelectedGate()
    g.require(HERE == Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/maya-s-comparison-v1/pack-v2'),
              'Physical Ubuntu construction namespace only')
    cpath = Path(q['actual_contract']); g.require(cpath == HERE / 'construct-contract-FIRST.json', 'Exact contract path')
    g.require(g.sha(cpath) == q['actual_contract_sha256'], 'Actual contract changed')
    completed_receipt(Path(g.read_json(cpath)['acquisition_receipt'])); gate()
    out = HERE / 'construct-CPU-FIRST'; g.require(not out.exists() and not TARGET.exists(), 'Fresh pack/CPU attempt required')
    with (Q / 'acquisition.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); gate(); out.mkdir()
        env = dict(os.environ, **CHILD_ENV)
        command = [sys.executable, '-B', str(Path(__file__)), '--child', '--qualification', str(qpath),
                   '--qualification-sha256', qpin, '--contract', str(cpath), '--output', str(out)]
        result = supervise(command, out, env)
        g.require(type(result['returncode']) is int and result['returncode'] == 0
                  and result['error'] is None and result['cleanup_errors'] == [], 'Metadata construction failed; preserve first attempt')
        gate(); return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--qualification', required=True); p.add_argument('--qualification-sha256', required=True)
    p.add_argument('--child', action='store_true'); p.add_argument('--contract'); p.add_argument('--output')
    args = p.parse_args()
    if args.child: raise SystemExit(child(Path(args.contract), Path(args.qualification), args.qualification_sha256, Path(args.output)))
    print(json.dumps(run(Path(args.qualification), args.qualification_sha256)), flush=True)
