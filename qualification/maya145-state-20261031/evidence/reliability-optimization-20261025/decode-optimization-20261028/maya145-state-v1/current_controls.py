"""Current-engine startup/process observations, unchanged transport and owned fence."""
import os
import json
import hashlib
import resource
import subprocess
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


def observed_cold_path(proof):
    token=proof['emitted_token_contract']
    runtime.require(type(token.get('count')) is int and 0<token['count']<32768 and re.fullmatch('[0-9a-f]{64}',token.get('ordered_ids_sha256','')),'Complete observed token path required')
    return {'historical_reference_required':False,'count':token['count'],'ordered_ids_sha256':token['ordered_ids_sha256'],'no_seeded_path_equivalence_claim':True}


def corrected_file_bound(meta,storage):
    g=dict(meta['storage_geometry'])
    for key in ('ratios','kv_sources','index_sources'):g[key]=tuple(g[key])
    storage.selected_geometry(g)
    identity=storage.identity_upper_bound(meta['engine_version'],meta['pack_files'])
    # Current source:3 base checks + up to16 retained marks; picture count8bytes even with zero images.
    pos=storage.MAX_PROMPT+storage.MAX_GENERATED
    sizes={'slot':storage.slot_bytes(g,pos,2**20,checkpoints=3)+16*storage.check_bytes(g)+8,'meta':storage.meta_bytes(pos,2**20,checkpoints=3)+16*8+8,'profile':43*384*4}
    runtime.require(all(type(v) is int and 0<v<storage.HARD_FILE_BYTES for v in sizes.values()),'Current legitimate native file can reach FSIZE')
    return g,{'actual_engine_macro':meta['engine_version'],'complete_pack_file_spellings':meta['pack_files'],'identity_bound':identity,'retained_checks_upper':19,'picture_count_bytes':8,'max_position':pos,'corrected_bounds':sizes,'hard_file_bytes':storage.HARD_FILE_BYTES,'scope':'Two own text-only unmeasured requests, no imported state or images; 1M allocated context is not serialized1Mpositions'}


def install_dump_limit(server,c,folder,storage):
    meta=json.loads((runtime.P/'PACK_STATE_SOURCE.json').read_text());g,bounds=corrected_file_bound(meta,storage)
    limit=storage.native_fsize_preexec(g,meta['engine_version'],meta['pack_files'],process_kind='UNMEASURED_NUMERICAL_NATIVE')
    original=server.popen;launched=[];api_limits=resource.getrlimit(resource.RLIMIT_FSIZE)
    def popen(what,args,role='engine',**kwargs):
        runtime.require(what=='the Strata engine' and args==config.expected_native_argv(c)[:-1] and role=='engine' and not launched,'One exact numerical native only')
        before=kwargs.get('preexec_fn')
        def child():
            if before:before()
            limit()
        kwargs['preexec_fn']=child
        proc=original(what,args,role=role,**kwargs);launched.append(proc.pid)
        try:
            runtime.require(resource.getrlimit(resource.RLIMIT_FSIZE)==api_limits,'API FSIZE must remain unchanged')
            runtime.emit(Path(folder)/'native-file-bound.json',{'native_pid':proc.pid,'argv':args,'file_limit_bytes':storage.HARD_FILE_BYTES,'API_limits_changed':False,'corrected_source_bound':bounds})
        except BaseException as primary:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
            except BaseException as cleanup:primary.add_note('Captured native receipt cleanup: '+repr(cleanup))
            raise
        return proc
    server.popen=popen
    return bounds


def native_limit_read(pid,*,proc=Path('/proc')):
    runtime.require(type(pid) is int and pid>1,'Exact numerical native PID')
    rows=[x for x in (proc/str(pid)/'limits').read_text().splitlines() if x.startswith('Max file size')]
    runtime.require(len(rows)==1 and rows[0].split()[3:5]==[str(512*2**20)]*2,'Actual native-only512MiB FSIZE required')
    return {'file_limit_bytes':512*2**20,'raw':rows[0],'native_pid':pid,'API_limits_changed':False}


