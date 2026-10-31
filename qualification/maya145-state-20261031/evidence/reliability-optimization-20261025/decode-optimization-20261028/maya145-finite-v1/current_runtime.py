"""New Maya145 compatibility admission over the unchanged selected4096 owner.

Imports are pure. No prior arm is reopened, no source globals are patched, and
production restoration always uses the original qualified native92 owner.
"""
import copy
import datetime
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import current_config as config

P=Path(__file__).resolve().parent
E=P.parents[1]
R=Path('/home/alex/strata-deepseek-test-20261024')
D=Path('/home/alex/deepseek-hosted-20261025')
Q=P.parent/'maya-s-comparison-v1'
MEMORY_MAX=80*2**30
HOST_MARGIN=8*2**30
PHASE_KEYS=('active_private_phase','active_GPU_phase','active_gpu_experiment','private_window','active_cpu_build',
            'production_restore_in_progress','production_verification_pending','production_temporarily_stopped')
COMPAT_CASE_ID='finite44-cold'
REUSED={'performance-v2/pv_runtime.py':'1811228e83217b961ae4ffed9c430f49edf10c3af999b4fd6753518a25001e58',
        'performance-v2/pv_config.py':'3c4b576866dd579823139644d072a547bc477696a3bb3406d0d55fdf6930c513',
        'performance-v2/pv_controls.py':'1038fad719fb7ed7516ab3e07d88d40fb3b5cd7408f6ed19ddc2296f13052cf5'}
NEW_SOURCES=('engine_profile.py','current_config.py','current_runtime.py','current_controls.py','current_compat.py',
             'test_current_mode.py','run_current_cpu.py','test_finite_controls.py','PACK_STATE_SOURCE.json')


def require(ok,why):
    if not ok:raise ValueError(why)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(65536),b''):h.update(block)
    return h.hexdigest()


def emit(path,value):
    path=Path(path);require(path.parent.is_dir() and not path.is_symlink(),'Owned receipt path')
    tmp=path.with_name(path.name+'.tmp');require(not tmp.exists() and not tmp.is_symlink(),'Preserve receipt residue')
    with tmp.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
    tmp.replace(path)


def reusable(name):
    require(name in ('pv_runtime','pv_controls'),'Reviewed helper only')
    for relative,pin in REUSED.items():require(sha(Q/relative)==pin,'Qualified helper changed')
    path=Q/'performance-v2'/(name+'.py');loaded=sys.modules.get(name)
    require(loaded is None or Path(loaded.__file__)==path,'Foreign cached helper')
    sys.path.insert(0,str(path.parent));m=importlib.import_module(name)
    require(Path(m.__file__)==path,'Helper origin');return m


def legacy_controls():
    original_module('ms_runtime')
    path=Q/'model-v1/ms_controls.py'
    require(sha(path)=='bec61db8733964af590f12d84044d6dbe6c30ea36014e394da64dc95b48bb20a','Original controls changed')
    loaded=sys.modules.get('ms_controls');require(loaded is None or Path(loaded.__file__)==path,'Foreign original controls')
    sys.path.insert(0,str(path.parent));m=importlib.import_module('ms_controls')
    require(Path(m.__file__)==path,'Original controls origin');return m


def support():return reusable('pv_runtime').support()
def original_module(name):return reusable('pv_runtime').original_module(name)
def compatibility_manifest():
    m=copy.deepcopy(original_module('ms_runtime').compatibility_manifest())
    case=m['cases'][0];case['id']='finite44-cold';warm=copy.deepcopy(case);warm.update(id='finite44-warm',expected_reuse='prompt-minus-one',dependency='finite44-cold');m.update(mode='finite',cases=[case,warm],purpose='UNMEASURED_FULL_MODEL_FINITE_AND_CACHE_STATE_ONLY',quality_or_performance_pass=False,automatic_next_arm=False);return m
def memory_available():return reusable('pv_runtime').memory_available()
def phase_free(state):return not any(state.get(k) for k in PHASE_KEYS)


def statuses(mode):
    require(mode=='finite','New short compatibility only')
    return {k:'MAYA145_FINITE_'+v for k,v in
            (('running','PRIVATE_RUNNING'),('complete','SELECTED4096_RESTORED'),('pending','PUBLIC_VERIFY_PENDING'))}


