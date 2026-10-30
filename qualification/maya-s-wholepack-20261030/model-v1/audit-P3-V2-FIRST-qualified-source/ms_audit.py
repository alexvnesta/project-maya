"""Independent saved-evidence checks. No model or generated-code execution."""
import hashlib
import json
import math
from pathlib import Path

import ms_config as config
import ms_fixtures as fixtures
import ms_runtime as runtime


def require(ok, message):
    if not ok: raise ValueError(message)


def read(path):
    def unique(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate saved JSON key'); value[key] = item
        return value
    return json.loads(Path(path).read_text(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite saved JSON')))


def resource_contract(samples, page_size):
    require(type(page_size) is int and page_size == 4096 and samples, 'Physical page size/resource samples required')
    for sample in samples:
        require(type(sample.get('root_free_bytes')) is int and sample['root_free_bytes'] >= 120 * 2**30,
                'Runtime root120 floor violated')
        n = sample.get('swap_pages', {}).get('pswpout')
        require(type(n) is int and n >= 0, 'Typed system swap counter required')
    values = [s['swap_pages']['pswpout'] for s in samples]
    require(all(a <= b for a, b in zip(values, values[1:])), 'System swap counter regressed')
    delta = (values[-1] - values[0]) * page_size
    require(delta < 2**30, 'System swapout limit violated')
    return {'root_min_GiB': min(s['root_free_bytes'] for s in samples) / 2**30,
            'system_swapout_delta_bytes': delta, 'swap_not_attributed_to_model': True}


def assembled_ready(raw):
    content = ''; finish = None; done = False
    for line in raw.splitlines():
        if not line.startswith('data:'): continue
        value = line[5:].strip()
        if value == '[DONE]':
            require(not done, 'Duplicate saved DONE'); done = True; continue
        require(not done, 'Saved SSE event after DONE'); event = json.loads(value)
        require('error' not in event, 'Saved API execution error')
        for choice in event.get('choices', []):
            content += choice.get('delta', {}).get('content') or ''
            finish = choice.get('finish_reason') or finish
    require(done and content.strip() == 'READY' and finish == 'stop', 'Assembled public READY/stop/DONE absent')
    return {'content': content, 'finish': finish, 'DONE': True}


def emitted_ids(path, count):
    ids = []; clocks = []
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        require(set(row) == {'token', 'seconds'} and type(row['token']) is int and 0 <= row['token'] < 129280,
                'Saved emitted vocabulary IDs invalid')
        value = row['seconds']; require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                                       'Saved emitted clock invalid')
        ids.append(row['token']); clocks.append(value)
    require(type(count) is int and len(ids) == count and all(a <= b for a, b in zip(clocks, clocks[1:])),
            'Saved emitted count/clock sequence differs')
    return {'count': len(ids), 'valid_vocabulary_ids': True,
            'ordered_ids_sha256': hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest()}


def metric(check):
    n = check['native']; generated = n.get('generated'); ms = n.get('decode_ms')
    require(type(generated) is int and generated > 1 and type(ms) in (int, float) and math.isfinite(ms) and ms > 0,
            'Complete decode metric required')
    offered, accepted = n.get('drafts_offered'), n.get('drafts_accepted')
    require(type(offered) is int and type(accepted) is int and 0 <= accepted <= offered, 'Actual DSpark counts required')
    return {'generated_tokens': generated, 'native_decode_ms': ms, 'native_decode_tps': generated * 1000 / ms,
            'prompt_tokens': n['prompt_tokens'], 'prompt_ms': n['prompt_ms'], 'reused': n['reused'],
            'drafts_offered': offered, 'drafts_accepted': accepted,
            'client_full_seconds': check.get('client_full_s'),
            'client_first_content_seconds': check.get('client_first_content_s'),
            'client_first_reasoning_seconds': check.get('client_first_reasoning_s'),
            'buffered_stream0_first_delta_is_not_true_TTFT': True}


def restoration_contract(state, metadata, legacy):
    verified = state['verified']; identity = verified['selected_identity']; public = verified['public']; health = verified['health']
    expected = {'native_sha256': config.BASE_NATIVE, 'config_sha256': config.BASE_SHA, 'context': 1048576,
                'output_default': 262144, 'prompt_skip_mode': 1, 'prefill_chunk': 4096, 'Q8': [1, 1],
                'DSpark': True, 'images': True, 'runtime_ablation': True, 'TP': 1, 'all_CPU_experts_RAM': True}
    require(all(type(identity.get(k)) is type(v) and identity[k] == v for k, v in expected.items()),
            'Exact selected deployment not restored')
    require(identity['start_binding']['native_pid'] == identity['native_pid']
            and public['unauthenticated_models'] == 401 and public['authenticated_models'] == 200
            and public['known_answer_passed'] is True and public['SSE_done'] is True and public['finish'] == 'stop',
            'Selected authentication/public binding proof absent')
    require(health['loaded'] is True and health['max_context'] == 1048576 and health['images'] is True
            and health['switcher']['active_model'] == health['switcher']['default_model'] == 'deepseek'
            and health['switcher']['fault'] is None, 'Selected router/default capabilities differ')
    assembled_ready((Path(metadata) / 'public-ready-sse.txt').read_text())
    close = read(Path(metadata) / 'old-owner-close.json')
    require(close['passed'] is True and legacy.close_contract(close['binding'], close['native_close'], close['before'], close['after']),
            'Raw old selected API/native exit0 proof absent')
    return verified


def private_cleanup(folder, pid):
    cleanup = read(Path(folder) / 'server-cleanup.json')
    closes = [json.loads(s) for s in (Path(folder) / 'native-close.jsonl').read_text().splitlines()]
    require(cleanup['passed'] is True and type(cleanup['server_returncode']) is int and cleanup['server_returncode'] == 0
            and cleanup['grace_timeout'] is False and cleanup['application_stopped'] is True
            and cleanup['native_ready_pid'] == pid, 'Actual private API exit0 missing')
    require(len(closes) == 1 and closes[0]['native_pid'] == pid and type(closes[0]['returncode']) is int
            and closes[0]['returncode'] == 0 and closes[0]['closed'] is True, 'Unique private native exit0 missing')
    return {'private_API_exit': 0, 'native_exit': 0}


def score_saved(case, response, check, *, quality):
    n = check['native']
    require(response.get('status') == 200 and response.get('done') is True and not response.get('cancelled')
            and not response.get('budget_not_started') and not response.get('intentional_budget_stop')
            and n['finish'] == 'stop' and response['finish_reason'] == 'stop'
            and 1 < check['observed_tokens'] == n['generated'] < 32768, 'Wrong/capped/partial result')
    if case.get('expected_reuse') is not None:
        wanted = 0 if case['expected_reuse'] == 'zero' else len(case['prompt_ids']) - 1
        require(n['reused'] == wanted, 'Actual prefix state differs')
    if case['kind'] == 'json':
        def unique(items):
            value = {}
            for key, item in items:
                require(key not in value, 'Duplicate answer key'); value[key] = item
            return value
        answer = json.loads(response['content'], object_pairs_hook=unique)
        require(fixtures.packed(answer) == fixtures.packed(case['expected']), 'Saved typed known answer wrong')
    if case['kind'] == 'literal': require(response['content'].strip() == case['expected'], 'Saved recovery answer wrong')
    if case['kind'] == 'prose': require(response['content'].strip().endswith(case['expected_last_sentence']), 'Prose ending absent')
    if quality: require(n['drafts_offered'] > 0 and n['drafts_accepted'] > 0, 'Positive DSpark path absent')
    return metric(check)


def compare_pair(a, b):
    require(a['mode'] == b['mode'] and a['mode'] in ('prose', 'coding') and a['accepted'] is b['accepted'] is True,
            'Two independently accepted matching families required')
    am, bm = a['main_metric'], b['main_metric']; ac, bc = a['cold_metric'], b['cold_metric']
    for main in (am, bm):
        require(type(main['generated_tokens']) is int and 1 < main['generated_tokens'] < 32768
                and type(main['native_decode_tps']) in (int, float)
                and math.isfinite(main['native_decode_tps']) and main['native_decode_tps'] > 0,
                'Actual finite nonzero uncapped primary rates required')
    for cold in (ac, bc):
        require(type(cold['prompt_tokens']) is int and cold['prompt_tokens'] > 0
                and type(cold['prompt_ms']) in (int, float) and math.isfinite(cold['prompt_ms'])
                and cold['prompt_ms'] > 0, 'Finite typed cold prefill metric required')
    rate_change = (bm['native_decode_tps'] / am['native_decode_tps'] - 1) * 100
    matched = ac['prompt_tokens'] == bc['prompt_tokens']
    prefill_change = (bc['prompt_ms'] / ac['prompt_ms'] - 1) * 100 if matched else None
    require(math.isfinite(rate_change) and (prefill_change is None or math.isfinite(prefill_change)),
            'Finite derived comparison required')
    return {'mode': a['mode'], 'native_decode_rate_change_percent': rate_change,
            'cold_prefill_change_percent': prefill_change, 'matched_prompt_token_count': matched,
            'screen_passed': rate_change >= 5 and matched and prefill_change <= 3,
            'required_decode_gain_percent': 5, 'maximum_cold_prefill_regression_percent': 3,
            'output_tokens': {'baseline': am['generated_tokens'], 'candidate': bm['generated_tokens']},
            'overall_task_speed_or_general_quality_claim': False, 'deployment_authorized': False}
