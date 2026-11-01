"""One actual1M static allocation snapshot; no routed-weight load or inference.

Uses the existing selected4096 owner, canonical window and restoration body.
The separate qualification pins all new source/CPU proofs and completed assets.
"""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
Q = HERE.parent
DC = Q.parent
E = DC.parent
R = E.parent
D = Path('/home/alex/deepseek-hosted-20261025')
NATIVE = Q / 'native-build-v2/native-build-FIRST/maya-ds4'
PACK = Q / 'candidate-pack-v1/pack-FIRST'
BASE_SHA = 'c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'
WINDOW_SHA = '170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f'
SUPPORT = {
    'base': ('iq2s-persistent-v1/model-v1/iq2s_model_runtime.py', '1516752104307ffc159fbb80afd972ccd43c5cb9a96cf3e47de126f62482d510'),
    'legacy': ('q8-sharing-v1/model-v1/q8share_model_runtime.py', '9bd594247cecc13980d864780b778a66da08fcaf2b0a3ff5b386e84e33a1ad2c'),
    'startup': ('head-batching-v1/head_startup.py', '53988e95be7c1883f7aeeb7ae2b87081da74d64b3f38eb43b6a274d93d1ff4f4'),
    'fence': ('maya-s-comparison-v1/performance-v2/pv_controls.py', '1038fad719fb7ed7516ab3e07d88d40fb3b5cd7408f6ed19ddc2296f13052cf5'),
}
PHASE_KEYS = ('active_private_phase', 'active_GPU_phase', 'active_gpu_experiment', 'private_window',
              'active_cpu_build', 'production_restore_in_progress', 'production_verification_pending',
              'production_temporarily_stopped')
SOURCES = ('placement.py', 'test_placement.py', 'run_cpu.py')
RUNNING = 'S2_PLACEMENT_PRIVATE_RUNNING'
COMPLETE = 'S2_PLACEMENT_SELECTED4096_RESTORED'


class ResourceDeferred(RuntimeError): pass


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(2**20), b''): h.update(b)
    return h.hexdigest()


def emit(path, row):
    path = Path(path); require(not path.is_symlink(), 'Receipt alias')
    temp = path.with_name(path.name + '.tmp'); require(not temp.exists(), 'Preserve temporary residue')
    with temp.open('x') as f: json.dump(row, f, indent=2, allow_nan=False); f.write('\n')
    temp.replace(path)


def load(name, path, pin):
    require(path.resolve() == path and path.is_file() and not path.is_symlink() and sha(path) == pin,
            'Exact unchanged helper source')
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def support():
    base = load('s2_placement_base', DC / SUPPORT['base'][0], SUPPORT['base'][1])
    a, old = base.support()
    legacy = load('s2_placement_legacy', DC / SUPPORT['legacy'][0], SUPPORT['legacy'][1])
    startup = load('s2_placement_startup', DC / SUPPORT['startup'][0], SUPPORT['startup'][1])
    # pv_controls imports its unchanged pv_runtime by its own exact path.
    fence = load('s2_placement_fence', DC / SUPPORT['fence'][0], SUPPORT['fence'][1])
    require(fence.runtime.MEMORY_MAX == 80 * 2**30 and fence.runtime.HOST_MARGIN == 8 * 2**30,
            'Existing80GiB private envelope')
    return a, old, base, legacy, startup, fence


def paths(output, *, present=False):
    output = Path(output)
    require(output.parent == E / 'results' and re.fullmatch(r's2-placement-P0-\d{8}T\d{6}Z', output.name),
            'One new placement namespace')
    meta = E / 'maintenance' / output.name
    require(not output.is_symlink() and not meta.is_symlink() and
            (output.is_dir() if present else not output.exists()), 'Fresh/present real output')
    return output, meta


