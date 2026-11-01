"""Pure S2-inspired recipe planning. No downloads, native loading, or deployment.

The supplied October 30 followup supersedes the document's T16 gate/up choice.
Native CPU experts and quantized GPU experts are distinct effective weights.
Selection must therefore use a frozen actual placement, with swaps disabled.
This creates a local recipe, never an assertion of private S2 identity.
"""
import hashlib
import json
import re
import struct

LAYERS, EXPERTS, DIM, FF = 40, 384, 5120, 2304
SENSITIVE = tuple(range(24, 29))
TARGET = 1870
ROLES = ('w1', 'w3', 'w2')
OFFICIAL_REVISION = '1bae0e1088993b9b82de08f59de5be5a34e42170'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def profile(raw):
    """Only the trunk or trunk+three DSpark layers of uint32 counts are accepted."""
    require(type(raw) is bytes and len(raw) in (40 * 384 * 4, 43 * 384 * 4),
            'Exact trunk or trunk+drafter profile bytes')
    values = struct.unpack('<15360I', raw[:40 * 384 * 4])
    rows = [list(values[l * EXPERTS:(l + 1) * EXPERTS]) for l in range(LAYERS)]
    require(all(sum(row) > 0 for row in rows), 'Every layer needs actual routing counts')
    return rows


def validate_counts(counts):
    require(type(counts) is list and len(counts) == LAYERS, 'Forty trunk count rows')
    for row in counts:
        require(type(row) is list and len(row) == EXPERTS
                and all(integer(n, 0, 2**32 - 1) for n in row) and sum(row) > 0,
                'Complete uint32 nonzero routing row')


def select_native(counts, gpu_ids, target=TARGET):
    """Cover sensitive-layer RAM experts, then the most-used remaining RAM ones.

    gpu_ids must come from an actual frozen placement, not a free-memory estimate.
    Counts alone cannot identify the placement made by the native allocator.
    """
    validate_counts(counts)
    require(type(gpu_ids) is list and len(gpu_ids) == LAYERS, 'Actual forty-layer GPU map')
    require(integer(target, 1, TARGET), 'Bounded native expert count')
    ram = []
    for layer, row in enumerate(gpu_ids):
        require(type(row) is list and len(row) <= EXPERTS
                and all(integer(e, 0, EXPERTS - 1) for e in row)
                and len(set(row)) == len(row), 'Unique actual GPU expert IDs')
        resident = set(row)
        ram.extend((layer, e) for e in range(EXPERTS) if e not in resident)
    critical = [pair for pair in ram if pair[0] in SENSITIVE]
    require(len(critical) <= target <= len(ram), 'Native budget must cover sensitive CPU set')
    other = sorted((pair for pair in ram if pair[0] not in SENSITIVE),
                   key=lambda pair: (-counts[pair[0]][pair[1]], pair[0], pair[1]))
    selected = sorted(critical + other[:target - len(critical)])
    return {'schema': 's2-local-cpu-selection-v1', 'selected': [list(p) for p in selected],
            'count': target, 'sensitive_cpu_count': len(critical), 'ram_count': len(ram),
            'profile_sha256': canonical_sha(counts), 'gpu_ids_sha256': canonical_sha(gpu_ids),
            'private_author_map_reproduced': False, 'adaptive_cache': False,
            'decode_streaming': False}


def geometry(role):
    require(role in ROLES, 'Only complete gate/up/down roles')
    return (DIM, FF) if role == 'w2' else (FF, DIM)


