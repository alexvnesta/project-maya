"""Prospective numerical owner composition; no action at import."""
from contextlib import contextmanager
import json
import os
from pathlib import Path

import cpu_model_dependencies as dependencies

fence = dependencies.load_fence()
MEMORY_MAX = fence.runtime.MEMORY_MAX
HOST_MARGIN = fence.runtime.HOST_MARGIN


def require(ok, why):
    if not ok:
        raise ValueError(why)


def memory_available():
    return fence.runtime.memory_available()


def startup(a, old, ready, health, models, log, allowed_cuts):
    return fence.startup(a, old, ready, health, models, log, allowed_cuts)


def stop_api(old, proc, folder, emit):
    """Retain the actual API Popen wait status, including every failed cleanup."""
    primary = None
    value = {'server_pid': proc.pid, 'actual_Popen_returncode': None, 'passed': False}
    try:
        cleanup = old.stop_server(proc, folder, timeout=100)
        rc = proc.wait(timeout=0) if proc.poll() is not None else None
        value.update(actual_Popen_returncode=rc, server_cleanup=cleanup)
        require(type(rc) is int and rc == 0 and cleanup.get('passed') is True
                and cleanup.get('server_pid') == proc.pid and cleanup.get('server_returncode') == rc,
                'Actual private API wait0 and native close0 required')
        value['passed'] = True
        return value
    except BaseException as exc:
        primary = exc; value['error'] = repr(exc)
        raise
    finally:
        value['actual_Popen_returncode'] = proc.poll()
        try:
            emit(Path(folder) / 'private-api-exit.json', value)
        except BaseException as exc:
            if primary is None:
                raise
            primary.add_note('Actual API-exit receipt: ' + repr(exc))


def own_ancestry(group, *, proc=Path('/proc'), current=None):
    """Only the phase and its still-live ancestors may remain in the window."""
    pid = os.getpid() if current is None else current
    require(type(pid) is int and pid > 1, 'Typed current phase PID required')
    result = set()
    for _ in range(128):
        require(pid not in result, 'Process ancestry cycle')
        path = Path(proc) / str(pid)
        relative = path.joinpath('cgroup').read_text().strip().splitlines()
        require(len(relative) == 1 and relative[0].startswith('0::/'), 'Unified phase ancestor cgroup required')
        if relative[0][3:] != group:
            break
        result.add(pid)
        fields = path.joinpath('stat').read_text().rsplit(') ', 1)[1].split()
        require(fields[1].isdecimal(), 'Typed phase parent PID required')
        parent = int(fields[1])
        if parent <= 1:
            break
        pid = parent
    else:
        raise ValueError('Phase ancestry bound exceeded')
    require(result, 'Current phase is outside the owned window')
    return result


def private_closed(folder, handles, record, *, proc=Path('/proc'), current=None):
    require(fence.private_children_closed(folder, handles, proc=proc), 'Private API/native children remain')
    for process in handles:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise ValueError('Owned private API group still exists')
    group = Path(record['cgroup'])
    def no_subgroups():
        require(all(not child.is_symlink() and not child.is_dir() for child in group.iterdir()),
                'Nested owned cgroup prevents descendant closure proof')
    no_subgroups()
    allowed = own_ancestry(record['unit_before']['ControlGroup'], proc=proc, current=current)
    lines = (group / 'cgroup.procs').read_text().splitlines()
    require(all(x.isdecimal() for x in lines), 'Typed owned cgroup process inventory required')
    actual = {int(x) for x in lines}
    require(actual <= allowed, 'Unregistered private descendant remains in the owned cgroup')
    no_subgroups()
    return {'passed': True, 'remaining_ancestor_pids': sorted(actual), 'allowed_ancestor_pids': sorted(allowed)}


@contextmanager
def fenced_phase(output):
    """Never relax properties while an unknown API/native descendant remains."""
    record = fence.install_private_fence(output)
    handles = []; primary = None
    try:
        yield record, handles
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            closed = private_closed(Path(output) / 'native', handles, record)
            fence.runtime.emit(Path(output) / 'private-child-closure.json', closed)
            fence.restore_private_fence(record, children_closed=True)
        except BaseException as exc:
            if primary is None:
                raise
            primary.add_note('Owned memory fence/child closure: ' + repr(exc))


def fence_terminal(record):
    return fence.fence_terminal(record)


def fence_collected(output, metadata):
    return fence.fence_collected(output, metadata)