def argv(base, folder):
    args = list(base['args'])
    require(args.count('--serve') == 1, 'Selected serve argument')
    args.remove('--serve')
    for name, value in (('--pack', str(PACK)), ('--expert-profile', str(folder / 'expert-profile.bin'))):
        require(args.count(name) == 1, 'Unique selected option'); args[args.index(name) + 1] = value
    for name, value in (('--max-context', '1048576'), ('--prefill-chunk', '4096'), ('--tp', '1'),
                        ('--dspark', 'on'), ('--cpu-threads', '24'), ('--mmap-experts', 'off')):
        require(args.count(name) == 1 and args[args.index(name) + 1] == value, 'Capacity/quality policy changed')
    require(not any(x in args for x in ('--cpu-native', '--expert-cache', '--placement-plan', '--layer-split', '--ids')),
            'No native payload, adaptive placement or inference in diagnostic')
    return [str(NATIVE), *args, '--no-expert-cache', '--layer-split', 'auto',
            '--placement-plan', str(folder / 'actual-placement.json')]


def environment(base, folder, window_env):
    env = dict(window_env); env.update(base['env'])
    for key, tail in (('STRATA_DS4_SLOT_DIR', 'cache'), ('DS4_LANE_CAL', 'lane.txt'), ('DS4_LT_STORE', 'lt.txt')):
        env[key] = str(folder / tail)
    for key, value in {'DS4_YOCO': '1', 'STRATA_DS4_PROMPT_SKIP': '1', 'DS4_REQUIRE_ALL_RAM': '1',
                       'DS4_STREAM': '0', 'STRATA_DS4_Q8_BATCH': '1', 'DS4_Q8_CHECK': '1'}.items():
        require(env.get(key) == value, 'Selected effective runtime policy changed')
    require(not any(env.get(k) for k in ('DS4_SERVE_DUMP', 'DS4_HELPER', 'DS4_CPU_TIER', 'DS4_FLOW', 'DS4_STORE')),
            'Foreign diagnostic mode')
    return env


def validate_plan(plan):
    require(plan.get('schema') == 'ds4-actual-placement-v1' and plan.get('context_total') == 1048576 and
            plan.get('prefill_chunk') == 4096 and plan.get('drafter_blocks') == 3 and
            plan.get('routed_experts_loaded') is False and plan.get('inference_executed') is False and
            plan.get('expert_cache') is False, 'Actual no-inference placement policy')
    rows = plan['layers']; require(type(rows) is list and len(rows) == 40, 'Complete actual trunk map')
    counts, gpu, cpu, size = [], [], 0, 0
    for layer, row in enumerate(rows):
        require(row['layer'] == layer and row['members'] == 1, 'StaticTP1 map')
        slot, hits = row['slots'], row['counts']
        require(len(slot) == len(hits) == 384 and all(type(v) is int and -1 <= v < 384 for v in slot) and
                all(type(v) is int and 0 <= v < 2**32 for v in hits) and sum(hits) > 0, 'Actual slots/counts')
        resident = [v for v in slot if v >= 0]
        require(sorted(resident) == list(range(len(resident))), 'Unique contiguous actual GPU slots')
        require(len(row['role_bytes']) == len(row['role_types']) == 3 and
                all(type(v) is int and v > 0 for v in row['role_bytes']), 'Actual three-role geometry')
        if 24 <= layer <= 28: require(row['role_types'][:2] == [21, 21] and row['role_bytes'][:2] == [5068800]*2,
                                     'Actual sensitive-layer IQ3_S gate/up')
        ram = 384 - len(resident); cpu += ram; size += ram * sum(row['role_bytes'])
        counts.append(hits); gpu.append([e for e, v in enumerate(slot) if v >= 0])
    require(type(plan['CPU_experts']) is int and plan['CPU_experts'] == cpu and
            type(plan['GPU_experts']) is int and plan['GPU_experts'] == 15360 - cpu and
            plan['CPU_base_payload_bytes'] == size and cpu >= 1870, 'Exact actual byte/expert accounting')
    return counts, gpu


