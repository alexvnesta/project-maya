"""Offline four-state evidence audit, only after selected production restoration.

Variable native batch rows are scanned in full, never mapped to emitted tokens.
This module admits no model action, comparison, retry, or deployment.
"""
import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import stat
import sys

import qv_config as config
import qv_runtime as runtime
saved = runtime.original_module('ms_audit')
fixtures = runtime.original_module('ms_fixtures')

require = saved.require
read = saved.read


def exact(a, b):
    return fixtures.packed(a) == fixtures.packed(b)


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'Absolute owned evidence required')
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'Evidence path alias refused')
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'One regular evidence file required')
    return path


def j(path):
    return read(regular(path))


def lines(path):
    return [json.loads(x) for x in regular(path).read_text().splitlines()]


def dependency(name, path, q):
    path = regular(path)
    require(q['files'].get(str(path)) == runtime.sha(path), 'Audited dependency not pinned')
    loaded = sys.modules.get(name)
    require(loaded is None or Path(loaded.__file__) == path, 'Foreign cached audit dependency')
    sys.path.insert(0, str(path.parent))
    module = importlib.import_module(name)
    require(Path(module.__file__) == path, 'Audit dependency origin differs')
    return module


def fresh_idle(a, base):
    current = read(runtime.E / 'STATE.json')
    require(runtime.phase_free(current), 'Offline audit deferred: private/pending phase')
    host = a.ChunkProductionHost()
    host.start_binding = base.current_binding(current)
    require(host.idle(), 'Offline audit deferred: user work active')
    host.guard_binding(host.start_binding['native_pid'])


def tokenizer_contract(manifest, pack, q):
    """Bind the CPU encoder's explicit pack bytes and effective API template."""
    directory = fixtures.tokenizer_directory(pack)
    pins = manifest['tokenizer_source_sha256']; template = manifest['effective_template']
    require(type(pins) is dict and set(pins) == set(fixtures.TOKENIZER_NAMES),
            'Exact five tokenizer source files required')
    def pinned(path, digest):
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest)
                and q['files'].get(str(path)) == digest, 'Tokenizer/template qualification membership differs')
        require(runtime.sha(regular(path)) == digest, 'Tokenizer/template current bytes changed')
    for name, digest in pins.items(): pinned(directory / name, digest)
    pack_template = directory / 'chat_template.jinja'
    require(template['pack_template_relative_to_E'] == str(pack_template.relative_to(fixtures.E))
            and template['pack_template_sha256'] == pins['chat_template.jinja']
            and type(template['pack_template_replaced']) is bool
            and template['selection_policy'] == 'EXACT_UNCHANGED_B1_DSML_PICKER_WITH_PINNED_V41_FALLBACK',
            'Pack template source/selection contract differs')
    expected = fixtures.E / fixtures.FALLBACK_TEMPLATE if template['pack_template_replaced'] else pack_template
    require(template['effective_template_relative_to_E'] == str(expected.relative_to(fixtures.E)),
            'Foreign or unreviewed effective template')
    pinned(expected, template['effective_template_sha256'])
    if template['pack_template_replaced']:
        require(template['effective_template_sha256'] == fixtures.SUPPORT_PINS[fixtures.FALLBACK_TEMPLATE],
                'Fallback template differs from pinned API fixture')
    else:
        require(template['effective_template_sha256'] == pins['chat_template.jinja'],
                'Unswapped pack template bytes differ')
    picker = 'native-vision-v2/runtime/serve/dsml.py'
    require(template['api_picker_sha256'] == fixtures.SUPPORT_PINS[picker], 'API picker source differs')
    pinned(fixtures.E / picker, template['api_picker_sha256'])
    return {'passed': True, 'tokenizer_source_sha256': pins, 'effective_template': template}


