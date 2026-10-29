"""Lightweight exploratory transport/known-answer checks. Never numerical acceptance."""
import pathlib,time
from iq2s_explore_dependencies import controls as prior
import iq2s_explore_fixtures as fixture
Incomplete=prior.NumericalIncomplete
owned_storage_snapshot=prior.owned_storage_snapshot
natural_contract=prior.natural_contract

def no_dumps(folder):
    if list(pathlib.Path(folder).glob('logits*')):raise ValueError('Numerical dump forbidden in timed exploratory mode')
    return True

def short_prompt_activation(log):
    # Selected model10968: a=0 unless n-2668>=1024; Run.yoco only set if a>0.
    #10996 prints only run.yoco>=0, so neither zero-skip nor positive line is expected.
    if any('ds4: prompt skip:'in x for x in log.splitlines()):raise ValueError('Unexpected short-prompt skip activation')
    return {'mode':1,'short_prompt_skip_expected':False,'activation_early_rows':[]}

def bounded_request(base,body,deadline,folder,*,stream_class,observe,wait_for,clock=time.monotonic):
    if deadline-clock()<10:return {'budget_not_started':True,'request_sent':False}
    stream=stream_class(base,body,timeout=1200).start();stop=None
    try:
        while not stream.finished.wait(min(.1,max(0,deadline-clock()))):
            no_dumps(folder)
            if owned_storage_snapshot(folder)['status']!='WITHIN_BUDGET':stop='PRIVATE_CACHE_OR_LOG_LIMIT';break
            if clock()>=deadline:stop='UNCHANGED_SOFT_DEADLINE';break
        if stop:
            stream.cancel();result=stream.result(1)
            def released():
                work=observe(base,'/v1/telemetry')['work']
                return all(type(work.get(k))is int and work[k]==0 for k in ('active','queued','admission_reserved'))
            wait_for(released,45,'Owned exploratory cancellation retained inference ownership')
            result.update(intentional_budget_stop=True,incomplete_reason=stop,retry=False)
            return result
        no_dumps(folder);result=stream.result(1)
        if owned_storage_snapshot(folder)['status']!='WITHIN_BUDGET':
            result.update(intentional_budget_stop=True,incomplete_reason='PRIVATE_CACHE_OR_LOG_LIMIT',retry=False)
        return result
    except BaseException as exc:
        exc.raw_transport={k:getattr(stream,k,None)for k in ('status','error','events','raw','content','reasoning','finish_reason','done')}
        raise
    finally:
        if stream.thread.is_alive():stream.cancel()

def run_cases(manifest,folder,pid,deadline,*,issue):
    fixture.validate_manifest(manifest);rows=[];current=None;complete=False;reason=None
    scores=[{'id':c['id'],'status':'UNRUN','passed':False}for c in manifest['cases']]
    try:
        for i,case in enumerate(manifest['cases']):
            current=i;scores[i]['status']='ISSUED_REVIEW_PENDING'
            response,proof=issue(case,folder,pid,deadline)
            rows.append(natural_contract(case,response,proof));scores[i].update(status='NATURAL_KNOWN_ANSWER_PASSED',passed=True)
        current=None;no_dumps(folder)
        if owned_storage_snapshot(folder)['status']!='WITHIN_BUDGET':raise Incomplete('Storage budget incomplete')
        complete=True
    except Incomplete as exc:
        reason=str(exc)
        if current is not None:scores[current].update(status='WRONG_CAP_PARTIAL_OR_UNRUN',reason=reason)
    return {'complete':complete,'rows':rows,'native_count':len(rows),'case_scores':scores,
            'unrun_ids':[x['id']for x in scores if x['status']=='UNRUN'],'incomplete_reason':reason,
            'prior_numerical_HOLD':True,'promotion_allowed':False,'quality_or_speed_pass':False,'retry':False}
