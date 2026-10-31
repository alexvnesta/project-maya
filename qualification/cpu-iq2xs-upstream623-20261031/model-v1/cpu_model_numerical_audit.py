"""Independent terminal/raw numerical audit after selected production restoration."""
import argparse,json,pathlib,hashlib,os,re,math
import cpu_model_numerical as mode
from cpu_model_dependencies import controls
import cpu_model_runtime as runtime
import cpu_model_config as config

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
    if not runtime.phase_keys_free(current):raise a.m.runtime.old.AdmissionDeferred('Another private/pending phase; numerical audit untouched')
    host=a.ChunkProductionHost();host.start_binding=runtime.current_binding(current)
    if not host.idle():raise a.m.runtime.old.AdmissionDeferred('User work active; numerical audit deferred before heavy CPU')
    host.guard_binding()

def audit(arm,finite_scans,*,guard):
    require(callable(guard), 'Explicit bounded audit owner guard required');guard()
    require(type(finite_scans) is list and len(finite_scans)==4, 'Four separately bounded finite scans required')
    a,old=runtime.support()
    out,meta,state=arm_context(arm);folder=out/'native';m=mode.frozen()
    require(state['status']==runtime.statuses(mode.MODE,arm)['complete'] and state['output']==str(out)
        and state['proof_path']==str(meta/'proof.json'),'Numerical controller not fully restored')
    q=runtime.qualified(mode.MODE,state['qualification_sha256']);proof=json.loads((meta/'proof.json').read_text())
    require(proof['files']==q['files'] and proof['arm']==arm and proof['mode']==mode.MODE
        and proof.get('output')==str(out) and proof.get('qualification_sha256')==state['qualification_sha256']
        and proof.get('qualified_for_owned_cpu_iq2xs_model') is True,'Wrong immutable source proof')
    window=pathlib.Path(state['window']);require(window.parent==runtime.R/'windows','Foreign window')
    w=json.loads(window.read_text());terminal_window(w,out,arm,meta)
    memory=read_json(meta/'post-stop-memory.json')
    require(memory.get('passed') is True and type(memory.get('available_bytes')) is int
            and type(memory.get('required_bytes')) is int and memory['required_bytes']==88*2**30
            and memory['available_bytes']>=memory['required_bytes'],'Actual post-stop88GiB witness absent')
    telemetry=[json.loads(x) for x in window.with_suffix('.telemetry.jsonl').read_text().splitlines()]
    require(type(w.get('test_returncode')) is int and w['test_returncode']==0 and w.get('maintenance_held') is True
        and w.get('maintenance_resume_allowed') is True and w.get('restored') is False,'Actual window exit0/cleanup missing')
    require(telemetry[-1].get('kernel_capture_returncode')==0 and telemetry[-1].get('kernel_fault_lines')==[],'Kernel fault or missing capture')
    resources=resource_contract([x for x in telemetry if 'root_free_bytes' in x])
    original=json.loads((meta/'old-owner-close.json').read_text())
    require(original['passed'] is True,'Old API/native exit proof absent')
    runtime.close_contract(original['binding'],original['native_close'],original['before'],original['after'])
    selected=state['verified'];restoration_contract(selected['selected_identity'],selected['public'],selected['health'])
    public_saved_contract(meta)
    c=json.loads((out/'candidate-config.json').read_text());base=json.loads((mode.P/'base-config.json').read_text())
    config.check_config(base,c,folder,mode.MODE,arm)
    require(json.loads((out/'fixture.json').read_text())==m,'Actual numerical fixture changed')
    native=json.loads((folder/'native-ready.json').read_text());pid=native['pid'];log=(folder/'engine.log').read_text(errors='replace')
    observed=json.loads((out/'startup-audit.json').read_text());startup=mode.startup(a,old,native,json.loads((out/'startup-health.json').read_text()),json.loads((out/'startup-models.json').read_text()),log,q['allowed_automatic_cuts'][arm])
    require(all(observed.get(k)==v for k,v in startup.items()),'Raw startup differs from observation')
    proc=observed['actual_process'];config.process_contract(c,proc['actual_argv'],proc['controlled_env'],proc['actual_cgroup'],same_executable=proc['same_executable'])
    raw_limit=proc['native_fsize_limits_raw'].split()
    require(raw_limit[:3]==['Max','file','size'] and raw_limit[3:5]==[str(mode.storage.HARD_FILE_BYTES)]*2,'Actual private native FSIZE raw limits differ')
    require(proc['native_sha256']==config.factor(mode.MODE,arm)['native_sha256'] and proc['native_pid']==pid,'Actual private executable differs')
    launch=json.loads((folder/'native-fsize-launch.json').read_text())
    require(launch['native_pid']==pid and launch['argv']==config.expected_native_argv(c)[:-1] and launch['API_limit_changed'] is False
        and launch['hard_file_bytes']==mode.storage.HARD_FILE_BYTES,'FSIZE was not exact numerical child-only')
    entry=json.loads((folder/'entry-audit.json').read_text())
    require(entry['server_pid']==json.loads((out/'server-start.json').read_text())['pid'] and entry['startup_retries']==0
        and entry['default_effort']==100 and entry['native_sha256']==config.factor(mode.MODE,arm)['native_sha256'],'Entry/retry/effort proof differs')
    cleanup_contract(json.loads((folder/'server-cleanup.json').read_text()),[json.loads(x) for x in (folder/'native-close.jsonl').read_text().splitlines()],pid)
    receipt=json.loads((out/'receipt.json').read_text());result=receipt['arm_results']
    fence_contract(json.loads((out/'private-memory-fence.json').read_text()),receipt['resource_fence_terminal'],
                   json.loads((out/'private-memory-fence-restored.json').read_text()),
                   json.loads((meta/'private-memory-fence-collected.json').read_text()))
    require(json.loads((out/'private-child-closure.json').read_text()).get('passed') is True,'Private descendant closure unproved')
    api=json.loads((folder/'private-api-exit.json').read_text());start=json.loads((out/'server-start.json').read_text())
    require(api.get('passed') is True and type(api.get('actual_Popen_returncode')) is int and api['actual_Popen_returncode']==0
            and api.get('server_pid')==start['pid'] and api['server_cleanup']==json.loads((folder/'server-cleanup.json').read_text()),
            'Prospective actual private API Popen wait0 missing')
    require(result['complete'] is True and result['actual_native_count']==4 and result['native_count']==4
        and result['quality_or_speed_pass'] is False and result['DSI1_leftovers']==[],'Wrong/cap/partial/UNRUN numerical result blocks')
    require(controls.dump_snapshot(folder,complete=True)['status']=='COMPLETE_SIZE_ONLY','Dump budget incomplete')
    require(controls.owned_storage_snapshot(folder)['status']=='WITHIN_BUDGET','Private cache/log budget exceeded')
    require(config.factor_activation(log,mode.MODE,arm)==result['CPU_IQ2XS'],'Factor activation differs')
    from q8_audit import reconcile
    from skip_controls import activation
    act=activation(log,1,required=True)
    require(act==result['activation'] and act['activation_early_rows']==m['expected_mode1_activation_skipped_tokens'],'Cold skip paths changed')
    require(type(result.get('rows')) is list and len(result['rows'])==4
            and [x.get('id') for x in result['rows']]==[x['id'] for x in m['cases']],'Exact four scored result IDs required')
    rows=[]
    for i,case in enumerate(m['cases']):
        trace=folder/('native-%03d'%i);dest=folder/'skip-controls'/case['id']
        require(json.loads((dest/'request.json').read_text())==case['request'],'Actual request changed')
        response=json.loads((dest/'response.json').read_text());saved_transport(response);binding=reconcile(trace,case,response,pid)
        require(binding==json.loads((dest/'native-audit.json').read_text()),'Raw token/PID/DONE/reuse binding differs')
        row=controls.natural_contract(case,response,binding);dump=folder/('logits.%d.f32'%(i+1));row['dump_size_only']=controls.dump_size(dump)
        require(row==result['rows'][i],'Natural raw case/dump differs from receipt')
        row['dump']=scanned_dump(dump,finite_scans[i],arm,i,case['id'],state['qualification_sha256'])
        row['tokens']=[json.loads(x)['token'] for x in (trace/'tokens.jsonl').read_text().splitlines()];rows.append(row)
    require({p.name for p in folder.glob('native-[0-9][0-9][0-9]')}=={'native-%03d'%i for i in range(4)},'Unexpected native request')
    require(not list((folder/'tmp').glob('deepseek-native-pictures-*/req-*.dsi')),'DSI1 leak')
    guard()
    return {'passed':True,'arm':arm,'output':str(out),'proof_path':str(meta/'proof.json'),
            'qualification_sha256':state['qualification_sha256'],'startup':startup,'rows':rows,'resources':resources,'actual_native_pid':pid,'selected_identity':selected['selected_identity'],
            'purpose':'UNMEASURED_NUMERICAL_ONLY','speed_pass':False,'general_quality_or_promotion_pass':False}



