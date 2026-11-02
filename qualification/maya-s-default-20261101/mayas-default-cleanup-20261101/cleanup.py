"""Exact unused weights only. Reuse previously qualified durable unlink/lock code.

No services, inference, glob deletion, cache deletion, retries or model changes.
Current selection must remain exact. One persistent attempt; count actual unlinks.
"""
import argparse, datetime, hashlib, importlib.util, json, os, re, shutil, subprocess, sys
from pathlib import Path

H=Path(__file__).resolve().parent
DC=H.parent
R=Path('/home/alex/strata-deepseek-test-20261024')
E=R/'reliability-optimization-20261025'
P=DC/'mayas-tp2-production-v4'
NATIVE='adff28a2d3a3f54ebfc0399e5e3ec7385f6fbb848e4e675fa1044cf7c6961f4f'
CONFIG='12fb4c1731cca16b6f7e8dd17bcf0b7431f2c34f6d4cc3358e9e436fa9c7910a'
PRIMITIVE=DC/'model-selection-closeout-20261101/remove_exact_payloads_admitted.py'
PRIMITIVE_SHA='73700509519edb649084d942a348d7e76d397fcd4db818e6a8f35aaf36b61cff'

def require(ok,why):
    if not ok:raise ValueError(why)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def load_primitive():
    require(sha(PRIMITIVE)==PRIMITIVE_SHA,'Exact already qualified durable deletion primitive')
    spec=importlib.util.spec_from_file_location('qualified_unlink',PRIMITIVE)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def allowed(path):
    path=Path(path);q=DC/'s2-reconstruction-v1'
    if path.parent==R/'models/ista-iq2-xs':return re.fullmatch(r'DeepSeek-V4\.1-Flash-1017-GSQ-RCO-IQ2_XS-0000[1-4]-of-00004\.gguf',path.name) is not None
    if path.parent==R/'models/shared':return path.name in ('DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf','dspark-DeepSeek-V4.1-Flash-1017-Q8_0.gguf')
    if path.parent in (q/'iq3s-source-acquisition-v1/assets/original',Path('/data2/deepseek-frankenstein-evidence-20261101/unused-original-sources')):
        return re.fullmatch(r'model-000[0-4][0-9]-of-00048\.safetensors',path.name) is not None
    if path.parent==q/'iq3s-bulk-v1/conversion-FIRST/parts':return re.fullmatch(r'[0-9]{4}\.iq3s',path.name) is not None
    return path in (q/'native-payload-v3/native-FIRST/native.cpu',q/'iq3s-bulk-v1/conversion-FIRST/overlay.iq3s',
                    q/'iq3s-bulk-v1/conversion-FIRST/overlay.partial',DC/'maya-s-comparison-v1/assets/dspark/dspark.bin')

def plan_contract(plan):
    require(plan['schema']=='mayas-selected-unused-weights-v1' and plan['selected_native']==NATIVE and plan['selected_config']==CONFIG,'Exact Maya-S selection')
    rows=plan['rows'];paths=[v['path'] for v in rows]
    require(len(rows)==plan['count']>0 and len(set(paths))==len(paths) and all(allowed(p) for p in paths),'Unique explicit unused weight paths only')
    require(sum(v['signature']['size'] for v in rows)==plan['bytes'],'Exact byte accounting')
    protected={(v['dev'],v['ino']) for v in plan['protected'].values()}
    require(all((v['signature']['dev'],v['signature']['ino']) not in protected for v in rows),'Selected dependency never deleted')
    return rows,protected

def state_contract(state,binding,claim=None):
    require(state['decode_optimization_current']['status']=='MAYAS_TP2_DEFAULT_ACTIVE_VERIFIED' and
            state['decode_optimization_current']['selected_identity']['start_binding']==binding,'Verified exact current Maya-S default')
    for k in ('active_private_phase','active_GPU_phase','active_gpu_experiment','private_window','production_restore_in_progress',
              'production_verification_pending','production_temporarily_stopped'):
        require(not state.get(k),'Foreign phase/pending restoration: '+k)
    require(state.get('active_cpu_build')==(claim if claim is not None else False),'Exact cleanup custody')

