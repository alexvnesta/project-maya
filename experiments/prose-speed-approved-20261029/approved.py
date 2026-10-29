"""One newly authorized hosted panel. No cancellation for competing demand.

Same selected model and policy; normal FIFO, no service/settings changes.
Old P0 remains closed. Report only the server's rounded native rate.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'prose-speed-v1'
PINS = {'transport.py': 'cd026ab8cc86228500f606efb0913e55a63ba89b4e55fbfc33707b18c595bf37',
        'prose_measure.py': '8d10d003bbbd7ffbb87251bacdf53d91af9f074151d34f06c957fa179f3108cf',
        'prose-fixtures.json': '8039ba7415335710ab481c5cd29f3c2c1bffb19b223d83ec586baf759a336faf'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def helpers():
    for name, pin in PINS.items():
        require(sha(OLD / name) == pin, 'Original qualified helper/fixture changed')
    sys.path.insert(0, str(OLD))
    m = importlib.import_module('prose_measure')
    require(Path(m.__file__).resolve() == OLD / 'prose_measure.py', 'Foreign helper')
    require(Path(m.transport.__file__).resolve() == OLD / 'transport.py', 'Foreign transport')
    return m


def rates(result, finite):
    require(result['done'] is True and result['finish_reason'] == 'stop', 'Incomplete prose')
    t, u = result['timings'], result['usage']
    require(type(t) is dict and type(u) is dict, 'Missing own timing/usage')
    for key in ('predicted_n', 'prompt_n', 'cache_n', 'draft_n', 'draft_n_accepted'):
        require(type(t.get(key)) is int and t[key] >= 0, 'Missing typed counter')
    require(t['predicted_n'] > 0 and t['draft_n_accepted'] <= t['draft_n'], 'Invalid generation/drafts')
    require(type(u.get('completion_tokens')) is int and u['completion_tokens'] == t['predicted_n'], 'API count mismatch')
    for key in ('predicted_ms', 'prompt_ms', 'predicted_per_second'):
        require(finite(t.get(key)) and t[key] >= 0, 'Invalid reported timing')
    require(t['predicted_ms'] > 0 and t['predicted_per_second'] > 0, 'No measured generation')
    return {'server_reported_rounded_native_tokens_per_second': t['predicted_per_second'],
            'rate_scope': 'Server native counter rate rounded to0.1; includes reasoning',
            'API_generated_tokens': t['predicted_n'], 'exact_native_generated_tokens': None,
            'decode_ms_rounded': t['predicted_ms'], 'prefill_ms_rounded': t['prompt_ms'],
            'prompt_read': t['prompt_n'], 'cache_tokens': t['cache_n'],
            'drafts_offered': t['draft_n'], 'drafts_accepted': t['draft_n_accepted'],
            'client_full_seconds': result['client_full_seconds'], 'true_TTFT': None,
            'exact_expert_hits': None, 'exact_expert_lookups': None}


def sample(case, *, factory, check, deadline, finite, clock=time.monotonic):
    stream = factory(case['request'])
    try:
        require(clock() < deadline, 'UNRUN deadline')
        check()
        stream.start()
        while not stream.finished.wait(.1):
            require(clock() < deadline, 'PARTIAL deadline')
            check()
        check()
        require(clock() < deadline, 'PARTIAL deadline at completion')
        result = stream.result()
        require(result.get('model') == case['request']['model'], 'Returned model differs')
        return {'id': case['id'], 'status': 'COMPLETE_MANUAL_REVIEW_PENDING',
                'result': result, 'metrics': rates(result, finite),
                'words': len(result['content'].split()),
                'last_sentence_matches': result['content'].rstrip().endswith(case['expected_last_sentence']),
                'manual_quality_passed': False, 'retry': False}
    except BaseException as exc:
        cleanup = []
        try:
            stream.cancel(timeout=3)
        except BaseException as secondary:
            cleanup.append(repr(secondary))
        return {'id': case['id'], 'status': 'INCOMPLETE_HOLD', 'error': repr(exc),
                'cleanup_errors': cleanup, 'partial': stream.partial(), 'retry': False}


def panel(cases, out, emit, **kwargs):
    rows = []
    for case in cases:
        if rows and rows[-1]['status'] != 'COMPLETE_MANUAL_REVIEW_PENDING':
            row = {'id': case['id'], 'status': 'UNRUN', 'retry': False}
        else:
            row = sample(case, **kwargs)
        emit(out / (case['id'] + '.json'), row)
        rows.append(row)
    return rows


def qualify(m, digest):
    path = HERE / 'qualification.json'
    require(sha(path) == digest, 'Qualification changed')
    q = m.load(path)
    require(q.get('source_read') is True and q.get('both_CPU_passed') is True, 'Source/CPU qualification missing')
    require(q['source_sha256'] == {n: sha(HERE / n) for n in ('approved.py', 'test_approved.py')}, 'New source changed')
    require(all(q['files'].get(str(HERE / n)) == pin for n, pin in q['source_sha256'].items()), 'Source absent from closure')
    for name, pin in q['files'].items():
        require(Path(name).is_absolute() and '..' not in Path(name).parts and sha(name) == pin, 'Pinned input changed')
    live = Path('/home/alex/deepseek-hosted-20261025')
    require(q['files'].get(str(live / 'bin/maya-ds4')) == m.NATIVE_SHA
            and q['files'].get(str(live / 'config.json')) == m.CONFIG_SHA
            and q['files'].get(str(live / 'runtime-native-vision-v2/serve/server.py')) ==
            'b1be40294f6c49692829ad5f85a7aa2867218180fdc8fbc9bef7710371ba3b9f', 'Wrong selected model/API')
    for label in ('darwin', 'linux'):
        folder = HERE / ('CPU-v2-' + label)
        child, receipt = m.load(folder / 'child.json'), m.load(folder / 'receipt.json')
        for name in ('child.json', 'receipt.json', 'child.log'):
            require(q['files'].get(str(folder / name)) == sha(folder / name), 'CPU raw missing')
        expected = {'returncode': 0, 'CPU_s': 30, 'wall_s': 90, 'nice': 15, 'CUDA_hidden': True,
                    'Linux_AS_MiB': 512 if label == 'linux' else None}
        require(all(type(child.get(k)) is type(v) and child[k] == v for k, v in expected.items())
                and child.get('error') is None and child.get('cleanup_errors') == [], 'CPU supervision incomplete')
        require(receipt.get('passed') is True and receipt['source_sha256'] == q['source_sha256']
                and receipt['test_ids'] == q['test_ids'] and type(receipt['controls']) is int
                and receipt['controls'] == len(q['test_ids']), 'CPU source/IDs differ')
    return q


def with_custody(m, host, record, out, body):
    """A partially written claim is still ours to release; never clear foreign state."""
    primary = release_error = owner_error = None
    claimed = created = False
    try:
        m.claim(m.E / 'STATE.json', record)
        claimed = True
        out.mkdir()
        created = True
        m.emit(out / 'attempt.json', record)
        body()
    except BaseException as exc:
        primary = repr(exc)
    finally:
        try:
            current = m.load(m.E / 'STATE.json')
            if current.get('active_gpu_experiment') == record and current.get('prose_speed_current') == dict(record, active=True):
                m.release(m.E / 'STATE.json', record)
            elif claimed:
                raise ValueError('Own reservation changed; foreign state preserved')
        except BaseException as exc:
            release_error = repr(exc)
        try:
            host.guard_binding()
        except BaseException as exc:
            owner_error = repr(exc)
        if created:
            m.emit(out / 'cleanup.json', {'primary_error': primary, 'release_error': release_error,
                   'owner_error': owner_error, 'retry': False})
    require(primary is None and release_error is None and owner_error is None,
            'Owned panel HOLD: ' + repr((primary, release_error, owner_error)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qualification-sha256', required=True)
    parser.add_argument('--admission-sha256', required=True)
    args = parser.parse_args()
    m = helpers()
    c, _, runtime, host, binding = m.support()
    state = m.load(m.E / 'STATE.json')
    require(runtime.phase_keys_free(state), 'Another phase/build/restoration')
    host.guard_binding()
    qualify(m, args.qualification_sha256)
    a = HERE / 'admission.json'
    require(sha(a) == args.admission_sha256, 'Admission changed')
    admission = m.load(a)
    require(admission['decision'] == 'APPROVED_SINGLE_P1_PROSE_PANEL'
            and admission['qualification_sha256'] == args.qualification_sha256
            and admission['binding'] == binding and admission['interrupt_permission'] is True, 'Wrong fresh authorization')
    require(__import__('shutil').disk_usage('/').free >= 132 * 2**30, 'Root132 floor')
    host.previous()
    host.kernel(admission['kernel_since'])
    out = HERE / 'P1-FIRST'
    require(not out.exists() and not out.is_symlink(), 'P1 already attempted')
    record = {'pid': os.getpid(), 'nonce': os.urandom(16).hex(), 'scope': 'APPROVED_SELECTED_PROSE_P1',
              'output': str(out), 'start_binding': binding}
    def body():
        proc = m.process_identity(binding)
        swap = m.swap_pages()
        def check():
            current = m.load(m.E / 'STATE.json')
            require(current.get('active_gpu_experiment') == record and runtime.current_binding(current) == binding,
                    'Own custody lost')
            require(not any(current.get(k) for k in m.PHASES if k != 'active_gpu_experiment'), 'Conflicting phase')
            require(m.process_identity(binding) == proc, 'Selected owner changed')
            m.resource_check(out, swap)
        fixture = m.fixtures(m.load(OLD / 'prose-fixtures.json'))
        start = time.monotonic()
        rows = panel(fixture['cases'], out, m.emit, factory=m.transport.Stream, check=check,
                     deadline=start + 1000, finite=m.transport.finite)
        check()
        m.emit(out / 'summary.json', {'rows': rows, 'binding': binding, 'native_restarts': 0,
               'quality_settings_changed': False, 'resources': m.resource_check(out, swap),
               'competition_cancellation_disabled_by_explicit_user_approval': True,
               'normal_FIFO_queue_time_in_client_latency': True, 'prior_P0_unchanged': True})
    with_custody(m, host, record, out, body)


if __name__ == '__main__':
    main()
