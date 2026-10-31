"""Shared source-only CPU IQ2_XS comparison lifecycle on the existing selected owner.

No entry point, model call or deadline inherited from the closed12h campaign.
The separate caller owns fixtures, private processes, budgets and attempt ledger.
"""
import copy
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys

import cpu_model_config as config
import cpu_model_controls as controls

P = Path(__file__).resolve().parent
R = Path('/home/alex/strata-deepseek-test-20261024')
E = R / 'reliability-optimization-20261025'
D = Path('/home/alex/deepseek-hosted-20261025')
F = E / 'autonomous-optimization-12h-20261028/chunk4096-v1/activation-v1'
OWNER_SHA = 'b2bb7676969661f98bf77d9969a840a4fcb44367f9644ab6f05ac19d70709056'
WINDOW_SHA = '170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f'
COORDINATE_SHA = '276a78f6f62d9ae7760e9b436863a6279715d58ea0960bb396bdb7adcc3776dd'
FINITE_GATE_SHA = '84a2e35ca3903b811656bda2811edbc318306587d4370621cfecafc088103b3a'
PERFORMANCE_HELPER_SHA = '4acd80c3a842c3c7f02aa5433de9015118b28c592e9822d6bde2b5e62fc71f80'
PHASE_KEYS = ('active_private_phase', 'active_GPU_phase', 'active_gpu_experiment',
              'private_window', 'active_cpu_build', 'production_restore_in_progress',
              'production_verification_pending', 'production_temporarily_stopped')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def real_directory(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Absolute real owned directory required')
    for ancestor in [*reversed(path.parents), path]:
        if ancestor.is_symlink() or not ancestor.is_dir():
            raise ValueError('Non-real owned directory ancestor')


def real_file(path):
    path = Path(path); real_directory(path.parent)
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('Exact real unlinked-alias file required')
    return path


def emit(path, value):
    path = Path(path); real_directory(path.parent)
    if path.exists(): real_file(path)
    if path.is_symlink(): raise ValueError('Receipt symlink refused')
    temporary = path.with_name(path.name + '.tmp')
    if temporary.exists() or temporary.is_symlink(): raise ValueError('Receipt temporary residue refused')
    with temporary.open('x') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def support():
    """Return the exact qualified current4096 owner and canonical coordinate module."""
    owner = F / 'activate_chunk4096.py'
    canonical = E / 'decode-profile-v1/maintenance.py'
    helper = E / 'prefill-cache-improvements-20261027/performance-v1/performance_mode.py'
    if sha(owner) != OWNER_SHA or sha(canonical) != COORDINATE_SHA or sha(helper) != PERFORMANCE_HELPER_SHA:
        raise ValueError('Existing owner/coordinate source changed')
    for name, expected in [('activate_chunk4096', owner), ('maintenance', canonical),
                           ('cpu_model_config', P / 'cpu_model_config.py')]:
        module = sys.modules.get(name)
        if module is not None and Path(module.__file__).resolve() != expected.resolve():
            raise ValueError('Foreign same-name imported module: ' + name)
    sys.path.insert(0, str(F))
    a = importlib.import_module('activate_chunk4096')
    old = a.m.runtime.old
    origins = [(a, owner), (a.m, F.parent / 'chunk4096_performance.py'),
               (a.m.runtime, F.parent / 'chunk4096_runtime.py'), (old, helper)]
    if any(Path(module.__file__).resolve() != expected.resolve() for module, expected in origins):
        raise ValueError('Inherited runtime module origin changed')
    maintenance = sys.modules.get('maintenance')
    if (maintenance is None or old.coordinate is not maintenance.coordinate
        or old.coordinate.__module__ != 'maintenance'
        or Path(old.coordinate.__code__.co_filename).resolve() != canonical.resolve()):
        raise ValueError('Coordinate alias is not the exact existing maintenance body')
    return a, old


def phase_keys_free(state):
    return not any(state.get(key) for key in PHASE_KEYS)


def binding_contract(binding):
    if (type(binding) is not dict or set(binding) != {'invocation', 'main_pid', 'native_pid', 'native_start_ticks'}
        or type(binding['invocation']) is not str or re.fullmatch('[0-9a-f]{32}', binding['invocation']) is None
        or any(type(binding[key]) is not int or binding[key] <= 0 for key in ('main_pid', 'native_pid', 'native_start_ticks'))):
        raise ValueError('Exact typed invocation/PID/starttick binding required')
    return dict(binding)


def current_binding(state=None):
    state = json.loads((E / 'STATE.json').read_text()) if state is None else state
    current = state.get('decode_optimization_current', {}).get('selected_identity')
    if current is None: current = state['chunk4096_activation']['selected_identity']
    return binding_contract(current['start_binding'])


def statuses(mode, arm):
    config.factor(mode, arm)
    prefix = 'CPU_IQ2XS_' + mode.upper()
    return {'running': prefix + '_PRIVATE_RUNNING', 'complete': prefix + '_COMPLETE_SELECTED4096_RESTORED',
            'pending': prefix + '_SELECTED4096_RUNNING_PUBLIC_VERIFY_PENDING'}


def owned_paths(output, mode, arm, *, output_state='absent', metadata_state='present'):
    config.factor(mode, arm); output = Path(output)
    if (output.parent != E / 'results' or '..' in output.parts or
        re.fullmatch('decode-cpu-iq2xs-' + mode + '-' + arm + r'-[0-9]{8}T[0-9]{6}Z', output.name) is None):
        raise ValueError('Exact new mode/arm namespace required')
    for root in (E / 'results', E / 'maintenance'): real_directory(root)
    metadata = E / 'maintenance' / output.name
    for path, policy in ((output, output_state), (metadata, metadata_state)):
        if policy not in ('absent', 'present', 'optional'): raise ValueError('Unknown path policy')
        if path.is_symlink(): raise ValueError('Owned leaf symlink refused')
        exists = path.exists()
        if (policy == 'absent' and exists) or (policy == 'present' and not exists):
            raise ValueError('Existing residue or missing owned directory')
        if exists: real_directory(path)
    return output, metadata


def finite_prerequisite(files):
    path=real_file(P/'finite-prerequisite.json')
    if files.get(str(path))!=FINITE_GATE_SHA or sha(path)!=FINITE_GATE_SHA:
        raise ValueError('Exact completed finite CPU prerequisite missing')
    gate=json.loads(path.read_text())
    if (gate.get('status')!='CPU_IQ2XS_FINITE_PREREQUISITE_COMPLETE_NOT_MODEL_QUALIFICATION'
        or gate.get('candidate_native_sha256')!=config.CANDIDATE_NATIVE
        or gate.get('accepted_jobs')!=46 or gate.get('accepted_case_rows')!=6336
        or gate.get('old_failure_and_partial_regraded') is not False):
        raise ValueError('Wrong candidate or finite CPU coverage')
    if any(files.get(name)!=pin for name,pin in gate['files'].items()):
        raise ValueError('Finite CPU source/raw/review closure omitted')
    report=json.loads(real_file(gate['combined_result']).read_text())
    review=json.loads(real_file(gate['independent_review']).read_text())
    if (sha(gate['combined_result'])!=gate['combined_result_sha256']
        or sha(gate['independent_review'])!=gate['independent_review_sha256']
        or report.get('status')!='COMPOSED_FINITE_SYNTHETIC_CPU_COVERAGE_46_JOBS_6336_CASE_ROWS_PASS'
        or report.get('native_candidate_sha256')!=config.CANDIDATE_NATIVE
        or report.get('combined_disjoint_jobs')!=46 or report.get('combined_finite_case_rows')!=6336
        or report.get('old_v4_job26_regraded') is not False
        or review.get('status')!='COMPOSED_FINITE_SYNTHETIC_46_JOB_6336_ROW_COVERAGE_PASS'):
        raise ValueError('Independent complete finite coverage prerequisite differs')
    return gate


def exact_module(name,path,pin):
    path=Path(path)
    if path.resolve()!=path or not path.is_file() or path.is_symlink() or sha(path)!=pin:
        raise ValueError('Exact pinned module required')
    module=sys.modules.get(name)
    if module is not None and Path(module.__file__).resolve()!=path:
        raise ValueError('Foreign module origin')
    if module is None:
        spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
        sys.modules[name]=module;spec.loader.exec_module(module)
    if Path(module.__file__).resolve()!=path or sha(path)!=pin:raise ValueError('Module changed')
    return module


def cpu_proofs(q):
    path=P/'cpu_driver.py';pin=q['source_sha256']['cpu_driver.py']
    if q['files'].get(str(path))!=pin:raise ValueError('New portable driver absent')
    driver=exact_module('cpu_iq2xs_model_portable_driver',path,pin)
    before=driver.checked(q['source_review_sha256'])
    if before!=(q['source_sha256'],q['input_sha256'],q['test_ids']):raise ValueError('Exact new CPU maps differ')
    if any(q['files'].get(str(P/name))!=pin for name,pin in before[0].items()) or any(q['files'].get(name)!=pin for name,pin in before[1].items()):
        raise ValueError('New CPU source/input membership missing')
    for label in ('darwin','linux'):
        folder=P/('CPU-R2-FIRST-'+label)
        for name in ('attempt.json','observed.json','receipt.json','child.json','child.log','parent.json'):
            if q['files'].get(str(folder/name))!=sha(real_file(folder/name)):raise ValueError('CPU raw membership absent')
        receipt=json.loads((folder/'receipt.json').read_text());child=json.loads((folder/'child.json').read_text())
        observed=json.loads((folder/'observed.json').read_text());attempt=json.loads((folder/'attempt.json').read_text())
        parent=json.loads((folder/'parent.json').read_text());driver.dependency_receipt(receipt.get('dependencies'),label,child['argv']);
        if child['argv'][6]!=q['source_review_sha256'] or child['argv'][8]!=str(attempt['parent_pid']):raise ValueError('Actual isolated CPU child invocation differs')
        driver.bounds(observed,child['pid'],attempt['parent_pid'])
        driver.attempt_contract(attempt,q['source_review_sha256'],observed['ppid'],before)
        if (type(child.get('returncode')) is not int or type(child.get('elapsed_seconds')) not in (int,float)
            or not math.isfinite(child['elapsed_seconds']) or child['elapsed_seconds']<0
            or any(type(receipt.get(k)) is not int for k in ('failures','errors','tests_run','pid'))
            or observed['platform']!=label or child['returncode']!=0 or child['error'] is not None or child['cleanup']!=[]
            or child['elapsed_seconds']>90 or receipt['status']!='PASS' or receipt['pid']!=child['pid']
            or receipt['observed']!=observed or receipt['post_observed']!=observed or receipt['failures']!=0 or receipt['errors']!=0
            or receipt['tests_run']!=len(before[2]) or receipt['test_ids']!=before[2]
            or receipt['source_sha256']!=before[0] or receipt['source_after_sha256']!=before[0]
            or receipt['input_sha256']!=before[1] or receipt['input_after_sha256']!=before[1]
            or receipt['review_sha256']!=q['source_review_sha256']):raise ValueError('Exact both-host CPU receipt differs')
        if parent!={'status':'PASS','pid':child['pid'],'review_sha256':q['source_review_sha256'],
             'receipt_sha256':sha(folder/'receipt.json'),'child_sha256':sha(folder/'child.json'),
             'log_sha256':sha(folder/'child.log')}:raise ValueError('CPU parent chain differs')


def qualified(mode, expected_digest=None):
    if mode not in config.MODES: raise ValueError('Unknown mode')
    qpath = real_file(P / (mode + '-qualification.json'))
    raw = qpath.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    if expected_digest is not None and (type(expected_digest) is not str or digest != expected_digest):
        raise ValueError('Frozen qualification bytes changed')
    q = json.loads(raw)
    if q.get('source_manually_reviewed') is not True or q.get('CPU_both_hosts_passed') is not True or q.get('mode') != mode:
        raise ValueError('Unqualified mode source')
    files, sources, ids = q['files'], q['source_sha256'], q['test_ids']
    if type(files) is not dict or type(sources) is not dict or not sources or type(ids) is not list or not ids:
        raise ValueError('Exact source, evidence and test maps required')
    if any(type(i) is not str for i in ids) or len(set(ids)) != len(ids): raise ValueError('Invalid test ID inventory')
    required = {str(R / 'window.py'): WINDOW_SHA, str(E / 'decode-profile-v1/maintenance.py'): COORDINATE_SHA,
                str(E / 'prefill-cache-improvements-20261027/performance-v1/performance_mode.py'): PERFORMANCE_HELPER_SHA,
                str(F / 'activate_chunk4096.py'): OWNER_SHA, str(D / 'bin/maya-ds4'): config.BASE_NATIVE,
                str(D / 'config.json'): config.BASE_SHA, str(config.CANDIDATE_EXE): config.CANDIDATE_NATIVE}
    if any(files.get(name) != pin for name, pin in required.items()):
        raise ValueError('Canonical owner/window/coordinate or exact binary/config pins missing')
    for name in ('cpu_model_runtime.py','test_cpu_model_runtime.py','cpu_model_'+mode+'.py',
                 'cpu_model_controls.py','cpu_model_numerical_audit.py','cpu_driver.py'):
        if name not in sources:raise ValueError('Required new mode source missing')
    for path in (P/'cpu_model_config.py',P/'cpu_model_dependencies.py',P/'base-config.json',P/'SOURCE_R2_ROOT_REVIEW.json'):
        if str(path) not in files:raise ValueError('New source/manual/dependency input absent')
    for name, pin in sources.items():
        if type(name) is not str or Path(name).name != name or not name.endswith('.py'):
            raise ValueError('New source map requires exact local Python basenames')
        if files.get(str(P / name)) != pin or sha(P / name) != pin: raise ValueError('New mode source changed')
    for name, pin in files.items():
        if type(name) is not str or not Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Immutable evidence path must be absolute and canonical')
        if type(pin) is not str or re.fullmatch('[0-9a-f]{64}', pin) is None or sha(name) != pin:
            raise ValueError('Immutable input changed: ' + name)
    finite_prerequisite(files)
    cpu_proofs(q)
    if sha(qpath) != digest: raise ValueError('Qualification changed during validation')
    return {**q, 'qualification_sha256': digest}


def last_close_row(path):
    with real_file(path).open('rb') as stream:
        stream.seek(0, 2); size = stream.tell(); stream.seek(max(0, size - 65536))
        data = stream.read(65536)
    lines = data.splitlines()
    if not lines or (len(lines) == 1 and size > 65536): raise ValueError('Bounded complete close row missing')
    return json.loads(lines[-1])


def exit_snapshot_fields(raw):
    fields = {}
    for line in raw.splitlines():
        if '=' not in line: raise ValueError('Malformed unit exit metadata')
        key, value = line.split('=', 1)
        if key in fields: raise ValueError('Duplicate unit exit metadata')
        fields[key] = value
    expected = {'InvocationID', 'MainPID', 'ActiveState', 'ExecMainCode', 'ExecMainStatus', 'Result'}
    if set(fields) != expected: raise ValueError('Missing/extra unit exit fields')
    return fields


def close_contract(binding, row, before, after):
    binding_contract(binding)
    if before != after or before != {'InvocationID': binding['invocation'], 'MainPID': '0',
            'ActiveState': 'inactive', 'ExecMainCode': '1', 'ExecMainStatus': '0', 'Result': 'success'}:
        raise ValueError('Old unit exit is not a stable successful bound stop')
    if (type(row.get('native_pid')) is not int or row['native_pid'] != binding['native_pid']
        or type(row.get('server_pid')) is not int or row['server_pid'] != binding['main_pid']
        or type(row.get('returncode')) is not int or row['returncode'] != 0 or row.get('closed') is not True):
        raise ValueError('Bound native close0 row missing')
    return True


class ResourceAdmissionDeferred(RuntimeError): pass


def startup_capture(host,old_invocation):
    path=E/'decode-optimization-20261028/head-batching-v1/head_startup.py'
    helper=exact_module('cpu_iq2xs_selected_startup',path,'53988e95be7c1883f7aeeb7ae2b87081da74d64b3f38eb43b6a274d93d1ff4f4')
    return helper.capture(host,old_invocation,emit=emit)


def host_class(a):
    old = a.m.runtime.old
    class ModelHost(a.ChunkProductionHost):
        private_attempted = False
        old_close_verified = False
        private_output = None

        def capture_pending_start(self,old_invocation):
            return startup_capture(self,old_invocation)

        def free(self):
            super().free()
            if self.private_attempted:
                self.collect_fence()
            else:
                available=controls.memory_available();required=controls.MEMORY_MAX+controls.HOST_MARGIN
                emit(self.audit_dir/'post-stop-memory.json',{'available_bytes':available,'required_bytes':required,
                                                          'passed':available>=required})
                if available<required:raise ResourceAdmissionDeferred('Post-stop physical RAM below88GiB')

        def collect_fence(self):
            if self.private_output is not None:
                output=Path(self.private_output)
                if (output/'private-memory-fence.json').is_file():controls.fence_collected(output,self.audit_dir)

        def baseline_reader(self):
            binding = binding_contract(self.baseline_binding)
            real_directory(self.audit_dir)
            reader = a.ChunkProductionHost()
            reader.start_binding = binding; reader.restored_pid = None; reader.audit_dir = self.audit_dir
            return reader

        def preflight(self, output):
            if not self.idle(): raise old.AdmissionDeferred('Busy; untouched')
            current = json.loads((E / 'STATE.json').read_text())
            if not phase_keys_free(current): raise old.AdmissionDeferred('Another phase/pending/stopped owner; untouched')
            if shutil.disk_usage('/').free < 132 * 2**30: raise old.AdmissionDeferred('Root132 unavailable; untouched')
            owned_paths(output, self.mode, self.arm)
            if current_binding(current) != self.baseline_binding: raise ValueError('Canonical selected owner changed')
            q = qualified(self.mode, self.qualification_sha256)
            reader = self.baseline_reader(); reader.guard_binding(self.baseline_binding['native_pid'])
            identity = reader.target_identity(); reader.guard_binding(self.baseline_binding['native_pid'])
            self.previous()
            if not callable(getattr(self, 'extra_preflight', None)): raise ValueError('Caller-specific admission gate required')
            extra = self.extra_preflight(output)
            if type(extra) is not dict: raise ValueError('Caller preflight receipt required')
            return {'qualified_for_owned_cpu_iq2xs_model': True, 'mode': self.mode, 'arm': self.arm,
                    'output': str(output), 'files': q['files'], 'qualification_sha256': self.qualification_sha256,
                    'baseline_identity': identity, 'mode_preflight': extra}

        def clean_stop(self, pid):
            binding = binding_contract(self.start_binding if self.start_binding is not None else self.baseline_binding)
            if type(pid) is not int or pid != binding['native_pid']: raise ValueError('Foreign close PID')
            name = 'restored-owner-close.json' if self.start_binding is not None else 'old-owner-close.json'
            receipt = {'binding': binding, 'before': None, 'native_close': None, 'after': None, 'passed': False}
            primary = None
            try:
                argv = ['systemctl', '--user', 'show', 'deepseek-hosted.service']
                for field in ('InvocationID', 'MainPID', 'ActiveState', 'ExecMainCode', 'ExecMainStatus', 'Result'):
                    argv += ['-p', field]
                before = self.command(argv, timeout=15).stdout
                receipt['before_raw'] = before; receipt['before'] = exit_snapshot_fields(before)
                receipt['native_close'] = last_close_row(D / 'receipts/native-close.jsonl')
                after = self.command(argv, timeout=15).stdout
                receipt['after_raw'] = after; receipt['after'] = exit_snapshot_fields(after)
                close_contract(binding, receipt['native_close'], receipt['before'], receipt['after'])
                receipt['passed'] = True
                if self.start_binding is None: self.old_close_verified = True
            except BaseException as exc:
                primary = exc; receipt['error'] = repr(exc)
                raise
            finally:
                try: emit(self.audit_dir / name, receipt)
                except BaseException as exc:
                    if primary is None: raise
                    primary.add_note('Owned close receipt failed: ' + repr(exc))

        def restore_ds(self):
            if not self.old_close_verified: raise ValueError('No raw bound old native/API stop proof')
            return super().restore_ds()

        def launch(self, prior, output, proof):
            output, metadata = owned_paths(output, self.mode, self.arm)
            if Path(proof) != metadata / 'proof.json': raise ValueError('Exact mode proof path required')
            data = json.loads(real_file(proof).read_text())
            if data.get('qualification_sha256') != self.qualification_sha256:
                raise ValueError('Phase proof qualification changed')
            qualified(self.mode, self.qualification_sha256)
            if not callable(getattr(self, 'phase_argv', None)) or not callable(getattr(self, 'reserve_attempt', None)):
                raise ValueError('Explicit caller phase and durable attempt callback required')
            argv = self.phase_argv(output, proof)
            expected = [str(R / 'venv/bin/python3.14'), '-B', str(P / ('cpu_model_' + self.mode + '.py')),
                        '--phase', '--arm', self.arm, '--output', str(output), '--proof', str(proof)]
            if argv != expected: raise ValueError('Only the explicit qualified mode caller may enter the window')
            self.private_attempted = True
            self.private_output = str(output)
            self.reserve_attempt(output, proof)
            return self.launch_owned(prior, argv, 1200)

        def verify(self):
            return self.verify_target(expected_pid=self.restored_pid)
    return ModelHost


def load_current_host(a, mode, arm, metadata, qualification_sha256):
    config.factor(mode, arm)
    metadata = Path(metadata)
    output, expected = owned_paths(E / 'results' / metadata.name, mode, arm)
    if metadata != expected: raise ValueError('Foreign metadata directory')
    if type(qualification_sha256) is not str or re.fullmatch('[0-9a-f]{64}', qualification_sha256) is None:
        raise ValueError('Exact qualification digest required')
    host = host_class(a)()
    host.mode, host.arm, host.audit_dir = mode, arm, metadata
    host.qualification_sha256 = qualification_sha256
    host.baseline_binding = current_binding(); host.baseline_pid = host.baseline_binding['native_pid']
    host.start_binding = None; host.restored_pid = None; host.private_attempted = False; host.old_close_verified = False
    host.private_output = None
    host.controller_pid = os.getpid()
    return host


class PendingCustodyChanged(ValueError): pass


def normalize_pending(value, mode, arm):
    pending = statuses(mode, arm)['pending']
    if value.get('verified', {}).get('pending_public_probe') and value['status'] != pending:
        value['resume_terminal_status'] = value['status']; value['status'] = pending
    return value


def make_saver(host, metadata, mode, arm, run):
    status = statuses(mode, arm); metadata = Path(metadata)
    if type(run) is not bool: raise ValueError('Explicit run boolean required')
    _, expected = owned_paths(E / 'results' / metadata.name, mode, arm, output_state='optional')
    if metadata != expected or metadata != host.audit_dir: raise ValueError('Wrong owned saver directory')
    def save(value):
        normalize_pending(value, mode, arm)
        if value.get('mode', mode) != mode or value.get('arm', arm) != arm:
            raise ValueError('Foreign mode/arm result')
        if value.get('qualification_sha256') != host.qualification_sha256:
            raise ValueError('Result qualification changed')
        if value.get('output') != str(E / 'results' / metadata.name): raise ValueError('Foreign output receipt')
        value.update(mode=mode, arm=arm, controller_pid=host.controller_pid,
                     start_binding=copy.deepcopy(getattr(host, 'start_binding', None)), kernel_since=host.since,
                     start_command_cleanup_error=getattr(host, 'start_command_cleanup_error', None))
        # Initial read-only/busy results have no global reservation to release.
        if not run or value['status'] in ('PREFLIGHT_OK', 'DEFERRED_NO_PRODUCTION_MUTATION',
                                         'DEFERRED_BUSY_OR_MANUAL_MODEL_NO_MUTATION'):
            emit(metadata / 'state.json', value); return
        current = json.loads((E / 'STATE.json').read_text())
        if value['status'] == 'DRAINING_ROUTER':
            if not phase_keys_free(current) or current_binding(current) != host.baseline_binding:
                raise ValueError('Admission changed before owned drain; untouched')
        elif (current.get('maintenance_controller') != str(metadata / 'state.json') or
              current.get('decode_optimization_current', {}).get('controller_pid') != host.controller_pid):
            # Local failure evidence is allowed; never claim or overwrite a foreign controller.
            emit(metadata / 'custody-refused.json', value)
            if value['status'] == 'STOPPED_FOR_OFFLINE_DIAGNOSIS': return
            raise PendingCustodyChanged('Foreign controller replacement preserved')
        before = copy.deepcopy(current)
        previous = current.get('decode_optimization_current', {}).get('selected_identity')
        if previous is None: previous = current.get('chunk4096_activation', {}).get('selected_identity')
        verification = value.get('verified', {})
        if verification.get('selected_identity') is not None: value['selected_identity'] = verification['selected_identity']
        elif previous is not None: value['selected_identity'] = previous
        active = value['status'] in ('DRAINING_ROUTER', status['running'], 'CLEAN_PHASE_RESTORING_SELECTED_DS',
                                    'DEFERRED_BEFORE_PRIVATE_WINDOW_RESTORING_SELECTED_DS')
        current.update(decode_optimization_current=value, maintenance_controller=str(metadata / 'state.json'),
                       active_gpu_experiment=active, active_private_phase=str(metadata) if active else None,
                       production_temporarily_stopped=active or value['status'] == 'STOPPED_FOR_OFFLINE_DIAGNOSIS')
        if verification.get('pending_public_probe'):
            current['production_verification_pending'] = str(metadata / 'state.json')
        elif verification.get('passed') is True:
            current['production_verification_pending'] = False
            current['current_native_pid'] = verification['selected_identity']['native_pid']
        emit(metadata / 'state.json', value)
        if json.loads((E / 'STATE.json').read_text()) != before:
            raise PendingCustodyChanged('Canonical custody changed before commit')
        emit(E / 'STATE.json', current)
    return save


def coordinate_mode(a, host, output, state, save, *, preflight_only=False, root_free=None):
    mode_status = statuses(host.mode, host.arm)
    if (state.get('running_status') != mode_status['running'] or state.get('complete_status') != mode_status['complete']
        or state.get('qualification_sha256') != host.qualification_sha256
        or state.get('proof_path') != str(host.audit_dir / 'proof.json')):
        raise ValueError('Exact mode/controller state required')
    if root_free is not None and not callable(root_free): raise ValueError('Explicit root sampler callable required')
    if host.restored_pid is not None or host.start_binding is not None or host.private_attempted:
        raise ValueError('A used/startup-bound host cannot enter another private phase')
    def tracked(value):
        normalize_pending(value, host.mode, host.arm)
        active_error = sys.exc_info()[1]
        try: save(value)
        except BaseException as receipt_error:
            if value['status'] != 'STOPPED_FOR_OFFLINE_DIAGNOSIS' or active_error is None: raise
            active_error.add_note('Canonical HOLD save failed: ' + repr(receipt_error))
    try:
        return a.m.runtime.old.coordinate(host, output, state, tracked, preflight_only=preflight_only,
            post_drain_root_free_bytes=root_free or (lambda: shutil.disk_usage('/').free))
    except ResourceAdmissionDeferred:
        raise
    except BaseException as primary:
        hold_owned(host,state,save,primary)
        raise


def hold_owned(host,state,save,primary):
    cleanup = None
    ours = False
    try:
        current = json.loads((E / 'STATE.json').read_text())
        ours = (current.get('maintenance_controller') == str(host.audit_dir / 'state.json') and
                current.get('decode_optimization_current', {}).get('controller_pid') == host.controller_pid)
    except BaseException as custody_error:
        primary.add_note('Cannot establish cleanup custody: ' + repr(custody_error))
    if ours and type(host.restored_pid) is int and host.restored_pid > 0:
        try: host.cleanup_owned_target(host.restored_pid)
        except BaseException as exc: cleanup = repr(exc)
    if ours and host.private_attempted:
        try:host.free()
        except BaseException as exc:primary.add_note('Owned private collection: '+repr(exc))
    hold = dict(state, status='STOPPED_FOR_OFFLINE_DIAGNOSIS', error=repr(primary), cleanup_error=cleanup,
                start_binding=getattr(host, 'start_binding', None),
                start_command_cleanup_error=getattr(host, 'start_command_cleanup_error', None))
    try: save(hold)
    except BaseException as receipt_error: primary.add_note('Mode HOLD save failed: ' + repr(receipt_error))


def pid_alive(pid):
    if type(pid) is not int or pid <= 0: raise ValueError('Typed original controller PID required')
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    except PermissionError: return True
    return True


def verify_pending(a, metadata, mode, arm):
    metadata = Path(metadata)
    _, expected = owned_paths(E / 'results' / metadata.name, mode, arm,
                              output_state='optional', metadata_state='present')
    if metadata != expected: raise ValueError('Foreign pending directory')
    state_path = real_file(metadata / 'state.json'); value = json.loads(state_path.read_text())
    current = json.loads((E / 'STATE.json').read_text())
    if (value.get('status') != statuses(mode, arm)['pending'] or value.get('mode') != mode or value.get('arm') != arm
        or current.get('production_verification_pending') != str(state_path)
        or current.get('maintenance_controller') != str(state_path)
        or current.get('decode_optimization_current', {}).get('controller_pid') != value.get('controller_pid')):
        raise ValueError('No exact pending continuation')
    if (value.get('output') != str(E / 'results' / metadata.name)
        or value.get('proof_path') != str(metadata / 'proof.json')
        or value.get('resume_terminal_status') not in (statuses(mode, arm)['complete'],
                                                       'DEFERRED_PRIVATE_ADMISSION_SELECTED_DS_RESTORED','RESOURCE_DEFERRED_SELECTED_RESTORED')):
        raise ValueError('Foreign pending output/proof/completion state')
    if any(current.get(k) for k in PHASE_KEYS if k != 'production_verification_pending'):
        raise ValueError('Another phase or stopped state; untouched')
    if pid_alive(value['controller_pid']): raise ValueError('Original controller still alive; no concurrent verification')
    host = host_class(a)(); host.start_binding = binding_contract(value['start_binding'])
    host.restored_pid = host.start_binding['native_pid']; host.audit_dir = metadata; host.since = value['kernel_since']
    host.guard_binding(host.restored_pid)
    if not host.idle(): return {'status': 'DEFERRED_BUSY_UNTOUCHED'}
    qualified(mode, value['qualification_sha256'])
    updated = None
    try:
        proof = host.verify_target(expected_pid=host.restored_pid)
        if proof.get('pending_public_probe'): return {'status': 'DEFERRED_BUSY_UNTOUCHED'}
        if proof.get('passed') is not True: raise ValueError('Pending selected verification failed')
        if json.loads((E / 'STATE.json').read_text()) != current or json.loads(state_path.read_text()) != value:
            raise PendingCustodyChanged('Pending custody changed during verification')
        value.update(status=value['resume_terminal_status'], verified=proof, selected_identity=proof['selected_identity'])
        emit(state_path, value)
        updated = dict(current, decode_optimization_current=value, production_verification_pending=False,
                       current_native_pid=proof['selected_identity']['native_pid'])
        if json.loads((E / 'STATE.json').read_text()) != current:
            raise PendingCustodyChanged('Pending custody changed before commit')
        emit(E / 'STATE.json', updated); emit(metadata / 'result.json', value)
        return value
    except BaseException as primary:
        cleanup = None
        live = None
        try: live = json.loads((E / 'STATE.json').read_text())
        except BaseException as custody_error:
            primary.add_note('Cannot establish pending cleanup custody: ' + repr(custody_error))
        unchanged = live is not None and (live == current or (updated is not None and live == updated))
        if unchanged and not isinstance(primary, PendingCustodyChanged):
            try: host.cleanup_owned_target(host.restored_pid)
            except BaseException as exc: cleanup = repr(exc)
        hold = dict(value, status='STOPPED_FOR_OFFLINE_DIAGNOSIS', error=repr(primary), cleanup_error=cleanup,
                    start_command_cleanup_error=getattr(host, 'start_command_cleanup_error', None))
        try:
            emit(metadata / 'pending-failure.json', hold)
            if unchanged:
                emit(state_path, hold); held = dict(live, decode_optimization_current=hold, production_temporarily_stopped=True)
                if json.loads((E / 'STATE.json').read_text()) != live:
                    raise PendingCustodyChanged('Pending custody changed during failure cleanup')
                emit(E / 'STATE.json', held)
        except BaseException as receipt_error: primary.add_note('Pending HOLD receipt failed: ' + repr(receipt_error))
        raise
