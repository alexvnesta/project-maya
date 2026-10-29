"""One separately qualified bounded kernel-only window; restore the existing selected4096 owner.

This fixture has no model or API server and establishes no generation-speed result.
"""
import argparse, datetime, hashlib, json, os, pathlib, re, resource, subprocess, sys, time
P=pathlib.Path(__file__).resolve().parent
R=pathlib.Path('/home/alex/strata-deepseek-test-20261024');E=R/'reliability-optimization-20261025'
F=E/'autonomous-optimization-12h-20261028/chunk4096-v1/activation-v1'
WINDOW_SHA='170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f'
COORDINATE_SHA='276a78f6f62d9ae7760e9b436863a6279715d58ea0960bb396bdb7adcc3776dd'
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for data in iter(lambda:f.read(65536),b''):h.update(data)
    return h.hexdigest()
def emit(path,value):
    path=pathlib.Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)
def phase_keys_free(state):
    return not any(state.get(k) for k in ['active_private_phase','active_GPU_phase','active_gpu_experiment',
        'private_window','active_cpu_build','production_restore_in_progress','production_verification_pending','production_temporarily_stopped'])
def selected_binding(state):
    selected=state.get('decode_optimization_current',{}).get('selected_identity')
    if selected is None:selected=state['chunk4096_activation']['selected_identity']
    binding=selected['start_binding']
    if (set(binding)!={'invocation','main_pid','native_pid','native_start_ticks'} or
        re.fullmatch('[0-9a-f]{32}',binding['invocation']) is None or
        any(type(binding[k]) is not int or binding[k]<=0 for k in ['main_pid','native_pid','native_start_ticks'])):
        raise ValueError('Typed exact selected owner binding required')
    return dict(binding)
def real_directory(path):
    path=pathlib.Path(path)
    if not path.is_absolute() or '..' in path.parts:raise ValueError('Absolute real directory required')
    for ancestor in [*reversed(path.parents),path]:
        if ancestor.is_symlink() or not ancestor.is_dir():raise ValueError('Real directory ancestors required')

def output_paths(output, *, metadata_state='optional'):
    output=pathlib.Path(output)
    if output.parent!=E/'results' or re.fullmatch(r'decode-iq2s-persistent-kernel-[0-9]{8}T[0-9]{6}Z',output.name) is None:
        raise ValueError('Exact fresh kernel namespace required')
    for root in [E,E/'results',E/'maintenance']:real_directory(root)
    if '..' in output.parts or output.is_symlink() or output.exists():raise ValueError('Kernel namespace already exists/foreign')
    metadata=E/'maintenance'/output.name
    if metadata_state not in ('absent','present','optional'):raise ValueError('Unknown metadata state')
    if metadata.is_symlink():raise ValueError('Metadata symlink refused')
    exists=metadata.exists()
    if (metadata_state=='absent' and exists) or (metadata_state=='present' and not exists):
        raise ValueError('Metadata freshness/ownership differs')
    if exists and not metadata.is_dir():raise ValueError('Metadata directory required')
    return output,metadata

def pending_paths(metadata):
    metadata=pathlib.Path(metadata)
    if metadata.parent!=E/'maintenance' or re.fullmatch(r'decode-iq2s-persistent-kernel-[0-9]{8}T[0-9]{6}Z',metadata.name) is None:
        raise ValueError('Exact owned pending namespace required')
    real_directory(metadata)
    state=metadata/'state.json'
    if state.is_symlink() or not state.is_file():raise ValueError('Owned pending state file required')
    return state

def expected_case_ids():
    cases=[]
    def direct(d,f,t,ne,grouped,empty,cap,pattern):
        return f'PASS direct D{d} F{f} type{t} ne{ne} grouped{grouped} empty{empty} cap{cap} pattern{pattern}'
    for d,f in [(512,256),(5120,2304)]:
        for cap in [0,1]:
            cases.append(direct(d,f,22,1,0,0,cap,0))
            cases.extend(direct(d,f,22,ne,1,0,cap,0) for ne in [1,2,4,5,8,9,16])
            cases.append(direct(d,f,22,1,1,1,cap,0))
            cases.append(direct(d,f,22,1,0,1,cap,0))
        cases.extend(direct(d,f,22,2,1,0,1,pattern) for pattern in [1,2,3])
        cases.extend([f'PASS public_token D{d} F{f}',f'PASS public_window D{d} F{f}'])
    cases.extend([direct(512,256,17,1,0,0,1,0),direct(512,256,17,5,1,0,1,0)])
    return cases