def restoration_contract(state, metadata, legacy, q):
    # Reuse only the exact source-reviewed pure current-producer consumer.
    path = runtime.E / 'decode-optimization-20261028/maya-s-comparison-v1/long-cold-v1/lc_audit.py'
    lc = dependency('lc_audit', path, q)
    original = runtime.original_module('ms_compat_audit')
    return lc.restoration_contract(state, metadata, legacy, saved=saved, config=config,
                                   recorder=original.Recorder(), original=original)


def window_contract(w, output, metadata, arm):
    expected = [str(runtime.R / 'venv/bin/python3.14'), '-B', str(runtime.P / 'qv_owner.py'),
                '--phase', '--mode', 'quality', '--arm', arm, '--output', str(output),
                '--proof', str(metadata / 'proof.json')]
    require(w.get('command') == expected and bool(w.get('continued_from'))
            and type(w.get('test_returncode')) is int and w['test_returncode'] == 0
            and w.get('maintenance_held') is True and w.get('maintenance_resume_allowed') is True
            and w.get('restored') is False, 'Actual exact quality window exit0/continuation required')


def sse_contract(response):
    """Reconstruct the stored transport from its own raw SSE, including reasoning."""
    content = ''; reasoning = ''; finish = None; done = 0; events = []; usage = None; timings = None
    for row in response['raw']:
        line = row['line']
        require(isinstance(line, str), 'Raw SSE line must be text')
        if not line.startswith('data:'): continue
        payload = line[5:].strip()
        if not payload: continue
        require(done == 0, 'Event after DONE or duplicate DONE')
        if payload == '[DONE]': done += 1; continue
        event = json.loads(payload)
        require(isinstance(event, dict) and 'error' not in event, 'Raw SSE execution error')
        events.append(event)
        if event.get('usage') is not None: usage = event['usage']
        if event.get('timings') is not None: timings = event['timings']
        for choice in event.get('choices', []):
            delta = choice.get('delta') or {}
            require(not delta.get('tool_calls'), 'Unexpected tool call in known-answer quality case')
            c = delta.get('content') or ''; r = delta.get('reasoning_content') or ''
            require(isinstance(c, str) and isinstance(r, str), 'Malformed raw text delta')
            content += c; reasoning += r
            if choice.get('finish_reason'):
                require(finish is None, 'Multiple terminal choices')
                finish = choice['finish_reason']
    require(done == 1 and finish == 'stop' and response.get('done') is True
            and response.get('finish_reason') == finish and response.get('content') == content
            and response.get('reasoning') == reasoning and exact(response.get('events'), events)
            and exact(response.get('usage'), usage) and exact(response.get('timings'), timings)
            and response.get('tool_calls') == [], 'Saved response/raw SSE mismatch')
    return {'DONE': True, 'finish': finish, 'raw_SSE_reconstructed': True,
            'content_characters': len(content), 'reasoning_characters': len(reasoning)}


def complete_contract(receipt, manifest, arm):
    require(receipt.get('mode') == 'quality' and receipt.get('arm') == arm
            and receipt.get('private_cleanup_passed') is True
            and receipt.get('not_a_promotion') is True, 'Wrong terminal arm or cleanup')
    r = receipt['arm_results']; ids = [c['id'] for c in manifest['cases']]
    require(len(ids) == len(set(ids)) == 4 and r.get('complete') is True
            and r.get('native_request_count') == 4 and type(r['native_request_count']) is int
            and r.get('retry') is False and r.get('reason') is None
            and r.get('unrun_ids') == [] and r.get('DSI1_leftovers') == []
            and len(r['rows']) == 4 and [x['id'] for x in r['rows']] == ids,
            'Wrong/cap/partial/UNRUN/incomplete quality arm')
    require(exact(r['scores'], [{'id': i, 'passed': True, 'status': 'NATURAL_RESULT_SOURCE_AND_STATE_PASSED'}
                                for i in ids]), 'All four independently scored cases required')
    return r


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


