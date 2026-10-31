"""Single selected92 restoration after clean native/API closure and observer refusal.

No candidate retry, no new health/native binary, no source or selected-profile
change. Exact stopped custody and the old qualified one-start owner are required.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import current_runtime as rt

P=Path(__file__).resolve().parent
E=P.parents[1]
R=Path('/home/alex/strata-deepseek-test-20261024')
FAILED='maya144-mayas-TP2-20261031T165111Z'
CONFIG='c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'
NATIVE='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'


def require(ok,why):
    if not ok:raise ValueError(why)


def closed_contract(s,phase,cleanup,close,window,kernel,collected):
    require(s.get('maintenance_controller')==str(E/'maintenance'/FAILED/'state.json')
        and s.get('decode_optimization_current',{}).get('status')=='STOPPED_FOR_OFFLINE_DIAGNOSIS'
        and s.get('current_native_pid') is None and s.get('production_temporarily_stopped') is True
        and not any(s.get(k) for k in rt.PHASE_KEYS if k!='production_temporarily_stopped'), 'Exact stopped failed-controller custody')
    require(not (s.get('maya144_baseline_recovery') or {}).get('active'),'Another recovery active')
    require(phase.get('error')=="ValueError('Native image contract changed')" and phase.get('retry') is False,
        'Specific saved observer refusal only')
    require(cleanup.get('passed') is True and type(cleanup.get('server_returncode')) is int
        and cleanup['server_returncode']==0 and cleanup.get('grace_timeout') is False
        and cleanup.get('wait_error') is None and cleanup.get('application_stopped') is True
        and close==cleanup.get('native_close') and len(close)==1
        and type(close[0].get('returncode')) is int and close[0]['returncode']==0 and close[0].get('closed') is True,
        'Actual clean private API/native exit0 required')
    require(type(window.get('test_returncode')) is int and window['test_returncode']==1
        and window.get('maintenance_held') is True and window.get('maintenance_resume_allowed') is False
        and kernel.get('kernel_capture_returncode')==0 and type(kernel['kernel_capture_returncode']) is int
        and kernel.get('kernel_fault_lines')==[] and collected.get('passed') is True
        and collected.get('unit_collected') is True and collected.get('fragment_absent') is True
        and collected.get('dropins_absent') is True,'Owned failed phase cleaned, kernel clean; no candidate retry')
    return True


def restore_sequence(host,save):
    host.restore_ds()  # exact existing single-start owner and its unchanged1250s bound
    host.restore_router()
    verified=host.verify()
    require(verified.get('passed') is True or verified.get('pending_public_probe') is True, 'Selected verification must pass or explicitly defer a busy public probe')
    identity=verified['selected_identity']
    require(identity['native_sha256']==NATIVE and identity['config_sha256']==CONFIG
        and identity['context']==1048576 and identity['output_default']==262144 and identity['DSpark'] is True,
        'Restoration must preserve the best qualified selected model/profile')
    save(verified)
    return verified


def command(argv):return subprocess.run(argv,check=True,capture_output=True,text=True,timeout=15).stdout


def diagnosis():
    s=json.loads((E/'STATE.json').read_text());m=E/'maintenance'/FAILED;o=E/'results'/FAILED
    raw={}
    def j(p):
        b=p.read_bytes();raw[str(p)]=hashlib.sha256(b).hexdigest();return json.loads(b)
    w=R/'windows/20261031T165214Z.json';t=w.with_suffix('.telemetry.jsonl')
    data=t.read_bytes();raw[str(t)]=hashlib.sha256(data).hexdigest();kernel=json.loads(data.splitlines()[-1])
    closed_contract(s,j(o/'phase-error.json'),j(o/'native/server-cleanup.json'),
        [json.loads(x) for x in (o/'native/native-close.jsonl').read_text().splitlines()],j(w),kernel,
        j(m/'private-memory-fence-collected.json'))
    old=j(m/'old-owner-close.json');require(old['passed'] is True and old['native_close']['returncode']==0,'Bound old selected close0')
    return s,old,raw


def stopped_units():
    row=dict(x.split('=',1) for x in command(['systemctl','--user','show','deepseek-hosted.service','-p','InvocationID,MainPID,ActiveState,Result']).splitlines())
    require(row['MainPID']=='0' and row['ActiveState']=='inactive' and row['Result']=='success','Selected unit must remain cleanly stopped')
    require(not command(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader']).strip(),'Foreign GPU owner; no restoration start')
    for user,unit in ((True,'strata-deepseek-window.service'),(False,'glm-qwen-switcher.service')):
        p=subprocess.run(['systemctl']+(['--user'] if user else [])+['is-active','--quiet',unit],capture_output=True,timeout=15)
        require(p.returncode in (3,4),'Existing window/router active or status unknown')
    return row


def run(review_pin):
    require(sys.platform=='linux' and P==rt.P==E/'decode-optimization-20261028/maya144-mayas-v1','Physical exact recovery entry')
    review=P/'ROOT_BASELINE_RESTORE_SOURCE_REVIEW.json';require(rt.sha(review)==review_pin,'Exact reviewed restoration source')
    source=json.loads(review.read_text())
    for name,pin in source['source_sha256'].items():require(rt.sha(P/name)==pin,'Reviewed restoration source changed')
    for platform in ('darwin','linux'):
        folder=P/('CPU-BASELINE-RESTORE-FIRST-'+platform)
        proof=json.loads((folder/'receipt.json').read_text());child=json.loads((folder/'child.json').read_text())
        rt.cpu_contract(source,proof,child,platform)
    stopped=stopped_units();state,old,evidence=diagnosis()
    require(stopped['InvocationID']==old['binding']['invocation'],'Stopped selected invocation changed')
    q=rt.qualified('compatibility','151b2f13eb028adcb54f964ddecba94de3d52b77a5300ab67bd13560e0815a3b')
    a,oldmodule,base,legacy,startup=rt.support();h=rt.make_host(a,oldmodule,base,legacy,startup)()
    folder=P/'baseline-restoration-FIRST';require(not folder.exists(),'One selected start only, no replay');folder.mkdir()
    h.audit_dir=folder;h.baseline_binding=old['binding'];h.old_close_verified=True;h.since=state['decode_optimization_current']['kernel_since']
    h.start_binding=None;h.restored_pid=None;h.private_attempted=False
    h.kernel(h.since);require(stopped_units()==stopped and json.loads((E/'STATE.json').read_text())==state,'Stopped custody changed')
    record={'active':True,'pid':os.getpid(),'failed_controller':state['maintenance_controller'],'status':'SINGLE_SELECTED_RESTORATION_RUNNING',
        'source_review_sha256':review_pin,'evidence_sha256':evidence,'candidate_retry':False}
    cas_path=E/'decode-optimization-20261028/prose-speed-v1/prose_measure.py'
    require(rt.sha(cas_path)=='8d10d003bbbd7ffbb87251bacdf53d91af9f074151d34f06c957fa179f3108cf','Qualified CAS source changed')
    sys.path.insert(0,str(cas_path.parent));cas=__import__('prose_measure')
    require(Path(cas.__file__)==E/'decode-optimization-20261028/prose-speed-v1/prose_measure.py','Exact CAS helper origin')
    before=(E/'STATE.json').read_bytes();require(json.loads(before)==state,'Recovery claim race')
    cas.cas_state(E/'STATE.json',before,{**state,'maya144_baseline_recovery':record,'production_restore_in_progress':record})
    def save(verified):
        before=(E/'STATE.json').read_bytes();s=json.loads(before)
        require(s.get('maya144_baseline_recovery')==record and s.get('production_restore_in_progress')==record,'Foreign recovery claim preserved')
        pending=verified.get('pending_public_probe') is True
        final={**record,'active':False,'status':'SELECTED_PUBLIC_VERIFY_PENDING' if pending else 'SELECTED_RESTORED_FAILED_CTP2_REMAINS_HOLD','verified':verified,'start_binding':h.start_binding}
        rt.emit(folder/'result.json',final)
        s.update(maya144_baseline_recovery=final,production_restore_in_progress=False,production_temporarily_stopped=False,
            production_verification_pending=str(folder/'result.json') if pending else False,current_native_pid=h.restored_pid)
        s['decode_optimization_current']['selected_identity']=verified['selected_identity']
        cas.cas_state(E/'STATE.json',before,s)
    try:return restore_sequence(h,save)
    except BaseException as exc:
        rt.emit(folder/'failure.json',{'error':repr(exc),'start_binding':h.start_binding,'retry':False});raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--review-sha256',required=True);args=p.parse_args()
    print(json.dumps(run(args.review_sha256)),flush=True)
