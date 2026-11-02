"""Local host-memory policy for the separately authorized essential4 run.

No system-wide tuning or action at import. Original passed modules and receipts
retain their old values. The native's conservative startup expert check is
unchanged; this governs the whole private API/native process and live requests.
"""
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
DC = HERE.parents[1]
D = Path('/home/alex/deepseek-hosted-20261025')
MEMORY_MAX = 88 * 2**30
HOST_MARGIN = 4 * 2**30
POST_STOP_FLOOR = MEMORY_MAX + HOST_MARGIN
OLD_RUNTIME_SHA = '1811228e83217b961ae4ffed9c430f49edf10c3af999b4fd6753518a25001e58'


class ResourceDeferred(RuntimeError): pass


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def emit(path, value):
    path = Path(path)
    require(path.parent.is_dir() and not path.is_symlink(), 'Owned receipt path required')
    tmp = path.with_name(path.name + '.tmp')
    require(not tmp.exists() and not tmp.is_symlink(), 'Preserve receipt residue')
    with tmp.open('x') as f: f.write(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def memory_available():
    values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    value, unit = values['MemAvailable'].split()
    require(value.isdecimal() and unit == 'kB', 'Typed available physical RAM required')
    return int(value) * 1024


def memory_floor(read, *, clock=time.monotonic, pause=time.sleep):
    began = clock()
    while True:
        available = read(); elapsed = clock() - began
        require(type(available) is int and available >= 0 and elapsed >= 0, 'Actual available memory/clock')
        if elapsed <= 60 and available >= POST_STOP_FLOOR: return available
        if elapsed >= 60: raise ResourceDeferred('Post-stop physical92GiB floor unavailable; no private attempt')
        pause(min(1, 60 - elapsed))


def old_runtime():
    path = DC/'maya-s-comparison-v1/performance-v2/pv_runtime.py'
    require(path.resolve() == path and not path.is_symlink() and sha(path) == OLD_RUNTIME_SHA, 'Exact old lifecycle source')
    old = sys.modules.get('pv_runtime')
    require(old is not None and Path(old.__file__) == path, 'Exact already checked lifecycle runtime')
    return old


def lifecycle_helper(): return old_runtime().lifecycle_helper()


def original_module(name): return old_runtime().original_module(name)
