"""One bounded longcold LC1 saved-evidence audit. No inference or service operations.

The immutable qualified dispatcher supplies only bootstrap/fresh-idle, child
limits and owned-group cleanup. A successful child result remains unpublished
until this parent independently checks exit, cleanup, current custody and hashes.
"""
import argparse
import ast
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
E = HERE.parents[2]
R = Path('/home/alex/strata-deepseek-test-20261024')
D_SHA = '8858c1d2f70cd7e97d416fa1535cb1af18f1a2647731c2d88e7c36d66b0e5bad'
ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
       'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
AS = 512 * 2**20
PAIRS = (('lc_audit.py', 'test_lc_audit.py'),
         ('lc_audit_dispatch.py', 'test_lc_audit_dispatch.py'))


def require(ok, why):
    if not ok: raise ValueError(why)


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and all(not p.is_symlink() for p in (path, *path.parents)), 'Canonical evidence path required')
    require(path.is_file() and path.stat().st_nlink == 1, 'One regular evidence file required')
    return path


def sha(path):
    h = hashlib.sha256()
    with regular(path).open('rb') as f:
        for b in iter(lambda: f.read(2**20), b''): h.update(b)
    return h.hexdigest()


def pairs(rows):
    result = {}
    for k, v in rows:
        require(k not in result, 'Duplicate JSON member'); result[k] = v
    return result


def read(path):
    p = regular(path); require(p.stat().st_size <= 32 * 2**20, 'Small metadata only')
    with p.open('rb') as f: raw = f.read(32 * 2**20 + 1)
    require(len(raw) <= 32 * 2**20, 'Metadata grew beyond bound')
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def same(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def write_new(path, value):
    path = Path(path)
    require(all(not p.is_symlink() for p in path.parents), 'Output parent alias')
    with path.open('x') as f: json.dump(value, f, indent=2, allow_nan=False); f.write('\n')


def load(name, path, pin):
    require(sha(path) == pin, 'Exact source before import')
    cached = sys.modules.get(name)
    require(cached is None or Path(cached.__file__) == path, 'Foreign cached helper')
    module = importlib.import_module(name)
    require(Path(module.__file__) == path, 'Imported helper origin differs'); return module


def base():
    path = HERE.parent / 'model-v1/ms_audit_dispatch.py'
    sys.path.insert(0,str(path.parent))
    return load('ms_audit_dispatch', path, D_SHA)


def source_proofs(q):
    for names in PAIRS:
        sm = {n: sha(HERE / n) for n in names}
        tree = ast.parse((HERE / names[1]).read_text()); module = Path(names[1]).stem
        ids = sorted(module + '.' + c.name + '.' + f.name for c in tree.body if isinstance(c, ast.ClassDef)
                     for f in c.body if isinstance(f, ast.FunctionDef) and f.name.startswith('test_'))
        require(ids and all(q['files'].get(str(HERE / n)) == h for n, h in sm.items()), 'New executing source/test omitted')
        require(any(all(g['source_sha256'].get(n) == h for n, h in sm.items())
                    and set(ids).issubset(g['test_ids']) for g in q['CPU_groups']), 'Every new audit/control ID needs matching both-host proof')


def qualification(pin):
    """Caller must establish genuine idle immediately before this hash pass."""
    qpath = HERE / 'longcold-qualification.json'
    require(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) and sha(qpath) == pin, 'Exact LC1 qualification')
    q = read(qpath)
    require(q['mode'] == 'longcold' and q['root_manual_review'] is True and q['astra_manual_review'] is True,
            'Compatibility manual qualification required')
    for name, digest in q['files'].items():
        p = regular(name)
        require(p.is_relative_to(E) or p == R / 'window.py'
                or p.is_relative_to(Path('/home/alex/deepseek-hosted-20261025')), 'Foreign qualification input')
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) and sha(p) == digest, 'Changed qualification input')
    source_proofs(q)
    for name in ('lc_config','lc_runtime'):
        path=HERE/(name+'.py')
        require(q['files'].get(str(path))==sha(path),'New source omitted before import')
        loaded=sys.modules.get(name)
        require(loaded is None or Path(loaded.__file__)==path,'Foreign LC module')
    runtime=load('lc_runtime',HERE/'lc_runtime.py',q['files'][str(HERE/'lc_runtime.py')])
    require(same(runtime.qualified('longcold',pin),q) and sha(qpath)==pin,
            'Full new source/both-host CPU/closedCS1/pack/resource qualification differs')

    return q


