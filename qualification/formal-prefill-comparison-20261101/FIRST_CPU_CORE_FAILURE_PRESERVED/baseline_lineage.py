"""Accepted baseline92 finite/known-workload lineage; no payload scan or replay."""
import hashlib,json,re
from pathlib import Path
import selected92_observer as selected
HERE=Path(__file__).resolve().parent
E=HERE.parents[1]

def require(value,message):
    if not value:raise ValueError(message)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def contract(review,audit,registry,fixtureA,fixtureB):
    require(review.get('accepted') is True and review.get('fully_reviewed') is True and review.get('arm')=='QS0'
            and review.get('decision')=='QS0_FOUR_STATE_BASELINE_QUALITY_SCREEN_ACCEPTED_NO_QS1_ADMISSION','Accepted source-specific baseline review')
    row=registry.get('QS0',{})
    require(row.get('attempted') is True and row.get('accepted') is True and row.get('fully_reviewed') is True
            and row.get('performance_qualified') is False and row.get('deployment_admitted') is False,'Original baseline finite screen remains scoped')
    require(audit.get('passed') is True and audit.get('stage')=='COMPLETE' and audit.get('mode')=='quality' and audit.get('arm')=='QS0'
            and audit.get('whole_pack_factor',{}).get('native_sha256')==selected.NATIVE_SHA
            and audit.get('qualification_sha256')==review['qualification_sha256']=='14d2f954bfe20186561b3e0f19a2773e110871f5907623c4d291629e94f118af'
            and audit.get('performance_claim') is False and audit.get('deployment_admitted') is False,'Exact accepted92 finite authority')
    require(len(audit['rows'])==4 and review['finite_scan_scope']['all_finite'] is True,'Four complete prior finite scans')
    for r in audit['rows']:
        require(r.get('typed_known_answer_correct') is True and r.get('natural_stop') is True,'Prior known answer and naturalstop required')
        d=r['dump'];require(d['all_finite'] is True and type(d['rows']) is int and d['rows']>0
            and type(d['bytes']) is int and d['bytes']==d['rows']*129280*4 and re.fullmatch('[0-9a-f]{64}',d['sha256'])
            and d['token_row_alignment_claimed'] is False,'Complete finite full-vocabulary bytes, no token alignment inference')
    fence=audit['private_fence'];require(fence['passed'] is True and type(fence['memory_max']) is int and fence['memory_max']==80*2**30 and type(fence['swap_max']) is int and fence['swap_max']==0
            and fence['events_delta']['oom']==fence['events_delta']['oom_kill']==0 and fence['prior_properties_restored'] is True
            and fence['transient_collected'] is True,'Prior selected92 owned finite closure')
    A,B=fixtureA['cases'][0],fixtureB['cases'][0]
    require(A['id']==B['id']=='ms-quality-cold-text' and A['kind']==B['kind']=='json' and A['prompt_tokens']==B['prompt_tokens']==8469
            and A['request']==B['request'] and A['prompt_ids']==B['prompt_ids'] and A['expected']==B['expected']=={'values':list(range(1,65))}
            and A['prompt_ids_sha256']==B['prompt_ids_sha256']=='010205e8f361a49baf7182628639afd8114a55a40224b5a06f86487d87ac3e65','Literal common complete8469 request and IDs')
    n=audit['rows'][0]['native'];require(type(n['prompt_tokens']) is int and n['prompt_tokens']==8469 and type(n['prompt_ms']) in (int,float) and n['prompt_ms']==8969.3 and type(n['reused']) is int and n['reused']==0 and n['finish']=='stop','Actual historical common workload, not extrapolation')
    return True

def guard(q):
    path=HERE/'BASELINE_LINEAGE_FROZEN.json';require(q['files'].get(str(path))==sha(path),'Baseline lineage membership')
    frozen=json.loads(path.read_text());documents={}
    for name,row in frozen.items():
        rel=Path(row['relative_to_E']);require(not rel.is_absolute() and '..' not in rel.parts,'Canonical original baseline source')
        p=E/rel;require(p.is_file() and not p.is_symlink() and p.resolve()==p and p.stat().st_size<4*2**20
                       and q['files'].get(str(p))==row['sha256']==sha(p),'Exact baseline accepted evidence pin')
        documents[name]=json.loads(p.read_text())
    require(set(documents)=={'review','audit','registry','fixtureA','fixtureB'},'Complete baseline lineage')
    require(frozen['audit']['sha256']==documents['review']['terminal_audit_sha256']==documents['registry']['QS0']['terminal_sha256'],'Original independent terminal pin')
    selected.source_contract((HERE/'selected92-source/ds4_main.cpp').read_bytes(),(HERE/'selected92-source/ds4_model.cu').read_bytes())
    return contract(**documents)
