"""Five separately frozen cases, lifecycle first; no generated-code execution."""
import current_config as config

def require(ok,msg):
    if not ok:raise ValueError(msg)

def run_suite(cases,folder,pid,deadline,*,issue,cancel,fixtures,controls,save_progress=lambda v:None):
    value={'complete':False,'scores':[{'id':c['id'],'passed':False,'status':'UNRUN'} for c in cases],'rows':[],'retry':False,'automatic_next_arm':False,'quality_or_performance_pass':False,'manual_review_required':True}
    responses={};save_progress(value)
    for i,case in enumerate(cases):
        try:
            require(case['kind'] in ('code','tool','json','literal','prefill-cancel') and type(case['prompt_tokens']) is int and case['prompt_tokens']>0 and case['request']['max_tokens']==32768 and case['request']['reasoning_effort']==100,'Fixed broader request and full cap/effort')
            require(config.normalized(case['request'])==case['request_sha256'] and config.normalized(case['prompt_ids'])==case['prompt_ids_sha256'],'Exact source request and prompt IDs')
            if case.get('dependency'):require(case['dependency'] in responses,'Prior dependency response absent')
            actual=controls.prior.followup_case(case,responses[case['dependency']],fixtures) if case['id']=='ms-prose-tool-followup' else case
            value['scores'][i]['status']='ISSUED_REVIEW_PENDING';save_progress(value)
            if case['kind']=='prefill-cancel':
                response,proof=cancel(actual,folder,pid,deadline);row=controls.prior.cancel_score(case,response,proof)
            else:
                response,proof=issue(actual,folder,pid,deadline)
                row=controls.score(case,response,proof,quality=False)
                require(row['native']['decode_ms']>0,'Positive natural decode duration')
                row['emitted_token_contract']=proof.get('emitted_token_contract')
            require(type(proof.get('prompt_tokens')) is int and proof['prompt_tokens']==case['prompt_tokens'],'Exact actual native prompt count')
            responses[case['id']]=response;value['rows'].append(row)
            value['scores'][i].update(passed=True,status='CONFIRMED_PREFILL_CANCEL_PASSED' if case['kind']=='prefill-cancel' else 'NATURAL_RESULT_SOURCE_AND_STATE_PASSED')
            save_progress(value)
        except controls.Incomplete as exc:
            value['scores'][i].update(status='UNRUN' if getattr(exc,'native_started',None) is False else 'WRONG_CAP_PARTIAL_HOLD',reason=str(exc));save_progress(value);return value
        except BaseException as exc:
            value['scores'][i].update(status='EXECUTION_FAULT_HOLD',reason=repr(exc))
            try:save_progress(value)
            except BaseException as secondary:exc.add_note('Broader progress: '+repr(secondary))
            raise
    value['complete']=True;save_progress(value);return value
