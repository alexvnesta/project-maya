"""Independent terminal/raw exploratory audit after selected production restoration."""
import argparse,json,pathlib
import iq2s_explore as mode
import iq2s_explore_controls as controls
import iq2s_explore_summary as summary
import iq2s_explore_runtime as runtime
import iq2s_explore_config as config

def require(ok,why):
    if not ok:raise ValueError(why)

def cleanup_contract(clean,closes,pid):
    require(clean.get('passed') is True and clean.get('server_returncode')==0 and type(clean.get('server_returncode')) is int
        and clean.get('grace_timeout') is False and clean.get('application_stopped') is True
        and clean.get('native_ready_pid')==pid,'Private API cleanup not clean')
    require(len(closes)==1 and closes[0].get('native_pid')==pid and closes[0].get('returncode')==0
        and type(closes[0].get('returncode')) is int and closes[0].get('closed') is True,'Unique private native close0 absent')

def resource_contract(samples):
    require(bool(samples),'Resource samples missing')
    for x in samples:
        require(type(x.get('root_free_bytes')) is int and x['root_free_bytes']>=120*2**30,'Runtime root120 floor failed')
        require(type(x.get('swap_pages',{}).get('pswpout')) is int and x['swap_pages']['pswpout']>=0,'Swap counter missing')
    delta=(samples[-1]['swap_pages']['pswpout']-samples[0]['swap_pages']['pswpout'])*4096
    require(0<=delta<2**30,'Swapout guard failed')
    return {'root_min_GiB':min(x['root_free_bytes'] for x in samples)/2**30,'system_swapout_delta_bytes':delta}

def restoration_contract(identity,public,health):
    wanted={'native_sha256':config.BASE_NATIVE,'config_sha256':config.BASE_SHA,'context':1048576,'output_default':262144,
            'prompt_skip_mode':1,'prefill_chunk':4096,'Q8':[1,1],'TP':1,'images':True,'runtime_ablation':True,
            'CPU_experts':4045,'all_CPU_experts_RAM':True}
    require(all(type(identity.get(k)) is type(v) and identity[k]==v for k,v in wanted.items()),'Selected4096 model/settings not restored')
    runtime.binding_contract(identity['start_binding'])
    require(identity['native_pid']==identity['start_binding']['native_pid'],'Restored owner binding mismatch')
    require(public.get('unauthenticated_models')==401 and public.get('authenticated_models')==200 and public.get('SSE_done') is True
        and public.get('finish')=='stop' and public.get('known_answer_passed') is True,'Selected public stream not verified')
    require(health.get('loaded') is True and health.get('max_context')==1048576 and health.get('images') is True
        and health.get('switcher',{}).get('active_model')=='deepseek' and health.get('switcher',{}).get('fault') is None,'Selected router/default failed')

def idle_guard(a):
    current=json.loads((runtime.E/'STATE.json').read_text())
    if not runtime.phase_keys_free(current):raise a.m.runtime.old.AdmissionDeferred('Another private/pending phase; exploratory audit untouched')
    host=a.ChunkProductionHost();host.start_binding=runtime.current_binding(current)
    if not host.idle():raise a.m.runtime.old.AdmissionDeferred('User work active; exploratory audit deferred before heavy CPU')
    host.guard_binding()

def trace_inventory(names):
    require(type(names) is list and sorted(names)==['native-000','native-001'],'Exactly two unique native traces required')

def result_contract(result):
    require(result.get('complete') is True and type(result.get('actual_native_count')) is int and result['actual_native_count']==2
        and type(result.get('native_count')) is int and result['native_count']==2 and result.get('quality_or_speed_pass') is False
        and result.get('prior_numerical_HOLD') is True and result.get('promotion_allowed') is False
        and result.get('unrun_ids')==[] and result.get('incomplete_reason') is None and result.get('DSI1_leftovers')==[],
        'Wrong/cap/partial/UNRUN or regraded diagnostic result')
    require([x['id'] for x in result['rows']]==list(mode.fixtures.IDS),'Exact ordered result rows required')
    require(result.get('case_scores')==[{'id':name,'status':'NATURAL_KNOWN_ANSWER_PASSED','passed':True}for name in mode.fixtures.IDS],
        'All original cases must remain scored and passed')

