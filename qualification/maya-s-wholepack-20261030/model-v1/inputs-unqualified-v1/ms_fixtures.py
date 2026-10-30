"""New whole-pack family requests; explicit pack CPU encoding, never model execution."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

HERE=Path(__file__).resolve().parent
E=HERE.parents[2]
V=E/'native-vision-v2'
BASE_PACK=E/'pack-native-vision-v1'
CANDIDATE_PACK=HERE.parent/'pack-v1/pack-FIRST'
POLICY={'model':'deepseek-v4.1-flash-iq2-xs','stream':True,'reasoning_effort':100,
        'reasoning_budget_tokens':0,'temperature':1.0,'top_p':1.0,'seed':1,'max_tokens':32768}
QUALITY_IDS=('ms-quality-cold-text','ms-quality-warm-text','ms-quality-two-images','ms-quality-return-text')
TIMED_IDS={mode:('ms-'+mode+'-cold-json','ms-'+mode+'-warm-json','ms-'+mode+'-main') for mode in ('prose','coding')}
LIFECYCLE_IDS=('ms-prose-tool','ms-prose-tool-followup','ms-prose-prefill-cancel','ms-prose-prefill-recovery')
LINE='Synthetic ledger: item=seven; status=reviewed; immutable=true.\n'
IMAGE_SOURCE='prefill-cache-improvements-20261027/numerical-fixtures/manifest.json'
PROSE_SOURCE='decode-optimization-20261028/prose-speed-v1/prose-fixtures.json'
CODE_SOURCE='prefill-v2/frozen/manifest.json'
SOURCE_PINS={
 IMAGE_SOURCE:'251f89c1949f43308994a2a08805195ff7069eb4f11642920ed442168db10061',
 PROSE_SOURCE:'8039ba7415335710ab481c5cd29f3c2c1bffb19b223d83ec586baf759a336faf',
 CODE_SOURCE:'d3e557d528aeea5e3765f73f6454ddd657b204fb8be6aa3351618cfb739ecdb1'}
SUPPORT_PINS={
 'native-vision-v2/test_native_vision.py':'3875dc32895821ded8a6929e5a4f5515cdfbe233cf43910d1ed7b5e723f70059',
 'native-vision-v2/runtime/serve/server.py':'b1be40294f6c49692829ad5f85a7aa2867218180fdc8fbc9bef7710371ba3b9f',
 'native-vision-v2/runtime/serve/ds4_vision.py':'761212e162004aacf591beb405dc8072f83ee1facaa5398013ec98d5c737da4e',
 'native-vision-v2/runtime/serve/dsml.py':'27717ea9099dcdff1f61203d5104c9cab1a3e3b45962edcfa02d5586e723255d',
 'native-vision-v2/runtime/tools/strata_tokenizer.py':'6db1ea62d3edbaa64dce139088146ccf370933998d5f997cd5f41a39300075a6'}
TOKENIZER_NAMES=('vocab.json','merges.txt','token_type.json','tokenizer.json','chat_template.jinja')
BASE_TOKENIZER_PINS={'vocab.json':'2f0bf5b31f4aa191d5d0d78291927a4f28c9ceb498a5e345b97e926c4cb99c1a',
 'merges.txt':'547bace837acea98652eef5669c9b01cee1c73ad1d2a44d6fdce9e6a81c22147',
 'token_type.json':'0a61021438e5ce6041133495f18fc360a6587aea748b17d953f552d2119ba51e',
 'tokenizer.json':'5a47981b685b75154e29bfb0299584c9b3a4a28679585e86d524c34c065d037f',
 'chat_template.jinja':'6f9bd1f87d9dad376b4c79683934b4254396d826ae514ab0244efa904ce1d1a4'}


def packed(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)


def checked_source(name):
    raw=(E/name).read_bytes();require(sha(raw)==SOURCE_PINS[name],'Frozen request source changed')
    return json.loads(raw)


def source_images():
    old=checked_source(IMAGE_SOURCE);case=next(c for c in old['cases'] if c['id']=='two-images')
    urls=[p['image_url']['url'] for p in case['request']['messages'][0]['content'] if p['type']=='image_url']
    validate_urls(urls)
    hashes=[sha(base64.b64decode(u.split(',',1)[1],validate=True)) for u in urls]
    require(hashes==old['images_sha256'],'Frozen PNG bytes changed')
    return urls,hashes


def validate_urls(urls):
    require(type(urls) is list and len(urls)==2,'Exactly two synthetic PNGs required')
    for url in urls:
        require(type(url) is str and url.startswith('data:image/png;base64,'),'No remote/user image source')
        require(base64.b64decode(url.split(',',1)[1],validate=True).startswith(b'\x89PNG\r\n\x1a\n'),'PNG signature')


def request(content,json_only=False):
    body={**POLICY,'messages':[{'role':'user','content':content}]}
    if json_only:body['response_format']={'type':'json_object'}
    return body


def sequence(mode):
    require(mode in ('quality','prose','coding'),'Unknown fixture mode')
    return request('Synthetic Maya-S whole-pack '+mode+' state T.\n'+LINE*520+
        '\nReturn only JSON with the single key "values", whose value is the array of every integer from 1 through 64, '
        'in ascending order, exactly once. Do not include the ledger or any other keys.',True)


def quality_cases(urls):
    validate_urls(urls)
    pictures=request([{'type':'text','text':'Synthetic Maya-S whole-pack quality state I.\n'+LINE*12},
        {'type':'image_url','image_url':{'url':urls[0]}},{'type':'text','text':LINE*400},
        {'type':'image_url','image_url':{'url':urls[1]}},{'type':'text','text':LINE*95+
        '\nReturn only JSON with keys "first" and "second", each a lowercase string naming the corresponding picture predominant color.'}],True)
    return [{'id':cid,'kind':'json','request':copy.deepcopy(pictures if i==2 else sequence('quality')),
             'expected':{'first':'red','second':'blue'} if i==2 else {'values':list(range(1,65))},
             'expected_reuse':'zero' if i in (0,2) else 'prompt-minus-one'} for i,cid in enumerate(QUALITY_IDS)]


# Exact visible work from pinned prose8039 and code d3e557; new case IDs only.
PROSE_CASES = [{'id': 'expository-prose', 'request': {'model': 'deepseek-v4.1-flash-iq2-xs', 'stream': True, 'reasoning_effort': 100, 'reasoning_budget_tokens': 0, 'temperature': 1.0, 'top_p': 1.0, 'seed': 1, 'max_tokens': 32768, 'messages': [{'role': 'user', 'content': 'Synthetic prose speed fixture P0 expository, 2026-10-29.\nWrite about 800 to 1000 words of clear continuous prose for a curious general reader explaining how a hash table finds a value. Explain hash functions and buckets, collision handling by chaining, the load factor and resizing, and why expected constant-time lookup differs from worst-case linear lookup. Include one small worked example using the keys cedar, maple and pine with explicitly made-up bucket assignments, without presenting those assignments as a real hash function. Use paragraphs, not code, tables, lists or headings. Complete the explanation naturally. End with exactly this sentence: That is how the lookup finds its way.'}]}, 'expected_last_sentence': 'That is how the lookup finds its way.', 'requested_words': [800, 1000], 'length_is_observed_not_fitted': True}, {'id': 'creative-prose', 'request': {'model': 'deepseek-v4.1-flash-iq2-xs', 'stream': True, 'reasoning_effort': 100, 'reasoning_budget_tokens': 0, 'temperature': 1.0, 'top_p': 1.0, 'seed': 1, 'max_tokens': 32768, 'messages': [{'role': 'user', 'content': 'Synthetic prose speed fixture P0 creative, 2026-10-29.\nWrite a self-contained literary short story of about 800 to 1000 words in natural, varied prose. In a small coastal village, a clock repairer named Mara returns to repair the clock at the old ferry terminal with her father Ilan. Their disagreement concerns whether the terminal should be preserved or replaced. Let the work on the clock change their understanding of each other, using sensory detail and believable dialogue. Keep the setting realistic, without magic or a sudden disaster. Use paragraphs without headings, lists or commentary about the writing. Give the story a complete ending. End with exactly this sentence: By morning, the clock was keeping ordinary time.'}]}, 'expected_last_sentence': 'By morning, the clock was keeping ordinary time.', 'requested_words': [800, 1000], 'length_is_observed_not_fitted': True}]
CODE_REQUEST = {'max_tokens': 32768, 'messages': [{'content': 'Write one complete Python3 module containing coalesce_ranges(ranges) plus unittest tests. Input is a list of pairs of integer half-open bounds [start,end). Reject bool and non-integer endpoints with TypeError; reject start>end with ValueError. Drop zero-length ranges. Return a sorted list of disjoint (start,end) tuples, merging overlaps and touching intervals. Never mutate input, including on errors. Handle negative and large integers. Use only the standard library. Include independent-looking tests for every rule. Return only the module, without prose.', 'role': 'user'}], 'model': 'deepseek-v4.1-flash-iq2-xs', 'reasoning_budget_tokens': 0, 'reasoning_effort': 100, 'seed': 1, 'stream': True, 'temperature': 1.0, 'top_p': 1.0}


def performance_cases(mode):
    require(mode in TIMED_IDS,'Exact separate timed family required')
    ids=TIMED_IDS[mode]
    cases=[{'id':cid,'kind':'json','request':sequence(mode),'expected':{'values':list(range(1,65))},
            'expected_reuse':'zero' if i==0 else 'prompt-minus-one'} for i,cid in enumerate(ids[:2])]
    if mode=='prose':
        cases.append({**copy.deepcopy(PROSE_CASES[0]),'id':ids[2],'kind':'prose','expected_reuse':'zero',
                      'manual_quality_review_required':True})
    else:
        cases.append({'id':ids[2],'kind':'code','request':copy.deepcopy(CODE_REQUEST),'expected_reuse':'zero',
                      'manual_quality_review_required':True,'generated_code_execution_admitted':False})
    return cases


TOOL_REQUEST = {'max_tokens': 32768, 'messages': [{'content': 'Use lookup_quote once for SKU PF2-731, quantity6. After the supplied tool result, return only JSON sku(string),quantity(integer),total_cents(integer),available(boolean). Price is unit_cents times quantity; available means stock is at least quantity.', 'role': 'user'}], 'model': 'deepseek-v4.1-flash-iq2-xs', 'reasoning_budget_tokens': 0, 'reasoning_effort': 100, 'seed': 1, 'stream': True, 'temperature': 1.0, 'tools': [{'function': {'description': 'Synthetic stock and price lookup; never contact external systems.', 'name': 'lookup_quote', 'parameters': {'additionalProperties': False, 'properties': {'quantity': {'type': 'integer'}, 'sku': {'type': 'string'}}, 'required': ['sku', 'quantity'], 'type': 'object'}}, 'type': 'function'}], 'top_p': 1.0}
TOOL_ARGS={'sku':'PF2-731','quantity':6}
TOOL_RESULT={'sku':'PF2-731','stock':17,'unit_cents':185}
TOOL_EXPECTED={'sku':'PF2-731','quantity':6,'total_cents':1110,'available':True}
FROZEN_CALL_ID='maya-s-frozen-call'


def tool_followup(first):
    require(type(first) is dict and first.get('finish_reason')=='tool_calls','Natural tool-call stop required')
    calls=first.get('tool_calls');require(type(calls) is list and len(calls)==1,'Exactly one actual call required')
    call=calls[0];require(type(call) is dict and type(call.get('id')) is str and bool(call['id']) and call.get('type')=='function','Typed actual tool call ID/type')
    fun=call.get('function');require(type(fun) is dict and fun.get('name')=='lookup_quote' and type(fun.get('arguments')) is str,'Exact tool name/arguments')
    def unique(pairs):
        out={}
        for k,v in pairs:
            require(k not in out,'Duplicate tool argument');out[k]=v
        return out
    args=json.loads(fun['arguments'],object_pairs_hook=unique)
    require(type(args) is dict and set(args)==set(TOOL_ARGS) and type(args.get('sku')) is str and type(args.get('quantity')) is int and args==TOOL_ARGS,'Exact typed synthetic tool arguments')
    normalized={'id':call['id'],'type':'function','function':{'name':'lookup_quote','arguments':json.dumps(TOOL_ARGS)}}
    body=copy.deepcopy(TOOL_REQUEST)
    body['messages'] += [{'role':'assistant','content':'','tool_calls':[normalized]},
        {'role':'tool','tool_call_id':call['id'],'content':json.dumps(TOOL_RESULT,sort_keys=True)}]
    return body


def synthetic_call(identifier):
    return {'finish_reason':'tool_calls','tool_calls':[{'id':identifier,'type':'function',
            'function':{'name':'lookup_quote','arguments':json.dumps(TOOL_ARGS)}}]}


def lifecycle_cases():
    cancelled=sequence('prose')
    cancelled['messages'][0]['content']=cancelled['messages'][0]['content'].replace(
        'Synthetic Maya-S whole-pack prose state T.','Synthetic Maya-S whole-pack prose prefill cancellation C.')
    return [
        {'id':LIFECYCLE_IDS[0],'kind':'tool','request':copy.deepcopy(TOOL_REQUEST),'expected_tool':{'name':'lookup_quote','arguments':dict(TOOL_ARGS)}},
        {'id':LIFECYCLE_IDS[1],'kind':'json','dependency':LIFECYCLE_IDS[0],'request':tool_followup(synthetic_call(FROZEN_CALL_ID)),'expected':dict(TOOL_EXPECTED)},
        {'id':LIFECYCLE_IDS[2],'kind':'prefill-cancel','request':cancelled,'purpose':'INTENTIONAL_CONFIRMED_PARTIAL_NOT_SPEED_OR_QUALITY'},
        {'id':LIFECYCLE_IDS[3],'kind':'literal','dependency':LIFECYCLE_IDS[2],
         'request':request('Return exactly RECOVERED_Q8_LITERAL and nothing else.'),'expected':'RECOVERED_Q8_LITERAL'}]


def validate_request_sources():
    prose=checked_source(PROSE_SOURCE);code=checked_source(CODE_SOURCE)
    require(packed(PROSE_CASES)==packed(prose['cases']),'Literal prose work changed')
    original=next(c for c in code['cases'] if c['id']=='coding-ranges')
    require(packed(CODE_REQUEST)==packed(original['request']),'Literal coding work changed')
    require(packed(TOOL_REQUEST)==packed(next(c['request'] for c in code['cases'] if c['id']=='tool-lookup')),'Literal tool work changed')


def validate_requests(cases,mode):
    require(type(cases) is list and mode in ('quality','prose','coding','lifecycle'),'Fixture mode/list')
    if mode=='quality':
        require(len(cases)==4,'Four quality cases')
        urls=[p['image_url']['url'] for p in cases[2]['request']['messages'][0]['content'] if p['type']=='image_url']
        expected=quality_cases(urls)
    else:expected=lifecycle_cases() if mode=='lifecycle' else performance_cases(mode)
    require(packed(cases)==packed(expected),'Exact typed request/answer/reuse/IDs required')
    for c in cases:
        for k,v in POLICY.items():require(type(c['request'].get(k)) is type(v) and c['request'][k]==v,'Full request policy changed')
    return cases


def image_spans(ids):
    out=[];start=None
    for i,t in enumerate([*ids,-1]):
        if t==129264 and start is None:start=i
        if t!=129264 and start is not None:out.append({'start':start,'length':i-start});start=None
    return out


ENCODED_KEYS={'prompt_ids','prompt_tokens','prompt_ids_sha256','request_sha256','image_spans'}
def validate_encoded(cases,mode):
    validate_requests([{k:v for k,v in c.items() if k not in ENCODED_KEYS} for c in cases],mode)
    for i,c in enumerate(cases):
        ids=c['prompt_ids'];require(type(ids) is list and all(type(x) is int and 0<=x<129280 for x in ids),'Vocabulary IDs')
        long=mode=='quality' or mode in TIMED_IDS and i<2 or mode=='lifecycle' and c['kind']=='prefill-cancel'
        lo,hi=(6000,11999) if long else ((1,2048) if mode=='lifecycle' else (64,2048))
        require(lo<=len(ids)<=hi and type(c['prompt_tokens']) is int and c['prompt_tokens']==len(ids),'Frozen prompt bounds; no resizing')
        require(c['prompt_ids_sha256']==sha(packed(ids)) and c['request_sha256']==sha(packed(c['request'])),'Encoded hash mismatch')
        require(c['image_spans']==image_spans(ids),'Image spans mismatch')
        require(mode=='quality' and i==2 or not c['image_spans'],'Unexpected image tokens')
    for i in ((1,3) if mode=='quality' else (() if mode=='lifecycle' else (1,))):
        require(cases[i]['prompt_ids']==cases[0]['prompt_ids'],'Warm/return text differs')
    if mode=='quality':
        spans=cases[2]['image_spans'];cut=cases[2]['prompt_tokens']-2668
        require(len(spans)==2 and spans[0]['start']+spans[0]['length']<=cut and spans[1]['start']>=cut,'Image before cut and retained tail required')
    return cases


def load_support():
    # Parent CPU qualification pins the entire inherited import closure before this call.
    for name,pin in SUPPORT_PINS.items():require(sha((E/name).read_bytes())==pin,'Pinned API support changed')
    for name,path in [('serve.server',V/'runtime/serve/server.py'),('serve.ds4_vision',V/'runtime/serve/ds4_vision.py'),
                      ('serve.dsml',V/'runtime/serve/dsml.py'),('strata_tokenizer',V/'runtime/tools/strata_tokenizer.py')]:
        loaded=sys.modules.get(name)
        if loaded is not None:require(Path(getattr(loaded,'__file__','')).resolve()==path.resolve(),'Foreign support module before import')
    spec=importlib.util.spec_from_file_location('ms_native_vision_cpu_support',V/'test_native_vision.py')
    s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
    for module,name in ((s.server,'runtime/serve/server.py'),(s.ds4_vision,'runtime/serve/ds4_vision.py'),
                        (s.dsml,'runtime/serve/dsml.py'),(s.ST,'runtime/tools/strata_tokenizer.py')):
        require(Path(module.__file__).resolve()==(V/name).resolve(),'Foreign support module origin')
    require('torch' not in sys.modules,'GPU framework forbidden')
    return s


def tokenizer_directory(pack):
    p=Path(pack)
    require(p.is_absolute() and '..' not in p.parts and p in (BASE_PACK,CANDIDATE_PACK),'Explicit approved pack required')
    return V/'tokenizer' if p==BASE_PACK else p/'tokenizer'


def tokenizer_bytes(pack):
    directory=tokenizer_directory(pack)
    require(directory.is_relative_to(E),'Tokenizer evidence containment')
    current=E
    require(not current.is_symlink(),'Evidence root alias')
    for part in directory.relative_to(E).parts:
        current=current/part;require(not current.is_symlink() and current.is_dir(),'Tokenizer directory alias/missing')
    raw={}
    for name in TOKENIZER_NAMES:
        p=directory/name
        require(not p.is_symlink() and p.is_file() and p.stat().st_size<=64*1024**2,'Tokenizer file alias/missing/oversize')
        raw[name]=p.read_bytes()
    pins={k:sha(v) for k,v in raw.items()}
    if Path(pack)==BASE_PACK:require(pins==BASE_TOKENIZER_PINS,'Verified baseline tokenizer fixture changed')
    return raw,pins,directory


def tokenizer_schema(raw):
    def unique(items):
        out={}
        for k,v in items:
            require(k not in out,'Duplicate tokenizer JSON key');out[k]=v
        return out
    def read(name):return json.loads(raw[name],object_pairs_hook=unique)
    vocab=read('vocab.json');types=read('token_type.json');cfg=read('tokenizer.json')
    require(type(vocab) is dict and len(vocab)==129280 and all(type(k) is str and type(v) is int for k,v in vocab.items()) and set(vocab.values())==set(range(129280)),'Exact bijective vocabulary')
    require(type(types) is list and len(types)==129280 and all(type(t) is int and 0<=t<=6 for t in types),'Token types')
    special=cfg.get('special_ids')
    require(cfg.get('pre')=='deepseek3' and type(special) is dict and set(special)=={'bos','eos','pad'} and all(type(x) is int and 0<=x<129280 for x in special.values()) and special['bos']==0 and special['eos']==1,'Native tokenizer/special IDs')
    tokens=[None]*129280
    for t,i in vocab.items():tokens[i]=t
    require(bool(raw['chat_template.jinja'].decode('utf-8').strip()),'Native chat template missing')
    return tokens,raw['merges.txt'].decode('utf-8').split('\n'),types,cfg


def encode(cases,mode,pack):
    validate_requests(cases,mode);raw,pins,directory=tokenizer_bytes(pack);tokens,merges,types,cfg=tokenizer_schema(raw)
    support=load_support();s=support.server
    tok=support.ST.Tokenizer(tokens,merges,types,cfg['pre'],cfg['special_ids'])
    selected,swapped=support.dsml.pick_template(directory/'chat_template.jinja')
    require(not swapped and Path(selected)==directory/'chat_template.jinja','No template substitution/fallback')
    with tempfile.TemporaryDirectory(prefix='maya-s-cpu-images-') as tmp:
        vision=support.ds4_vision.Vision(support.ds4_vision.Geometry(),Path(tmp),s.Vision.load)
        try:
            svc=s.Service(s.MockEngine(tok,['CPU'],max_context=1048576),tok,s.ChatTemplate(selected),vision=vision,fit_max_tokens=False)
            svc.set_family('deepseek41');svc.answer_room=False;svc.reasoning_budget_configured=True
            svc.reasoning_budget_tokens=0;svc.reasoning_loop_recovery=False;svc.repeat_stop_tokens=0
            def encode_body(body):
                messages,tools,kwargs=s.openai_to_messages(copy.deepcopy(body))
                messages,_=s.prepare_format(body.get('response_format'),messages,with_tools=bool(tools))
                return svc.encode_prompt(messages,tools,kwargs,store=False)
            result=[]
            for c in cases:
                body=copy.deepcopy(c['request']);ids=encode_body(body)
                result.append({**copy.deepcopy(c),'prompt_ids':ids,'prompt_tokens':len(ids),'image_spans':image_spans(ids),
                               'prompt_ids_sha256':sha(packed(ids)),'request_sha256':sha(packed(body))})
            if mode=='lifecycle':
                for alternate in ('maya-s-alternate-call-1','different-provider-ID-2'):
                    require(encode_body(tool_followup(synthetic_call(alternate)))==result[1]['prompt_ids'],'Actual pack DSML call-ID normalization failed')
            require('torch' not in sys.modules,'GPU framework forbidden')
            require(tokenizer_bytes(pack)[1]==pins,'Tokenizer changed during CPU encoding')
            return validate_encoded(result,mode),pins
        finally:vision.shutdown()


def build_manifest(pack,mode):
    require(mode in ('quality','prose','coding'),'Unknown manifest mode');tokenizer_directory(pack)
    validate_request_sources();urls,images=source_images()
    cases=quality_cases(urls) if mode=='quality' else performance_cases(mode)
    cases,pins=encode(cases,mode,pack)
    lifecycle=[]
    if mode=='prose':
        lifecycle,lpins=encode(lifecycle_cases(),'lifecycle',pack)
        require(lpins==pins,'Tokenizer changed between main/lifecycle encodings')
    return {'id':'maya-s-wholepack-'+mode+'-v1','mode':mode,'context':1048576,'default_output':262144,
            'policy':dict(POLICY),'pack_relative_to_E':str(Path(pack).relative_to(E)),
            'tokenizer_source_sha256':pins,'request_source_sha256':dict(SOURCE_PINS),'images_sha256':images,
            'API_sha256':SUPPORT_PINS['native-vision-v2/runtime/serve/server.py'],'cases':cases,
            'lifecycle_cases':lifecycle,'lifecycle_applies_only_to':{'mode':'prose','arms':['A1','B1']},
            'tool_call_ID_normalization_CPU_proved':bool(lifecycle),
            'lifecycle_unmeasured_no_dump':True,'creative_source_unmeasured_not_in_any_panel':True,
            'expected_reuse_tokens':[0 if c['expected_reuse']=='zero' else c['prompt_tokens']-1 for c in cases],
            'expected_mode1_activation_skipped_tokens':[c['prompt_tokens']-2668 for c in cases if c['kind']=='json' and c['expected_reuse']=='zero'],
            'CPU_only':True,'native_model_executed':False,'GPU_launch_ready':False,
            'whole_pack_factor_not_numerical_equivalence':True,
            'rows_per_request':'variable native batches; no per-token framing claim',
            'short_fixtures_do_not_establish_near_full_context_or_full_output':True}
