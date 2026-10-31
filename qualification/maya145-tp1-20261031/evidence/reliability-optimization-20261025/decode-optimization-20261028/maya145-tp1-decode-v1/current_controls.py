"""Current-engine startup/process observations, unchanged transport and owned fence."""
import os
import json
import hashlib
import math
import re
from pathlib import Path
import current_runtime as runtime
import current_config as config
import engine_profile

# Reuse exact qualified pure scoring, bounded transport and private-memory fence.
# These helpers do not invoke the old controller/old native/old arm registries.
prior=runtime.legacy_controls()
Incomplete=prior.Incomplete
for _name in ('token_contract','bounded_request','score'):
    globals()[_name]=getattr(prior,_name)


# Actual qualified80GiB fence: transport/scoring stay on the original pure helpers.
fence_owner=runtime.reusable('pv_controls')
fenced_phase=fence_owner.fenced_phase
fence_terminal=fence_owner.fence_terminal

def current_capacity(native,health,models,engine_log,chunk,*,expected_context=262144):
 if type(expected_context) is not int or expected_context not in (262144,524288,1048576):raise ValueError("Unqualified expected context")
 info=native.get('info') or {}
 if type(native.get('pid')) is not int or native['pid']<=0:raise ValueError('No actual child PID')
 if native.get('context')!=expected_context or info.get('kv_resident')!=expected_context or info.get('engine_kind')!='ds4':raise ValueError('Wrong context/native engine')
 if native.get('batch_slots') not in [0,None] or native.get('can_stop') is not True:raise ValueError('Unqualified execution/cancel geometry')
 if type(info.get('cpu_experts')) is not int or info['cpu_experts']<=0 or info.get('ram_experts')!=info['cpu_experts']:raise ValueError('CPU experts are not all resident in RAM')
 if type(info.get('expert_slots')) is not int or info['expert_slots']<=0:raise ValueError('Unknown expert placement')
 if info.get('vision')!='ds4' or any(type(info.get(k)) is not int or info[k]!=v for k,v in [('vision_mib',0),('vision_room_mib',318),('vision_max_tokens',1024)]) or info.get('vision_room')!='chunk':raise ValueError('Native image contract changed')
 if health.get('loaded') is not True or health.get('max_context')!=expected_context or health.get('images') is not True:raise ValueError('HTTP contract mismatch')
 rows=models.get('data') or []
 selected=[x for x in rows if x.get('id')=='deepseek-v4.1-flash-iq2-xs']
 if len(selected)!=1:raise ValueError('Wrong advertised model')
 row=selected[0];arch=row.get('architecture') or {};caps=row.get('capabilities') or {}
 # The pinned private API publishes meta.n_ctx + architecture modalities. The
 # authenticated public router adds context_length/capabilities. Do not require
 # those public-only fields on the private API or infer image input from absence.
 context=row.get('meta',{}).get('n_ctx',row.get('context_length'))
 if context!=expected_context or (row.get('context_length') is not None and row['context_length']!=context) or arch.get('input_modalities')!=['text','image'] or ('image_input' in caps and caps['image_input'] is not True):raise ValueError('Advertised context/images mismatch')
 # Actual startup log, not CLI alone. Native INFO does not export the prefill chunk.
 chunks=re.findall(r'prompts in chunks of (\d+)',engine_log)
 if not chunks or set(chunks)!={str(chunk)}:raise ValueError('Actual native prefill chunk not demonstrated')
 full=re.findall(r'(\d+) of the CPU lane.s (\d+) experts copied into RAM',engine_log)
 if not full or any(int(a)!=int(b) or int(a)!=info['cpu_experts'] for a,b in full):raise ValueError('Full-RAM actual startup evidence missing')
 if 'no disk fallback' not in engine_log:raise ValueError('Strict RAM startup not evidenced')
 return {'passed':True,'native_pid':native['pid'],'actual_chunk':chunk,'context':expected_context,'vision':True,'expert_slots':info['expert_slots'],'cpu_experts':info['cpu_experts'],'ram_experts':info['ram_experts'],'placement_warning':'Chunk workspace may change GPU/CPU expert counts; retain actual values, not only common profile seed.'}


def startup(a,old,ready,health,models,log,variant):
    result=current_capacity(ready,health,models,log,4096,expected_context=1048576)
    result['current_engine']=engine_profile.startup(log,variant)
    runtime.require('has no DSpark drafter blocks' not in log and any(row['last_layer']==42 or row['draft_blocks']==[0,1,2] for row in result['current_engine']['placement']),'Published DSpark blocks must be loaded')
    result['drafter']={'configured_and_loaded':True,'execution_proven':False,'old_API_drafting_field_is_not_native_evidence':True}
    runtime.require(result['expert_slots']+result['cpu_experts']==15360,'Actual trunk expert accounting')
    return result