def execute(plan_pin,parent):
    require(sys.platform=='linux' and H==E/'decode-optimization-20261028/mayas-default-cleanup-20261101','Canonical physical Ubuntu')
    c=load_primitive();require(sha(H/'PLAN.json')==plan_pin,'Exact audited explicit plan')
    plan=read(H/'PLAN.json');rows,protected=plan_contract(plan)
    review=read(H/'SOURCE_REVIEW_FIRST.json')
    require(review['ROOT_full_source_tests_read'] and review['source_sha256']==sha(H/'cleanup.py') and review['test_sha256']==sha(H/'test_cleanup.py'),'Exact source review')
    for platform in ('darwin','linux'):
        r=read(H/('CPU-FIRST-'+platform+'.json'));child=read(H/('CPU-FIRST-'+platform)/'child.json')
        require(r['passed'] and r['controls']==9 and r['source_sha256']==review['source_sha256'] and r['test_sha256']==review['test_sha256'] and
                r['ids']==review['test_ids'] and child['returncode']==0 and child['cleanup']==[] and child['error'] is None,'Both physical FIRST controls')
    spec=importlib.util.spec_from_file_location('qualified_bounded_cpu',DC/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py')
    d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d);observed=d.observed();d.bounds(observed,os.getpid(),parent)
    sys.path.insert(0,str(P));import activate_mayas as a,policy as p
    q=a.qualified(sha(P/'qualification.json'));base,owner,old,legacy=a.support(q)
    host=a.production_host(owner,legacy,q)();host.start_binding=dict(plan['binding']);host.audit_dir=H
    require(a.sha(p.D/'bin/maya-ds4')==NATIVE and a.sha(p.D/'config.json')==CONFIG,'Actual tested artifacts')
    state_contract(read(E/'STATE.json'),plan['binding']);host.guard_binding(plan['binding']['native_pid']);host.target_identity()
    health=host.get('/health');require(health['loaded'] and health['max_context']==1048576 and health['switcher']['active_model']==health['switcher']['default_model']=='deepseek' and health['switcher']['fault'] is None,'Healthy selected default')
    # User explicitly permits interruption; cleanup does not interrupt or signal.
    for path,row in plan['protected'].items():
        t=Path(path).stat();require((t.st_dev,t.st_ino,t.st_size)==(row['dev'],row['ino'],row['size']),'Protected selected dependency drift')
    for row in rows:c.checked_leaf(row,protected)
    # Separate exact batches avoid ARG_MAX. Every target observed, uncertainty fails closed.
    for i in range(0,len(rows),100):
        held=subprocess.run(['sudo','-n','lsof','-nP','-F','pfn','--',*[v['path'] for v in rows[i:i+100]]],capture_output=True,text=True,timeout=15)
        require(held.returncode==1 and held.stdout==held.stderr=='','Target is open/mapped or observer uncertain')
    prefixes=[str(DC/'s2-reconstruction-v1/iq3s-source-acquisition-v1').encode(),str(DC/'s2-reconstruction-v1/iq3s-bulk-v1').encode(),str(DC/'s2-reconstruction-v1/native-payload-v3').encode()]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():continue
        try:argv=(proc/'cmdline').read_bytes()
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
        require(not any(v in argv for v in prefixes),'Active constructor/acquisition process; no unlink')
    completed=[];error=None;before=shutil.disk_usage('/').free
    claim={'kind':'Maya-S-default-unused-weight-cleanup','pid':os.getpid(),'plan_sha256':plan_pin}
    def guard():
        state_contract(read(E/'STATE.json'),plan['binding'],claim);host.guard_binding(plan['binding']['native_pid'])
    def append(v):
        with (H/'REMOVALS_FIRST.jsonl').open('a') as f:f.write(json.dumps(v)+'\n');f.flush();os.fsync(f.fileno())
    def unlinked(v):completed.append(v);append(dict(v,stage='UNLINK_RETURNED_SUCCESS'))
    with (R/'experiment.lock').open('r') as lock:
        # Existing selected API owns this flock for its lifetime. Never release it.
        c.canonical_lock_guard(lock,plan['binding']['main_pid'])
        original=(E/'STATE.json').read_bytes();state=json.loads(original);state_contract(state,plan['binding'])
        c.exclusive_attempt(H/'ATTEMPT_FIRST.json',claim)
        cas=a.cas_library(q);state['active_cpu_build']=claim;cas.cas_state(E/'STATE.json',original,state)
        try:
            for i,row in enumerate(rows):
                if i%64==0:guard();c.canonical_lock_guard(lock,plan['binding']['main_pid'])
                result=c.unlink_record(row,protected,append,unlinked);append(dict(result,stage='DURABLE_REMOVAL_CONFIRMED'))
            guard();require(all(not Path(v['path']).exists() for v in rows),'Every explicit path absent')
            for path,row in plan['protected'].items():
                t=Path(path).stat();require((t.st_dev,t.st_ino,t.st_size)==(row['dev'],row['ino'],row['size']),'Selected dependency preserved')
        except BaseException as exc:error=repr(exc);raise
        finally:
            result={'passed':error is None and len(completed)==len(rows),'error':error,'removed_count':len(completed),
                    'removed_bytes':sum(v['bytes'] for v in completed),'expected_count':len(rows),'expected_bytes':plan['bytes'],
                    'root_free_before':before,'root_free_after':shutil.disk_usage('/').free,'binding':plan['binding'],
                    'observed_child_limits':observed,'no_service_or_inference_action':True,'raw_logs_results_and_caches_preserved':True}
            c.exclusive_attempt(H/'RESULT_FIRST.json',result)
            raw=(E/'STATE.json').read_bytes();state=json.loads(raw);state_contract(state,plan['binding'],claim)
            state['active_cpu_build']=False;state['mayas_default_payload_cleanup']={'result':str(H/'RESULT_FIRST.json'),'passed':result['passed']}
            cas.cas_state(E/'STATE.json',raw,state)
    print(json.dumps(result))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--plan-sha256',required=True);parser.add_argument('--parent',type=int,required=True)
    args=parser.parse_args();execute(args.plan_sha256,args.parent)
