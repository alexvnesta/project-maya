"""Independent saved receipt audit for new native145 compatibility only.

No model/service actions. Caller provides bounded CPU30/AS512/wall90/nice15,
source-qualified child supervision and exact current restored binding.
"""
import hashlib
import json
from pathlib import Path
import re
MAX_EVIDENCE_BYTES=32*2**20


def require(value, why):
    if not value: raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with regular(path).open('rb') as f:
        for block in iter(lambda: f.read(2**20), b''): h.update(block)
    return h.hexdigest()


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts
            and all(not x.is_symlink() for x in (path, *path.parents)), 'Canonical nonalias path')
    require(path.is_file() and path.stat().st_nlink == 1, 'One regular evidence file')
    return path


def pairs(rows):
    result = {}
    for k, v in rows:
        require(k not in result, 'Duplicate JSON member'); result[k] = v
    return result


def same(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':'), allow_nan=False) == json.dumps(b, sort_keys=True, separators=(',', ':'), allow_nan=False)


def parse(data):
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


class Recorder:
    """Hash the exact small bytes read, never caches, tensors or logits."""
    def __init__(self): self.pins = {}; self.total = 0
    def bytes(self, path):
        path = regular(path); require(path.stat().st_size <= MAX_EVIDENCE_BYTES, 'Saved receipt too large for bounded audit')
        with path.open('rb') as f: data = f.read(MAX_EVIDENCE_BYTES + 1)
        require(len(data) <= MAX_EVIDENCE_BYTES, 'Growing receipt exceeds audit bound')
        pin = hashlib.sha256(data).hexdigest(); key = str(path)
        require(key not in self.pins or self.pins[key] == pin, 'Receipt changed during read')
        if key not in self.pins: self.total += len(data)
        require(self.total <= 128 * 2**20, 'Bounded small-evidence inventory exceeded')
        self.pins[key] = pin; return data
    def json(self, path): return parse(self.bytes(path))
    def text(self, path): return self.bytes(path).decode(errors='replace')
    def lines(self, path): return [parse(x) for x in self.bytes(path).splitlines() if x.strip()]


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
    require(terminal.get('passed') is True and same(terminal['events_delta'], delta)
            and delta['oom'] == delta['oom_kill'] == 0, 'Private memory compatibility failed')
    require(restored.get('passed') is True and restored.get('same_invocation') is True
            and restored.get('children_closed') is True
            and set(restored['prior_properties']) == {'MemoryMax', 'MemorySwapMax'}
            and all(type(v) is str and (v == 'max' or v.isdecimal()) for v in restored['prior_properties'].values())
            and same(initial['prior_properties'], restored['prior_properties'])
            and same(restored['prior_properties'], restored['restored_properties']),
            'Private memory properties not restored after child cleanup')
    before_unit, after_unit = initial['unit_before'], restored['unit_after']
    def properties(unit):
        result = {}
        for name in ('MemoryMax', 'MemorySwapMax'):
            value = unit[name]
            require(type(value) is str and (value in ('max', 'infinity') or value.isdecimal()), 'Raw unit property invalid')
            result[name] = 'max' if value in ('max', 'infinity', str(2**64 - 1)) else str(int(value))
        return result
    installed=initial.get('unit_installed') or {}
    require(initial.get('installed') is True and initial.get('mutation_attempted') is True
            and type(initial.get('initial_current')) is int and 0<=initial['initial_current']<80*2**30,
            'Actual successful fence install/readback required')
    require(same(properties(installed),{'MemoryMax':str(80*2**30),'MemorySwapMax':'0'})
            and all(installed.get(k)==before_unit.get(k) for k in ('Transient','InvocationID','ControlGroup','FragmentPath')),
            'Raw installed80GiB/zero-swap fence identity differs')
    require(same(properties(before_unit), initial['prior_properties'])
            and same(properties(after_unit), restored['restored_properties']), 'Raw memory property snapshots differ')
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


