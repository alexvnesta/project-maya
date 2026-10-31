"""New whole-pack observations and private-window resource fence; no action at import."""
import json
import hashlib
import math
import os
from pathlib import Path
import re
import subprocess
import time
from contextlib import contextmanager

import ms_runtime as runtime


class Incomplete(Exception): pass


def typed_pairs(pairs):
    value = {}
    for k, v in pairs:
        if k in value: raise ValueError('Duplicate JSON answer key')
        value[k] = v
    return value


def token_contract(path, expected_count):
    ids = []; last = -1.0
    with Path(path).open() as f:
        for line in f:
            row = json.loads(line)
            runtime.require(set(row) == {'token', 'seconds'} and type(row['token']) is int
                            and 0 <= row['token'] < 129280 and type(row['seconds']) in (int, float)
                            and math.isfinite(row['seconds']) and row['seconds'] >= last,
                            'Invalid emitted token/source-clock row')
            ids.append(row['token']); last = row['seconds']
    runtime.require(type(expected_count) is int and len(ids) == expected_count, 'Emitted token count mismatch')
    return {'count': len(ids), 'valid_vocabulary_ids': True,
            'ordered_ids_sha256': hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest()}


def memory_events(root):
    fields = dict(line.split() for line in (Path(root) / 'memory.events').read_text().splitlines())
    runtime.require(all(v.isdecimal() for v in fields.values()) and {'oom', 'oom_kill'} <= fields.keys(),
                    'Typed private memory events required')
    return {k: int(v) for k, v in fields.items()}


def private_cgroup(raw, root=Path('/sys/fs/cgroup')):
    lines = raw.strip().splitlines()
    runtime.require(len(lines) == 1 and lines[0].startswith('0::/'), 'Unified private cgroup required')
    relative = lines[0][3:]
    runtime.require('..' not in relative.split('/') and relative.split('/')[-1] == 'strata-deepseek-window.service',
                    'Only the existing private window may receive the fence')
    path = Path(str(root) + relative)
    runtime.require(path.is_dir() and not path.is_symlink(), 'Actual owned cgroup directory required')
    return path


UNIT = 'strata-deepseek-window.service'
FENCE_FIELDS = ('InvocationID', 'Transient', 'ControlGroup', 'MemoryMax', 'MemorySwapMax',
                'FragmentPath', 'DropInPaths', 'LoadState')


def limit_value(raw):
    runtime.require(type(raw) is str and (raw in ('infinity', 'max') or raw.isdecimal()), 'Typed memory property required')
    return 'max' if raw in ('infinity', 'max', str(2**64 - 1)) else str(int(raw))


def unit_memory(command=subprocess.run):
    argv = ['systemctl', '--user', 'show', UNIT]
    for name in FENCE_FIELDS: argv += ['-p', name]
    result = command(argv, check=False, timeout=15, capture_output=True, text=True,
                     env=dict(os.environ, XDG_RUNTIME_DIR='/run/user/' + str(os.getuid())))
    runtime.require(type(result.returncode) is int and result.returncode in (0, 4), 'Cannot observe exact private unit')
    rows = [line.split('=', 1) for line in result.stdout.splitlines()]
    runtime.require(all(len(row) == 2 for row in rows) and len({row[0] for row in rows}) == len(rows),
                    'Malformed/duplicate private unit properties')
    value = dict(rows); runtime.require(set(value) == set(FENCE_FIELDS), 'Exact private unit property fields required')
    value['DropInPaths'] = value['DropInPaths'].split()
    return value


def memory_properties(value):
    return {key: limit_value(value[key]) for key in ('MemoryMax', 'MemorySwapMax')}


def fence_identity(value, group, transient_root):
    fragment = Path(transient_root) / UNIT
    runtime.require(value['Transient'] == 'yes' and value['LoadState'] == 'loaded'
                    and re.fullmatch('[0-9a-f]{32}', value['InvocationID']) is not None
                    and value['ControlGroup'] and str(group).endswith(value['ControlGroup'])
                    and value['FragmentPath'] == str(fragment), 'Exact transient unit invocation/cgroup/fragment required')
    return fragment


def set_memory(properties, command):
    args = [key + '=' + ('infinity' if properties[key] == 'max' else properties[key])
            for key in ('MemoryMax', 'MemorySwapMax')]
    command(['systemctl', '--user', 'set-property', '--runtime', UNIT, *args],
            check=True, timeout=15, capture_output=True, text=True,
            env=dict(os.environ, XDG_RUNTIME_DIR='/run/user/' + str(os.getuid())))


