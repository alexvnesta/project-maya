"""Fail-closed admission and fresh profile seed for the hosted DeepSeek owner."""
import os
import datetime, fcntl, hashlib, json, pathlib, shutil, socket, subprocess, sys
ROOT=pathlib.Path(os.environ['MAYA_QUALIFICATION_ROOT'])
DEPLOY=pathlib.Path(os.environ['MAYA_DEPLOY_ROOT'])
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def competing_model_units():
    # The CPU-only router is the model lifecycle owner, not a competing GPU backend.
    return [(True,'glm53-b2.service'),(True,'glm53-b2-watchdog.timer'),(False,'qwen-flash-vllm.service')]
def validate_config(config):
    if config['host']!='127.0.0.1' or config['port']!=18141:raise RuntimeError('Unexpected hosting bind')
    args=config['args']
    for flag,value in [('--prefill-chunk','4096'),('--max-context','1048576'),('--dspark','on'),('--vision','on'),('--tp','1'),('--ablate',str(DEPLOY/'runtime-direction-L22.gguf')),('--ablate-scale','1')]:
        if args.count(flag)!=1 or args.index(flag)+1>=len(args) or args[args.index(flag)+1]!=value:raise RuntimeError('Serving contract mismatch')
    if config.get('hosted_default_effort')!=100:raise RuntimeError('Default maximum effort changed')
    if any(config.get(k)!=v for k,v in [('answer_room',False),('reasoning_budget_tokens',0),('repeat_stop_tokens',0),('reasoning_loop_recovery',False),('fit_max_tokens',False)]):raise RuntimeError('Quality policy changed')
    if config['exe']!=str(DEPLOY/'bin/maya-ds4'):raise RuntimeError('Unexpected native executable')
    env=config.get('env',{})
    if env.get('STRATA_DS4_Q8_BATCH')!='1' or env.get('DS4_Q8_CHECK')!='1':raise RuntimeError('Q8/check disabled')
    if env.get('DS4_YOCO')!='1' or env.get('STRATA_DS4_PROMPT_SKIP')!='1':raise RuntimeError('Qualified mode1 prompt skip required')
    if any(k in env for k in ['DS4_CHUNK','DS4_CHUNK_MIN','DS4_CACHE_REUSE_MIB','DS4_COPY_PIN','DS4_FLOW','DS4_Q5K_SHARED_SUMS','DS4_SERVE_DUMP','DS4_SPLIT','DS4_YOCO_KEEP','STRATA_DS4_DECODE_TRIM','STRATA_DS4_DRAFT_VRAM','STRATA_DS4_HC_FUSE','STRATA_DS4_LOAD_DROP_CACHE','STRATA_DS4_ROUTE_FUSE']):raise RuntimeError('Unqualified mixed factors')
    if env.get('STRATA_DS4_SLOT_DIR')!=str(DEPLOY/('state/conversation-cache-'+os.environ['MAYA_DIRECTION_SHA256']+'-s1-1m-yoco1-chunk4096')):raise RuntimeError('Projection requires isolated KV cache namespace')
def main():
    manifest=json.loads((DEPLOY/'release.json').read_text())
    config=json.loads((DEPLOY/'config.json').read_text())
    for name,expected in manifest['files'].items():
        if sha(name)!=expected:raise RuntimeError('Release identity changed: '+name)
    validate_config(config)
    args=config['args']
    if json.loads((DEPLOY/'config.shared-settings.json').read_text()).get('max_tokens')!=262144:raise RuntimeError('Output default changed')
    lock=(ROOT/'experiment.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    latest=max((ROOT/'windows').glob('*.json'),key=lambda p:p.stat().st_mtime)
    state=json.loads(latest.read_text())
    kernel=json.loads(latest.with_suffix('.telemetry.jsonl').read_text().splitlines()[-1])
    if state.get('test_returncode')!=0 or not state.get('maintenance_resume_allowed') or kernel.get('kernel_capture_returncode')!=0 or kernel.get('kernel_fault_lines')!=[]:
        raise RuntimeError('Latest maintenance window requires diagnosis: '+str(latest))
    for user,name in competing_model_units():
        p=subprocess.run(['systemctl',*(['--user'] if user else []),'is-active','--quiet',name])
        if p.returncode==0:raise RuntimeError('Competing model/router active: '+name)
    if subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip():raise RuntimeError('GPU owner already exists')
    used=[int(x) for x in subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).splitlines()]
    if len(used)!=2 or max(used)>=2000:raise RuntimeError('Unexpected GPU allocation')
    if shutil.disk_usage(ROOT).free<120*2**30:raise RuntimeError('Root free below campaign floor')
    with socket.socket() as s:s.bind(('127.0.0.1',18141))
    memory={x.split(':')[0]:int(x.split()[1]) for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')}
    if memory['MemAvailable']<60*2**20:raise RuntimeError('Insufficient RAM for qualified full-copy placement')
    profile=pathlib.Path(args[args.index('--expert-profile')+1]);seed=DEPLOY/'profile-seed.bin'
    if profile!=DEPLOY/'state/expert-profile.bin' or profile.is_symlink():raise RuntimeError('Unexpected mutable profile destination')
    if sha(seed)!=manifest['profile_seed_sha256']:raise RuntimeError('Frozen placement seed changed')
    profile.parent.mkdir(exist_ok=True);(DEPLOY/'receipts').mkdir(exist_ok=True)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if profile.exists():shutil.copyfile(profile,DEPLOY/'receipts'/('profile-output-'+stamp+'.bin'))
    shutil.copyfile(seed,profile)
    log=pathlib.Path(config['log'])
    (DEPLOY/'startup-preflight.json').write_text(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'engine_log_offset':log.stat().st_size if log.exists() else 0,'profile_seed_sha256':sha(seed),'last_clean_window':str(latest)},indent=2)+'\n')
    print(json.dumps({'preflight':'passed','model':config['model_name'],'release':manifest['id'],'gpu_owner':'free','root_free_gib':shutil.disk_usage(ROOT).free/2**30}),flush=True)
if __name__=='__main__':main()
