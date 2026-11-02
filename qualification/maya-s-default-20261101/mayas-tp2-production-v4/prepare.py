"""Bounded explicit-user-switch metadata relocation; no serving mutation."""
import copy
import datetime
import json
import os
from pathlib import Path
import resource
import sys

H = Path(__file__).resolve().parent
sys.path.insert(0,str(H))
import activate_mayas as a
import policy as p
import run_cpu as driver


def main():
    p.require(sys.platform == 'linux' and H == p.P, 'Canonical physical Ubuntu metadata preparation')
    sys.path.insert(0,str(p.DC/'iq2s-persistent-v1/model-v1'));import iq2s_model_runtime as base_runtime
    p.require(a.sha(Path(base_runtime.__file__)) == '1516752104307ffc159fbb80afd972ccd43c5cb9a96cf3e47de126f62482d510', 'Qualified baseline owner source')
    a.legacy_import_guard();owner,_ = base_runtime.support()
    class SwitchGate:
        def __init__(self):
            self.host = owner.ChunkProductionHost()
            self.host.start_binding = base_runtime.current_binding(a.read(p.E/'STATE.json'))
            self()
        def __call__(self):
            self.host.guard_binding(self.host.start_binding['native_pid'])
            p.switch_guard_contract(a.read(p.E/'STATE.json'),self.host.start_binding,self.host.get('/health'),user_interrupt_authorized=True)
    gate = SwitchGate()
    resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(512*2**20,)*2);os.nice(15)
    review = a.read(H/'ROOT_SOURCE_REVIEW.json')
    for platform in ('darwin','linux'):
        a.cpu_contract(a.read(H/('CPU-FIRST-'+platform+'.json')),a.read(H/('CPU-FIRST-'+platform)/'child.json'),review,platform)
    p.require(review['source_map'] == {n:a.sha(H/n) for n in a.SOURCES}, 'Actual source unchanged since FIRST CPU')
    p.require(driver.inputs() == review['input_map'], 'Actual metadata/config/parser inputs unchanged since FIRST CPU')
    qold_path = p.DC/'s2-reconstruction-v1/essential-runtime-v4/qualification.json'
    p.require(a.sha(qold_path) == '876aeb3cc60bcabd70fe8ad566ce90d63a20a863d91a75ab5156d01dd776ca5f', 'Exact recent publication fingerprints')
    prior = a.read(qold_path)
    base = a.read(H/'base-config.json');p.require(a.sha(H/'base-config.json') == a.sha(p.D/'config.json') == p.BASE_SHA, 'Actual baseline config')
    target = p.target_config(base);p.config_contract(base,target)
    meta = p.DC/'s2-reconstruction-v1/candidate-pack-v1'
    pins = a.read(meta/'BASE_METADATA_PINS.json');blobs = {n:(meta/'base-metadata'/n).read_bytes() for n in pins}
    outputs = p.rebind_metadata(blobs,pins)
    manifest = p.DC/'s2-reconstruction-v1/base-acquisition-v2/ASSET_MANIFEST.json'
    terminal = manifest.with_name('acquisition-state.json')
    p.require(a.sha(manifest) == '22ecce3e7085e29520fadaa67d603beb8cc0905f834ff3563029f6038825034b' and
              a.sha(terminal) == 'f0a3afafa55e93fc3aff35a375cfecac74e003e06bed18de856edcce4972713d', 'Exact complete published acquisition')
    m,t = a.read(manifest),a.read(terminal);p.require(len(m['files']) == len(t['files']) == 8, 'All eight assets')
    assets = {}
    for expected, actual in zip(m['files'],t['files']):
        path = p.ASSETS/expected['path'];p.require(actual['path'] == expected['path'] and actual['sha256'] == expected['sha256'] and
            actual['bytes'] == expected['size'], 'Published source size/SHA')
        fp = a.fingerprint(path)
        if str(path) in prior['large_verified']:
            verified = prior['large_verified'][str(path)]
            p.require(fp == verified['fingerprint'] and verified['sha256'] == expected['sha256'], 'Stable fully verified published asset')
        else: p.require(a.sha(path) == expected['sha256'] == prior['files'][str(path)], 'Exact small published metadata asset')
        assets[str(path)] = {'fingerprint':fp,'sha256':expected['sha256'],'published_manifest':str(manifest)}
    # Native vision is unchanged, shared, and retained. It is not a loser payload.
    vision = Path(p.VISION);p.require(str(vision) in prior['large_verified'], 'Prior verified native vision')
    assets[str(vision)] = copy.deepcopy(prior['large_verified'][str(vision)])
    p.require(a.fingerprint(vision) == assets[str(vision)]['fingerprint'] and a.sha(p.NATIVE) == p.NATIVE_SHA, 'Actual vision/native identity')
    gate()
    p.PACK.mkdir(exist_ok=False)
    for name, data in outputs.items():
        dest = p.PACK/name;dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('xb') as f:f.write(data)
    a.emit(H/'PACK_RELOCATION_FIRST.json',{'passed':True,'tensor_bytes_changed':False,'metadata_only':True,
        'outputs':{n:{'sha256':a.sha(p.PACK/n),'bytes':len(b)} for n,b in outputs.items()},
        'assets':assets,'native_sha256':p.NATIVE_SHA,'selected_before':gate.host.start_binding})
    a.emit(H/'candidate-config.json',target)
    base_release = a.read(H/'base-release.json')
    p.require(a.sha(p.D/'release.json') == a.sha(H/'base-release.json'), 'Actual baseline release')
    release_files = copy.deepcopy(base_release['files'])
    for name in ('ds4.txt','tensors.txt','engram.bin'):release_files.pop(str(p.E/'pack-native-vision-v1'/name))
    for name in outputs:release_files[str(p.PACK/name)] = a.sha(p.PACK/name)
    for name in ('hosting_preflight.py','hosting_ready.py'):release_files[str(p.D/name)] = a.sha(H/name)
    release_files[str(p.D/'config.json')] = a.sha(H/'candidate-config.json')
    release_files[str(p.D/'bin/maya-ds4')] = p.NATIVE_SHA
    release = {'id':a.RELEASE,'created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'parent_release':base_release['id'],
        'selected_backend':'maya','native_sha256':p.NATIVE_SHA,'profile_seed_sha256':base_release['profile_seed_sha256'],
        'public_endpoint':base_release['public_endpoint'],'files':release_files,'status':'ACTIVATING_EXPLICIT_USER_SELECTION',
        'production_active':False,'selection':{'model':'Published original Maya-S IQ2_XXS','TP':2,'CPU_experts':6490,'all_CPU_experts_RAM':True,
            'context_total':1048576,'output_allowance':262144,'drafter':'published Maya-S DSpark .65/max4, enabled','prefill_chunk':4096},
        'source_refs':{'native':'Maya1.1.45 tested adff28a2/build5c9ba2f','model_revision':m['revision'],'manifest':str(manifest)},
        'user_selection':'Explicit Maya-S TP2 default request; previous15.6percent cold-prefill regression remains disclosed, no new general speed superiority claim',
        'cache_namespace':str(p.CACHE),'served_model_alias':target['model_name']}
    a.emit(H/'candidate-release.json',release)
    q = {'root_entire_source_tests_read':True,'user_selected_MayaS_TP2':True,'context_total':1048576,'output_allowance':262144,
         'native_sha256':p.NATIVE_SHA,'selected_binding':copy.deepcopy(gate.host.start_binding),'assets':assets,'files':{},
         'target_config_sha256':a.sha(H/'candidate-config.json'),'target_preflight_sha256':a.sha(H/'hosting_preflight.py'),
         'target_ready_sha256':a.sha(H/'hosting_ready.py'),'base_release_sha256':a.sha(H/'base-release.json'),'target_release_files':release_files}
    def add(path, expected=None):
        path = Path(path);actual = a.sha(path)
        if expected is not None:p.require(actual == expected, 'Required unchanged source/proof: '+str(path))
        q['files'][str(path)] = actual
    # Exact inherited read-only lifecycle imports, all previously qualified by the latest closed mode.
    a.support({'files':prior['files']});sys.path.insert(0,str(p.DC/'prose-speed-v1'))
    for module in tuple(sys.modules.values()):
        path = Path(getattr(module,'__file__','') or '/')
        if path.is_absolute() and path.is_relative_to(p.E) and path.suffix == '.py' and not path.is_relative_to(p.P):
            p.require(str(path) in prior['files'], 'Unqualified inherited import: '+str(path));add(path,prior['files'][str(path)])
    for name in a.SOURCES:add(H/name)
    for name in ('ROOT_SOURCE_REVIEW.json','SOL_SOURCE_REVIEW_FIRST.json','base-config.json','base-release.json','candidate-config.json',
                 'candidate-release.json','PACK_RELOCATION_FIRST.json','TP2_STARTUP_FIXTURE.txt'):add(H/name)
    for platform in ('darwin','linux'):
        add(H/('CPU-FIRST-'+platform+'.json'))
        for name in ('child.json','child.log'):add(H/('CPU-FIRST-'+platform)/name)
    for name in outputs:add(p.PACK/name);add(meta/'base-metadata'/name,pins[name])
    for path in (manifest,terminal,meta/'BASE_METADATA_PINS.json',qold_path,p.NATIVE,p.DC/'prose-speed-v1/prose_measure.py',
                 p.DC/'prose-speed-v1/transport.py',p.DC/'maya145-directstate-v1/engine_profile.py',
                 p.DC/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'):add(path)
    a.emit(H/'qualification.json',q);a.qualified(a.sha(H/'qualification.json'))
    print(json.dumps({'passed':True,'qualification_sha256':a.sha(H/'qualification.json'),'files':len(q['files']),
        'config_sha256':q['target_config_sha256'],'native_sha256':p.NATIVE_SHA,'assets':len(assets),'model_or_service_started':False}))


if __name__ == '__main__': main()
