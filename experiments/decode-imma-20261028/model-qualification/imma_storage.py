"""Pure selected-source storage bounds and numerical-native-only FSIZE factory.

No filesystem writes, limit changes or model imports happen at import time.
Caller must separately prove fresh real owned paths, four requests, pinned pack
file-name/version inventory, no inherited cache, and exact selected geometry.
"""
import hashlib
from pathlib import PurePosixPath
import resource
import signal

MIB = 1 << 20
HARD_FILE_BYTES = 512 * MIB
SOFT_DUMP_BYTES = 1024 * MIB
MAX_DUMP_FILES = 4
MAX_PROMPT = 12000
MAX_GENERATED = 32768
ROW_BYTES = 129280 * 4
PACK_SHA = '48c01d890cbe53efafdacf50bf704437439f738f86787e6e529f6b5a62cd001c'
RATIOS = (0, 0) + (2,) * 18 + (1,) * 20 + (0,) * 3
KV_SOURCES = (2, 8, 14, 20)
INDEX_SOURCES = (2, 8, 14, 20, 24, 28, 32, 36)


def uint(value, name, maximum=None):
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise ValueError('Invalid ' + name)
    return value


def geometry(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != PACK_SHA:
        raise ValueError('Selected immutable pack metadata required')
    fields = {}
    for line in raw.decode('utf-8').splitlines():
        key, value = line.split(' ', 1)
        if key in fields:
            raise ValueError('Duplicate geometry field')
        fields[key] = value
    exact = {'num_hidden_layers': '40', 'head_dim': '512', 'index_head_dim': '128',
             'sliding_window': '128', 'n_routed_experts': '384', 'hidden_size': '5120',
             'max_position_embeddings': '1048576', 'dspark_target_layer_ids': '37,38,39',
             'compress_ratios': ','.join(map(str, RATIOS)),
             'kv_source_layer_ids': ','.join(map(str, KV_SOURCES)),
             'index_source_layer_ids': ','.join(map(str, INDEX_SOURCES))}
    if any(fields.get(k) != v for k, v in exact.items()):
        raise ValueError('Unsupported geometry')
    return {'layers': 43, 'head_dim': 512, 'index_head_dim': 128, 'window': 128,
            'ratios': RATIOS, 'kv_sources': KV_SOURCES, 'index_sources': INDEX_SOURCES,
            'experts_per_layer_profile': 384}


def selected_geometry(g):
    expected = {'layers': 43, 'head_dim': 512, 'index_head_dim': 128, 'window': 128,
                'ratios': RATIOS, 'kv_sources': KV_SOURCES, 'index_sources': INDEX_SOURCES,
                'experts_per_layer_profile': 384}
    if type(g) is not dict or g != expected or any(type(g[k]) is not int for k in
            ('layers', 'head_dim', 'index_head_dim', 'window', 'experts_per_layer_profile')):
        raise ValueError('Only the exact selected geometry is covered')
    if any(type(g[k]) is not tuple or any(type(x) is not int for x in g[k])
           for k in ('ratios', 'kv_sources', 'index_sources')):
        raise ValueError('Geometry arrays must be exact integer tuples')


def row_bytes(fmt, dim):
    uint(dim, 'row dimension')
    if dim == 0 or dim % 32:
        raise ValueError('Selected packed row dimension must be a positive multiple of32')
    if fmt == 'fp8':
        size = dim + dim // 32
    elif fmt == 'fp4':
        size = dim // 2 + dim // 16
    elif fmt == 'fp4p':
        size = dim // 2 + dim // 32
    else:
        raise ValueError('Unknown selected row format')
    return (size + 15) // 16 * 16


def check_bytes(g):
    selected_geometry(g)
    # c_kv exists only for ratio>1 KV-source layers; consumers do not own it.
    partial = sum(2 * g['ratios'][i] * g['head_dim'] * 4 for i in g['kv_sources'] if g['ratios'][i] > 1)
    return 16 + g['layers'] * g['window'] * row_bytes('fp8', g['head_dim']) + partial


def slot_bytes(g, pos, identity_bytes, checkpoints=3):
    selected_geometry(g)
    uint(pos, 'position', MAX_PROMPT + MAX_GENERATED)
    uint(identity_bytes, 'identity byte length', MIB)
    uint(checkpoints, 'checkpoint count', 3)
    if not identity_bytes:
        raise ValueError('Nonempty actual identity bound required')
    rings_and_partials = check_bytes(g) - 16
    sources = sum(8 + (pos // max(1, g['ratios'][i])) *
                  (row_bytes('fp4', g['head_dim']) + row_bytes('fp4p', g['index_head_dim']))
                  for i in g['kv_sources'])
    return 24 + identity_bytes + pos * 4 + g['layers'] * 16 + rings_and_partials + sources + 8 + checkpoints * check_bytes(g) + 8


def meta_bytes(pos, identity_bytes, checkpoints=3):
    uint(pos, 'position', MAX_PROMPT + MAX_GENERATED)
    uint(identity_bytes, 'identity byte length', MIB)
    uint(checkpoints, 'checkpoint count', 3)
    if not identity_bytes:
        raise ValueError('Nonempty identity bound required')
    return 48 + identity_bytes + pos * 4 + checkpoints * 8


def identity_upper_bound(engine_version, pack_files):
    """Conservative byte bound from COMPLETE pinned pk.files names and version.

    File sizes are unsigned64 so use20 decimal digits each. Paths supplied here
    must be exactly pk.files values, not guessed basenames or a partial list.
    Caller binds completeness to its immutable pack input inventory.
    """
    if type(engine_version) is not str or not engine_version or len(engine_version.encode()) > 4096:
        raise ValueError('Pinned engine version required')
    if type(pack_files) not in (list, tuple) or not 1 <= len(pack_files) <= 1024:
        raise ValueError('Complete nonempty pinned pack filename inventory required')
    if any(type(n) is not str or not n or '\x00' in n or len(n.encode()) > 4096 for n in pack_files):
        raise ValueError('Invalid pack filename')
    if len(set(pack_files)) != len(pack_files):
        raise ValueError('Duplicate pack filename')
    s = ('maya-ds4-session-2 engine=' + engine_version + ' mtp=3 dim=5120 hd=512 win=128 ratios=' +
         ''.join(str(r) + ',' for r in RATIOS) + ' kv=' + ''.join(str(i) + ',' for i in KV_SOURCES) +
         ' ix=' + ''.join(str(i) + ',' for i in INDEX_SOURCES))
    for name in ('ds4.txt', 'engram.bin', 'tensors.txt'):
        s += ' ' + name + ':' + '9' * 20
    for name in pack_files:
        s += ' ' + name + ':' + '9' * 20
    bound = len(s.encode('utf-8'))
    if bound > MIB:
        raise ValueError('Identity bound exceeds conservative1MiB allowance')
    return bound


def storage_bound(g, engine_version, pack_files):
    selected_geometry(g)
    identity = identity_upper_bound(engine_version, pack_files)
    pos = MAX_PROMPT + MAX_GENERATED
    sizes = {'slot_bin_or_tmp': slot_bytes(g, pos, identity),
             'slot_meta_or_tmp': meta_bytes(pos, identity),
             'expert_profile_or_tmp': g['layers'] * g['experts_per_layer_profile'] * 4}
    if any(v >= HARD_FILE_BYTES for v in sizes.values()):
        raise ValueError('HOLD: legitimate selected private write can reach FSIZE')
    return {'max_position': pos, 'identity_bytes_upper_bound': identity, 'max_checkpoints': 3,
            'native_owned_file_bounds': sizes, 'hard_per_file': HARD_FILE_BYTES,
            'soft_dump_aggregate': SOFT_DUMP_BYTES, 'hard_dump_aggregate': MAX_DUMP_FILES * HARD_FILE_BYTES,
            'max_dump_files': MAX_DUMP_FILES,
            'scope': 'Fresh four-case native numerical child only; no imported cache or other requests. '
                     'API image staging, driver caches, logs and other child processes require separate caller inventory.'}


def native_fsize_preexec(g, engine_version, pack_files, *, process_kind):
    """Compose into the caller's existing native preexec; never apply to API/timed arms."""
    if process_kind != 'UNMEASURED_NUMERICAL_NATIVE':
        raise ValueError('FSIZE is forbidden outside the numerical native child')
    storage_bound(g, engine_version, pack_files)
    def apply_in_native_child():
        soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
        if any(v != resource.RLIM_INFINITY and v < HARD_FILE_BYTES for v in (soft, hard)):
            raise ValueError('Do not relax a stricter inherited FSIZE limit')
        signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
        resource.setrlimit(resource.RLIMIT_FSIZE, (HARD_FILE_BYTES, HARD_FILE_BYTES))
    return apply_in_native_child


def dump_policy(root, entries, *, complete=False):
    """Pure caller-supplied lstat snapshot; never resolve or inspect filesystem paths.

    Snapshot entries: exact path/bytes/regular/symlink/nlink. Caller must
    validate real owned ancestors and kill/cancel on any HOLD via existing owner.
    Soft limit can be overshot between polls; per-file child FSIZE is the hard cap.
    """
    if type(root) is not str or not root.startswith('/') or root.startswith('//') or '..' in root.split('/') or '\x00' in root:
        raise ValueError('Absolute canonical owned dump root required')
    r = PurePosixPath(root)
    if str(r) != root or type(entries) is not list or len(entries) > MAX_DUMP_FILES or type(complete) is not bool:
        raise ValueError('Invalid dump path/count/snapshot')
    indexes, total, hard = [], 0, False
    for e in entries:
        if type(e) is not dict or set(e) != {'path', 'bytes', 'regular', 'symlink', 'nlink'}:
            raise ValueError('Exact lstat receipt fields required')
        if e['regular'] is not True or e['symlink'] is not False:
            raise ValueError('Owned regular non-symlink dump required')
        if type(e['nlink']) is not int or e['nlink'] != 1:
            raise ValueError('Hardlinked dump is forbidden')
        if type(e['path']) is not str:
            raise ValueError('Invalid path')
        valid = {str(r / ('logits.' + str(i) + '.f32')): i for i in range(1, 5)}
        if e['path'] not in valid or valid[e['path']] in indexes:
            raise ValueError('Unexpected or repeated dump path')
        indexes.append(valid[e['path']])
        size = uint(e['bytes'], 'dump byte count')
        total += size
        hard = hard or size >= HARD_FILE_BYTES
        if complete and (size == 0 or size % ROW_BYTES):
            raise ValueError('Incomplete float32 vocabulary rows')
    if sorted(indexes) != list(range(1, len(indexes) + 1)) or (complete and len(entries) != 4):
        raise ValueError('Missing or gapped dump receipt')
    hold = hard or total >= SOFT_DUMP_BYTES
    return {'status': 'INCOMPLETE_HOLD' if hold else ('COMPLETE_SIZE_ONLY' if complete else 'WITHIN_BUDGET'),
            'total_bytes': total, 'count': len(entries), 'hard_limit_reached': hard,
            'soft_limit_reached': total >= SOFT_DUMP_BYTES, 'retry_allowed': False,
            'numerical_quality_or_equivalence_pass': False}
