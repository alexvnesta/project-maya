"""New isolated natural-stop N0/N1 state qualification; no speed or promotion claim."""
import argparse,datetime,fcntl,importlib.util,json,os,pathlib,shutil,subprocess,sys,time
import iq2s_config as config
from iq2s_dependencies import fixtures, storage, controls
import iq2s_model_runtime as runtime
P=pathlib.Path(__file__).resolve().parent
R,E,D=runtime.R,runtime.E,runtime.D
MODE='numerical'

def frozen():
    pin=json.loads((P/'numerical-fixture-pin.json').read_text())
    if runtime.sha(P/'numerical-fixtures.json')!=pin['sha256']:raise ValueError('New numerical fixtures changed')
    m=json.loads((P/'numerical-fixtures.json').read_text());fixtures.validate_encoded(m['cases'])
    if m['id']!='imma-fullcap-numeric-state64-v1' or m['GPU_launch_ready'] is not False:raise ValueError('Foreign fixture mode')
    return m

def prerequisites(arm,registry):
    config.factor(MODE,arm)
    if arm in registry:raise ValueError('Numerical arm already attempted; no replay')
    if arm=='N1' and registry.get('N0',{}).get('fully_reviewed') is not True:raise ValueError('Reviewed current N0 required first')

def reserve(arm,output,proof):
    path=P/'numerical-arms.json';registry=json.loads(path.read_text());prerequisites(arm,registry)
    registry[arm]={'attempted':True,'fully_reviewed':False,'output':str(output),'proof':str(proof),'controller_pid':os.getpid()}
    runtime.emit(path,registry)

def extra_preflight(arm,output):
    prerequisites(arm,json.loads((P/'numerical-arms.json').read_text()));m=frozen()
    meta=json.loads((P/'pack-files.json').read_text());g=storage.geometry((P/'pack-geometry.ds4.txt').read_bytes())
    bound=storage.storage_bound(g,meta['engine_version'],[x['name'] for x in meta['pk_files']])
    return {'fixture_sha256':runtime.sha(P/'numerical-fixtures.json'),'storage_bound':bound,
            'factor':config.factor(MODE,arm),'purpose':m['purpose'],'speed_or_promotion_admitted':False}

def custody_contract(proof,current,registry,saved,output,arm,metadata):
    wanted={'mode':MODE,'arm':arm,'output':str(output),'proof_path':str(metadata/'proof.json')}
    selected=current.get('decode_optimization_current',{});attempt=registry.get(arm,{})
    if (proof.get('qualified_for_owned_iq2s_model') is not True or proof.get('mode')!=MODE or proof.get('arm')!=arm or
        proof.get('output')!=str(output) or any(saved.get(k)!=v or selected.get(k)!=v for k,v in wanted.items()) or
        selected.get('status')!=runtime.statuses(MODE,arm)['running'] or saved.get('status')!=selected.get('status') or
        current.get('maintenance_controller')!=str(metadata/'state.json') or current.get('active_private_phase')!=str(metadata) or
        current.get('active_gpu_experiment') is not True or attempt.get('attempted') is not True or
        attempt.get('fully_reviewed') is not False or attempt.get('output')!=str(output) or attempt.get('proof')!=str(metadata/'proof.json') or
        type(selected.get('controller_pid')) is not int or selected['controller_pid']<=0 or
        selected['controller_pid']!=saved.get('controller_pid') or selected['controller_pid']!=attempt.get('controller_pid') or
        proof.get('qualification_sha256')!=selected.get('qualification_sha256') or proof.get('qualification_sha256')!=saved.get('qualification_sha256')):
        raise ValueError('Exact active numerical controller/attempt/proof custody missing')
    return True

def read_phase_proof(output,arm,proofpath,*,output_state='absent'):
    output=pathlib.Path(output);_,metadata=runtime.owned_paths(output,MODE,arm,output_state=output_state)
    if pathlib.Path(proofpath)!=metadata/'proof.json':raise ValueError('Foreign phase proof path; no read')
    proof=json.loads(runtime.real_file(proofpath).read_text())
    current=json.loads((E/'STATE.json').read_text());registry=json.loads((P/'numerical-arms.json').read_text())
    saved=json.loads(runtime.real_file(metadata/'state.json').read_text())
    custody_contract(proof,current,registry,saved,output,arm,metadata)
    return proof

