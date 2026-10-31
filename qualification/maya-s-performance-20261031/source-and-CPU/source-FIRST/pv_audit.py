"""Independent saved timed whole-pack evidence audit, only after selected production restoration.

No native dump, serving action or generated-code execution is performed.
This module admits no model action, comparison, retry, or deployment.
"""
import argparse
import hashlib
import importlib
import json
import math
import os
import resource
from pathlib import Path
import re
import stat
import sys

import pv_config as config
import pv_runtime as runtime
saved = runtime.original_module('ms_audit')
fixtures = runtime.original_module('ms_fixtures')

require = saved.require
read = saved.read


def exact(a, b):
    return fixtures.packed(a) == fixtures.packed(b)


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'Absolute owned evidence required')
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'Evidence path alias refused')
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'One regular evidence file required')
    return path


def j(path):
    return read(regular(path))


def lines(path):
    return [json.loads(x) for x in regular(path).read_text().splitlines()]


def dependency(name, path, q):
    path = regular(path)
    require(q['files'].get(str(path)) == runtime.sha(path), 'Audited dependency not pinned')
    loaded = sys.modules.get(name)
    require(loaded is None or Path(loaded.__file__) == path, 'Foreign cached audit dependency')
    sys.path.insert(0, str(path.parent))
    module = importlib.import_module(name)
    require(Path(module.__file__) == path, 'Audit dependency origin differs')
    return module


def fresh_idle(a, base):
    current = read(runtime.E / 'STATE.json')
    require(runtime.phase_free(current), 'Offline audit deferred: private/pending phase')
    host = a.ChunkProductionHost()
    host.start_binding = base.current_binding(current)
    require(host.idle(), 'Offline audit deferred: user work active')
    host.guard_binding(host.start_binding['native_pid'])


def tokenizer_contract(manifest, pack, q):
    """Bind the CPU encoder's explicit pack bytes and effective API template."""
    directory = fixtures.tokenizer_directory(pack)
    pins = manifest['tokenizer_source_sha256']; template = manifest['effective_template']
    require(type(pins) is dict and set(pins) == set(fixtures.TOKENIZER_NAMES),
            'Exact five tokenizer source files required')
    def pinned(path, digest):
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest)
                and q['files'].get(str(path)) == digest, 'Tokenizer/template qualification membership differs')
        require(runtime.sha(regular(path)) == digest, 'Tokenizer/template current bytes changed')
    for name, digest in pins.items(): pinned(directory / name, digest)
    pack_template = directory / 'chat_template.jinja'
    require(template['pack_template_relative_to_E'] == str(pack_template.relative_to(fixtures.E))
            and template['pack_template_sha256'] == pins['chat_template.jinja']
            and type(template['pack_template_replaced']) is bool
            and template['selection_policy'] == 'EXACT_UNCHANGED_B1_DSML_PICKER_WITH_PINNED_V41_FALLBACK',
            'Pack template source/selection contract differs')
    expected = fixtures.E / fixtures.FALLBACK_TEMPLATE if template['pack_template_replaced'] else pack_template
    require(template['effective_template_relative_to_E'] == str(expected.relative_to(fixtures.E)),
            'Foreign or unreviewed effective template')
    pinned(expected, template['effective_template_sha256'])
    if template['pack_template_replaced']:
        require(template['effective_template_sha256'] == fixtures.SUPPORT_PINS[fixtures.FALLBACK_TEMPLATE],
                'Fallback template differs from pinned API fixture')
    else:
        require(template['effective_template_sha256'] == pins['chat_template.jinja'],
                'Unswapped pack template bytes differ')
    picker = 'native-vision-v2/runtime/serve/dsml.py'
    require(template['api_picker_sha256'] == fixtures.SUPPORT_PINS[picker], 'API picker source differs')
    pinned(fixtures.E / picker, template['api_picker_sha256'])
    return {'passed': True, 'tokenizer_source_sha256': pins, 'effective_template': template}


