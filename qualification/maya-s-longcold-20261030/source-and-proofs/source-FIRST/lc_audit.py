"""Independent saved-receipt audit for one new full-policy longcold/LC1.

Pure reconciliation only. The separately qualified parent owns live custody,
exact source imports, CPU/AS/wall bounds and publication after owned cleanup.
No inference, source mutation, dumps, scan, restart, retry or advancement.
"""
from pathlib import Path
import json
import re

SOURCE_MANIFEST_SHA = 'c77c34d85a59f4696bb82397a20df97f92235a7ad752d8d3ad80ccfa38377707'
CASE_ID = 'ms-longcold-single-text'
REQUEST_SHA = '400196a1ffde50b4258720e5ded806c91c546d1c9b5affc78a55e4fc8a586487'
PROMPT_IDS_SHA = '010205e8f361a49baf7182628639afd8114a55a40224b5a06f86487d87ac3e65'
PUBLIC_DEFAULT_REQUEST = {
    'model':'deepseek-v4.1-flash-iq2-xs',
    'messages':[{'role':'user','content':'Return exactly the text between the tags, excluding the tags. Add no punctuation or explanation.\n<answer>READY</answer>'}],
    'reasoning_effort':'none','temperature':0,'seed':1,'stream':True,
}


def require(ok, why):
    if not ok:raise ValueError(why)


def exact(a,b):
    return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)


def restoration_contract(state, metadata, legacy, *, saved, config, recorder, original):
    """Same selected identity/health/close gates, actual producer request and SSE."""
    require = original.require
    verified = state['verified']; identity = verified['selected_identity']; public = verified['public']; health = verified['health']
    expected = {'native_sha256': config.BASE_NATIVE, 'config_sha256': config.BASE_SHA, 'context': 1048576,
                'output_default': 262144, 'prompt_skip_mode': 1, 'prefill_chunk': 4096, 'Q8': [1, 1],
                'DSpark': True, 'images': True, 'runtime_ablation': True, 'TP': 1, 'all_CPU_experts_RAM': True}
    require(all(type(identity.get(k)) is type(v) and identity[k] == v for k, v in expected.items()),
            'Exact selected deployment not restored')
    require(identity['start_binding']['native_pid'] == identity['native_pid']
            and public['unauthenticated_models'] == 401 and public['authenticated_models'] == 200
            and public['known_answer_passed'] is True and public['SSE_done'] is True and public['finish'] == 'stop',
            'Selected authentication/public binding proof absent')
    require(health['loaded'] is True and health['max_context'] == 1048576 and health['images'] is True
            and health['switcher']['active_model'] == health['switcher']['default_model'] == 'deepseek'
            and health['switcher']['fault'] is None, 'Selected router/default capabilities differ')
    request = recorder.json(Path(metadata) / 'public-default-output-request.json')
    require(original.same(request, PUBLIC_DEFAULT_REQUEST),
            'Exact public default-output request required, with no max_tokens override')
    saved.assembled_ready(recorder.text(Path(metadata) / 'public-default-output-sse.txt'))
    close = recorder.json(Path(metadata) / 'old-owner-close.json')
    require(close['passed'] is True and legacy.close_contract(close['binding'], close['native_close'], close['before'], close['after']),
            'Raw old selected API/native exit0 proof absent')
    return verified