def window_contract(w, output, metadata, runtime, arm):
    cmd = [str(runtime.R / 'venv/bin/python3.14'), '-B', str(runtime.P / 'current_compat.py'),
           '--phase', '--mode', 'compatibility', '--arm', arm, '--output', str(output), '--proof', str(metadata / 'proof.json')]
    require(w.get('command') == cmd and w.get('continued_from')
            and type(w.get('test_returncode')) is int and w['test_returncode'] == 0
            and w.get('maintenance_held') is True and w.get('maintenance_resume_allowed') is True
            and w.get('restored') is False, 'Exact clean owned compatibility window required')


def case_contract(case, config, runtime):
    require(case['id'] == runtime.COMPAT_CASE_ID and case['kind'] == 'literal'
            and type(case['prompt_tokens']) is int and case['prompt_tokens'] == 44
            and case['expected_reuse'] == 'zero' and case['expected'] == 'RECOVERED_Q8_LITERAL'
            and config.normalized(case['request']) == 'da06aa190c3a42a5abe68d10e6c86a233ce09a3b8a7e000282031c08dec8375e'
            and config.normalized(case['prompt_ids']) == '0f51ef0261a3e5cb81f4434bfe4a056af8f1e6d040fbe186370c553ba24beff7',
            'Exact 44-token source-aligned one-shot literal')


def complete_contract(receipt, manifest, arm):
    r = receipt['arm_results']; case = manifest['cases'][0]
    require(receipt.get('mode') == 'compatibility' and receipt.get('arm') == arm
            and receipt.get('private_cleanup_passed') is True and receipt.get('not_a_promotion') is True
            and r.get('complete') is True and type(r.get('native_request_count')) is int and r['native_request_count'] == 1
            and r.get('retry') is False and r.get('automatic_next_arm') is False
            and r.get('quality_or_performance_pass') is False and r.get('manual_review_required') is True
            and r.get('DSI1_leftovers') == [] and r.get('reason') is None and r.get('unrun_ids', []) == [] and len(r['rows']) == 1
            and same(r.get('scores'), [{'id': case['id'], 'passed': True, 'status': 'SHORT_LITERAL_SOURCE_AND_STATE_PASSED'}]),
            'Partial/failed/replayed or broader compatibility claim')
    return r


def case_audit(case, folder, pid, row, reconcile, qa, saved):
    dest = folder / 'skip-controls' / case['id']; trace = folder / 'native-000'
    require(qa.exact(qa.j(dest / 'request.json'), case['request']), 'Actual request differs')
    response = qa.j(dest / 'response.json'); sse = qa.sse_contract(response)
    check = reconcile(trace, case, response, pid)
    require(qa.exact(check, qa.j(dest / 'native-audit.json')), 'Saved T/PID/DONE/cache differs from raw')
    saved.score_saved(case, response, check, quality=False)  # Zero drafts permitted, actual counters still required.
    tokens = saved.emitted_ids(trace / 'tokens.jsonl', check['observed_tokens'])
    expected = {'id': case['id'], 'passed': True, 'native': check['native'], 'observed_tokens': check['observed_tokens'],
                'native_decode_tokens_per_second': check['native']['generated'] / (check['native']['decode_ms'] / 1000),
                'client_seconds': check.get('client_full_s'), 'content_characters': sse['content_characters'],
                'reasoning_characters': sse['reasoning_characters'], 'manual_review_pending': False,
                'general_quality_or_equivalence_claim': False}
    require(qa.exact(row, expected), 'Producer row does not match independent raw evidence')
    return {'id': case['id'], 'literal_correct': True, 'natural_stop': True, 'native': check['native'],
            'observed_tokens': check['observed_tokens'], 'token_contract': tokens, 'SSE': sse}


