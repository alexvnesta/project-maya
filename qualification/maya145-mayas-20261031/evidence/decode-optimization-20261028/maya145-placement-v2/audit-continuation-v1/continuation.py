"""Only downstream checks missing from the first offline auditor's stale receipt-path failure.

The first auditor rc1 remains immutable. No model/window retry or regrade and no
service/inference action. Exact unchanged producer evidence and selected binding.
"""
import importlib
import hashlib
import json
from pathlib import Path
import sys
import re
HERE=Path(__file__).resolve().parent
P=HERE.parent
sys.path.insert(0,str(P))
import current_audit as original
require=original.require
same=original.same
case_contract=original.case_contract
complete_contract=original.complete_contract
case_audit=original.case_audit
fence_contract=original.fence_contract
SELECTED='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'


def restoration(state,metadata,legacy,runtime,saved,qa,q,rec):
    baseline=runtime.original_module('ms_config')
    require(baseline.BASE_NATIVE==SELECTED,'Restore consumer must use selected92, not candidateadff')
    lc=qa.dependency('lc_audit',runtime.Q/'long-cold-v1/lc_audit.py',q)
    return lc.restoration_contract(state,metadata,legacy,saved=saved,config=baseline,recorder=rec,original=original)


def failure_contract(child,log):
    require(type(child.get('returncode')) is int and child['returncode']==1 and child.get('error')=="ValueError('Child nonzero')" and child.get('cleanup')==[],'Exact first offline observer failure must be preserved')
    require('current_audit.py' in log and 'rec.bytes(metadata / name)' in log and 'ValueError: One regular evidence file' in log,'Only diagnosed missing public-ready receipt continuation')


def downstream(runtime,config,fixtures,saved,qa,q,qpin,binding,arm,rec,output,metadata,state,resources):
    expected_binding=binding
    j,lines,text=rec.json,rec.lines,rec.text
    exact,dependency=qa.exact,qa.dependency
    tokenizer_contract=qa.tokenizer_contract
    a,old,base,legacy,startup=runtime.support()
    restored = restoration(state, metadata, legacy, runtime, saved, qa, q, rec)
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



def qualified(pin):
    path=HERE/'QUALIFICATION.json';require(original.sha(path)==pin,'Exact new offline qualification')
    q=json.loads(path.read_text());require(q['manual_source_tests_read'] is True,'Manual read required')
    for name,digest in q['files'].items():require(original.sha(name)==digest,'Offline input changed: '+name)
    runtime=importlib.import_module('current_runtime')
    require(Path(runtime.__file__)==P/'current_runtime.py','Exact CPU proof consumer')
    for platform,paths in q['CPU_group']['proofs'].items():
        runtime.cpu_contract(q['CPU_group'],json.loads(Path(paths['receipt']).read_text()),json.loads(Path(paths['child']).read_text()),platform)
    require(set(q['CPU_group']['proofs'])=={'darwin','linux'},'Both physical CPU proofs')
    return q


def run(pin):
    import os,resource,importlib.util
    require(sys.platform=='linux' and sys.flags.isolated and sys.dont_write_bytecode and list(resource.getrlimit(resource.RLIMIT_CPU))==[30,30] and list(resource.getrlimit(resource.RLIMIT_AS))==[512*2**20]*2 and os.getpriority(os.PRIO_PROCESS,0)==15 and os.getpgrp()==os.getpid(),'Actual bounded physical Linux offline child')
    qnew=qualified(pin);runtime=importlib.import_module('current_runtime');config=importlib.import_module('current_config')
    require(Path(runtime.__file__)==P/'current_runtime.py' and Path(config.__file__)==P/'current_config.py','Original actual support modules')
    prefix=json.loads((HERE/'PREFIX_ROOT_REVIEW.json').read_text());require(prefix['root_manual_source_and_raw_prefix_review'] is True and prefix['first_auditor_not_regraded'] is True and prefix['first_auditor_returncode']==1,'Concrete separate prefix review')
    for name,digest in prefix['input_sha256'].items():require(original.sha(name)==digest,'Original prefix evidence changed')
    child=json.loads((P/'DTP2/child.json').read_text());log=(P/'DTP2/child.log').read_text();failure_contract(child,log)
    qpin=prefix['original_qualification_sha256'];q=runtime.qualified('compatibility',qpin)
    expected=[str(runtime.R/'venv/bin/python3.14'),'-I','-B',str(P/'current_audit.py'),'--qualification-sha256',qpin,'--arm','DTP2','--binding-json',json.dumps(prefix['expected_binding'],separators=(',',':'))]
    require(child['argv']==expected,'Exact original failed auditor invocation')
    a,old,base,legacy,startup=runtime.support();binding=prefix['expected_binding'];require(base.current_binding()==binding,'Current selected owner changed')
    fixtures=runtime.original_module('ms_fixtures');saved=runtime.original_module('ms_audit');qa=runtime.original_module('ms_quality_audit');rec=original.Recorder()
    output=Path(prefix['output']);metadata=Path(prefix['metadata']);state=rec.json(metadata/'state.json')
    result=downstream(runtime,config,fixtures,saved,qa,q,qpin,binding,'DTP2',rec,output,metadata,state,prefix['resources'])
    require(base.current_binding()==binding,'Selected owner changed during offline audit')
    for name,digest in result['evidence_sha256'].items():require(original.sha(name)==digest,'Downstream receipt changed')
    require(qualified(pin)==qnew,'Offline source/CPU qualification changed')
    result.update(first_auditor_returncode_preserved=1,original_auditor_regraded=False,downstream_continuation_only=True,no_new_native_API_or_window=True)
    with (HERE/'CONTINUED_TERMINAL_AUDIT_FIRST.json').open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    return result

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--qualification-sha256',required=True);args=parser.parse_args();result=run(args.qualification_sha256);print(json.dumps({'passed':result['passed'],'purpose':result['purpose'],'original_auditor_regraded':False}))