def audit(arm):
    a,old=runtime.support();idle_guard(a)
    reg=json.loads((mode.P/'exploratory-arms.json').read_text())[arm]
    out=pathlib.Path(reg['output']);_,meta=runtime.owned_paths(out,mode.MODE,arm,output_state='present')
    state=json.loads((meta/'state.json').read_text());folder=out/'native';m=mode.frozen()
    require(state['status']==runtime.statuses(mode.MODE,arm)['complete'] and state['output']==str(out)
        and state['proof_path']==str(meta/'proof.json'),'Numerical controller not fully restored')
    q=runtime.qualified(mode.MODE,state['qualification_sha256']);proof=json.loads((meta/'proof.json').read_text())
    require(proof['files']==q['files'] and proof['arm']==arm and proof['mode']==mode.MODE,'Wrong immutable source proof')
    window=pathlib.Path(state['window']);require(window.parent==runtime.R/'windows','Foreign window')
    w=json.loads(window.read_text());telemetry=[json.loads(x) for x in window.with_suffix('.telemetry.jsonl').read_text().splitlines()]
    require(type(w.get('test_returncode')) is int and w['test_returncode']==0 and w.get('maintenance_held') is True
        and w.get('maintenance_resume_allowed') is True and w.get('restored') is False,'Actual window exit0/cleanup missing')
    require(telemetry[-1].get('kernel_capture_returncode')==0 and telemetry[-1].get('kernel_fault_lines')==[],'Kernel fault or missing capture')
    resources=resource_contract([x for x in telemetry if 'root_free_bytes' in x])
    original=json.loads((meta/'old-owner-close.json').read_text())
    require(original['passed'] is True,'Old API/native exit proof absent')
    runtime.close_contract(original['binding'],original['native_close'],original['before'],original['after'])
    selected=state['verified'];restoration_contract(selected['selected_identity'],selected['public'],selected['health'])
    c=json.loads((out/'candidate-config.json').read_text());base=json.loads((mode.P/'base-config.json').read_text())
    config.check_config(base,c,folder,mode.MODE,arm)
    require(json.loads((out/'fixture.json').read_text())==m,'Actual exploratory fixture changed')
    native=json.loads((folder/'native-ready.json').read_text());pid=native['pid'];log=(folder/'engine.log').read_text(errors='replace')
    observed=json.loads((out/'startup-audit.json').read_text());startup=mode.startup(a,old,native,json.loads((out/'startup-health.json').read_text()),json.loads((out/'startup-models.json').read_text()),log)
    require(all(observed.get(k)==v for k,v in startup.items()),'Raw startup differs from observation')
    proc=observed['actual_process'];config.process_contract(c,proc['actual_argv'],proc['controlled_env'],proc['actual_cgroup'],same_executable=proc['same_executable'])
    require(proc['native_fsize_limits_raw'].split()[3:5]==['unlimited','unlimited'],'Unexpected timed native FSIZE')
    require(proc['native_sha256']==config.factor(mode.MODE,arm)['native_sha256'] and proc['native_pid']==pid,'Actual private executable differs')
    launch=json.loads((folder/'native-launch.json').read_text())
    require(launch['native_pid']==pid and launch['argv']==config.expected_native_argv(c)[:-1] and launch['API_limit_changed'] is False
        and launch['FSIZE_hook_installed'] is False,'Exploratory native launch guard changed limits')
    entry=json.loads((folder/'entry-audit.json').read_text())
    require(entry['server_pid']==json.loads((out/'server-start.json').read_text())['pid'] and entry['startup_retries']==0
        and entry['default_effort']==100 and entry.get('FSIZE_hook_installed') is False and entry.get('prior_numerical_HOLD') is True and entry.get('promotion_allowed') is False and entry['native_sha256']==config.factor(mode.MODE,arm)['native_sha256'],'Entry/retry/effort proof differs')
    cleanup_contract(json.loads((folder/'server-cleanup.json').read_text()),[json.loads(x) for x in (folder/'native-close.jsonl').read_text().splitlines()],pid)
    receipt=json.loads((out/'receipt.json').read_text());result=receipt['arm_results']
    result_contract(result)
    controls.no_dumps(folder)
    require(result.get('prior_numerical_HOLD') is True and result.get('promotion_allowed') is False,'Diagnostic scope changed')
    require(controls.owned_storage_snapshot(folder)['status']=='WITHIN_BUDGET','Private cache/log budget exceeded')
    require(config.factor_activation(log,mode.MODE,arm)==result['IQ2S'],'Factor activation differs')
    from q8_audit import reconcile
    act=controls.short_prompt_activation(log)
    require(act==result['activation'] and act['activation_early_rows']==m['expected_mode1_activation_skipped_tokens'],'Cold skip paths changed')
    rows=[]
    for i,case in enumerate(m['cases']):
        trace=folder/('native-%03d'%i);dest=folder/'skip-controls'/case['id']
        require(json.loads((dest/'request.json').read_text())==case['request'],'Actual request changed')
        response=json.loads((dest/'response.json').read_text());binding=reconcile(trace,case,response,pid)
        require(binding==json.loads((dest/'native-audit.json').read_text()),'Raw token/PID/DONE/reuse binding differs')
        row=controls.natural_contract(case,response,binding)
        require(row==result['rows'][i],'Natural raw case/dump differs from receipt')
        row['tokens']=[json.loads(x)['token'] for x in (trace/'tokens.jsonl').read_text().splitlines()]
        row['observations']=summary.observation(row,response)
        rows.append(row)
    trace_inventory([p.name for p in folder.glob('native-[0-9][0-9][0-9]')])
    require(not list((folder/'tmp').glob('deepseek-native-pictures-*/req-*.dsi')),'DSI1 leak')
    return {'passed':True,'arm':arm,'rows':rows,'resources':resources,'actual_native_pid':pid,'selected_identity':selected['selected_identity'],
            'purpose':'EXPLORATORY_DESCRIPTIVE_DECODE_ONLY','prior_numerical_HOLD':True,'promotion_allowed':False,'speed_pass':False,'general_quality_or_promotion_pass':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm',required=True,choices=['X0','X1']);args=p.parse_args()
    result=audit(args.arm);directory=mode.P/args.arm;directory.mkdir(exist_ok=True)
    path=directory/'terminal-audit.json'
    if path.exists():raise ValueError('Independent first audit output already exists')
    runtime.emit(path,result);print(json.dumps({'passed':True,'arm':args.arm,'manual_result_review_pending':True}))
