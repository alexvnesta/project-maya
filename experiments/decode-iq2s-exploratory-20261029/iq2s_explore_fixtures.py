"""Two short-input, full-cap known-answer requests. Import never encodes or writes."""
import copy,json,tempfile,sys
from pathlib import Path
from iq2s_explore_dependencies import fixtures as prior
POLICY=dict(prior.POLICY)
IDS=('sequence1024-cold','sequence1024-warm')
PURPOSE='EXPLORATORY_DESCRIPTIVE_DECODE_ONLY'
SERVER_SHA=prior.SERVER_SHA
packed=prior.packed
digest=prior.digest
load_support=prior.load_support

def make_cases():
    text=('Exploratory IQ2_S decode fixture.\n'+prior.LINE*80+
          '\nReturn only JSON with the single key "values", whose value is the array of every '
          'integer from 1 through 1024, in ascending order, exactly once. '
          'Do not include the ledger or any other keys.')
    request=prior.request(text)
    return [{'id':name,'kind':'json','purpose':PURPOSE,'request':copy.deepcopy(request),
             'expected':{'values':list(range(1,1025))},
             'expected_reuse':'zero' if i==0 else 'prompt-minus-one'} for i,name in enumerate(IDS)]

def validate_requests(cases):
    if packed(cases)!=packed(make_cases()):raise ValueError('Exact two full-cap synthetic requests required')
    return cases

def validate_encoded(cases):
    extra=('prompt_ids','prompt_tokens','prompt_ids_sha256','request_sha256','image_spans')
    validate_requests([{k:v for k,v in c.items()if k not in extra}for c in cases])
    for c in cases:
        ids=c['prompt_ids']
        if (type(ids)is not list or any(type(t)is not int or not 0<=t<129280 for t in ids)
            or not 1024<=len(ids)<=2048 or type(c['prompt_tokens'])is not int or c['prompt_tokens']!=len(ids)):
            raise ValueError('Actual short prompt must be1024..2048 valid tokens; no resizing')
        if c['prompt_ids_sha256']!=digest(packed(ids)) or c['request_sha256']!=digest(packed(c['request'])):
            raise ValueError('Actual prompt/request hashes differ')
        if c['image_spans'] or 129264 in ids:raise ValueError('No image tokens in narrow diagnostic')
    if cases[0]['prompt_ids']!=cases[1]['prompt_ids']:raise ValueError('Warm prompt must be identical')
    return cases

def validate_manifest(m):
    validate_encoded(m['cases'])
    expected={'id':'iq2s-exploratory-sequence1024-v1','purpose':PURPOSE,'context':1048576,'default_output':262144,
              'policy':POLICY,'prior_numerical_HOLD':True,'promotion_allowed':False,'GPU_launch_ready':False,
              'API_sha256':SERVER_SHA,'expected_reuse_tokens':[0,m['cases'][0]['prompt_tokens']-1],
              'expected_mode1_activation_skipped_tokens':[]}
    for k,v in expected.items():
        if packed(m.get(k))!=packed(v):raise ValueError('Frozen diagnostic manifest contract changed: '+k)
    if type(m.get('canonical_answer_tokens'))is not int or not 1<m['canonical_answer_tokens']<=4096:
        raise ValueError('Canonical answer outside predeclared CPU token budget')
    return m

def build_manifest():
    """FIRST admitted CPU encoder only. No model, output file or GPU admission."""
    cases=make_cases();validate_requests(cases)
    support=load_support();s=support.server;tok=support.tokenizer()
    # Same API template/settings as selected; no images or native process.
    with tempfile.TemporaryDirectory(prefix='iq2s-explore-cpu-') as tmp:
        vision=support.ds4_vision.Vision(support.ds4_vision.Geometry(),Path(tmp),s.Vision.load)
        try:
            svc=s.Service(s.MockEngine(tok,['CPU'],max_context=1048576),tok,
                          s.ChatTemplate(support.dsml.pick_template(prior.V/'tokenizer/chat_template.jinja')[0]),
                          vision=vision,fit_max_tokens=False)
            svc.set_family('deepseek41');svc.answer_room=False;svc.reasoning_budget_configured=True
            svc.reasoning_budget_tokens=0;svc.reasoning_loop_recovery=False;svc.repeat_stop_tokens=0
            encoded=[]
            for case in cases:
                body=json.loads(packed(case['request']));messages,tools,kwargs=s.openai_to_messages(body)
                messages,_=s.prepare_format(body.get('response_format'),messages,with_tools=bool(tools))
                ids=svc.encode_prompt(messages,tools,kwargs,store=False)
                encoded.append({**copy.deepcopy(case),'prompt_ids':ids,'prompt_tokens':len(ids),
                                'prompt_ids_sha256':digest(packed(ids)),'request_sha256':digest(packed(body)),
                                'image_spans':prior.image_spans(ids)})
            count=len(tok.encode(packed(cases[0]['expected']).decode()))
            if 'torch'in sys.modules:raise ValueError('Unexpected GPU framework')
            return validate_manifest({'id':'iq2s-exploratory-sequence1024-v1','purpose':PURPOSE,
                'context':1048576,'default_output':262144,'policy':dict(POLICY),'cases':encoded,
                'prior_numerical_HOLD':True,'promotion_allowed':False,'GPU_launch_ready':False,
                'API_sha256':SERVER_SHA,'expected_reuse_tokens':[0,encoded[0]['prompt_tokens']-1],
                'expected_mode1_activation_skipped_tokens':[],'canonical_answer_tokens':count})
        finally:vision.shutdown()