def paths():
    return HERE / 'LC1/offline-audit-FIRST', HERE / 'LC1/terminal-audit.json'


def command(pin, attempt_pin, dispatch_pin):
    return [sys.executable, '-B', str(HERE / 'lc_audit_dispatch.py'), '--qualification-sha', pin,
            '--attempt-sha', attempt_pin, '--dispatch-sha', dispatch_pin, '--child']


def observed():
    # Before loading even the pinned bootstrap module in the child.
    a = {'pid': os.getpid(), 'CPU_seconds': list(resource.getrlimit(resource.RLIMIT_CPU)),
         'Linux_AS_bytes': list(resource.getrlimit(resource.RLIMIT_AS)),
         'nice': os.getpriority(os.PRIO_PROCESS, 0), 'environment': {k: os.environ.get(k) for k in ENV}}
    require(sys.platform == 'linux' and a['CPU_seconds'] == [30, 30] and a['Linux_AS_bytes'] == [AS, AS]
            and 15 <= a['nice'] <= 19 and a['environment'] == ENV and os.getpgrp() == a['pid'],
            'Actual isolated CPU/AS/nice/environment child required')
    return a


def child(pin, attempt_pin, dispatch_pin):
    before = observed(); root, target = paths()
    require(sha(root / 'dispatch-attempt.json') == dispatch_pin and sha(root / 'attempt.json') == attempt_pin,
            'Exact original parent attempts required')
    doc = read(root / 'dispatch-attempt.json'); attempt = read(root / 'attempt.json')
    require(same(doc, {'parent_pid': os.getppid(), 'qualification_sha256': pin,
                    'attempt_sha256': attempt_pin, 'retry': False})
            and same(attempt, {'stage': 'longcold-terminal', 'arm': 'LC1', 'qualification_sha256': pin,
                              'expected_binding': attempt['expected_binding']})
            and sys.argv == command(pin, attempt_pin, dispatch_pin)[2:], 'Foreign parent/entry/attempt')
    binding = attempt['expected_binding']; d = base(); d.fresh_idle(binding); q = qualification(pin); d.fresh_idle(binding)
    require(not target.exists() and not target.is_symlink(), 'Preserve existing terminal result')
    write_new(root / 'child-observed.json', {'before': before, 'qualification_sha256': pin,
              'attempt_sha256': attempt_pin, 'dispatch_sha256': dispatch_pin})
    runtime=load('lc_runtime',HERE/'lc_runtime.py',q['files'][str(HERE/'lc_runtime.py')])
    config=load('lc_config',HERE/'lc_config.py',q['files'][str(HERE/'lc_config.py')])
    audit=load('lc_audit',HERE/'lc_audit.py',q['files'][str(HERE/'lc_audit.py')])
    modules=runtime.audit_modules()
    bounds={'CPU':before['CPU_seconds'],'AS':before['Linux_AS_bytes'],'nice':before['nice'],'environment':before['environment']}
    claim=root/'audit-started.json'
    write_new(claim,{'pid':before['pid'],'attempt_sha256':attempt_pin,'retry':False,'observed_before_project_imports':bounds})
    claim_pin=sha(claim);source_pin=q['files'][str(HERE/'lc_audit.py')]
    result=audit.audit_saved(runtime,config,modules['fixtures'],modules['saved'],modules['qa'],q,pin,binding,original=modules['original'])
    result.update(audit_source_sha256=source_pin,observed_before_project_imports=bounds,audit_started_sha256=claim_pin,
                  dispatch_attempt_sha256=attempt_pin,parent_exit0_cleanup_and_wall90_proof_required=True)
    write_new(root / 'result.json', result)  # Raw only; keep it even if later custody refuses publication.
    after = observed(); require(same(before, after), 'Actual child resource contract changed')
    d.fresh_idle(binding)
    require(sha(root / 'dispatch-attempt.json') == dispatch_pin and sha(root / 'attempt.json') == attempt_pin,
            'Original attempt changed')
    write_new(root / 'child-finished.json', {'after': after, 'result_sha256': sha(root / 'result.json'),
              'qualification_sha256': pin, 'attempt_sha256': attempt_pin, 'dispatch_sha256': dispatch_pin})
    return 0


