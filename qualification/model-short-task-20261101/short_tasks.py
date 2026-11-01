"""Distinct single-main short observations from complete pinned public requests.

No old panel is marked complete, and no long-input bound or GPU admission follows.
"""
import copy,hashlib,json,re
from pathlib import Path
P=Path(__file__).resolve().parent;E=P.parents[1]
PROFILES=('HGU','UNSLOTH','MS2','MS1')
ARMS={f'{prefix}-{profile}-{rep}':{'profile':profile,'task':task,'replicate':rep} for prefix,task in [('P','prose'),('C','coding')] for profile in PROFILES for rep in (1,2)}
POLICY={'model':'deepseek-v4.1-flash-iq2-xs','stream':True,'reasoning_effort':100,'reasoning_budget_tokens':0,'temperature':1.0,'top_p':1.0,'seed':1,'max_tokens':32768}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def packed(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(packed(v)).hexdigest()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pairs(items):
    d={}
    for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
    return d

def read(p):
    p=Path(p);require(p.is_file() and not p.is_symlink() and p.resolve()==p and p.stat().st_size<4*2**20,'Bounded canonical public source')
    return json.loads(p.read_text(),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def factor(arm):
    require(type(arm) is str and arm in ARMS,'Exact frozen short-task arm only');return copy.deepcopy(ARMS[arm])
def source(profile,task):
    require(profile in PROFILES and task in ('prose','coding'),'Explicit task/profile')
    registry=read(P/'SHORT_SOURCES_FROZEN.json');require(set(registry)=={x+'-'+t for x in PROFILES for t in ('prose','coding')},'Exact eight source factors')
    row=registry[profile+'-'+task];rel=Path(row['source_relative_to_E']);require(not rel.is_absolute() and '..' not in rel.parts,'Exact source containment')
    path=E/rel;require(sha(path)==row['source_sha256'],'Original public source changed');original=read(path)
    require(original['context']==1048576 and original['default_output']==262144 and packed(original['policy'])==packed(POLICY),'Original capacity and full request policy')
    cases=[c for c in original['cases'] if c['id']==row['case_id']];require(len(cases)==1,'One exact original main case')
    case=cases[0];require(digest(case)==row['case_sha256'] and case['kind']==('prose' if task=='prose' else 'code'),'Complete unchanged public main case')
    require(case['request_sha256']==digest(case['request'])==row['request_sha256'] and case['prompt_ids_sha256']==digest(case['prompt_ids'])==row['prompt_ids_sha256'],'Exact original typed request and actual CPU encoding')
    require(type(case['prompt_tokens']) is int and case['prompt_tokens']==len(case['prompt_ids'])==row['prompt_tokens']==(169 if task=='prose' else 140),'Exact short task, no resize')
    require(case.get('expected_reuse')=='zero' and not case['image_spans'] and all(type(x) is int and 0<=x<129280 for x in case['prompt_ids']),'Cold text main only')
    require(all(type(case['request'].get(k)) is type(v) and case['request'][k]==v for k,v in POLICY.items()),'Full unmodified benchmark policy')
    require(original['tokenizer_source_sha256']==row['tokenizer_source_sha256'] and original['effective_template']==row['effective_template'],'Original actual template/tokenizer provenance')
    return row,case,original

def manifest(arm):
    f=factor(arm);row,case,original=source(f['profile'],f['task'])
    return {'id':'model-short-task-'+arm,'mode':'task','arm':arm,**f,'context':1048576,'default_output':262144,'policy':copy.deepcopy(POLICY),'cases':[copy.deepcopy(case)],'lifecycle_cases':[],
      'source_panel_sha256':row['source_sha256'],'source_panel_relative_to_E':row['source_relative_to_E'],'selected_case_sha256':row['case_sha256'],
      'tokenizer_source_sha256':row['tokenizer_source_sha256'],'effective_template':row['effective_template'],'API_sha256':original.get('API_sha256','b1be40294f6c49692829ad5f85a7aa2867218180fdc8fbc9bef7710371ba3b9f'),
      'purpose':'SINGLE_COMPLETE_PUBLIC_MAIN_SHORT_COLD_OBSERVATION','source_whole_panel_claimed_complete':False,'cold_bound_previously_measured_for_this_profile':False,'long_input_runtime_bound_claim':False,
      'general_quality_or_equivalence_claim':False,'deployment_admitted':False,'automatic_next_arm':False}
