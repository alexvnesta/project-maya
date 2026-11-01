"""Selected92 request-scoped DSpark attribution from its existing protocol.

No native changes or adff-only counters. The exact source's round() assigns
positive offered only after Model.draft then Model.verify. DONE and STAT are
reconciled with the same request/PID; zero acceptance is permitted. This does
not supply unavailable native draft time or round counts.
"""
import hashlib
import json
import math
from pathlib import Path

MAIN_SHA='1efa69ff5e2b7615b4f522bd695e0feecf5849df6e070eeb35cc9f900a92a2da'
MODEL_SHA='dfe326d6a60d77354c8c92fb14ec423a92afff76b91f0810104f0a54a51a6350'
NATIVE_SHA='92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
HERE=Path(__file__).resolve().parent

def require(value,message):
    if not value:raise ValueError(message)

def pairs(items):
    result={}
    for k,v in items:
        require(k not in result,'Duplicate native92 JSON member');result[k]=v
    return result

def parsed(data):return json.loads(data,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite native92 JSON')))

def packed(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)

def source_contract(main,model):
    require(hashlib.sha256(main).hexdigest()==MAIN_SHA and hashlib.sha256(model).hexdigest()==MODEL_SHA,'Exact selected92 source mapping')
    return True

def contract(request,trace,statistics,receipt,rows,pid,expected_request,expected_ids,*,trace_number=0,native_sha256=NATIVE_SHA,required=True):
    require(native_sha256==NATIVE_SHA and type(pid) is int and pid>1 and type(trace_number) is int and trace_number>=0,'Exact selected92/PID/trace')
    require(request.get('native_pid')==pid and type(request['native_pid']) is int and request.get('has_images') is False
            and type(request.get('max_new')) is int and request['max_new']==32768
            and packed(request.get('sampling'))==packed(expected_request) and request.get('ids')==expected_ids
            and all(type(x) is int and 0<=x<129280 for x in expected_ids),'Exact current text command/IDs/full request policy')
    require(type(trace.get('native_pid')) is int and trace['native_pid']==pid and trace.get('DONE_observed') is True and trace.get('error') is None,'Same native DONE closure')
    generated=statistics.get('generated');offered=statistics.get('drafts_offered');accepted=statistics.get('drafts_accepted')
    require(all(type(x) is int for x in (generated,offered,accepted)) and 1<generated<32768 and 0<=accepted<=offered<=4*generated
            and type(trace.get('T_lines')) is int and trace['T_lines']==generated
            and statistics.get('finish')=='stop' and type(statistics.get('prompt_tokens')) is int
            and statistics['prompt_tokens']==len(expected_ids),'Complete natural DONE/T/draft counters')
    require(not required or offered>0,'No positive native92 draft/verify witness')
    require(type(receipt.get('native_pid')) is int and receipt['native_pid']==pid and type(receipt.get('trace_number')) is int
            and receipt['trace_number']==trace_number and receipt.get('complete') is True and receipt.get('DONE_observed') is True
            and receipt.get('capture_error') is None and receipt.get('primary_error') is None
            and type(receipt.get('samples')) is int and 0<len(rows)==receipt['samples']<=100000,'Exact request STAT receipt')
    digest=hashlib.sha256();clock=-1.;last={}
    for row in rows:
        sec=row.get('seconds');raw=row.get('raw')
        require(type(row.get('native_pid')) is int and row['native_pid']==pid and type(row.get('trace_number')) is int
                and row['trace_number']==trace_number and type(sec) in (int,float) and math.isfinite(sec) and sec>=clock
                and type(raw) is str and raw.startswith('STAT ') and len(raw)<=4096 and '\n' not in raw and '\r' not in raw,'STAT source/PID/trace/order')
        clock=sec;parts=[x.split('=',1) for x in raw.split()[1:]]
        require(all(len(x)==2 for x in parts) and len({x[0] for x in parts})==len(parts),'Unique complete STAT fields')
        last=dict(parts);require({'tok_s','ms_tok','vram_hit','cpu','ram','promo','engram_ms'}<=last.keys(),'Selected92 STAT field contract')
        require(all(math.isfinite(float(v)) and float(v)>=0 for v in last.values()),'Finite nonnegative STAT values')
        if 'drafts' in last:
            require(0<=float(last['drafts'])<=1,'STAT draft ratio')
            require(accepted!=0 or float(last['drafts'])==0,'Earlier positive acceptance contradicts zero final accepted')
        digest.update((raw+'\n').encode())
    require(digest.hexdigest()==receipt.get('raw_lines_sha256'),'Exact raw STAT bytes')
    if offered>0:require('drafts' in last and abs(float(last['drafts'])-accepted/offered)<=0.000501,'Final request STAT/DONE draft reconciliation')
    return {'configured_and_loaded_separate':True,'execution_proven':offered>0,
            'evidence':'Exact native92 round() off>0 only after Model.draft/verify; same-command natural DONE and final STAT ratio',
            'drafts_offered':offered,'drafts_accepted':accepted,'zero_acceptance_permitted':True,
            'draft_rounds':None,'draft_ms':None,'verify_ms':None,'unavailable_native92_counters_not_inferred':True,
            'samples':len(rows),'raw_lines_sha256':digest.hexdigest(),'source_main_sha256':MAIN_SHA,'source_model_sha256':MODEL_SHA}

def observe(folder,pid,case,*,required=True):
    source_contract((HERE/'selected92-source/ds4_main.cpp').read_bytes(),(HERE/'selected92-source/ds4_model.cu').read_bytes())
    folder=Path(folder)
    require(folder.name.startswith('native-') and folder.name[7:].isdecimal(),'Exact native request folder')
    def read(name):
        p=folder/name;require(p.is_file() and not p.is_symlink() and p.stat().st_size<=4*2**20,'Bounded native92 evidence')
        return parsed(p.read_text())
    path=folder/'stat-lines.jsonl';require(path.is_file() and not path.is_symlink() and path.stat().st_size<=4*2**20,'Bounded raw STAT')
    rows=[parsed(line) for line in path.read_text().splitlines()]
    return contract(read('request.json'),read('trace-receipt.json'),read('native-statistics.json'),read('stat-receipt.json'),rows,pid,
                    case['request'],case['prompt_ids'],trace_number=int(folder.name[7:]),required=required)
