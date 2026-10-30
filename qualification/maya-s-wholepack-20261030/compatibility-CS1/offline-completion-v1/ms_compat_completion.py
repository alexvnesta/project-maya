"""Pure offline completion of the saved CS1 audit's public-file schema defect.

No project imports, live checks, process execution or file writes here. A NEW
qualified bounded parent owns original/new qualification checks, genuine idle,
source origins, child limits, evidence custody, cleanup and separate publication.
Its original argument is the pinned unchanged ms_compat_audit module; q/qpin must
be the ORIGINAL admitted model qualification, not the completion qualification.
The original failed attempt, model sources and producer receipts stay untouched.
"""
from pathlib import Path
import re

PRODUCER_SHA256 = 'a1f957e9866388b65eec6a2fcbf943d1143b434f9b106d38aca7e0620aa45ff1'
PUBLIC_DEFAULT_REQUEST = {
    'model': 'deepseek-v4.1-flash-iq2-xs',
    'messages': [{'role': 'user', 'content':
        'Return exactly the text between the tags, excluding the tags. Add no punctuation or explanation.\n<answer>READY</answer>'}],
    'reasoning_effort': 'none', 'temperature': 0, 'seed': 1, 'stream': True,
}


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


def audit_saved(runtime, config, fixtures, saved, qa, q, qpin, expected_binding, *, original):
    """Saved-evidence reconciliation after the qualified parent establishes custody."""
    require = original.require
    Recorder = original.Recorder
    window_contract = original.window_contract
    case_contract = original.case_contract
    complete_contract = original.complete_contract
    case_audit = original.case_audit
    arm = 'CS1'; rec = Recorder()
    j, lines, text = rec.json, rec.lines, rec.text
    exact, dependency = qa.exact, qa.dependency
    tokenizer_contract, fence_contract = qa.tokenizer_contract, qa.fence_contract
    producer = runtime.E / 'hosting-1m-output256k-v3-20261027/capacity_mode.py'
    require(q['files'].get(str(producer)) == PRODUCER_SHA256, 'Exact public-probe producer membership required')
    a, old, base, legacy, startup = runtime.support()
    registry = j(runtime.P / 'compatibility-arms.json')[arm]
    output, metadata = runtime.owned_paths(registry['output'], 'compatibility', arm, present=True)
    state = j(metadata / 'state.json')
    require(registry.get('attempted') is True and state.get('status') == runtime.statuses('compatibility')['complete']
            and state.get('mode') == 'compatibility' and state.get('arm') == arm
            and state.get('output') == str(output) and state.get('proof_path') == str(metadata / 'proof.json')
            and type(state.get('controller_pid')) is int and state['controller_pid'] == registry.get('controller_pid'),
            'Only actual completed/restored owned compatibility arm')
    require(state['qualification_sha256'] == qpin, 'Exact admitted qualification')
    for filename in ('ms_compat_audit.py', 'ms_quality_audit.py', 'ms_audit.py'):
        require(q['files'].get(str(runtime.P / filename)) == runtime.sha(runtime.P / filename),
                'Independent auditor omitted from qualification')
    proof = j(metadata / 'proof.json')
    require(proof.get('qualified_for_owned_maya_s') is True and proof.get('mode') == 'compatibility'
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
    folder = output / 'native'; factor = config.factor('compatibility', arm); which = 'B' if factor['candidate'] else 'A'
    manifest_path = runtime.P / 'prose-fixtures-B.json'
    require(q['files'].get(str(manifest_path)) == runtime.COMPAT_SOURCE_SHA
            == runtime.sha(manifest_path), 'Actual candidate source manifest omitted')
    rec.bytes(manifest_path)
    m = runtime.compatibility_manifest()
    require(exact(j(output / 'fixtures.json'), m), 'Exact derived one-case fixture required')
    case_contract(m['cases'][0], config, runtime)
    tokenizer = tokenizer_contract(m, Path(factor['pack']), q)
    c = j(output / 'candidate-config.json'); baseline = j(runtime.P / 'base-config.json')
    config.check_config(baseline, c, folder, 'compatibility', arm)
    require(j(output / 'candidate-config.shared-settings.json') == {'max_tokens': 262144}, 'Shared default output differs')
    ready = j(folder / 'native-ready.json'); pid = ready['pid']
    require(type(pid) is int and pid > 0, 'Typed actual native PID')
    log = text(folder / 'engine.log')
    # Pure saved-data helpers only; no producer phase/entry invocation.
    controls = dependency('ms_controls', runtime.P / 'ms_controls.py', q)
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
    expected_entry = [str(runtime.R / 'venv/bin/python3.14'), '-u', '-B', str(runtime.P / 'ms_compat.py'),
                      '--entry', '--mode', 'compatibility', '--arm', arm, '--config', str(output / 'candidate-config.json'),
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
    observed_skip = skip.activation(log, 1, required=False)
    require(exact(observed_skip, result['mode1_activation'])
            and observed_skip['activation_early_rows'] == [], 'Unexpected skip state for the single short cold prompt')
    require({p.name for p in folder.glob('native-*') if p.is_dir() or p.is_symlink()} == {'native-000'}
            and not list((folder / 'tmp').glob('deepseek-native-pictures-*/req-*.dsi')), 'Extra native request or image lifetime leak')
    case = m['cases'][0]
    for name in ('request.json', 'trace-receipt.json', 'native-statistics.json', 'tokens.jsonl'):
        rec.bytes(folder / 'native-000' / name)
    for name in ('request.json', 'response.json', 'native-audit.json'):
        rec.bytes(folder / 'skip-controls' / case['id'] / name)
    row = case_audit(case, folder, pid, result['rows'][0], trace_helper.reconcile, qa, saved)
    return {'stage': 'COMPATIBILITY_TERMINAL', 'passed': True, 'mode': 'compatibility', 'arm': 'CS1',
            'qualification_sha256': qpin, 'output': str(output), 'window': str(window),
            'evidence_sha256': rec.pins, 'whole_pack_factor': factor, 'rows': [row],
            'completion_scope': 'EXISTING_CS1_PUBLIC_DEFAULT_OUTPUT_SCHEMA_COMPLETION_ONLY',
            'original_audit_regraded': False, 'model_execution_performed': False,
            'resources': resources, 'private_fence': fence, 'tokenizer_custody': tokenizer,
            'actual_native_pid': pid, 'selected_identity': restored['selected_identity'],
            'purpose': 'ONE_SHORT_COLD_LITERAL_COMPATIBILITY_SCREEN_ONLY',
            'manual_full_output_review_required': True, 'cross_pack_numeric_equivalence': False,
            'finite_logits_checked': False, 'near_full_context_or_output_tested': False,
            'general_quality_claim': False, 'performance_claim': False, 'deployment_admitted': False,
            'automatic_next_arm': False, 'retry': False}
