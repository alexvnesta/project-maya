"""ROOT-read exact metadata freeze for new assembly; never launches or retries a conversion."""
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import os
import shutil
import sys

HERE=Path(__file__).resolve().parent
Q=HERE.parent
DC=Q.parent
E=DC.parent


def require(ok,why):
    if not ok:raise ValueError(why)


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def emit(p,row):
    with Path(p).open('x') as f:json.dump(row,f,indent=2);f.write('\n')


def main():
    require(sys.platform=='linux' and str(Q)=='/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/s2-reconstruction-v1','Actual physical metadata namespace')
    sys.dont_write_bytecode=True;sys.path.insert(0,str(DC/'maya-s-comparison-v1'));import acquire
    gate=acquire.SelectedGate();gate()
    # Only this short-lived metadata process receives these limits.
    resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20));os.nice(15)
    spec=importlib.util.spec_from_file_location('compose_actual_assembly',HERE/'assembly.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
    require(sha(HERE/'assembly.py')=='8e2a1787bdf73ecb3b4c6bbde15f071f151f477ec46e42788be12c96f4ec01d7','Exact manually reviewed assembly')
    terminal=read(Q/'original-expert-acquisition-v2/acquisition-state.json');require(terminal.get('status')=='ALL_FORTY_TRUNK_EXPERT_SHARDS_VERIFIED_NO_MODEL_RUN' and terminal.get('returncode')==0,'Complete original40 before freeze')
    need=a.disk_admission(shutil.disk_usage('/').free)
    files={}
    def add(p):
        p=Path(p);require(p.resolve()==p and not p.is_symlink() and p.is_file() and p.stat().st_size<=512*2**20,'Small exact metadata/source file')
        files[str(p)]=sha(p)
    def component(name,names):
        root=Q/name
        for n in (*names,'ROOT_SOURCE_REVIEW.json','CPU-FIRST-darwin.json','CPU-FIRST-linux.json','CPU-FIRST-darwin/child.json','CPU-FIRST-darwin/child.log','CPU-FIRST-linux/child.json','CPU-FIRST-linux/child.log'):add(root/n)
        review=read(root/'ROOT_SOURCE_REVIEW.json');sources={n:sha(root/n) for n in names}
        require(review['source_map']==sources and review['entire_source_tests_driver_manually_read'] is True,'Exact full manual source read')
        for host in ('darwin','linux'):a.cpu_contract(read(root/('CPU-FIRST-'+host+'.json')),read(root/('CPU-FIRST-'+host)/'child.json'),review,host)
        return root,review
    component('iq3s-assembly-v3',a.SOURCES)
    component('bounded-sha256-v1',('fork_hash.py','test_hash.py','run_cpu.py'))
    launchroot,launchreview=component('launch-custody-v1',('launch.py','test_launch.py','run_cpu.py'))
    launchq=launchroot/'qualification.json'
    if not launchq.exists():
        emit(launchq,{'CPUReview':str(launchroot/'ROOT_SOURCE_REVIEW.json'),'source_map':launchreview['source_map'],'input_map':launchreview['input_map'],'test_ids':launchreview['test_ids'],
            'CPU':{h:{'receipt':str(launchroot/('CPU-FIRST-'+h+'.json')),'child':str(launchroot/('CPU-FIRST-'+h)/'child.json'),'log':str(launchroot/('CPU-FIRST-'+h)/'child.log')} for h in ('darwin','linux')},
            'scope':'Actual child wait only; no target admission/deadline override, signals or retry'})
    for f in (launchq,Q/'bounded-sha256-v1/qualification.json',a.BUILD,a.BULK,a.PLAN,Q/'iq3s-conversion-v1/convert.py',DC/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py',Q/'iq3s-bulk-v1/qualification.json',Q/'original-expert-acquisition-v2/ASSET_MANIFEST.json',Q/'original-expert-acquisition-v2/acquisition-state.json'):add(f)
    for n in ('attempt.json','absence.json','supervision.json','join/observed.json','join/child.json'):add(a.ORIGINAL/n)
    fp=a.regular(a.ORIGINAL/'overlay.partial');require(fp[2]==17583667200,'Preserve exact failed original bytes at original path')
    parts={}
    for i in range(a.COUNT):
        stem=a.ORIGINAL/'parts'/('%04d'%i)
        parts[str(i)]={suffix:sha(stem.with_suffix(suffix)) for suffix in ('.json','.child.json','.DONE.json','.observed.json')}
    original=read(a.ORIGINAL/'attempt.json')
    q={'sources':{n:sha(HERE/n) for n in a.SOURCES},'root_entire_source_tests_driver_read':True,
        'mode':'s2-iq3s-assembly-v3-FIRST','output_root':str(a.OUT),'captured_outer_launch_required':True,
        'outer_exit_capture_qualification':str(launchq),'selected_binding':gate.host.start_binding,
        'CPU_review':str(HERE/'ROOT_SOURCE_REVIEW.json'),
        'CPU':{h:{'receipt':str(HERE/('CPU-FIRST-'+h+'.json')),'child':str(HERE/('CPU-FIRST-'+h)/'child.json'),'log':str(HERE/('CPU-FIRST-'+h)/'child.log')} for h in ('darwin','linux')},
        'bounded_hash_qualification':str(Q/'bounded-sha256-v1/qualification.json'),'files':files,
        'part_proof_sha256':parts,'original_controller_pid':original['controller_pid'],
        'original_bulk_qualification_sha256':sha(Q/'iq3s-bulk-v1/qualification.json'),
        'failed_partial_fingerprint':fp,'original_outer_exit_status':'UNKNOWN','failure_cause':'UNDETERMINED',
        'ROOT_admission':'Separate bounded partition assembly only of immutable3840 successful matrices; originalfailedjoin/partial preserved; no GPU/model/default action',
        'budget_before_bytes':shutil.disk_usage('/').free,'budget_required_bytes':need}
    a.source40_closed(q);a.original_failure(q);a.hash_helper(q)
    emit(HERE/'qualification.json',q);pin=sha(HERE/'qualification.json');a.qualification(pin)
    plan={'ROOT_explicit_admission':True,'no_replay':True,'target_owns_bounds_and_restore':True,
        'argv':['/home/alex/strata-deepseek-test-20261024/venv/bin/python3.14','-I','-B',str(HERE/'assembly.py'),'run',pin],
        'target_source_sha256':sha(HERE/'assembly.py'),'cwd':str(HERE),'output':str(launchroot/'capture-assembly-FIRST')}
    emit(launchroot/'assembly-FIRST-plan.json',plan)
    print(json.dumps({'qualification_sha256':pin,'launch_plan_sha256':sha(launchroot/'assembly-FIRST-plan.json'),'root_free_bytes':shutil.disk_usage('/').free,'required_bytes':need,'files':len(files),'immutable_part_proof_groups':len(parts)}))


if __name__=='__main__':main()
