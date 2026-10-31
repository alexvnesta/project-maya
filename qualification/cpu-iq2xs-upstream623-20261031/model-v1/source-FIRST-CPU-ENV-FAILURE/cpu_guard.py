"""CPU-only healthy-host guard under the current chat's work-interruption authority.

This does not admit a GPU/private phase, model launch or service operation.
"""
import json
import shutil


def require(ok, message):
    if not ok:
        raise ValueError(message)


def health_contract(health, telemetry):
    require(type(health) is dict and type(telemetry) is dict, 'Typed hosting observations required')
    require(health.get('status') == 'ok' and health.get('service') == 'strata'
            and health.get('model') == 'deepseek-v4.1-flash-iq2-xs'
            and health.get('loaded') is True and health.get('images') is True
            and type(health.get('max_context')) is int and health['max_context'] == 1048576
            and type(health.get('busy')) is bool, 'Healthy exact selected model/capacity required')
    switcher = health.get('switcher'); work = telemetry.get('work')
    require(type(switcher) is dict and type(work) is dict, 'Switcher/work observations required')
    require(switcher.get('active_model') == switcher.get('default_model') == 'deepseek'
            and 'fault' in switcher and switcher['fault'] is None, 'Default selected model without fault required')
    for obj, names in ((switcher, ('inflight', 'waiting')),
                       (work, ('active', 'queued', 'admission_reserved'))):
        require(all(type(obj.get(k)) is int and obj[k] >= 0 for k in names),
                'Typed nonnegative hosting counters required')
    return {'ordinary_hosted_work_allowed_for_CPU_only': True,
            'busy': health['busy'],
            'switcher': {k: switcher[k] for k in ('inflight', 'waiting')},
            'work': {k: work[k] for k in ('active', 'queued', 'admission_reserved')}}


def guard(runtime, host, binding, state_path, reservation=None):
    """Retain ownership/phase/resource gates; permit only ordinary healthy work."""
    state = json.loads(state_path.read_text())
    for key in runtime.PHASE_KEYS:
        if key == 'active_cpu_build' and reservation is not None:
            require(state.get(key) == reservation, 'CPU reservation changed')
        else:
            require(not state.get(key), 'Active phase/build/pending restoration')
    require(runtime.current_binding(state) == binding, 'Selected owner changed')
    health_contract(host.get('/health'), host.get('/v1/telemetry'))
    host.guard_binding()
    require(shutil.disk_usage('/').free >= 132 * 2**30, 'Root132 unavailable')
    # Detect an owner/maintenance change across the observation reads.
    require(json.loads(state_path.read_text()) == state, 'Coordination changed across hosting observations')
    return state