def cpu_contract(proofs, source):
    require(set(proofs) == {'mac', 'ubuntu'}, 'Both physical controls')
    first = proofs['mac']
    for label, proof in proofs.items():
        platform = 'darwin' if label == 'mac' else 'linux'
        require(proof['passed'] is True and proof['returncode'] == 0 and proof['controls'] == len(first['test_ids'])
                and proof['test_ids'] == first['test_ids'] and proof['source_sha256'] == source and
                proof['input_sha256'] == first['input_sha256'] and proof['failures'] == proof['errors'] == 0,
                'Exact new source/input/IDs and complete clean CPU proof')
        observed = proof['observed']
        require(observed['platform'] == platform and observed['cpu'] == [30, 30] and observed['nice'] == 15 and
                observed['as'] == ([512*2**20]*2 if platform == 'linux' else None) and
                observed['pid'] == observed['pgid'] and observed['dont_write_bytecode'] is True,
                'Actual bounded physical CPU child')
        require(all(observed['environment'].get(k) == v for k, v in
                    {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
                     'MALLOC_ARENA_MAX': '1'}.items()), 'Clean data-child environment')


def qualified(pin):
    require(sha(HERE / 'qualification.json') == pin, 'Exact placement qualification')
    q = json.loads((HERE / 'qualification.json').read_text())
    require(q['entire_source_tests_driver_manually_read'] is True and q['mode'] == 'placement' and
            q['selected_binding'] and q['context_total'] == 1048576 and q['output_allowance'] == 262144 and
            q['inference_requests'] == 0 and q['native_sha256'] and q['weight_materialization_closed'] is True,
            'Completed new-source/materialization qualification')
    source = {n: sha(HERE / n) for n in SOURCES}
    proofs = {label: json.loads((HERE / ('CPU-FIRST-' + label + '.json')).read_text()) for label in ('mac', 'ubuntu')}
    cpu_contract(proofs, source)
    for name, pin in q['files'].items():
        p = Path(name); require(p.resolve() == p and not p.is_symlink() and sha(p) == pin, 'Placement input drift: ' + name)
    require(q['files'].get(str(NATIVE)) == q['native_sha256'] and q['files'].get(str(D / 'config.json')) == BASE_SHA
            and q['files'].get(str(R / 'window.py')) == WINDOW_SHA and
            all(q['files'].get(str(HERE / n)) == pin for n, pin in source.items()), 'Required source/artifact/window pins')
    return q