def finish_dump_pair(folder,numerical):
    policy=numerical.dump_snapshot(folder,complete=False)
    if policy['status']!='WITHIN_BUDGET' or policy['count']!=2:raise Incomplete('Exactly two complete bounded dumps required; four-file legacy completion is inapplicable')
    sizes=[numerical.dump_size(Path(folder)/('logits.%d.f32'%i)) for i in (1,2)]
    return {'count':2,'sizes':sizes,'full_finite_audit_pending':True,'token_row_alignment_claimed':False,'source_format':'headerless float32 vocabulary rows; first prompt-last row then variable decode-round batches'}


def storage_source_contract(meta,cmake,main,model,marks):
    versions=re.findall(r'project\(strata VERSION ([0-9.]+) LANGUAGES CXX\)',cmake)
    runtime.require(versions==[meta['engine_version']],'Actual native session identity macro version')
    runtime.require(re.findall(r'constexpr int kMarksMax = ([0-9]+);',marks)==['16'] and '3 + (int) mk.size()' in model,'Current retained-checkpoint ceiling')
    runtime.require('n += 8 + n_pics * 24;' in model and 'const uint64_t np = pics.size();' in main,'Current zero-image picture count bytes')
    runtime.require('maya-ds4-session-2 engine=' in model and 'const char* dump_prefix = std::getenv("DS4_SERVE_DUMP")' in main and 'std::to_string(++n_req)' in main and 'if (dump_f != nullptr) std::fflush(dump_f);' in main,'Actual serial dump prefix/request-number/flush source')
    return {'source_bound_reviewed':True,'retained_checks_upper':19,'zero_image_extra_bytes':8,'headerless_vocabulary_float32':True,'per_token_row_alignment_claimed':False,'dump_prefix_is_directory':False}

def round_schedule(path,token_counts):
    """Existing native diagnostic log: only rounds that made drafts are logged.

    It omits plain steps and does not export RNG counters or raw logits row ranges.
    Do not call it a complete sampler execution trace.
    """
    path=Path(path)
    runtime.require(type(token_counts) is list and len(token_counts)==2 and all(type(x) is int and 0<x<32768 for x in token_counts),'Two completed natural token counts')
    runtime.require(not path.is_symlink() and path.is_file() and path.stat().st_nlink==1 and path.stat().st_size<=4*2**20,'Owned bounded native schedule log')
    raw=path.read_bytes();lines=raw.decode().splitlines()
    runtime.require(lines and lines[0]=='# tag\tposition\tsource\tmade\tverified\tkept\tconfidences' and len(lines)<=65537,'Exact native schedule header/count')
    rows=[];last={'r1':-1,'r2':-1};next_min={'r1':44,'r2':44};seen_second=False
    for line in lines[1:]:
        fields=line.split('\t');runtime.require(len(fields)==7,'Seven exact native schedule fields')
        tag,pos,source,made,verified,kept,confidence=fields
        runtime.require(tag in last and all(re.fullmatch('[0-9]+',x) for x in (pos,made,verified,kept)),'Typed request schedule identity')
        pos,made,verified,kept=map(int,(pos,made,verified,kept));idx=int(tag[1:])-1
        runtime.require(source in ('lookup','dspark') and 44<=pos<44+token_counts[idx] and pos>last[tag] and pos>=next_min[tag] and 1<=made<=15 and 0<=kept<=verified<=made<=15,'Source-bounded draft schedule fields')
        runtime.require(not(seen_second and tag=='r1'),'Interleaved foreign request schedule')
        seen_second=seen_second or tag=='r2';last[tag]=pos;next_min[tag]=pos+kept+1
        conf=[] if confidence=='-' else [float(x) for x in confidence.split(',')]
        runtime.require((source=='lookup' and confidence=='-' and made==verified) or (source=='dspark' and len(conf)==made and all(math.isfinite(x) and 0<=x<=1 for x in conf)),'Native source confidence format')
        rows.append({'tag':tag,'position':pos,'token_offset':pos-44,'source':source,'made':made,'verified':verified,'kept':kept,'confidence_rounded':conf})
    runtime.require(last['r1']>=44 and last['r2']>=44,'Both requests need actual drafted schedule evidence')
    return {'diagnostic_only':True,'raw_sha256':hashlib.sha256(raw).hexdigest(),'rows':rows,'request_tags':['r1','r2'],'plain_steps_omitted':True,'RNG_counters_exported':False,'source_log_not_per_token_logit_alignment':True,'causality_proven':False}
