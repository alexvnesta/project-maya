"""First bounded controls for new numerical caller/runtime/auditor, dependencies pinned."""
import argparse,hashlib,json,os,pathlib,resource,subprocess,sys,unittest
P=pathlib.Path(__file__).resolve().parent;E=P.parent.parent
MODULES=('test_imma_model_runtime','test_imma_numeric_controls','test_imma_numerical')
SOURCE=('imma_model_runtime.py','test_imma_model_runtime.py','imma_numeric_controls.py','test_imma_numeric_controls.py',
        'imma_numerical.py','imma_numerical_audit.py','test_imma_numerical.py','qualify_numerical_cpu.py')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(65536),b''):h.update(b)
    return h.hexdigest()
def source_map():return {n:sha(P/n) for n in SOURCE}
def input_map():
    comp=json.loads((P/'fixture-CPU-both-hosts.json').read_text())
    if comp['passed'] is not True or comp['controls_each_host']!=63:raise ValueError('Component proof absent')
    inputs=dict(comp['source_input_sha256'])
    for name,pin in comp['proofs'].items():inputs[str((P/name).relative_to(E))]=pin
    # Reuse the already exact prior input inventory only to locate inherited
    # Python helpers. This admits none of that older GPU mode or its outcomes.
    prior=P.parent/'gpu-qualification.json';remote_prefix='/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/'
    inputs[str(prior.relative_to(E))]=sha(prior)
    old=json.loads(prior.read_text())
    for name,pin in old['files'].items():
        # Router application source is not imported by this CPU/owner helper
        # chain; its physical live unit/release pin belongs to GPU preflight.
        if name.startswith(remote_prefix) and name.endswith('.py') and not name.startswith(remote_prefix+'apps-model-router/'):
            inputs[name[len(remote_prefix):]]=pin
    for n in ('numerical-fixtures.json','numerical-fixture-pin.json','fixture-CPU-both-hosts.json'):
        p=P/n;inputs[str(p.relative_to(E))]=sha(p)
    for n in SOURCE:
        p=P/n;inputs[str(p.relative_to(E))]=sha(p)
    for directory in ('decode-profile-v1','prefill-v2','q8-batch-v1','hosting-1m-output256k-v3-20261027',
                      'prefill-cache-improvements-20261027'):
        for p in sorted((E/directory).glob('*.py')):inputs[str(p.relative_to(E))]=sha(p)
    for name in ('decode-profile-v1/maintenance.py','hosting-1m-output256k-v3-20261027/capacity_observer.py'):
        inputs[name]=sha(E/name)
    for n,pin in inputs.items():
        if sha(E/n)!=pin:raise ValueError('Component/dependency source changed: '+n)
    return inputs
def ids(suite):
    for t in suite:
        if isinstance(t,unittest.TestSuite):yield from ids(t)
        else:yield t.id()
def main():
    p=argparse.ArgumentParser();p.add_argument('--child',action='store_true');p.add_argument('--out',required=True);args=p.parse_args()
    out=pathlib.Path(args.out)
    if sys.platform not in ('darwin','linux') or out!=P/('numerical-CPU-'+sys.platform):raise ValueError('Exact fresh numerical CPU namespace required')
    src=source_map();inputs=input_map();review=json.loads((P/'numerical-CPU-source-review.json').read_text())
    if src!=review['source_sha256'] or inputs!=review['source_input_sha256'] or review['decision']!='FIRST_BOUNDED_NUMERICAL_CPU_ONLY':raise ValueError('Exact numerical source review missing')
    if args.child:
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in MODULES);names=list(ids(suite))
        if names!=review['test_ids']:raise ValueError('Numerical control IDs differ')
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        if source_map()!=src or input_map()!=inputs:raise ValueError('Source/input changed in numerical CPU child')
        (out/'receipt.json').write_text(json.dumps({'passed':result.wasSuccessful(),'controls':result.testsRun,'test_ids':names,
            'source_sha256':src,'source_input_sha256':inputs,'native_execution':False,'GPU_execution':False},indent=2)+'\n')
        raise SystemExit(0 if result.wasSuccessful() else 1)
    if out.exists():raise ValueError('FIRST numerical CPU result already exists')
    if sys.platform=='linux':
        F=E/'autonomous-optimization-12h-20261028/chunk4096-v1/activation-v1';sys.path.insert(0,str(F));import activate_chunk4096 as a
        state=json.loads((E/'STATE.json').read_text())
        if any(state.get(k) for k in ('active_private_phase','active_GPU_phase','active_gpu_experiment','private_window','active_cpu_build','production_restore_in_progress','production_verification_pending','production_temporarily_stopped')):raise ValueError('Another phase; untouched')
        host=a.ChunkProductionHost();host.start_binding=state['decode_optimization_current']['selected_identity']['start_binding']
        if not host.idle():raise ValueError('DEFERRED_BUSY_UNTOUCHED')
        host.guard_binding()
    out.mkdir(exist_ok=False)
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MALLOC_ARENA_MAX='1',PYTHONDONTWRITEBYTECODE='1')
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU,(30,30))
        if sys.platform=='linux':resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20))
        os.nice(15)
    with (out/'child.log').open('w') as log:
        try:
            child=subprocess.run([sys.executable,'-B',str(P/'qualify_numerical_cpu.py'),'--child','--out',str(out)],cwd=P,env=env,preexec_fn=limits,timeout=90,stdout=log,stderr=subprocess.STDOUT);code=child.returncode
        except subprocess.TimeoutExpired:code=None
    (out/'child.json').write_text(json.dumps({'returncode':code,'CPU_s':30,'wall_s':90,'nice':15,'Linux_AS_MiB':512 if sys.platform=='linux' else None,'CUDA_hidden':True})+'\n')
    if code!=0:raise SystemExit('FIRST numerical CPU proof failed; preserved')
    if source_map()!=src or input_map()!=inputs:raise ValueError('Source/input changed across numerical CPU proof')
    print(json.dumps({'passed':True,'controls':json.loads((out/'receipt.json').read_text())['controls'],'native_execution':False,'GPU_execution':False}))
if __name__=='__main__':main()