def check_result(stdout,code,device):
    if type(device) is not int or device not in [0,1] or type(code) is not int or code!=0:
        raise ValueError('Fixture device/exit incomplete')
    expected=expected_case_ids()
    final=f'ALL 52 IQ2_S checks passed device{device}'
    lines=stdout.splitlines()
    if ([x for x in lines if x.startswith('PASS ')]!=expected
        or [x for x in lines if x.startswith('ALL ')]!=[final]
        or any('FAIL' in line for line in lines)):
        raise ValueError('Kernel result missing/duplicate/failed; no regrade')
    return {'device':device,'affected_direct_cases':46,'public_integration_cases':4,
            'unaffected_IQ2_XS_cases':2,'total_cases':52,'test_ids':expected,'exit0':True,
            'actual_dispatch_and_canary_assertions':True,'model_execution':False,'speed_claim':False}
def fixture_contract(binary,expected,output,device):
    output,_=output_paths(output)
    if binary!=P/'build-FIRST/ds4_gguf_test-candidate' or type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected):
        raise ValueError('Unqualified fixture binary')
    if type(device) is not int or device not in [0,1]:raise ValueError('Exact physical GPU required')
    return [str(binary),'--iq2s-persist-check',str(device)]
def owned_cgroup(value):
    return isinstance(value,str) and 'strata-deepseek-window.service' in value.strip().split('/')
def child_identity(pid,binary,command,proc_root=pathlib.Path('/proc')):
    proc=proc_root/str(pid)
    if type(pid) is not int or pid<=0 or not os.path.samefile(proc/'exe',binary):
        raise ValueError('Fixture child executable differs')
    if (proc/'cmdline').read_bytes().decode().split(chr(0))!=[*command,'']:
        raise ValueError('Fixture argv differs')
    cgroup=(proc/'cgroup').read_text()
    if not owned_cgroup(cgroup):
        raise ValueError('Fixture outside existing owned window')
    return {'pid':pid,'same_executable':True,'argv':command,'cgroup':cgroup,
            'start_ticks':int((proc/'stat').read_text().rsplit(') ',1)[1].split()[19])}
def qualified(expected_digest=None):
    raw=(P/'gpu-qualification.json').read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if expected_digest is not None:
        if not isinstance(expected_digest,str) or re.fullmatch('[0-9a-f]{64}',expected_digest) is None or digest!=expected_digest:
            raise ValueError('Frozen kernel qualification changed before use')
    q=json.loads(raw)
    if q.get('source_manually_reviewed') is not True or q.get('CPU_both_hosts_passed') is not True:
        raise ValueError('Unqualified kernel window source')
    if q['files'].get(str(R/'window.py'))!=WINDOW_SHA:raise ValueError('Canonical window source absent')
    if q['files'].get(str(E/'decode-profile-v1/maintenance.py'))!=COORDINATE_SHA:
        raise ValueError('Exact tested canonical coordinate source absent')
    required=[P/'qualify_iq2s_gpu_cpu.py']+[P/('gpu-CPU-'+host)/name for host in ['darwin','linux']
                for name in ['receipt.json','child.json','child.log']]
    if any(str(path) not in q['files'] for path in required):raise ValueError('Exact CPU raw proof/driver pins absent')
    if (q.get('fixture_binary')!=str(P/'build-FIRST/ds4_gguf_test-candidate') or
        q['files'].get(q['fixture_binary'])!=q.get('fixture_sha256')):
        raise ValueError('Exact built fixture must be qualified')
    if set(q['source_sha256'])!={'iq2s_gpu_check.py','test_iq2s_gpu_check.py'}:
        raise ValueError('Exact new controller source inventory required')
    for name,pin in q['source_sha256'].items():
        if sha(P/name)!=pin or q['files'].get(str(P/name))!=pin:raise ValueError('Controller source differs')
    for name,pin in q['files'].items():
        if sha(name)!=pin:raise ValueError('Qualified kernel input changed: '+name)
    for label in ['darwin','linux']:
        proof=json.loads((P/('gpu-CPU-'+label)/'receipt.json').read_text())
        if (proof.get('passed') is not True or proof['source_sha256']!=q['source_sha256'] or
            proof['test_ids']!=q['test_ids'] or not proof['test_ids'] or
            type(proof.get('controls')) is not int or proof['controls']!=len(proof['test_ids']) or
            len(set(proof['test_ids']))!=len(proof['test_ids']) or
            proof.get('GPU_execution') is not False or proof.get('native_execution') is not False):
            raise ValueError('Matching both-host kernel CPU proof absent')
        child=json.loads((P/('gpu-CPU-'+label)/'child.json').read_text())
        bounds={'returncode':0,'CPU_s':30,'wall_s':90,'nice':15,'CUDA_hidden':True,
                'Linux_AS_MiB':512 if label=='linux' else None}
        if (any(type(child.get(k)) is not type(v) or child[k]!=v for k,v in bounds.items())
            or child.get('error') is not None or child.get('cleanup_errors')!=[]):
            raise ValueError('Kernel CPU child failed or supervision/bounds differ')
    return {**q,'qualification_sha256':digest}
