"""Exact unchanged five-case selection; no fitting, retokenizing or limit changes."""
import hashlib,json
PINS={'prose-fixtures-B.json':'d572147c2f668b7702531ec62a90b5ba9fe8e0b47ac864f05ecca8c73402c601','coding-fixtures-B.json':'513cebf5837290ef69171d2274240afaa8f38cc441373fb52a6c140ce3e3f4dd'}
IDS=['ms-prose-tool','ms-prose-tool-followup','ms-prose-prefill-cancel','ms-prose-prefill-recovery','ms-coding-main']
COUNTS=[372,465,8471,44,140]

def require(ok,msg):
    if not ok:raise ValueError(msg)
def packed(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def manifest(path,root):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<2**20,'Bounded owned fixture')
    source={}
    for n,pin in PINS.items():
        f=root/n;require(f.is_file() and not f.is_symlink() and sha(f)==pin,'Frozen whole source manifest changed');source[n]=json.loads(f.read_text())
    a,b=source['prose-fixtures-B.json'],source['coding-fixtures-B.json']
    for k in ('context','default_output','policy','tokenizer_source_sha256','effective_template','API_sha256'):
        require(packed(a[k])==packed(b[k]),'Shared model/frontend policy differs')
    expected=a['lifecycle_cases']+[next(c for c in b['cases'] if c['id']=='ms-coding-main')]
    m=json.loads(path.read_text());require(m['mode']=='broader' and m['source_manifests']==PINS and packed(m['cases'])==packed(expected) and m['lifecycle_cases']==[],'Only unchanged five-source cases in declared order')
    require(m['context']==1048576 and m['default_output']==262144 and all(packed(m[k])==packed(b[k]) for k in ('policy','tokenizer_source_sha256','effective_template','API_sha256')),'Full unchanged policy/tokenizer/frontend')
    require([c['id'] for c in expected]==IDS and [c['prompt_tokens'] for c in expected]==COUNTS,'Exact full encoded counts')
    for c in expected:
        require(c['request']['max_tokens']==32768 and c['request']['reasoning_effort']==100 and hashlib.sha256(packed(c['request'])).hexdigest()==c['request_sha256'] and hashlib.sha256(packed(c['prompt_ids'])).hexdigest()==c['prompt_ids_sha256'],'Unchanged request/encoding/output/effort')
    require(m['automatic_next_arm'] is False and m['quality_or_performance_pass'] is False,'No automatic advancement')
    return m