def owned_paths(output,mode,arm,*,present=False):
    variant=config.variant(mode,arm);output=Path(output)
    require(output.parent==E/'results' and '..' not in output.parts
        and re.fullmatch('maya145-finite-mayas-'+variant+r'-[0-9]{8}T[0-9]{6}Z',output.name),'New variant namespace required')
    metadata=E/'maintenance'/output.name
    for root in (E/'results',E/'maintenance'):
        require(root.is_dir() and root.resolve()==root,'Real owned parent required')
    require(not output.is_symlink() and not metadata.is_symlink(),'Leaf alias')
    require(output.is_dir() if present else not output.exists(),'Fresh/present output contract')
    return output,metadata


def prerequisite(mode,arm,registry):
    config.factor(mode,arm)
    require(type(registry) is dict and set(registry)<=set(config.MODE_ARMS[mode]) and arm not in registry,
            'Preserve every attempted arm; no replay')
    # The profiles have independent first compatibility attempts. Neither one
    # grants admission to timing or to the other profile automatically.
    require(all(row.get('fully_reviewed') is True and row.get('accepted') is True for row in registry.values()),'Earlier attempt needs independent review')


def cpu_contract(group,receipt,child,platform):
    require(receipt.get('passed') is True and receipt.get('controls')==len(group['test_ids'])
        and receipt.get('test_ids')==group['test_ids'] and len(set(group['test_ids']))==len(group['test_ids'])
        and receipt.get('source_sha256')==group['source_sha256']
        and receipt.get('input_sha256')==group['input_sha256'],'Exact new source/input/test IDs required')
    require(type(child.get('returncode')) is int and child['returncode']==0
        and child.get('error') is None and child.get('cleanup')==[] and child.get('elapsed_seconds',100)>0
        and child['elapsed_seconds']<90,'Actual clean bounded CPU child required')
    actual=receipt['observed'];env={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
        'MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}
    require(actual['cpu']==[30,30] and actual['as']==([512*2**20]*2 if platform=='linux' else None)
        and actual['platform']==platform and actual['nice']==15 and actual['environment']==env
        and actual['pgid']==actual['pid']==child['pid'] and actual['dont_write_bytecode'] is True,
        'Observed CPU30/AS512/nice15/CUDAhidden child-only bounds required')


def qualification_path():return P/'finite-qualification.json'


def await_headroom(read,guard,*,clock,pause,samples):
    """One bounded observation of actual release; never lower the88GiB floor."""
    import math
    began=clock()
    while True:
        guard();available=read();elapsed=clock()-began
        require(type(available) is int and available>=0 and math.isfinite(elapsed) and elapsed>=0,
                'Typed actual memory and monotonic clock required')
        samples.append({'elapsed_seconds':elapsed,'available_bytes':available})
        if elapsed>60:raise ResourceAdmissionDeferred('Post-stop memory observation deadline')
        if available>=MEMORY_MAX+HOST_MARGIN:return available
        if elapsed>=60:raise ResourceAdmissionDeferred('Physical memory floor unavailable within60s; no launch')
        pause(min(1,60-elapsed))


def qualified(mode,expected):
    require(mode=='finite','No timing or promotion admission in this mode')
    path=qualification_path()
    require(sha(path)==expected,'Exact immutable mode qualification')
    q=json.loads(path.read_text())
    require(q['mode']==mode and q['root_manual_review'] is True and q['context']==1048576
        and q['output_allowance']==262144 and q['benchmark_cap']==32768 and q['effort']==100
        and q['drafting'] is True and q['recovery_capability_prospectively_qualified'] is True,'Full policy/recovery qualification')
    for name,pin in q['files'].items():
        p=Path(name);require(p.is_absolute() and p.resolve()==p and not p.is_symlink() and p.is_file()
            and sha(p)==pin,'Immutable qualification input changed: '+name)
    require(q['files'].get(str(R/'window.py'))=='170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f'
        and q['files'].get(str(D/'bin/maya-ds4'))==config.SELECTED_NATIVE
        and q['files'].get(str(D/'config.json'))==config.BASE_SHA
        and q['files'].get(str(config.profile.NATIVE))==config.BASE_NATIVE,'Window/selected/new native custody')
    for name in NEW_SOURCES:
        require(q['files'].get(str(P/name))==sha(P/name)
            and any(g['source_sha256'].get(name)==sha(P/name) for g in q['CPU_groups']),
            'Changed source missing from both-host CPU proof: '+name)
    for group in q['CPU_groups']:
        for name,pin in group['source_sha256'].items():
            require(q['files'].get(str(P/name))==pin,'CPU source omitted from qualification')
        require(set(group['input_paths'])==set(group['input_sha256']),'Exact CPU input mapping required')
        for name,pin in group['input_sha256'].items():
            require(q['files'].get(group['input_paths'][name])==pin,'CPU input omitted from qualification')
        require(set(group['proofs'])=={'darwin','linux'},'Two physical CPU proofs required')
        for platform,paths in group['proofs'].items():
            require(set(paths)=={'receipt','child','log'} and all(q['files'].get(p)==sha(p) for p in paths.values()),'Raw CPU proof omitted')
            cpu_contract(group,json.loads(Path(paths['receipt']).read_text()),json.loads(Path(paths['child']).read_text()),platform)
    require(q['CPU_groups'] and q['native_source_controls_reviewed'] is True
        and q['private_memory_max']==MEMORY_MAX and q['host_margin']==HOST_MARGIN,'Native source controls/resource envelope')
    prior=reusable('pv_runtime')
    prior.pack_custody(q)  # existing public weight bytes/stat identities, no prior engine-result substitution
    artifact=json.loads((P.parent/'maya145-mayas-v1/BUILD-ARTIFACT-AUDIT-FIRST/result.json').read_text())
    require(artifact.get('passed') is True and artifact['native_sha256']==config.BASE_NATIVE
        and artifact['original_supervision_regraded'] is False,'Separate compiler artifact completion required')
    compatibility_manifest()
    require(sha(path)==expected,'Qualification changed while checking')
    return q


class ResourceAdmissionDeferred(RuntimeError):pass


def make_host(a,old,base,legacy,startup):
    prior=reusable('pv_runtime').make_host(a,old,base,legacy,startup)
    class CurrentHost(prior):
        def preflight(self,output):
            q=qualified(self.mode,self.qualification_sha256);current=json.loads((E/'STATE.json').read_text())
            require(phase_free(current) and base.current_binding(current)==self.baseline_binding,'Phase/current owner changed')
            require(self.idle() and shutil.disk_usage('/').free>=132*2**30,'Selected healthy/default/root132')
            reader=self.baseline_reader();reader.guard_binding(self.baseline_pid)
            identity=reader.target_identity();reader.guard_binding(self.baseline_pid)
            prerequisite(self.mode,self.arm,json.loads((P/'finite-arms.json').read_text()))
            self.previous();self.extra_preflight(output)
            return {'qualified_for_owned_maya_s':True,'mode':self.mode,'arm':self.arm,'output':str(output),
                'qualification_sha256':self.qualification_sha256,'files':q['files'],'baseline_identity':identity,
                'explicit_interruption_authorized':True,'private_memory_max':MEMORY_MAX}
        def free(self):
            # The reused host's free raises its own ResourceAdmissionDeferred;
            # translate that exact class only, preserving all genuine failures.
            try:return super().free()
            except reusable('pv_runtime').ResourceAdmissionDeferred as exc:
                if (getattr(self,'private_attempted',False) or not getattr(self,'old_close_verified',False)
                        or getattr(self,'start_binding',None) is not None):
                    raise ResourceAdmissionDeferred(str(exc)) from exc
                import time
                emit(self.audit_dir/'post-stop-memory-initial.json',
                     json.loads((self.audit_dir/'post-stop-memory.json').read_text()))
                def guard():
                    state=json.loads((E/'STATE.json').read_text());active=state.get('decode_optimization_current',{})
                    require(state.get('maintenance_controller')==str(self.audit_dir/'state.json')
                        and state.get('active_private_phase')==str(self.audit_dir)
                        and active.get('controller_pid')==self.controller_pid
                        and active.get('mode')==self.mode and active.get('arm')==self.arm
                        and active.get('selected_identity',{}).get('start_binding')==self.baseline_binding
                        and state.get('production_temporarily_stopped') is True
                        and not state.get('active_cpu_build') and not state.get('production_verification_pending'),
                        'Exact own pre-window memory-observation custody required')
                row={'maximum_seconds':60,'required_bytes':MEMORY_MAX+HOST_MARGIN,'samples':[],
                     'passed':False,'private_window_extended':False,'private_arm_attempted':False}
                primary=None
                try:
                    row['available_bytes']=await_headroom(memory_available,guard,clock=time.monotonic,
                        pause=time.sleep,samples=row['samples'])
                    guard();result=super().free()  # recheck sole GPU/lock and actual floor before any reserve
                    row['passed']=True;return result
                except reusable('pv_runtime').ResourceAdmissionDeferred as failure:
                    primary=ResourceAdmissionDeferred(str(failure));raise primary from failure
                except BaseException as failure:
                    primary=failure;raise
                finally:
                    if primary is not None:row['error']=repr(primary)
                    try:emit(self.audit_dir/'post-stop-memory-wait.json',row)
                    except BaseException as receipt:
                        if primary is None:raise
                        primary.add_note('Memory wait receipt: '+repr(receipt))
        def launch(self,prior,output,proofpath):
            qualified(self.mode,self.qualification_sha256)
            require(Path(proofpath)==self.audit_dir/'proof.json','Exact proof path')
            self.reserve_attempt(output,proofpath);self.private_attempted=True;self.private_output=str(output)
            return self.launch_owned(prior,self.phase_argv(output,proofpath),1200)
    return CurrentHost


def saver(host, mode, arm):
    status = statuses(mode)
    def save(value):
        value = copy.deepcopy(value)
        require(value.get('qualification_sha256') == host.qualification_sha256, 'Controller qualification changed')
        value.update(mode=mode, arm=arm, controller_pid=host.controller_pid,
                     start_binding=copy.deepcopy(host.start_binding), kernel_since=host.since)
        if value.get('verified', {}).get('pending_public_probe'):
            value['resume_terminal_status'] = value['status']; value['status'] = status['pending']
        emit(host.audit_dir / 'state.json', value)
        if value['status'] in ('PREFLIGHT_OK', 'DEFERRED_NO_PRODUCTION_MUTATION', 'DEFERRED_BUSY_OR_MANUAL_MODEL_NO_MUTATION'): return
        current = json.loads((E / 'STATE.json').read_text()); before = copy.deepcopy(current)
        if value['status'] == 'DRAINING_ROUTER':
            require(phase_free(current) and current['decode_optimization_current']['selected_identity']['start_binding'] == host.baseline_binding,
                    'Reservation changed before drain')
        else:
            require(current.get('maintenance_controller') == str(host.audit_dir / 'state.json')
                    and current.get('decode_optimization_current', {}).get('controller_pid') == host.controller_pid,
                    'Foreign maintenance controller; no canonical overwrite')
        previous = current['decode_optimization_current']['selected_identity']
        verified = value.get('verified', {}); value['selected_identity'] = verified.get('selected_identity', previous)
        active = value['status'] in ('DRAINING_ROUTER', status['running'], 'CLEAN_PHASE_RESTORING_SELECTED_DS',
                                     'DEFERRED_BEFORE_PRIVATE_WINDOW_RESTORING_SELECTED_DS')
        current.update(decode_optimization_current=value, maintenance_controller=str(host.audit_dir / 'state.json'),
                       active_gpu_experiment=active, active_private_phase=str(host.audit_dir) if active else None,
                       production_temporarily_stopped=active or value['status'] == 'STOPPED_FOR_OFFLINE_DIAGNOSIS')
        if host.old_close_verified and host.start_binding is None:
            current['current_native_pid'] = None  # raw bound old API/native close0 already observed
        if verified.get('pending_public_probe'): current['production_verification_pending'] = str(host.audit_dir / 'state.json')
        elif verified.get('passed') is True:
            current['production_verification_pending'] = False; current['current_native_pid'] = value['selected_identity']['native_pid']
        emit(host.audit_dir / 'state.json', value)
        require(json.loads((E / 'STATE.json').read_text()) == before, 'Canonical state changed before commit')
        emit(E / 'STATE.json', current)
    return save


def hold_owned(host, state, save, primary):
    """Never clean up a foreign owner or turn a failed observation into success."""
    ours = False; cleanup = None
    try:
        current = json.loads((E / 'STATE.json').read_text())
        ours = (current.get('maintenance_controller') == str(host.audit_dir / 'state.json')
                and current.get('decode_optimization_current', {}).get('controller_pid') == host.controller_pid)
    except BaseException as exc: primary.add_note('Cannot establish cleanup custody: ' + repr(exc))
    if ours and type(host.restored_pid) is int and host.restored_pid > 0:
        try: host.cleanup_owned_target(host.restored_pid)
        except BaseException as exc: cleanup = repr(exc)
    if ours and getattr(host, 'private_attempted', False):
        try: host.free()  # existing GPU/lock-free check, then exact transient collection
        except BaseException as exc:
            primary.add_note('Private phase cleanup/collection remains incomplete: ' + repr(exc))
    value = dict(state, status='STOPPED_FOR_OFFLINE_DIAGNOSIS', error=repr(primary), cleanup_error=cleanup,
                 start_binding=host.start_binding,
                 start_command_cleanup_error=getattr(host, 'start_command_cleanup_error', None))
    try: save(value)
    except BaseException as exc: primary.add_note('Owned HOLD save failed: ' + repr(exc))


def coordinate(old, host, output, state, save, *, preflight_only):
    try:
        return old.coordinate(host, output, state, save, preflight_only=preflight_only,
                              post_drain_root_free_bytes=lambda: shutil.disk_usage('/').free)
    except ResourceAdmissionDeferred:
        # The controller handles this exact pre-window refusal separately.
        raise
    except BaseException as primary:
        hold_owned(host, state, save, primary)
        raise


def verify_pending(mode, arm, metadata):
    """Only finish an already restored owner's public audit, without a restart."""
    metadata = Path(metadata); path = metadata / 'state.json'
    value = json.loads(path.read_text()); current = json.loads((E / 'STATE.json').read_text())
    output, expected = owned_paths(E / 'results' / metadata.name, mode, arm,
                                   present=(E / 'results' / metadata.name).is_dir())
    require(metadata == expected and value.get('mode') == mode and value.get('arm') == arm
            and value.get('output') == str(output) and value.get('proof_path') == str(metadata / 'proof.json')
            and value.get('status') == statuses(mode)['pending']
            and value.get('resume_terminal_status') in (statuses(mode)['complete'], 'RESOURCE_DEFERRED_SELECTED_RESTORED',
                                                       'DEFERRED_PRIVATE_ADMISSION_SELECTED_DS_RESTORED')
            and current.get('maintenance_controller') == current.get('production_verification_pending') == str(path)
            and current.get('decode_optimization_current') == value
            and not any(current.get(k) for k in PHASE_KEYS if k != 'production_verification_pending'),
            'No exact pending public-audit continuation')
    pid = value.get('controller_pid'); require(type(pid) is int and pid > 0, 'Original typed controller PID')
    try: os.kill(pid, 0)
    except ProcessLookupError: pass
    else: raise ValueError('Original controller remains alive; no concurrent audit')
    qualified(mode, value['qualification_sha256'])
    a, old, base, legacy, startup = support()
    h = make_host(a, old, base, legacy, startup)(); h.start_binding = base.binding_contract(value['start_binding'])
    h.restored_pid = h.start_binding['native_pid']; h.since = value['kernel_since']; h.audit_dir = metadata
    h.mode, h.arm, h.controller_pid = mode, arm, pid
    h.qualification_sha256 = value['qualification_sha256']; h.baseline_binding = h.start_binding
    h.guard_binding(h.restored_pid)
    if not h.idle(): return {'status': 'DEFERRED_BUSY_UNTOUCHED'}
    try:
        verified = h.verify()
        if verified.get('pending_public_probe'): return {'status': 'DEFERRED_BUSY_UNTOUCHED'}
        require(verified.get('passed') is True, 'Pending public audit failed')
    except BaseException as primary:
        if json.loads((E / 'STATE.json').read_text()) == current:
            hold_owned(h, value, saver(h, mode, arm), primary)
        raise
    require(json.loads((E / 'STATE.json').read_text()) == current and json.loads(path.read_text()) == value,
            'Pending custody changed; no canonical overwrite')
    value.update(status=value['resume_terminal_status'], verified=verified)
    saver(h, mode, arm)(value); emit(metadata / 'result.json', value)
    return value


def stat_observer():
    folder=P.parent/'adaptive-expert-cache-v1/performance-v1'
    pins={'ae_controls.py':'2ffec310fffaf166ac243826c91fd733fd4bb8a3a8ac903632b93d92132d5465','ae_runtime.py':'b5c5be169e58ddeae399a2226cf1f5985c303c84c2973780f839add448de52e7','ae_config.py':'e31a30b829be090a13e518f3a6ab1a4cb5600286261c0bc6457854c7bc021d20'}
    for name,pin in pins.items():
        require(sha(folder/name)==pin,'Existing STAT observer source changed')
        loaded=sys.modules.get(name[:-3])
        require(loaded is None or Path(loaded.__file__)==folder/name,'Foreign cached STAT observer')
    sys.path.insert(0,str(folder));m=importlib.import_module('ae_controls')
    require(Path(m.__file__)==folder/'ae_controls.py','Exact STAT observer origin');return m