def fence_contract(initial, terminal, restored, collected):
    require(type(initial.get('memory_max')) is int and initial['memory_max'] == 80 * 2**30
            and type(initial.get('swap_max')) is int and initial['swap_max'] == 0,
            'Frozen private memory/swap fence differs')
    before, after = initial['events_before'], terminal['events_after']
    require({'oom', 'oom_kill'} <= before.keys() and before.keys() <= after.keys()
            and all(type(v) is int and v >= 0 for v in before.values())
            and all(type(v) is int and v >= before.get(k, 0) for k, v in after.items()),
            'Typed monotone private memory events required')
    delta = {k: v - before.get(k, 0) for k, v in after.items()}
    require(terminal.get('passed') is True and exact(terminal['events_delta'], delta)
            and delta['oom'] == delta['oom_kill'] == 0, 'Private memory compatibility failed')
    require(restored.get('passed') is True and restored.get('same_invocation') is True
            and restored.get('children_closed') is True
            and set(restored['prior_properties']) == {'MemoryMax', 'MemorySwapMax'}
            and all(type(v) is str and (v == 'max' or v.isdecimal()) for v in restored['prior_properties'].values())
            and exact(initial['prior_properties'], restored['prior_properties'])
            and exact(restored['prior_properties'], restored['restored_properties']),
            'Private memory properties not restored after child cleanup')
    before_unit, after_unit = initial['unit_before'], restored['unit_after']
    def properties(unit):
        result = {}
        for name in ('MemoryMax', 'MemorySwapMax'):
            value = unit[name]
            require(type(value) is str and (value in ('max', 'infinity') or value.isdecimal()), 'Raw unit property invalid')
            result[name] = 'max' if value in ('max', 'infinity', str(2**64 - 1)) else str(int(value))
        return result
    require(exact(properties(before_unit), initial['prior_properties'])
            and exact(properties(after_unit), restored['restored_properties']), 'Raw memory property snapshots differ')
    require(before_unit['Transient'] == after_unit['Transient'] == 'yes'
            and re.fullmatch('[0-9a-f]{32}', before_unit['InvocationID'])
            and before_unit['InvocationID'] == after_unit['InvocationID']
            and before_unit['ControlGroup'] == after_unit['ControlGroup']
            and before_unit['FragmentPath'] == after_unit['FragmentPath'] == initial['fragment'],
            'Fence restoration belongs to another unit identity')
    require(all(collected.get(k) is True for k in ('passed', 'transient', 'unit_collected',
                                                 'fragment_absent', 'dropins_absent')),
            'Transient fence/drop-ins not observed collected')
    require(collected['original_invocation'] == before_unit['InvocationID']
            and collected['fragment'] == initial['fragment']
            and collected['owned_dropin_directory'] == initial['owned_dropin_directory'] == initial['fragment'] + '.d',
            'Collection receipt belongs to another transient unit')
    return {'passed': True, 'memory_max': initial['memory_max'], 'swap_max': 0,
            'events_delta': delta, 'prior_properties_restored': True, 'transient_collected': True}


def window_contract(w, output, metadata, runtime):
    cmd = [str(runtime.R / 'venv/bin/python3.14'), '-B', str(runtime.P / 'lc_owner.py'),
           '--phase', '--mode', 'longcold', '--arm', 'LC1', '--output', str(output), '--proof', str(metadata / 'proof.json')]
    require(w.get('command') == cmd and w.get('continued_from')
            and type(w.get('test_returncode')) is int and w['test_returncode'] == 0
            and w.get('maintenance_held') is True and w.get('maintenance_resume_allowed') is True
            and w.get('restored') is False, 'Exact clean owned longcold window required')


def case_contract(case, config, runtime):
    require(case['id']==CASE_ID and case['kind']=='json' and type(case['prompt_tokens']) is int
            and case['prompt_tokens']==8469 and case['expected_reuse']=='zero' and case['image_spans']==[]
            and exact(case['expected'],{'values':list(range(1,65))})
            and config.normalized(case['request'])==REQUEST_SHA
            and config.normalized(case['prompt_ids'])==PROMPT_IDS_SHA
            and case['request_sha256']==REQUEST_SHA and case['prompt_ids_sha256']==PROMPT_IDS_SHA,
            'Exact unchanged source-aligned8469 cold request and typedJSON expected answer')