def case_audit(case, folder, index, pid, result_row, reconcile, numerical):
    dest = folder / 'skip-controls' / case['id']; trace = folder / ('native-%03d' % index)
    for name in ('request.json', 'trace-receipt.json', 'native-statistics.json', 'tokens.jsonl'):
        regular(trace / name)
    require(exact(j(dest / 'request.json'), case['request']), 'Actual request differs from frozen fixture')
    response = j(dest / 'response.json'); sse = sse_contract(response)
    check = reconcile(trace, case, response, pid)
    require(exact(check, j(dest / 'native-audit.json')), 'Raw T/PID/DONE/request/cache proof differs')
    metrics = saved.score_saved(case, response, check, quality=True)
    tokens = saved.emitted_ids(trace / 'tokens.jsonl', check['observed_tokens'])
    size = numerical.dump_size(regular(folder / ('logits.%d.f32' % (index + 1))))
    expected = {'id': case['id'], 'passed': True, 'native': check['native'],
                'observed_tokens': check['observed_tokens'],
                # Match the producer's JSON arithmetic order; this is a stored
                # diagnostic field, not a numerical tolerance for model logits.
                'native_decode_tokens_per_second': check['native']['generated'] / (check['native']['decode_ms'] / 1000),
                'client_seconds': check.get('client_full_s'),
                'content_characters': sse['content_characters'], 'reasoning_characters': sse['reasoning_characters'],
                'manual_review_pending': False, 'general_quality_or_equivalence_claim': False,
                'dump_size_only': size}
    require(exact(result_row, expected), 'Phase case row does not match saved raw evidence')
    return {'id': case['id'], 'typed_known_answer_correct': True, 'natural_stop': True,
            'native': check['native'], 'observed_tokens': check['observed_tokens'],
            'token_contract': tokens, 'SSE': sse, 'dump_size_only': size}


def scan_cases(cases, folder, pid, result_rows, reconcile, numerical, guard):
    rows = []
    for i, case in enumerate(cases):
        guard()
        row = case_audit(case, folder, i, pid, result_rows[i], reconcile, numerical)
        row['dump'] = numerical.finite_dump(folder / ('logits.%d.f32' % (i + 1)))
        require(row['dump']['all_finite'] is True and row['dump']['token_row_alignment_claimed'] is False
                and re.fullmatch('[0-9a-f]{64}', row['dump']['sha256'])
                and row['dump']['bytes'] == row['dump_size_only']['bytes']
                and row['dump']['rows'] == row['dump_size_only']['rows'], 'Incomplete/changed finite dump audit')
        rows.append(row)
    return rows


def file_identity(path):
    s = regular(path).stat()
    return dict(device=s.st_dev, inode=s.st_ino, bytes=s.st_size, mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)


def stage_paths(arm):
    require(arm in ('QS0', 'QS1'), 'Exact quality arm')
    root = runtime.P / arm / 'offline-audit-FIRST'
    return root, root / 'metadata.json'


def bounded_child(path, stage, result_path, metadata):
    r = j(path); c = r['child']
    require(r['stage'] == stage and r['arm'] == metadata['arm']
            and r['qualification_sha256'] == metadata['qualification_sha256']
            and r['metadata_sha256'] == runtime.sha(stage_paths(metadata['arm'])[1])
            and r['result_path'] == str(result_path) and r['result_sha256'] == runtime.sha(regular(result_path))
            and exact(r['audit_source_sha256'], metadata['audit_source_sha256']), 'Bounded child artifact binding differs')
    require(type(c['pid']) is int and c['pid'] > 0 and type(c['returncode']) is int and c['returncode'] == 0
            and c['error'] is None and c['cleanup_errors'] == []
            and type(c['wall_seconds']) in (int, float) and math.isfinite(c['wall_seconds']) and 0 <= c['wall_seconds'] <= 90
            and type(c['CPU_limit_seconds']) is int and c['CPU_limit_seconds'] == 30
            and type(c['wall_limit_seconds']) is int and c['wall_limit_seconds'] == 90
            and type(c['nice_increment']) is int and c['nice_increment'] == 15
            and type(c['Linux_AS_bytes']) is int and c['Linux_AS_bytes'] == 512 * 2**20,
            'One successful bounded physical Linux audit child required')
    require(all(c['environment'].get(k) == v for k, v in {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1',
                'OPENBLAS_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1'}.items()),
            'Audit child environment differs')
    return runtime.sha(regular(path))


