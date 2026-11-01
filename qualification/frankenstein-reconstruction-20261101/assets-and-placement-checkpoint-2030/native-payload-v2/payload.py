"""Original MXFP4 native1870 materializer, with one disjoint output allocation.

Planning is metadata only. materialize() requires exact review/CPU/placement/
source qualification and an outer admitted CPU owner, guard and child registry.
It never claims STATE, loads a model, opens a GPU or changes a service itself.
The caller must retain its CPU claim until registry absence is proven.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import re
import shutil
import stat
import struct
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
Q = HERE.parent
RECIPE = Q / 'recipe-v1/reconstruction.py'
RECIPE_SHA = '36f20ef551185a49793e0d1eb94b7e33994c2e0f4b527f9c0b7b432a2e3bd430'
HEADER = Q / 'native-lane-v1/native_header.py'
HEADER_SHA = '96cb8eb51463bc195fb3f39ce65e54f59b55e66ccf3af3ce4a68c34ab57b30d7'
CONVERSION = Q / 'iq3s-conversion-v1/convert.py'
CONVERSION_SHA = '8bad9fd42a851bf5571f34f8727c19a88668e619f470cea046784b4a4a1bb574'
CODEC_SOURCE_SHA = '178229dc37b9c4907c604e1787b4acf7615a5f5c095375a6685f1b6a4ad10f40'
CODEC_PROOF_SHA = '631c3f24506e4c54942f1ccce3db8b6a6294a6f39cc9d51354615c2f431f90c1'
CODECS = {'darwin': '6ca0b37b8612ab2ca23ace0a5f47bb4b6d77cf28aa8693e4398c22b6e16241ff',
          'linux': 'd158d81dfcfd2d6bc13202acdf39ae2523910e41f4dcb36c492d0ca03f52f897'}
INDEX_SHA = '74b0686a3d2891980d5e303251b075a3bccae2c2ff650747db2620a649b98fa8'
METADATA_SHA = 'f4f8d13ede75d7ad4918c602d6b5f3e0c6981f2afa4f8e7bc685d4292d51045a'
HEADER_BYTES, MATRIX_BYTES, COUNT = 102400, 6266880, 1870
PAYLOAD_BYTES = COUNT * 3 * MATRIX_BYTES
FILE_BYTES = HEADER_BYTES + PAYLOAD_BYTES
RESERVE = 132 * 2**30
SOURCES = ('payload.py', 'test_payload.py', 'run_cpu.py')
CLEAN_ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
             'MALLOC_ARENA_MAX': '1', 'PYTHONDONTWRITEBYTECODE': '1',
             'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}
CPU_ENV = dict(CLEAN_ENV, MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
SUPERVISOR_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''): digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def object_sha(value): return hashlib.sha256(canonical(value)).hexdigest()


def emit(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.resolve() == path,
            'Real absolute file required')
    st = path.stat()
    require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, 'One ordinary file required')
    return stamp(st)


def stamp(st): return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def exact(name, path, digest):
    regular(path); require(sha(path) == digest, 'Pinned dependency changed: ' + name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def dependencies():
    return (exact('native_payload_recipe', RECIPE, RECIPE_SHA),
            exact('native_payload_header', HEADER, HEADER_SHA))


def validate_ranges(records, header_bytes, matrix_bytes, count):
    require(len(records) == count * 3, 'Every selected expert has three roles')
    seen = set()
    for index, row in enumerate(records):
        identity = (row['layer'], row['expert'], row['role'])
        require(identity not in seen and row['role'] == ('w1', 'w3', 'w2')[index % 3] and
                row['output_offset'] == index * matrix_bytes and row['output_bytes'] == matrix_bytes,
                'Unique complete contiguous three-role output map')
        seen.add(identity)
        if index % 3:
            previous = records[index - 1]
            require((row['layer'], row['expert']) == (previous['layer'], previous['expert']),
                    'One complete expert per three-role run')
        require(header_bytes + row['output_offset'] + matrix_bytes <= header_bytes + count * 3 * matrix_bytes,
                'Output role range inside exact artifact')


def make_plan(placement, selection, index, headers, metadata):
    """Pure metadata: no original bytes, native loading or placement estimates."""
    recipe, writer = dependencies()
    require(placement.get('schema') == 'ds4-actual-placement-v1' and
            placement.get('context_total') == 1048576 and placement.get('prefill_chunk') == 4096 and
            placement.get('expert_cache') is False and
            placement.get('inference_executed') is False and placement.get('routed_experts_loaded') is False and
            placement.get('drafter_blocks') == 3 and len(placement['layers']) == 40,
            'Actual static full-capacity trunk placement receipt required')
    counts, slots = [], []
    for number, row in enumerate(placement['layers']):
        require(row['layer'] == number and row['members'] == 1, 'TP1 ordered complete actual trunk map')
        counts.append(row['counts']); slots.append(row['slots'])
    gpu = [[expert for expert, slot in enumerate(row) if slot >= 0] for row in slots]
    require(selection == recipe.select_native(counts, gpu), 'Exact counts/placement-derived native1870 selection')
    require(metadata.get('id') == 'deepseek-ai/DeepSeek-V4.1-Flash-1017' and
            metadata.get('sha') == recipe.OFFICIAL_REVISION, 'Exact original checkpoint metadata')
    siblings = {row['rfilename']: row for row in metadata['siblings']}
    require(len(siblings) == len(metadata['siblings']), 'Unique original metadata names')
    records, source_headers = recipe.native_records(selection), {}
    for row in records:
        row['source_ranges'] = recipe.original_range(row, index, headers)
        for plane in row['source_ranges'].values():
            name = plane['file']; h = headers[name]; official = siblings[name]
            require(h['source_revision'] == recipe.OFFICIAL_REVISION and h['source_file'] == name and
                    h['source_file_sha256'] == official['lfs']['sha256'] and
                    h['file_bytes'] == official['size'] == official['lfs']['size'] and
                    type(h['header_sha256']) is str and len(h['header_sha256']) == 64,
                    'Original raw header and published LFS identity')
            source_headers[name] = {key: h[key] for key in ('header_bytes', 'file_bytes', 'header_sha256',
                                                           'source_file_sha256', 'source_revision')}
    validate_ranges(records, HEADER_BYTES, MATRIX_BYTES, COUNT)
    body = {'schema': 'original-native1870-source-map-v1', 'official_revision': recipe.OFFICIAL_REVISION,
            'placement_sha256': object_sha(placement), 'selection_sha256': object_sha(selection),
            'counts': counts, 'slots': slots, 'selected': selection['selected'], 'records': records,
            'source_headers': source_headers, 'header_bytes': HEADER_BYTES,
            'payload_bytes': PAYLOAD_BYTES, 'file_bytes': FILE_BYTES,
            'source_policy': 'Original I8 adjacent FP4 nibbles and F8_E8M0 scales only; no lowbit upconversion'}
    map_sha = object_sha(body)
    header = writer.make_header(counts, slots, selection['selected'], map_sha)
    require(len(header) == HEADER_BYTES, 'Exact native wire header')
    return dict(body, source_map_sha256=map_sha, header_sha256=hashlib.sha256(header).hexdigest())


def validate_plan(plan):
    body = {key: value for key, value in plan.items() if key not in ('source_map_sha256', 'header_sha256')}
    require(object_sha(body) == plan['source_map_sha256'] and plan.get('schema') == 'original-native1870-source-map-v1' and
            plan['header_bytes'] == HEADER_BYTES and plan['payload_bytes'] == PAYLOAD_BYTES and
            plan['file_bytes'] == FILE_BYTES, 'Exact external map and native geometry')
    recipe, writer = dependencies()
    selection = recipe.select_native(plan['counts'],
        [[expert for expert, slot in enumerate(row) if slot >= 0] for row in plan['slots']])
    require(selection['selected'] == plan['selected'] and object_sha(selection) == plan['selection_sha256'],
            'Frozen actual selection unchanged')
    expected = recipe.native_records(selection)
    require(len(expected) == len(plan['records']), 'Complete selected native role records')
    for original, row in zip(expected, plan['records']):
        require(all(row.get(key) == value for key, value in original.items()), 'Role identity/geometry drift')
    validate_ranges(plan['records'], HEADER_BYTES, MATRIX_BYTES, COUNT)
    header = writer.make_header(plan['counts'], plan['slots'], plan['selected'], plan['source_map_sha256'])
    require(hashlib.sha256(header).hexdigest() == plan['header_sha256'], 'Exact header SHA')
    return header


def source_contract(plan, receipt, root):
    require(receipt.get('root') == str(root) and receipt.get('official_revision') == plan['official_revision'] and
            receipt.get('source_map_sha256') == plan['source_map_sha256'], 'Full-SHA receipt bound to root/map/revision')
    for name, expected in plan['source_headers'].items():
        require(type(name) is str and re.fullmatch(r'model-\d{5}-of-00048\.safetensors', name),
                'Original source filename only')
        row = receipt['files'][name]
        require(row.get('full_sha_verified') is True and row['sha256'] == expected['source_file_sha256'] and
                row['fingerprint'][2] == expected['file_bytes'] and regular(Path(root) / name) == row['fingerprint'],
                'Stable full original SHA/fingerprint receipt required')


def pread_exact(fd, count, offset):
    pieces, done = [], 0
    while done < count:
        data = os.pread(fd, count - done, offset + done)
        require(bool(data), 'Short original read')
        pieces.append(data); done += len(data)
    return b''.join(pieces)


def pwrite_all(fd, data, offset, *, write=os.pwrite):
    require(type(offset) is int and offset >= 0, 'Nonnegative explicit output offset')
    view = memoryview(data); done = 0
    while done < len(view):
        wrote = write(fd, view[done:], offset + done)
        require(type(wrote) is int and 0 < wrote <= len(view) - done, 'Short/invalid native output write')
        done += wrote


def read_role(row, root, receipt, descriptors, recipe):
    planes = {}
    actual_headers = {}
    for kind in ('weight', 'scale'):
        plane = row['source_ranges'][kind]; name = plane['file']; path = Path(root) / name
        require(type(name) is str and re.fullmatch(r'model-\d{5}-of-00048\.safetensors', name),
                'Original role source filename only')
        expected = receipt['files'][name]['fingerprint']; descriptor = descriptors[name]
        require(regular(path) == expected, 'Original source modified before role read')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            require(stamp(os.fstat(fd)) == expected, 'Source FD changed at open')
            length = struct.unpack('<Q', pread_exact(fd, 8, 0))[0]
            require(length == descriptor['header_bytes'] and 1 <= length <= 8 * 2**20, 'Exact bounded raw header')
            raw = pread_exact(fd, length, 8)
            require(hashlib.sha256(raw).hexdigest() == descriptor['header_sha256'], 'Actual original header SHA')
            actual_headers[name] = {'header_bytes': length, 'file_bytes': expected[2], 'tensors': json.loads(raw)}
            offset, count = plane['offset'], plane['bytes']
            n, k = row['shape']
            require(count == n * k // (2 if kind == 'weight' else 32), 'Exact complete original plane size')
            require(type(offset) is type(count) is int and 8 + length <= offset <= expected[2] - count and count > 0,
                    'Complete explicit source plane')
            planes[kind] = pread_exact(fd, count, offset)
            require(stamp(os.fstat(fd)) == expected and regular(path) == expected,
                    'Original source modified during role read')
        finally: os.close(fd)
    index = {'weight_map': {row['source_' + kind]: row['source_ranges'][kind]['file'] for kind in ('weight', 'scale')}}
    require(recipe.original_range(row, index, actual_headers) == row['source_ranges'],
            'Raw original header confirms dtype/shape/exact ranges')
    return planes['weight'], planes['scale']


def codec_path():
    path = Q / ('native-codec-v2/mxpack-FIRST-' + sys.platform)
    require(sha(Q / 'native-codec-v2/mxpack.cpp') == CODEC_SOURCE_SHA and
            sha(Q / 'native-codec-v2/BOTH_HOST_CPU_FIRST.json') == CODEC_PROOF_SHA,
            'Exact qualified lossless codec source/proof')
    regular(path); require(sha(path) == CODECS[sys.platform], 'Exact physical lossless codec binary')
    return path


def pack_role(weight, scale, shape, codec, *, runner=subprocess.run):
    n, k = shape
    require(type(n) is type(k) is int and 1 <= n <= 5120 and 32 <= k <= 5120 and k % 32 == 0 and
            len(weight) == n * k // 2 and len(scale) == n * k // 32, 'Complete original role planes')
    result = runner([str(codec), '--rows', str(n), '--k', str(k)], input=weight + scale,
                    capture_output=True, timeout=30, env=CLEAN_ENV)
    require(result.returncode == 0 and len(result.stdout) == n * (k // 32) * 17,
            'Lossless original codec failed; no retry')
    return result.stdout


def limits():
    require(sys.flags.isolated and sys.dont_write_bytecode and dict(os.environ) == CLEAN_ENV,
            'Isolated clean data child')
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    priority = os.getpriority(os.PRIO_PROCESS, 0)
    require(priority <= 15, 'Inherited nice priority'); os.nice(15 - priority)


def observed():
    return {'pid': os.getpid(), 'ppid': os.getppid(), 'pgid': os.getpgrp(),
            'cpu': list(resource.getrlimit(resource.RLIMIT_CPU)),
            'as': list(resource.getrlimit(resource.RLIMIT_AS)), 'nice': os.getpriority(os.PRIO_PROCESS, 0),
            'environment': dict(os.environ), 'isolated': bool(sys.flags.isolated)}


def actual_limits(row, pid, parent):
    require(row == {'pid': pid, 'ppid': parent, 'pgid': pid, 'cpu': [30, 30],
                    'as': [512 * 2**20] * 2, 'nice': 15, 'environment': CLEAN_ENV, 'isolated': True},
            'Actual child identity/resources required')


def input_map():
    paths = {'bounded_hash_helper': HASH_HELPER, 'recipe': RECIPE, 'header': HEADER, 'conversion': CONVERSION,
             'codec_source': Q / 'native-codec-v2/mxpack.cpp',
             'codec_proof': Q / 'native-codec-v2/BOTH_HOST_CPU_FIRST.json',
             'index': Q / 'source-plan-v1/inputs/official-index-FIRST.json',
             'metadata': Q / 'source-plan-v1/inputs/official-HF-metadata-FIRST.json',
             'fixture_weight': Q / 'iq3s-real-matrix-v1/original-weight.bin',
             'fixture_scale': Q / 'iq3s-real-matrix-v1/original-scale.bin'}
    return {name: sha(path) for name, path in paths.items()}


def qualification(path, pin):
    require(Path(path) == HERE / 'qualification.json' and sha(path) == pin, 'Exact native payload qualification')
    q = json.loads(Path(path).read_text())
    sources = {name: sha(HERE / name) for name in SOURCES}
    require(q.get('entire_source_tests_driver_manually_read') is True and q.get('CPU_both_hosts_passed') is True and
            q.get('sources') == sources and q.get('inputs') == input_map() and q.get('test_ids'),
            'Current manual/source/both-host CPU payload qualification')
    for platform in ('darwin', 'linux'):
        item = q['CPU'][platform]
        require(sha(item['path']) == item['sha256'] and
                sha(item['supervision_path']) == item['supervision_sha256'], 'Pinned physical CPU proof/closure')
        proof = json.loads(Path(item['path']).read_text())
        supervision = json.loads(Path(item['supervision_path']).read_text())
        cpu_proof_contract(proof, supervision, sources, q['inputs'], q['test_ids'], platform,
                           q['source_review_sha256'])
    require(sha(HERE / 'ROOT_SOURCE_REVIEW.json') == q['source_review_sha256'], 'Pinned manual CPU source review')
    require(q.get('output_directory') == str(HERE / 'native-FIRST') and
            q.get('source_root') == str(Q / 'iq3s-source-acquisition-v1/assets/original'), 'Exact owned source/output roots')
    for name in ('plan', 'source_receipt', 'placement'):
        regular(q[name]['path']); require(sha(q[name]['path']) == q[name]['sha256'], 'Pinned ' + name)
    require(q.get('selected_binding') and q.get('outer_CPU_custody_required') is True,
            'Outer selected-owner CPU lifecycle required')
    plan = json.loads(Path(q['plan']['path']).read_text()); validate_plan(plan)
    placement = json.loads(Path(q['placement']['path']).read_text())
    require(object_sha(placement) == plan['placement_sha256'] and
            placement.get('schema') == 'ds4-actual-placement-v1' and placement.get('context_total') == 1048576 and
            placement.get('prefill_chunk') == 4096 and
            placement.get('expert_cache') is False and placement.get('drafter_blocks') == 3 and
            placement.get('inference_executed') is False and placement.get('routed_experts_loaded') is False and
            len(placement['layers']) == 40 and
            all(row['layer'] == i and row['members'] == 1 for i, row in enumerate(placement['layers'])) and
            [row['counts'] for row in placement['layers']] == plan['counts'] and
            [row['slots'] for row in placement['layers']] == plan['slots'],
            'Exact actual full-capacity static TP1 placement receipt')
    require(q.get('source_map_sha256') == plan['source_map_sha256'] and
            sha(Q / 'source-plan-v1/inputs/official-index-FIRST.json') == INDEX_SHA and
            sha(Q / 'source-plan-v1/inputs/official-HF-metadata-FIRST.json') == METADATA_SHA,
            'Exact external original source-map/index/metadata')
    official_contract(plan, json.loads((Q / 'source-plan-v1/inputs/official-index-FIRST.json').read_text()),
                      json.loads((Q / 'source-plan-v1/inputs/official-HF-metadata-FIRST.json').read_text()))
    receipt = json.loads(Path(q['source_receipt']['path']).read_text())
    source_contract(plan, receipt, Path(q['source_root']))
    hash_helper(q)
    return q, plan, receipt


def cpu_proof_contract(proof, supervision, sources, inputs, ids, platform, review_sha):
    require(type(ids) is list and ids and len(ids) == len(set(ids)) and all(type(i) is str for i in ids),
            'Exact unique ordered CPU control IDs')
    require(proof.get('passed') is True and proof.get('physical_platform') == platform and
            proof.get('sources') == sources and proof.get('inputs') == inputs and proof.get('test_ids') == ids and
            type(proof.get('tests_run')) is int and proof['tests_run'] == len(ids) and
            all(type(proof.get(key)) is int and proof[key] == 0 for key in ('returncode', 'failures', 'errors')),
            'Complete exact physical CPU results, not passed-only')
    as_limit = [512 * 2**20] * 2 if platform == 'linux' else None
    require(proof.get('controls') == {'CPU_seconds': 30, 'AS_bytes': as_limit, 'wall_seconds': 90,
                                     'nice': 15} and proof.get('isolated') is True and
            proof.get('process_environment') == CPU_ENV and proof.get('supervisor_sha256') == SUPERVISOR_SHA and
            proof.get('source_review_sha256') == review_sha, 'Exact physical CPU control policy/source review')
    observed = proof['observed']; pid, parent = observed.get('pid'), proof.get('supervisor_pid')
    expected_env = {key: CPU_ENV[key] for key in ('CUDA_VISIBLE_DEVICES', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                    'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'MALLOC_ARENA_MAX', 'PYTHONDONTWRITEBYTECODE')}
    require(type(pid) is int and type(parent) is int and pid > 1 and parent > 1 and pid != parent and
            observed.get('ppid') == parent and observed.get('pgid') == pid and observed.get('cpu') == [30, 30] and
            observed.get('as') == as_limit and observed.get('nice') == 15 and
            observed.get('platform') == platform and observed.get('dont_write_bytecode') is True and
            observed.get('environment') == expected_env, 'Actual child PID/group/resources/environment')
    argv = supervision.get('argv', [])
    require(supervision.get('pid') == pid and type(supervision.get('returncode')) is int and
            supervision['returncode'] == 0 and supervision.get('error') is None and supervision.get('cleanup') == [] and
            type(supervision.get('elapsed_seconds')) in (int, float) and 0 <= supervision['elapsed_seconds'] <= 90 and
            len(argv) == 9 and argv[1:3] == ['-I', '-B'] and Path(argv[3]).name == 'run_cpu.py' and
            argv[4:] == ['--review-sha256', review_sha, '--child', '--parent', str(parent)],
            'Actual matching bounded supervisor exit and owned-group cleanup')


def official_contract(plan, index, metadata):
    require(metadata.get('sha') == plan['official_revision'], 'Original revision unchanged')
    siblings = {row['rfilename']: row for row in metadata['siblings']}
    require(len(siblings) == len(metadata['siblings']), 'Unique official filenames')
    used = set()
    for row in plan['records']:
        for kind in ('weight', 'scale'):
            name = row['source_ranges'][kind]['file']
            require(index['weight_map'][row['source_' + kind]] == name, 'Exact official original tensor location')
            used.add(name)
    require(set(plan['source_headers']) == used, 'Exact used original source-header closure')
    for name in used:
        require(re.fullmatch(r'model-\d{5}-of-00048\.safetensors', name), 'Canonical official source filename')
        row, h = siblings[name], plan['source_headers'][name]
        require(row['size'] == row['lfs']['size'] == h['file_bytes'] and
                row['lfs']['sha256'] == h['source_file_sha256'] and
                h['source_revision'] == plan['official_revision'], 'Exact official LFS/header source identity')


def output_fd(folder, plan):
    attempt = json.loads((folder / 'attempt.json').read_text())
    path = folder / 'native.partial'
    require(regular(path)[:3] == attempt['output_identity'], 'Owned shared output inode/size')
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        require(stamp(os.fstat(fd))[:3] == attempt['output_identity'] and
                hashlib.sha256(pread_exact(fd, HEADER_BYTES, 0)).hexdigest() == plan['header_sha256'],
                'Actual output FD/header identity')
    except BaseException:
        os.close(fd); raise
    return fd


def worker(index, folder, qpath, qpin):
    require(type(index) is int and 0 <= index < COUNT and folder == HERE / 'native-FIRST',
            'One selected original expert in the admitted output directory')
    limits(); emit(folder / ('%04d.observed.json' % index), observed())
    q, plan, receipt = qualification(qpath, qpin)
    recipe, _ = dependencies(); codec = codec_path(); fd = output_fd(folder, plan)
    results = []
    try:
        for row in plan['records'][index * 3:index * 3 + 3]:
            weight, scale = read_role(row, Path(q['source_root']), receipt, plan['source_headers'], recipe)
            data = pack_role(weight, scale, row['shape'], codec)
            require(len(data) == MATRIX_BYTES, 'Complete original native matrix')
            offset = HEADER_BYTES + row['output_offset']
            pwrite_all(fd, data, offset)
            digest = hashlib.sha256(data).hexdigest()
            require(hashlib.sha256(pread_exact(fd, len(data), offset)).hexdigest() == digest,
                    'Exact native role write/readback')
            results.append({'record': row, 'sha256': digest, 'codec_returncode': 0,
                            'weight_sha256': hashlib.sha256(weight).hexdigest(),
                            'scale_sha256': hashlib.sha256(scale).hexdigest()})
        os.fsync(fd)
        source_contract(plan, receipt, Path(q['source_root']))
        emit(folder / ('%04d.DONE.json' % index), {'index': index, 'roles': results, 'complete': True})
    finally: os.close(fd)


class Children:
    def __init__(self, registry): self.registry, self.lock = registry, threading.Lock()
    def spawn(self, argv, **kwargs):
        with self.lock:
            name = 'native-' + str(len(self.registry.children)); self.registry.starting(name)
            process = subprocess.Popen(argv, **kwargs); self.registry.registered(process, name)
            return process


def run_child(mode, folder, qpath, qpin, children, owner, guard, deadline):
    name = '%04d' % mode if type(mode) is int else mode
    start = time.monotonic(); process = None
    row = {'mode': mode, 'pid': None, 'returncode': None, 'error': None, 'cleanup': []}
    try:
        guard(); require(start < deadline - 95, 'Remaining native data-child budget')
        with (folder / (name + '.log')).open('x') as log:
            argv = [str(Path(sys.executable).resolve()), '-I', '-B', str(HERE / 'payload.py'),
                    str(mode), str(folder), str(qpath), qpin]
            process = children.spawn(argv, cwd=HERE, env=CLEAN_ENV, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            row['pid'] = process.pid
            while process.poll() is None:
                guard(); require(time.monotonic() < min(start + 75, deadline - 20), 'Native child wall budget')
                try: process.wait(timeout=1)
                except subprocess.TimeoutExpired: pass
            row['returncode'] = process.returncode
            require(process.returncode == 0, 'Native payload child failed; no retry')
            actual_limits(json.loads((folder / (name + '.observed.json')).read_text()), process.pid, os.getpid())
    except BaseException as exc: row['error'] = repr(exc)
    finally:
        if process is not None:
            try: owner.cleanup(process, min(start + 90, deadline))
            except BaseException as exc:
                row['cleanup'].append(repr(exc)); children.registry.cleanup_failed(name, exc)
            row['returncode'] = process.poll()
        emit(folder / (name + '.child.json'), row)
    require(row['returncode'] == 0 and row['error'] is None and not row['cleanup'], 'Native payload HOLD')
    return mode


def completion_contract(plan, folder):
    attempt = json.loads((folder / 'attempt.json').read_text())
    for index in range(COUNT):
        done = json.loads((folder / ('%04d.DONE.json' % index)).read_text())
        child = json.loads((folder / ('%04d.child.json' % index)).read_text())
        require(done.get('index') == index and done.get('complete') is True and len(done['roles']) == 3 and
                child.get('returncode') == 0 and child.get('error') is None and child.get('cleanup') == [],
                'Every exact expert/child must finish cleanly')
        actual_limits(json.loads((folder / ('%04d.observed.json' % index)).read_text()), child['pid'],
                      attempt['controller_pid'])
        for result, expected in zip(done['roles'], plan['records'][index * 3:index * 3 + 3]):
            require(result['record'] == expected and result['codec_returncode'] == 0 and
                    len(result['sha256']) == 64, 'Complete three-role original coverage')


def finalize(folder, qpath, qpin):
    limits(); emit(folder / 'finalize.observed.json', observed())
    q, plan, receipt = qualification(qpath, qpin); completion_contract(plan, folder)
    fd = output_fd(folder, plan)
    try:
        # Each child revalidates the entire ordered plan, writes only its index's
        #3 fixed matrix intervals through pwrite_all, and SHA-checks each actual
        #write/readback before DONE. All worker groups have closed before this
        #stage. This single streaming whole-file SHA does not independently
        #recompute every role hash; integrity relies on those disjoint reviewed
        #writers and stable output inode/stamp, not OS region access isolation.
        before = stamp(os.fstat(fd))
        hashing = hash_helper(q).file_sha256(folder / 'native.partial')
        require(hashing['fingerprint'] == before and stamp(os.fstat(fd)) == before and regular(folder / 'native.partial') == before,
                'Native artifact changed during final streaming SHA')
        source_contract(plan, receipt, Path(q['source_root']))
        emit(folder / 'FINAL-DONE.json', {'complete': True, 'bytes': FILE_BYTES,
             'artifact_sha256': hashing['sha256'], 'bounded_hash_hops': hashing['hops'],
             'aggregate_CPU_can_exceed30_each_process_CPU30': True, 'header_sha256': plan['header_sha256'],
             'source_map_sha256': plan['source_map_sha256'], 'plan_sha256': q['plan']['sha256'],
             'source_receipt_sha256': q['source_receipt']['sha256'], 'original_native_experts': COUNT,
             'roles_per_expert': 3, 'no_lowbit_upconversion': True, 'model_executed': False,
             'integrity_basis': 'Per-role write/readback SHA with validated disjoint offsets and closed worker groups; '
                                'one stable whole-file streaming SHA; no second role-hash pass or OS region isolation'})
    finally: os.close(fd)


def materialize(qpath, qpin, *, owner, registry, guard, wall=7200):
    """Call only while an admitted outer CPU owner retains its lease/claim.

    guard must fail on changed selected binding, phase, source custody or resources.
    registry is that owner's existing qualified OwnedChildren instance. All new
    handles are registered before any parent receipt operation can lose them.
    """
    require(sys.platform == 'linux' and sys.flags.isolated and sys.dont_write_bytecode and
            callable(guard) and 120 <= wall <= 7200, 'Bounded isolated admitted CPU materialization')
    guard(); q, plan, _ = qualification(qpath, qpin); codec_path()
    folder = Path(q['output_directory'])
    require(not folder.exists() and not folder.is_symlink(), 'Fresh no-replay native output directory')
    require(shutil.disk_usage(HERE).free >= RESERVE + FILE_BYTES, 'One native payload plus root132; no duplicate payload')
    deadline = time.monotonic() + wall; folder.mkdir(); fd = None
    children = Children(registry); children_start = len(registry.children)
    failure = None; result = None
    try:
        fd = os.open(folder / 'native.partial', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        os.ftruncate(fd, FILE_BYTES); pwrite_all(fd, validate_plan(plan), 0); os.fsync(fd)
        emit(folder / 'attempt.json', {'controller_pid': os.getpid(), 'qualification_sha256': qpin,
             'selected_binding': q['selected_binding'], 'source_map_sha256': plan['source_map_sha256'],
             'output_identity': stamp(os.fstat(fd))[:3], 'file_bytes': FILE_BYTES})
        queue = exact('native_payload_qualified_queue', CONVERSION, CONVERSION_SHA)
        done = queue.convert_queue(list(range(COUNT)),
            lambda index: run_child(index, folder, qpath, qpin, children, owner, guard, deadline),
            guard, workers=4, wall=max(0, deadline - time.monotonic() - 210))
        require(done == list(range(COUNT)) and registry.absence()['passed'], 'All original expert worker groups closed')
        run_child('finalize', folder, qpath, qpin, children, owner, guard, deadline)
        result = json.loads((folder / 'FINAL-DONE.json').read_text())
        require(result.get('complete') is True and result['bytes'] == FILE_BYTES and
                result['source_map_sha256'] == plan['source_map_sha256'], 'Complete exact external native artifact')
        guard()
    except BaseException as exc: failure = exc
    finally:
        if fd is not None: os.close(fd)
        # Cleanup only handles registered by this call; prior owner's children
        # remain its responsibility. Complete absence includes its full registry.
        for name, process, _ in list(registry.children)[children_start:]:
            try: owner.cleanup(process, deadline)
            except BaseException as exc: registry.cleanup_failed(name, exc)
        absence = registry.absence(); emit(folder / 'absence.json', absence)
        if absence['passed'] is not True and failure is None: failure = ValueError('Owned native groups remain')
        emit(folder / 'supervision.json', {'passed': failure is None, 'error': repr(failure) if failure else None,
                                         'CPU_claim_owned_by_outer_controller': True})
    if failure is not None: raise failure
    # Publication has no replacement semantics. Payload bytes are never copied.
    final = folder / 'native.cpu'; os.link(folder / 'native.partial', final); (folder / 'native.partial').unlink()
    emit(folder / 'result.json', dict(result, passed=True, artifact_path=str(final)))
    return result



HASH_HELPER=Q/'bounded-sha256-v1/fork_hash.py'
HASH_SHA='26ab3c1bb4330e1e933a11d739806f7cd2db8a890ac100d208f52a9d67b0cec2'


def hash_helper(q=None):
    """Exact helper; actual runs also require all original raw five-control proofs."""
    module=exact('integrated_bounded_sha256',HASH_HELPER,HASH_SHA)
    if q is None:return module  # CPU smoke tests still enforce helper.bounds().
    files=q['files']
    def checked(path):
        path=Path(path);regular(path)
        require(path.stat().st_size<=512*2**20 and files.get(str(path))==sha(path),'Pinned bounded-hash raw qualification member')
        return path
    qualification=json.loads(checked(q['bounded_hash_qualification']).read_text())
    review=json.loads(checked(qualification['CPUReview']).read_text())
    names=('fork_hash.py','test_hash.py','run_cpu.py')
    sources={n:sha(checked(HASH_HELPER.parent/n)) for n in names}
    require(sources['fork_hash.py']==HASH_SHA and qualification['source_map']==review['source_map']==sources and
        qualification['input_map']==review['input_map']=={'qualified_supervisor':'3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'} and
        qualification['test_ids']==review['test_ids'] and len(set(review['test_ids']))==len(review['test_ids'])==5 and
        review['entire_source_tests_driver_manually_read'] is True and set(qualification['CPU'])=={'darwin','linux'},
        'Actual identical helper source/input/five IDs/manual/both-host qualification')
    supervisor=Q.parent/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
    require(sha(checked(supervisor))==qualification['input_map']['qualified_supervisor'],'Exact helper supervisor')
    for platform,paths in qualification['CPU'].items():
        require(set(paths)=={'receipt','child','log'},'All raw helper CPU proof paths')
        proof=json.loads(checked(paths['receipt']).read_text());child=json.loads(checked(paths['child']).read_text());checked(paths['log'])
        observed=proof['observed'];environment={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
            'MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1'}
        require(proof.get('passed') is True and proof.get('returncode')==0 and proof.get('failures')==proof.get('errors')==0 and
            proof['source_map']==sources and proof['input_map']==qualification['input_map'] and proof['test_ids']==review['test_ids'] and
            proof['controls']==5 and proof['isolated'] is True and observed['platform']==platform and
            observed['pid']==observed['pgid']==child['pid'] and observed['ppid']==proof['supervisor_pid'] and
            observed['cpu']==[30,30] and observed['nice']==15 and observed['as']==([512*2**20]*2 if platform=='linux' else None) and
            observed['environment']==environment and observed['dont_write_bytecode'] is True and
            child['returncode']==0 and child.get('error') is None and child.get('cleanup')==[] and 0<=child['elapsed_seconds']<=90,
            'Actual clean bounded physical helper child and nested-group supervision')
    return module


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode'); parser.add_argument('folder', type=Path)
    parser.add_argument('qualification', type=Path); parser.add_argument('qualification_sha256')
    args = parser.parse_args()
    require(args.folder == HERE / 'native-FIRST', 'Only the admitted owned output directory')
    if args.mode == 'finalize': finalize(args.folder, args.qualification, args.qualification_sha256)
    else:
        require(args.mode.isdecimal(), 'Only exact numeric expert or finalize child')
        worker(int(args.mode), args.folder, args.qualification, args.qualification_sha256)