def audit_saved(runtime, config, fixtures, saved, qa, q, qpin, expected_binding, arm):
    """Pure saved-evidence reconciliation after run() establishes live custody."""
    config.factor('compatibility',arm); rec = Recorder()
    j, lines, text = rec.json, rec.lines, rec.text
    exact, dependency = qa.exact, qa.dependency
    tokenizer_contract = qa.tokenizer_contract
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
    for filename in ('current_audit.py', 'current_compat.py', 'current_controls.py'):
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
    window_contract(j(window), output, metadata, runtime, arm)
    telemetry = lines(window.with_suffix('.telemetry.jsonl'))
    require(telemetry and type(telemetry[-1].get('kernel_capture_returncode')) is int
            and telemetry[-1]['kernel_capture_returncode'] == 0 and telemetry[-1].get('kernel_fault_lines') == [],
            'Kernel capture/fault proof missing')
    resources = saved.resource_contract([s for s in telemetry if 'root_free_bytes' in s], 4096)
    for name in ('old-owner-close.json', 'public-ready-sse.txt'):
        rec.bytes(metadata / name)
    restored = saved.restoration_contract(state, metadata, legacy)
    base.binding_contract(restored['selected_identity']['start_binding'])
    require(restored.get('passed') is True and exact(restored['selected_identity']['start_binding'], expected_binding),
            'Restoration must match the fresh current selected binding')
    folder = output / 'native'; factor = config.factor('compatibility', arm); which = 'B' if factor['candidate'] else 'A'
    manifest_path = runtime.Q / 'model-v1/prose-fixtures-B.json'
    require(q['files'].get(str(manifest_path)) == 'd572147c2f668b7702531ec62a90b5ba9fe8e0b47ac864f05ecca8c73402c601'
            == runtime.sha(manifest_path), 'Actual candidate source manifest omitted')
    rec.bytes(manifest_path)
    m = runtime.compatibility_manifest()
    require(exact(j(output / 'fixtures.json'), m), 'Exact derived one-case fixture required')
    case_contract(m['cases'][0], config, runtime)
    tokenizer = tokenizer_contract(m, Path(factor['pack']), q)
    c = j(output / 'candidate-config.json'); baseline = j(runtime.P / 'profile-base-config.json')
    config.check_config(baseline, c, folder, 'compatibility', arm)
    require(j(output / 'candidate-config.shared-settings.json') == {'max_tokens': 262144}, 'Shared default output differs')
    ready = j(folder / 'native-ready.json'); pid = ready['pid']
    require(type(pid) is int and pid > 0, 'Typed actual native PID')
    log = text(folder / 'engine.log')
    # Pure saved-data helpers only; no producer phase/entry invocation.
    controls = dependency('current_controls', runtime.P / 'current_controls.py', q)
    observed = j(output / 'startup-audit.json')
    actual = controls.startup(a, old, ready, j(output / 'startup-health.json'),
                              j(output / 'startup-models.json'), log, config.variant('compatibility',arm))
    require(all(exact(observed.get(k), v) for k, v in actual.items()), 'Saved startup source/placement differs')
    proc = observed['actual_process']
    config.process_contract(c, proc['actual_argv'], proc['controlled_env'], proc['actual_cgroup'], same_executable=proc['same_executable'])
    group = proc['actual_cgroup'].strip().splitlines()
    require(len(group) == 1 and group[0].startswith('0::/')
            and group[0].split('/')[-1] == 'strata-deepseek-window.service'
            and proc['native_sha256'] == config.BASE_NATIVE and proc['native_pid'] == pid
            and type(proc['start_ticks']) is int and proc['start_ticks'] > 0, 'Exact native executable/cgroup identity absent')
    entry = j(folder / 'entry-audit.json'); server = j(output / 'server-start.json')
    expected_entry = [str(runtime.R / 'venv/bin/python3.14'), '-u', '-B', str(runtime.P / 'current_compat.py'),
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
    receipt = j(output / 'receipt.json'); result = complete_contract(receipt, m, arm)
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
    for name in ('request.json', 'trace-receipt.json', 'native-statistics.json', 'tokens.jsonl', 'stat-lines.jsonl','stat-receipt.json'):
        rec.bytes(folder / 'native-000' / name)
    for name in ('request.json', 'response.json', 'native-audit.json'):
        rec.bytes(folder / 'skip-controls' / case['id'] / name)
    row = case_audit(case, folder, pid, result['rows'][0], trace_helper.reconcile, qa, saved)
    drafter=controls.native_stat(folder/'native-000',pid,required=False)
    require(same(drafter,result.get('drafter_execution')),'Saved drafter execution differs from raw STAT')
    return {'stage': 'COMPATIBILITY_TERMINAL', 'passed': True, 'mode': 'compatibility', 'arm': arm,
            'qualification_sha256': qpin, 'output': str(output), 'window': str(window),
            'evidence_sha256': rec.pins, 'whole_pack_factor': factor, 'rows': [row],
            'resources': resources, 'private_fence': fence, 'tokenizer_custody': tokenizer,
            'actual_native_pid': pid, 'selected_identity': restored['selected_identity'],
            'purpose': 'ONE_SHORT_COLD_LITERAL_COMPATIBILITY_SCREEN_ONLY',
            'manual_full_output_review_required': True, 'cross_pack_numeric_equivalence': False,
            'finite_logits_checked': False, 'near_full_context_or_output_tested': False,
            'general_quality_claim': False, 'performance_claim': False, 'deployment_admitted': False,
            'automatic_next_arm': False, 'retry': False}


def audit_cpu_membership(q,root):
    import ast
    names=('current_audit.py','test_current_audit.py','run_audit_cpu.py')
    source={n:sha(Path(root)/n) for n in names}
    tree=ast.parse((Path(root)/names[1]).read_text())
    ids=sorted('test_current_audit.'+c.name+'.'+f.name for c in tree.body if isinstance(c,ast.ClassDef)
        for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'))
    require(ids and all(q['files'].get(str(Path(root)/n))==pin for n,pin in source.items())
        and any(all(g['source_sha256'].get(n)==pin for n,pin in source.items())
            and set(ids)==set(g['test_ids']) for g in q['CPU_groups']), 'Exact independent auditor CPU membership required')


def run(pin,arm,binding):
    import importlib
    import os
    import resource
    import sys
    root=Path(__file__).resolve().parent
    require(sys.platform=='linux' and sys.dont_write_bytecode and sys.flags.isolated
        and list(resource.getrlimit(resource.RLIMIT_CPU))==[30,30]
        and list(resource.getrlimit(resource.RLIMIT_AS))==[512*2**20]*2
        and os.getpriority(os.PRIO_PROCESS,0)==15 and os.getpgrp()==os.getpid(), 'Actual bounded isolated physical Linux audit child')
    env={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
        'NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}
    require(all(os.environ.get(k)==v for k,v in env.items()),'Actual child-only environment')
    path=root/'compatibility-qualification.json';require(sha(path)==pin,'Exact admitted mode qualification')
    q=Recorder().json(path)
    for name in ('current_runtime','current_config','current_controls'):
        require(q['files'].get(str(root/(name+'.py')))==sha(root/(name+'.py')),'Auditor support preimport membership')
    audit_cpu_membership(q,root)
    sys.path.insert(0,str(root));runtime=importlib.import_module('current_runtime');config=importlib.import_module('current_config')
    require(Path(runtime.__file__)==root/'current_runtime.py' and Path(config.__file__)==root/'current_config.py','Actual support origin')
    require(same(runtime.qualified('compatibility',pin),q),'Full new both-host/source qualification')
    a,old,base,legacy,startup=runtime.support()
    require(base.current_binding()==base.binding_contract(binding),'Restored selected owner changed')
    fixtures=runtime.original_module('ms_fixtures');saved=runtime.original_module('ms_audit');qa=runtime.original_module('ms_quality_audit')
    result=audit_saved(runtime,config,fixtures,saved,qa,q,pin,binding,arm)
    require(base.current_binding()==binding and same(runtime.qualified('compatibility',pin),q),'Post-audit selected/source custody')
    for name,digest in result['evidence_sha256'].items():require(sha(name)==digest,'Saved evidence changed')
    target=root/arm/'terminal-audit.json';require(target.parent.is_dir(),'Parent must precreate fresh audit leaf')
    with target.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification-sha256',required=True)
    parser.add_argument('--arm',choices=('RTP2','RTP1'),required=True)
    parser.add_argument('--binding-json',required=True)
    args=parser.parse_args();result=run(args.qualification_sha256,args.arm,parse(args.binding_json))
    print(json.dumps({'passed':result['passed'],'arm':args.arm,'purpose':result['purpose']}))