def actual_native(c,pid,config):
    proc=Path('/proc')/str(pid)
    env=dict(x.split('=',1) for x in (proc/'environ').read_bytes().decode().split('\0') if '=' in x)
    argv=(proc/'cmdline').read_bytes().decode().split('\0');group=(proc/'cgroup').read_text()
    same=os.path.samefile(proc/'exe',c['exe'])
    result=config.process_contract(c,argv,env,group,same_executable=same)
    runtime.require(runtime.sha(c['exe'])==config.BASE_NATIVE,'New native changed')
    return {**result,'native_pid':pid,'native_sha256':config.BASE_NATIVE,
        'controlled_env':config.controlled_environment(env),'actual_argv':argv,'actual_cgroup':group,
        'same_executable':same,'start_ticks':int((proc/'stat').read_text().rsplit(') ',1)[1].split()[19])}


def draft_execution(stats, *, required):
    """Request-scoped native DSpark work, distinct from prompt lookup offered counts."""
    rounds=stats.get('draft_rounds',0)
    runtime.require(type(rounds) is int and rounds>=0,'Typed DSpark round count')
    for key in ('draft_ms','verify_ms'):
        value=stats.get(key,0.)
        runtime.require(type(value) in (int,float) and math.isfinite(value) and value>=0,'Finite native drafter timing')
    active=rounds>0 and stats.get('draft_ms',0)>0
    runtime.require(not required or active,'Actual DSpark execution required for timing')
    return {'configured_and_loaded_separate':True,'execution_proven':active,'draft_rounds':rounds,'draft_ms':stats.get('draft_ms',0.),'verify_ms':stats.get('verify_ms',0.),'acceptance_can_be_zero':True}


def native_stat(folder,pid,*,required):
    folder=Path(folder);receipt=json.loads((folder/'stat-receipt.json').read_text(),object_pairs_hook=prior.typed_pairs)
    runtime.require(type(pid) is int and pid>0 and re.fullmatch('native-[0-9]{3}',folder.name) and type(receipt.get('trace_number')) is int and receipt['trace_number']==int(folder.name[-3:]) and type(receipt.get('samples')) is int,'Exact request STAT namespace/count')
    runtime.require(receipt.get('native_pid')==pid and receipt.get('complete') is True and receipt.get('DONE_observed') is True and receipt.get('capture_error') is None and receipt.get('primary_error') is None,'Complete owned STAT trace required')
    runtime.require((folder/'stat-lines.jsonl').stat().st_size<=4*2**20,'Bounded saved STAT')
    rows=[json.loads(line,object_pairs_hook=prior.typed_pairs) for line in (folder/'stat-lines.jsonl').read_text().splitlines()]
    runtime.require(len(rows)==receipt.get('samples') and len(rows)<=100000,'STAT count')
    digest=hashlib.sha256();last=None;clock=-1.;rounds=-1
    for row in rows:
        raw=row['raw'];sec=row['seconds']
        runtime.require(row.get('native_pid')==pid and row.get('trace_number')==receipt['trace_number'] and type(sec) in (int,float) and math.isfinite(sec) and sec>=clock and type(raw) is str and raw.startswith('STAT ') and len(raw)<=4096 and '\n' not in raw and '\r' not in raw,'STAT identity/clock/line')
        clock=sec;digest.update((raw+'\n').encode());pairs=[part.split('=',1) for part in raw.split()[1:]]
        runtime.require(all(len(pair)==2 for pair in pairs) and len({k for k,v in pairs})==len(pairs),'Exact unique STAT fields')
        values=dict(pairs);runtime.require(all(k in values for k in ('draft_rounds','draft_ms','verify_ms')) and values['draft_rounds'].isdecimal(),'Native DSpark fields')
        last={'draft_rounds':int(values['draft_rounds']),'draft_ms':float(values['draft_ms']),'verify_ms':float(values['verify_ms'])}
        draft_execution(last,required=False);runtime.require(last['draft_rounds']>=rounds,'Request DSpark rounds regressed');rounds=last['draft_rounds']
    runtime.require(digest.hexdigest()==receipt.get('raw_lines_sha256'),'Raw STAT bytes differ')
    return {**draft_execution(last or {},required=required),'samples':len(rows),'raw_lines_sha256':digest.hexdigest()}


def native_file_limit_record(record,pid):
    runtime.require(type(pid) is int and pid>1 and record.get('native_pid')==pid and record.get('mutated') is False,'Exact timed native PID and untouched limit')
    raw=record.get('raw','');runtime.require(raw.startswith('Max file size') and raw.split()[3:5]==['unlimited','unlimited'] and record.get('soft')==record.get('hard')=='unlimited','Timed native must not inherit numerical FSIZE fencing')
    return record


def native_file_limit(pid,*,proc=Path('/proc')):
    runtime.require(type(pid) is int and pid>1,'Exact timed native PID')
    rows=[x for x in (proc/str(pid)/'limits').read_text().splitlines() if x.startswith('Max file size')]
    runtime.require(len(rows)==1,'One actual native file limit')
    return native_file_limit_record({'native_pid':pid,'soft':'unlimited','hard':'unlimited','raw':rows[0],'mutated':False},pid)