def stop_child(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try: proc.wait(timeout=15)
        except subprocess.TimeoutExpired: os.killpg(proc.pid, signal.SIGKILL); proc.wait(timeout=15)
    try: os.killpg(proc.pid, 0)
    except ProcessLookupError: return
    os.killpg(proc.pid, signal.SIGKILL)
    raise RuntimeError('Owned native descendants remained after exit')


def memory_floor(read, *, clock=time.monotonic, pause=time.sleep):
    began = clock()
    while True:
        available = read(); elapsed = clock() - began
        require(type(available) is int and available >= 0 and elapsed >= 0, 'Actual available memory/clock')
        if elapsed <= 60 and available >= 88*2**30: return available
        if elapsed >= 60: raise ResourceDeferred('Post-stop physical88GiB floor unavailable; no private attempt')
        pause(min(1, 60 - elapsed))


def phase(output, proofpath):
    a, old, base, legacy, startup, fence = support()
    output, meta = paths(output); proof = json.loads(Path(proofpath).read_text())
    current = json.loads((E / 'STATE.json').read_text())
    require(Path(proofpath) == meta / 'proof.json' and current['active_private_phase'] == str(meta) and
            current['decode_optimization_current']['status'] == RUNNING and
            current['decode_optimization_current']['controller_pid'] == proof['controller_pid'] and
            json.loads((HERE / 'arms.json').read_text())['P0']['output'] == str(output), 'Exact owned placement phase')
    window, record = old.owned_window()
    expected = [str(R / 'venv/bin/python3.14'), '-B', str(HERE / 'placement.py'), '--phase',
                '--output', str(output), '--proof', str(proofpath)]
    require(record['command'] == expected and record.get('continued_from') and record['test_returncode'] is None,
            'Existing canonical bounded window')
    old.q8_phase.admission(proof, 'P0', output, qualification_key='qualified_for_owned_s2_placement')
    output.mkdir(); folder = output / 'native'; folder.mkdir()
    for n in ('cache', 'tmp', 'cuda-cache'): (folder / n).mkdir()
    shutil.copyfile(D / 'profile-seed.bin', folder / 'expert-profile.bin')
    require(sha(folder / 'expert-profile.bin') == old.q8_phase.SEED_SHA, 'Unchanged frozen profile seed')
    cfg = json.loads((D / 'config.json').read_text()); command = argv(cfg, folder)
    env = environment(cfg, folder, old.q8_phase.environment(folder, window))
    with fence.fenced_phase(output) as (limits, handles):
        with (folder / 'engine.log').open('x') as log:
            proc = subprocess.Popen(command, cwd=D, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            handles.append(proc)
            primary = None
            try:
                emit(output / 'native-start.json', {'pid': proc.pid, 'argv': command})
                # Snapshot only our exact child before it can load any experts.
                actual = Path('/proc') / str(proc.pid)
                require(os.path.samefile(actual / 'exe', NATIVE), 'Actual new native executable')
                require('strata-deepseek-window.service' in (actual / 'cgroup').read_text(), 'Existing owned native cgroup')
                actual_argv = (actual / 'cmdline').read_bytes().decode().split('\0')[:-1]
                require(actual_argv == command, 'Actual placement argv')
                emit(output / 'native-identity.json', {'pid': proc.pid, 'argv': actual_argv,
                    'cgroup': (actual / 'cgroup').read_text(), 'same_executable': True})
                rc = proc.wait(timeout=900)
                require(rc == 0, 'First placement native failed; preserve and HOLD')
            except BaseException as exc: primary = exc; raise
            finally:
                try: stop_child(proc)
                except BaseException as exc:
                    if primary is None: raise
                    primary.add_note('Owned native cleanup: ' + repr(exc))
                emit(output / 'native-exit.json', {'pid': proc.pid, 'returncode': proc.poll(),
                    'error': repr(primary) if primary else None, 'API_started': False, 'inference_requests': 0})
        plan = json.loads((folder / 'actual-placement.json').read_text()); validate_plan(plan)
        end = fence.fence_terminal(limits)
        emit(output / 'receipt.json', {'passed': True, 'native_returncode': 0, 'API_started': False,
             'inference_requests': 0, 'actual_placement': plan, 'private_resources': end,
             'qualification_sha256': proof['qualification_sha256']})


def controller(run):
    a, old, base, legacy, startup, fence = support()
    current = json.loads((E / 'STATE.json').read_text())
    require(not any(current.get(k) for k in PHASE_KEYS), 'Existing private/build/restoration work')
    pin = sha(HERE / 'qualification.json'); q = qualified(pin)
    require(not json.loads((HERE / 'arms.json').read_text()), 'Single P0 only; no replay')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output, meta = paths(E / 'results' / ('s2-placement-P0-' + stamp)); meta.mkdir()
    legacy_base, startup_base = legacy.host_class(a), startup.guarded_host(a)
    class Host(legacy_base, startup_base):
        def idle(self): return self.baseline_reader().idle() if self.restored_pid is None else super().idle()
        def preflight(self, out):
            if not self.idle(): raise old.AdmissionDeferred('Busy; untouched')
            now = json.loads((E / 'STATE.json').read_text())
            require(not any(now.get(k) for k in PHASE_KEYS) and base.current_binding(now) == self.baseline_binding,
                    'Current exact selected owner/phase')
            require(q['selected_binding'] == self.baseline_binding and shutil.disk_usage('/').free >= 132*2**30,
                    'Qualified owner/root132')
            qualified(pin); reader = self.baseline_reader(); reader.guard_binding(self.baseline_pid)
            identity = reader.target_identity(); reader.guard_binding(self.baseline_pid); self.previous()
            return {'qualified_for_owned_s2_placement': True, 'qualification_sha256': pin,
                    'files': q['files'], 'controller_pid': os.getpid(), 'mode': 'placement', 'arm': 'P0',
                    'output': str(out), 'baseline_identity': identity}
        def free(self):
            super().free()
            if self.private_attempted: fence.fence_collected(output, meta)
            else: memory_floor(fence.runtime.memory_available)
        def launch(self, prior, out, proof):
            require(not json.loads((HERE / 'arms.json').read_text()), 'Fresh P0 only')
            emit(HERE / 'arms.json', {'P0': {'attempted': True, 'output': str(out), 'controller_pid': os.getpid(),
                                          'qualification_sha256': pin}})
            self.private_attempted = True
            return self.launch_owned(prior, [str(R / 'venv/bin/python3.14'), '-B', str(HERE / 'placement.py'),
                '--phase', '--output', str(out), '--proof', str(proof)], 1200)
    host = Host(); host.audit_dir = meta; host.baseline_binding = base.current_binding(current)
    host.baseline_pid = host.baseline_binding['native_pid']; host.start_binding = None; host.restored_pid = None
    host.old_close_verified = False; host.private_attempted = False
    state = {'utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
             'output': str(output), 'proof_path': str(meta / 'proof.json'), 'mode': 'placement', 'arm': 'P0',
             'qualification_sha256': pin, 'controller_pid': os.getpid(), 'running_status': RUNNING,
             'complete_status': COMPLETE, 'completion_scope': 'Actual1M placement only; no inference, timing or promotion'}
    def save(value):
        emit(meta / 'state.json', value)
        if value['status'] in ('PREFLIGHT_OK', 'DEFERRED_NO_PRODUCTION_MUTATION', 'DEFERRED_BUSY_OR_MANUAL_MODEL_NO_MUTATION'): return
        now = json.loads((E / 'STATE.json').read_text()); before = copy.deepcopy(now)
        if value['status'] == 'DRAINING_ROUTER':
            require(not any(now.get(k) for k in PHASE_KEYS) and base.current_binding(now) == host.baseline_binding,
                    'Selected reservation changed before drain')
        else: require(now.get('maintenance_controller') == str(meta / 'state.json'), 'Foreign maintenance custody')
        selected = value.get('verified', {}).get('selected_identity', now['decode_optimization_current']['selected_identity'])
        value = dict(value, selected_identity=selected, start_binding=host.start_binding)
        active = value['status'] in ('DRAINING_ROUTER', RUNNING, 'CLEAN_PHASE_RESTORING_SELECTED_DS',
                                    'DEFERRED_BEFORE_PRIVATE_WINDOW_RESTORING_SELECTED_DS')
        now.update(decode_optimization_current=value, maintenance_controller=str(meta / 'state.json'),
                   active_private_phase=str(meta) if active else None, active_gpu_experiment=active,
                   production_temporarily_stopped=active or value['status'] == 'STOPPED_FOR_OFFLINE_DIAGNOSIS')
        if value.get('verified', {}).get('pending_public_probe'): now['production_verification_pending'] = str(meta / 'state.json')
        elif value.get('verified', {}).get('passed') is True:
            now['production_verification_pending'] = False; now['current_native_pid'] = selected['native_pid']
        emit(meta / 'state.json', value)
        require(json.loads((E / 'STATE.json').read_text()) == before, 'Canonical state changed before owned save')
        emit(E / 'STATE.json', now)
    try:
        result = old.coordinate(host, output, state, save, preflight_only=not run,
                                post_drain_root_free_bytes=lambda: shutil.disk_usage('/').free)
    except ResourceDeferred as exc:
        require(not host.private_attempted and host.old_close_verified and host.start_binding is None,
                'Only exact no-private resource refusal may restore here')
        emit(meta / 'resource-refusal.json', {'reason': str(exc), 'private_attempted': False})
        save(dict(state, status='CLEAN_PHASE_RESTORING_SELECTED_DS', resource_refused=True))
        host.restore_ds(); host.restore_router(); verified = host.verify()
        result = dict(state, status='RESOURCE_DEFERRED_SELECTED_RESTORED', verified=verified, private_attempted=False)
        save(result)
    emit(meta / 'result.json', result); return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--run', action='store_true')
    parser.add_argument('--phase', action='store_true'); parser.add_argument('--output'); parser.add_argument('--proof')
    args = parser.parse_args(); require(not (args.run and args.phase), 'One controller action')
    if args.phase: phase(args.output, args.proof)
    else: print(json.dumps(controller(args.run)))