def restore_private_fence(fence, *, children_closed, command=subprocess.run):
    output = Path(fence['output']); record = {'passed': False, 'children_closed': children_closed,
        'prior_properties': fence['prior_properties'], 'same_invocation': False}
    try:
        runtime.require(children_closed is True, 'Do not relax limits while private children may remain')
        current = unit_memory(command); original = fence['unit_before']
        fence_identity(current, Path(fence['cgroup']), Path(fence['transient_root']))
        runtime.require(current['InvocationID'] == original['InvocationID']
                        and current['ControlGroup'] == original['ControlGroup'], 'Foreign private invocation; no property write')
        record['same_invocation'] = True
        actual = memory_properties(current)
        for name, installed in (('MemoryMax', str(runtime.MEMORY_MAX)), ('MemorySwapMax', '0')):
            runtime.require(actual[name] in (fence['prior_properties'][name], installed), 'Memory property changed by another owner')
        set_memory(fence['prior_properties'], command)
        after = unit_memory(command); fence_identity(after, Path(fence['cgroup']), Path(fence['transient_root']))
        runtime.require(after['InvocationID'] == original['InvocationID'] and after['ControlGroup'] == original['ControlGroup'],
                        'Invocation changed during property restoration')
        record['restored_properties'] = memory_properties(after)
        runtime.require(record['restored_properties'] == fence['prior_properties'], 'Original memory property readback differs')
        group = Path(fence['cgroup'])
        runtime.require((group / 'memory.max').read_text().strip() == record['restored_properties']['MemoryMax']
                        and (group / 'memory.swap.max').read_text().strip() == record['restored_properties']['MemorySwapMax'],
                        'Original cgroup limits were not restored')
        record.update(passed=True, unit_after=after)
        return record
    except BaseException as exc:
        record['error'] = repr(exc); raise
    finally: runtime.emit(output / 'private-memory-fence-restored.json', record)


def install_private_fence(output, *, command=subprocess.run, proc=Path('/proc/self/cgroup'), root=Path('/sys/fs/cgroup'),
                          transient_root=None):
    """Admitted phase only, BEFORE any API/native child. Partial writes are restored."""
    group = private_cgroup(proc.read_text(), root)
    transient_root = Path(transient_root or ('/run/user/%d/systemd/transient' % os.getuid()))
    before = unit_memory(command); fragment = fence_identity(before, group, transient_root)
    prior = memory_properties(before)
    runtime.require(prior['MemoryMax'] == 'max' or int(prior['MemoryMax']) >= runtime.MEMORY_MAX,
                    'Do not relax a stricter preexisting private memory maximum')
    runtime.require((group / 'memory.max').read_text().strip() == prior['MemoryMax']
                    and (group / 'memory.swap.max').read_text().strip() == prior['MemorySwapMax'],
                    'Original property/cgroup limits differ')
    fence = {'output': str(output), 'cgroup': str(group), 'memory_max': runtime.MEMORY_MAX, 'swap_max': 0,
        'prior_properties': prior, 'unit_before': before, 'transient_root': str(transient_root),
        'fragment': str(fragment), 'owned_dropin_directory': str(fragment) + '.d',
        'events_before': memory_events(group), 'mutation_attempted': False}
    try:
        fence['mutation_attempted'] = True
        runtime.emit(Path(output) / 'private-memory-fence.json', fence)
        set_memory({'MemoryMax': str(runtime.MEMORY_MAX), 'MemorySwapMax': '0'}, command)
        after = unit_memory(command); fence_identity(after, group, transient_root)
        runtime.require(after['InvocationID'] == before['InvocationID'] and after['ControlGroup'] == before['ControlGroup'],
                        'Private invocation changed during memory fence install')
        runtime.require(memory_properties(after) == {'MemoryMax': str(runtime.MEMORY_MAX), 'MemorySwapMax': '0'}
                        and (group / 'memory.max').read_text().strip() == str(runtime.MEMORY_MAX)
                        and (group / 'memory.swap.max').read_text().strip() == '0', 'Private fence readback differs')
        current = (group / 'memory.current').read_text().strip()
        runtime.require(current.isdecimal() and int(current) < runtime.MEMORY_MAX, 'Private fence already exhausted')
        runtime.require(runtime.memory_available() >= runtime.HOST_MARGIN, 'Physical host margin unavailable')
        fence.update(unit_installed=after, initial_current=int(current), installed=True)
        runtime.emit(Path(output) / 'private-memory-fence.json', fence)
        return fence
    except BaseException as primary:
        try: restore_private_fence(fence, children_closed=True, command=command)
        except BaseException as cleanup: primary.add_note('Partial fence restore failed: ' + repr(cleanup))
        raise