def restoration_contract(state, metadata, legacy, q):
    # Reuse only the exact source-reviewed pure current-producer consumer.
    path = runtime.E / 'decode-optimization-20261028/maya-s-comparison-v1/long-cold-v1/lc_audit.py'
    lc = dependency('lc_audit', path, q)
    original = runtime.original_module('ms_compat_audit')
    return lc.restoration_contract(state, metadata, legacy, saved=saved, config=config,
                                   recorder=original.Recorder(), original=original)


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


def window_contract(w, output, metadata, mode, arm):
    expected=[str(runtime.R/'venv/bin/python3.14'),'-B',str(runtime.P/'pv_owner.py'),'--phase','--mode',mode,'--arm',arm,'--output',str(output),'--proof',str(metadata/'proof.json')]
    require(w.get('command')==expected and bool(w.get('continued_from'))
        and type(w.get('test_returncode')) is int and w['test_returncode']==0
        and w.get('maintenance_held') is True and w.get('maintenance_resume_allowed') is True
        and w.get('restored') is False,'Exact new timed window exit0/continuation required')


def sse_contract(response, *, tool=False):
    content='';reasoning='';finish=None;done=0;events=[];usage=None;timings=None;tools={}
    for row in response['raw']:
        line=row['line'];require(type(line) is str,'Raw line text')
        if not line.startswith('data:'):continue
        payload=line[5:].strip()
        if not payload:continue
        require(done==0,'Event after DONE or duplicate DONE')
        if payload=='[DONE]':done+=1;continue
        e=json.loads(payload);require(type(e) is dict and 'error' not in e,'Raw execution error');events.append(e)
        if e.get('usage') is not None:usage=e['usage']
        if e.get('timings') is not None:timings=e['timings']
        for choice in e.get('choices',[]):
            d=choice.get('delta') or {};c=d.get('content') or '';r=d.get('reasoning_content') or ''
            require(type(c) is str and type(r) is str,'Text deltas');content+=c;reasoning+=r
            for fragment in d.get('tool_calls') or []:
                require(tool and type(fragment.get('index')) is int and fragment['index']>=0,'Unexpected/invalid tool fragment')
                call=tools.setdefault(fragment['index'],{'id':'','type':'function','function':{'name':'','arguments':''}})
                if fragment.get('id'):
                    require(type(fragment['id']) is str and (not call['id'] or call['id']==fragment['id']),'Tool ID changed');call['id']=fragment['id']
                require(fragment.get('type','function')=='function','Tool kind')
                for key in ('name','arguments'):
                    value=(fragment.get('function') or {}).get(key) or ''
                    require(type(value) is str,'Tool fragment text');call['function'][key]+=value
            if choice.get('finish_reason'):
                require(finish is None,'Multiple terminal choices');finish=choice['finish_reason']
    expected_finish='tool_calls' if tool else 'stop'
    require(done==1 and finish==expected_finish and response.get('done') is True
        and response.get('finish_reason')==finish and response.get('content')==content
        and response.get('reasoning')==reasoning and exact(response.get('events'),events)
        and exact(response.get('usage'),usage) and exact(response.get('timings'),timings)
        and exact(response.get('tool_calls'),[tools[k] for k in sorted(tools)]),'Saved/raw SSE mismatch')
    require(bool(tools)==tool,'Expected tool state absent')
    return {'DONE':True,'finish':finish,'raw_SSE_reconstructed':True,'content_characters':len(content),'reasoning_characters':len(reasoning)}


def complete_contract(receipt, manifest, mode, arm):
    require(receipt.get('mode')==mode and receipt.get('arm')==arm and receipt.get('private_cleanup_passed') is True
        and receipt.get('not_a_promotion') is True,'Wrong arm/cleanup')
    r=receipt['arm_results'];ids=[c['id'] for c in manifest['cases']]
    require(len(ids)==len(set(ids))==3 and r.get('complete') is True and r.get('retry') is False
        and r.get('reason') is None and r.get('unrun_ids')==[] and r.get('DSI1_leftovers')==[]
        and [x['id'] for x in r['rows']]==ids,'Wrong/capped/partial/UNRUN main panel')
    require(exact(r['scores'],[{'id':i,'passed':True,'status':'NATURAL_RESULT_SOURCE_AND_STATE_PASSED'} for i in ids]),'All main scores required')
    needed=runtime.lifecycle_required(mode,arm);life=r.get('lifecycle')
    require(type(life) is dict and life.get('complete') is True and life.get('unrun_ids')==[],'Lifecycle incomplete')
    wanted=[c['id'] for c in manifest['lifecycle_cases']] if needed else []
    require(life.get('required') is needed and [x['id'] for x in life['rows']]==wanted
        and exact(life['scores'],[{'id':c['id'],'passed':True,'status':'CONFIRMED_PREFILL_CANCEL_PASSED' if c['kind']=='prefill-cancel' else 'NATURAL_RESULT_SOURCE_AND_STATE_PASSED'} for c in manifest['lifecycle_cases']] if needed else []),'Required lifecycle rows missing/failed')
    require(type(r.get('native_request_count')) is int and r['native_request_count']==3+len(wanted),'Extra/missing native request')
    return r


