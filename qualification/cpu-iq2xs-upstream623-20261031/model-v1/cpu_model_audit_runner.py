"""Independent post-restoration audit: four bounded finite scans, then assembly.

No model launch, service action or automatic acceptance. First failures remain.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
import resource
import shutil
import urllib.request
from pathlib import Path
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
R = Path('/home/alex/strata-deepseek-test-20261024')
E = R / 'reliability-optimization-20261025'
BUILD = HERE.parent / 'build-v3/build.py'
BUILD_SHA = 'a765195c6fc6fe65e2d780bce3d166d28f181de722d68d725f7bceb568dd7380'
GUARD_SHA = '4f40c04a69701cf86e478bdf4f13a021de05f18fae1b943fcd7b88aee19295fd'
JOBS = ('scan-0', 'scan-1', 'scan-2', 'scan-3', 'assemble', 'compare')


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink()
            and path.is_file() and path.stat().st_nlink == 1, 'Exact regular input required')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(65536), b''): h.update(part)
    return h.hexdigest()


def read(path):
    sha(path)
    return json.loads(Path(path).read_text())


def emit(path, value):
    require(path.parent.resolve() == path.parent, 'Owned real output directory required')
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')


def exact_module(name, path, pin):
    require(sha(path) == pin, 'Exact module bytes required')
    old = sys.modules.get(name)
    require(old is None or Path(old.__file__).resolve() == path, 'Foreign imported module')
    if old is None:
        spec = importlib.util.spec_from_file_location(name, path)
        old = importlib.util.module_from_spec(spec); sys.modules[name] = old
        spec.loader.exec_module(old)
    require(sha(path) == pin and Path(old.__file__).resolve() == path, 'Module changed')
    return old



def early_bounds(parent):
    env={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
         'NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}
    value={'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgid(0),
           'cpu':list(resource.getrlimit(resource.RLIMIT_CPU)),
           'as':list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform=='linux' else None,
           'nice':os.getpriority(os.PRIO_PROCESS,0),'environment':{k:os.environ.get(k) for k in env},
           'platform':sys.platform,'dont_write_bytecode':sys.dont_write_bytecode}
    require(type(parent) is int and parent>1 and value['ppid']==parent and value['pgid']==value['pid']
            and value['cpu']==[30,30] and value['as']==[512*2**20]*2 and value['nice']==15
            and value['environment']==env and value['platform']=='linux' and value['dont_write_bytecode'] is True,
            'Actual child bounds must precede project bootstrap')
    return value


def early_guard(reservation=None):
    state=json.loads((E/'STATE.json').read_text())
    keys=('active_private_phase','active_GPU_phase','active_gpu_experiment','private_window','active_cpu_build',
          'production_restore_in_progress','production_verification_pending','production_temporarily_stopped')
    for key in keys:
        if key=='active_cpu_build' and reservation is not None:require(state.get(key)==reservation,'Early own CPU claim changed')
        else:require(not state.get(key),'Early private/build/restoration refusal before hashing')
    identity=state.get('decode_optimization_current',{}).get('selected_identity') or state['chunk4096_activation']['selected_identity']
    require(identity.get('native_sha256')=='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
            and identity.get('config_sha256')=='c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa',
            'Early selected profile changed')
    binding=identity['start_binding'];pid=binding['native_pid']
    require(all(type(binding.get(k)) is int and binding[k]>1 for k in ('main_pid','native_pid','native_start_ticks')),
            'Early actual owner binding required')
    stat=(Path('/proc')/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()
    require(int(stat[1])==binding['main_pid'] and int(stat[19])==binding['native_start_ticks']
            and os.path.samefile(Path('/proc')/str(pid)/'exe',Path('/home/alex/deepseek-hosted-20261025/bin/maya-ds4')),
            'Early actual selected native owner changed')
    observations=[]
    for endpoint in ('/health','/v1/telemetry'):
        with urllib.request.urlopen('http://127.0.0.1:8012'+endpoint,timeout=5) as response:
            raw=response.read(1024*1024+1);require(len(raw)<=1024*1024,'Oversized lightweight hosting observation')
            observations.append(json.loads(raw))
    module=exact_module('cpu_iq2xs_audit_early_health',HERE/'cpu_guard.py',GUARD_SHA)
    module.health_contract(*observations)
    require(shutil.disk_usage('/').free>=132*2**30,'Early root132 unavailable')
    require(json.loads((E/'STATE.json').read_text())==state,'Early coordination changed')
    return binding

def bootstrap(pin,reservation=None):
    early_guard(reservation)  # before qualification scans or project imports
    qpath = HERE / 'numerical-qualification.json'
    require(sha(qpath) == pin, 'Exact qualification required')
    q = read(qpath)
    # Prove every project source/input before importing runtime or any helper.
    require(q['files'].get(str(BUILD)) == BUILD_SHA
            and q['source_sha256'].get('cpu_guard.py') == GUARD_SHA, 'Qualified CPU ownership/guard omitted')
    for name, value in q['files'].items():
        if name.endswith('.py'): require(sha(Path(name)) == value, 'Preimport Python changed')
    driver = exact_module('cpu_iq2xs_model_audit_driver', HERE / 'cpu_driver.py', q['source_sha256']['cpu_driver.py'])
    driver.checked(q['source_review_sha256'])
    sys.path.insert(0, str(HERE))
    import cpu_model_runtime as runtime
    require(runtime.qualified('numerical', pin) == {**q, 'qualification_sha256': pin}, 'New mode qualification differs')
    build = exact_module('cpu_iq2xs_model_audit_build', BUILD, BUILD_SHA)
    guard = exact_module('cpu_iq2xs_model_audit_guard', HERE / 'cpu_guard.py', GUARD_SHA)
    return q, driver, runtime, build, guard


def record_contract(record, arm, pin, parent, binding):
    require(type(record) is dict and record.get('mode') == 'cpu-iq2xs-model-offline-audit'
            and record.get('arm') == arm and record.get('qualification_sha256') == pin
            and type(record.get('controller_pid')) is int and record['controller_pid'] == parent
            and record.get('start_binding') == binding and type(record.get('controller_start_ticks')) is int
            and record['controller_start_ticks'] > 0
            and type(record.get('nonce')) is str and len(record['nonce']) == 32,
            'Exact original audit parent claim required')


def paths(arm, job=None):
    require(arm in ('N0', 'N1'), 'Numerical arm only')
    root = HERE / arm / 'AUDIT-FIRST'
    if job is not None: require(job in JOBS, 'Exact finite child job required')
    return root if job is None else root / job


def child_chain(driver, q, arm, job, parent):
    folder = paths(arm, job)
    attempt, proc, actual, result = [read(folder / name) for name in
                                    ('attempt.json', 'child.json', 'observed.json', 'result.json')]
    require(attempt == {'arm': arm, 'job': job, 'parent_pid': parent,
                        'qualification_sha256': q['qualification_sha256']}, 'Child attempt association differs')
    driver.bounds(actual, proc['pid'], parent)
    expected = [sys.executable, '-I', '-B', str(HERE / 'cpu_model_audit_runner.py'), '--arm', arm,
                '--qualification-pin', q['qualification_sha256'], '--worker', job, '--parent-pid', str(parent)]
    require(proc['argv'] == expected and actual['platform'] == 'linux', 'Actual physical child command differs')
    require(proc['error'] is None and proc['cleanup'] == [] and type(proc['returncode']) is int
            and proc['returncode'] == 0 and type(proc.get('elapsed_seconds')) in (int,float)
            and math.isfinite(proc['elapsed_seconds']) and 0 <= proc['elapsed_seconds'] <= 90,
            'Actual bounded child exit/cleanup failed')
    require(result['observed'] == result['post_observed'] == actual and result['passed'] is True
            and result['arm'] == arm and result['job'] == job
            and result['qualification_sha256'] == q['qualification_sha256']
            and result['source_sha256'] == result['source_after_sha256'] == q['source_sha256']
            and result['input_sha256'] == result['input_after_sha256'] == q['input_sha256'],
            'Exact child result/maps/bounds required')
    return result['value']


def worker(arm, job, pin, parent):
    actual = early_bounds(parent)  # before any project import/hash scan
    record = read(paths(arm) / 'attempt.json')['record']
    q, driver, runtime, build, guard = bootstrap(pin,record)
    driver.bounds(actual, os.getpid(), parent)
    folder = paths(arm, job); root = paths(arm)
    attempt = read(folder / 'attempt.json')
    require(attempt == {'arm': arm, 'job': job, 'parent_pid': parent,
                        'qualification_sha256': pin}, 'Exact child attempt required')
    a, _ = runtime.support(); host = a.ChunkProductionHost(); host.start_binding = runtime.current_binding()
    record_contract(record, arm, pin, parent, host.start_binding)
    require(build.process_ticks(parent) == record['controller_start_ticks'], 'Parent PID reused')
    def check():
        guard.guard(runtime, host, host.start_binding, E / 'STATE.json', record)
        require(build.process_ticks(parent) == record['controller_start_ticks'], 'Original parent gone')
    check(); before = driver.checked(q['source_review_sha256'])
    emit(folder / 'observed.json', actual)
    import cpu_model_numerical_audit as audit
    evidence = audit.saved_evidence(arm)
    if job.startswith('scan-'):
        value = audit.scan_one(arm, int(job[-1]), pin)
    elif job == 'assemble':
        evidence_rows = [read(paths(arm,name)/'result.json')['evidence'] for name in JOBS[:4]]
        require(all(x==evidence for x in evidence_rows),'Evidence changed between finite scans and assembly')
        scans = [child_chain(driver, {**q, 'qualification_sha256': pin}, arm, name, parent) for name in JOBS[:4]]
        value = audit.audit(arm, scans, guard=check)
    else:
        require(arm == 'N1', 'Only new candidate can compare accepted N0')
        import cpu_model_numerical as mode
        registry = read(HERE / 'numerical-arms.json'); mode.prerequisites('N1', {k:v for k,v in registry.items() if k != 'N1'})
        baseline = read(HERE / 'N0/terminal-audit.json')
        require(audit.saved_evidence('N0')==baseline['saved_evidence'],'Accepted N0 raw evidence changed')
        candidate = child_chain(driver, {**q, 'qualification_sha256': pin}, arm, 'assemble', parent)
        value = audit.compare_complete(baseline, candidate)
        require(value['passed'] is True, 'Exact whole-model numerical comparison failed: ' + json.dumps(value))
    require(audit.saved_evidence(arm) == evidence, 'Saved numerical evidence changed during bounded child')
    check(); after = driver.checked(q['source_review_sha256']); post = driver.observed()
    require(before == after and actual == post, 'Audit inputs/bounds changed')
    emit(folder / 'result.json', {'passed': True, 'arm': arm, 'job': job,
         'qualification_sha256': pin, 'observed': actual, 'post_observed': post,
         'source_sha256': before[0], 'source_after_sha256': after[0],
         'input_sha256': before[1], 'input_after_sha256': after[1], 'evidence': evidence, 'value': value})


def parent(arm, pin):
    started = time.monotonic()
    require(sys.platform == 'linux' and HERE == E / 'decode-optimization-20261028/cpu-iq2xs-upstream623-v1/model-v1'
            and sys.dont_write_bytecode, 'Physical canonical Linux -B owner required')
    q, driver, runtime, build, guard = bootstrap(pin)
    a, _ = runtime.support(); host = a.ChunkProductionHost(); binding = runtime.current_binding(); host.start_binding = binding
    guard.guard(runtime, host, binding, E / 'STATE.json')
    first_gpu = build.observe_gpu_lease(host, binding); cas = build.load_cas()
    root = paths(arm); build.fresh(root); record = None; claimed = False; released = False
    primary = None; value = None; absence = None
    with build.CPULease(E / 'cpu-build.lock') as lease:
        state = guard.guard(runtime, host, binding, E / 'STATE.json'); lease.check()
        root.mkdir(); owned = build.OwnedChildren(root / 'owned-children.jsonl')
        record = {'mode': 'cpu-iq2xs-model-offline-audit', 'arm': arm, 'qualification_sha256': pin,
                  'controller_pid': os.getpid(), 'controller_start_ticks': build.process_ticks(os.getpid()),
                  'nonce': uuid.uuid4().hex, 'start_binding': binding, 'cpu_lease': dict(lease.identity)}
        emit(root / 'attempt.json', {'record': record, 'GPU_lease': first_gpu,
             'global_state_CAS_atomic': False, 'single_coordinator_maintenance_freeze': True})
        try:
            raw = (E / 'STATE.json').read_bytes()
            require(json.loads(raw) == state and not state.get('active_cpu_build'), 'Coordination changed before claim')
            cas.cas_state(E / 'STATE.json', raw, dict(state, active_cpu_build=record)); claimed = True
            for job in (JOBS if arm == 'N1' else JOBS[:-1]):
                lease.check(); guard.guard(runtime, host, binding, E / 'STATE.json', record)
                require(time.monotonic() - started < 500, 'Five-child soft admission budget')
                folder = paths(arm, job); folder.mkdir()
                emit(folder / 'attempt.json', {'arm': arm, 'job': job, 'parent_pid': os.getpid(), 'qualification_sha256': pin})
                argv = [sys.executable, '-I', '-B', str(HERE / 'cpu_model_audit_runner.py'), '--arm', arm,
                        '--qualification-pin', pin, '--worker', job, '--parent-pid', str(os.getpid())]
                owned.starting(job)
                proc = driver.supervise(argv, folder, on_spawn=lambda p: owned.registered(p, job))
                for fault in proc['cleanup']: owned.cleanup_failed(job, RuntimeError(fault))
                require(not proc['cleanup'] and proc['returncode'] == 0 and proc['error'] is None,
                        'Audit child failed; original attempt retained')
                value = child_chain(driver, {**q, 'qualification_sha256': pin}, arm, job, os.getpid())
            guard.guard(runtime, host, binding, E / 'STATE.json', record)
            build.observe_gpu_lease(host, binding, first_gpu['identity'])
        except BaseException as exc: primary = exc
        finally:
            try:
                lease.check(); absence = owned.absence()
                require(absence['passed'], 'Owned descendants survive; retain CPU claim')
                raw = (E / 'STATE.json').read_bytes(); state = json.loads(raw)
                if state.get('active_cpu_build') == record:
                    cas.cas_state(E / 'STATE.json', raw, dict(state, active_cpu_build=False)); released = True
                else: require(not claimed and state.get('active_cpu_build') is False, 'Own CPU claim changed')
                build.observe_gpu_lease(host, binding, first_gpu['identity'])
                require(time.monotonic() - started <= 600, 'Audit parent wall exceeded')
            except BaseException as exc:
                if primary is None: primary = exc
                else: primary.add_note('Audit ownership closure: ' + repr(exc))
            emit(root / 'supervision.json', {'passed': primary is None, 'error': None if primary is None else repr(primary),
                 'error_notes': [] if primary is None else list(getattr(primary, '__notes__', [])),
                 'own_claim_released': released, 'owned_groups_absence': absence,
                 'production_changed': False, 'GPU_lease_mutated': False, 'elapsed_seconds': time.monotonic() - started})
        if primary is not None: raise primary
        require(value['passed'] is True and released and absence['passed'], 'Incomplete terminal audit')
        guard.guard(runtime,host,binding,E/'STATE.json')
        lease.check();driver.checked(q['source_review_sha256'])
        import cpu_model_numerical_audit as audit
        evidence=read(paths(arm,'assemble')/'result.json')['evidence']
        audit.evidence_fingerprints(evidence)
        child_pins={job:{name:sha(paths(arm,job)/name) for name in ('attempt.json','child.json','observed.json','result.json','child.log')} for job in (JOBS if arm=='N1' else JOBS[:-1])}
        comparison = value if arm == 'N1' else None
        value = child_chain(driver, {**q, 'qualification_sha256': pin}, arm, 'assemble', os.getpid())
        value['exact_comparison'] = comparison
        value['bounded_offline_supervision_sha256'] = sha(root / 'supervision.json')
        value['bounded_child_result_sha256'] = {job: sha(paths(arm, job) / 'result.json') for job in (JOBS if arm == 'N1' else JOBS[:-1])}
        guard.guard(runtime,host,binding,E/'STATE.json');lease.check()
        require(child_pins=={job:{name:sha(paths(arm,job)/name) for name in pins} for job,pins in child_pins.items()},'Bounded child evidence changed before publication')
        audit.evidence_fingerprints(evidence)
        value['saved_evidence']=evidence;value['bounded_child_raw_sha256']=child_pins
        emit(HERE / arm / 'terminal-audit.json', value)
        return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm', choices=('N0', 'N1'), required=True)
    parser.add_argument('--qualification-pin', required=True)
    parser.add_argument('--worker', choices=JOBS)
    parser.add_argument('--parent-pid', type=int)
    args = parser.parse_args()
    require((args.worker is None) == (args.parent_pid is None), 'Exact worker/parent arguments required')
    if args.worker: worker(args.arm, args.worker, args.qualification_pin, args.parent_pid)
    else: parent(args.arm, args.qualification_pin)