def fixture_phase(output,proof_path):
    # Entry executes only inside the established window cgroup and durable state.
    sys.path.insert(0,str(E/'decode-profile-v1'))
    from native_worker import owned_window
    window,_=owned_window()
    if not owned_cgroup(pathlib.Path('/proc/self/cgroup').read_text()):
        raise ValueError('Phase outside actual owned window cgroup')
    output,metadata=output_paths(output,metadata_state='present')
    proof_path=pathlib.Path(proof_path)
    if proof_path!=metadata/'proof.json' or proof_path.is_symlink():raise ValueError('Exact owned proof path required')
    state_path=pending_paths(metadata)
    proof=json.loads(proof_path.read_text());saved=json.loads(state_path.read_text())
    current=json.loads((E/'STATE.json').read_text())
    attempt=json.loads((P/'gpu-attempt.json').read_text())
    if (proof.get('qualified_for_owned_iq2s_kernel') is not True or proof.get('output')!=str(output)
        or saved.get('output')!=str(output) or saved.get('status')!='IQ2S_KERNEL_PRIVATE_RUNNING'
        or current.get('maintenance_controller')!=str(state_path) or current.get('active_private_phase')!=str(metadata)
        or attempt.get('metadata')!=str(metadata) or attempt.get('output')!=str(output)
        or not isinstance(proof.get('qualification_sha256'),str)
        or saved.get('qualification_sha256')!=proof['qualification_sha256']):
        raise ValueError('Wrong kernel admission proof/current ownership')
    q=qualified(proof['qualification_sha256']);binary=pathlib.Path(q['fixture_binary']);pin=q['fixture_sha256']
    commands={device:fixture_contract(binary,pin,output,device) for device in [0,1]}
    output.mkdir()
    if sha(binary)!=pin:raise ValueError('Fixture changed')
    began=time.monotonic();rows=[]
    env={k:v for k,v in os.environ.items() if not k.startswith(('DS4_','MAYA_DS4_','STRATA_DS4_'))}
    env.update(STRATA_DS4_Q8_BATCH='1',DS4_Q8_CHECK='1',DS4_IQ_PERSIST='0',OMP_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1',MALLOC_ARENA_MAX='1')
    for device in [0,1]:
        command=commands[device]
        child=None;identity=None;primary=None;cleanup=[]
        def limits():resource.setrlimit(resource.RLIMIT_CPU,(120,120))
        with (output/f'gpu{device}.stdout').open('xb') as out,(output/f'gpu{device}.stderr').open('xb') as err:
            try:
                if time.monotonic()-began>=900:raise TimeoutError('Unstarted fixture exceeds soft budget')
                child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,env=env,
                                       preexec_fn=limits)
                identity=child_identity(child.pid,binary,command)
                emit(output/f'gpu{device}-start.json',identity)
                code=child.wait(timeout=120)
                if code!=0:raise RuntimeError('FIRST fixture failed: exit'+str(code))
            except BaseException as exc:primary=exc
            finally:
                if child is not None and child.poll() is None:
                    try:child.terminate();child.wait(timeout=10)
                    except BaseException as exc:
                        cleanup.append(repr(exc))
                        try:child.kill();child.wait(timeout=10)
                        except BaseException as exc2:cleanup.append(repr(exc2))
                try:
                    emit(output/f'gpu{device}-exit.json',{'pid':getattr(child,'pid',None),
                        'identity':identity,'returncode':getattr(child,'returncode',None),
                        'primary':repr(primary) if primary else None,'cleanup_errors':cleanup,'retry':False})
                except BaseException as receipt_error:
                    if primary is None:primary=receipt_error
                    else:primary.add_note('Fixture terminal receipt failed: '+repr(receipt_error))
        if primary is not None:raise primary
        if cleanup:raise RuntimeError('Fixture cleanup fault')
        rows.append(check_result((output/f'gpu{device}.stdout').read_text(),child.returncode,device))
        if sha(binary)!=pin:raise ValueError('Fixture changed during window')
    result={'passed':True,'window':str(window),'devices':rows,'fixture_sha256':pin,
            'GPU_kernel_execution':True,'model_execution':False,'speed_claim':False}
    emit(output/'kernel-receipt.json',result)
    return 0

