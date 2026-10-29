"""Full-cap natural numerical observations and bounded dump monitoring only."""
import array,hashlib,json,math,os,pathlib,stat,sys,time
import imma_config as config
import imma_fixtures as fixture
import imma_storage as storage

class NumericalIncomplete(Exception):pass
def emit(path,value):pathlib.Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def owned_storage_snapshot(folder):
    """Lightweight sizes only of this fresh private tree; never follow a link."""
    folder=pathlib.Path(folder);cache_bytes=0;log_bytes=0
    if folder.is_symlink() or not folder.is_dir():raise ValueError('Real private storage root required')
    for root,dirs,files in os.walk(folder,followlinks=False):
        root=pathlib.Path(root)
        for name in dirs:
            if (root/name).is_symlink():raise ValueError('Private directory symlink refused')
        for name in files:
            p=root/name
            try:st=p.lstat()
            except FileNotFoundError:continue # API may unlink its completed synthetic image temporary.
            if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:raise ValueError('Private nonregular/aliased file refused')
            if p.relative_to(folder).parts[0]=='cache':cache_bytes+=st.st_size
            else:log_bytes+=st.st_size # Includes dumps/traces/temporary images and CUDA driver cache.
    return {'cache_bytes':cache_bytes,'log_and_auxiliary_bytes':log_bytes,
            'status':'INCOMPLETE_HOLD' if cache_bytes>=8*2**30 or log_bytes>=4*2**30 else 'WITHIN_BUDGET',
            'private_cache_limit_bytes':8*2**30,'log_and_auxiliary_limit_bytes':4*2**30}
def dump_snapshot(folder,*,complete=False):
    folder=pathlib.Path(folder);entries=[]
    for p in sorted(folder.glob('logits.*.f32')):
        st=p.lstat()
        entries.append({'path':str(p),'bytes':st.st_size,'regular':stat.S_ISREG(st.st_mode),
                        'symlink':stat.S_ISLNK(st.st_mode),'nlink':st.st_nlink})
    return storage.dump_policy(str(folder),entries,complete=complete)

