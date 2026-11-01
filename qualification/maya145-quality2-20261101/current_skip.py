"""Pure Maya145 mode1 source/device/span reconciliation, never a run regrade.

Source: plan_chunks prints devs[L[20].dev].id. TP2's trunk lives on its lead
member; TP1 layer20 belongs to the trunk segment shown by CUDA1's first layer.
Old CUDA1-only observers and their failed raw receipts remain unchanged.
"""
import re

NATIVE_SHA='adff28a2d3a3f54ebfc0399e5e3ec7385f6fbb848e4e675fa1044cf7c6961f4f'
PATTERN=re.compile(r'ds4: prompt skip: layers 20-39 from CUDA([01]), ([1-9][0-9]*) early rows KV-only, 2668 kept')

def require(ok,why):
    if not ok:raise ValueError(why)

def source_device(startup,variant):
    require(variant in ('TP1','TP2') and type(startup) is dict and startup.get('passed') is True,'Explicit current startup/variant')
    pid=startup['native_pid'];actual=startup['actual_process'];engine=startup['current_engine']
    require(actual.get('native_sha256')==NATIVE_SHA,'Exact qualified Maya145 native source identity')
    require(type(pid) is int and pid>1 and actual['native_pid']==pid and all(actual.get(k) is True for k in ('argv_matches','controlled_env_matches','same_executable','owned_window_cgroup')),'Actual source-aligned startup identity')
    env=actual['controlled_env'];require(env.get('DS4_YOCO')==env.get('STRATA_DS4_PROMPT_SKIP')=='1','Actual unchanged mode1 flags')
    require(engine['passed'] is True and all(type(engine[k]) is list and engine[k]==[0,1] and all(type(x) is int for x in engine[k]) for k in ('Q8_devices','projection_devices')),'Actual source-specific startup checks')
    rows=engine['placement'];require(type(rows) is list and len(rows)==2 and all(type(r) is dict for r in rows),'Two actual placement rows')
    for row in rows:
        require(all(type(row[k]) is int for k in ('device','first_layer','last_layer','tp')) and row['device'] in (0,1) and 0<=row['first_layer']<=row['last_layer']<=42 and row['tp']==int(variant[-1]),'Typed matching actual placement')
    by={r['device']:r for r in rows};require(set(by)=={0,1},'Distinct GPU placement rows')
    if variant=='TP2':
        require(all(type(r['member']) is int and r['first_layer']==0 and r['last_layer']>=39 for r in rows) and sorted(r['member'] for r in rows)==[0,1],'Complete source TP2 trunk group')
        return next(r['device'] for r in rows if r['member']==0)
    require(all(r.get('member') is None for r in rows) and by[0]['first_layer']==0 and by[0]['last_layer']==42 and 1<=by[1]['first_layer']<=39 and by[1]['last_layer']==39,'Actual automatic TP1 trunk segments and drafter')
    return 1 if by[1]['first_layer']<=20 else 0

def activation(log,startup,variant,expected_early,*,complete):
    require(type(log) is str and type(complete) is bool and type(expected_early) is list and all(type(n) is int and n>0 for n in expected_early),'Typed frozen complete/partial activation expectation')
    device=source_device(startup,variant);rows=[]
    for line in log.splitlines():
        if 'ds4: prompt skip' not in line:continue
        match=PATTERN.fullmatch(line);require(match is not None,'Exact source layer span, retained rows and typed marker')
        require(int(match[1])==device,'Skip source device differs from actual placement')
        rows.append(int(match[2]))
    require(rows==(expected_early if complete else expected_early[:len(rows)]) and len(rows)<=len(expected_early),'Exact ordered cold activation counts; partial evidence cannot imply completion')
    return {'mode':1,'source':20,'last_layer':39,'source_device':device,'retained_rows':2668,'activation_early_rows':rows,'complete_evidence':complete,'scope':'ACTIVATION_SOURCE_ONLY_NO_PHASE_LIFECYCLE_QUALITY_SPEED_OR_REGRADE'}
