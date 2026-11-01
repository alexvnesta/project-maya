"""ROOT metadata-only admission freeze. No inference, service or launch action."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import sys

H=Path(__file__).resolve().parent
Q=H.parent
DC=Q.parent
E=DC.parent
R=E.parent
D=Path('/home/alex/deepseek-hosted-20261025')

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def emit(p,x):
    with Path(p).open('x') as f:json.dump(x,f,indent=2,allow_nan=False);f.write('\n')
def load(n,p):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
    assert sys.platform=='linux' and str(R)=='/home/alex/strata-deepseek-test-20261024'
    sys.dont_write_bytecode=True;sys.path.insert(0,str(DC/'maya-s-comparison-v1'))
    import acquire
    gate=acquire.SelectedGate();gate()
    resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(512*2**20,)*2);os.nice(15)
    p=load('p0_admission',H/'placement.py');p.support()
    assert not (H/'qualification.json').exists() and not (H/'arms.json').exists()
    assert shutil.disk_usage('/').free>=132*2**30
    files={}
    def add(path,pin=None):
        path=Path(path)
        assert path.resolve()==path and path.is_file() and not path.is_symlink() and path.stat().st_size<=512*2**20,str(path)
        h=sha(path)
        if pin is not None:assert h==pin,str(path)
        files[str(path)]=h
    def metadata(root):
        for path in sorted(Path(root).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:add(path)
    # Existing qualified source/CPU proofs, all actual build terminal receipts.
    for path in (H/'placement.py',H/'test_placement.py',H/'run_cpu.py',H/'ROOT_SOURCE_REVIEW.json',H/'CANDIDATE_LAYOUT.json',H/'prepare_p0.py'):
        add(path)
    for label in ('mac','ubuntu'):add(H/('CPU-FIRST-'+label+'.json'))
    for label in ('darwin','linux'):metadata(H/('CPU-FIRST-'+label))
    p.cpu_contract({k:read(H/('CPU-FIRST-'+k+'.json')) for k in ('mac','ubuntu')},{n:sha(H/n) for n in p.SOURCES})
    for name in ('native-engine-v2','native-build-v2/configure-r4-FIRST','native-build-v2/compile-r4-FIRST'):
        metadata(Q/name)
    for name in ('SOURCE_MANIFEST_FIRST.json','ROOT_BUILD_R4_SOURCE_REVIEW.json','compile-r4-qualification.json','configure-r4-qualification.json','FIRST_BUILD_COMPLETION.json'):
        add(Q/'native-build-v2'/name)
    cq=read(Q/'native-build-v2/compile-r4-qualification.json')
    prefix=str(Q/'native-build-v2/source-FIRST')+'/'
    source_entries={n:h for n,h in cq['files'].items() if n.startswith(prefix)}
    assert len(source_entries)==724,len(source_entries)
    for n,h in source_entries.items():add(n,h)
    build=read(Q/'native-build-v2/FIRST_BUILD_COMPLETION.json')
    assert build['passed'] is True and build['configure_returncode']==build['compile_returncode']==0 and build['owned_claim_released'] is True
    add(p.NATIVE,build['artifact_sha256'])
    for folder in ('configure-r4-FIRST','compile-r4-FIRST'):
        root=Q/'native-build-v2'/folder
        child,supervision=read(root/'child.json'),read(root/'supervision.json')
        assert child['returncode']==0 and not child.get('cleanup') and supervision['passed'] is True
    # No mass rehash: actual complete published ALL8 hashes plus stable inode snapshots.
    base=Q/'base-acquisition-v2';terminal=read(base/'acquisition-state.json');manifest=read(base/'ASSET_MANIFEST.json')
    assert terminal['status']=='ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN' and terminal['returncode']==0 and len(terminal['files'])==len(manifest['files'])==8
    assert terminal['manifest_sha256']==sha(base/'ASSET_MANIFEST.json')=='22ecce3e7085e29520fadaa67d603beb8cc0905f834ff3563029f6038825034b'
    chain=load('p0_publication',Q/'publication-chain-v3/chain.py')
    artifacts={}
    for row,spec in zip(terminal['files'],manifest['files']):
        assert row['path']==spec['path'] and row['bytes']==spec['size'] and row['sha256']==spec['sha256'] and row['status'] in ('DOWNLOADED_VERIFIED','VERIFIED_EXISTING')
        path=Q/'base-acquisition-v1/assets'/spec['path'];fp=chain.fingerprint(path);assert fp[2]==spec['size']
        artifacts[str(path)]={'sha256':spec['sha256'],'fingerprint':fp,'basis':'Published complete acquisition SHA; postpublication fingerprint, outer exit UNKNOWN'}
    lock=Q/'base-acquisition-v1/acquisition.lock'
    with chain.writer_free({'path':str(lock),'fingerprint':chain.fingerprint(lock)}):pass
    assert chain.absent(terminal['pid'])
    metadata(base)
    # Audit actual NEW assembly receipts; original failed join remains failed.
    assembly=Q/'iq3s-assembly-v3';aq=read(assembly/'qualification.json');ap=sha(assembly/'qualification.json')
    for n,h in aq['files'].items():add(n,h)
    for i,proofs in aq['part_proof_sha256'].items():
        stem=Q/'iq3s-bulk-v1/conversion-FIRST/parts'/('%04d'%int(i))
        for suffix,h in proofs.items():add(stem.with_suffix(suffix),h)
    metadata(assembly/'assembly-FIRST');add(assembly/'qualification.json');add(assembly/'assembly.py')
    metadata(Q/'launch-custody-v1/capture-assembly-FIRST');add(Q/'launch-custody-v1/launch.py')
    result=read(assembly/'assembly-FIRST/result.json');artifact=Path(result['artifact_path'])
    snapshot={'schema':'s2-publication-fingerprints-v1','kind':'bounded-overlay-join','source_result_path':str(assembly/'assembly-FIRST/result.json'),
              'source_result_sha256':sha(assembly/'assembly-FIRST/result.json'),'files':{str(artifact):{'fingerprint':chain.fingerprint(artifact),'published_inode':result['source_inode']}}}
    snap=assembly/'PUBLICATION_SNAPSHOT_FIRST.json'
    if snap.exists():assert read(snap)==snapshot
    else:emit(snap,snapshot)
    add(snap)
    group={'kind':'bounded-overlay-join','source':str(assembly/'assembly.py'),'qualification':str(assembly/'qualification.json'),
           'result':str(assembly/'assembly-FIRST/result.json'),'artifact':str(artifact),'publication_snapshot':str(snap),
           'controller_start':str(Q/'launch-custody-v1/capture-assembly-FIRST/controller-start.json'),
           'controller_exit':str(Q/'launch-custody-v1/capture-assembly-FIRST/controller-exit.json'),'raw_paths':list(files)}
    publication={'files':files};context=chain.source_qualification(publication,group)
    chain.overlay_group(publication,group,context)
    artifacts[str(artifact)]={'sha256':result['sha256'],'fingerprint':result['fingerprint'],'basis':'Separate new31group assembly and captured actual outer exit0; original join -9 preserved'}
    metadata(Q/'candidate-pack-v1/pack-FIRST');add(Q/'candidate-pack-v1/CONSTRUCTION_FIRST.json')
    for n in ('construct_pack.py','metadata.py','ROOT_SOURCE_REVIEW.json','CPU-FIRST-mac.json','CPU-FIRST-ubuntu.json','child-FIRST-mac.json','child-FIRST-ubuntu.json'):
        add(Q/'candidate-pack-v1'/n)
    # Exact loaded Python dependency origins, selected config/canonical window and native proof.
    for module in tuple(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name:
            path=Path(name)
            if path.is_absolute() and path.is_relative_to(R) and path.suffix=='.py':add(path)
    for relative,pin in list(p.SUPPORT.values())+list(p.TRANSITIVE.values()):add(DC/relative,pin)
    add(D/'config.json',p.BASE_SHA);add(R/'window.py',p.WINDOW_SHA)
    emit(H/'MATERIALIZATION_ADMISSION_FIRST.json',{'passed':True,'selected_binding':gate.host.start_binding,'base_assets':artifacts,
         'original_join_failure_preserved':True,'native1870_materialization':'PENDING actualP0 expert IDs','no_inference':True})
    add(H/'MATERIALIZATION_ADMISSION_FIRST.json')
    q={'entire_source_tests_driver_manually_read':True,'mode':'placement','selected_binding':gate.host.start_binding,
       'context_total':1048576,'output_allowance':262144,'inference_requests':0,'native_sha256':build['artifact_sha256'],
       'weight_materialization_closed':True,'materialization_scope':'All8MayaS and newIQ3S overlay only; native1870 selection needs this no-inference P0',
       'files':files,'ROOT_admission':'ONE new P0 no-inference allocation only; no benchmark/model/promotion',
       'large_assets':artifacts}
    emit(H/'qualification.json',q);pin=sha(H/'qualification.json');p.qualified(pin)
    emit(H/'arms.json',{})
    plan={'ROOT_explicit_admission':True,'no_replay':True,'target_owns_bounds_and_restore':True,
          'argv':[str(R/'venv/bin/python3.14'),'-I','-B',str(H/'placement.py'),'--run'],
          'target_source_sha256':sha(H/'placement.py'),'cwd':str(H),'output':str(Q/'launch-custody-v1/capture-placement-P0-FIRST')}
    emit(Q/'launch-custody-v1/placement-P0-FIRST-plan.json',plan)
    print(json.dumps({'qualification_sha256':pin,'files':len(files),'large_assets':len(artifacts),
        'launch_plan_sha256':sha(Q/'launch-custody-v1/placement-P0-FIRST-plan.json')}))

if __name__=='__main__':main()
