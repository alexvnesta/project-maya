"""Small opt-in host-memory gate for NEW HTTP inference reservations.

The request guard does no tokenization, waiting, cancellation or automatic retry.
Startup may wait before its first request. No model settings or request data are
changed. This is a pressure safeguard, not a per-request memory bound.
"""
import math
from pathlib import Path
import time


class MemoryPressureError(RuntimeError):
    pass


def check_memory(env, meminfo=Path('/proc/meminfo'), pressure=Path('/proc/pressure/memory')):
    raw = env.get('STRATA_HOST_MEM_MIN_GIB', '')
    if raw == '':
        return None
    try:
        floor = float(raw)
        max_stall = float(env.get('STRATA_HOST_MEM_PSI_MAX', '10'))
        if not (math.isfinite(floor) and 0 < floor <= 1024
                and math.isfinite(max_stall) and 0 < max_stall <= 100):
            raise ValueError('invalid policy')
        values = {}
        for line in meminfo.read_text().splitlines():
            key, value = line.split(':', 1)
            values[key] = value.split()
        row = values['MemAvailable']
        if len(row) != 2 or row[1] != 'kB' or not row[0].isdecimal():
            raise ValueError('invalid available memory')
        available = int(row[0]) * 1024
        some = [line for line in pressure.read_text().splitlines() if line.startswith('some ')]
        if len(some) != 1:
            raise ValueError('missing memory pressure')
        fields = dict(item.split('=', 1) for item in some[0].split()[1:])
        stalled = float(fields['avg10'])
        if not math.isfinite(stalled) or not 0 <= stalled <= 100:
            raise ValueError('invalid memory pressure')
    except (OSError, KeyError, ValueError) as e:
        raise MemoryPressureError('Host memory safety readings unavailable') from e
    if available < floor * 2**30 or stalled >= max_stall:
        raise MemoryPressureError('Host memory pressure; retry later')
    return {'available_bytes': available, 'some_avg10': stalled, 'floor_GiB': floor}


def wait_for_safe_memory(env, deadline, *, checker=check_memory, clock=time.monotonic, sleep=time.sleep):
    """Wait for admission before the FIRST startup request, within its existing deadline.

    No HTTP call or inference retry is made here. A missing/unsafe reading remains
    fail-closed, and exhausting the original deadline fails startup.
    """
    while True:
        if clock() >= deadline:
            raise MemoryPressureError('Host memory was not safe before the existing startup deadline')
        try:
            return checker(env)
        except MemoryPressureError:
            left = deadline - clock()
            if left <= 0:
                raise
            sleep(min(3.0, left))