def dump_size(path):
    path=pathlib.Path(path);st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or not 0<st.st_size<storage.HARD_FILE_BYTES or st.st_size%storage.ROW_BYTES:
        raise ValueError('Incomplete/foreign numerical dump')
    return {'bytes':st.st_size,'rows':st.st_size//storage.ROW_BYTES,'finite_or_equivalence_proven':False}

def finite_dump(path):
    """OFFLINE after restoration: exact bytes/finite, one vocabulary row in RAM."""
    path=pathlib.Path(path);dump_size(path);st=path.lstat()
    h=hashlib.sha256();rows=0
    with path.open('rb') as f:
        while raw:=f.read(storage.ROW_BYTES):
            if len(raw)!=storage.ROW_BYTES:raise ValueError('Partial logit row')
            h.update(raw);values=array.array('f');values.frombytes(raw)
            if sys.byteorder!='little':values.byteswap()
            if not all(math.isfinite(x) for x in values):raise ValueError('Nonfinite model logit')
            rows+=1
    after=path.lstat()
    if (st.st_ino,st.st_size,st.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('Dump changed during finite audit')
    return {'bytes':st.st_size,'rows':rows,'sha256':h.hexdigest(),'all_finite':True,
            'token_row_alignment_claimed':False}

def natural_contract(case,response,proof):
    native=proof['native'];body=case['request']
    if (response.get('status')!=200 or response.get('done') is not True or response.get('cancelled') or
        response.get('finish_reason')!='stop' or native.get('finish')!='stop' or
        response.get('intentional_budget_stop') or response.get('budget_not_started')):
        raise NumericalIncomplete('Wrong/cap/partial/UNRUN numerical case remains scored HOLD')
    try:answer=json.loads(response['content'])
    except (ValueError,KeyError,TypeError):raise NumericalIncomplete('Numerical JSON answer invalid') from None
    if fixture.packed(answer)!=fixture.packed(case['expected']):raise NumericalIncomplete('Wrong numerical answer')
    if type(proof.get('observed_tokens')) is not int or not 1<proof['observed_tokens']<body['max_tokens']:
        raise NumericalIncomplete('Natural multi-token output required')
    wanted=0 if case['expected_reuse']=='zero' else case['prompt_tokens']-1
    if native.get('reused')!=wanted:raise NumericalIncomplete('Numerical cache state differs')
    for key in ('drafts_offered','drafts_accepted'):
        if type(native.get(key)) is not int or native[key]<=0:raise NumericalIncomplete('DSpark verification path not positively exercised: '+key)
    if native['drafts_accepted']>native['drafts_offered']:raise ValueError('Invalid native draft accounting')
    return {'id':case['id'],'natural_stop':True,'typed_answer_correct':True,'native':native,
            'observed_tokens':proof['observed_tokens'],'numerical_equivalence_pass':False}

def bounded_request(base,body,deadline,folder,*,stream_class,observe,wait_for,clock=time.monotonic):
    if deadline-clock()<10:return {'budget_not_started':True,'request_sent':False}
    stream=stream_class(base,body,timeout=1200).start()
    stop=None
    try:
        while not stream.finished.wait(min(.1,max(0,deadline-clock()))):
            policy=dump_snapshot(folder)
            if policy['status']=='INCOMPLETE_HOLD':stop='NUMERICAL_DUMP_LIMIT';break
            if owned_storage_snapshot(folder)['status']=='INCOMPLETE_HOLD':stop='PRIVATE_CACHE_OR_LOG_LIMIT';break
            if clock()>=deadline:stop='UNCHANGED_SOFT_DEADLINE';break
        if stop:
            stream.cancel();result=stream.result(1)
            def released():
                work=observe(base,'/v1/telemetry')['work']
                return all(type(work.get(k)) is int and work[k]==0 for k in ('active','queued','admission_reserved'))
            wait_for(released,45,'Owned numerical cancellation retained inference ownership')
            result.update(intentional_budget_stop=True,incomplete_reason=stop,retry=False)
            return result
        policy=dump_snapshot(folder)
        result=stream.result(1)
        if policy['status']=='INCOMPLETE_HOLD':result.update(intentional_budget_stop=True,incomplete_reason='NUMERICAL_DUMP_LIMIT',retry=False)
        if owned_storage_snapshot(folder)['status']=='INCOMPLETE_HOLD':result.update(intentional_budget_stop=True,incomplete_reason='PRIVATE_CACHE_OR_LOG_LIMIT',retry=False)
        return result
    except BaseException as exc:
        exc.raw_transport={k:getattr(stream,k,None) for k in ('status','error','events','raw','content','reasoning','finish_reason','done')}
        raise
    finally:
        if stream.thread.is_alive():stream.cancel()

def run_cases(manifest,folder,pid,deadline,*,issue):
    fixture.validate_encoded(manifest['cases'])
    rows=[];complete=False;reason=None
    scores=[{'id':case['id'],'status':'UNRUN','passed':False} for case in manifest['cases']]
    current=None
    try:
        for i,case in enumerate(manifest['cases']):
            current=i;scores[i]['status']='ISSUED_REVIEW_PENDING'
            response,proof=issue(case,folder,pid,deadline)
            rows.append(natural_contract(case,response,proof))
            scores[i].update(status='NATURAL_ANSWER_AND_STATE_PASSED',passed=True)
        current=None
        if dump_snapshot(folder,complete=True)['status']!='COMPLETE_SIZE_ONLY' or owned_storage_snapshot(folder)['status']!='WITHIN_BUDGET':raise NumericalIncomplete('Numerical storage budget incomplete')
        for i,row in enumerate(rows,1):row['dump_size_only']=dump_size(pathlib.Path(folder)/('logits.%d.f32'%i))
        complete=True
    except NumericalIncomplete as exc:
        reason=str(exc)
        if current is not None:scores[current].update(status='WRONG_CAP_PARTIAL_OR_UNRUN_HOLD',passed=False,reason=reason)
    return {'complete':complete,'rows':rows,'incomplete_reason':reason,'native_count':len(rows),
            'case_scores':scores,'unrun_ids':[x['id'] for x in scores if x['status']=='UNRUN'],
            'quality_or_speed_pass':False,'numerical_review_pending':True,'retry':False}

def compare_matched(a,b):
    """No tolerance, row realignment or path matching after a divergence."""
    if len(a)!=4 or len(b)!=4:raise ValueError('Four complete matched state paths required')
    if [x['id'] for x in a]!=list(fixture.IDS) or [x['id'] for x in b]!=list(fixture.IDS):raise ValueError('Exact ordered matched state paths required')
    for x in [*a,*b]:
        d=x['dump']
        if d.get('all_finite') is not True or type(d.get('rows')) is not int or d['rows']<=0 or not x['tokens']:
            raise ValueError('Complete finite dump and emitted token proof required')
    for x,y in zip(a,b):
        if x['id']!=y['id'] or x['tokens']!=y['tokens']:return {'passed':False,'status':'HOLD_TOKEN_PATH_DIFFERS','id':x['id'],'retry':False}
        if x['dump']!=y['dump']:return {'passed':False,'status':'HOLD_NONZERO_LOGIT_OR_ROW_DRIFT','id':x['id'],'retry':False}
        for key in ('prompt_tokens','generated','reused','drafts_offered','drafts_accepted'):
            if x['native'].get(key)!=y['native'].get(key):return {'passed':False,'status':'HOLD_NATIVE_STATE_DIFFERS','id':x['id'],'field':key,'retry':False}
    return {'passed':True,'status':'EXACT_MATCHED_FOUR_STATE_PATHS','speed_pass':False,'general_quality_claim':False}