def host_class(a):
    class KernelHost(a.ChunkProductionHost):
        baseline_binding=None
        def baseline_reader(self):
            if not self.baseline_binding:raise ValueError('Current selected4096 binding required')
            reader=a.ChunkProductionHost();reader.start_binding=dict(self.baseline_binding)
            reader.audit_dir=self.audit_dir
            return reader
        def preflight(self,output):
            if not self.idle():raise a.m.old.AdmissionDeferred('Busy; untouched')
            state=json.loads((E/'STATE.json').read_text())
            if not phase_keys_free(state):raise a.m.old.AdmissionDeferred('Other phase/pending verification')
            q=qualified(self.qualification_sha256)
            for path in [P,E/'results',E/'maintenance']:a.real_ancestors(path)
            if not isinstance(self.baseline_binding,dict):raise ValueError('No selected baseline binding')
            self.baseline_reader().guard_binding(self.baseline_binding['native_pid'])
            self.baseline_reader().target_identity();self.previous()
            import shutil
            if shutil.disk_usage('/').free<132*2**30:raise a.m.old.AdmissionDeferred('Root132 unavailable')
            output_paths(output,metadata_state='present')
            return {'qualified_for_owned_iq2s_kernel':True,'output':str(output),'files':q['files'],
                    'qualification_sha256':self.qualification_sha256}
        def launch(self,prior,output,proof):
            return self.launch_owned(prior,[str(R/'venv/bin/python3.14'),'-B',str(P/'iq2s_gpu_check.py'),
                '--phase','--output',str(output),'--proof',str(proof)],1200)
        def verify(self):
            return self.verify_target(expected_pid=self.restored_pid)
    return KernelHost

class PendingCustodyChanged(ValueError):pass

def normalize_pending(value):
    if (value.get('verified',{}).get('pending_public_probe')
        and value['status']!='IQ2S_KERNEL_SELECTED_RUNNING_PUBLIC_VERIFY_PENDING'):
        value['resume_terminal_status']=value['status']
        value['status']='IQ2S_KERNEL_SELECTED_RUNNING_PUBLIC_VERIFY_PENDING'
    return value

def coordinate_kernel(a,host,output,state,save,*,preflight_only=False,root_free=None):
    host.restored_pid=None
    def tracked(value):
        normalize_pending(value);save(value)
    try:
        return a.m.old.coordinate(host,output,state,tracked,preflight_only=preflight_only,
                                  post_drain_root_free_bytes=root_free)
    except BaseException as primary:
        cleanup=None
        if type(host.restored_pid) is int and host.restored_pid>0:
            try:host.cleanup_owned_target(host.restored_pid)
            except BaseException as exc:cleanup=repr(exc)
        try:
            save(dict(state,status='STOPPED_FOR_OFFLINE_DIAGNOSIS',error=repr(primary),
                      cleanup_error=cleanup,start_binding=getattr(host,'start_binding',None),
                      start_command_cleanup_error=getattr(host,'start_command_cleanup_error',None)))
        except BaseException as receipt_error:primary.add_note('Kernel HOLD save failed: '+repr(receipt_error))
        raise