def artifact(pin, q, binding, attempt_pin, dispatch_pin, c):
    root, target = paths()
    require(type(c['returncode']) is int and c['returncode'] == 0 and c['error'] is None and c['cleanup_errors'] == []
            and type(c['pid']) is int and c['pid'] > 0
            and type(c['wall_seconds']) in (int, float) and math.isfinite(c['wall_seconds'])
            and 0 <= c['wall_seconds'] <= 90, 'Actual bounded child0/cleanup required')
    require(sha(root / 'attempt.json') == attempt_pin and sha(root / 'dispatch-attempt.json') == dispatch_pin,
            'Parent attempt changed')
    before = read(root / 'child-observed.json'); after = read(root / 'child-finished.json')
    for x in (before, after):
        require(x['qualification_sha256'] == pin and x['attempt_sha256'] == attempt_pin
                and x['dispatch_sha256'] == dispatch_pin, 'Child observation belongs to another attempt')
    a = before['before']
    require(same(a, after['after']) and a['pid'] == c['pid'] and a['CPU_seconds'] == [30, 30]
            and a['Linux_AS_bytes'] == [AS, AS] and type(a['nice']) is int and 15 <= a['nice'] <= 19
            and a['environment'] == ENV, 'Actual observed resources/PID differ')
    result = read(root / 'result.json')
    require(after['result_sha256'] == sha(root / 'result.json') and result['stage'] == 'LONGCOLD_TERMINAL'
            and result['mode'] == 'longcold' and result['arm'] == 'LC1' and result['passed'] is True
            and result['qualification_sha256'] == pin
            and result['audit_source_sha256'] == q['files'][str(HERE / 'lc_audit.py')]
            and result['dispatch_attempt_sha256'] == attempt_pin
            and result['audit_started_sha256'] == sha(root / 'audit-started.json')
            and result['parent_exit0_cleanup_and_wall90_proof_required'] is True
            and same(result['selected_identity']['start_binding'], binding), 'Child result custody differs')
    require(result.get('completion_scope')=='SINGLE_UNCHANGED_COLD_LONG_REQUEST_ONLY'
            and result.get('purpose')=='ONE_COLD_LONG_COMPATIBILITY_SCREEN_NOT_A_COMPARISON',
            'Only this distinct single cold compatibility scope')
    require(all(result[k] is False for k in ('retry', 'automatic_next_arm', 'performance_claim', 'general_quality_claim',
                 'cross_pack_numeric_equivalence', 'finite_logits_checked', 'near_full_context_or_output_tested', 'deployment_admitted')),
            'No advancement/equivalence/performance permission')
    expected = {'CPU': a['CPU_seconds'], 'AS': a['Linux_AS_bytes'], 'nice': a['nice'], 'environment': a['environment']}
    claim = read(root / 'audit-started.json')
    require(claim['pid'] == c['pid'] and claim['attempt_sha256'] == attempt_pin and claim['retry'] is False
            and same(claim['observed_before_project_imports'], expected)
            and same(result['observed_before_project_imports'], expected), 'Auditor did not observe the same child')
    runtime = load('lc_runtime', HERE / 'lc_runtime.py', q['files'][str(HERE / 'lc_runtime.py')])
    output, metadata = runtime.owned_paths(result['output'], 'longcold', 'LC1', present=True)
    window = Path(result['window'])
    require(window.parent == R / 'windows' and re.fullmatch(r'[0-9]{8}T[0-9]{6}Z.json', window.name), 'Foreign window evidence')
    explicit = {window, window.with_suffix('.telemetry.jsonl'), HERE / 'longcold-arms.json',
                HERE / 'base-config.json', HERE.parent/'model-v1/quality-fixtures-B.json'}
    require(result['evidence_sha256'], 'No saved evidence inventory')
    total = 0
    for name, digest in result['evidence_sha256'].items():
        path = regular(name); size = path.stat().st_size; total += size
        require(path in explicit or path.is_relative_to(output) or path.is_relative_to(metadata), 'Foreign raw evidence')
        require(size <= 32 * 2**20 and total <= 128 * 2**20 and sha(path) == digest, 'Changed/oversized raw evidence')
    return result