def complete_contract(receipt, manifest):
    result=receipt['arm_results'];case=manifest['cases'][0]
    require(receipt.get('mode')=='longcold' and receipt.get('arm')=='LC1'
            and receipt.get('private_cleanup_passed') is True and receipt.get('not_a_promotion') is True
            and result.get('complete') is True and type(result.get('native_request_count')) is int
            and result['native_request_count']==1 and result.get('retry') is False
            and result.get('automatic_next_arm') is False and result.get('quality_or_performance_pass') is False
            and result.get('manual_review_required') is True and result.get('DSI1_leftovers')==[]
            and result.get('reason') is None and result.get('unrun_ids',[])==[] and len(result['rows'])==1
            and exact(result.get('scores'),[{'id':case['id'],'passed':True,'status':'LONGCOLD_JSON_SOURCE_AND_STATE_PASSED'}]),
            'Wrong/cap/partial/UNRUN or broader comparison claim remains rejected')
    return result


def case_audit(case, folder, pid, row, reconcile, qa, saved):
    dest = folder / 'skip-controls' / case['id']; trace = folder / 'native-000'
    require(qa.exact(qa.j(dest / 'request.json'), case['request']), 'Actual request differs')
    response = qa.j(dest / 'response.json'); sse = qa.sse_contract(response)
    check = reconcile(trace, case, response, pid)
    require(qa.exact(check, qa.j(dest / 'native-audit.json')), 'Saved T/PID/DONE/cache differs from raw')
    saved.score_saved(case, response, check, quality=True)
    tokens = saved.emitted_ids(trace / 'tokens.jsonl', check['observed_tokens'])
    expected = {'id': case['id'], 'passed': True, 'native': check['native'], 'observed_tokens': check['observed_tokens'],
                'native_decode_tokens_per_second': check['native']['generated'] / (check['native']['decode_ms'] / 1000),
                'client_seconds': check.get('client_full_s'), 'content_characters': sse['content_characters'],
                'reasoning_characters': sse['reasoning_characters'], 'manual_review_pending': False,
                'general_quality_or_equivalence_claim': False}
    require(qa.exact(row, expected), 'Producer row does not match independent raw evidence')
    return {'id': case['id'], 'typed_known_answer_correct': True, 'natural_stop': True, 'native': check['native'],
            'observed_tokens': check['observed_tokens'], 'token_contract': tokens, 'SSE': sse}


