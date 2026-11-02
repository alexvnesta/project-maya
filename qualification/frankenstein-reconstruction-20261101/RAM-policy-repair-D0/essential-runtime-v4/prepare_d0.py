"""Metadata only: new RAM policy, exact unchanged candidate and request bodies.
No service, inference, drain, restart or window action. Old C0 remains failed.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys

H = Path(__file__).resolve().parent
Q = H.parent
DC = Q.parent
E = DC.parent


def main():
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(DC/'maya-s-comparison-v1'))
    import acquire
    gate = acquire.SelectedGate(); gate()
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (512*2**20,)*2)
    os.nice(15)
    spec = importlib.util.spec_from_file_location('essential4_metadata_runtime', H/'runtime.py')
    rt = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt)
    read = lambda p: json.loads(Path(p).read_text())
    previous = Q/'essential-runtime-v3/qualification.json'
    assert rt.sha(previous) == 'a1b3aa3bcf1b1d59029b9314f2a6a327eb871917c0702f5799e69a1e2289b237'
    q = read(previous)
    def add(p):
        p = Path(p); assert rt.fingerprint(p)[2] <= 512*2**20
        value = rt.sha(p)
        assert str(p) not in q['files'] or q['files'][str(p)] == value, str(p)
        q['files'][str(p)] = value
    def folder(root):
        for f in sorted(Path(root).rglob('*')):
            if f.is_file() and '__pycache__' not in f.parts and f.name not in ('qualification.json','arms.json') and not f.name.endswith('-admission.json'):
                add(f)
    report = Q/'FINAL_ESSENTIAL_RESULT_FIRST.json'
    assert rt.sha(report) == '2c36b66a3ba46cd69290c367bdd0c076d5727d5407b062fb728663d6d4c0360f'
    report0 = read(report)
    assert report0['promotion_performed'] is False
    add(report); add(previous)
    old = read(Q/'essential-runtime-v3/arms.json')
    assert set(old) == {'C0'} and old['C0']['attempted'] is True
    add(Q/'essential-runtime-v3/arms.json')
    failed = Path(old['C0']['output'])
    for name in ('native/server-cleanup.json','private-memory-fence.json','private-memory-fence-restored.json','case-progress.json'):
        add(failed/name)
    close = read(failed/'native/server-cleanup.json')
    assert close['passed'] is False and close['native_close'][0]['returncode'] == -9
    outer = Q/'launch-custody-v1/capture-essential3-C0-FIRST'
    assert read(outer/'controller-exit.json')['returncode'] == 1
    folder(outer)
    state = read(E/'STATE.json'); recovered = state['s2essential3_recovery_current']
    assert recovered['active'] is False and recovered['result']['verified']['passed'] is True
    assert recovered['result']['start_binding'] == gate.host.start_binding
    folder(Q/'essential-recovery-v2')
    for name in ('capture-essential3-recovery-health-FIRST','capture-essential3-recovery-restore-FIRST'):
        folder(Q/'launch-custody-v1'/name)
    folder(H)
    q.update(mode=rt.MODE, selected_binding=copy.deepcopy(gate.host.start_binding),
        CPU_review=str(H/'ROOT_SOURCE_REVIEW.json'),
        CPU={p:{'receipt':str(H/('CPU-FIRST-'+p+'.json')),'child':str(H/('CPU-FIRST-'+p)/'child.json'),'log':str(H/('CPU-FIRST-'+p)/'child.log')} for p in ('darwin','linux')},
        memory_policy={'private_max':88*2**30,'host_reserve':4*2**30,'post_stop_floor':92*2**30,'private_swap':0},
        previous_C0_failed_and_not_regraded=True,
        authorization='Alex explicitly requested obsolete ClickHouse-era RAM reserve be fixed; bounded fresh D0 under new RAM envelope, model/settings unchanged')
    q['profiles'] = {'D0':copy.deepcopy(q['profiles']['C0']), 'A2':copy.deepcopy(q['profiles']['A1'])}
    # Existing manifests are unchanged frozen requests and exact source-aligned IDs.
    modules = rt.helpers(q)
    for arm in ('D0','A2'):
        rt.fixture_contract(read(q['profiles'][arm]['manifest']), modules[-2], arm)
    target = H/'qualification.json'; assert not target.exists()
    with target.open('x') as f: json.dump(q, f, indent=2, allow_nan=False); f.write('\n')
    pin = rt.sha(target); rt.qualified(pin, 'D0')
    with (H/'arms.json').open('x') as f: json.dump({}, f); f.write('\n')
    print(json.dumps({'passed':True,'qualification_sha256':pin,'files':len(q['files']),
        'binding':gate.host.start_binding,'memory_policy':q['memory_policy'],'model_executed':False}))


if __name__ == '__main__': main()
