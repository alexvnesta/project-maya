"""Descriptive paired fixed-task observations, never speed acceptance or promotion."""
import math
import iq2s_explore_fixtures as fixtures

def number(v,name,positive=False):
    if type(v)not in (int,float)or not math.isfinite(v)or (v<=0 if positive else v<0):
        raise ValueError('Finite nonnegative metric required: '+name)
    return v

def observation(row,response):
    n=row['native'];count=n['generated'];tokens=row['tokens']
    if type(count)is not int or not 1<count<32768 or len(tokens)!=count or any(type(t)is not int or not 0<=t<129280 for t in tokens):
        raise ValueError('Actual emitted token count/path required')
    if n['finish']!='stop' or row.get('natural_stop')is not True or row.get('typed_answer_correct')is not True:
        raise ValueError('Only completed correct known-answer observations')
    decode=number(n['decode_ms'],'decode_ms',True);prefill=number(n['prompt_ms'],'prompt_ms')
    client=number(response['client_full_seconds'],'client_full_seconds',True)
    visible={}
    for k in ('client_first_content_seconds','client_first_reasoning_seconds','client_first_tool_seconds'):
        v=response.get(k)
        if v is not None:
            number(v,k)
            if v>client:raise ValueError('Visible delta after completion')
        visible[k]=v
    return {'generated_tokens_including_reasoning':count,'native_decode_ms':decode,'native_tokens_per_second':count*1000/decode,
            'native_prefill_ms':prefill,'client_completion_seconds':client,
            'buffered_first_visible_delta_seconds':visible,'actual_TTFT_proven':False,
            'content_characters':len(response['content']),'reasoning_characters':len(response['reasoning']),
            'prompt_tokens':n['prompt_tokens'],'reused_tokens':n['reused'],
            'drafts_offered':n['drafts_offered'],'drafts_accepted':n['drafts_accepted'],
            'cache_hits':n['hits'],'cache_lookups':n['lookups']}

def compare(a,b):
    for arm,report in [('X0',a),('X1',b)]:
        if (report.get('passed')is not True or report.get('arm')!=arm or
            report.get('purpose')!=fixtures.PURPOSE or report.get('prior_numerical_HOLD')is not True or
            report.get('promotion_allowed')is not False or [x['id']for x in report['rows']]!=list(fixtures.IDS)):
            raise ValueError('Exact two audited diagnostic arms required')
    rows=[]
    for x,y in zip(a['rows'],b['rows']):
        if any(r.get('natural_stop')is not True or r.get('typed_answer_correct')is not True for r in (x,y)):
            raise ValueError('Wrong/partial case cannot be timed as completed useful work')
        if x['native']['prompt_tokens']!=y['native']['prompt_tokens']or x['native']['reused']!=y['native']['reused']:
            raise ValueError('Cache/prompt work differs')
        xo,yo=x['observations'],y['observations']
        for o in (xo,yo):
            for k in ('native_tokens_per_second','client_completion_seconds'):number(o[k],k,True)
        rows.append({'id':x['id'],'baseline':xo,'candidate':yo,'emitted_paths_identical':x['tokens']==y['tokens'],
            'diagnostic_native_rate_ratio':yo['native_tokens_per_second']/xo['native_tokens_per_second'],
            'fixed_known_answer_client_latency_ratio':yo['client_completion_seconds']/xo['client_completion_seconds'],
            'matched_token_speedup_claim':False})
    return {'purpose':fixtures.PURPOSE,'rows':rows,'prior_numerical_HOLD':True,'promotion_allowed':False,
            'speed_acceptance':False,'general_quality_claim':False,'replication_authorized':False,
            'scope':'Single observations per arm/case; identical correct visible task, variable reasoning and token paths. Native rates descriptive. Buffered visible delta is not real TTFT. No deployment qualification.'}