def audit_saved(runtime, config, fixtures, saved, qa, q, qpin, expected_binding, *, original):
    """Saved-evidence reconciliation after the qualified parent establishes custody."""
    require = original.require
    Recorder = original.Recorder
    arm = 'LC1'; rec = Recorder()
    j, lines, text = rec.json, rec.lines, rec.text
    exact, dependency = qa.exact, qa.dependency
    tokenizer_contract = qa.tokenizer_contract
    producer = runtime.E / 'hosting-1m-output256k-v3-20261027/capacity_mode.py'
    require(q['files'].get(str(producer)) == 'a1f957e9866388b65eec6a2fcbf943d1143b434f9b106d38aca7e0620aa45ff1', 'Exact public-probe producer membership required')
    a, old, base, legacy, startup = runtime.support()
    registry = j(runtime.P / 'longcold-arms.json')[arm]
    output, metadata = runtime.owned_paths(registry['output'], 'longcold', arm, present=True)
    state = j(metadata / 'state.json')
    require(registry.get('attempted') is True and state.get('status') == runtime.statuses('longcold')['complete']
            and state.get('mode') == 'longcold' and state.get('arm') == arm
            and state.get('output') == str(output) and state.get('proof_path') == str(metadata / 'proof.json')
            and type(state.get('controller_pid')) is int and state['controller_pid'] == registry.get('controller_pid'),
            'Only actual completed/restored owned longcold arm')
    require(state['qualification_sha256'] == qpin, 'Exact admitted qualification')
    for filename in ('lc_audit.py','lc_runtime.py','lc_config.py','lc_controls.py','lc_owner.py','lc_audit_dispatch.py'):
        require(q['files'].get(str(runtime.P / filename)) == runtime.sha(runtime.P / filename),
                'Independent auditor omitted from qualification')
    proof = j(metadata / 'proof.json')
    require(proof.get('qualified_for_owned_maya_s') is True and proof.get('mode') == 'longcold'
            and proof.get('arm') == arm and proof.get('output') == str(output)
            and proof.get('qualification_sha256') == qpin and proof.get('files') == q['files'],
            'Immutable arm/source proof differs')
    window = Path(state['window'])
    require(window.parent == runtime.R / 'windows' and re.fullmatch(r'[0-9]{8}T[0-9]{6}Z.json', window.name),
            'Foreign canonical window receipt')
    window_contract(j(window), output, metadata, runtime)
    telemetry = lines(window.with_suffix('.telemetry.jsonl'))
    require(telemetry and type(telemetry[-1].get('kernel_capture_returncode')) is int
            and telemetry[-1]['kernel_capture_returncode'] == 0 and telemetry[-1].get('kernel_fault_lines') == [],
            'Kernel capture/fault proof missing')
    resources = saved.resource_contract([s for s in telemetry if 'root_free_bytes' in s], 4096)
    restored = restoration_contract(state, metadata, legacy, saved=saved, config=config,
                                    recorder=rec, original=original)
    base.binding_contract(restored['selected_identity']['start_binding'])
    require(restored.get('passed') is True and exact(restored['selected_identity']['start_binding'], expected_binding),
            'Restoration must match the fresh current selected binding')
    folder = output / 'native'; factor = config.factor('longcold', arm); which = 'B' if factor['candidate'] else 'A'
    manifest_path = runtime.Q / 'model-v1/quality-fixtures-B.json'
    require(q['files'].get(str(manifest_path)) == SOURCE_MANIFEST_SHA
            == runtime.sha(manifest_path), 'Actual candidate source manifest omitted')
    rec.bytes(manifest_path)
    m = runtime.longcold_manifest()
    require(exact(j(output / 'fixtures.json'), m), 'Exact derived one-case fixture required')
    case_contract(m['cases'][0], config, runtime)
    tokenizer = tokenizer_contract(m, Path(factor['pack']), q)
    c = j(output / 'candidate-config.json'); baseline = j(runtime.P / 'base-config.json')
    config.check_config(baseline, c, folder, 'longcold', arm)
    require(j(output / 'candidate-config.shared-settings.json') == {'max_tokens': 262144}, 'Shared default output differs')
    ready = j(folder / 'native-ready.json'); pid = ready['pid']
    require(type(pid) is int and pid > 0, 'Typed actual native PID')
    log = text(folder / 'engine.log')
    # Pure saved-data helpers only; no producer phase/entry invocation.
    controls = dependency('lc_controls', runtime.P / 'lc_controls.py', q)
    observed = j(output / 'startup-audit.json')
    actual = controls.startup(a, old, ready, j(output / 'startup-health.json'),
                              j(output / 'startup-models.json'), log, q['allowed_automatic_cuts'][which])
    require(all(exact(observed.get(k), v) for k, v in actual.items()), 'Saved startup source/placement differs')
    proc = observed['actual_process']
    config.process_contract(c, proc['actual_argv'], proc['controlled_env'], proc['actual_cgroup'], same_executable=proc['same_executable'])
    group = proc['actual_cgroup'].strip().splitlines()
    require(len(group) == 1 and group[0].startswith('0::/')
            and group[0].split('/')[-1] == 'strata-deepseek-window.service'
            and proc['native_sha256'] == config.BASE_NATIVE and proc['native_pid'] == pid
            and type(proc['start_ticks']) is int and proc['start_ticks'] > 0, 'Exact native executable/cgroup identity absent')
    entry = j(folder / 'entry-audit.json'); server = j(output / 'server-start.json')
    expected_entry = [str(runtime.R / 'venv/bin/python3.14'), '-u', '-B', str(runtime.P / 'lc_owner.py'),
                      '--entry', '--mode', 'longcold', '--arm', arm, '--config', str(output / 'candidate-config.json'),
                      '--config-sha256', runtime.sha(output / 'candidate-config.json'), '--trace-directory', str(folder)]
    require(type(server['pid']) is int and server['pid'] > 0 and server['argv'] == expected_entry
            and entry['server_pid'] == server['pid'] and type(entry['startup_retries']) is int and entry['startup_retries'] == 0
            and type(entry['default_effort']) is int and entry['default_effort'] == 100 and entry['native_sha256'] == config.BASE_NATIVE
            and entry['config_sha256'] == runtime.sha(output / 'candidate-config.json')
            and entry['owned_window'] == str(window) and entry['context'] == 1048576
            and entry['output_allowance'] == 262144 and exact(entry['whole_pack_factor'], factor),
            'Private API/config/retry0/whole-pack identity differs')
    rec.bytes(folder / 'server-cleanup.json'); rec.bytes(folder / 'native-close.jsonl')
    saved.private_cleanup(folder, pid)
    cleanup = j(folder / 'server-cleanup.json'); closes = lines(folder / 'native-close.jsonl')
    require(cleanup['server_pid'] == server['pid'] and cleanup['wait_error'] is None
            and exact(cleanup['native_close'], closes)
            and closes[0]['server_pid'] == server['pid']
            and '[strata] stopped' in text(folder / 'server.log'),
            'Private raw API/native parent closure differs')
    helper = runtime.E / 'decode-optimization-20261028/model-v1'
    numerical = dependency('imma_numeric_controls', helper / 'imma_numeric_controls.py', q)
    receipt = j(output / 'receipt.json'); result = complete_contract(receipt, m)
    fence = fence_contract(j(output / 'private-memory-fence.json'), receipt['resource_fence_terminal'],
                           j(output / 'private-memory-fence-restored.json'), j(metadata / 'private-memory-fence-collected.json'))
    require(numerical.owned_storage_snapshot(folder)['status'] == 'WITHIN_BUDGET', 'Closed cache/log budget failed')
    require(not list(folder.glob('logits*.f32')) and not (folder / 'native-file-bound.json').exists(),
            'Compatibility must not produce logits or use a native dump hook')
    trace_helper = dependency('q8_audit', runtime.E / 'q8-batch-v1/q8_audit.py', q)
    skip = dependency('skip_controls', runtime.E / 'prefill-cache-improvements-20261027/skip_controls.py', q)
    observed_skip = skip.activation(log, 1, required=True)
    require(exact(observed_skip, result['mode1_activation'])
            and observed_skip['activation_early_rows'] == [5801], 'Unexpected skip state for the single long cold prompt')
    require({p.name for p in folder.glob('native-*') if p.is_dir() or p.is_symlink()} == {'native-000'}
            and not list((folder / 'tmp').glob('deepseek-native-pictures-*/req-*.dsi')), 'Extra native request or image lifetime leak')
    case = m['cases'][0]
    for name in ('request.json', 'trace-receipt.json', 'native-statistics.json', 'tokens.jsonl'):
        rec.bytes(folder / 'native-000' / name)
    for name in ('request.json', 'response.json', 'native-audit.json'):
        rec.bytes(folder / 'skip-controls' / case['id'] / name)
    row = case_audit(case, folder, pid, result['rows'][0], trace_helper.reconcile, qa, saved)
    return {'stage': 'LONGCOLD_TERMINAL', 'passed': True, 'mode': 'longcold', 'arm': 'LC1',
            'qualification_sha256': qpin, 'output': str(output), 'window': str(window),
            'evidence_sha256': rec.pins, 'whole_pack_factor': factor, 'rows': [row],
            'completion_scope': 'SINGLE_UNCHANGED_COLD_LONG_REQUEST_ONLY',
            'resources': resources, 'private_fence': fence, 'tokenizer_custody': tokenizer,
            'actual_native_pid': pid, 'selected_identity': restored['selected_identity'],
            'purpose': 'ONE_COLD_LONG_COMPATIBILITY_SCREEN_NOT_A_COMPARISON',
            'manual_full_output_review_required': True, 'cross_pack_numeric_equivalence': False,
            'finite_logits_checked': False, 'near_full_context_or_output_tested': False,
            'general_quality_claim': False, 'performance_claim': False, 'deployment_admitted': False,
            'automatic_next_arm': False, 'retry': False}
