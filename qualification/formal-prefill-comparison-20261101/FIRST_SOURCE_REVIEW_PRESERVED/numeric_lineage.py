"""Pin previously closed, full finite diagnostics. No payload reread or old-arm replay."""
import json,hashlib,re
from pathlib import Path
import engine_profile
P=Path(__file__).resolve().parent;E=P.parents[1]
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def contract(profile,row,registry,audit):
    require(profile in engine_profile.PACKS and row['arm'] in registry,'Explicit prior diagnostic')
    r=registry[row['arm']];require(r.get('attempted') is True and r.get('fully_reviewed') is True and r.get('accepted') is True,'Previous finite diagnostic not accepted/reviewed')
    require(audit.get('passed') is True and audit.get('arm')==row['arm'] and audit.get('mode')==row['mode'] and audit.get('qualification_sha256')==row['qualification_sha256'] and audit.get('finite_logits_checked') is True,'Actual qualified finite diagnostic')
    f=audit['whole_pack_factor'];wanted=engine_profile.factor(profile)
    require(type(f['tp']) is int and f['native_sha256']=='adff28a2d3a3f54ebfc0399e5e3ec7385f6fbb848e4e675fa1044cf7c6961f4f' and all(f[k]==wanted[k] for k in ('native','pack','tp','context_total','output_allowance','effort','prefill_chunk')),'Exact same compiled model/TP/fullpolicy numerical lineage')
    dumps=audit['finite_dumps'];require(len(dumps)==2,'Two complete prior dumps')
    for d in dumps:
        require(type(d['rows']) is int and d['rows']>0 and type(d['bytes']) is int and d['bytes']==d['rows']*129280*4 and re.fullmatch('[0-9a-f]{64}',d['sha256']) and d['all_finite'] is True and d['token_row_alignment_claimed'] is False,'Complete full-vocabulary finite raw byte proof, no row-alignment claim')
    fence=audit['private_fence'];require(fence['passed'] is True and type(fence['memory_max']) is int and fence['memory_max']==80*2**30 and type(fence['swap_max']) is int and fence['swap_max']==0 and fence['events_delta']['oom']==fence['events_delta']['oom_kill']==0 and fence['prior_properties_restored'] is True and fence['transient_collected'] is True,'Clean owned numerical phase/resource closure')
    require(audit['general_quality_claim'] is False and audit['performance_claim'] is False and audit['deployment_admitted'] is False and audit['retry'] is False,'Prior diagnostic scope cannot become timing/quality proof')
    return True

def guard(q):
    frozen=P/'NUMERICAL_LINEAGE_FROZEN.json';require(q['files'].get(str(frozen))==sha(frozen),'Frozen prior diagnostic source map membership')
    rows=json.loads(frozen.read_text());require(set(rows)==set(engine_profile.PACKS)-{'PROD'},'All four explicit factors need numerical lineage')
    for profile,row in rows.items():
        documents={}
        require(set(row['files'])>={'registry','audit','root_review','qualification'},'Complete prior closure authority')
        for name,entry in row['files'].items():
            rel=Path(entry['relative_to_E']);require(not rel.is_absolute() and '..' not in rel.parts,'Exact small closure paths');p=E/rel
            require(p.is_file() and p.resolve()==p and not p.is_symlink() and p.stat().st_size<4*2**20 and q['files'].get(str(p))==entry['sha256']==sha(p),'Unchanged qualified previous numerical evidence')
            documents[name]=json.loads(p.read_text())
        require(row['qualification_sha256']==row['files']['qualification']['sha256'],'Actual previous qualification pin')
        contract(profile,row,documents['registry'],documents['audit'])
    return True
