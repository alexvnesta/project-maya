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

import ms_config as config

P = Path(__file__).resolve().parent
E = P.parents[2]
R = Path('/home/alex/strata-deepseek-test-20261024')
D = Path('/home/alex/deepseek-hosted-20261025')
Q = E / 'decode-optimization-20261028/maya-s-comparison-v1'
F = E / 'autonomous-optimization-12h-20261028/chunk4096-v1/activation-v1'
MEMORY_MAX = 76 * 2**30
HOST_MARGIN = 8 * 2**30
PHASE_KEYS = ('active_private_phase', 'active_GPU_phase', 'active_gpu_experiment',
              'private_window', 'active_cpu_build', 'production_restore_in_progress',
              'production_verification_pending', 'production_temporarily_stopped')
PINS = {
    'decode-optimization-20261028/iq2s-persistent-v1/model-v1/iq2s_model_runtime.py': '1516752104307ffc159fbb80afd972ccd43c5cb9a96cf3e47de126f62482d510',
    'decode-optimization-20261028/q8-sharing-v1/model-v1/q8share_model_runtime.py': '9bd594247cecc13980d864780b778a66da08fcaf2b0a3ff5b386e84e33a1ad2c',
    'decode-optimization-20261028/head-batching-v1/head_startup.py': '53988e95be7c1883f7aeeb7ae2b87081da74d64b3f38eb43b6a274d93d1ff4f4',
}
PACK_CUSTODY_FILES = {
    'constructor_qualification': ('pack-v3/construct-qualification-FIRST.json', '9ac9ff14bb0e9ae77ac3caa38ef75ed5e5dc5d39afceee1de77430af8490d692'),
    'constructor_contract': ('pack-v3/construct-contract-FIRST.json', 'b7a25b3db67e30af7ed1ef4b3746093b5b476e3fc144eb47648c575ce8eda02e'),
    'constructor_result': ('pack-v3/construct-CPU-FIRST/pack-result.json', '9d42caa2d48361b4c176df2453e5bf1d97f405deb1080f0242db23769164ae9e'),
    'constructor_child': ('pack-v3/construct-CPU-FIRST/child.json', '315442dbf5280bbefb13bd77cff6756224fce5ae650e5cb331c2e5443af1eb35'),
    'constructor_log': ('pack-v3/construct-CPU-FIRST/child.log', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    'constructor_result_review': ('pack-v3/CONSTRUCT_RESULT_ASTRA_REVIEW.json', 'ea4744a195c06f620621e4f387e85b9d950919cb7d32a653c91c201659d558a8'),
    'acquisition_receipt': ('acquisition-authorized-v2/acquisition-attempt-20261030T141645810845Z-3166208.json', '829dc2974aefd88d1c0adb65a799dc1b35bc1076eb21e4e5119e761b61cfa577'),
}
PACK_OUTPUTS = {'ds4.txt', 'tensors.txt', 'engram.bin', 'tokenizer/vocab.json',
                'tokenizer/merges.txt', 'tokenizer/token_type.json',
                'tokenizer/tokenizer.json', 'tokenizer/chat_template.jinja'}


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
    prefix = 'MAYA_S_' + mode.upper()
    return {'running': prefix + '_PRIVATE_RUNNING', 'complete': prefix + '_SELECTED_RESTORED',
            'pending': prefix + '_PUBLIC_VERIFY_PENDING'}


def support():
    for relative, pin in PINS.items(): require(sha(E / relative) == pin, 'Qualified support changed')
    paths = [('iq2s_model_runtime', E / next(k for k in PINS if k.endswith('/iq2s_model_runtime.py'))),
             ('q8share_model_runtime', E / next(k for k in PINS if k.endswith('/q8share_model_runtime.py'))),
             ('head_startup', E / next(k for k in PINS if k.endswith('/head_startup.py')))]
    modules = []
    for name, path in paths:
        loaded = sys.modules.get(name)
        require(loaded is None or Path(loaded.__file__) == path, 'Foreign helper module')
        sys.path.insert(0, str(path.parent)); module = importlib.import_module(name)
        require(Path(module.__file__) == path, 'Helper origin mismatch'); modules.append(module)
    base, legacy, startup = modules
    a, old = base.support()
    return a, old, base, legacy, startup


def owned_paths(output, mode, arm, *, present=False):
    config.factor(mode, arm); output = Path(output)
    require(output.parent == E / 'results' and '..' not in output.parts and
            re.fullmatch('maya-s-' + mode + '-' + arm + r'-[0-9]{8}T[0-9]{6}Z', output.name), 'New exact arm namespace required')
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
    require(source_base in (P, Q / 'pack-v3'), 'Unapproved CPU source base')
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
    entry = {'quality': 'ms_quality.py', 'compatibility': 'ms_compat.py'}.get(mode, 'ms_mode.py')
    for name in ('ms_config.py', 'ms_fixtures.py', 'ms_runtime.py', 'ms_controls.py', 'ms_audit.py',
                 'ms_quality_audit.py', 'ms_audit_dispatch.py', entry):
        pin = sha(P / name)
        require(q['files'].get(str(P / name)) == pin
                and any(g['source_sha256'].get(name) == pin for g in q['CPU_groups']),
                'Executing changed source omitted from exact CPU qualification: ' + name)
    require(q['files'].get(str(R / 'window.py')) == '170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f'
            and q['files'].get(str(D / 'config.json')) == config.BASE_SHA
            and q['files'].get(str(D / 'bin/maya-ds4')) == config.BASE_NATIVE,
            'Canonical window and unchanged selected native/config must be explicitly pinned')
    for group in q['CPU_groups']:
        cpu_membership(group, q['files'])
        for label, paths in group['proofs'].items():
            cpu_group_contract(group, json.loads(Path(paths['receipt']).read_text()),
                               json.loads(Path(paths['child']).read_text()), label)
    require(q['CPU_groups'] and q['pack_and_resource_prerequisite_reviewed'] is True,
            'Pack/resource prerequisite not reviewed')
    pack_custody(q)
    encoded_custody(q, mode)
    require(q['private_memory_max'] == MEMORY_MAX and q['host_margin'] == HOST_MARGIN,
            'Frozen compatibility envelope changed')
    require(sha(P / (mode + '-qualification.json')) == expected, 'Qualification changed while checking')
    return q


def pack_file(path):
    """Exact evidence-root paths, including ancestors, must not be aliases."""
    path = Path(path)
    require(path.is_absolute() and path.is_relative_to(E) and '..' not in path.parts
            and not E.is_symlink(), 'Foreign pack evidence path')
    current = E
    for part in path.relative_to(E).parts:
        current = current / part
        require(not current.is_symlink(), 'Pack evidence ancestor/leaf alias')
    require(path.is_file(), 'Pack evidence file missing')
    return path


def pack_custody(q):
    """Bind successful P3 metadata, leaving the two failed constructors intact.

    Only small metadata is hashed here. Acquisition already hashed tensor assets;
    their exact stat identities are retained rather than rehashed in a phase.
    """
    evidence = q['pack_custody']
    require(set(evidence) == set(PACK_CUSTODY_FILES), 'Exact P3 custody fields required')
    rows = {}
    for name, (relative, pin) in PACK_CUSTODY_FILES.items():
        require(evidence[name] == str(Q / relative), 'Successful P3 evidence path changed')
        path = pack_file(evidence[name])
        require(q['files'].get(str(path)) == pin == sha(path), 'Exact P3 evidence omitted/changed')
        if name != 'constructor_log': rows[name] = json.loads(path.read_text())
    cq = rows['constructor_qualification']; base = Q / 'pack-v3'
    require(cq['root_manual_review'] is True and cq['astra_manual_review'] is True
            and cq['pack_guard_both_physical_hosts_passed'] is True
            and cq['construct_controller_both_physical_hosts_passed'] is True
            and cq['actual_contract'] == evidence['constructor_contract']
            and cq['actual_contract_sha256'] == PACK_CUSTODY_FILES['constructor_contract'][1]
            and cq['pack_output_is_original_never_created_fresh_target'] == str(Q / 'pack-v1/pack-FIRST'),
            'Exact completed P3 qualification/contract/target required')
    require(cq['files'] and all(q['files'].get(name) == pin for name, pin in cq['files'].items()),
            'Constructor source/input/proof closure missing from model qualification')
    groups = cq['CPU_groups']
    require(len(groups) == 2 and {g['name'] for g in groups} == {'pack_guard', 'construct_controller'},
            'Both original P3 CPU groups required')
    for group in groups:
        count, prefix = (94, 'CPU-FIRST') if group['name'] == 'pack_guard' else (31, 'CONSTRUCT-FIRST')
        require(len(group['test_ids']) == count and group['test_ids'] == sorted(group['test_ids']),
                'Exact ordered P3 CPU control inventory required')
        require(set(group['proofs']) == {'darwin', 'linux'}, 'Both physical P3 proofs required')
        for platform, paths in group['proofs'].items():
            for key, leaf in (('receipt', 'receipt.json'), ('child', 'child.json'), ('log', 'child.log')):
                require(paths[key] == str(base / (prefix + '-' + platform) / leaf), 'P3 raw proof path changed')
                pack_file(paths[key])
        cpu_membership(group, cq['files'], source_base=base)
        for platform, paths in group['proofs'].items():
            cpu_group_contract(group, json.loads(Path(paths['receipt']).read_text()),
                               json.loads(Path(paths['child']).read_text()), platform)
    child = rows['constructor_child']
    expected_command = [str(R / 'venv/bin/python3.14'), '-B', str(base / 'construct_pack.py'), '--child',
        '--qualification', evidence['constructor_qualification'], '--qualification-sha256',
        PACK_CUSTODY_FILES['constructor_qualification'][1], '--contract', evidence['constructor_contract'],
        '--output', str(base / 'construct-CPU-FIRST')]
    require(child['command'] == expected_command and type(child['returncode']) is int and child['returncode'] == 0
            and child['error'] is None and child['cleanup_errors'] == []
            and type(child['pid']) is int and child['pid'] > 0
            and type(child['seconds']) in (int, float) and 0 <= child['seconds'] <= 90
            and child['CPU_limit_seconds'] == 30 and child['Linux_AS_bytes'] == 512 * 2**20
            and child['wall_limit_seconds'] == 90 and child['nice_increment'] == 15
            and child['environment'] == {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1',
                'OPENBLAS_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
            and type(child['GPU_or_service_actions']) is int and child['GPU_or_service_actions'] == 0,
            'Actual P3 constructor child failed or differs from admitted metadata command')
    review = rows['constructor_result_review']
    require(review['passed'] is True and review['model_or_GPU_admitted'] is False
            and review['qualification_sha256'] == PACK_CUSTODY_FILES['constructor_qualification'][1],
            'Independent actual P3 result review missing')
    contract, result, acquired = (rows[k] for k in ('constructor_contract', 'constructor_result', 'acquisition_receipt'))
    require(contract['output'] == str(Q / 'pack-v1/pack-FIRST') and contract['assets_root'] == str(Q / 'assets')
            and contract['vision_dir'] == str(E / 'vision-assets-1017')
            and contract['acquisition_receipt'] == evidence['acquisition_receipt']
            and contract['acquisition_receipt_sha256'] == q['files'][evidence['acquisition_receipt']]
            and acquired.get('status') == 'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN'
            and type(acquired.get('returncode')) is int and acquired['returncode'] == 0
            and result['status'] == 'PACK_METADATA_VERIFIED_NO_MODEL_ADMISSION'
            and type(acquired.get('model_or_service_actions')) is int and acquired['model_or_service_actions'] == 0
            and result['asset_stats'] == contract['asset_stats'] and result['vision_stats'] == contract['vision_stats']
            and result['capacity_inputs']['limits_preserved'] == contract['profile']
            and set(result['output_sha256']) == PACK_OUTPUTS,
            'Completed acquisition/pack construction custody differs')
    assets = Q / 'assets'; seen = set()
    require(len(acquired['files']) == 8, 'Exact eight acquisition rows required')
    for row in acquired['files']:
        relative = Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts
                and row['status'] in ('DOWNLOADED_VERIFIED', 'VERIFIED_EXISTING'), 'Acquisition path/status changed')
        path = pack_file(assets / relative); seen.add(str(path))
        st = path.stat(); actual = [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]
        require(st.st_nlink == 1 and contract['asset_stats'].get(str(path)) == actual
                and row['bytes'] == st.st_size and result['asset_sha256'].get(row['path']) == row['sha256'],
                'Acquired asset identity changed; no inherited payload hash claim')
    require(len(seen) == 8 and seen == set(contract['asset_stats'])
            and set(result['asset_sha256']) == {row['path'] for row in acquired['files']},
            'Exact eight asset identities required')
    for relative, digest in result['output_sha256'].items():
        path = pack_file(Q / 'pack-v1/pack-FIRST' / relative)
        require('..' not in Path(relative).parts and not Path(relative).is_absolute()
                and q['files'].get(str(path)) == digest == sha(path), 'Constructed metadata omitted/changed')
    require(set(contract['vision_stats']) == {str(E / 'vision-assets-1017' / n) for n in ('vision.json', 'vision.bin')},
            'Both selected vision identities required')
    for name, original in contract['vision_stats'].items():
        path = pack_file(name)
        require(path.parent == E / 'vision-assets-1017' and path.name in ('vision.json', 'vision.bin')
                and not path.is_symlink(), 'Exact selected vision asset required')
        st = path.stat()
        require(st.st_nlink == 1 and original == [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns],
                'Selected vision stat custody changed')
    return result


COMPAT_SOURCE_SHA = 'd572147c2f668b7702531ec62a90b5ba9fe8e0b47ac864f05ecca8c73402c601'
COMPAT_CASE_ID = 'ms-compatibility-short-cold'


def compatibility_manifest():
    """Derive only the already encoded candidate 44-token literal; never encode/resize."""
    import ms_fixtures as fixtures
    path = P / 'prose-fixtures-B.json'
    require(sha(path) == COMPAT_SOURCE_SHA, 'Exact previously encoded candidate artifact required')
    source = json.loads(path.read_text())
    require(source['mode'] == 'prose' and source['context'] == 1048576
            and source['default_output'] == 262144 and source['policy'] == fixtures.POLICY
            and source['pack_relative_to_E'] == str(config.CANDIDATE_PACK.relative_to(config.E)),
            'Candidate whole-pack encoding and unchanged full policy required')
    fixtures.validate_encoded(source['lifecycle_cases'], 'lifecycle')
    rows = [c for c in source['lifecycle_cases'] if c['id'] == 'ms-prose-prefill-recovery']
    require(len(rows) == 1, 'One exact prior encoded literal source required')
    case = copy.deepcopy(rows[0])
    require(case['prompt_tokens'] == 44 and case['kind'] == 'literal'
            and case['expected'] == 'RECOVERED_Q8_LITERAL' and case['image_spans'] == []
            and case['request_sha256'] == 'da06aa190c3a42a5abe68d10e6c86a233ce09a3b8a7e000282031c08dec8375e'
            and case['prompt_ids_sha256'] == '0f51ef0261a3e5cb81f4434bfe4a056af8f1e6d040fbe186370c553ba24beff7',
            'Frozen short request/actual candidate IDs changed')
    case.pop('dependency'); case.update(id=COMPAT_CASE_ID, expected_reuse='zero')
    keep = ('context', 'default_output', 'policy', 'pack_relative_to_E', 'tokenizer_source_sha256',
            'effective_template', 'API_sha256', 'CPU_only', 'native_model_executed')
    result = {k: copy.deepcopy(source[k]) for k in keep}
    result.update(id='maya-s-short-cold-compatibility-v1', mode='compatibility', cases=[case],
                  source_manifest='prose-fixtures-B.json', source_manifest_sha256=COMPAT_SOURCE_SHA,
                  source_case_id='ms-prose-prefill-recovery', derived_without_reencoding=True,
                  quality_or_performance_pass=False, automatic_next_arm=False)
    return result


def encoded_custody(q, mode):
    import ms_fixtures as fixtures
    if mode == 'compatibility':
        compatibility_manifest()  # derive one already encoded request; no tokenizer execution
        manifests = [('prose', 'B', 'CS1')]
    else:
        manifests = [(mode, 'A', config.MODE_ARMS[mode][0]), (mode, 'B', config.MODE_ARMS[mode][1])]
    for source_mode, which, arm in manifests:
        path = P / (source_mode + '-fixtures-' + which + '.json')
        require(q['files'].get(str(path)) == sha(path), 'Exact encoded pack-specific manifest required')
        manifest = json.loads(path.read_text()); directory = fixtures.tokenizer_directory(config.factor(mode, arm)['pack'])
        pins = manifest['tokenizer_source_sha256']; template = manifest['effective_template']
        require(set(pins) == set(fixtures.TOKENIZER_NAMES), 'Exact encoded tokenizer file inventory required')
        for name, pin in pins.items():
            require(q['files'].get(str(directory / name)) == pin, 'Tokenizer source omitted from qualification')
        pack_template = directory / 'chat_template.jinja'
        expected = fixtures.E / fixtures.FALLBACK_TEMPLATE if template['pack_template_replaced'] else pack_template
        require(type(template['pack_template_replaced']) is bool
                and template['effective_template_relative_to_E'] == str(expected.relative_to(fixtures.E))
                and q['files'].get(str(expected)) == template['effective_template_sha256'],
                'Effective API template omitted from qualification')


def prerequisite(mode, arm, registry):
    config.factor(mode, arm); require(arm not in registry, 'Preserve original arm; never replay')
    order = config.MODE_ARMS[mode]; index = order.index(arm)
    if index:
        previous = registry.get(order[index - 1], {})
        require(previous.get('fully_reviewed') is True and previous.get('accepted') is True,
                'Previous arm must pass independent review; failed outcomes block advancement')
    if mode not in ('quality', 'compatibility'):
        quality = json.loads((P / 'quality-arms.json').read_text())
        require(all(quality.get(a, {}).get('fully_reviewed') is True and quality[a].get('accepted') is True
                    for a in config.MODE_ARMS['quality']), 'Both quality/resource screens must pass')
        if arm in ('B2', 'A2'):
            require(json.loads((P / ('first-pair-' + mode + '.json')).read_text()).get('confirmation_admitted') is True,
                    'Matched first pair must admit reversed confirmation')


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
                import ms_controls
                ms_controls.fence_collected(output, self.audit_dir)

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
