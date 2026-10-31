"""Prospective latest-engine Maya-S profiles and source-specific startup evidence.

Pure helpers only. Neither a controller nor a GPU admission. Original validators
and all closed experiments remain unchanged.
"""
import copy
import hashlib
import json
import math
from pathlib import PurePosixPath as Path
import re

R = Path('/home/alex/strata-deepseek-test-20261024')
E = R / 'reliability-optimization-20261025'
P = E / 'decode-optimization-20261028/maya145-placement-v2'
PACK = E / 'decode-optimization-20261028/maya-s-comparison-v1/pack-v1/pack-FIRST'
NATIVE = E / 'decode-optimization-20261028/maya145-mayas-v1/native-build-r2-FIRST/maya-ds4'
BASE_NORMALIZED = '84ebe7a435304f8d1734b8616066edae868b4273a0afec575bd7d3c81159ea6e'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def factor(variant):
    require(variant in ('TP1', 'TP2'), 'Two source-reviewed placement profiles only')
    return {'variant': variant, 'tp': int(variant[-1]), 'native': str(NATIVE), 'pack': str(PACK),
            'drafter': 'published Maya-S DSpark, enabled', 'context_total': 1048576,
            'output_allowance': 262144, 'effort': 100, 'prefill_chunk': 4096,
            'numerical_equivalence_claim': False}


def profile(base, directory, variant):
    require(hashlib.sha256(packed(base)).hexdigest() == BASE_NORMALIZED, 'Exact selected4096 typed config required')
    f = factor(variant)
    directory = Path(directory)
    require(directory.is_absolute() and '..' not in directory.parts and directory.name == 'native'
            and directory.parent.parent == E / 'results'
            and re.fullmatch(r'maya145p2-mayas-(?:TP1|TP2)-[0-9]{8}T[0-9]{6}Z', directory.parent.name)
            and directory.parent.name.startswith('maya145p2-mayas-' + variant + '-'), 'Fresh matching private namespace')
    out = copy.deepcopy(base)
    out.update(exe=str(NATIVE), tokenizer=str(PACK / 'tokenizer'), port=18041, log=str(directory / 'engine.log'))
    for option, value in (('--pack', str(PACK)), ('--tp', str(f['tp'])),
                          ('--expert-profile', str(directory / 'expert-profile.bin'))):
        require(out['args'].count(option) == 1, 'Unique unchanged option required: ' + option)
        out['args'][out['args'].index(option) + 1] = value
    out['args'].append('--verbose')
    for key, tail in (('STRATA_DS4_SLOT_DIR', 'cache'), ('DS4_LANE_CAL', 'lane.txt'), ('DS4_LT_STORE', 'lt.txt')):
        out['env'][key] = str(directory / tail)
    require(not any(k in out['env'] for k in ('DS4_SERVE_DUMP', 'DS4_YOCO_KEEP', 'DS4_DRAFT_VRAM',
                                             'DS4_TP_SHARES', 'DS4_DENSE_REQ')), 'Unfrozen quality/placement factor')
    if variant == 'TP2':
        # Maya-S down matrices use 256-value blocks: 2304/2 is not an integral
        # block count. Explicit uneven-block support prevents silently falling to TP1.
        # Keep FP32 reductions; the author's private FP16-wire path is not adopted.
        out['env'].update(DS4_TP_GGUF_UNEVEN='1', DS4_TP_CHECK='1', DS4_AR2='1')
    return out


def check_profile(base, value, directory, variant):
    require(packed(value) == packed(profile(base, directory, variant)), 'Exact new native/model/policy profile required')
    return True


Q8 = re.compile(r"^ds4: CUDA([0-9]+) Q8 batch check: 8 jobs \(k 32 \.\. 5120, rows 1 \.\. 16, strided, "
                r"one input read with two k, two jobs sharing a rounding\): 50976 int8 and 1593 scales "
                r"the per-job launches' bit for bit, every guard intact \(DS4_Q8_CHECK\)$", re.M)
