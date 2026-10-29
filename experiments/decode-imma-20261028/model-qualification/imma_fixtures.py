"""Synthetic full-cap IMMA numerical fixtures. Importing does not encode or write.

build_manifest() is a separately admitted CPU-only tokenizer operation. It never
starts a model, publishes a manifest, or qualifies a private window.
"""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

P = Path(__file__).resolve().parent
E = P.parent.parent
V = E / 'native-vision-v2'
IMAGE_MANIFEST = E / 'prefill-cache-improvements-20261027/numerical-fixtures/manifest.json'
IMAGE_MANIFEST_SHA = '251f89c1949f43308994a2a08805195ff7069eb4f11642920ed442168db10061'
SERVER_SHA = 'b1be40294f6c49692829ad5f85a7aa2867218180fdc8fbc9bef7710371ba3b9f'
IDS = ('cold-text', 'rewind-text', 'two-images', 'restore-text')
KEEP = 2668
MAX_PROMPT = 12000
POLICY = {'model': 'deepseek-v4.1-flash-iq2-xs', 'stream': True,
          'reasoning_effort': 100, 'reasoning_budget_tokens': 0,
          'temperature': 1.0, 'top_p': 1.0, 'seed': 1, 'max_tokens': 32768}
LINE = 'Synthetic ledger: item=seven; status=reviewed; immutable=true.\n'


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sequence_expected(end):
    if type(end) is not int or end not in (64, 256):
        raise ValueError('Only the frozen numeric64 and future timed256 variants exist')
    return {'values': list(range(1, end + 1))}


def request(content):
    return {**POLICY, 'messages': [{'role': 'user', 'content': content}],
            'response_format': {'type': 'json_object'}}


def sequence_request(end=64):
    sequence_expected(end)
    return request('Synthetic numerical state fixture T.\n' + LINE * 520 +
                   '\nReturn only JSON with the single key "values", whose value is the array of every '
                   f'integer from 1 through {end}, in ascending order, exactly once. '
                   'Do not include the ledger or any other keys.')


def source_images():
    """Reuse two exact synthetic PNGs from the already frozen CPU fixture."""
    raw = IMAGE_MANIFEST.read_bytes()
    if digest(raw) != IMAGE_MANIFEST_SHA:
        raise ValueError('Frozen synthetic image source changed')
    source = json.loads(raw)
    image_case = next(c for c in source['cases'] if c['id'] == 'two-images')
    urls = [part['image_url']['url'] for part in image_case['request']['messages'][0]['content']
            if part['type'] == 'image_url']
    if len(urls) != 2:
        raise ValueError('Exactly two frozen synthetic images required')
    hashes = []
    for url in urls:
        if not url.startswith('data:image/png;base64,'):
            raise ValueError('Frozen PNG data URL required')
        image = base64.b64decode(url.split(',', 1)[1], validate=True)
        if not image.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid frozen PNG')
        hashes.append(digest(image))
    if hashes != source['images_sha256']:
        raise ValueError('Frozen image byte hashes differ')
    return urls, hashes


def make_cases(urls):
    if type(urls) is not list or len(urls) != 2 or any(type(x) is not str for x in urls):
        raise ValueError('Two synthetic image URLs required')
    text = sequence_request(64)
    pictures = request([
        {'type': 'text', 'text': 'Synthetic numerical state fixture I.\n' + LINE * 12},
        {'type': 'image_url', 'image_url': {'url': urls[0]}},
        {'type': 'text', 'text': LINE * 400},
        {'type': 'image_url', 'image_url': {'url': urls[1]}},
        {'type': 'text', 'text': LINE * 95 + '\nReturn only JSON with keys "first" and "second", '
         'each a lowercase string naming the corresponding picture predominant color.'},
    ])
    cases = []
    for case_id in IDS:
        image = case_id == 'two-images'
        cases.append({'id': case_id, 'kind': 'json', 'purpose': 'UNMEASURED_NUMERICAL_STATE',
                      'request': copy.deepcopy(pictures if image else text),
                      'expected': {'first': 'red', 'second': 'blue'} if image else sequence_expected(64),
                      'expected_reuse': 'zero' if case_id in ('cold-text', 'two-images') else 'prompt-minus-one'})
    return cases


def validate_requests(cases):
    if type(cases) is not list or [c.get('id') for c in cases] != list(IDS):
        raise ValueError('Exact ordered four-case state sequence required')
    for c in cases:
        body = c['request']
        for key, value in POLICY.items():
            if type(body.get(key)) is not type(value) or body[key] != value:
                raise ValueError('Full-cap sampling policy changed: ' + key)
        if set(body) != set(POLICY) | {'messages', 'response_format'}:
            raise ValueError('Unexpected request override')
        if body['response_format'] != {'type': 'json_object'}:
            raise ValueError('JSON response format required')
    expected = make_cases([part['image_url']['url'] for part in cases[2]['request']['messages'][0]['content']
                           if part['type'] == 'image_url'])
    if packed(cases) != packed(expected):
        raise ValueError('Frozen synthetic request, expected answer or reuse changed')


def image_spans(ids):
    spans, start = [], None
    for i, token in enumerate([*ids, -1]):
        if token == 129264 and start is None:
            start = i
        if token != 129264 and start is not None:
            spans.append({'start': start, 'length': i - start})
            start = None
    return spans


