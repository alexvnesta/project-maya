"""Separately admitted fixed/current-adaptive cache policy observations.

This source is prospective until exact CPU, pack, compatibility and recovery
qualification is complete. There is no promotion or automatic next-arm loop.
"""
import argparse
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import ae_config as config
import ae_controls as controls
import ae_runtime as runtime

P, E, R, D = runtime.P, runtime.E, runtime.R, runtime.D


def helpers():
    a, old, base, legacy, startup = runtime.support()
    path = E / 'decode-optimization-20261028/model-v1'
    sys.path.insert(0, str(path))
    import imma_numeric_controls as numerical
    import imma_storage as storage
    runtime.require(Path(numerical.__file__) == path / 'imma_numeric_controls.py'
                    and Path(storage.__file__) == path / 'imma_storage.py', 'Foreign state helper origin')
    return a, old, base, legacy, startup, numerical, storage


def manifest(mode, arm):
    config.factor(mode, arm)
    return runtime.performance_manifest(mode, arm)


def read_proof(output, mode, arm, proofpath, *, present=False):
    output, metadata = runtime.owned_paths(output, mode, arm, present=present)
    runtime.require(Path(proofpath) == metadata / 'proof.json', 'Foreign phase proof path')
    proof = json.loads(Path(proofpath).read_text())
    s = json.loads((E / 'STATE.json').read_text()); active = s.get('decode_optimization_current', {})
    saved = json.loads((metadata / 'state.json').read_text())
    reg = json.loads((P / (mode + '-arms.json')).read_text()).get(arm, {})
    for value in (proof, active, saved):
        runtime.require(value.get('mode') == mode and value.get('arm') == arm and value.get('output') == str(output)
                        and value.get('qualification_sha256') == proof.get('qualification_sha256'), 'Exact mode/arm/proof custody')
    runtime.require(proof.get('qualified_for_owned_adaptive_cache') is True
                    and active.get('status') == saved.get('status') == runtime.statuses(mode)['running']
                    and s.get('active_private_phase') == str(metadata) and s.get('active_gpu_experiment') is True
                    and s.get('maintenance_controller') == str(metadata / 'state.json')
                    and reg.get('attempted') is True and reg.get('output') == str(output)
                    and active.get('controller_pid') == saved.get('controller_pid') == reg.get('controller_pid'),
                    'Single owned active controller/registry required')
    return proof


def window_contract(old, output, mode, arm, proofpath):
    path, window = old.owned_window()
    expected = [str(R / 'venv/bin/python3.14'), '-B', str(P / 'ae_owner.py'), '--phase', '--mode', mode,
                '--arm', arm, '--output', str(output), '--proof', str(proofpath)]
    runtime.require(Path(path).parent == R / 'windows' and window.get('command') == expected
                    and window.get('continued_from') and window.get('test_returncode') is None
                    and window.get('maintenance_held') is not True and window.get('restored') is False,
                    'Exact newly admitted canonical window required')
    return path


def entry(args):
    runtime.require(args.mode == 'prose', 'Separately qualified timed families only')
    a, old, base, legacy, startup, numerical, storage = helpers()
    folder = Path(args.trace_directory); output = folder.parent
    runtime.require(folder == output / 'native' and Path(args.config) == output / 'candidate-config.json', 'Exact private entry paths')
    proof = read_proof(output, args.mode, args.arm, E / 'maintenance' / output.name / 'proof.json', present=True)
    runtime.qualified(args.mode, proof['qualification_sha256'])
    window = window_contract(old, output, args.mode, args.arm, E / 'maintenance' / output.name / 'proof.json')
    runtime.require(runtime.sha(args.config) == args.config_sha256 and runtime.sha(D / 'config.json') == config.BASE_SHA,
                    'Private config/selected base changed')
    c = json.loads(Path(args.config).read_text()); config.check_config(json.loads((D / 'config.json').read_text()), c, folder, args.mode, args.arm)
    sys.path.insert(0, str(D / 'runtime-native-vision-v2')); from serve import server
    runtime.require(Path(server.__file__) == D / 'runtime-native-vision-v2/serve/server.py'
                    and runtime.sha(server.__file__) == old.SERVER_SHA, 'Exact unchanged private API required')
    spec = importlib.util.spec_from_file_location('ae_hosting_defaults', D / 'hosting_defaults.py')
    defaults = importlib.util.module_from_spec(spec); spec.loader.exec_module(defaults)
    audit = old.prepare_server(server, c, folder, defaults.install)
    # Only the owned private entry factory is composed, as in prepare_server.
    server.StrataEngine = controls.stat_trace_class(server.StrataEngine, folder)
    audit['request_scoped_STAT_observer'] = True
    runtime.require('DS4_SERVE_DUMP' not in c['env'], 'No dumps or native FSIZE hook in timed entry')
    audit.update(server_pid=os.getpid(), owned_window=str(window), native_sha256=config.BASE_NATIVE,
                 config_sha256=args.config_sha256, context=1048576, output_allowance=262144,
                 adaptive_cache_policy=config.factor(args.mode, args.arm))
    runtime.emit(folder / 'entry-audit.json', audit)
    return server.main(['--engine', 'strata', '--config', args.config, '--host', '127.0.0.1',
                        '--port', '18041', '--shutdown-timeout', '60'])