def load_metadata(arm):
    a, old, base, legacy, startup = runtime.support(); fresh_idle(a, base)
    root, path = stage_paths(arm); d = j(path)
    require(d['stage'] == 'METADATA' and d['metadata_passed'] is True and d['passed'] is False
            and d['arm'] == arm and d['mode'] == 'quality', 'Exact successful metadata-only audit required')
    qpath = runtime.P / 'quality-qualification.json'
    require(runtime.sha(regular(qpath)) == d['qualification_sha256'], 'Metadata qualification changed')
    q = j(qpath)
    require(exact(d['audit_source_sha256'], {p: v for p, v in q['files'].items() if p.endswith('.py')})
            and str(runtime.P / 'qv_audit.py') in d['audit_source_sha256'], 'Metadata audit source closure differs')
    for p, digest in d['audit_source_sha256'].items():
        require(runtime.sha(regular(p)) == digest, 'Audit source changed after metadata stage')
    output, metadata = runtime.owned_paths(d['output'], 'quality', arm, present=True)
    registry = j(runtime.P / 'quality-arms.json')[arm]
    require(registry['attempted'] is True and registry['output'] == str(output), 'Metadata arm/output custody differs')
    factor=config.factor('quality',arm);which='B' if factor['candidate'] else 'A'
    require(d['encoded_manifest_path']==str(runtime.encoded_path(which)), 'Exact original encoded manifest reference required')
    window=Path(d['window'])
    require(window.parent==runtime.R/'windows' and re.fullmatch(r'[0-9]{8}T[0-9]{6}Z.json',window.name),
            'Exact owned canonical window reference required')
    require(len(d['rows']) == len(d['dump_files']) == 4, 'Four metadata rows/files required')
    for i, item in enumerate(d['dump_files'], 1):
        expected = output / 'native' / ('logits.%d.f32' % i)
        require(item['path'] == str(expected) and item['index'] == i and item['case_id'] == d['rows'][i - 1]['id']
                and exact(file_identity(expected), item['identity']), 'Dump source/identity changed after metadata stage')
    for p, digest in d['evidence_sha256'].items():
        p = Path(p)
        require(p.is_relative_to(output) or p.is_relative_to(metadata)
                or p in (Path(d['window']), Path(d['window']).with_suffix('.telemetry.jsonl'), Path(d['encoded_manifest_path'])),
                'Foreign terminal evidence path')
        require(runtime.sha(regular(p)) == digest, 'Terminal evidence changed after metadata stage')
    bounded_child(root / 'metadata.child.json', 'metadata', path, d)
    return d, q, a, base


def finite_contract(row, item, metadata_sha, arm, qpin, pid):
    require(row['stage'] == 'FINITE_SCAN' and row['passed'] is True and row['arm'] == arm
            and row['qualification_sha256'] == qpin and row['metadata_sha256'] == metadata_sha
            and type(row['native_pid']) is int and row['native_pid'] == pid
            and row['index'] == item['index'] and row['case_id'] == item['case_id'] and row['path'] == item['path']
            and exact(row['identity_before'], item['identity']) and exact(row['identity_after'], item['identity']),
            'Finite scan arm/case/file identity differs')
    f = row['dump']
    require(f['all_finite'] is True and f['token_row_alignment_claimed'] is False
            and type(f['bytes']) is int and f['bytes'] == item['identity']['bytes']
            and type(f['rows']) is int and f['rows'] > 0 and f['rows'] * 517120 == f['bytes']
            and type(f['sha256']) is str and re.fullmatch('[0-9a-f]{64}', f['sha256']), 'Complete finite result required')