def make_saver(host,metadata,*,run):
    def save(value):
        normalize_pending(value)
        value.update(start_binding=getattr(host,'start_binding',None),kernel_since=host.since,
                     start_command_cleanup_error=getattr(host,'start_command_cleanup_error',None))
        emit(metadata/'state.json',value)
        status=value['status']
        # These outcomes have never claimed or drained production. Preserve the entire global state.
        if not run or status in ['PREFLIGHT_OK','DEFERRED_NO_PRODUCTION_MUTATION',
                                  'DEFERRED_BUSY_OR_MANUAL_MODEL_NO_MUTATION']:return
        state_now=json.loads((E/'STATE.json').read_text())
        if status=='DRAINING_ROUTER':
            if not phase_keys_free(state_now) or selected_binding(state_now)!=host.baseline_binding:
                raise ValueError('Admission changed before owned drain; untouched')
        elif state_now.get('maintenance_controller')!=str(metadata/'state.json'):
            raise ValueError('Foreign controller replacement preserved')
        previous=state_now.get('decode_optimization_current',{}).get('selected_identity')
        if previous is None:previous=state_now.get('chunk4096_activation',{}).get('selected_identity')
        if value.get('verified',{}).get('selected_identity') is not None:
            value['selected_identity']=value['verified']['selected_identity']
        elif previous is not None:value['selected_identity']=previous
        if status=='IQ2S_KERNEL_PRIVATE_RUNNING':
            with (P/'gpu-attempt.json').open('x') as attempt:
                attempt.write(json.dumps({'metadata':str(metadata),'output':value['output'],
                                          'qualification_sha256':value['qualification_sha256'],'retry':False})+'\n')
        active=status in ['DRAINING_ROUTER','IQ2S_KERNEL_PRIVATE_RUNNING','CLEAN_PHASE_RESTORING_SELECTED_DS']
        state_now.update(decode_optimization_current=value,maintenance_controller=str(metadata/'state.json'),
                         active_gpu_experiment=active,active_private_phase=str(metadata) if active else None,
                         production_temporarily_stopped=active or status=='STOPPED_FOR_OFFLINE_DIAGNOSIS')
        if 'verified' in value:
            proof=value['verified']
            if proof.get('pending_public_probe'):
                state_now['production_verification_pending']=str(metadata/'state.json')
            elif proof.get('passed') is True:
                state_now['production_verification_pending']=False
                state_now['current_native_pid']=proof['selected_identity']['native_pid']
        emit(metadata/'state.json',value);emit(E/'STATE.json',state_now)
    return save

