"""Thin new whole-pack lifecycle over the unchanged owned window and selected4096 owner.

No serving, model, build or service action at import. Each new arm requires an
immutable mode qualification and a separately reviewed action-time admission.
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

import qv_config as config

P = Path(__file__).resolve().parent
E = P.parents[2]
R = Path('/home/alex/strata-deepseek-test-20261024')
D = Path('/home/alex/deepseek-hosted-20261025')
Q = E / 'decode-optimization-20261028/maya-s-comparison-v1'
F = E / 'autonomous-optimization-12h-20261028/chunk4096-v1/activation-v1'
MEMORY_MAX = 80 * 2**30
HOST_MARGIN = 8 * 2**30
PHASE_KEYS = ('active_private_phase', 'active_GPU_phase', 'active_gpu_experiment',
              'private_window', 'active_cpu_build', 'production_restore_in_progress',
              'production_verification_pending', 'production_temporarily_stopped')
PINS = {
    'decode-optimization-20261028/iq2s-persistent-v1/model-v1/iq2s_model_runtime.py': '1516752104307ffc159fbb80afd972ccd43c5cb9a96cf3e47de126f62482d510',
    'decode-optimization-20261028/q8-sharing-v1/model-v1/q8share_model_runtime.py': '9bd594247cecc13980d864780b778a66da08fcaf2b0a3ff5b386e84e33a1ad2c',
    'decode-optimization-20261028/head-batching-v1/head_startup.py': '53988e95be7c1883f7aeeb7ae2b87081da74d64b3f38eb43b6a274d93d1ff4f4',
}
original_model_dir = Q / 'model-v1'
ORIGINAL_PINS = {'ms_config': '8bb87901179135bf01f852b7a4e5c2a57dadd4033199ece802cb624196484176',
 'ms_runtime': 'ea789de73b4a9b8cb3b8887360bc40573efc600544f1c47980ee25deb22860ca',
 'ms_fixtures': '76e3731d48792545b6135f335df60e9d9b4e7266ce23e70a3093a9916b74a869',
 'ms_audit': 'fc36ab4832652ba8b99d151e0162f3e492a04257e356344bf33bff69eedb255b',
 'ms_quality_audit': '9ce588341f83e0aa4a4aa7292d8641a8683a95af96214074f37fe50acf1db737',
 'ms_compat_audit': 'a55f6a71c42a2b6de4d4dcb2207b213fa4b579ab7f2118cb0ef53f0f1311cad6'}
CS1_PINS = {'compatibility-qualification.json': 'a8d5ff19fa187f46adf70b53287b652241a5f4b256a61811643d750cd770c090',
 'compatibility-completion-qualification.json': 'dd2b17daaf5a2d905163972848e08410296f20838bc66cb9c9875fa0065c05f8',
 'CS1/terminal-completion.json': '878b1b96d874a2d324f558ad3463f22fb950acc758594fc394299c0deccfc299',
 'CS1_COMPLETION_ASTRA_RESULT_REVIEW.json': '19774af77d7c6d6f91c0dd5344dd723b70be2a785fe62e133d3f7d995bd1f559',
 'CS1/compatibility-arms-at-terminal.json': '6425be5db6c0429243a093331ffb4d8387b348a99978838b709d5edf4bd5fcbb',
 'CS1/offline-audit-FIRST/attempt.json': '7ec03a30f3de3fcffc547c495f353ae4c5056d3497a266107d722e8d87a11b21',
 'CS1/offline-audit-FIRST/audit-started.json': '9b9b34da4a0c4c28ee8399150c5d93b23dacc21409a94b906efff15a72548a7a',
 'CS1/offline-audit-FIRST/child-observed.json': 'ba13e96b264b2a979c4eb1ef1fed47677592b1eec1884fe9f036dafa2e150a4a',
 'CS1/offline-audit-FIRST/child.log': '18b46bd9df075f9b86ee6c05e1c3b599d04b2cfd70f3c6724084723c72792fd9',
 'CS1/offline-audit-FIRST/dispatch-attempt.json': '0517fea5cacb771c651d9cd4bafa35be66710fc110d5af58984b1963a8273d61',
 'CS1/offline-audit-FIRST/supervision.json': '2dcc98429f4d68d590961e636e0aa7d531c7ded8e75ea4e24c5008fe5180825c'}
PINS.update({str((original_model_dir / (name + '.py')).relative_to(E)): pin for name, pin in ORIGINAL_PINS.items()})


class ResourceAdmissionDeferred(RuntimeError): pass


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(2**20), b''): h.update(b)
    return h.hexdigest()


def emit(path, value):
    path = Path(path)
    require(path.parent.is_dir() and not path.is_symlink(), 'Owned receipt path required')
    tmp = path.with_name(path.name + '.tmp')
    require(not tmp.exists() and not tmp.is_symlink(), 'Preserve receipt temporary residue')
    with tmp.open('x') as f: f.write(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def phase_free(state): return not any(state.get(k) for k in PHASE_KEYS)


def statuses(mode):
    require(mode in config.MODE_ARMS, 'Unknown whole-pack mode')
    prefix = 'MAYA_S_QUALITY_V2'
    return {'running': prefix + '_PRIVATE_RUNNING', 'complete': prefix + '_SELECTED_RESTORED',
            'pending': prefix + '_PUBLIC_VERIFY_PENDING'}


def original_module(name):
    """Verify immutable M1 helpers before importing; never replace a module/global."""
    require(name in ORIGINAL_PINS, 'Unreviewed original module')
    for key, pin in ORIGINAL_PINS.items():
        path = original_model_dir / (key + '.py')
        require(path.is_file() and not path.is_symlink() and path.resolve() == path
                and sha(path) == pin, 'Original M1 helper changed')
        loaded = sys.modules.get(key)
        require(loaded is None or Path(loaded.__file__) == path, 'Foreign original module')
    sys.path.insert(0, str(original_model_dir))
    module = importlib.import_module(name)
    require(Path(module.__file__) == original_model_dir / (name + '.py'), 'Original module origin')
    return module


def audit_modules():
    return {key: original_module(name) for key, name in
            (('fixtures', 'ms_fixtures'), ('saved', 'ms_audit'),
             ('qa', 'ms_quality_audit'), ('original', 'ms_compat_audit'))}


def support():
    for relative, pin in PINS.items(): require(sha(E / relative) == pin, 'Qualified support changed')
    return original_module('ms_runtime').support()


def owned_paths(output, mode, arm, *, present=False):
    config.factor(mode, arm); output = Path(output)
    require(output.parent == E / 'results' and '..' not in output.parts and
            re.fullmatch('maya-s-' + mode + '-v2-' + arm + r'-[0-9]{8}T[0-9]{6}Z', output.name), 'New exact arm namespace required')
    metadata = E / 'maintenance' / output.name
    for root in (E / 'results', E / 'maintenance'):
        require(root.is_dir() and not root.is_symlink(), 'Existing owned parent required')
    require(not output.is_symlink() and not metadata.is_symlink(), 'Owned leaf alias refused')
    require(output.is_dir() if present else not output.exists(), 'Fresh/present output contract')
    return output, metadata


def cpu_group_contract(group, receipt, child, platform):
    require(platform in ('darwin', 'linux'), 'Physical platform required')
    require(receipt.get('passed') is True and receipt.get('controls') == len(group['test_ids'])
            and receipt.get('test_ids') == group['test_ids'] and len(set(group['test_ids'])) == len(group['test_ids'])
            and receipt.get('source_sha256') == group['source_sha256']
            and receipt.get('input_sha256') == group['input_sha256'], 'Exact new CPU proof required')
    require(child.get('returncode') == 0 and type(child['returncode']) is int and child.get('error') is None
            and child.get('cleanup_errors') == [] and child.get('CPU_limit_seconds') == 30
            and child.get('wall_limit_seconds') == 90 and child.get('nice_increment') == 15,
            'CPU supervision incomplete')
    require(receipt.get('CPU_seconds') == [30, 30] and type(receipt.get('nice')) is int
            and 15 <= receipt['nice'] <= 19, 'Observed child CPU controls required')
    wanted = [512 * 2**20] * 2 if platform == 'linux' else None
    require(receipt.get('Linux_AS_bytes') == wanted, 'Observed child AS limit required')
    env = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
           'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    require(receipt.get('environment') == child.get('environment') == env, 'CPU child environment changed')


def cpu_membership(group, files, *, source_base=None):
    source_base = P if source_base is None else Path(source_base)
    require(source_base in (P, P / 'source-FIRST', Q / 'pack-v3'), 'Unapproved CPU source base')
    for name, pin in group['source_sha256'].items():
        require(Path(name).name == name and files.get(str(source_base / name)) == pin,
                'CPU source omitted from immutable qualification')
    for name, pin in group['input_sha256'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
                and files.get(str(E / name)) == pin, 'CPU input omitted from immutable qualification')
    require(set(group['proofs']) == {'darwin', 'linux'}, 'Both physical proofs required')
    for paths in group['proofs'].values():
        require(set(paths) == {'receipt', 'child', 'log'}
                and all(files.get(name) == sha(name) for name in paths.values()),
                'Exact raw CPU receipt/child/log must be pinned')


def qualified(mode, expected):
    require(mode == 'quality', 'Only separately qualified quality-v2')
    path = P / (mode + '-qualification.json')
    require(re.fullmatch('[0-9a-f]{64}', expected or '') and sha(path) == expected, 'Exact mode qualification pin')
    q = json.loads(path.read_text())
    require(q['mode'] == mode and q['root_manual_review'] is True and q['astra_manual_review'] is True
            and q['authorization_sha256'] == 'cb2698ff10b5bd42b029968f20f59aa78d3d6924b4b8a4b5548bc3b28e78ce5a'
            and q['context'] == 1048576 and q['output_allowance'] == 262144, 'Whole-pack mode not qualified')
    for name, pin in q['files'].items():
        path = Path(name)
        require(path.is_absolute() and '..' not in path.parts and not path.is_symlink()
                and re.fullmatch('[0-9a-f]{64}', pin or '') and sha(path) == pin, 'Immutable mode input changed: ' + name)
    for name in ('qv_config.py', 'qv_runtime.py', 'qv_controls.py', 'qv_owner.py', 'qv_audit.py', 'qv_dispatch.py'):
        pin = sha(P / name)
        require(q['files'].get(str(P / name)) == pin
                and any(g['source_sha256'].get(name) == pin for g in q['CPU_groups']),
                'Executing changed source omitted from exact CPU qualification: ' + name)
    require(q['files'].get(str(R / 'window.py')) == '170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f'
            and q['files'].get(str(D / 'config.json')) == config.BASE_SHA
            and q['files'].get(str(D / 'bin/maya-ds4')) == config.BASE_NATIVE,
            'Canonical window and unchanged selected native/config must be explicitly pinned')
    for group in q['CPU_groups']:
        cpu_membership(group, q['files'], source_base=group.get('source_base', P))
        for label, paths in group['proofs'].items():
            cpu_group_contract(group, json.loads(Path(paths['receipt']).read_text()),
                               json.loads(Path(paths['child']).read_text()), label)
    require(q['CPU_groups'] and q['pack_and_resource_prerequisite_reviewed'] is True,
            'Pack/resource prerequisite not reviewed')
    for relative, helper_pin in PINS.items():
        require(q['files'].get(str(E / relative)) == helper_pin, 'Original helper omitted from qualification')
    closed_cs1(q)
    closed_lc1(q)
    pack_custody(q)
    for name, pin in STORAGE_PINS.items():
        require(q['files'].get(str(original_model_dir / name)) == pin
                and sha(original_model_dir / name) == pin, 'Native-only dump bound input omitted or changed')
    encoded_custody(q, mode)
    require(q['private_memory_max'] == MEMORY_MAX and q['host_margin'] == HOST_MARGIN,
            'Frozen compatibility envelope changed')
    require(sha(P / (mode + '-qualification.json')) == expected, 'Qualification changed while checking')
    return q


def pack_custody(q):
    # Exact P3 asset/stat/tokenizer/constructor CPU custody already qualified in M1.
    return original_module('ms_runtime').pack_custody(q)


def closed_cs1(q):
    for relative, pin in CS1_PINS.items():
        path = original_model_dir / relative
        require(q['files'].get(str(path)) == pin and sha(path) == pin,
                'Preserve closed CS1 proof and failed first audit bytes')
    terminal = json.loads((original_model_dir / 'CS1/terminal-completion.json').read_text())
    require(terminal.get('passed') is True and terminal.get('original_audit_regraded') is False
            and terminal.get('model_execution_performed') is False
            and terminal.get('automatic_next_arm') is False, 'Bounded CS1 completion only')
    snapshot = json.loads((original_model_dir / 'CS1/compatibility-arms-at-terminal.json').read_text())['CS1']
    require(snapshot.get('fully_reviewed') is False and snapshot.get('accepted') is False,
            'At-terminal registry evidence must remain historical')
    current_path = original_model_dir / 'compatibility-arms.json'
    require(str(current_path) not in q['files'], 'Do not hash mutable reviewed registry as historical evidence')
    current = json.loads(current_path.read_text())['CS1']
    require(current.get('attempted') is True and current.get('fully_reviewed') is True
            and current.get('accepted') is False and current.get('short_literal_compatibility_passed') is True
            and current.get('quality_or_performance_qualified') is False
            and current.get('original_audit_returncode') == 1 and current.get('original_audit_regraded') is False
            and current.get('no_automatic_next_arm') is True
            and current.get('completion_sha256') == CS1_PINS['CS1/terminal-completion.json']
            and current.get('completion_review_sha256') == CS1_PINS['CS1_COMPLETION_ASTRA_RESULT_REVIEW.json']
            and all(current.get(k) == snapshot[k] for k in ('output', 'proof', 'controller_pid')),
            'CS1 closure is not quality acceptance or automatic quality-v2 permission')
    return True


QUALITY_MANIFEST_PINS = {'A': '3aa80903f946ba4a032aa47fe5f1c6906c531ac259dbfc8f9d9ff482b5ad4f23', 'B': 'c77c34d85a59f4696bb82397a20df97f92235a7ad752d8d3ad80ccfa38377707'}
STORAGE_PINS = {'pack-state-A.json': '5ad3c46fd35167ab51b29b9e4f8af58005b2b3adf65691922e3f3de54885d195', 'pack-state-B.json': 'e17311967e6cbb807281ba3f998c80aeefa9e9a7505c99017fbc92e37b56dcb7'}
QUALITY_CASE_IDS = ('ms-quality-cold-text', 'ms-quality-warm-text', 'ms-quality-two-images', 'ms-quality-return-text')


def encoded_path(which):
    require(which in ('A', 'B'), 'Exact A/B manifest selector')
    return original_model_dir / ('quality-fixtures-' + which + '.json')


def quality_manifest(arm):
    factor = config.factor('quality', arm); which = 'B' if factor['candidate'] else 'A'
    fixtures = original_module('ms_fixtures'); path = encoded_path(which)
    require(sha(path) == QUALITY_MANIFEST_PINS[which], 'Exact existing encoded quality artifact required')
    value = json.loads(path.read_text())
    require(value['mode'] == 'quality' and value['context'] == 1048576
            and value['default_output'] == 262144 and value['policy'] == fixtures.POLICY
            and value['pack_relative_to_E'] == str(Path(factor['pack']).relative_to(config.E)),
            'Exact pack-specific quality policy required')
    fixtures.validate_encoded(value['cases'], 'quality')
    require(tuple(c['id'] for c in value['cases']) == QUALITY_CASE_IDS
            and [c['prompt_tokens'] for c in value['cases']] == [8469, 8469, 8656, 8469]
            and [c['expected_reuse'] for c in value['cases']] == ['zero', 'prompt-minus-one', 'zero', 'prompt-minus-one'],
            'Unchanged four-state work/order required')
    return value


def encoded_custody(q, mode):
    require(mode == 'quality', 'Only the complete quality family')
    for arm in config.MODE_ARMS[mode]:
        quality_manifest(arm)
    # Original helper validates both tokenizers and the source-defined baseline
    # template fallback independently; candidate uses its own published template.
    return original_module('ms_runtime').encoded_custody(q, mode)


def prerequisite(mode, arm, registry):
    config.factor(mode, arm)
    require(type(registry) is dict and arm not in registry, 'Preserve original arm; never replay')
    require(set(registry) <= {'QS0', 'QS1'}, 'Foreign arm in quality-v2 registry')
    if arm == 'QS0':
        require(not registry, 'Baseline must be the first new quality-v2 arm')
    else:
        previous = registry.get('QS0', {})
        require(previous.get('attempted') is True and previous.get('fully_reviewed') is True
                and previous.get('accepted') is True, 'QS0 requires independent accepted review before QS1')


longcold_dir = Q / 'long-cold-v1'
LC1_PINS = {'longcold-qualification.json': 'ca406101a1b47dfb5ad713db67ae44c65318b2169a19a176c3f46f7f5fe395df', 'LC1_ADMISSION_ASTRA.json': 'fde6e6544ca53bfbf901374303196b3b83ad78a86009523a602ef29ad5529403', 'LC1/terminal-audit.json': 'b0ec6af73900a819df73bd3f3fe686f739952f88b3ee8e5c5eaf9c2670a3089e', 'LC1_RESULT_ASTRA_REVIEW.json': 'c1aa384d537cbba1510baafe0604be7d792e20089bcf1a0850bc03f04c7ea052', 'LC1/longcold-arms-at-terminal.json': 'ae38033116d26a7da5d1e9ecc8626a8757ca96a00f22b187c7fa8c0ddf49a34b'}


def closed_lc1(q):
    for relative, pin in LC1_PINS.items():
        path = longcold_dir / relative
        require(q['files'].get(str(path)) == pin and sha(path) == pin,
                'Closed LC1 prerequisite changed or omitted')
    terminal = json.loads((longcold_dir / 'LC1/terminal-audit.json').read_text())
    review = json.loads((longcold_dir / 'LC1_RESULT_ASTRA_REVIEW.json').read_text())
    require(terminal.get('passed') is True and terminal.get('mode') == 'longcold' and terminal.get('arm') == 'LC1'
            and terminal.get('qualification_sha256') == LC1_PINS['longcold-qualification.json']
            and terminal.get('automatic_next_arm') is False and terminal.get('deployment_admitted') is False
            and review.get('decision') == 'LC1_SINGLE_COLD_LONG_JSON_COMPATIBILITY_FULLY_REVIEWED_SELECTED_RESTORATION_REVIEWED'
            and review.get('quality_panel_pass') is False and review.get('performance_acceptance') is False,
            'LC1 is compatibility evidence only, never quality acceptance')
    mutable = longcold_dir / 'longcold-arms.json'
    historical = longcold_dir / 'LC1/longcold-arms-at-terminal.json'
    # The original terminal map is preserved exactly. Only this new prerequisite
    # uses the byte-identical historical snapshot for its mutable registry entry.
    registry_key = str(config.Q / 'long-cold-v1/longcold-arms.json')
    require(terminal['evidence_sha256'].get(registry_key) == LC1_PINS['LC1/longcold-arms-at-terminal.json'],
            'LC1 historical registry hash mismatch')
    for name, pin in terminal['evidence_sha256'].items():
        if name == registry_key: name = str(historical)
        require(q['files'].get(name) == pin, 'Complete LC1 raw closure omitted')
    require(str(mutable) not in q['files'] and str(P / 'quality-arms.json') not in q['files'],
            'Mutable arm registries must not be frozen evidence')
    snapshot = json.loads(historical.read_text())['LC1']
    current = json.loads(mutable.read_text())['LC1']
    require(snapshot.get('fully_reviewed') is False and snapshot.get('accepted') is False
            and current.get('attempted') is True and current.get('fully_reviewed') is True
            and current.get('accepted') is False
            and current.get('terminal_sha256') == LC1_PINS['LC1/terminal-audit.json']
            and current.get('result_review_sha256') == LC1_PINS['LC1_RESULT_ASTRA_REVIEW.json']
            and all(current.get(k) == snapshot[k] for k in ('output', 'proof', 'controller_pid')),
            'Narrow reviewed LC1 closure required; no replay or promotion')
    return True


def memory_available():
    values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    value, unit = values['MemAvailable'].split()
    require(value.isdecimal() and unit == 'kB', 'Typed available physical RAM required')
    return int(value) * 1024


def make_host(a, old, base, legacy, startup):
    # Reuse only raw old-owner close0 observation and one-start restoration from
    # the qualified legacy host. Its old preflight/qualification/launcher are
    # never called. The fixed startup adapter composes over the same exact owner.
    legacy_base = legacy.host_class(a)
    startup_base = startup.guarded_host(a)
    class MayaHost(legacy_base, startup_base):
        def idle(self):
            if self.restored_pid is not None: return super().idle()
            h = self.get('/health'); s = h.get('switcher', {})
            return (h.get('status') == 'ok' and h.get('loaded') is True and h.get('images') is True
                    and h.get('max_context') == 1048576 and s.get('active_model') == s.get('default_model') == 'deepseek'
                    and s.get('fault') is None)

        def preflight(self, output):
            q = qualified(self.mode, self.qualification_sha256)
            current = json.loads((E / 'STATE.json').read_text())
            require(phase_free(current) and base.current_binding(current) == self.baseline_binding, 'Phase/selected owner changed')
            require(self.idle() and shutil.disk_usage('/').free >= 132 * 2**30, 'Selected healthy/root132 required')
            reader = self.baseline_reader(); reader.guard_binding(self.baseline_pid)
            identity = reader.target_identity(); reader.guard_binding(self.baseline_pid)
            prerequisite(self.mode, self.arm, json.loads((P / (self.mode + '-arms.json')).read_text()))
            self.previous(); self.extra_preflight(output)
            return {'qualified_for_owned_maya_s': True, 'mode': self.mode, 'arm': self.arm,
                    'output': str(output), 'qualification_sha256': self.qualification_sha256,
                    'files': q['files'], 'baseline_identity': identity,
                    'explicit_interruption_authorized': True, 'private_memory_max': MEMORY_MAX}

        def free(self):
            super().free()
            if self.private_attempted:
                self.collect_fence()
            else:
                available = memory_available()
                emit(self.audit_dir / 'post-stop-memory.json', {'available_bytes': available,
                     'required_bytes': MEMORY_MAX + HOST_MARGIN, 'passed': available >= MEMORY_MAX + HOST_MARGIN})
                if available < MEMORY_MAX + HOST_MARGIN:
                    raise ResourceAdmissionDeferred('Post-stop physical memory compatibility admission unavailable')

        def collect_fence(self):
            output = self.private_output
            path = Path(output) / 'private-memory-fence.json'
            if path.is_file():
                import qv_controls
                qv_controls.fence_collected(output, self.audit_dir)

        def launch(self, prior, output, proofpath):
            qualified(self.mode, self.qualification_sha256)
            require(Path(proofpath) == self.audit_dir / 'proof.json', 'Exact proof path required')
            self.reserve_attempt(output, proofpath); self.private_attempted = True
            self.private_output = str(output)
            return self.launch_owned(prior, self.phase_argv(output, proofpath), 1200)

    return MayaHost


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