def prior_scans(root, d, count):
    pin = runtime.sha(root / 'metadata.json'); scans = []
    for index in range(1, count + 1):
        p = root / ('scan-%d.json' % index); row = j(p)
        finite_contract(row, d['dump_files'][index - 1], pin, d['arm'], d['qualification_sha256'], d['actual_native_pid'])
        bounded_child(root / ('scan-%d.child.json' % index), 'scan-%d' % index, p, d)
        scans.append(row)
    return scans


def scan_index(arm, index):
    require(type(index) is int and 1 <= index <= 4, 'Exactly one finite file index')
    d, q, a, base = load_metadata(arm); root, path = stage_paths(arm); pin = runtime.sha(path)
    prior_scans(root, d, index - 1)  # No skipping an incomplete/failed prior child.
    item = d['dump_files'][index - 1]; p = Path(item['path'])
    numerical = dependency('imma_numeric_controls', runtime.E / 'decode-optimization-20261028/model-v1/imma_numeric_controls.py', q)
    fresh_idle(a, base); before = file_identity(p)
    result = numerical.finite_dump(p)  # Exactly ONE full finite/byte-hash scan.
    after = file_identity(p); fresh_idle(a, base)
    require(runtime.sha(regular(path)) == pin
            and runtime.sha(runtime.P / 'quality-qualification.json') == d['qualification_sha256'], 'Audit custody changed')
    row = {'stage': 'FINITE_SCAN', 'passed': True, 'arm': arm, 'qualification_sha256': d['qualification_sha256'],
           'native_pid': d['actual_native_pid'],
           'metadata_sha256': pin, 'index': index, 'case_id': item['case_id'], 'path': str(p),
           'identity_before': before, 'identity_after': after, 'dump': result}
    finite_contract(row, item, pin, arm, d['qualification_sha256'], d['actual_native_pid'])
    return row


def assemble(arm):
    d, q, a, base = load_metadata(arm); root, path = stage_paths(arm)
    scans = prior_scans(root, d, 4); rows = []
    for row, scan in zip(d['rows'], scans): rows.append({**row, 'dump': scan['dump']})
    fresh_idle(a, base)
    return {**d, 'stage': 'COMPLETE', 'passed': True, 'rows': rows, 'metadata_sha256': runtime.sha(path),
            'finite_scan_receipt_sha256': {str(root / ('scan-%d.child.json' % i)): runtime.sha(root / ('scan-%d.child.json' % i)) for i in range(1, 5)},
            'finite_scans_in_separate_bounded_children': True}