def private_children_closed(folder, api_processes, *, command=subprocess.run, proc=Path('/proc')):
    # Handles are captured immediately after Popen, before receipt writes. A
    # missing receipt is never evidence that a launched child was cleaned up.
    runtime.require(type(api_processes) is list and len(api_processes) <= 1, 'One captured private API handle required')
    if any(p.poll() is None for p in api_processes): return False
    ready = Path(folder) / 'native-ready.json'
    if ready.exists():
        native = json.loads(ready.read_text())['pid']
        runtime.require(type(native) is int and native > 0, 'Typed owned native PID required')
        if (Path(proc) / str(native)).exists(): return False
    observed = command(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'],
                       check=True, timeout=15, capture_output=True, text=True)
    runtime.require(all(line.strip().isdecimal() for line in observed.stdout.splitlines() if line.strip()),
                    'Cannot establish private GPU child closure')
    return not observed.stdout.strip()


@contextmanager
def fenced_phase(output):
    """Restore only the two captured properties, after actual child closure."""
    fence = install_private_fence(output); handles = []; primary = None
    try:
        yield fence, handles
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            closed = private_children_closed(Path(output) / 'native', handles)
            restore_private_fence(fence, children_closed=closed)
        except BaseException as cleanup:
            if primary is not None: primary.add_note('Private fence cleanup: ' + repr(cleanup))
            else: raise


def fence_collected(output, metadata, *, command=subprocess.run, clock=time.monotonic, pause=time.sleep):
    fence = json.loads((Path(output) / 'private-memory-fence.json').read_text()); old = fence['unit_before']
    deadline = clock() + 30
    while True:
        current = unit_memory(command)
        runtime.require(not current['InvocationID'] or current['InvocationID'] == old['InvocationID'],
                        'Another private invocation appeared; no collection claim')
        if current['LoadState'] == 'not-found' and not current['InvocationID']: break
        if clock() >= deadline: raise RuntimeError('Owned transient window collection not observed')
        pause(.2)
    fragment = Path(fence['fragment']); dropins = Path(fence['owned_dropin_directory'])
    runtime.require(fragment == Path(fence['transient_root']) / UNIT and str(dropins) == str(fragment) + '.d',
                    'Exact recorded owned transient paths required')
    runtime.require(not fragment.exists() and not fragment.is_symlink() and not dropins.exists() and not dropins.is_symlink(),
                    'Owned transient fragment/drop-ins remain')
    record = {'passed': True, 'transient': old['Transient'] == 'yes', 'unit_collected': True,
              'fragment_absent': True, 'dropins_absent': True, 'fragment': str(fragment),
              'owned_dropin_directory': str(dropins), 'original_invocation': old['InvocationID']}
    runtime.emit(Path(metadata) / 'private-memory-fence-collected.json', record)
    return record


def fence_terminal(fence):
    after = memory_events(fence['cgroup']); before = fence['events_before']
    runtime.require(all(after.get(k, -1) >= v for k, v in before.items()), 'Private memory event counters regressed')
    delta = {k: after[k] - before.get(k, 0) for k in after}
    runtime.require(delta.get('oom', 0) == delta.get('oom_kill', 0) == 0, 'Private compatibility fence recorded OOM')
    return {'passed': True, 'events_after': after, 'events_delta': delta,
            'cache_charging_disclosure': 'memory.current/peak include charged file cache and pinned memory; not process RSS'}


def placement(log, allowed_cuts):
    rows = []
    pattern = (r'ds4: CUDA([01]) layers \[([0-9]+), ([0-9]+)\](?: \+ head)?: weights ([0-9.]+) GB, '
               r'experts ([0-9.]+) GB \(([0-9]+) of ([0-9]+) in VRAM\), caches ([0-9.]+) GB, ([0-9]+) MiB free')
    for line in log.splitlines():
        if not line.startswith('ds4: CUDA') or ' layers [' not in line: continue
        match = re.fullmatch(pattern, line); runtime.require(match is not None, 'Unknown native placement row')
        v = match.groups(); row = {'device': int(v[0]), 'first': int(v[1]), 'last': int(v[2]),
             'weights_GB_rounded': float(v[3]), 'experts_GB_rounded': float(v[4]),
             'human_experts_including_drafter': int(v[5]), 'human_total': int(v[6]),
             'cache_GB_rounded': float(v[7]), 'free_MiB': int(v[8])}
        runtime.require((' + head:' in line) == (row['device'] == 1), 'Head must remain on last GPU')
        if row not in rows: rows.append(row)
    rows.sort(key=lambda r: r['device'])
    runtime.require(len(rows) == 2 and [r['device'] for r in rows] == [0, 1]
                    and (rows[0]['first'], rows[0]['last'], rows[1]['last']) == (0, 42, 39),
                    'Two-device trunk/drafter placement required')
    cut = rows[1]['first']
    runtime.require(type(allowed_cuts) is list and all(type(x) is int for x in allowed_cuts)
                    and cut in allowed_cuts and 1 <= cut < 40, 'Automatic split outside frozen source-reviewed set')
    return {'trunk_split': [cut, 40 - cut], 'human_rows': rows,
            'drafter_GPU': 0, 'head_GPU': 1, 'direct_INFO_counts_are_separate': True}