def exact(a,b):
    return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)


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


PUBLIC_DEFAULT_REQUEST={'model':'deepseek-v4.1-flash-iq2-xs',
 'messages':[{'role':'user','content':'Return exactly the text between the tags, excluding the tags. Add no punctuation or explanation.\n<answer>READY</answer>'}],
 'reasoning_effort':'none','temperature':0,'seed':1,'stream':True}


def assembled_ready(raw):
    text='';finish=None;done=0
    for line in raw.splitlines():
        if not line.startswith('data:'):continue
        value=line[5:].strip()
        if not value:continue
        require(done==0,'Event after saved DONE')
        if value=='[DONE]':done+=1;continue
        event=json.loads(value);require(type(event) is dict and 'error' not in event,'Saved public API execution error')
        for choice in event.get('choices',[]):
            part=choice.get('delta',{}).get('content') or ''
            require(type(part) is str,'Typed saved public content required');text+=part
            if choice.get('finish_reason'):
                require(finish is None,'Multiple public terminal choices');finish=choice['finish_reason']
    require(text.strip()=='READY' and finish=='stop' and done==1,'Assembled public READY/stop/DONE absent')
    return {'content':text,'finish':finish,'DONE':True}


def public_saved_contract(metadata):
    request=json.loads(runtime.real_file(metadata/'public-default-output-request.json').read_text())
    require(exact(request,PUBLIC_DEFAULT_REQUEST),'Actual unchanged default-output public probe request required')
    return assembled_ready(runtime.real_file(metadata/'public-default-output-sse.txt').read_text())


