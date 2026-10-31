"""One unchanged natural prose request; preliminary decode observation, no comparative gain or promotion.

This source is prospective until exact CPU, pack, compatibility and recovery
qualification is complete. There is no promotion or automatic next-arm loop.
"""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import current_config as config
import current_controls as controls
import current_runtime as runtime

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
    runtime.require(mode == 'decode' and arm in ('PTP2','PTP1'), 'Separately admitted new native compatibility only')
    return runtime.compatibility_manifest()


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
    runtime.require(proof.get('qualified_for_owned_maya_s') is True
                    and active.get('status') == saved.get('status') == runtime.statuses(mode)['running']
                    and s.get('active_private_phase') == str(metadata) and s.get('active_gpu_experiment') is True
                    and s.get('maintenance_controller') == str(metadata / 'state.json')
                    and reg.get('attempted') is True and reg.get('output') == str(output)
                    and active.get('controller_pid') == saved.get('controller_pid') == reg.get('controller_pid'),
                    'Single owned active controller/registry required')
    return proof


def window_contract(old, output, mode, arm, proofpath):
    path, window = old.owned_window()
    expected = [str(R / 'venv/bin/python3.14'), '-B', str(P / 'current_compat.py'), '--phase', '--mode', mode,
                '--arm', arm, '--output', str(output), '--proof', str(proofpath)]
    runtime.require(Path(path).parent == R / 'windows' and window.get('command') == expected
                    and window.get('continued_from') and window.get('test_returncode') is None
                    and window.get('maintenance_held') is not True and window.get('restored') is False,
                    'Exact newly admitted canonical window required')
    return path


def entry(args):
    runtime.require(args.mode == 'decode' and args.arm in ('PTP2','PTP1'), 'This frozen owner is short compatibility only')
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
    spec = importlib.util.spec_from_file_location('maya_s_hosting_defaults', D / 'hosting_defaults.py')
    defaults = importlib.util.module_from_spec(spec); spec.loader.exec_module(defaults)
    audit = old.prepare_server(server, c, folder, defaults.install)
    server.StrataEngine=runtime.stat_observer().stat_trace_class(server.StrataEngine,folder)
    runtime.require(all(k not in c['env'] for k in ('DS4_SERVE_DUMP','DS4_ROUND_LOG')), 'No numerical dump or native FSIZE hook in compatibility')
    audit.update(server_pid=os.getpid(), owned_window=str(window), native_sha256=config.BASE_NATIVE,
                 config_sha256=args.config_sha256, context=1048576, output_allowance=262144,
                 whole_pack_factor=config.factor(args.mode, args.arm))
    runtime.emit(folder / 'entry-audit.json', audit)
    return server.main(['--engine', 'strata', '--config', args.config, '--host', '127.0.0.1',
                        '--port', '18041', '--shutdown-timeout', '60'])