PROJECTION = re.compile(r'^abliteration check: device ([0-9]+) rows 2 dim 5120 target blocks 40 drafter untouched '
                        r'max_abs ([0-9.eE+\-]+) PASS$', re.M)
PLACEMENT = re.compile(r'^ds4: CUDA([0-9]+) layers \[([0-9]+), ([0-9]+)\]'
                      r'(?: \(tensor parallel ([0-9]+), part ([0-9]+)\))?( \+ head)?'
                      r'(?: \+ blocks ([0-9,]+))?: weights ([0-9.]+) GB, experts ([0-9.]+) GB '
                      r'\(([0-9]+) of ([0-9]+) in VRAM\), caches ([0-9.]+) GB, ([0-9]+) MiB free$', re.M)


def startup(log, variant):
    f = factor(variant)
    require('Q8 batch check FAILED' not in log and 'prompt copies' + ' FAILED' not in log,
            'Actual native startup failure')
    require(sorted(Q8.findall(log)) == ['0', '1'], 'Exactly one current Q8 sharing check on each GPU')
    projections = PROJECTION.findall(log)
    require(sorted(x[0] for x in projections) == ['0', '1']
            and all(math.isfinite(float(x[1])) and float(x[1]) >= 0 for x in projections),
            'Actual per-device projection check missing/invalid')
    rows = []; repeats = 0
    for values in PLACEMENT.findall(log):
        d, first, last, tp, member, head, blocks, weights, experts, kept, total, cache, free = values
        row = {'device': int(d), 'first_layer': int(first), 'last_layer': int(last), 'tp': int(tp or '1'),
               'member': int(member) if member else None, 'head': bool(head),
               'draft_blocks': [int(x) for x in blocks.split(',')] if blocks else [],
               'weights_GB_rounded': float(weights), 'experts_GB_rounded': float(experts),
               'experts_human_with_drafter': int(kept), 'experts_total_with_drafter': int(total),
               'cache_GB_rounded': float(cache), 'free_MiB_rounded': int(free)}
        require(row['tp'] == f['tp'] and row['last_layer'] < 43 and row['first_layer'] <= row['last_layer']
                and 0 < row['experts_human_with_drafter'] <= row['experts_total_with_drafter']
                and all(math.isfinite(row[k]) and row[k] >= 0 for k in ('weights_GB_rounded', 'experts_GB_rounded', 'cache_GB_rounded')),
                'Malformed or unexpected actual placement')
        existing=next((r for r in rows if r['device']==row['device']),None)
        require(existing is None or existing==row,'Conflicting placement snapshots for one device')
        if existing is None:rows.append(row)
        else:repeats+=1
    require(sorted(r['device'] for r in rows) == [0, 1], 'Exactly two actual owning GPU placement rows')
    if variant == 'TP2':
        require(sorted(r['member'] for r in rows) == [0, 1]
                and all(r['first_layer'] == 0 and r['last_layer'] >= 39 for r in rows), 'Actual TP2 trunk group required')
        require('ds4: TP check passed (' in log and '(DS4_TP_CHECK)' in log, 'Actual TP2 startup arithmetic/copy check required')
        require('ds4: DS4_AR2=1: the prompt chunks\' all-reduces on ' in log, 'Actual FP32 pipelined prompt reduction required')
    else:
        devices = {r['device']: r for r in rows}
        require(devices[0]['first_layer'] == 0 and devices[0]['last_layer'] == 42 and not devices[0]['head']
                and 1 <= devices[1]['first_layer'] <= 39 and devices[1]['last_layer'] == 39 and devices[1]['head'],
                'Actual automatic TP1 trunk/drafter/head placement required')
    return {'passed': True, 'Q8_devices': [0, 1], 'projection_devices': [0, 1], 'placement': rows, 'identical_placement_repeat_rows': repeats,
            'source_specific_startup_only': True, 'model_quality_or_speed_proof': False}