def fingerprint(path):
    st=runtime.real_file(path).stat()
    return {'device':st.st_dev,'inode':st.st_ino,'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'nlink':st.st_nlink}


def scanned_dump(path,scan,arm,index,case_id,qpin):
    require(type(index) is int and 0<=index<4 and scan.get('passed') is True
            and scan.get('operation')=='scan' and scan.get('arm')==arm and scan.get('index')==index
            and scan.get('case_id')==case_id and scan.get('path')==str(path)
            and scan.get('qualification_sha256')==qpin,'Exact separately bounded scan association required')
    result=scan['dump'];size=controls.dump_size(path)
    require(type(result.get('bytes')) is int and type(result.get('rows')) is int,'Typed finite byte/row counts required')
    require(scan['before']==scan['after']==fingerprint(path),'Dump identity changed after bounded scan')
    require(type(result.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}',result['sha256']) is not None
            and result.get('all_finite') is True and result.get('token_row_alignment_claimed') is False
            and result.get('bytes')==size['bytes'] and result.get('rows')==size['rows'],
            'Complete finite dump/bytes/rows proof required')
    return result


def arm_context(arm):
    require(arm in ('N0','N1'),'Exact actual numerical arm required')
    reg=json.loads((mode.P/'numerical-arms.json').read_text()).get(arm,{})
    require(reg.get('attempted') is True,'Actual attempted arm required')
    out=pathlib.Path(reg['output']);_,meta=runtime.owned_paths(out,mode.MODE,arm,output_state='present')
    state=json.loads(runtime.real_file(meta/'state.json').read_text())
    require(state.get('status')==runtime.statuses(mode.MODE,arm)['complete']
            and state.get('controller_pid')==reg.get('controller_pid')
            and state.get('output')==str(out) and state.get('proof_path')==reg.get('proof'),
            'Complete restored arm/controller custody required before offline work')
    return out,meta,state


def scan_one(arm,index,qpin):
    require(type(index) is int and 0<=index<4,'One of four exact finite scans required')
    out,meta,state=arm_context(arm)
    require(state['qualification_sha256']==qpin,'Scan qualification differs')
    manifest=mode.frozen();case=manifest['cases'][index];path=out/'native'/('logits.%d.f32'%(index+1))
    before=fingerprint(path);result=controls.finite_dump(path);after=fingerprint(path)
    require(before==after,'Actual dump identity changed across finite scan')
    return {'passed':True,'operation':'scan','arm':arm,'index':index,'case_id':case['id'],'path':str(path),
            'qualification_sha256':qpin,'before':before,'after':after,'dump':result}


def comparison_placement(startup):
    p=startup['placement']
    counts=[]
    for row in p['human_rows']:
        keys=('device','first','last','human_experts_including_drafter','human_total')
        require(all(type(row.get(k)) is int for k in keys),'Typed actual placement counts required')
        counts.append({k:row[k] for k in keys})
    require(type(startup.get('cpu_experts')) is int and type(startup.get('expert_slots')) is int
            and startup['cpu_experts']+startup['expert_slots']==15360,'Complete actual trunk accounting required')
    return {'cpu':startup['cpu_experts'],'GPU':startup['expert_slots'],'trunk_split':p['trunk_split'],
            'head_GPU':p['head_GPU'],'drafter_GPU':p['drafter_GPU'],'counts':counts}


def compare_complete(baseline,candidate):
    require(baseline.get('passed') is True and candidate.get('passed') is True
            and baseline.get('arm')=='N0' and candidate.get('arm')=='N1'
            and baseline.get('qualification_sha256')==candidate.get('qualification_sha256'),
            'Two fully audited exact mode arms required')
    require(exact(comparison_placement(baseline['startup']),comparison_placement(candidate['startup'])),
            'Actual private placement changed; no isolated kernel claim')
    return controls.compare_matched(baseline['rows'],candidate['rows'])


def read_json(path):
    return json.loads(runtime.real_file(path).read_text())


def terminal_window(value,output,arm,metadata):
    command=[str(runtime.R/'venv/bin/python3.14'),'-B',str(mode.P/'cpu_model_numerical.py'),'--phase','--arm',arm,
             '--output',str(output),'--proof',str(metadata/'proof.json')]
    require(value.get('command')==command and value.get('maintenance_root_window')=='20261025T032914Z.json'
            and type(value.get('continued_from')) is str and bool(value['continued_from']),
            'Exact actual numerical window command/root ancestry required')


def saved_transport(response):
    require(type(response.get('raw')) is list and bool(response['raw']),'Raw saved private SSE required')
    content='';reasoning='';events=[];finish=None;done=0;usage=None;timings=None;last=-1
    for item in response['raw']:
        require(type(item) is dict and type(item.get('seconds')) in (int,float)
                and math.isfinite(item['seconds']) and item['seconds']>=last and type(item.get('line')) is str,
                'Typed monotone saved raw SSE required')
        last=item['seconds'];line=item['line']
        if not line.startswith('data:'):continue
        require(done==0,'Data after private saved DONE');value=line[5:].strip()
        if value=='[DONE]':done+=1;continue
        event=json.loads(value);require(type(event) is dict and 'error' not in event,'Private raw execution error')
        events.append(event)
        if event.get('usage') is not None:usage=event['usage']
        if event.get('timings') is not None:timings=event['timings']
        for choice in event.get('choices',[]):
            delta=choice.get('delta') or {};c=delta.get('content') or '';r=delta.get('reasoning_content') or ''
            require(type(c) is str and type(r) is str and not delta.get('tool_calls'),'Unexpected numerical text/tool stream')
            content+=c;reasoning+=r
            if choice.get('finish_reason'):
                require(finish is None,'Multiple private terminal choices');finish=choice['finish_reason']
    require(done==1 and finish=='stop' and response.get('done') is True and response.get('finish_reason')==finish
            and response.get('status')==200 and response.get('cancelled') is False
            and exact(events,response.get('events')) and content==response.get('content')
            and reasoning==response.get('reasoning') and exact(usage,response.get('usage'))
            and exact(timings,response.get('timings')) and response.get('tool_calls')==[],
            'Raw private SSE differs from saved response envelope')
    return {'passed':True,'DONE':True,'finish':finish,'events':len(events)}


def saved_evidence(arm):
    """Hash only this completed synthetic arm; each caller is a bounded CPU child.

    Logits have independent finite scan SHA proofs. Their fingerprints are retained
    here so the four scans must share exactly one immutable evidence snapshot.
    """
    out,metadata,state=arm_context(arm);paths=[]
    require(controls.owned_storage_snapshot(out/'native')['status']=='WITHIN_BUDGET','Private payload storage budget failed')
    require(controls.dump_snapshot(out/'native',complete=True)['status']=='COMPLETE_SIZE_ONLY','Exact four completed dumps required')
    excluded={out/'native'/name for name in ('cache','tmp','cuda-cache')}
    for base in (out,metadata):
        runtime.real_directory(base)
        for root,dirs,files in os.walk(base,followlinks=False):
            root=pathlib.Path(root)
            for name in dirs:
                require(not (root/name).is_symlink(),'Saved evidence directory symlink refused')
            dirs[:]=[name for name in dirs if root/name not in excluded]
            paths.extend(root/name for name in files)
    window=pathlib.Path(state['window']);require(window.parent==runtime.R/'windows','Foreign evidence window')
    paths.extend((window,window.with_suffix('.telemetry.jsonl')))
    require(len(paths)==len(set(paths)),'Saved evidence inventory duplicates')
    result={}
    for path in sorted(paths):
        before=fingerprint(path)
        row={'fingerprint':before,'sha256':None,'finite_scan_separately_required':False}
        if path.parent==out/'native' and re.fullmatch(r'logits\.[1-4]\.f32',path.name):
            row['finite_scan_separately_required']=True
        else:row['sha256']=runtime.sha(path)
        require(fingerprint(path)==before,'Saved evidence mutated while hashing')
        result[str(path)]=row
    require(result,'Saved evidence snapshot empty')
    return result


def evidence_fingerprints(evidence):
    require(type(evidence) is dict and bool(evidence),'Immutable saved-evidence map required')
    for name,row in evidence.items():
        require(fingerprint(pathlib.Path(name))==row['fingerprint'],'Saved evidence changed after bounded audit')
    return True