def audit(arm):
    require(arm in ('QS0', 'QS1'), 'Only new whole-pack quality arms')
    a, old, base, legacy, startup = runtime.support()
    fresh_idle(a, base)  # Before qualification hashes or any float scan.
    registry = j(runtime.P / 'quality-arms.json')[arm]
    output, metadata = runtime.owned_paths(registry['output'], 'quality', arm, present=True)
    state = j(metadata / 'state.json')
    require(registry.get('attempted') is True and state.get('status') == runtime.statuses('quality')['complete']
            and state.get('mode') == 'quality' and state.get('arm') == arm
            and state.get('output') == str(output) and state.get('proof_path') == str(metadata / 'proof.json')
            and type(state.get('controller_pid')) is int and state['controller_pid'] == registry.get('controller_pid'),
            'Only actual completed/restored owned quality arm')
    qpin = state['qualification_sha256']; q = runtime.qualified('quality', qpin)
    for filename in ('qv_audit.py', 'qv_dispatch.py'):
        require(q['files'].get(str(runtime.P / filename)) == runtime.sha(runtime.P / filename),
                'Independent auditor omitted from qualification')
    proof = j(metadata / 'proof.json')
    require(proof.get('qualified_for_owned_maya_s') is True and proof.get('mode') == 'quality'
            and proof.get('arm') == arm and proof.get('output') == str(output)
            and proof.get('qualification_sha256') == qpin and proof.get('files') == q['files'],
            'Immutable arm/source proof differs')
    window = Path(state['window'])
    require(window.parent == runtime.R / 'windows' and re.fullmatch(r'[0-9]{8}T[0-9]{6}Z.json', window.name),
            'Foreign canonical window receipt')
    window_contract(j(window), output, metadata, arm)
    telemetry = lines(window.with_suffix('.telemetry.jsonl'))
    require(telemetry and type(telemetry[-1].get('kernel_capture_returncode')) is int
            and telemetry[-1]['kernel_capture_returncode'] == 0 and telemetry[-1].get('kernel_fault_lines') == [],
            'Kernel capture/fault proof missing')
    resources = saved.resource_contract([s for s in telemetry if 'root_free_bytes' in s], 4096)
    restored = restoration_contract(state, metadata, legacy, q)
    base.binding_contract(restored['selected_identity']['start_binding'])
    require(restored.get('passed') is True, 'Restoration/public verification not complete')
    folder = output / 'native'; factor = config.factor('quality', arm); which = 'B' if factor['candidate'] else 'A'
    manifest_path = runtime.encoded_path(which)
    require(q['files'].get(str(manifest_path)) == runtime.sha(manifest_path), 'Encoded fixture not qualified')
    m = j(manifest_path)
    require(exact(m, runtime.quality_manifest(arm)), 'Frozen original quality manifest changed')
    require(m['mode'] == 'quality' and m['context'] == 1048576 and m['default_output'] == 262144
            and exact(m['policy'], fixtures.POLICY) and len(m['cases']) == 4 and m['lifecycle_cases'] == []
            and m['pack_relative_to_E'] == str(Path(factor['pack']).relative_to(config.E))
            and exact(j(output / 'fixtures.json'), m), 'Exact pack-specific four-state fixture required')
    fixtures.validate_encoded(m['cases'], 'quality')
    tokenizer = tokenizer_contract(m, Path(factor['pack']), q)
    c = j(output / 'candidate-config.json'); baseline = j(runtime.P / 'base-config.json')
    config.check_config(baseline, c, folder, 'quality', arm)
    require(j(output / 'candidate-config.shared-settings.json') == {'max_tokens': 262144}, 'Shared default output differs')
    ready = j(folder / 'native-ready.json'); pid = ready['pid']
    require(type(pid) is int and pid > 0, 'Typed actual native PID')
    log = regular(folder / 'engine.log').read_text(errors='replace')
    # Pure saved-data helpers only; no producer phase/entry invocation.
    controls = dependency('qv_controls', runtime.P / 'qv_controls.py', q)
    observed = j(output / 'startup-audit.json')
    actual = controls.startup(a, old, ready, j(output / 'startup-health.json'),
                              j(output / 'startup-models.json'), log, q['allowed_automatic_cuts'][which])
    require(all(exact(observed.get(k), v) for k, v in actual.items()), 'Saved startup source/placement differs')
    proc = observed['actual_process']
    config.process_contract(c, proc['actual_argv'], proc['controlled_env'], proc['actual_cgroup'], same_executable=proc['same_executable'])
    group = proc['actual_cgroup'].strip().splitlines()
    require(len(group) == 1 and group[0].startswith('0::/')
            and group[0].split('/')[-1] == 'strata-deepseek-window.service'
            and proc['native_sha256'] == config.BASE_NATIVE and proc['native_pid'] == pid
            and type(proc['start_ticks']) is int and proc['start_ticks'] > 0, 'Exact native executable/cgroup identity absent')
    entry = j(folder / 'entry-audit.json'); server = j(output / 'server-start.json')
    expected_entry = [str(runtime.R / 'venv/bin/python3.14'), '-u', '-B', str(runtime.P / 'qv_owner.py'),
                      '--entry', '--mode', 'quality', '--arm', arm, '--config', str(output / 'candidate-config.json'),
                      '--config-sha256', runtime.sha(output / 'candidate-config.json'), '--trace-directory', str(folder)]
    require(type(server['pid']) is int and server['pid'] > 0 and server['argv'] == expected_entry
            and entry['server_pid'] == server['pid'] and type(entry['startup_retries']) is int and entry['startup_retries'] == 0
            and type(entry['default_effort']) is int and entry['default_effort'] == 100 and entry['native_sha256'] == config.BASE_NATIVE
            and entry['config_sha256'] == runtime.sha(output / 'candidate-config.json')
            and entry['owned_window'] == str(window) and entry['context'] == 1048576
            and entry['output_allowance'] == 262144 and exact(entry['whole_pack_factor'], factor),
            'Private API/config/retry0/whole-pack identity differs')
    saved.private_cleanup(folder, pid)
    cleanup = j(folder / 'server-cleanup.json'); closes = lines(folder / 'native-close.jsonl')
    require(cleanup['server_pid'] == server['pid'] and cleanup['wait_error'] is None
            and exact(cleanup['native_close'], closes)
            and closes[0]['server_pid'] == server['pid']
            and '[strata] stopped' in regular(folder / 'server.log').read_text(errors='replace'),
            'Private raw API/native parent closure differs')
    helper = runtime.E / 'decode-optimization-20261028/model-v1'
    numerical = dependency('imma_numeric_controls', helper / 'imma_numeric_controls.py', q)
    storage = dependency('imma_storage', helper / 'imma_storage.py', q)
    launch = j(folder / 'native-file-bound.json')
    require(launch['native_pid'] == pid and launch['argv'] == config.expected_native_argv(c)[:-1]
            and launch['API_limits_changed'] is False and launch['file_limit_bytes'] == storage.HARD_FILE_BYTES
            and observed['native_file_limit_raw'].split()[3:5] == [str(storage.HARD_FILE_BYTES)] * 2,
            'Actual child-only finite dump file bound absent')
    receipt = j(output / 'receipt.json'); result = complete_contract(receipt, m, arm)
    fence = fence_contract(j(output / 'private-memory-fence.json'), receipt['resource_fence_terminal'],
                           j(output / 'private-memory-fence-restored.json'), j(metadata / 'private-memory-fence-collected.json'))
    require(numerical.dump_snapshot(folder, complete=True)['status'] == 'COMPLETE_SIZE_ONLY'
            and numerical.owned_storage_snapshot(folder)['status'] == 'WITHIN_BUDGET', 'Closed dump/cache/log budget failed')
    trace_helper = dependency('q8_audit', runtime.E / 'q8-batch-v1/q8_audit.py', q)
    skip = dependency('skip_controls', runtime.E / 'prefill-cache-improvements-20261027/skip_controls.py', q)
    observed_skip = skip.activation(log, 1, required=True)
    require(exact(observed_skip, result['mode1_activation'])
            and observed_skip['activation_early_rows'] == m['expected_mode1_activation_skipped_tokens'], 'Actual four-state skip path differs')
    require({p.name for p in folder.glob('native-[0-9][0-9][0-9]')} == {'native-%03d' % i for i in range(4)}
            and not list((folder / 'tmp').glob('deepseek-native-pictures-*/req-*.dsi')), 'Extra native request or image lifetime leak')
    rows = [case_audit(case, folder, i, pid, result['rows'][i], trace_helper.reconcile, numerical)
            for i, case in enumerate(m['cases'])]
    dump_files = [{'index': i + 1, 'case_id': case['id'], 'path': str(folder / ('logits.%d.f32' % (i + 1))),
                   'identity': file_identity(folder / ('logits.%d.f32' % (i + 1)))} for i, case in enumerate(m['cases'])]
    evidence = [window, window.with_suffix('.telemetry.jsonl'), manifest_path, metadata / 'state.json', metadata / 'proof.json',
                metadata / 'public-default-output-request.json', metadata / 'public-default-output-sse.txt', metadata / 'old-owner-close.json', metadata / 'private-memory-fence-collected.json']
    evidence += [output / n for n in ('fixtures.json', 'candidate-config.json', 'candidate-config.shared-settings.json',
                 'startup-audit.json', 'startup-health.json', 'startup-models.json', 'server-start.json', 'receipt.json',
                 'private-memory-fence.json', 'private-memory-fence-restored.json')]
    evidence += [folder / n for n in ('native-ready.json', 'engine.log', 'entry-audit.json', 'server-cleanup.json',
                 'native-close.jsonl', 'server.log', 'native-file-bound.json')]
    for i, case in enumerate(m['cases']):
        evidence += [folder / ('native-%03d' % i) / n for n in ('request.json', 'trace-receipt.json', 'native-statistics.json', 'tokens.jsonl')]
        evidence += [folder / 'skip-controls' / case['id'] / n for n in ('request.json', 'response.json', 'native-audit.json')]
    fresh_idle(a, base)
    require(runtime.sha(runtime.P / 'quality-qualification.json') == qpin, 'Qualification changed during audit')
    return {'stage': 'METADATA', 'passed': False, 'metadata_passed': True, 'mode': 'quality', 'arm': arm, 'qualification_sha256': qpin,
            'output': str(output), 'window': str(window), 'encoded_manifest_path': str(manifest_path), 'dump_files': dump_files,
            'evidence_sha256': {str(p): runtime.sha(regular(p)) for p in evidence},
            'audit_source_sha256': {p: v for p, v in q['files'].items() if p.endswith('.py')},
            'whole_pack_factor': factor, 'rows': rows, 'resources': resources, 'private_fence': fence,
            'tokenizer_custody': tokenizer,
            'actual_native_pid': pid, 'selected_identity': restored['selected_identity'],
            'purpose': 'BOUNDED_FOUR_STATE_WHOLE_PACK_FINITE_AND_KNOWN_ANSWER_SCREEN',
            'manual_full_output_review_required': True, 'cross_pack_numeric_equivalence': False,
            'token_row_alignment_claimed': False, 'near_full_context_or_output_tested': False,
            'general_quality_claim': False, 'performance_claim': False, 'deployment_admitted': False}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--arm', choices=['QS0', 'QS1'], required=True)
    parser.add_argument('--stage', choices=['metadata', 'scan', 'assemble'], required=True)
    parser.add_argument('--index', type=int)
    args = parser.parse_args(); root, meta = stage_paths(args.arm)
    require((args.stage == 'scan' and args.index in (1, 2, 3, 4)) or (args.stage != 'scan' and args.index is None), 'Exact stage/index')
    name = 'scan-%d' % args.index if args.stage == 'scan' else args.stage
    target = meta if args.stage == 'metadata' else (root / (name + '.json') if args.stage == 'scan' else runtime.P / args.arm / 'terminal-audit.json')
    for p in (target.parent, *target.parent.parents): require(not p.is_symlink(), 'Audit output parent alias')
    a, old, base, legacy, startup = runtime.support(); fresh_idle(a, base)
    root.mkdir(parents=True, exist_ok=True)
    attempt = root / (name + '.attempt.json')
    require(not target.exists() and not target.is_symlink(), 'Preserve first terminal audit')
    with attempt.open('x') as f: json.dump({'arm': args.arm, 'stage': name, 'retry': False}, f)
    result = audit(args.arm) if args.stage == 'metadata' else scan_index(args.arm, args.index) if args.stage == 'scan' else assemble(args.arm)
    with target.open('x') as f: json.dump(result, f, indent=2, allow_nan=False); f.write('\n')


if __name__ == '__main__': main()