def dispatch(pin):
    root, target = paths(); d = base(); binding = d.fresh_idle(); q = qualification(pin); d.fresh_idle(binding)
    require(all(not p.is_symlink() for p in (root, *root.parents)), 'Output ancestry alias')
    require(not target.exists() and not target.is_symlink(), 'Preserve previous terminal result')
    root.mkdir(parents=True, exist_ok=False)  # One immutable parent attempt, even if a later write fails.
    start = time.monotonic(); proc = None; rc = None; error = None; errors = []; result = None; cmd = None
    attempt_pin = dispatch_pin = None
    try:
        write_new(root / 'attempt.json', {'stage': 'longcold-terminal', 'arm': 'LC1',
                  'qualification_sha256': pin, 'expected_binding': binding})
        attempt_pin = sha(root / 'attempt.json')
        write_new(root / 'dispatch-attempt.json', {'parent_pid': os.getpid(), 'qualification_sha256': pin,
                  'attempt_sha256': attempt_pin, 'retry': False})
        dispatch_pin = sha(root / 'dispatch-attempt.json'); cmd = command(pin, attempt_pin, dispatch_pin)
        with (root / 'child.log').open('xb') as log:
            proc = subprocess.Popen(cmd, cwd=HERE, env=dict(os.environ, **ENV), stdin=subprocess.DEVNULL,
                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=d.limits)
            rc = proc.wait(timeout=90)
    except BaseException as exc: error = type(exc).__name__ + ': ' + str(exc)
    finally:
        if proc is not None:
            try: errors = d.cleanup(proc)
            except BaseException as exc: errors = ['Unexpected owned cleanup ' + type(exc).__name__ + ': ' + str(exc)]
    c = {'pid': proc.pid if proc else None, 'returncode': rc, 'error': error, 'cleanup_errors': errors,
         'wall_seconds': time.monotonic() - start, 'CPU_limit_seconds': 30, 'Linux_AS_bytes': AS,
         'wall_limit_seconds': 90, 'nice_increment': 15, 'environment': dict(ENV), 'command': cmd}
    if rc == 0 and error is None and not errors:
        try:
            d.fresh_idle(binding); require(same(qualification(pin), q), 'Post-child qualification changed')
            d.fresh_idle(binding)
            result = artifact(pin, q, binding, attempt_pin, dispatch_pin, c)
        except BaseException as exc: c['error'] = 'Post-child ' + type(exc).__name__ + ': ' + str(exc)
    success = result is not None and c['error'] is None and not c['cleanup_errors']
    supervision = {'passed': success, 'arm': 'LC1', 'stage': 'longcold-terminal', 'qualification_sha256': pin,
                   'attempt_sha256': attempt_pin, 'dispatch_sha256': dispatch_pin, 'binding': binding,
                   'child': c, 'retry': False, 'terminal_publication': 'NOT_YET_ATTEMPTED'}
    write_new(root / 'supervision.json', supervision)
    if success:
        # Only a supervised, cleaned, freshly verified child can publish here.
        write_new(target, {**result, 'bounded_child': c, 'parent_supervision_sha256': sha(root / 'supervision.json'),
                           'parent_dispatch_attempt_sha256': dispatch_pin, 'observed_child_sha256': sha(root / 'child-observed.json'),
                           'finished_child_sha256': sha(root / 'child-finished.json')})
    return 0 if success else 1


def main():
    p = argparse.ArgumentParser(); p.add_argument('--qualification-sha', required=True)
    p.add_argument('--attempt-sha'); p.add_argument('--dispatch-sha'); p.add_argument('--child', action='store_true'); a = p.parse_args()
    require((a.child and a.attempt_sha and a.dispatch_sha) or
            (not a.child and a.attempt_sha is None and a.dispatch_sha is None), 'Exact parent/child command')
    return child(a.qualification_sha, a.attempt_sha, a.dispatch_sha) if a.child else dispatch(a.qualification_sha)


if __name__ == '__main__': sys.exit(main())
