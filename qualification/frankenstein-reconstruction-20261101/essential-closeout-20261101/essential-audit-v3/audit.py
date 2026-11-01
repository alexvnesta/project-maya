"""Independent saved native/token/window closure checks; no inference or grading execution."""
import hashlib
import json
import math
from pathlib import Path


def require(ok,why):
    if not ok:raise ValueError(why)


def native_case(request,trace,stats,tokens,case,pid,cancelled=False):
    require(request.get('native_pid')==trace.get('native_pid')==pid and type(pid) is int and pid>1,'Exact native identity')
    require(request['ids']==case['prompt_ids'] and request['max_new']==32768 and
        stats['prompt_tokens']==case['prompt_tokens']==len(request['ids']),'Actual frozen prompt/cap')
    require(trace.get('DONE_observed') is True and trace.get('error') is None and
        trace['T_lines']==stats['generated']==len(tokens),'Complete native DONE/token conservation')
    require(stats['finish']==('cancel' if cancelled else 'stop') and
        (len(tokens)==0 if cancelled else 1<len(tokens)<32768),'Natural or exact intended zero-generation cancellation')
    previous=-1.
    for row in tokens:
        require(set(row)=={'token','seconds'} and type(row['token']) is int and 0<=row['token']<129280 and
            type(row['seconds']) in (int,float) and math.isfinite(row['seconds']) and 0<=row['seconds'] and row['seconds']>=previous,'Actual token sequence/clock')
        previous=row['seconds']
    sampling=request.get('sampling') or {}
    require(all(sampling.get(k)==v for k,v in [('temperature',1.),('top_p',1.),('seed',1)]),'Same actual sampling')
    for key in ('prompt_ms','decode_ms'):
        require(type(stats.get(key)) in (int,float) and math.isfinite(stats[key]) and stats[key]>=0,'Finite native clocks')
    require(type(stats.get('reused')) is int and 0<=stats['reused']<=case['prompt_tokens'],'Actual cache reuse')
    if not cancelled:
        want=0 if case.get('expected_reuse')=='zero' else case['prompt_tokens']-1 if case.get('expected_reuse') else None
        require(want is None or stats['reused']==want,'Frozen useful prefix reuse')
    require(type(stats.get('drafts_offered')) is int and type(stats.get('drafts_accepted')) is int and
        0<=stats['drafts_accepted']<=stats['drafts_offered'],'Native drafter counters')
    return {'native_pid':pid,'prompt_tokens':case['prompt_tokens'],'generated':len(tokens),'native':stats,
        'ordered_tokens_sha256':hashlib.sha256(json.dumps([x['token'] for x in tokens],separators=(',',':')).encode()).hexdigest()}


def terminal(api,window,telemetry,fence,collection,restoration,arm):
    require(api.get('passed') is True and api.get('server_returncode')==0 and api.get('grace_timeout') is False and
        api.get('wait_error') is None and api.get('application_stopped') is True,'Actual private API exit0/graceful stop')
    rows=[x for x in api['native_close'] if x.get('native_pid') is not None]
    require(len(rows)==1 and rows[0]['native_pid']==api['native_ready_pid'] and rows[0].get('closed') is True and
        rows[0].get('returncode')==0,'Actual private native close0')
    require(window.get('test_returncode')==0 and window.get('maintenance_resume_allowed') is True and
        window.get('maintenance_held') is True and window.get('maintenance_root_window')=='20261025T032914Z.json',
        'Actual canonical window0/owned continuation')
    require(telemetry.get('kernel_capture_returncode')==0 and telemetry.get('kernel_fault_lines')==[], 'Actual kernel closure')
    require(fence.get('passed') is True and fence.get('children_closed') is True and fence.get('same_invocation') is True and
        collection.get('passed') is True and collection.get('unit_collected') is True and
        collection.get('fragment_absent') is True and collection.get('dropins_absent') is True,'Owned memory fence restored/collected')
    require(restoration.get('status')=='S2_ESSENTIAL3_SELECTED4096_RESTORED' and restoration.get('arm')==arm and
        restoration['verified'].get('passed') is True,'Independent completed selected restoration')
    identity=restoration['verified']['selected_identity'];public=restoration['verified']['public']
    require(identity.get('native_sha256')=='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1' and
        identity.get('config_sha256')=='c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa' and
        identity.get('context')==1048576 and identity.get('output_default')==262144 and identity.get('DSpark') is True and
        identity.get('all_CPU_experts_RAM') is True,'Exact selected capacity/quality recovery')
    require(public.get('unauthenticated_models')==401 and public.get('authenticated_models')==200 and
        public.get('content')=='READY' and public.get('finish')=='stop' and public.get('SSE_done') is True and
        public.get('known_answer_passed') is True,'Public authentication and assembled READY-stop-DONE')
    return {'passed':True,'private_native_pid':api['native_ready_pid'],'private_API_pid':api['server_pid'],
        'private_native_API_window_exit0':True,'selected_binding':identity['start_binding'],'promotion_performed':False}


def audit_saved(output,metadata,window_path):
    output,metadata,window_path=map(Path,(output,metadata,window_path))
    read=lambda path:json.loads(Path(path).read_text())
    receipt=read(output/'receipt.json');arm=receipt['arm'];cases=read(output/'fixtures.json')['cases']
    progress=read(output/'case-progress.json');rows=receipt['result']['rows']
    require(arm in ('C0','A1') and receipt['result'].get('complete') is True and
        len(rows)==len(progress['rows'])==len(cases)==(11 if arm=='C0' else 3) and rows==progress['rows'] and
        len(progress['scores'])==len(cases) and all(x['status']=='NATURAL_SOURCE_CHECKED_MANUAL_PENDING' for x in progress['scores']),
        'Every exact essential request completed; no UNRUN, cap or partial omission')
    folder=output/'native';paths=sorted(folder.glob('native-[0-9][0-9][0-9]'))
    require(len(paths)==len(cases),'Exactly one native execution per frozen request; retry0')
    api=read(folder/'server-cleanup.json');observations=[]
    for path,case,row in zip(paths,cases,rows):
        request,trace,stats=(read(path/n) for n in ('request.json','trace-receipt.json','native-statistics.json'))
        tokens=[json.loads(x) for x in (path/'tokens.jsonl').read_text().splitlines()]
        observed=native_case(request,trace,stats,tokens,case,api['native_ready_pid'],case['kind']=='prefill-cancel')
        require(row.get('passed') is True and row['native']==observed['native'] and row['observed_tokens']==observed['generated'],
            'Producer agrees with independently read actual native trace')
        if case['id'].startswith('s2-essential-'):
            require(row['activity']['cpu']>0 and row['activity']['ram']>0 and row['native']['drafts_offered']>0,
                'Actual CPU offload/RAM and drafter on each task')
            if arm=='C0':require(row['original_CPU_participation']['positive'] is True and
                row['original_CPU_participation']['sensitive_selected_CPU_hits'],'Source-bound native original CPU routing on each task')
        observations.append(observed)
    telemetry=[json.loads(x) for x in window_path.with_suffix('.telemetry.jsonl').read_text().splitlines()]
    end=terminal(api,read(window_path),telemetry[-1],read(output/'private-memory-fence-restored.json'),
        read(metadata/'private-memory-fence-collected.json'),read(metadata/'result.json'),arm)
    require(receipt['private_resources']['passed'] is True and all(receipt['private_resources']['events_delta'].get(x)==0 for x in ('oom','oom_kill')),
        'Actual private OOM counters zero')
    return dict(end,arm=arm,observations=observations,manual_prose_and_independent_code_acceptance_still_required=True,
        near_full_context_or_output_claim=False)