def validate_encoded(cases):
    validate_requests([{k: v for k, v in c.items() if k not in
                        ('prompt_ids', 'prompt_tokens', 'prompt_ids_sha256', 'request_sha256', 'image_spans')}
                       for c in cases])
    for c in cases:
        ids = c['prompt_ids']
        if type(ids) is not list or any(type(t) is not int or not 0 <= t < 129280 for t in ids):
            raise ValueError('Encoded API tokens must be valid vocabulary IDs')
        if not 6000 <= len(ids) < MAX_PROMPT or type(c['prompt_tokens']) is not int or c['prompt_tokens'] != len(ids):
            raise ValueError('Expected synthetic prefix length is 6000 <= n < 12000')
        if c['prompt_ids_sha256'] != digest(packed(ids)) or c['request_sha256'] != digest(packed(c['request'])):
            raise ValueError('Encoded request/token hashes do not match')
        if c['image_spans'] != image_spans(ids):
            raise ValueError('Image span receipt does not match actual IDs')
        if c['id'] != 'two-images' and c['image_spans']:
            raise ValueError('Text fixture contains image tokens')
    if any(cases[i]['prompt_ids'] != cases[0]['prompt_ids'] for i in (1, 3)):
        raise ValueError('Text rewind and slot-return prompt must be identical')
    spans = cases[2]['image_spans']
    cut = len(cases[2]['prompt_ids']) - KEEP
    if len(spans) != 2 or spans[0]['start'] + spans[0]['length'] > cut or spans[1]['start'] < cut:
        raise ValueError('First image must precede cut; second must be in retained tail')
    return cases


def load_support():
    """Import the existing mock API/tokenizer support only on an admitted CPU call."""
    api = V / 'runtime/serve/server.py'
    if digest(api.read_bytes()) != SERVER_SHA:
        raise ValueError('Selected API source changed before import')
    spec = importlib.util.spec_from_file_location('imma_native_vision_cpu_support', V / 'test_native_vision.py')
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    for module, path in ((support.server, api), (support.ds4_vision, V / 'runtime/serve/ds4_vision.py'),
                         (support.dsml, V / 'runtime/serve/dsml.py'),
                         (support.ST, V / 'runtime/tools/strata_tokenizer.py')):
        if Path(module.__file__).resolve() != path.resolve():
            raise ValueError('CPU support imported a foreign same-name module')
    if 'torch' in sys.modules:
        raise ValueError('Unexpected GPU framework import')
    return support


def encode_cases(cases):
    """CPU prompt encoding, distinct from old cap1 encoder; no output files."""
    validate_requests(cases)
    support = load_support()
    s, tok = support.server, support.tokenizer()
    with tempfile.TemporaryDirectory(prefix='imma-cpu-synthetic-images-') as tmp:
        vision = support.ds4_vision.Vision(support.ds4_vision.Geometry(), Path(tmp), s.Vision.load)
        try:
            svc = s.Service(s.MockEngine(tok, ['CPU'], max_context=1048576), tok,
                            s.ChatTemplate(support.dsml.pick_template(V / 'tokenizer/chat_template.jinja')[0]),
                            vision=vision, fit_max_tokens=False)
            svc.set_family('deepseek41')
            svc.answer_room = False
            svc.reasoning_budget_configured = True
            svc.reasoning_budget_tokens = 0
            svc.reasoning_loop_recovery = False
            svc.repeat_stop_tokens = 0
            encoded = []
            for case in cases:
                body = json.loads(packed(case['request']))
                messages, tools, kwargs = s.openai_to_messages(body)
                messages, _ = s.prepare_format(body.get('response_format'), messages, with_tools=bool(tools))
                ids = svc.encode_prompt(messages, tools, kwargs, store=False)
                encoded.append({**copy.deepcopy(case), 'prompt_ids': ids, 'prompt_tokens': len(ids),
                                'prompt_ids_sha256': digest(packed(ids)), 'request_sha256': digest(packed(body)),
                                'image_spans': image_spans(ids)})
            # Informational only: emitted reasoning, formatting and verification paths can differ.
            lengths = {str(n): len(tok.encode(packed(sequence_expected(n)).decode())) for n in (64, 256)}
            if 'torch' in sys.modules:
                raise ValueError('Unexpected GPU framework import')
            return validate_encoded(encoded), lengths
        finally:
            vision.shutdown()


def build_manifest():
    urls, image_hashes = source_images()
    cases, lengths = encode_cases(make_cases(urls))
    return {'id': 'imma-fullcap-numeric-state64-v1', 'purpose': 'UNMEASURED_NUMERICAL_ONLY',
            'context': 1048576, 'default_output': 262144, 'policy': dict(POLICY),
            'API_sha256': SERVER_SHA, 'synthetic_image_source_sha256': IMAGE_MANIFEST_SHA,
            'images_sha256': image_hashes, 'cases': cases,
            'expected_reuse_tokens': [0, cases[0]['prompt_tokens'] - 1, 0, cases[0]['prompt_tokens'] - 1],
            'expected_mode1_activation_skipped_tokens': [cases[i]['prompt_tokens'] - KEEP for i in (0, 2)],
            'canonical_answer_token_lengths_CPU_only': lengths,
            'timed256_variant_admitted': False, 'native_model_executed': False,
            'GPU_launch_ready': False, 'rows_per_request': 'variable; not a framed token-to-row transcript',
            'gate': 'Require natural stop/exact typed JSON and actual DSpark offered>0 and accepted>0; '
                    'finite complete dumps, emitted IDs, state and lifecycle checks. Any nonzero drift, '
                    'path/row mismatch, overflow or partial result is HOLD; no tolerance or retry.'}