def phase(output, mode, arm, proofpath):
    runtime.require(mode == 'decode' and arm in ('PTP2','PTP1'), 'This frozen phase is short compatibility only')
    began = time.monotonic()
    a, old, base, legacy, startup, numerical, storage = helpers()
    output = Path(output); proof = read_proof(output, mode, arm, proofpath)
    q = runtime.qualified(mode, proof['qualification_sha256'])
    window_contract(old, output, mode, arm, proofpath)
    window = old.q8_phase.admission(proof, arm, output, qualification_key='qualified_for_owned_maya_s')
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
    shutil.copyfile(D / 'profile-seed.bin', folder / 'expert-profile.bin')
    runtime.require(runtime.sha(folder / 'expert-profile.bin') == old.q8_phase.SEED_SHA, 'Frozen expert profile seed changed')
    c = config.make_config(json.loads((D / 'config.json').read_text()), folder, mode, arm)
    path = output / 'candidate-config.json'; runtime.emit(path, c)
    runtime.emit(output / 'candidate-config.shared-settings.json', {'max_tokens': 262144})
    runtime.emit(output / 'proof.json', proof); runtime.emit(output / 'fixtures.json', m)
    command = [str(R / 'venv/bin/python3.14'), '-u', '-B', str(P / 'current_compat.py'), '--entry', '--mode', mode,
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
            start = controls.startup(a, old, ready, health, models, text, config.variant(mode,arm))
            start['actual_process'] = controls.actual_native(c, ready['pid'], config)
            start['native_file_limit']=controls.native_file_limit(ready['pid'])
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
                    observation['DSpark_execution']=controls.native_stat(next(iter(traces)),pid,required=True)
                    return response, observation
                except skip_controls.ControlBudgetStop as exc: raise controls.Incomplete(str(exc)) from exc
            result = run_one(m['cases'][0], folder, ready['pid'], began + 1000, issue=issue,
                             save_progress=lambda value: runtime.emit(output / 'case-progress.json', value))
            result['native_request_count'] = len(old.q8_phase.native_paths(folder))
            if result['complete']:result['drafter_execution']=controls.native_stat(folder/'native-000',ready['pid'],required=True)
            runtime.require(result['native_request_count'] in (0, 1)
                            and (not result['complete'] or result['native_request_count'] == 1),
                            'Compatibility permits at most one native request, exactly one on success')
            # Current upstream forward_chunks only sets Run::yoco (initially -1)
            # when n-keep >= kYocoMin. This169token cold prose prompt cannot exercise it.
            text = (folder / 'engine.log').read_text(errors='replace')
            observed = skip_controls.activation(text, 1, required=False)
            runtime.require(observed['activation_early_rows'] == [], 'Unexpected long-prompt skip in short screen')
            result['mode1_activation'] = observed
            runtime.require(not list(folder.glob('logits*.f32')), 'No dump files in compatibility screen')
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
            except BaseException as secondary: exc.add_note('Compatibility error receipt: ' + repr(secondary))
            raise


def run_one(case, folder, pid, deadline, *, issue, save_progress=lambda value: None):
    runtime.require(case['id'] == runtime.COMPAT_CASE_ID and case['kind'] == 'prose'
                    and type(case['prompt_tokens']) is int and case['prompt_tokens'] == 169 and case['expected_reuse'] == 'zero'
                    and case['expected_last_sentence'] == 'That is how the lookup finds its way.'
                    and config.normalized(case['request']) == '5be1101ce505f65a63ca67719f88b11cd3797bd276da32b02eedee0594f296b7'
                    and config.normalized(case['prompt_ids']) == '9c2ae1f025497f4ec8183c4ce667b6c5947816f74b36e4cd6843a6e8905d0d5c',
                    'One frozen short cold case')
    value = {'complete': False, 'scores': [{'id': case['id'], 'passed': False, 'status': 'UNRUN'}],
             'rows': [], 'retry': False, 'automatic_next_arm': False,
             'quality_or_performance_pass': False, 'manual_review_required': True}
    save_progress(value)
    try:
        value['scores'][0]['status'] = 'ISSUED_REVIEW_PENDING'; save_progress(value)
        response, proof = issue(case, folder, pid, deadline)
        row = controls.score(case, response, proof, quality=False)
        runtime.require(proof['native']['decode_ms']>0,'Positive native decode measurement required')
        if not response.get('content','').strip().endswith(case['expected_last_sentence']):
            raise controls.Incomplete('Exact requested natural prose ending required')
        runtime.require(proof.get('prompt_tokens') == 169 and type(proof['prompt_tokens']) is int,
                        'Actual prompt must match frozen candidate encoding')
        value['rows'] = [row]; value['complete'] = True
        value['scores'][0].update(passed=True, status='PROSE_NATURAL_SOURCE_AND_STATE_PASSED')
    except controls.Incomplete as exc:
        value['scores'][0].update(status='INCOMPLETE_HOLD', reason=str(exc))
    except BaseException as exc:
        value['scores'][0].update(status='FAULT_HOLD', reason=repr(exc))
        try: save_progress(value)
        except BaseException as secondary: exc.add_note('Compatibility progress: ' + repr(secondary))
        raise
    save_progress(value)
    return value


def reserve(mode, arm, output, proofpath):
    path = P / (mode + '-arms.json'); registry = json.loads(path.read_text())
    runtime.prerequisite(mode, arm, registry)
    registry[arm] = {'attempted': True, 'fully_reviewed': False, 'accepted': False,
                    'output': str(output), 'proof': str(proofpath), 'controller_pid': os.getpid()}
    runtime.emit(path, registry)


def controller(args):
    runtime.require(args.mode == 'decode' and args.arm in ('PTP2','PTP1'), 'This frozen owner is short compatibility only')
    a, old, base, legacy, startup, numerical, storage = helpers()
    current = json.loads((E / 'STATE.json').read_text()); runtime.require(runtime.phase_free(current), 'Another active phase/restoration')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out, meta = runtime.owned_paths(E / 'results' / ('maya145-decode-mayas-' + config.variant(args.mode,args.arm) + '-' + stamp), args.mode, args.arm)
    runtime.require(not meta.exists(), 'Fresh controller metadata required'); meta.mkdir()
    qpin = runtime.sha(runtime.qualification_path())
    h = runtime.make_host(a, old, base, legacy, startup)()
    h.mode, h.arm, h.audit_dir, h.qualification_sha256 = args.mode, args.arm, meta, qpin
    h.baseline_binding = base.current_binding(current); h.baseline_pid = h.baseline_binding['native_pid']
    h.start_binding = None; h.restored_pid = None; h.private_attempted = False; h.old_close_verified = False
    h.controller_pid = os.getpid()
    def extra(output):
        q = runtime.qualified(args.mode, qpin)
        runtime.require(q['recovery_capability_prospectively_qualified'] is True, 'Prospective baseline fault recovery required')
        m = manifest(args.mode, args.arm)
        return {'case_count': len(m['cases']), 'one_unchanged_169token_prose': True, 'no_claim_of_prior_Maya_S_fit': True}
    h.extra_preflight = extra
    h.reserve_attempt = lambda output, proof: reserve(args.mode, args.arm, output, proof)
    h.phase_argv = lambda output, proof: [str(R / 'venv/bin/python3.14'), '-B', str(P / 'current_compat.py'), '--phase',
             '--mode', args.mode, '--arm', args.arm, '--output', str(output), '--proof', str(proof)]
    state = {'utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
             'mode': args.mode, 'arm': args.arm, 'output': str(out), 'proof_path': str(meta / 'proof.json'),
             'qualification_sha256': qpin, 'running_status': runtime.statuses(args.mode)['running'],
             'complete_status': runtime.statuses(args.mode)['complete'],
             'completion_scope': 'One unchanged169token fullcap prose request; preliminary timing only, no comparison, general quality or promotion'}
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
    p = argparse.ArgumentParser(); p.add_argument('--mode', required=True, choices=['decode'])
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