def normalized_followup(case, first):
    actual=fixtures.tool_followup(first);frozen=case['request']
    normalized=json.loads(json.dumps(actual))
    normalized['messages'][-2]['tool_calls'][0]['id']=fixtures.FROZEN_CALL_ID
    normalized['messages'][-1]['tool_call_id']=fixtures.FROZEN_CALL_ID
    require(exact(normalized,frozen),'Followup changed beyond actual tool-call IDs')
    return actual


def cancel_contract(control, proof, case):
    before=control.get('observed_before_cancel',{});n=proof['native'];transport=control.get('transport',{})
    require(control.get('passed') is True and control.get('replay') is False
        and control.get('classification')=='confirmed_prefill_cancel' and control.get('recovery_required') is True
        and type(control.get('client_disconnect_cancels_delta')) is int and control['client_disconnect_cancels_delta']>=1
        and before.get('state')=='reading' and before.get('first_delta') is False
        and type(before.get('read')) is int and type(before.get('total')) is int
        and before['total']==case['prompt_tokens'] and 1024<=before['read']<before['total']-64
        and n.get('finish')=='cancel' and type(n.get('generated')) is int and n['generated']==0
        and type(proof.get('observed_tokens')) is int and proof['observed_tokens']==0 and not control.get('cleanup_error')
        and proof.get('cancelled_control_or_budget') is True and transport.get('cancelled') is True
        and not transport.get('content') and not transport.get('reasoning') and not transport.get('tool_calls')
        and not control.get('intentional_budget_stop') and not control.get('budget_not_started'),
        'Actual before-first-token cancellation/ownership release absent')
    return {'confirmed_prefill_cancel':True,'generated':0,'no_speed_or_quality_metric':True}


def case_audit(case,folder,index,pid,row,reconcile,*,first=None):
    dest=folder/'skip-controls'/case['id'];trace=folder/('native-%03d'%index)
    for name in ('request.json','trace-receipt.json','native-statistics.json','tokens.jsonl'):regular(trace/name)
    request=normalized_followup(case,first) if case.get('dependency')=='ms-prose-tool' else case['request']
    require(exact(j(dest/'request.json'),request),'Actual request differs from frozen fixture')
    response=j(dest/'response.json');cancelled=case['kind']=='prefill-cancel'
    transport=response.get('transport') or {} if cancelled else response
    check=reconcile(trace,case,transport,pid,cancelled=cancelled)
    tokens=saved.emitted_ids(trace/'tokens.jsonl',check['observed_tokens'])
    recorded=j(dest/'native-audit.json')
    if cancelled:require(exact(recorded.pop('emitted_token_contract',None),tokens),'Cancelled emitted token proof differs')
    require(exact(check,recorded),'Raw T/PID/DONE/cache proof mismatch')
    require(row.get('id')==case['id'] and row.get('passed') is True,'Producer row wrong/failed')
    if cancelled:
        detail=cancel_contract(response,check,case);metric=None
    else:
        detail=sse_contract(response,tool=case['kind']=='tool')
        if case['kind']=='tool':
            fixtures.tool_followup(response)
            require(response.get('status')==200 and not response.get('cancelled') and check['native']['finish']=='stop'
                and 0<check['observed_tokens']==check['native']['generated']<32768,'Tool natural stop/count absent')
            metric=saved.metric(check)
        else:metric=saved.score_saved(case,response,check,quality=False)
    require(exact(row.get('native'),check['native']) and type(row.get('observed_tokens')) is int and row['observed_tokens']==check['observed_tokens'],'Producer native/emitted counters differ')
    require(exact(row.get('emitted_token_contract'),tokens),'Producer emitted IDs proof differs')
    if 'native_decode_tokens_per_second' in row:
        require(not cancelled and exact(row['native_decode_tokens_per_second'],check['native']['generated']/(check['native']['decode_ms']/1000)),'Producer rate differs from native counters')
    if 'client_seconds' in row:require(exact(row['client_seconds'],check.get('client_full_s')),'Producer client time differs')
    return {'id':case['id'],'passed':True,'native':check['native'],'observed_tokens':check['observed_tokens'],
        'token_contract':tokens,'transport':detail,'metric':metric,'content':transport.get('content',''),
        'reasoning':transport.get('reasoning',''),'manual_review_required':case['kind'] in ('code','prose')},response