def verify_pending(a,metadata):
    state_path=pending_paths(metadata);value=json.loads(state_path.read_text())
    current=json.loads((E/'STATE.json').read_text())
    if (value.get('status')!='IQ2S_KERNEL_SELECTED_RUNNING_PUBLIC_VERIFY_PENDING' or
        current.get('production_verification_pending')!=str(state_path) or
        current.get('maintenance_controller')!=str(state_path)):
        raise ValueError('No exact pending continuation; no replay')
    if any(current.get(k) for k in ['active_private_phase','active_GPU_phase','active_gpu_experiment','private_window','active_cpu_build','production_restore_in_progress']):
        raise ValueError('Another phase; untouched')
    binding=selected_binding({'decode_optimization_current':{'selected_identity':{'start_binding':value['start_binding']}}})
    host=host_class(a)();host.start_binding=binding;host.restored_pid=binding['native_pid']
    host.audit_dir=metadata;host.since=value['kernel_since']
    host.guard_binding(host.restored_pid)
    if not host.idle():return {'status':'DEFERRED_BUSY_UNTOUCHED'}
    qualified(value['qualification_sha256'])
    try:
        proof=host.verify_target(expected_pid=host.restored_pid)
        if proof.get('pending_public_probe'):return {'status':'DEFERRED_BUSY_UNTOUCHED'}
        if proof.get('passed') is not True:raise ValueError('Pending selected verification failed')
        if json.loads((E/'STATE.json').read_text())!=current or json.loads(state_path.read_text())!=value:
            raise PendingCustodyChanged('Pending custody changed during verification')
        value.update(status=value.get('resume_terminal_status','IQ2S_KERNEL_COMPLETE_SELECTED4096_RESTORED'),
                     verified=proof,selected_identity=proof['selected_identity'])
        emit(state_path,value)
        current.update(decode_optimization_current=value,production_verification_pending=False,
                       current_native_pid=proof['selected_identity']['native_pid'])
        emit(E/'STATE.json',current);emit(metadata/'result.json',value)
        return value
    except BaseException as primary:
        cleanup=None
        if not isinstance(primary,PendingCustodyChanged):
            try:host.cleanup_owned_target(host.restored_pid)
            except BaseException as exc:cleanup=repr(exc)
        hold={**value,'status':'STOPPED_FOR_OFFLINE_DIAGNOSIS','error':repr(primary),'cleanup_error':cleanup,
              'start_command_cleanup_error':getattr(host,'start_command_cleanup_error',None)}
        # A replacement controller's canonical state is never rewritten by this continuation.
        try:
            emit(metadata/'pending-failure.json',hold)
            if json.loads((E/'STATE.json').read_text())==current:
                emit(state_path,hold);current.update(decode_optimization_current=hold,production_temporarily_stopped=True)
                emit(E/'STATE.json',current)
        except BaseException as receipt_error:primary.add_note('Pending HOLD receipt failed: '+repr(receipt_error))
        raise

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',action='store_true')
    parser.add_argument('--output',type=pathlib.Path);parser.add_argument('--proof',type=pathlib.Path)
    parser.add_argument('--run',action='store_true');parser.add_argument('--verify',type=pathlib.Path);args=parser.parse_args()
    if args.verify and (args.phase or args.run):raise ValueError('Verification cannot launch a phase')
    if args.verify:
        sys.path.insert(0,str(F));import activate_chunk4096 as a
        return verify_pending(a,args.verify)
    if args.phase:return fixture_phase(args.output,args.proof)
    if args.run and (P/'gpu-attempt.json').exists():raise ValueError('Kernel window already attempted; no replay')
    sys.path.insert(0,str(F));import activate_chunk4096 as a
    real_directory(P)
    host=host_class(a)()
    current=json.loads((E/'STATE.json').read_text())
    if not phase_keys_free(current):raise ValueError('Other phase/pending verification; untouched')
    if not host.idle():return {'status':'DEFERRED_BUSY_UNTOUCHED'}
    q=qualified();host.qualification_sha256=q['qualification_sha256']
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output=E/'results'/('decode-iq2s-persistent-kernel-'+stamp);_,metadata=output_paths(output,metadata_state='absent')
    metadata.mkdir(mode=0o700,exist_ok=False)
    host.audit_dir=metadata
    host.baseline_binding=selected_binding(current)
    state={'utc':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        'output':str(output),'proof_path':str(metadata/'proof.json'),'qualification_sha256':q['qualification_sha256'],
        'running_status':'IQ2S_KERNEL_PRIVATE_RUNNING','complete_status':'IQ2S_KERNEL_COMPLETE_SELECTED4096_RESTORED',
        'completion_scope':'Kernel correctness only; no model inference/speed claim'}
    save=make_saver(host,metadata,run=args.run)
    host.since=state['utc']
    # Existing coordinate owns drain, old-native close/free, window and one selected restoration.
    result=coordinate_kernel(a,host,output,state,save,preflight_only=not args.run,
        root_free=lambda:__import__('shutil').disk_usage('/').free)
    emit(metadata/'result.json',result)
    return result
if __name__=='__main__':
    result=main()
    if isinstance(result,int):raise SystemExit(result)
    print(json.dumps(result))
