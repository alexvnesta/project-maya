import os
import datetime, hashlib, json, math, pathlib, re, time, urllib.request
D=pathlib.Path(os.environ['MAYA_DEPLOY_ROOT'])
def projection_receipt(native_log,cfg):
    args=cfg['args'];direction=args[args.index('--ablate')+1]
    rows=re.findall(r'^abliteration check: device ([01]) rows 2 dim 5120 target blocks 40 drafter untouched max_abs ([0-9.eE+-]+) PASS$',native_log,re.M)
    if len(rows)!=2 or sorted(x[0] for x in rows)!=['0','1']:raise RuntimeError('Both owning GPUs require actual projection checks')
    if any(not math.isfinite(float(x[1])) or float(x[1])>1e-4 for x in rows):raise RuntimeError('Projection numerical check mismatch')
    if 'ds4: abliteration: '+direction+' direction.1, scale 1' not in native_log:raise RuntimeError('Loaded direction identity missing')
    return {'enabled':True,'mode':'runtime residual projection','scale':1,'main_blocks':40,'drafter_unchanged':True,'direction_sha256':hashlib.sha256(pathlib.Path(direction).read_bytes()).hexdigest(),'numeric_checks':{x[0]:float(x[1]) for x in rows},'scope':'Projection math and targeted functionality, not broad quality or universal refusal-removal proof'}
def q8_receipt(native_log):
    rows=re.findall(r"^ds4: CUDA([01]) Q8 batch check: 8 jobs .*: ([0-9]+) int8 and ([0-9]+) scales the per-job launches' bit for bit, every guard intact \(DS4_Q8_CHECK\)$",native_log,re.M)
    if len(rows)!=2 or sorted(x[0] for x in rows)!=['0','1'] or any(x[1:]!=('42784','1337') for x in rows):raise RuntimeError('Actual both-GPU Q8 checks missing')
    return {'passed':True,'devices':[0,1],'int8_each':42784,'scales_each':1337}
def main():
    cfg=json.loads((D/'config.json').read_text());base='http://127.0.0.1:18141';deadline=time.monotonic()+1100
    while True:
        try:
            with urllib.request.urlopen(base+'/health',timeout=5) as f:health=json.load(f)
            with urllib.request.urlopen(base+'/v1/models',timeout=5) as f:models=json.load(f)
            if health.get('loaded') and health.get('max_context')==1048576 and health.get('images') is True and models['data'][0]['id']==cfg['model_name']:break
        except (OSError,ValueError,KeyError,IndexError):pass
        if time.monotonic()>deadline:raise RuntimeError('Hosted model readiness timeout')
        time.sleep(3)
    body={'model':cfg['model_name'],'messages':[{'role':'user','content':'Reply with exactly READY and no other final answer.'}],
          'temperature':0,'seed':1,'reasoning_budget_tokens':0,'max_tokens':256}
    started=time.monotonic()
    with urllib.request.urlopen(urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=180) as f:answer=json.load(f)
    c=answer['choices'][0]
    if c.get('finish_reason')!='stop' or c['message'].get('content','').strip()!='READY':raise RuntimeError('Hosted real READY failed')
    preflight=json.loads((D/'startup-preflight.json').read_text())
    with pathlib.Path(cfg['log']).open('rb') as f:f.seek(preflight['engine_log_offset']);native_log=f.read().decode('utf-8',errors='replace')
    copies=re.findall(r'(\d+) routed experts on the CPU lane .*?: (\d+) copied into RAM',native_log)
    if not copies or copies[-1][0]!=copies[-1][1]:raise RuntimeError('Hosted placement did not copy every CPU expert')
    projection=projection_receipt(native_log,cfg);q8=q8_receipt(native_log)
    if json.loads((D/'config.shared-settings.json').read_text()).get('max_tokens')!=262144:raise RuntimeError('Output default changed')
    receipt={'Q8':q8,'projection':projection,'max_output_tokens':262144,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'health':health,'models':models,'real_ready':answer,'ready_seconds':time.monotonic()-started,'cpu_experts':int(copies[-1][0]),'ram_experts':int(copies[-1][1]),'profile_seed_sha256':preflight['profile_seed_sha256']}
    (D/'startup-ready.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'hosted_ready':True,'model':cfg['model_name'],'context':1048576,'real_READY':True}),flush=True)
if __name__=='__main__':main()