def window_contract(window,state,output,arm,metadata):
    expected=[str(R/'venv/bin/python3.14'),'-B',str(P/'iq2s_numerical.py'),'--phase','--arm',arm,'--output',str(output),'--proof',str(metadata/'proof.json')]
    if (pathlib.Path(window).parent!=R/'windows' or state.get('command')!=expected or
        state.get('maintenance_root_window')!='20261025T032914Z.json' or not state.get('continued_from') or
        state.get('test_returncode') is not None or state.get('maintenance_held') is True or state.get('restored') is not False):
        raise ValueError('Not the current exact admitted numerical window')
    return True

def window_admission(old,proof,arm,output):
    if (proof.get('qualified_for_owned_iq2s_model') is not True or proof.get('mode')!=MODE or
        proof.get('arm')!=arm or proof.get('output')!=str(output)):
        raise ValueError('Exact new numerical ownership proof required')
    q=runtime.qualified(MODE,proof['qualification_sha256'])
    if proof['files']!=q['files']:raise ValueError('Phase proof inventory differs')
    window,state=old.owned_window()
    window_contract(window,state,output,arm,E/'maintenance'/pathlib.Path(output).name)
    if 'strata-deepseek-window.service' not in pathlib.Path('/proc/self/cgroup').read_text().strip().split('/'):
        raise ValueError('Not the existing owned window')
    if subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip():raise ValueError('Another GPU owner')
    if shutil.disk_usage('/').free<132*2**30:raise ValueError('Root132 unavailable')
    with (R/'experiment.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:pass
        else:
            fcntl.flock(lock,fcntl.LOCK_UN);raise ValueError('Canonical parent lock absent')
    return window

def install_native_limit(server,c,folder):
    """Private API launch hook: apply FSIZE only to its exact numerical native."""
    meta=json.loads((P/'pack-files.json').read_text());g=storage.geometry((P/'pack-geometry.ds4.txt').read_bytes())
    limit=storage.native_fsize_preexec(g,meta['engine_version'],[x['name'] for x in meta['pk_files']],process_kind='UNMEASURED_NUMERICAL_NATIVE')
    original=server.popen;count=[];wanted=config.expected_native_argv(c)[:-1]
    def popen(what,args,role='engine',**kw):
        if what!='the Strata engine' or args!=wanted or role!='engine' or count:
            raise ValueError('Only one exact numerical native launch allowed')
        before=kw.get('preexec_fn')
        def child():
            if before:before()
            limit()
        kw['preexec_fn']=child
        proc=original(what,args,role=role,**kw);count.append(proc.pid)
        try:
            runtime.emit(pathlib.Path(folder)/'native-fsize-launch.json',{'native_pid':proc.pid,'argv':args,
                'hard_file_bytes':storage.HARD_FILE_BYTES,'scope':'ONLY_UNMEASURED_NUMERICAL_NATIVE','API_limit_changed':False})
        except BaseException as primary:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
            except BaseException as cleanup:primary.add_note('Unregistered owned numerical native cleanup failed: '+repr(cleanup))
            raise
        return proc
    server.popen=popen
    return count

def actual_native(c,pid,arm):
    proc=pathlib.Path('/proc')/str(pid)
    argv=(proc/'cmdline').read_bytes().decode().split('\0')
    env=dict(x.split('=',1) for x in (proc/'environ').read_bytes().decode().split('\0') if '=' in x)
    group=(proc/'cgroup').read_text();same=os.path.samefile(proc/'exe',c['exe'])
    result=config.process_contract(c,argv,env,group,same_executable=same)
    if runtime.sha(c['exe'])!=config.factor(MODE,arm)['native_sha256']:raise ValueError('Private executable identity changed')
    limits=(proc/'limits').read_text()
    line=next(x for x in limits.splitlines() if x.startswith('Max file size'))
    if line.split()[3:5]!=[str(storage.HARD_FILE_BYTES)]*2:raise ValueError('Numerical native hard file limit missing')
    return {**result,'native_pid':pid,'native_sha256':config.factor(MODE,arm)['native_sha256'],
            'actual_argv':argv,'controlled_env':config.controlled_environment(env),'actual_cgroup':group,'same_executable':same,
            'native_fsize_limits_raw':line,'process_start_ticks':int((proc/'stat').read_text().rsplit(')',1)[1].split()[19])}

def startup(a,old,ready,health,models,log):
    result=a.m.runtime.startup(ready,health,models,log,4096)
    if result.get('cpu_experts')!=4045 or result.get('expert_slots')!=11315:raise ValueError('Actual placement changed; HOLD one-factor trial')
    return result

def entry(args):
    a,old=runtime.support();folder=pathlib.Path(args.trace_directory);output=folder.parent
    runtime.owned_paths(output,MODE,args.arm,output_state='present')
    if folder!=output/'native' or pathlib.Path(args.config)!=output/'candidate-config.json':raise ValueError('Exact owned entry paths required')
    runtime.real_directory(folder);runtime.real_file(args.config)
    proof=read_phase_proof(output,args.arm,E/'maintenance'/output.name/'proof.json',output_state='present')
    runtime.qualified(MODE,proof['qualification_sha256'])
    window,window_state=old.owned_window();window_contract(window,window_state,output,args.arm,E/'maintenance'/output.name)
    if runtime.sha(args.config)!=args.config_sha256 or runtime.sha(D/'config.json')!=config.BASE_SHA:raise ValueError('Entry config changed')
    c=json.loads(pathlib.Path(args.config).read_text());base=json.loads((D/'config.json').read_text())
    config.check_config(base,c,folder,MODE,args.arm)
    for p,sha in [(pathlib.Path(c['exe']),config.factor(MODE,args.arm)['native_sha256']),
                  (D/'runtime-native-vision-v2/serve/server.py',fixtures.SERVER_SHA),
                  (D/'hosting_defaults.py',old.DEFAULTS_SHA)]:
        if runtime.sha(p)!=sha:raise ValueError('Private entry identity changed')
    sys.path.insert(0,str(D/'runtime-native-vision-v2'));from serve import server
    if pathlib.Path(server.__file__).resolve()!=(D/'runtime-native-vision-v2/serve/server.py').resolve():raise ValueError('Foreign API module')
    spec=importlib.util.spec_from_file_location('iq2s_numeric_defaults',D/'hosting_defaults.py')
    defaults=importlib.util.module_from_spec(spec);spec.loader.exec_module(defaults)
    proof=old.prepare_server(server,c,folder,defaults.install)
    install_native_limit(server,c,folder)
    proof.update(native_exe=c['exe'],native_sha256=config.factor(MODE,args.arm)['native_sha256'],
        requested_context=1048576,server_pid=os.getpid(),config_sha256=args.config_sha256,owned_window=str(window),
        numerical_only=True,skip=1,prefill_chunk=4096,native_only_FSIZE_bytes=storage.HARD_FILE_BYTES)
    runtime.emit(folder/'entry-audit.json',proof)
    return server.main(['--engine','strata','--config',args.config,'--host','127.0.0.1','--port','18041','--shutdown-timeout','60'])

def body_and_cleanup(body,cleanup):
    primary=None
    try:return body()
    except BaseException as exc:primary=exc;raise
    finally:
        try:cleanup()
        except BaseException as cleanup_error:
            if primary is None:raise
            primary.add_note('Owned private API/native cleanup also failed: '+repr(cleanup_error))

def phase(output,arm,proof):
    a,old=runtime.support();output=pathlib.Path(output);runtime.owned_paths(output,MODE,arm)
    began=time.monotonic();window=window_admission(old,proof,arm,output);m=frozen()
    c=config.make_config(json.loads((D/'config.json').read_text()),output/'native',MODE,arm)
    output.mkdir(exist_ok=False);folder=output/'native';folder.mkdir()
    for name in ('cache','tmp','cuda-cache'):(folder/name).mkdir()
    shutil.copyfile(D/'profile-seed.bin',folder/'expert-profile.bin')
    if runtime.sha(folder/'expert-profile.bin')!=old.q8_phase.SEED_SHA:raise ValueError('Profile seed changed')
    path=output/'candidate-config.json';runtime.emit(path,c)
    runtime.emit(output/'candidate-config.shared-settings.json',{'max_tokens':262144})
    runtime.emit(output/'proof.json',proof);runtime.emit(output/'fixture.json',m)
    command=[str(R/'venv/bin/python3.14'),'-u','-B',str(P/'iq2s_numerical.py'),'--entry','--arm',arm,
             '--config',str(path),'--config-sha256',runtime.sha(path),'--trace-directory',str(folder)]
    with (folder/'server.log').open('w') as log:
        proc=subprocess.Popen(command,cwd=P,env=old.q8_phase.environment(folder,window),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        def body():
            runtime.emit(output/'server-start.json',{'pid':proc.pid,'argv':command,'arm':arm})
            ready,health,models=old.q8_phase.wait_startup(proc,folder,min(began+1000,began+800))
            runtime.emit(output/'startup-health.json',health);runtime.emit(output/'startup-models.json',models)
            text=(folder/'engine.log').read_text(errors='replace')
            result=startup(a,old,ready,health,models,text);result['actual_process']=actual_native(c,ready['pid'],arm)
            runtime.emit(output/'startup-audit.json',result)
            import skip_controls
            from protocol import Stream,json_get,wait_for
            def requester(base,body,deadline):return controls.bounded_request(base,body,deadline,folder,stream_class=Stream,observe=json_get,wait_for=wait_for)
            def issue(case,folder,pid,deadline):
                try:return skip_controls.issue(case,folder,pid,deadline,requester=requester)
                except skip_controls.ControlBudgetStop as exc:raise controls.NumericalIncomplete(str(exc)) from exc
            result=controls.run_cases(m,folder,ready['pid'],began+1000,issue=issue)
            result['actual_native_count']=len(old.q8_phase.native_paths(folder))
            text=(folder/'engine.log').read_text(errors='replace')
            act=skip_controls.activation(text,1,required=result['complete'])
            expected=m['expected_mode1_activation_skipped_tokens'];observed=act['activation_early_rows']
            if observed!=(expected if result['complete'] else expected[:len(observed)]):raise ValueError('Actual cold skip paths differ')
            result['activation']=act;result['IQ2S']=config.factor_activation(text,MODE,arm)
            result['DSI1_leftovers']=sorted(str(p.relative_to(folder)) for p in (folder/'tmp').glob('deepseek-native-pictures-*/req-*.dsi'))
            result['complete']=result['complete'] and not result['DSI1_leftovers']
            return result
        try:
            result=body_and_cleanup(body,lambda:old.stop_server(proc,folder,timeout=100))
            runtime.emit(output/'receipt.json',{'arm':arm,'arm_results':result,'native_server_cleanup_passed':True,
                'seconds_including_load':time.monotonic()-began,'not_a_promotion':True,'speed_pass':False})
            return 0
        except BaseException as exc:
            try:runtime.emit(output/'phase-error.json',{'error':repr(exc),'secondary_errors':getattr(exc,'__notes__',[]),'retry':False})
            except BaseException as receipt_error:exc.add_note('Private phase error receipt also failed: '+repr(receipt_error))
            raise

def controller(args):
    a,old=runtime.support()
    if args.verify_state:return runtime.verify_pending(a,pathlib.Path(args.verify_state).parent,MODE,args.arm)
    # Read-only user-work deferral precedes metadata, hashing and owner binding.
    probe=a.ChunkProductionHost();probe.start_binding=runtime.current_binding()
    if not runtime.phase_keys_free(json.loads((E/'STATE.json').read_text())) or not probe.idle():return {'status':'DEFERRED_BUSY_UNTOUCHED'}
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=E/'results'/('decode-iq2s-numerical-'+args.arm+'-'+stamp)
    _,metadata=runtime.owned_paths(out,MODE,args.arm,metadata_state='absent');metadata.mkdir(exist_ok=False)
    digest=runtime.sha(P/'numerical-qualification.json');host=runtime.load_current_host(a,MODE,args.arm,metadata,digest)
    host.extra_preflight=lambda output:extra_preflight(args.arm,output)
    host.reserve_attempt=lambda output,proof:reserve(args.arm,output,proof)
    host.phase_argv=lambda output,proof:[str(R/'venv/bin/python3.14'),'-B',str(P/'iq2s_numerical.py'),'--phase','--arm',args.arm,'--output',str(output),'--proof',str(proof)]
    status=runtime.statuses(MODE,args.arm)
    state={'utc':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
           'mode':MODE,'arm':args.arm,'output':str(out),'proof_path':str(metadata/'proof.json'),
           'qualification_sha256':digest,'running_status':status['running'],'complete_status':status['complete'],
           'completion_scope':'Four full-cap natural numerical state paths only; no speed/general quality/promotion claim'}
    save=runtime.make_saver(host,metadata,MODE,args.arm,args.run)
    result=runtime.coordinate_mode(a,host,out,state,save,preflight_only=not args.run)
    runtime.emit(metadata/'result.json',result)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',required=True,choices=['N0','N1'])
    for n in ('entry','phase','run'):p.add_argument('--'+n,action='store_true')
    for n in ('config','config-sha256','trace-directory','output','proof','verify-state'):p.add_argument('--'+n)
    args=p.parse_args()
    if args.entry:return entry(args)
    if args.phase:return phase(args.output,args.arm,read_phase_proof(args.output,args.arm,args.proof))
    print(json.dumps(controller(args)),flush=True);return 0
if __name__=='__main__':raise SystemExit(main())
