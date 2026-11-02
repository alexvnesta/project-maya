"""Separately audited remaining rows, max64 per bounded child. No absent skipping.
Original timeout and every successful unlink remain recorded in the first run.
"""
import importlib.util,json,os,sys,subprocess,shutil
from pathlib import Path
H=Path(__file__).resolve().parent
DC=H.parent
def old():
    p=DC/'mayas-default-cleanup-v2-20261101/cleanup.py'
    spec=importlib.util.spec_from_file_location('reviewed_cleanup_contract',p);c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
    assert c.sha(p)==json.loads((H/'PLAN.json').read_text())['contract_source_sha256']
    return c
def subset(rows,index):
    if type(index) is not int or index<0 or index*64>=len(rows):raise ValueError('Exact nonempty bounded batch index')
    return rows[index*64:(index+1)*64]
def execute(pin,parent,index):
    c=old();prim=c.load_primitive();assert c.sha(H/'PLAN.json')==pin
    plan=c.read(H/'PLAN.json');c.plan_contract(plan);rows=subset(plan['rows'],index)
    dpath=DC/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py';assert c.sha(dpath)=='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
    s=importlib.util.spec_from_file_location('bounded',dpath);d=importlib.util.module_from_spec(s);s.loader.exec_module(d);observed=d.observed();d.bounds(observed,os.getpid(),parent)
    sys.path.insert(0,str(c.P));import activate_mayas as a,policy as p
    q=a.qualified(a.sha(c.P/'qualification.json'));base,owner,legacyold,legacy=a.support(q)
    host=a.production_host(owner,legacy,q)();host.start_binding=plan['binding'];host.audit_dir=H
    host.command=lambda argv,timeout=180,check=True:subprocess.run(argv,timeout=timeout,check=check,text=True,capture_output=True,env=c.command_environment(argv))
    state=c.read(c.E/'STATE.json');c.state_contract(state,plan['binding']);host.guard_binding(plan['binding']['native_pid'])
    protected={(v['dev'],v['ino']) for v in plan['protected'].values()}
    for path,v in plan['protected'].items():
        t=Path(path).stat();assert (t.st_dev,t.st_ino,t.st_size)==(v['dev'],v['ino'],v['size'])
    for row in rows:prim.checked_leaf(row,protected)
    held=subprocess.run(['sudo','-n','lsof','-nP','-F','pfn','--',*[v['path'] for v in rows]],capture_output=True,text=True,timeout=15)
    assert held.returncode==1 and held.stdout==held.stderr==''
    out=H/('BATCH-%03d'%index);assert out.is_dir()
    completed=[];error=None;claim={'kind':'bounded_remaining_weight_batch','pid':os.getpid(),'index':index,'plan_sha256':pin}
    def append(v):
        with (out/'removals.jsonl').open('a') as f:f.write(json.dumps(v)+'\n');f.flush();os.fsync(f.fileno())
    def unlinked(v):completed.append(v);append(dict(v,stage='UNLINK_RETURNED_SUCCESS'))
    with (c.R/'experiment.lock').open('r') as lock:
        prim.canonical_lock_guard(lock,plan['binding']['main_pid']);raw=(c.E/'STATE.json').read_bytes();state=json.loads(raw);c.state_contract(state,plan['binding'])
        prim.exclusive_attempt(out/'attempt.json',claim);cas=a.cas_library(q);state['active_cpu_build']=claim;cas.cas_state(c.E/'STATE.json',raw,state)
        try:
            for row in rows:prim.unlink_record(row,protected,append,unlinked)
            host.guard_binding(plan['binding']['native_pid']);assert all(not Path(v['path']).exists() for v in rows)
        except BaseException as exc:error=repr(exc);raise
        finally:
            r={'passed':error is None and len(completed)==len(rows),'error':error,'count':len(completed),'bytes':sum(v['bytes'] for v in completed),'index':index,'observed':observed}
            prim.exclusive_attempt(out/'result.json',r)
            raw=(c.E/'STATE.json').read_bytes();state=json.loads(raw);c.state_contract(state,plan['binding'],claim);state['active_cpu_build']=False;cas.cas_state(c.E/'STATE.json',raw,state)
    print(json.dumps(r))