def poststop_memory_contract(value):
    require(value.get('passed') is True and type(value.get('required_bytes')) is int
        and value['required_bytes']==88*2**30 and type(value.get('available_bytes')) is int
        and value['available_bytes']>=value['required_bytes'],'Typed actual post-stop88GiB physical memory floor required')
    return value


def audit(mode,arm):
    require(mode in ('prose','coding') and arm in ('A1','B1','B2','A2'),'Exact timed family/arm')
    a,old,base,legacy,startup=runtime.support();fresh_idle(a,base)
    registry=j(runtime.P/(mode+'-arms.json'))[arm]
    output,metadata=runtime.owned_paths(registry['output'],mode,arm,present=True);state=j(metadata/'state.json')
    require(registry.get('attempted') is True and state.get('status')==runtime.statuses(mode)['complete']
        and state.get('mode')==mode and state.get('arm')==arm and state.get('output')==str(output)
        and state.get('proof_path')==str(metadata/'proof.json') and type(state.get('controller_pid')) is int
        and state['controller_pid']==registry.get('controller_pid'),'Actual completed/restored owner required')
    pin=state['qualification_sha256'];q=runtime.qualified(mode,pin);proof=j(metadata/'proof.json')
    require(proof.get('qualified_for_owned_maya_s') is True and proof.get('mode')==mode and proof.get('arm')==arm
        and proof.get('output')==str(output) and proof.get('qualification_sha256')==pin and proof.get('files')==q['files'],'Immutable source/arm proof differs')
    window=Path(state['window']);require(window.parent==runtime.R/'windows' and re.fullmatch(r'[0-9]{8}T[0-9]{6}Z.json',window.name),'Foreign canonical window')
    window_contract(j(window),output,metadata,mode,arm);telemetry=lines(window.with_suffix('.telemetry.jsonl'))
    require(telemetry and type(telemetry[-1].get('kernel_capture_returncode')) is int
        and telemetry[-1]['kernel_capture_returncode']==0 and telemetry[-1].get('kernel_fault_lines')==[],'Kernel capture/fault proof missing')
    resources=saved.resource_contract([s for s in telemetry if 'root_free_bytes' in s],4096)
    poststop=poststop_memory_contract(j(metadata/'post-stop-memory.json'))
    restored=restoration_contract(state,metadata,legacy,q);base.binding_contract(restored['selected_identity']['start_binding'])
    require(restored.get('passed') is True,'Selected public restoration incomplete')
    factor=config.factor(mode,arm);which='B' if factor['candidate'] else 'A';mp=runtime.encoded_path(mode,which)
    require(q['files'].get(str(mp))==runtime.sha(regular(mp)),'Original fixture not qualified')
    m=j(mp);require(exact(m,runtime.performance_manifest(mode,arm)) and m['mode']==mode
        and m['context']==1048576 and m['default_output']==262144 and exact(m['policy'],fixtures.POLICY)
        and len(m['cases'])==3 and exact(j(output/'fixtures.json'),m),'Exact original timed fixture required')
    fixtures.validate_encoded(m['cases'],mode)
    if mode=='prose':fixtures.validate_encoded(m['lifecycle_cases'],'lifecycle')
    tokenizer=tokenizer_contract(m,Path(factor['pack']),q)
    folder=output/'native';c=j(output/'candidate-config.json');config.check_config(j(runtime.P/'base-config.json'),c,folder,mode,arm)
    require(j(output/'candidate-config.shared-settings.json')=={'max_tokens':262144},'Shared output differs')
    require(not list(folder.glob('logits.*')) and not (folder/'native-file-bound.json').exists(),'Timed mode dump/FSIZE forbidden')
    controls=dependency('pv_controls',runtime.P/'pv_controls.py',q)
    ready=j(folder/'native-ready.json');pid=ready['pid'];require(type(pid) is int and pid>0,'Actual native PID')
    log=regular(folder/'engine.log').read_text(errors='replace');observed=j(output/'startup-audit.json')
    actual=controls.startup(a,old,ready,j(output/'startup-health.json'),j(output/'startup-models.json'),log,q['allowed_automatic_cuts'][which])
    require(all(exact(observed.get(k),v) for k,v in actual.items()),'Saved startup/source/placement mismatch')
    require(observed.get('native_file_limit_raw','').split()[3:5]==['unlimited','unlimited'],'Actual timed native FSIZE was modified')
    proc=observed['actual_process'];config.process_contract(c,proc['actual_argv'],proc['controlled_env'],proc['actual_cgroup'],same_executable=proc['same_executable'])
    require(proc['native_sha256']==config.BASE_NATIVE and proc['native_pid']==pid and type(proc['start_ticks']) is int and proc['start_ticks']>0,'Native executable/PID identity')
    entry=j(folder/'entry-audit.json');server=j(output/'server-start.json')
    argv=[str(runtime.R/'venv/bin/python3.14'),'-u','-B',str(runtime.P/'pv_owner.py'),'--entry','--mode',mode,'--arm',arm,'--config',str(output/'candidate-config.json'),'--config-sha256',runtime.sha(output/'candidate-config.json'),'--trace-directory',str(folder)]
    require(type(server['pid']) is int and server['pid']>0 and server['argv']==argv and entry['server_pid']==server['pid']
        and type(entry['startup_retries']) is int and entry['startup_retries']==0 and type(entry['default_effort']) is int and entry['default_effort']==100
        and entry['native_sha256']==config.BASE_NATIVE and entry['config_sha256']==runtime.sha(output/'candidate-config.json')
        and entry['owned_window']==str(window) and entry['context']==1048576 and entry['output_allowance']==262144
        and exact(entry['whole_pack_factor'],factor),'Private API/config/retry0/whole-pack identity')
    saved.private_cleanup(folder,pid);cleanup=j(folder/'server-cleanup.json');closes=lines(folder/'native-close.jsonl')
    require(cleanup['server_pid']==server['pid'] and cleanup['wait_error'] is None and exact(cleanup['native_close'],closes)
        and closes[0]['server_pid']==server['pid'] and '[strata] stopped' in regular(folder/'server.log').read_text(errors='replace'),'Private API parent/raw close mismatch')
    receipt=j(output/'receipt.json');result=complete_contract(receipt,m,mode,arm)
    fence=fence_contract(j(output/'private-memory-fence.json'),receipt['resource_fence_terminal'],j(output/'private-memory-fence-restored.json'),j(metadata/'private-memory-fence-collected.json'))
    numerical=dependency('imma_numeric_controls',runtime.E/'decode-optimization-20261028/model-v1/imma_numeric_controls.py',q)
    require(numerical.owned_storage_snapshot(folder)['status']=='WITHIN_BUDGET','Private cache/log budget')
    helper=dependency('q8_audit',runtime.E/'q8-batch-v1/q8_audit.py',q)
    skip=dependency('skip_controls',runtime.E/'prefill-cache-improvements-20261027/skip_controls.py',q)
    act=skip.activation(log,1,required=True);require(exact(act,result['mode1_activation']),'Mode1 path differs')
    cases=m['cases']+(m['lifecycle_cases'] if runtime.lifecycle_required(mode,arm) else [])
    wanted=[case['prompt_tokens']-2668 for case in cases if case.get('expected_reuse')=='zero' and case['prompt_tokens']>2668 or case['kind']=='prefill-cancel']
    require(act['activation_early_rows']==wanted,'Actual cold and cancellation mode1 path differs')
    require({p.name for p in folder.glob('native-[0-9][0-9][0-9]')}=={'native-%03d'%i for i in range(len(cases))}
        and not list((folder/'tmp').glob('deepseek-native-pictures-*/req-*.dsi')),'Extra native request/image leak')
    rows=[];first=None;producer_rows=result['rows']+result['lifecycle']['rows']
    for i,case in enumerate(cases):
        row,response=case_audit(case,folder,i,pid,producer_rows[i],helper.reconcile,first=first)
        if case['kind']=='tool':first=response
        if i<3:require(all(type(row['native'].get(k)) is int and row['native'][k]>0 for k in ('drafts_offered','drafts_accepted')),'Main positive draft path absent')
        rows.append(row)
    evidence=[window,window.with_suffix('.telemetry.jsonl'),mp]+[metadata/n for n in ('state.json','proof.json','public-default-output-request.json','public-default-output-sse.txt','old-owner-close.json','post-stop-memory.json','private-memory-fence-collected.json')]
    evidence += [output/n for n in ('fixtures.json','candidate-config.json','candidate-config.shared-settings.json','startup-audit.json','startup-health.json','startup-models.json','server-start.json','receipt.json','private-memory-fence.json','private-memory-fence-restored.json')]
    evidence += [folder/n for n in ('native-ready.json','engine.log','entry-audit.json','server-cleanup.json','native-close.jsonl','server.log')]
    for i,case in enumerate(cases):
        evidence += [folder/('native-%03d'%i)/n for n in ('request.json','trace-receipt.json','native-statistics.json','tokens.jsonl')]
        evidence += [folder/'skip-controls'/case['id']/n for n in ('request.json','response.json','native-audit.json')]
    fresh_idle(a,base);require(runtime.sha(runtime.P/(mode+'-qualification.json'))==pin,'Qualification changed during audit')
    return {'passed':True,'mode':mode,'arm':arm,'qualification_sha256':pin,'output':str(output),'window':str(window),
        'evidence_sha256':{str(p):runtime.sha(regular(p)) for p in evidence},'audit_source_sha256':{p:v for p,v in q['files'].items() if p.endswith('.py')},
        'rows':rows,'cold_metric':rows[0]['metric'],'warm_metric':rows[1]['metric'],'main_metric':rows[2]['metric'],
        'resources':resources,'post_stop_memory':poststop,'private_fence':fence,'tokenizer_custody':tokenizer,'actual_native_pid':pid,'private_API_pid':server['pid'],
        'whole_pack_factor':factor,'selected_identity':restored['selected_identity'],'manual_full_output_review_required':True,
        'accepted':False,'overall_task_speed_or_general_quality_claim':False,'cross_pack_numerical_equivalence':False,'deployment_authorized':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('prose','coding'),required=True);p.add_argument('--arm',choices=('A1','B1','B2','A2'),required=True);a=p.parse_args()
    root=runtime.P/a.mode/a.arm/'offline-audit-FIRST';attempt=j(root/'dispatch-attempt.json');observed=j(root/'observed.json')
    env={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}
    require(sys.platform=='linux' and list(resource.getrlimit(resource.RLIMIT_CPU))==[30,30]
        and list(resource.getrlimit(resource.RLIMIT_AS))==[512*2**20]*2 and os.getpriority(os.PRIO_PROCESS,0)>=15
        and os.getpgrp()==os.getpid() and observed['pid']==os.getpid() and attempt['parent_pid']==os.getppid()
        and attempt['mode']==a.mode and attempt['arm']==a.arm and attempt['retry'] is False
        and all(os.environ.get(k)==v for k,v in env.items()),'Only actual bounded original audit child may consume evidence')
    dest=runtime.P/a.mode/a.arm/'terminal-audit.json';require(not dest.exists(),'Preserve FIRST terminal audit')
    result=audit(a.mode,a.arm);dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')


if __name__=='__main__':main()
