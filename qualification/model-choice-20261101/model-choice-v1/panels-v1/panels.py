"""Re-encode exact public quality/timing/lifecycle work under each original pack template.

CPU fixtures only. No model run or cold-bound/timing/deployment admission.
"""
import copy,hashlib,importlib.util,json,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'fixtures-v1/fixtures.py'
PRIOR_SHA='c9becdd55427156300d4c1ae4ab17fd60a76c2e393bbcc5d56866b62e23c95fc'

def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def prior():
    require(sha(PRIOR)==PRIOR_SHA,'Exact first qualified candidate fixture support')
    name='model_choice_qualified_fixture_support'
    if name not in sys.modules:
        s=importlib.util.spec_from_file_location(name,PRIOR);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m)
    m=sys.modules[name];require(Path(m.__file__)==PRIOR,'Exact support origin');return m

def requests(f,mode):
    require(mode in ('quality','prose','coding','lifecycle'),'Explicit unchanged visible panel')
    f.validate_request_sources()
    if mode=='quality':cases=f.quality_cases(f.source_images()[0])
    elif mode=='lifecycle':cases=f.lifecycle_cases()
    else:cases=f.performance_cases(mode)
    f.validate_requests(cases,mode)
    return cases

def contract(manifest,f):
    require(manifest['candidate'] in ('HGU','UNSLOTH') and manifest['mode'] in ('quality','prose','coding','lifecycle'),'Exact candidate/panel')
    require(manifest['context']==1048576 and manifest['default_output']==262144 and manifest['policy']==f.POLICY,'Same full capacity/request policy')
    q=prior();row,pack,raw=q.pack_inputs(manifest['candidate'])
    require(manifest['pack_relative_to_E']==row['pack_relative_to_E'] and manifest['tokenizer_source_sha256']==row['tokenizer_sha256'] and manifest['request_source_sha256']==f.SOURCE_PINS,'Exact pack and public request provenance')
    require(manifest['effective_template']==f.effective_template(f.load_support(),pack/'tokenizer',raw)[1],'Original effective template retained')
    expected=requests(f,manifest['mode']);cases=manifest['cases'];require(len(cases)==len(expected),'Complete visible work')
    clean=[{k:v for k,v in c.items() if k not in f.ENCODED_KEYS} for c in cases]
    require(f.packed(clean)==f.packed(expected),'Visible tasks/policy cannot be resized or rewritten')
    f.validate_encoded(cases,manifest['mode'])
    for c in cases:require(c['request']['max_tokens']==32768 and c['request']['reasoning_effort']==100,'Full benchmark policy')
    require(manifest['GPU_launch_ready'] is False and manifest['quality_or_performance_pass'] is False and manifest['automatic_next_arm'] is False,'Encoding is no model admission')
    return True

def encode(candidate,mode):
    q=prior();row,pack,raw=q.pack_inputs(candidate);f=q.helper();cases=requests(f,mode)
    tokens,merges,types,cfg=f.tokenizer_schema(raw);support=f.load_support();s=support.server
    tokenizer=support.ST.Tokenizer(tokens,merges,types,cfg['pre'],cfg['special_ids'])
    template,provenance=f.effective_template(support,pack/'tokenizer',raw)
    with tempfile.TemporaryDirectory(prefix='public-model-panel-') as tmp:
        vision=support.ds4_vision.Vision(support.ds4_vision.Geometry(),Path(tmp),s.Vision.load)
        try:
            service=s.Service(s.MockEngine(tokenizer,['CPU'],max_context=1048576),tokenizer,s.ChatTemplate(template),vision=vision,fit_max_tokens=False)
            service.set_family('deepseek41');service.answer_room=False;service.reasoning_budget_configured=True
            service.reasoning_budget_tokens=0;service.reasoning_loop_recovery=False;service.repeat_stop_tokens=0
            def encode_request(body):
                messages,tools,kwargs=s.openai_to_messages(copy.deepcopy(body))
                messages,_=s.prepare_format(body.get('response_format'),messages,with_tools=bool(tools))
                return service.encode_prompt(messages,tools,kwargs,store=False)
            result=[]
            for case in cases:
                ids=encode_request(case['request'])
                result.append({**copy.deepcopy(case),'prompt_ids':ids,'prompt_tokens':len(ids),'image_spans':f.image_spans(ids),'prompt_ids_sha256':q.digest(ids),'request_sha256':q.digest(case['request'])})
            if mode=='lifecycle':
                for callid in ('maya-s-alternate-call-1','different-provider-ID-2'):
                    require(encode_request(f.tool_followup(f.synthetic_call(callid)))==result[1]['prompt_ids'],'Actual per-pack DSML call-ID normalization')
            require('torch' not in sys.modules,'CPU-only public encoding')
            require(q.pack_inputs(candidate)[0]==row and f.effective_template(support,pack/'tokenizer',raw)==(template,provenance),'Actual pack/template source drift')
        finally:vision.shutdown()
    manifest={'id':'public-model-'+candidate+'-'+mode+'-v1','candidate':candidate,'mode':mode,'context':1048576,'default_output':262144,'policy':dict(f.POLICY),'pack_relative_to_E':row['pack_relative_to_E'],'tokenizer_source_sha256':row['tokenizer_sha256'],'effective_template':provenance,'request_source_sha256':dict(f.SOURCE_PINS),'cases':result,'GPU_launch_ready':False,'quality_or_performance_pass':False,'automatic_next_arm':False,'cold_bound_measured':False,'near_full_context_or_output_tested':False,'CPU_only':True}
    contract(manifest,f);return manifest