def matrix_bytes(role, dtype):
    n, k = geometry(role)
    per, size = {'MXFP4': (32, 17), 'IQ2_XXS': (256, 66),
                 'IQ2_S': (256, 82), 'IQ3_XXS': (256, 98),
                 'IQ3_S': (256, 110)}[dtype]
    require(k % per == 0, 'Whole quant blocks per row')
    return n * (k // per) * size


def native_records(selection):
    ids = selection['selected']
    require(type(ids) is list and integer(len(ids), 1, TARGET), 'Bounded explicit native IDs')
    require(all(type(p) is list and len(p) == 2 and integer(p[0], 0, 39)
                and integer(p[1], 0, 383) for p in ids), 'Typed trunk-only expert IDs')
    require(ids == sorted(ids) and len({tuple(p) for p in ids}) == len(ids),
            'Unique ordered native IDs')
    require(selection.get('count') == len(ids) and type(selection.get('count')) is int,
            'Native count agrees with coverage')
    records, offset = [], 0
    for layer, expert in ids:
        for role in ROLES:
            n, k = geometry(role)
            name = f'layers.{layer}.ffn.experts.{expert}.{role}.weight'
            size = matrix_bytes(role, 'MXFP4')
            records.append({'layer': layer, 'expert': expert, 'role': role,
                            'source_weight': name, 'source_scale': name[:-6] + 'scale',
                            'dtype': 'MXFP4', 'shape': [n, k],
                            'output_offset': offset, 'output_bytes': size})
            offset += size
    return records


def original_range(record, index, headers):
    """Safetensors I8 nibble plane + E8M0 scales; no dequant/requant substitution."""
    require(integer(record['layer'], 0, 39) and integer(record['expert'], 0, 383)
            and record['role'] in ROLES, 'Original trunk/role identity')
    expected = f'layers.{record["layer"]}.ffn.experts.{record["expert"]}.{record["role"]}.weight'
    require(record['source_weight'] == expected and record['source_scale'] == expected[:-6] + 'scale'
            and record['shape'] == list(geometry(record['role']))
            and record['dtype'] == 'MXFP4', 'Source IDs agree with declared output role')
    result = {}
    for kind in ('weight', 'scale'):
        key = record['source_' + kind]
        filename = index['weight_map'][key]
        require(type(filename) is str and re.fullmatch(r'model-\d{5}-of-00048\.safetensors', filename),
                'Pinned official shard name')
        h = headers[filename]
        require(type(h) is dict and integer(h['header_bytes'], 1, 8 * 2**20)
                and integer(h['file_bytes'], h['header_bytes'] + 9, 16 * 2**30),
                'Bounded original header/file')
        n, k = geometry(record['role'])
        d = h['tensors'][key]
        shape = [n, k // (2 if kind == 'weight' else 32)]
        dtype = 'I8' if kind == 'weight' else 'F8_E8M0'
        require(d['dtype'] == dtype and d['shape'] == shape
                and all(type(v) is int for v in d['shape']), 'Original dtype and shape')
        offsets = d['data_offsets']
        require(type(offsets) is list and len(offsets) == 2
                and all(integer(v, 0, h['file_bytes']) for v in offsets), 'Typed source range')
        a, b = offsets
        base = 8 + h['header_bytes']
        require(a < b and b - a == shape[0] * shape[1] and base + b <= h['file_bytes'],
                'Complete source plane inside original file')
        result[kind] = {'file': filename, 'offset': base + a, 'bytes': b - a}
    if result['weight']['file'] == result['scale']['file']:
        w, s = result['weight'], result['scale']
        require(w['offset'] + w['bytes'] <= s['offset']
                or s['offset'] + s['bytes'] <= w['offset'], 'Distinct weight and scale planes')
    return result


def overlay_budget(native_count=TARGET):
    require(integer(native_count, 1, TARGET), 'Bounded native count')
    roles = ('w1', 'w3')
    matrices = len(SENSITIVE) * EXPERTS * len(roles)
    iq3 = sum(matrix_bytes(r, 'IQ3_S') for r in roles) * len(SENSITIVE) * EXPERTS
    prior = sum(matrix_bytes(r, 'IQ2_XXS') for r in roles) * len(SENSITIVE) * EXPERTS
    native = native_count * sum(matrix_bytes(r, 'MXFP4') for r in ROLES)
    return {'native_expert_count': native_count, 'native_packed_bytes': native,
            'iq3_s_gate_up_matrices': matrices, 'iq3_s_gate_up_bytes': iq3,
            'iq3_s_growth_over_maya_s_gate_up_bytes': iq3 - prior,
            'sidecar_payload_bytes': native + iq3,
            'RAM_VRAM_fit_proven': False, 'does_not_include_headers_scratch_or_base': True}


def recipe():
    return {'schema': 's2-local-reconstruction-recipe-v1', 'exact_private_S2': False,
            'base': 'peasantsmith/DeepSeek-V4.1-Flash-1017-Maya-GGUF',
            'base_revision': 'd1fc01009f21e26157acb6858c315d0365483b72',
            'original': 'deepseek-ai/DeepSeek-V4.1-Flash-1017',
            'original_revision': OFFICIAL_REVISION,
            'total_context': 1048576, 'output_allowance': 262144, 'effort': 100,
            'benchmark_cap': 32768, 'drafter': 'unchanged published Maya-S DSpark, on',
            'gate_up': {'layers': list(SENSITIVE), 'dtype': 'IQ3_S',
                        'source': 'original MXFP4, not upconverted IQ2 or T16',
                        'encoder_and_calibration': 'UNQUALIFIED_NOT_YET_SELECTED'},
            'native_cpu': {'target_experts': TARGET, 'roles': list(ROLES),
                           'selection': 'all sensitive-layer RAM experts, then most-used other RAM experts',
                           'exact_ids': 'UNFROZEN_REQUIRES_ACTUAL_CANDIDATE_PLACEMENT'},
            'initial_placement': 'static, no expert-cache swaps or decode streaming',
            'new_native_required': True,
            'forbidden_shortcuts': ['private identity claim', 'T16-as-EXL3 reinterpretation',
                                   'expert deferral', 'FP8 projection switch', 'lower effort or capacity'],
            'required_before_timing': ['CPU/GPU codec and numerical-distribution checks',
                                       'actual 1M allocation and per-device placement/RAM fit',
                                       'full code/prose/tool/image/cache/cancel/lifecycle checks'],
            'selection_metric': 'matched natural completion latency and bounded answer quality; '
                                'report prefill/decode/output lengths, no independent prefill-only veto',
            'budget': overlay_budget()}