def startup(a, old, ready, health, models, log, allowed_cuts):
    result = old.capacity_startup(ready, health, models, log, 4096, expected_context=1048576)
    result['placement'] = placement(log, allowed_cuts)
    result['Q8'] = old.q8_phase.startup_q8_receipt(log, 1)
    result['projection'] = old.startup_guard(log, {'id': 'B1', 'direction': str(runtime.D / 'runtime-direction-L22.gguf')})
    runtime.require(result['expert_slots'] + result['cpu_experts'] == 15360, 'Actual trunk expert accounting differs')
    return result


def actual_native(c, pid, config):
    proc = Path('/proc') / str(pid)
    env = dict(x.split('=', 1) for x in (proc / 'environ').read_bytes().decode().split('\0') if '=' in x)
    argv = (proc / 'cmdline').read_bytes().decode().split('\0'); group = (proc / 'cgroup').read_text()
    same = os.path.samefile(proc / 'exe', c['exe'])
    result = config.process_contract(c, argv, env, group, same_executable=same)
    runtime.require(runtime.sha(c['exe']) == config.BASE_NATIVE, 'Selected native changed')
    return {**result, 'native_pid': pid, 'native_sha256': config.BASE_NATIVE,
            'controlled_env': config.controlled_environment(env),
            'actual_argv': argv, 'actual_cgroup': group, 'same_executable': same,
            'start_ticks': int((proc / 'stat').read_text().rsplit(') ', 1)[1].split()[19])}


def bounded_request(base, body, deadline, folder, quality, *, stream_class, observe, wait_for,
                    dump_snapshot, storage_snapshot, clock=time.monotonic):
    if deadline - clock() < 10: return {'budget_not_started': True, 'request_sent': False}
    stream = stream_class(base, body, timeout=1200).start(); stop = None; next_resource = clock()
    try:
        while not stream.finished.wait(min(.1, max(0, deadline - clock()))):
            if quality and dump_snapshot(folder)['status'] == 'INCOMPLETE_HOLD': stop = 'FINITE_DUMP_LIMIT'; break
            if clock() >= next_resource:
                if storage_snapshot(folder)['status'] == 'INCOMPLETE_HOLD': stop = 'PRIVATE_STORAGE_LIMIT'; break
                if runtime.memory_available() < runtime.HOST_MARGIN: stop = 'PHYSICAL_HOST_MARGIN'; break
                next_resource = clock() + 1
            if clock() >= deadline: stop = 'UNCHANGED_SOFT_DEADLINE'; break
        if stop:
            stream.cancel(); result = stream.result(1)
            def released():
                work = observe(base, '/v1/telemetry')['work']
                return all(type(work.get(k)) is int and work[k] == 0 for k in ('active', 'queued', 'admission_reserved'))
            wait_for(released, 45, 'Owned cancellation retained private inference')
            result.update(intentional_budget_stop=True, incomplete_reason=stop, retry=False)
            return result
        result = stream.result(1)
        if (quality and dump_snapshot(folder)['status'] == 'INCOMPLETE_HOLD') or storage_snapshot(folder)['status'] == 'INCOMPLETE_HOLD':
            result.update(intentional_budget_stop=True, incomplete_reason='PRIVATE_STORAGE_LIMIT', retry=False)
        return result
    except BaseException as exc:
        exc.raw_transport = {k: getattr(stream, k, None) for k in ('status', 'error', 'events', 'raw', 'content', 'reasoning', 'finish_reason', 'done')}
        raise
    finally:
        if stream.thread.is_alive(): stream.cancel()


