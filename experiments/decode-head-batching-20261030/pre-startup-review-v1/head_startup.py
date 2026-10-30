"""Future head-family startup adapter. No late adoption, restart or inference.

The selected owner's unchanged restore_ds still owns its one start and1250s
deadline. Wait for systemd's initial MainPID before querying a native owner.
Once a positive MainPID or native binding is observed, replacement is a fault.
The failed Q8 run and its original owner source are never changed.
"""
import hashlib
from pathlib import Path

OWNER = Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/autonomous-optimization-12h-20261028/chunk4096-v1/activation-v1/activate_chunk4096.py')
OWNER_SHA = 'b2bb7676969661f98bf77d9969a840a4fcb44367f9644ab6f05ac19d70709056'


def capture(host, old_invocation, *, emit):
    before = host.unit_snapshot()
    if not before['invocation'] or before['invocation'] == old_invocation:
        return
    if host.start_invocation is None:
        host.start_invocation = before['invocation']
    if before['invocation'] != host.start_invocation:
        raise ValueError('Attempted unit invocation replaced')
    if type(before['main_pid']) is not int or before['main_pid'] < 0:
        raise ValueError('Invalid initial main PID')
    if before['main_pid'] == 0:
        if host.start_main_pid is not None or host.start_binding is not None:
            raise ValueError('Observed startup owner disappeared')
        # No owner is claimed. The unchanged outer start deadline bounds this.
        return
    if host.start_main_pid is None:
        host.start_main_pid = before['main_pid']
    if before['main_pid'] != host.start_main_pid:
        raise ValueError('Attempted unit main PID replaced')
    if before['state'] not in ['activating', 'active']:
        return
    actual = host.native_snapshot(before)
    after = host.unit_snapshot()
    if (before['invocation'], before['main_pid']) != (after['invocation'], after['main_pid']):
        raise ValueError('Unstable startup invocation; refuse capture')
    if actual is None:
        return
    if host.start_binding is not None and actual != host.start_binding:
        raise ValueError('Native changed during startup; never recapture')
    if host.start_binding is None:
        host.start_binding = actual
        host.restored_pid = actual['native_pid']
        emit(host.audit_dir / 'start-binding.json', actual)


def guarded_host(owner_module):
    """Compose only with the exact, already qualified selected4096 owner."""
    if Path(owner_module.__file__).resolve() != OWNER:
        raise ValueError('Foreign selected owner module')
    if hashlib.sha256(OWNER.read_bytes()).hexdigest() != OWNER_SHA:
        raise ValueError('Selected owner source changed')
    base = owner_module.ChunkProductionHost
    for name in ('capture_pending_start', 'restore_ds', 'guard_binding', 'native_snapshot', 'unit_snapshot'):
        if Path(getattr(base, name).__code__.co_filename).resolve() != OWNER:
            raise ValueError('Selected owner method origin changed')
    class HeadStartupHost(base):
        def capture_pending_start(self, old_invocation):
            return capture(self, old_invocation, emit=owner_module.emit)
    return HeadStartupHost
