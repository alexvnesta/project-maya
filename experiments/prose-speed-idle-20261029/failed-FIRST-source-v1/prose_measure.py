"""Selected-hosted P0 prose, descriptive only. Never starts/stops a service/model.

Cooperative STATE reservation is optimistic compare/write/readback, not atomic
HTTP admission. Foreign demand cancels ONLY this process's captured socket.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import uuid

import transport

HERE = Path(__file__).resolve().parent
R = Path('/home/alex/strata-deepseek-test-20261024')
E = R / 'reliability-optimization-20261025'
EXPECTED = E / 'decode-optimization-20261028/prose-speed-v1'
BUILD = HERE.parent / 'iq2s-persistent-v1/iq2s_build.py'
BUILD_SHA = 'e8dcd79bd3a80cba931885149438f107d6d840693e508f738fd616fd6885f9ff'
SCOPE = 'SELECTED_HOSTED_PROSE_DESCRIPTIVE_ONLY'
NATIVE_SHA = '92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
CONFIG_SHA = 'c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'
PHASES = ('active_private_phase', 'active_GPU_phase', 'active_gpu_experiment', 'private_window',
          'active_cpu_build', 'production_restore_in_progress', 'production_verification_pending',
          'production_temporarily_stopped')
POLICY = {'model': 'deepseek-v4.1-flash-iq2-xs', 'stream': True, 'reasoning_effort': 100,
          'reasoning_budget_tokens': 0, 'temperature': 1.0, 'top_p': 1.0, 'seed': 1, 'max_tokens': 32768}
CASES = ('expository-prose', 'creative-prose')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def packed(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def real_directory(path):
    require(path.is_absolute() and '..' not in path.parts, 'Canonical directory required')
    for ancestor in [*reversed(path.parents), path]:
        require(not ancestor.is_symlink() and ancestor.is_dir(), 'Directory alias/missing ancestor')


def load(path):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 16 * 2**20,
            'Unsafe metadata file')
    return json.loads(path.read_text())


def emit(path, value):
    real_directory(path.parent)
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def fixtures(value):
    require(value.get('scope') == SCOPE and type(value.get('context')) is int and value['context'] == 1048576
            and type(value.get('output_allowance')) is int and value['output_allowance'] == 262144, 'Wrong model/limits/scope')
    require(packed(value.get('policy')) == packed(POLICY), 'Policy changed')
    require(value.get('prior_numerical_HOLD') is True and value.get('candidate_allowed') is False
            and value.get('promotion_allowed') is False and value.get('case_retry_allowed') is False,
            'Diagnostic restrictions changed')
    require([c['id'] for c in value['cases']] == list(CASES), 'Exact two fixtures required')
    for case in value['cases']:
        request = case['request']
        require(set(request) == set(POLICY) | {'messages'} and packed({k: request[k] for k in POLICY}) == packed(POLICY),
                'Request settings differ')
        messages = request['messages']
        require(type(messages) is list and len(messages) == 1 and set(messages[0]) == {'role', 'content'}
                and messages[0]['role'] == 'user' and type(messages[0]['content']) is str
                and messages[0]['content'], 'Synthetic text fixture required')
        require(case.get('length_is_observed_not_fitted') is True and type(case.get('expected_last_sentence')) is str,
                'Manual prose criteria required')
    return value


def encoded_fixture(value, original):
    fixtures(value)
    require(value.get('CPU_only') is True, 'Real CPU-only encoding proof required')
    for case, source in zip(value['cases'], original['cases']):
        require(packed(case['request']) == packed(source['request']), 'Encoded request differs')
        ids = case['prompt_ids']
        require(type(ids) is list and all(type(n) is int and n >= 0 for n in ids)
                and type(case.get('prompt_tokens')) is int and case['prompt_tokens'] == len(ids)
                and 64 <= len(ids) <= 1024, 'Frozen input bounds; no automatic resizing')
    return value


def support():
    require(sha(BUILD) == BUILD_SHA, 'Read-only support source differs')
    prior = sys.modules.get('iq2s_build')
    require(prior is None or Path(prior.__file__).resolve() == BUILD, 'Foreign helper origin')
    sys.path.insert(0, str(BUILD.parent))
    c = importlib.import_module('iq2s_build')
    b, runtime, a, host, binding = c.support()
    return c, b, runtime, host, binding


def cpu_contract(receipt, child, q, label):
    require(label in ('darwin', 'linux'), 'Physical host label required')
    require(receipt.get('passed') is True and type(receipt.get('controls')) is int
            and receipt['controls'] == len(q['test_ids']) and receipt.get('test_ids') == q['test_ids']
            and receipt.get('source_sha256') == q['source_sha256']
            and receipt.get('source_input_sha256') == q['source_input_sha256'], 'Exact CPU proof differs')
    require(receipt.get('GPU_execution') is False and receipt.get('native_execution') is False
            and receipt.get('compiler_execution') is False, 'Non-CPU proof refused')
    expected = {'returncode': 0, 'CPU_s': 30, 'wall_s': 90, 'nice': 15, 'CUDA_hidden': True,
                'Linux_AS_MiB': 512 if label == 'linux' else None}
    require(all(type(child.get(k)) is type(v) and child[k] == v for k, v in expected.items())
            and child.get('error') is None and child.get('cleanup_errors') == [], 'CPU bounds/cleanup')


def qualified(qpath, digest):
    require(qpath == HERE / 'qualification.json' and sha(qpath) == digest, 'Exact qualification required')
    q = load(qpath)
    require(q.get('scope') == SCOPE and q.get('manual_source_reviewed') is True
            and q.get('CPU_both_hosts_passed') is True and q.get('prior_numerical_HOLD') is True,
            'Manual source/CPU closure absent')
    inherited = HERE.parent / 'iq2s-persistent-v1/model-v1/numerical-qualification.json'
    require(q['files'].get(str(inherited)) == '11deaac7b10b7d53bd988acff210136b5e2107d533d1a13e28c315037810113e'
            and sha(inherited) == q['files'][str(inherited)], 'Qualified helper closure absent')
    require(all(q['files'].get(name) == pin for name, pin in load(inherited)['files'].items()
                if name.endswith('.py')), 'Inherited Python import closure incomplete')
    live = Path('/home/alex/deepseek-hosted-20261025')
    require(q['files'].get(str(live / 'bin/maya-ds4')) == NATIVE_SHA
            and q['files'].get(str(live / 'config.json')) == CONFIG_SHA
            and q['files'].get(str(live / 'runtime-native-vision-v2/serve/server.py')) ==
            'b1be40294f6c49692829ad5f85a7aa2867218180fdc8fbc9bef7710371ba3b9f', 'Selected native/config/API pins absent')
    require(Path(transport.__file__).resolve() == HERE / 'transport.py', 'Foreign transport import')
    sources = q['source_sha256']
    require(set(sources) == {'prose_measure.py', 'test_prose_measure.py', 'transport.py', 'test_transport.py',
                            'qualify_prose_cpu.py', 'test_qualify_prose_cpu.py'}, 'Exact new source inventory')
    for name, pin in q['files'].items():
        path = Path(name)
        require(path.is_absolute() and '..' not in path.parts and sha(path) == pin, 'Qualification input changed')
    for name, pin in sources.items():
        require(q['files'].get(str(HERE / name)) == pin and sha(HERE / name) == pin, 'Source custody')
    ids = q['test_ids']
    require(type(ids) is list and ids and len(ids) == len(set(ids)), 'Test ID inventory')
    for label in ('darwin', 'linux'):
        folder = HERE / ('prose-CPU-FIRST-' + label)
        for name in ('receipt.json', 'child.json', 'child.log', 'encoded-fixture.json'):
            require(q['files'].get(str(folder / name)) == sha(folder / name), 'CPU raw proof unpinned')
        receipt, child = load(folder / 'receipt.json'), load(folder / 'child.json')
        cpu_contract(receipt, child, q, label)
    left = HERE / 'prose-CPU-FIRST-darwin/encoded-fixture.json'
    right = HERE / 'prose-CPU-FIRST-linux/encoded-fixture.json'
    require(sha(left) == sha(right), 'Both-host real encoding differs')
    original = HERE / 'prose-fixtures.json'
    require(q['files'].get(str(original)) == sha(original), 'Fixture not pinned')
    encoded_fixture(load(left), fixtures(load(original)))
    require(q['files'].get(str(BUILD)) == BUILD_SHA and sha(qpath) == digest, 'Import/q custody changed')
    return q


def cas_state(path, before, after):
    """Optimistic cooperative CAS: other writers must honor the same reservation."""
    require(not path.is_symlink() and path.read_bytes() == before, 'STATE changed before write')
    temp = path.with_name(path.name + '.prose-' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('xb') as stream:
            stream.write(packed(after) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        require(path.read_bytes() == before, 'STATE changed during preparation')
        os.replace(temp, path)
        require(packed(load(path)) == packed(after), 'STATE write/readback conflict')
    finally:
        if temp.exists():
            temp.unlink()


def claim(path, record):
    require(not path.is_symlink(), 'STATE alias refused')
    before = path.read_bytes()
    value = json.loads(before)
    require(not any(value.get(k) for k in PHASES) and not value.get('prose_speed_current', {}).get('active'),
            'Foreign phase/reservation')
    value['prose_speed_current'] = dict(record, active=True)
    value['active_gpu_experiment'] = record
    cas_state(path, before, value)


def release(path, record):
    require(not path.is_symlink(), 'STATE alias refused')
    before = path.read_bytes()
    value = json.loads(before)
    require(value.get('active_gpu_experiment') == record
            and value.get('prose_speed_current') == dict(record, active=True), 'Foreign/missing reservation; untouched')
    value['active_gpu_experiment'] = False
    value['prose_speed_current'] = dict(record, active=False)
    cas_state(path, before, value)
    require(load(path).get('active_gpu_experiment') is False, 'Own release unverified')


def held_production_lock(path):
    import fcntl
    require(path.is_file() and not path.is_symlink(), 'Existing production lock absent')
    with path.open('rb') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        fcntl.flock(stream, fcntl.LOCK_UN)
        raise ValueError('Production lock unexpectedly unheld; no inference')


def process_identity(binding, proc=Path('/proc')):
    base = proc / str(binding['native_pid'])
    stat = (base / 'stat').read_text()
    ticks = int(stat.rsplit(') ', 1)[1].split()[19])
    env = (base / 'environ').read_bytes()
    require(len(env) <= 2**20, 'Process environment oversized')
    invocation = [v.split(b'=', 1)[1].decode() for v in env.split(b'\0') if v.startswith(b'INVOCATION_ID=')]
    require(invocation == [binding['invocation']] and ticks == binding['native_start_ticks'], 'Native owner changed')
    # No environment contents are persisted. Exact cmdline/cgroup equality is checked
    # against the initial current-owner snapshot on every lightweight observation.
    return {'ticks': ticks, 'invocation': invocation[0], 'exe': os.readlink(base / 'exe'),
            'cmdline_bytes': (base / 'cmdline').read_bytes(),
            'cgroup': (base / 'cgroup').read_text(), 'main_exists': (proc / str(binding['main_pid'])).is_dir()}


def observe(get=transport.get_json):
    native = get(18141, '/v1/telemetry')
    router = get(8012, '/health')
    work, activity, switcher = native['work'], native['activity'], router['switcher']
    # Drop all content/history and unrelated telemetry before persistence.
    return {'instance': {'id': native['instance']['id'], 'state': native['instance']['state']},
            'work': {**{k: work.get(k) for k in ('active', 'queued', 'admission_reserved', 'requests_omitted')},
                     'requests': [{'id': r['id'], 'state': r['state']} for r in work['requests']]},
            'activity': {'last_seq': activity['last_seq'],
                         'events': [{k: r[k] for k in ('seq', 'request_id', 'event', 'outcome') if k in r}
                                    for r in activity['events']]},
            'router': {**{k: switcher.get(k) for k in ('active_model', 'default_model', 'inflight', 'waiting', 'fault')},
                       'status': router.get('status'), 'busy': router.get('busy')}}


def nint(value):
    return type(value) is int and value >= 0


def idle_snapshot(value):
    work, router = value['work'], value['router']
    require(value['instance']['state'] == 'ready' and type(value['instance']['id']) is str, 'API not ready')
    require(router['status'] == 'ok' and router['active_model'] == router['default_model'] == 'deepseek'
            and not router['fault'], 'Default router unavailable')
    require(all(nint(router[k]) and router[k] == 0 for k in ('inflight', 'waiting'))
            and router['busy'] is False, 'DEFERRED_BUSY_UNTOUCHED')
    require(all(nint(work[k]) and work[k] == 0 for k in ('active', 'queued', 'admission_reserved', 'requests_omitted'))
            and work['requests'] == [], 'DEFERRED_BUSY_UNTOUCHED')
    require(nint(value['activity']['last_seq']), 'Missing activity cursor')


class Epoch:
    def __init__(self, baseline):
        idle_snapshot(baseline)
        self.instance = baseline['instance']['id']
        self.cursor = baseline['activity']['last_seq']
        self.start_cursor = self.cursor
        self.ids = set()
        self.terminal = set()

    def update(self, value):
        require(value['instance'] == {'id': self.instance, 'state': 'ready'}, 'API identity/state changed')
        activity, work = value['activity'], value['work']
        last = activity['last_seq']
        require(nint(last) and 0 <= last - self.cursor <= 32, 'Activity cursor reset/gap/overrun')
        events = [r for r in activity['events'] if nint(r.get('seq')) and r['seq'] > self.cursor]
        require([r['seq'] for r in events] == list(range(self.cursor + 1, last + 1)), 'Activity gap/overrun/duplicate')
        for row in events:
            request_id = row['request_id']
            require(type(request_id) is str and re.fullmatch('[0-9a-f]{12}', request_id), 'Internal ID shape')
            self.ids.add(request_id)
            if row['event'] in ('finished', 'cancelled', 'disconnected', 'timeout', 'error'):
                self.terminal.add(request_id)
        self.cursor = last
        require(work.get('requests_omitted') == 0 and type(work.get('requests_omitted')) is int, 'Omitted requests')
        for row in work['requests']:
            require(type(row['id']) is str and re.fullmatch('[0-9a-f]{12}', row['id']), 'Live ID shape')
            self.ids.add(row['id'])
        return value

    def safe(self, value):
        self.update(value)
        router, work = value['router'], value['work']
        require(router['status'] == 'ok' and router['active_model'] == router['default_model'] == 'deepseek'
                and not router['fault'] and all(nint(router[k]) and router[k] == 0 for k in ('inflight', 'waiting')),
                'FOREIGN_ROUTER_DEMAND')
        # Router.busy includes our native request, so it is NOT a foreign-work bit.
        require(all(nint(work[k]) and work[k] <= 1 for k in ('active', 'queued', 'admission_reserved'))
                and work['active'] + work['queued'] <= 1 and len(self.ids) <= 1
                and len(work['requests']) <= 1, 'FOREIGN_OR_AMBIGUOUS_NATIVE_DEMAND')

    def receipt(self, value):
        return {**value, 'activity': {**value['activity'], 'events': [r for r in value['activity']['events']
                if r['seq'] > self.start_cursor]}}

    def released(self, value):
        self.update(value)
        return (len(self.ids) == 1 and self.ids <= self.terminal
                and not (self.ids & {r['id'] for r in value['work']['requests']}))


def swap_pages(path=Path('/proc/vmstat')):
    values = dict(line.split() for line in path.read_text().splitlines())
    value = int(values['pswpout'])
    require(value >= 0, 'Swap counter invalid')
    return value


def resource_check(output, initial_swap, *, disk=shutil.disk_usage, swap=swap_pages):
    require(disk('/').free >= 120 * 2**30, 'Root120 floor')
    delta = swap() - initial_swap
    require(0 <= delta * 4096 < 2**30, 'Swap reset/budget')
    total = 0
    for folder, dirs, names in os.walk(output, followlinks=False):
        for name in dirs + names:
            path = Path(folder) / name
            require(not path.is_symlink(), 'Output link refused')
        total += sum((Path(folder) / name).stat().st_size for name in names)
    require(total < 4 * 2**30, 'Owned log budget')
    return {'root_free_bytes': disk('/').free, 'swap_delta_bytes': delta * 4096, 'owned_log_bytes': total}


def own_history(request_id, get=transport.get_json):
    # Read redacted history only; never request /api/requests or persist other rows.
    value = get(18141, '/metrics')
    rows = [r for r in value.get('requests', []) if r.get('id') == request_id]
    require(len(rows) == 1, 'Own redacted native history absent/ambiguous')
    keys = ('id', 'finish', 'prompt_tokens', 'reused', 'output_tokens', 'engine_generated',
            'prompt_total', 'prompt_read', 'prompt_ms', 'decode_ms', 'hit_rate', 'drafts_offered', 'drafts_accepted',
            'reasoning_recoveries', 'first_engine_token_s')
    return {key: rows[0].get(key) for key in keys}


def metrics(result, native):
    timing, usage = result['timings'], result['usage']
    require(type(timing) is dict and type(usage) is dict, 'Missing own timing/usage')
    for key in ('predicted_n', 'prompt_n', 'cache_n', 'draft_n', 'draft_n_accepted'):
        require(nint(timing.get(key)), 'Missing typed native timing counter: ' + key)
    require(timing['draft_n_accepted'] <= timing['draft_n'], 'Draft counters inconsistent')
    for key in ('predicted_ms', 'prompt_ms', 'predicted_per_second'):
        require(transport.finite(timing.get(key)) and timing[key] >= 0, 'Invalid timing')
    require(timing['predicted_ms'] > 0 and timing['predicted_n'] > 0, 'No useful decode')
    require(type(usage.get('completion_tokens')) is int and usage['completion_tokens'] == timing['predicted_n'],
            'API generated counters disagree')
    require(native.get('finish') == 'stop' and type(native.get('reasoning_recoveries')) is int
            and native['reasoning_recoveries'] == 0, 'Native continuation scope not qualified')
    for key in ('engine_generated', 'drafts_offered', 'drafts_accepted', 'prompt_tokens', 'reused'):
        require(nint(native.get(key)), 'Missing own native counter: ' + key)
    require(native['engine_generated'] > 0 and transport.finite(native.get('decode_ms'))
            and native['decode_ms'] > 0 and native['drafts_accepted'] <= native['drafts_offered'],
            'Invalid native decode/drafts')
    require(nint(native.get('prompt_total')) and native['prompt_tokens'] == native['prompt_total'],
            'Natural prompt total differs')
    read = native.get('prompt_read')
    require(read is None or (nint(read) and read <= native['prompt_total']), 'Native prompt-read scope')
    effective_cache = max(native['reused'], max(0, native['prompt_tokens'] - read)) if read is not None else native['reused']
    require(native.get('output_tokens') == timing['predicted_n'] and type(native.get('output_tokens')) is int
            and native['drafts_offered'] == timing['draft_n'] and native['drafts_accepted'] == timing['draft_n_accepted']
            and native['prompt_tokens'] == timing['prompt_n'] + timing['cache_n']
            and effective_cache == timing['cache_n']
            and round(native['decode_ms'], 1) == timing['predicted_ms']
            and round(native['engine_generated'] / (native['decode_ms'] / 1000), 1) == timing['predicted_per_second'],
            'Own native/SSE counters disagree; no rate qualification')
    require(native['hit_rate'] is None or (transport.finite(native['hit_rate']) and 0 <= native['hit_rate'] <= 1),
            'Invalid rounded hit rate')
    return {'api_generated_tokens': timing['predicted_n'], 'native_decode_ms_rounded': timing['predicted_ms'],
            'native_reported_tokens_per_second_rounded': timing['predicted_per_second'],
            'exact_native_generated_tokens': native['engine_generated'], 'exact_native_decode_ms': native['decode_ms'],
            'exact_native_tokens_per_second': native['engine_generated'] / (native['decode_ms'] / 1000),
            'native_count_scope': 'Unique redacted terminal-ID history row; zero reasoning recoveries',
            'expert_hit_rate_rounded': native['hit_rate'],
            'prefill_ms_rounded': timing['prompt_ms'], 'prompt_read': timing['prompt_n'], 'prompt_reused': timing['cache_n'],
            'drafts_offered': timing['draft_n'], 'drafts_accepted': timing['draft_n_accepted'],
            'raw_expert_hits': None, 'raw_expert_lookups': None,
            'client_full_seconds': result['client_full_seconds'],
            'buffered_first_visible_seconds': result['buffered_first_visible_seconds'], 'true_TTFT': None}


def measure_case(case, *, stream_factory=transport.Stream, observe_fn=observe, lightweight=lambda: None,
                 deadline, cleanup_deadline, history_fn=own_history, clock=time.monotonic, sleep=time.sleep):
    baseline = observe_fn()
    epoch = Epoch(baseline)
    lightweight()
    require(clock() < deadline, 'UNRUN soft deadline')
    # Recheck immediately before own POST. There is deliberately no claim of atomic admission.
    epoch.safe(observe_fn())
    require(not epoch.ids, 'UNRUN request raced admission')
    stream = stream_factory(case['request'])
    primary = None
    cleanup_errors = []
    released = False
    observations = []
    try:
        stream.start()
        while True:
            require(clock() < deadline, 'PARTIAL soft deadline')
            lightweight()
            row = observe_fn()
            epoch.safe(row)
            observations.append(epoch.receipt(row))
            if stream.finished.is_set():
                result = stream.result()
                if epoch.released(row):
                    released = True
                    break
            sleep(.1)
        require(clock() < deadline, 'PARTIAL soft deadline before metadata')
        native = history_fn(next(iter(epoch.ids)))
        if 'prompt_tokens' in case:
            require(native.get('prompt_total') == case['prompt_tokens'], 'Encoded prompt total changed')
        lightweight()
        after_history = observe_fn()
        epoch.safe(after_history)
        observations.append(epoch.receipt(after_history))
        require(clock() < deadline, 'PARTIAL soft deadline after metadata')
        require(epoch.released(after_history), 'Own request release changed')
        value = {'id': case['id'], 'status': 'NATURAL_COMPLETION_MANUAL_REVIEW_PENDING',
                 'result': result, 'metrics': metrics(result, native), 'own_native_history': native, 'unique_internal_id': next(iter(epoch.ids)),
                 'attribution': 'Unique uncontended redacted epoch; not HTTP ID echo', 'own_release_verified': True,
                 'last_sentence_matches': result['content'].rstrip().endswith(case['expected_last_sentence']),
                 'observed_words': len(result['content'].split()), 'manual_quality_passed': False,
                 'prior_numerical_HOLD': True, 'promotion_allowed': False, 'retry_allowed': False}
    except BaseException as exc:
        primary = repr(exc)
        cleanup_deadline = min(cleanup_deadline, clock() + 200)
        try:
            stream.cancel(timeout=min(3, max(.01, cleanup_deadline - clock())))
        except BaseException as cleanup:
            cleanup_errors.append(repr(cleanup))
        # No global-idle wait: other users may be active. Ambiguous IDs cannot prove own release.
        while clock() < cleanup_deadline and len(epoch.ids) <= 1 and not released:
            try:
                released = epoch.released(observe_fn())
            except BaseException as cleanup:
                cleanup_errors.append(repr(cleanup))
                break
            if not released:
                sleep(.1)
        value = {'id': case['id'], 'status': 'INCOMPLETE_HOLD_NO_RETRY', 'primary_error': primary,
                 'cleanup_errors': cleanup_errors, 'partial': stream.partial(), 'own_release_verified': False, 'unique_epoch_terminal_observed': released,
                 'release_scope': 'Cancelled/ambiguous request: joined own reader only; no own-ID assertion',
                 'manual_quality_passed': False, 'prior_numerical_HOLD': True, 'promotion_allowed': False,
                 'retry_allowed': False}
    value['observations'] = observations
    return value


def panel(cases, folder, **kwargs):
    results = []
    stopped = False
    for case in cases:
        if stopped:
            value = {'id': case['id'], 'status': 'UNRUN', 'retry_allowed': False}
        else:
            try:
                value = measure_case(case, **kwargs)
            except BaseException as exc:
                value = {'id': case['id'], 'status': 'UNRUN_HOLD_NO_RETRY', 'primary_error': repr(exc), 'retry_allowed': False}
            stopped = value['status'] != 'NATURAL_COMPLETION_MANUAL_REVIEW_PENDING'
        emit(folder / (case['id'] + '.json'), value)
        results.append(value)
    return results


def run(host, runtime, binding, qdigest, admission, *, clock=time.monotonic):
    state_path = E / 'STATE.json'
    output = HERE / 'P0-FIRST'
    real_directory(HERE)
    require(not output.exists() and not output.is_symlink(), 'P0 already attempted; no replay')
    require(shutil.disk_usage('/').free >= 132 * 2**30, 'Root132 floor')
    idle_snapshot(observe())
    host.guard_binding()
    held_production_lock(R / 'experiment.lock')
    record = {'pid': os.getpid(), 'mode': SCOPE, 'output': str(output), 'qualification_sha256': qdigest,
              'nonce': uuid.uuid4().hex, 'start_binding': binding}
    primary = None
    release_error = None
    post_owner_error = None
    created = False
    summary = None
    try:
        require(runtime.current_binding(load(state_path)) == binding, 'Selected binding changed before claim')
        claim(state_path, record)
        output.mkdir()
        created = True
        emit(output / 'attempt.json', record)
        before_proc = process_identity(binding)
        require(before_proc['main_exists'], 'Selected main disappeared')
        first_swap = swap_pages()
        start = clock()
        def lightweight():
            state = load(state_path)
            require(state.get('active_gpu_experiment') == record
                    and state.get('prose_speed_current') == dict(record, active=True), 'Reservation changed')
            require(not any(state.get(k) for k in PHASES if k != 'active_gpu_experiment'), 'Foreign phase')
            require(runtime.current_binding(state) == binding and process_identity(binding) == before_proc,
                    'Selected identity changed')
            resource_check(output, first_swap)
        fixture = encoded_fixture(load(HERE / 'prose-CPU-FIRST-darwin/encoded-fixture.json'),
                                  fixtures(load(HERE / 'prose-fixtures.json')))
        results = panel(fixture['cases'], output, lightweight=lightweight, deadline=start + 1000,
                        cleanup_deadline=start + 1200, clock=clock)
        lightweight()
        summary = {'scope': SCOPE, 'status': 'P0_TERMINAL_MANUAL_REVIEW_PENDING', 'results': results,
                   'before_binding': binding, 'after_binding': binding, 'same_process_observed': True,
                   'resources': resource_check(output, first_swap), 'source_cpu_only_not_quality': True,
                   'prior_numerical_HOLD': True, 'promotion_allowed': False, 'native_restarts': 0,
                   'latency_scope': 'Direct native API, not public router end-to-end',
                   'atomic_idle_admission': False, 'user_priority': 'Best effort own-socket cancellation'}
    except BaseException as exc:
        primary = repr(exc)
    finally:
        try:
            current = load(state_path)
            if current.get('active_gpu_experiment') == record or current.get('prose_speed_current') == dict(record, active=True):
                release(state_path, record)
            else:
                raise ValueError('Own reservation not retained; no foreign state cleanup')
        except BaseException as exc:
            release_error = repr(exc)
        try:
            host.guard_binding()  # metadata only; never requires global idle after our request
            require(runtime.current_binding(load(state_path)) == binding, 'Post-request canonical owner changed')
        except BaseException as exc:
            post_owner_error = repr(exc)
        if created and not output.is_symlink() and output.is_dir():
            emit(output / 'controller-result.json', {'summary': summary, 'primary_error': primary,
                 'reservation_release_error': release_error, 'post_owner_error': post_owner_error, 'retry_allowed': False,
                 'own_reservation_released': release_error is None})
    require(primary is None and release_error is None and post_owner_error is None,
            'P0 HOLD: ' + repr((primary, release_error, post_owner_error)))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qualification-sha256', required=True)
    parser.add_argument('--admission-sha256')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    require(HERE == EXPECTED, 'Exact hosted source namespace required')
    c, b, runtime, host, binding = support()
    c.guard(runtime, host, binding)  # before full closure hashing/output or request
    q = qualified(HERE / 'qualification.json', args.qualification_sha256)
    c.guard(runtime, host, binding)
    idle_snapshot(observe())
    held_production_lock(R / 'experiment.lock')
    previous = Path(host.previous())
    require(previous.parent == R / 'windows' and not previous.is_symlink(), 'Canonical previous window required')
    if not args.run:
        print(json.dumps({'status': 'READ_ONLY_PREFLIGHT_PASS', 'binding': binding,
                          'qualification_sha256': args.qualification_sha256, 'model_request': False,
                          'previous_window_path': str(previous), 'previous_window_sha256': sha(previous),
                          'previous_telemetry_sha256': sha(previous.with_suffix('.telemetry.jsonl'))}, sort_keys=True))
        return
    path = HERE / 'admission.json'
    require(args.admission_sha256 and sha(path) == args.admission_sha256, 'Separate exact admission required')
    admission = load(path)
    require(admission.get('decision') == 'CONDITIONAL_SINGLE_P0_HOSTED_PROSE_ONLY'
            and admission.get('qualification_sha256') == args.qualification_sha256
            and admission.get('binding') == binding, 'Admission scope/owner mismatch')
    require(type(admission.get('kernel_since')) is str and admission['kernel_since']
            and admission.get('previous_window_path') == str(previous)
            and admission.get('previous_window_sha256') == sha(previous)
            and admission.get('previous_telemetry_sha256') == sha(previous.with_suffix('.telemetry.jsonl')),
            'Kernel/exact previous-window gate missing')
    host.kernel(admission['kernel_since'])
    c.guard(runtime, host, binding)
    result = run(host, runtime, binding, args.qualification_sha256, admission)
    print(json.dumps({'status': result['status'], 'output': str(HERE / 'P0-FIRST'),
                      'same_process_observed': result['same_process_observed'],
                      'prior_numerical_HOLD': True, 'promotion_allowed': False}, sort_keys=True))


if __name__ == '__main__':
    main()
