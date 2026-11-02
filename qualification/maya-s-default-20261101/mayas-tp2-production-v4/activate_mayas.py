"""Single existing-owner activation of explicitly selected, tested Maya-S TP2.

No model arithmetic, new engine build, model benchmark, or action on import.
Publication follows exact old native/API exit0. A failed activation stays failed.
"""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

import policy as p

HERE = Path(__file__).resolve().parent
RELEASE = 'deepseek-maya-s-tp2-1m-vision-q8-yoco1-output256k-20261101'
SOURCES = ('policy.py','activate_mayas.py','hosting_preflight.py','hosting_ready.py','test_activation.py','run_cpu.py','prepare.py')
PHASES = ('active_private_phase','active_GPU_phase','active_gpu_experiment','private_window','active_cpu_build',
          'production_restore_in_progress','production_verification_pending','production_temporarily_stopped')
CAS_SHA = '8d10d003bbbd7ffbb87251bacdf53d91af9f074151d34f06c957fa179f3108cf'
CPU_ENV = {'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
           'NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(2**20), b''): h.update(b)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text())


def emit(path, value):
    path = Path(path); tmp = path.with_name(path.name+'.new')
    p.require(not path.is_symlink() and not tmp.exists() and not tmp.is_symlink(), 'Owned atomic receipt')
    with tmp.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def fingerprint(path):
    path = Path(path)
    p.require(path.is_absolute() and not path.is_symlink() and path.is_file() and path.resolve() == path, 'Real explicit file')
    s = path.stat(); p.require(s.st_nlink == 1, 'No hardlink alias')
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def cpu_contract(r, c, review, platform):
    p.require(r['passed'] is True and r['returncode'] == 0 and r['controls'] == len(review['test_ids']) and
              r['test_ids'] == review['test_ids'] and len(set(r['test_ids'])) == r['controls'] > 0 and
              r['source_map'] == review['source_map'] and r['input_map'] == review['input_map'] and
              r['failures'] == r['errors'] == 0 and c['returncode'] == 0 and c['cleanup'] == [] and c['error'] is None,
              'Both physical matching bounded CPU proofs')
    ob = r['observed']
    p.require(ob['platform'] == platform and ob['cpu'] == [30,30] and ob['nice'] == 15 and
              ob['as'] == ([512*2**20]*2 if platform == 'linux' else None) and ob['environment'] == CPU_ENV and
              ob['pid'] == ob['pgid'] == c['pid'] and ob['ppid'] == r['supervisor_pid'] and
              ob['dont_write_bytecode'] is True and r['isolated'] is True and 0 <= c['elapsed_seconds'] <= 90,
              'Observed physical child-only CPU/AS/PID/environment/wall bounds')


def qualified(pin):
    path = HERE/'qualification.json'; p.require(sha(path) == pin, 'Exact activation qualification')
    q = read(path)
    p.require(q['root_entire_source_tests_read'] is True and q['user_selected_MayaS_TP2'] is True and
              q['context_total'] == 1048576 and q['output_allowance'] == 262144 and
              q['native_sha256'] == p.NATIVE_SHA, 'Explicit source/model/capacity selection')
    for name, expected in q['files'].items(): p.require(sha(name) == expected, 'Qualified input drift: '+name)
    sm = {n:sha(HERE/n) for n in SOURCES}
    review = read(HERE/'ROOT_SOURCE_REVIEW.json')
    p.require(review['source_map'] == sm and review['entire_source_tests_driver_manually_read'] is True, 'Exact manual source review')
    spec = importlib.util.spec_from_file_location('mayas_qualified_CPU_inputs',HERE/'run_cpu.py')
    driver = importlib.util.module_from_spec(spec); spec.loader.exec_module(driver)
    p.require(driver.inputs() == review['input_map'], 'Actual CPU inputs unchanged')
    for platform in ('darwin','linux'):
        r = read(HERE/('CPU-FIRST-'+platform+'.json')); c = read(HERE/('CPU-FIRST-'+platform)/'child.json')
        cpu_contract(r,c,review,platform)
    for name, row in q['assets'].items(): p.require(fingerprint(name) == row['fingerprint'], 'Published asset changed')
    p.config_contract(read(HERE/'base-config.json'), read(HERE/'candidate-config.json'))
    p.require(sha(HERE/'candidate-config.json') == q['target_config_sha256'], 'Exact target config')
    return q


def legacy_import_guard():
    cached = sys.modules.get('activate')
    expected = p.E/'prefill-cache-improvements-20261027/activation-v1/activate.py'
    p.require(cached is None or Path(getattr(cached,'__file__','')).resolve() == expected,
              'Foreign cached legacy activation module; never replace or adopt it')


def support(q):
    legacy_import_guard()
    root = p.DC/'iq2s-persistent-v1/model-v1'
    for n in ('iq2s_model_runtime.py','iq2s_config.py'):
        p.require(sha(root/n) == q['files'][str(root/n)], 'Qualified existing lifecycle source')
    sys.path.insert(0,str(root)); import iq2s_model_runtime as base
    p.require(Path(base.__file__) == root/'iq2s_model_runtime.py', 'Lifecycle origin')
    a, old = base.support()
    legacy_path = p.DC/'q8-sharing-v1/model-v1/q8share_model_runtime.py'
    p.require(sha(legacy_path) == q['files'][str(legacy_path)], 'Raw old-close implementation')
    sys.path.insert(0,str(legacy_path.parent)); import q8share_model_runtime as legacy
    p.require(Path(legacy.__file__) == legacy_path, 'Close helper origin')
    return base, a, old, legacy


def cas_library(q):
    path = p.DC/'prose-speed-v1/prose_measure.py'
    p.require(sha(path) == CAS_SHA == q['files'][str(path)], 'Exact qualified cooperative CAS helper')
    sys.path.insert(0,str(path.parent))
    spec = importlib.util.spec_from_file_location('mayas_production_cas',path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def reservation_contract(now, previous, binding):
    if previous is None:
        p.require(now.get('mayas_tp2_activation') is None and not any(now.get(k) for k in PHASES) and
                  now['decode_optimization_current']['selected_identity']['start_binding'] == binding, 'Initial activation reservation race')
    else:
        p.require(now.get('mayas_tp2_activation') == previous and
                  now.get('production_restore_in_progress') == (previous if previous['active'] else False),
                  'Exact previous activation and phase reservation required')
        p.require(not any(now.get(k) for k in PHASES if k not in
                  ('production_restore_in_progress','production_verification_pending','production_temporarily_stopped')),
                  'Foreign active phase preserved')
        pending = str(HERE/'activation-FIRST/state.json') if previous['status'] == 'MAYAS_TP2_RUNNING_PUBLIC_PENDING' else False
        p.require(now.get('production_verification_pending') == pending, 'Foreign public verification reservation preserved')
        p.require(now.get('maintenance_controller') == str(HERE/'activation-FIRST/state.json'), 'Foreign maintenance custody preserved')
        stopped = (previous.get('production_stopped') if previous['status'] == 'HOLD_ACTIVATION_FAILURE_NO_RETRY' else
                   previous['status'] != 'DRAINING_EXACT_SELECTED_OWNER' and not previous.get('start_binding') and
                   not previous.get('verified',{}).get('passed'))
        p.require(now.get('production_temporarily_stopped') is stopped, 'Foreign stopped-owner reservation preserved')
    return True


def state_update(current, previous, value, binding):
    reservation_contract(current,previous,binding)
    now = copy.deepcopy(current)
    now['mayas_tp2_activation'] = copy.deepcopy(value)
    now['maintenance_controller'] = str(HERE/'activation-FIRST/state.json')
    now['production_restore_in_progress'] = copy.deepcopy(value) if value['active'] else False
    if value.get('verified',{}).get('passed'):
        identity = value['verified']['selected_identity']
        now['decode_optimization_current'] = {'status':'MAYAS_TP2_DEFAULT_ACTIVE_VERIFIED','selected_identity':identity,'activation':str(HERE/'activation-FIRST/state.json')}
        now.update(current_native_pid=identity['native_pid'],production_temporarily_stopped=False,production_verification_pending=False)
    elif value['status'] == 'HOLD_ACTIVATION_FAILURE_NO_RETRY':
        if value['production_stopped']:
            now.update(current_native_pid=None,production_temporarily_stopped=True,production_verification_pending=False)
            now['decode_optimization_current'] = dict(now['decode_optimization_current'],status='MAYAS_TP2_ACTIVATION_HOLD_NO_CURRENT_OWNER_CLAIM')
    elif value.get('start_binding'):
        now['current_native_pid'] = value['start_binding']['native_pid']
        now['production_verification_pending'] = str(HERE/'activation-FIRST/state.json')
        now['production_temporarily_stopped'] = False
        now['decode_optimization_current'] = {'status':'MAYAS_TP2_RUNNING_PUBLIC_PENDING','selected_identity':value['selected_identity'],'activation':str(HERE/'activation-FIRST/state.json')}
    elif value['status'] != 'DRAINING_EXACT_SELECTED_OWNER':
        now.update(current_native_pid=None,production_temporarily_stopped=True)
    return now


def production_host(a, legacy, q):
    class MayaProductionHost(legacy.host_class(a), a.ChunkProductionHost):
        def native_snapshot(self, unit):
            rows = self.command(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader']).stdout.splitlines()
            ids = {v.strip() for v in rows if v.strip()}
            if not ids: return None
            p.require(len(ids) == 1 and next(iter(ids)).isdecimal(), 'One actual native GPU owner')
            pid = int(next(iter(ids))); proc = Path('/proc')/str(pid)
            p.require(sha(p.D/'config.json') == q['target_config_sha256'], 'Actual target configuration')
            cfg = read(p.D/'config.json'); env = dict(v.split('=',1) for v in (proc/'environ').read_bytes().decode().split('\0') if '=' in v)
            p.process_contract(cfg,(proc/'cmdline').read_bytes().decode().split('\0'),env,(proc/'cgroup').read_text(),os.path.samefile(proc/'exe',p.D/'bin/maya-ds4'))
            p.require(unit['invocation'] and unit['main_pid'] > 0 and env.get('INVOCATION_ID') == unit['invocation'], 'Unit/native invocation identity')
            ticks = int((proc/'stat').read_text().rsplit(') ',1)[1].split()[19])
            return {'invocation':unit['invocation'],'main_pid':unit['main_pid'],'native_pid':pid,'native_start_ticks':ticks}

        def owned_target_pid(self):
            pid = self.guard_binding()
            p.require(sha(p.D/'bin/maya-ds4') == p.NATIVE_SHA, 'Actual tested native')
            return pid

        def target_identity(self):
            pid = self.owned_target_pid(); ready = read(p.D/'startup-ready.json')
            p.require(sha(p.D/'hosting_preflight.py') == q['target_preflight_sha256'] and
                      sha(p.D/'hosting_ready.py') == q['target_ready_sha256'], 'Actual source-qualified readiness/preflight')
            p.require(ready['health']['max_context'] == 1048576 and ready['health']['images'] is True and
                      ready['max_output_tokens'] == 262144 and ready['cpu_experts'] == ready['ram_experts'] == 6490 and
                      ready['Q8']['passed'] is True and ready['projection']['enabled'] is True, 'Actual capacity/CPU RAM/math readiness')
            release = read(p.D/'release.json')
            p.require(release['id'] == RELEASE and release['files'] == q['target_release_files'], 'Exact selected release graph')
            return {'native_pid':pid,'native_sha256':p.NATIVE_SHA,'config_sha256':q['target_config_sha256'],
                    'context':1048576,'output_default':262144,'images':True,'TP':2,'prefill_chunk':4096,
                    'DSpark':True,'Q8':[1,1],'prompt_skip_mode':1,'runtime_ablation':True,
                    'CPU_experts':6490,'all_CPU_experts_RAM':True,'GPU_trunk_experts':8870,
                    'GPU_slot_basis':'Matched qualified original TP2 startup and current complete all6490 CPU count; TP replicas not double-counted',
                    'start_binding':dict(self.start_binding),'cache_namespace':str(p.CACHE),'model':'Maya-S IQ2_XXS',
                    'served_model_alias':read(p.D/'config.json')['model_name']}
    return MayaProductionHost


def install(q, out):
    for directory in (p.D,p.D/'bin',p.D/'state'):
        p.require(directory.is_dir() and not directory.is_symlink() and directory.resolve() == directory, 'Real production directories')
    p.require(sha(p.D/'config.json') == p.BASE_SHA and sha(p.D/'release.json') == q['base_release_sha256'], 'Original production unchanged')
    p.require(not p.CACHE.exists() and not p.CACHE.is_symlink() and not p.PROFILE.exists(), 'Fresh Maya-S model state')
    for name in ('candidate-config.json','hosting_preflight.py','hosting_ready.py'):
        p.require(sha(HERE/name) == q['files'][str(HERE/name)], 'Prepared target source changed')
    backup = p.D/'releases'/('before-mayas-tp2-'+out.name)
    backup.mkdir(exist_ok=False)
    for name in ('config.json','hosting_preflight.py','hosting_ready.py','release.json','startup-ready.json','startup-preflight.json'):
        source = p.D/name; p.require(not source.is_symlink(), 'No publication alias')
        if source.exists(): shutil.copy2(source,backup/name)
    shutil.copy2(p.D/'bin/maya-ds4',backup/'maya-ds4')
    p.CACHE.mkdir(mode=0o700)
    operations = ((HERE/'candidate-config.json',p.D/'config.json'),(HERE/'hosting_preflight.py',p.D/'hosting_preflight.py'),
                  (HERE/'hosting_ready.py',p.D/'hosting_ready.py'),(p.NATIVE,p.D/'bin/maya-ds4'))
    staged = []
    for source, dest in operations:
        tmp = dest.with_name(dest.name+'.mayas-new'); p.require(not tmp.exists() and not tmp.is_symlink(), 'Publication residue')
        p.require(not dest.is_symlink(), 'No destination alias')
        shutil.copy2(source,tmp)
        expected = p.NATIVE_SHA if dest == p.D/'bin/maya-ds4' else q['files'][str(source)]
        p.require(sha(tmp) == expected, 'Staged exact bytes before publication')
        staged.append((tmp,dest))
    for tmp,dest in staged: os.replace(tmp,dest)
    release = read(HERE/'candidate-release.json')
    p.require(release['files'] == q['target_release_files'], 'Exact release dependencies')
    emit(p.D/'release.json',release)
    return {'backup':str(backup),'release':RELEASE,'native_sha256':p.NATIVE_SHA,'cache':str(p.CACHE)}


def run(pin, admission_pin):
    q = qualified(pin); base,a,old,legacy = support(q)
    cas = cas_library(q)
    before = (p.E/'STATE.json').read_bytes(); state = json.loads(before)
    p.require(not any(state.get(k) for k in PHASES) and base.current_binding(state) == q['selected_binding'], 'Action-time selected owner/phase')
    ad = HERE/'ADMISSION_FIRST.json'; p.require(sha(ad) == admission_pin, 'Exact separate activation admission')
    admission = read(ad)
    p.require(admission['selected_binding'] == q['selected_binding'] and admission['qualification_sha256'] == pin and
              admission['single_use'] is True and admission['user_selected_MayaS_TP2'] is True, 'Explicit user selection admission')
    out = HERE/'activation-FIRST'; out.mkdir(exist_ok=False)
    host = production_host(a,legacy,q)(); host.audit_dir = out; host.baseline_binding = q['selected_binding']
    host.baseline_pid = q['selected_binding']['native_pid']; host.start_binding = None; host.restored_pid = None
    host.old_close_verified = False; host.since = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    reader = host.baseline_reader(); reader.guard_binding(host.baseline_pid); reader.target_identity(); reader.guard_binding(host.baseline_pid)
    host.previous(); p.require(shutil.disk_usage('/').free >= 132*2**30, 'Root132 admission')
    # User explicitly permits interrupting DeepSeek. Other owners/phases remain disallowed.
    record = {'status':'DRAINING_EXACT_SELECTED_OWNER','pid':os.getpid(),'selected_before':q['selected_binding'],
              'qualification_sha256':pin,'admission_sha256':admission_pin,'kernel_since':host.since,'active':True}
    previous = None
    def save(value):
        nonlocal previous
        raw = (p.E/'STATE.json').read_bytes(); now = json.loads(raw)
        updated = state_update(now,previous,value,q['selected_binding'])
        try: cas.cas_state(p.E/'STATE.json',raw,updated)
        except BaseException:
            actual = read(p.E/'STATE.json')
            if actual.get('mayas_tp2_activation') == value and actual.get('production_restore_in_progress') == (value if value['active'] else False):
                previous = copy.deepcopy(value)  # Capture only our exact partially published claim after a readback fault.
            raise
        previous = copy.deepcopy(value); emit(out/'state.json',value)
    old_stop_attempted = False
    router_stop_attempted = False
    try:
        save(record)
        reader.guard_binding(host.baseline_pid); router_stop_attempted = True
        host.stop_router(); reader.guard_binding(host.baseline_pid)
        old_stop_attempted = True
        host.stop_ds(); host.clean_stop(host.baseline_pid); host.free(); host.kernel(host.since)
        record = dict(record,status='PUBLISHING_AFTER_BOUND_OLD_EXIT0'); save(record)
        with host.publication_lock(): installed = install(q,out)
        record = dict(record,status='STARTING_SINGLE_MAYAS_TP2_OWNER',installation=installed); save(record)
        host.restore_ds(); host.restore_router(); verified = host.verify_target(expected_pid=host.restored_pid)
        identity = verified.get('selected_identity') or host.target_identity()
        final = dict(record,status='MAYAS_TP2_DEFAULT_ACTIVE_VERIFIED' if verified.get('passed') else 'MAYAS_TP2_RUNNING_PUBLIC_PENDING',
                     active=False,verified=verified,selected_identity=identity,start_binding=host.start_binding)
        release = read(p.D/'release.json'); release.update(status=final['status'],production_active=bool(verified.get('passed')),activation=str(out/'state.json'))
        emit(p.D/'release.json',release)
        save(final)
        return final
    except BaseException as exc:
        cleanup = None
        try: reservation_contract(read(p.E/'STATE.json'),previous,q['selected_binding'])
        except ValueError as custody:
            exc.add_note('Foreign custody preserved: '+repr(custody))
            emit(out/'foreign-custody-failure.json',{'error':repr(exc),'custody_error':repr(custody),'foreign_state_preserved':True,'no_service_signal_after_custody_change':True})
            raise exc
        if host.start_binding:
            try: host.cleanup_owned_target(expected_pid=host.restored_pid)
            except BaseException as error: cleanup = repr(error)
        elif router_stop_attempted and not old_stop_attempted:
            try: reader.guard_binding(host.baseline_pid); host.restore_router()
            except BaseException as error: cleanup = repr(error)
        unknown_start = record['status'] == 'STARTING_SINGLE_MAYAS_TP2_OWNER' and host.start_binding is None
        if unknown_start: cleanup = 'Attempted startup has no captured native binding; preserve ownership/HOLD'
        if old_stop_attempted and not host.old_close_verified:
            cleanup = (cleanup+'; ' if cleanup else '')+'Old-owner shutdown not verified; preserve active HOLD'
        if record['status'] == 'STARTING_SINGLE_MAYAS_TP2_OWNER':
            try:
                release = read(p.D/'release.json')
                p.require(release['id'] == RELEASE, 'Foreign release preserved on failed activation')
                release.update(status='HOLD_ACTIVATION_FAILURE_NO_RETRY',production_active=False)
                emit(p.D/'release.json',release)
            except BaseException as error: cleanup = (cleanup+'; ' if cleanup else '')+'Release HOLD recording: '+repr(error)
        failure = dict(record,status='HOLD_ACTIVATION_FAILURE_NO_RETRY',active=bool(cleanup),error=repr(exc),cleanup_error=cleanup,
                       production_stopped=old_stop_attempted,owned_cleanup_completed=bool(host.start_binding) and cleanup is None)
        try: save(failure)
        except BaseException as error:
            exc.add_note('Failure-state custody save: '+repr(error)); emit(out/'failure-state-save-error.json',failure)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--qualification',required=True); parser.add_argument('--admission',required=True)
    args = parser.parse_args(); result = run(args.qualification,args.admission)
    print(json.dumps({k:result.get(k) for k in ('status','start_binding','installation')}))
