"""Encode unchanged visible literal requests with each new pack's real API template.

CPU only. No native, tensor data, service operations, network or inference.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

HERE=Path(__file__).resolve().parent
E=HERE.parents[2]
Q=E/'decode-optimization-20261028/maya-s-comparison-v1'
SOURCE=Q/'model-v1/prose-fixtures-B.json'
SOURCE_SHA='d572147c2f668b7702531ec62a90b5ba9fe8e0b47ac864f05ecca8c73402c601'
HELPER=Q/'model-v1/ms_fixtures.py'
HELPER_SHA='76e3731d48792545b6135f335df60e9d9b4e7266ce23e70a3093a9916b74a869'
REQUEST_SHA='f7bde83281d0d70b95b9be1f28eb10356f7746798c05403599c185a7164ae1c6'
NAMES=('vocab.json','merges.txt','token_type.json','tokenizer.json','chat_template.jinja')

def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def registry():
    p=HERE/'PACKS_FROZEN.json';require(p.stat().st_size<2**20,'Small exact registry')
    rows=json.loads(p.read_text());require(set(rows)=={'HGU','UNSLOTH'},'Exactly the two not-yet-model-tested public candidates')
    for r in rows.values():
        require(r['context_total']==1048576 and r['output_allowance']==262144 and r['benchmark_cap']==32768
                and r['effort']==100 and r['drafter_unchanged'] is True and r['exact_private_S2'] is False,'Full unchanged policy/source scope')
    return rows

def pack_inputs(name):
    rows=registry();require(name in rows,'Known explicit candidate')
    row=rows[name];relative=Path(row['pack_relative_to_E']);require(not relative.is_absolute() and '..' not in relative.parts,'Relative exact pack')
    pack=E/relative;require(pack.is_dir() and pack.resolve()==pack,'Canonical pack metadata mirror')
    require(set(row['tokenizer_sha256'])==set(NAMES) and set(row['metadata_sha256'])=={'ds4.txt','tensors.txt','engram.bin'},'Complete metadata/tokenizer maps')
    raw={}
    for base,pins in [(pack,row['metadata_sha256']),(pack/'tokenizer',row['tokenizer_sha256'])]:
        for n,pin in pins.items():
            path=base/n;require(path.is_file() and path.resolve()==path and not path.is_symlink()
                and 0<path.stat().st_size<=64*2**20 and sha(path)==pin,'Exact small candidate metadata/tokenizer changed')
            if base.name=='tokenizer':raw[n]=path.read_bytes()
    return row,pack,raw

def helper():
    require(sha(HELPER)==HELPER_SHA,'Original CPU/API fixture helper changed')
    name='model_choice_frozen_fixture_helper'
    m=sys.modules.get(name)
    if m is None:
        spec=importlib.util.spec_from_file_location(name,HELPER);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    require(Path(m.__file__)==HELPER,'Original helper import origin')
    return m

def literal_request():
    require(sha(SOURCE)==SOURCE_SHA,'Frozen visible request changed')
    case=copy.deepcopy(json.loads(SOURCE.read_text())['lifecycle_cases'][-1])
    require(case['kind']=='literal' and case['expected']=='RECOVERED_Q8_LITERAL','Original literal task')
    body=case['request'];body['seed']=2
    require(digest(body)==REQUEST_SHA and body['max_tokens']==32768 and body['reasoning_effort']==100
            and body['reasoning_budget_tokens']==0,'Same original full-output/effort request required')
    return body

def encode(name):
    row,pack,raw=pack_inputs(name);f=helper();tokens,merges,types,cfg=f.tokenizer_schema(raw)
    support=f.load_support();s=support.server
    tokenizer=support.ST.Tokenizer(tokens,merges,types,cfg['pre'],cfg['special_ids'])
    template,provenance=f.effective_template(support,pack/'tokenizer',raw)
    request=literal_request()
    with tempfile.TemporaryDirectory(prefix='model-choice-visible-fixture-') as temp:
        vision=support.ds4_vision.Vision(support.ds4_vision.Geometry(),Path(temp),s.Vision.load)
        try:
            service=s.Service(s.MockEngine(tokenizer,['CPU'],max_context=1048576),tokenizer,s.ChatTemplate(template),vision=vision,fit_max_tokens=False)
            service.set_family('deepseek41');service.answer_room=False;service.reasoning_budget_configured=True
            service.reasoning_budget_tokens=0;service.reasoning_loop_recovery=False;service.repeat_stop_tokens=0
            messages,tools,kwargs=s.openai_to_messages(copy.deepcopy(request))
            messages,_=s.prepare_format(request.get('response_format'),messages,with_tools=bool(tools))
            ids=service.encode_prompt(messages,tools,kwargs,store=False)
            require(type(ids) is list and 0<len(ids)<=1024 and all(type(x) is int and 0<=x<129280 for x in ids),'Actual short source vocabulary encoding')
            require('torch' not in sys.modules,'No GPU framework import')
            require(pack_inputs(name)[0]==row and f.effective_template(support,pack/'tokenizer',raw)==(template,provenance),'Metadata/template source drift')
        finally:vision.shutdown()
    cases=[]
    for suffix,reuse in [('cold','zero'),('warm','prompt-minus-one')]:
        case={'id':'model-state-'+suffix,'kind':'literal','expected':'RECOVERED_Q8_LITERAL','request':copy.deepcopy(request),
              'prompt_ids':ids[:],'prompt_tokens':len(ids),'prompt_ids_sha256':digest(ids),'request_sha256':digest(request),'expected_reuse':reuse,'image_spans':[]}
        if suffix=='warm':case['dependency']='model-state-cold'
        cases.append(case)
    return {'id':'model-choice-'+name+'-literal-v1','candidate':name,'purpose':'SHORT_KNOWN_ANSWER_SOURCE_STATE_ONLY',
        'context':1048576,'default_output':262144,'benchmark_cap':32768,'effort':100,'drafter':True,
        'pack_relative_to_E':row['pack_relative_to_E'],'tokenizer_source_sha256':row['tokenizer_sha256'],
        'effective_template':provenance,'cases':cases,'actual_prompt_tokens':len(ids),'automatic_next_arm':False,
        'performance_or_general_quality_proof':False,'request_source_sha256':SOURCE_SHA}