def score(case, response, proof, *, quality):
    n = proof['native']
    runtime.require(type(proof.get('observed_tokens')) is int and type(n.get('generated')) is int
                    and proof['observed_tokens'] == n['generated'], 'Native/emitted token count differs')
    if (response.get('status') != 200 or response.get('done') is not True or response.get('cancelled')
            or response.get('intentional_budget_stop') or response.get('budget_not_started')
            or response.get('finish_reason') != 'stop' or n.get('finish') != 'stop'):
        raise Incomplete('Wrong/cap/partial/UNRUN remains failed; no retry')
    if not 1 < proof['observed_tokens'] < case['request']['max_tokens']:
        raise Incomplete('Natural multi-token completion required')
    if case.get('expected_reuse') is not None:
        want = 0 if case['expected_reuse'] == 'zero' else case['prompt_tokens'] - 1
        if n['reused'] != want: raise Incomplete('Useful prefix state mismatch')
    if case['kind'] == 'json':
        try:
            actual = json.loads(response.get('content', ''), object_pairs_hook=typed_pairs,
                                parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        except (ValueError, TypeError): raise Incomplete('Invalid known-answer JSON') from None
        if json.dumps(actual, sort_keys=True, separators=(',', ':'), allow_nan=False) != json.dumps(case['expected'], sort_keys=True, separators=(',', ':')):
            raise Incomplete('Wrong typed known answer')
    if quality:
        for key in ('drafts_offered', 'drafts_accepted'):
            if type(n.get(key)) is not int or n[key] <= 0: raise Incomplete('Actual DSpark path not positively exercised')
    runtime.require(type(n.get('drafts_offered')) is int and type(n.get('drafts_accepted')) is int
                    and 0 <= n['drafts_accepted'] <= n['drafts_offered'], 'Actual draft counters inconsistent')
    for key in ('prompt_ms', 'decode_ms'):
        runtime.require(type(n.get(key)) in (int, float) and math.isfinite(n[key]) and n[key] >= 0, 'Finite actual timing required')
    if case['kind'] == 'prose' and case.get('expected_last_sentence'):
        if not response.get('content', '').strip().endswith(case['expected_last_sentence']):
            raise Incomplete('Required natural prose ending absent')
    native_rate = n['generated'] / (n['decode_ms'] / 1000) if n['decode_ms'] > 0 else None
    return {'id': case['id'], 'passed': True, 'native': n, 'observed_tokens': proof['observed_tokens'],
            'native_decode_tokens_per_second': native_rate, 'client_seconds': proof.get('client_full_s'),
            'content_characters': len(response.get('content', '')), 'reasoning_characters': len(response.get('reasoning', '')),
            'manual_review_pending': case['kind'] in ('code', 'prose'),
            'general_quality_or_equivalence_claim': False}


def run_cases(cases, folder, pid, deadline, *, issue, quality, dump_snapshot, dump_size,
              save_progress=lambda value: None):
    scores = [{'id': c['id'], 'passed': False, 'status': 'UNRUN'} for c in cases]; rows = []
    current = None; why = None
    try:
        for i, case in enumerate(cases):
            current = i; scores[i]['status'] = 'ISSUED_REVIEW_PENDING'
            save_progress({'scores': scores, 'rows': rows, 'complete': False, 'retry': False})
            response, proof = issue(case, folder, pid, deadline)
            row = score(case, response, proof, quality=quality); rows.append(row)
            scores[i].update(status='NATURAL_RESULT_SOURCE_AND_STATE_PASSED', passed=True)
            save_progress({'scores': scores, 'rows': rows, 'complete': False, 'retry': False})
        current = None
        if quality:
            if dump_snapshot(folder, complete=True)['status'] != 'COMPLETE_SIZE_ONLY': raise Incomplete('Complete four dump files required')
            for i, row in enumerate(rows, 1): row['dump_size_only'] = dump_size(Path(folder) / ('logits.%d.f32' % i))
    except Incomplete as exc:
        why = str(exc)
        if current is not None: scores[current].update(status='WRONG_CAP_PARTIAL_HOLD', reason=why)
    except BaseException as exc:
        if current is not None: scores[current].update(status='EXECUTION_FAULT_HOLD', reason=repr(exc))
        save_progress({'scores': scores, 'rows': rows, 'complete': False, 'retry': False, 'fault': repr(exc)})
        raise
    return {'complete': why is None and len(rows) == len(cases), 'rows': rows, 'scores': scores,
            'reason': why, 'retry': False, 'manual_review_required': True,
            'unrun_ids': [s['id'] for s in scores if s['status'] == 'UNRUN']}