def phase(output, mode, arm, proofpath):
    runtime.require(mode == 'prose', 'Separately qualified timed families only')
    began = time.monotonic()
    a, old, base, legacy, startup, numerical, storage = helpers()
    output = Path(output); proof = read_proof(output, mode, arm, proofpath)
    q = runtime.qualified(mode, proof['qualification_sha256'])
    window_contract(old, output, mode, arm, proofpath)
    window = old.q8_phase.admission(proof, arm, output, qualification_key='qualified_for_owned_adaptive_cache')
    m = manifest(mode, arm)
    output.mkdir(exist_ok=False); folder = output / 'native'; folder.mkdir()
    for n in ('cache', 'tmp', 'cuda-cache'): (folder / n).mkdir()
    with controls.fenced_phase(output) as (fence, api_processes):
        receipt = phase_body(output, mode, arm, proof, q, window, m, folder, fence, api_processes, began,
                             a, old, numerical, storage)
    runtime.emit(output / 'receipt.json', receipt)
    return 0


def phase_body(output, mode, arm, proof, q, window, m, folder, fence, api_processes, began,
               a, old, numerical, storage):
    runtime.require(runtime.sha(P / 'profile-seed.bin') == old.q8_phase.SEED_SHA, 'Immutable arm seed changed')
    shutil.copyfile(P / 'profile-seed.bin', output / 'profile-seed-at-start.bin')
    runtime.require(runtime.sha(output / 'profile-seed-at-start.bin') == old.q8_phase.SEED_SHA, 'Initial seed snapshot changed')
    shutil.copyfile(output / 'profile-seed-at-start.bin', folder / 'expert-profile.bin')
    runtime.require(runtime.sha(folder / 'expert-profile.bin') == old.q8_phase.SEED_SHA, 'Frozen expert profile seed changed')
    c = config.make_config(json.loads((D / 'config.json').read_text()), folder, mode, arm)
    path = output / 'candidate-config.json'; runtime.emit(path, c)
    runtime.emit(output / 'candidate-config.shared-settings.json', {'max_tokens': 262144})
    runtime.emit(output / 'proof.json', proof); runtime.emit(output / 'fixtures.json', m)
    command = [str(R / 'venv/bin/python3.14'), '-u', '-B', str(P / 'ae_owner.py'), '--entry', '--mode', mode,
               '--arm', arm, '--config', str(path), '--config-sha256', runtime.sha(path), '--trace-directory', str(folder)]
    with (folder / 'server.log').open('x') as log:
        proc = subprocess.Popen(command, cwd=P, env=old.q8_phase.environment(folder, window),
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        api_processes.append(proc)  # capture before the first receipt or startup wait
        def body():
            runtime.emit(output / 'server-start.json', {'pid': proc.pid, 'argv': command})
            ready, health, models = old.q8_phase.wait_startup(proc, folder, min(began + 800, began + 1000))
            runtime.emit(output / 'startup-health.json', health); runtime.emit(output / 'startup-models.json', models)
            text = (folder / 'engine.log').read_text(errors='replace')
            which = 'B' if config.factor(mode, arm)['candidate'] else 'A'
            start = controls.startup(a, old, ready, health, models, text, q['allowed_automatic_cuts'][which])
            start['actual_process'] = controls.actual_native(c, ready['pid'], config)
            limits=(Path('/proc')/str(ready['pid'])/'limits').read_text()
            limit_row=next(line for line in limits.splitlines() if line.startswith('Max file size'))
            runtime.require(limit_row.split()[3:5] == ['unlimited','unlimited'], 'Timed native inherited unexpected FSIZE bound')
            start['native_file_limit_raw']=limit_row
            runtime.emit(output / 'startup-audit.json', start)
            import skip_controls
            from protocol import Stream, json_get, wait_for
            def requester(url, request, deadline):
                return controls.bounded_request(url, request, deadline, folder, False, stream_class=Stream,
                     observe=json_get, wait_for=wait_for, dump_snapshot=numerical.dump_snapshot,
                     storage_snapshot=numerical.owned_storage_snapshot)
            def issue(case, out, pid, deadline):
                try:
                    before = set(old.q8_phase.native_paths(out))
                    response, observation = skip_controls.issue(case, out, pid, deadline, requester=requester)
                    traces = set(old.q8_phase.native_paths(out)) - before
                    runtime.require(len(traces) == 1, 'Exactly one trace for this issued request')
                    observation['emitted_token_contract'] = controls.token_contract(next(iter(traces)) / 'tokens.jsonl', observation['observed_tokens'])
                    return response, observation
                except skip_controls.ControlBudgetStop as exc: raise controls.Incomplete(str(exc)) from exc
            cancellation = runtime.lifecycle_helper()
            fixtures = runtime.original_module('ms_fixtures')
            def cancel(case, out, pid, deadline):
                destination=Path(out)/'skip-controls'/case['id'];destination.mkdir(parents=True,exist_ok=False)
                runtime.emit(destination/'request.json',case['request']);before=set(old.q8_phase.native_paths(out))
                next_resource=[0.]
                def guard_resource():
                    if time.monotonic() >= next_resource[0]:
                        runtime.require(numerical.owned_storage_snapshot(out)['status'] != 'INCOMPLETE_HOLD'
                                        and runtime.memory_available() >= runtime.HOST_MARGIN, 'Prefill-control resource margin exhausted')
                        next_resource[0]=time.monotonic()+1
                def observe(base,path):
                    guard_resource();return cancellation.json_get(base,path)
                def progress(base):
                    guard_resource();return cancellation.progress(base)
                try: response=cancellation.prefill_cancel(old.q8_phase.BASE,case['request'],deadline,Path(out)/'engine.log',1,
                                                          observe=observe,observe_progress=progress)
                except BaseException as exc:
                    runtime.emit(destination/'transport-error.json',{'error':repr(exc),'raw':getattr(exc,'raw_transport',None),'retry':False});raise
                runtime.emit(destination/'response.json',response)
                traces=set(old.q8_phase.native_paths(out))-before
                if response.get('budget_not_started') or (response.get('intentional_budget_stop') and not traces):
                    runtime.require(not traces,'Unstarted cancellation reached native')
                    raise controls.Incomplete('UNRUN prefill cancellation before unchanged deadline')
                runtime.require(len(traces)==1,'Exact one cancelled prefill trace required')
                trace=next(iter(traces));old.q8_phase.await_trace(trace,max(deadline,time.monotonic()+5))
                observation=cancellation.reconcile(trace,case,response.get('transport') or {},pid,cancelled=True)
                observation['emitted_token_contract']=controls.token_contract(trace/'tokens.jsonl',observation['observed_tokens'])
                runtime.emit(destination/'native-audit.json',observation)
                return response,observation
            result = controls.run_panel(m, mode, arm, folder, ready['pid'], began + 1000,
                       issue=issue, cancel=cancel, fixtures=fixtures,
                       save_progress=lambda value: runtime.emit(output / 'case-progress.json', value))
            result['native_request_count'] = len(old.q8_phase.native_paths(folder))
            expected_count=9
            runtime.require(result['native_request_count'] <= expected_count
                            and (not result['complete'] or result['native_request_count']==expected_count),
                            'Unexpected native requests or missing complete main/lifecycle trace')
            text = (folder / 'engine.log').read_text(errors='replace')
            observed = skip_controls.activation(text, 1, required=result['complete'])
            used_cases=m['cases']+(m['lifecycle_cases'] if runtime.lifecycle_required(mode,arm) else [])
            wanted = [c['prompt_tokens'] - 2668 for c in used_cases
                      if (c.get('expected_reuse') == 'zero' or c['kind']=='prefill-cancel') and c['prompt_tokens'] > 2668]
            runtime.require(observed['activation_early_rows'] == (wanted if result['complete'] else wanted[:len(observed['activation_early_rows'])]),
                            'Actual prompt-skip state paths differ')
            result['mode1_activation'] = observed
            result['DSI1_leftovers'] = sorted(str(x.relative_to(folder)) for x in (folder / 'tmp').glob('deepseek-native-pictures-*/req-*.dsi'))
            result['complete'] = result['complete'] and not result['DSI1_leftovers']
            return result
        try:
            result = old.body_and_cleanup(body, lambda: old.stop_server(proc, folder, timeout=100))
            end = controls.fence_terminal(fence)
            return {'mode': mode, 'arm': arm, 'arm_results': result,
                    'seconds_including_load': time.monotonic() - began, 'private_cleanup_passed': True,
                    'resource_fence_terminal': end, 'manual_review_pending': True, 'not_a_promotion': True}
        except BaseException as exc:
            try:
                runtime.emit(output / 'phase-error.json', {'error': repr(exc), 'secondary': getattr(exc, '__notes__', []), 'retry': False})
            except BaseException as secondary: exc.add_note('Performance error receipt: ' + repr(secondary))
            raise


def reserve(mode, arm, output, proofpath):
    path = P / (mode + '-arms.json'); registry = json.loads(path.read_text())
    runtime.prerequisite(mode, arm, registry)
    registry[arm] = {'attempted': True, 'fully_reviewed': False, 'accepted': False,
                    'output': str(output), 'proof': str(proofpath), 'controller_pid': os.getpid()}
    runtime.emit(path, registry)


def controller(args):
    runtime.require(args.mode == 'prose', 'Separately qualified timed families only')
    a, old, base, legacy, startup, numerical, storage = helpers()
    current = json.loads((E / 'STATE.json').read_text()); runtime.require(runtime.phase_free(current), 'Another active phase/restoration')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out, meta = runtime.owned_paths(E / 'results' / ('adaptive-cache-' + args.mode + '-v1-' + args.arm + '-' + stamp), args.mode, args.arm)
    runtime.require(not meta.exists(), 'Fresh controller metadata required'); meta.mkdir()
    qpin = runtime.sha(P / (args.mode + '-qualification.json'))
    h = runtime.make_host(a, old, base, legacy, startup)()
    h.mode, h.arm, h.audit_dir, h.qualification_sha256 = args.mode, args.arm, meta, qpin
    h.baseline_binding = base.current_binding(current); h.baseline_pid = h.baseline_binding['native_pid']
    h.start_binding = None; h.restored_pid = None; h.private_attempted = False; h.old_close_verified = False
    h.controller_pid = os.getpid()
    def extra(output):
        q = runtime.qualified(args.mode, qpin)
        runtime.require(q['recovery_capability_prospectively_qualified'] is True, 'Prospective baseline fault recovery required')
        m = manifest(args.mode, args.arm)
        return {'case_count': len(m['cases']), 'lifecycle_count':4 if runtime.lifecycle_required(args.mode,args.arm) else 0, 'no_dump_timing':True}
    h.extra_preflight = extra
    h.reserve_attempt = lambda output, proof: reserve(args.mode, args.arm, output, proof)
    h.phase_argv = lambda output, proof: [str(R / 'venv/bin/python3.14'), '-B', str(P / 'ae_owner.py'), '--phase',
             '--mode', args.mode, '--arm', args.arm, '--output', str(output), '--proof', str(proof)]
    state = {'utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
             'mode': args.mode, 'arm': args.arm, 'output': str(out), 'proof_path': str(meta / 'proof.json'),
             'qualification_sha256': qpin, 'running_status': runtime.statuses(args.mode)['running'],
             'complete_status': runtime.statuses(args.mode)['complete'],
             'completion_scope': 'Selected fixed/adaptive policy observations; manual quality/lifecycle/performance review pending, no promotion'}
    save = runtime.saver(h, args.mode, args.arm)
    try:
        result = runtime.coordinate(old, h, out, state, save, preflight_only=not args.run)
    except runtime.ResourceAdmissionDeferred as exc:
        # This is an observed post-stop resource refusal BEFORE launch/reserve,
        # not a failed model/window or permission to resize/replay an arm.
        runtime.require(not h.private_attempted and h.old_close_verified and h.start_binding is None,
                        'Only the exact pre-window resource refusal can restore here')
        runtime.emit(meta / 'resource-admission-refusal.json', {'reason': str(exc), 'GPU_window_created': False,
                     'private_arm_attempted': False, 'prior_hold_pointer': json.loads((meta / 'state.json').read_text())})
        save(dict(state, status='CLEAN_PHASE_RESTORING_SELECTED_DS', resource_admission_refused=True))
        try:
            h.restore_ds(); h.restore_router(); verified = h.verify()
        except BaseException as primary:
            runtime.hold_owned(h, state, save, primary)
            raise
        result = dict(state, status='RESOURCE_DEFERRED_SELECTED_RESTORED', resource_admission_refused=True,
                      private_arm_attempted=False, verified=verified)
        save(result)
    runtime.emit(meta / 'result.json', result)
    return result


def main():
    p = argparse.ArgumentParser(); p.add_argument('--mode', required=True, choices=['prose'])
    p.add_argument('--arm', required=True)
    for name in ('run', 'entry', 'phase'): p.add_argument('--' + name, action='store_true')
    for name in ('output', 'proof', 'config', 'config-sha256', 'trace-directory', 'verify-pending'): p.add_argument('--' + name)
    args = p.parse_args(); config.factor(args.mode, args.arm)
    runtime.require(sum(bool(x) for x in (args.run, args.entry, args.phase, args.verify_pending)) <= 1,
                    'One explicit controller action only')
    if args.verify_pending:
        print(json.dumps(runtime.verify_pending(args.mode, args.arm, args.verify_pending)), flush=True); return 0
    if args.entry: return entry(args)
    if args.phase: return phase(args.output, args.mode, args.arm, args.proof)
    print(json.dumps(controller(args)), flush=True); return 0


if __name__ == '__main__': raise SystemExit(main())
