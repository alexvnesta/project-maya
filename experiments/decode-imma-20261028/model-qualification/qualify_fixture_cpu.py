"""First component proof and one captured CPU encoding; no native/model execution."""
import argparse,datetime,hashlib,json,os,pathlib,resource,subprocess,sys,unittest
P=pathlib.Path(__file__).resolve().parent
E=P.parent.parent
MODULES=('test_imma_config','test_imma_fixtures','test_imma_storage')
SOURCE=('imma_config.py','test_imma_config.py','imma_fixtures.py','test_imma_fixtures.py',
        'imma_storage.py','test_imma_storage.py','qualify_fixture_cpu.py')
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def inputs():
    paths=[P/n for n in SOURCE]+[P/n for n in ('base-config.json','pack-files.json','pack-geometry.ds4.txt')]
    V=E/'native-vision-v2'
    paths += [V/'test_native_vision.py', E/'prefill-cache-improvements-20261027/numerical-fixtures/manifest.json']
    paths += sorted((V/'runtime').rglob('*.py'))
    paths += [V/'tokenizer'/n for n in ('vocab.json','merges.txt','tokenizer.json','token_type.json','chat_template.jinja')]
    if any(p.is_symlink() or not p.is_file() for p in paths):raise ValueError('Regular pinned component input required')
    return {str(p.relative_to(E)):sha(p) for p in paths}
def ids(suite):
    for t in suite:
        if isinstance(t,unittest.TestSuite):yield from ids(t)
        else:yield t.id()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--child',action='store_true');ap.add_argument('--out',required=True)
    ap.add_argument('--delta',action='store_true')
    args=ap.parse_args();out=pathlib.Path(args.out)
    expected=P/('fixture-CPU-darwin-delta2' if args.delta else 'fixture-CPU-linux')
    if sys.platform not in ('darwin','linux') or out!=expected or (args.delta!=(sys.platform=='darwin')):raise ValueError('Exact component output required')
    before=inputs();review=json.loads((P/'fixture-CPU-r2-source-review.json').read_text())
    if before!=review['source_input_sha256'] or review['decision']!='DARWIN_DELTA2_LINUX_FIRST63_CPU_ONLY':raise ValueError('Exact review missing')
    def original_proof():
        if args.delta:
            for name,pin in review['original_darwin_files'].items():
                if sha(P/'fixture-CPU-darwin'/name)!=pin:raise ValueError('Original Darwin evidence changed')
    original_proof()
    if args.child:
        selectors=review['delta_test_ids'] if args.delta else MODULES
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in selectors)
        names=list(ids(suite))
        wanted=review['delta_test_ids'] if args.delta else review['test_ids']
        if names!=wanted or len(names)!=(2 if args.delta else 63):raise ValueError('Exact component controls required')
        import imma_fixtures as fixture
        original=fixture.build_manifest;captured=[]
        def record():
            value=original();captured.append(value);return value
        # The single real-tokenizer test calls the original exactly once. Its
        # validated result is retained for matching hosts instead of re-encoding.
        fixture.build_manifest=record
        try:result=unittest.TextTestRunner(verbosity=2).run(suite)
        finally:fixture.build_manifest=original
        if len(captured)!=(0 if args.delta else 1):raise ValueError('Exactly one original encoding, no delta re-encoding')
        manifest=json.loads((P/'fixture-CPU-darwin/manifest.json').read_text()) if args.delta else captured[0]
        manifest_bytes=(json.dumps(manifest,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
        (out/'manifest.json').write_bytes(manifest_bytes)
        if inputs()!=before:raise ValueError('Inputs changed during controls')
        original_proof()
        proof={'passed':result.wasSuccessful(),'controls':result.testsRun,'test_ids':names,
               'source_input_sha256':before,'actual_CPU_encodings':0 if args.delta else 1,
               'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
               'GPU_execution':False,'native_execution':False,'model_execution':False}
        (out/'receipt.json').write_text(json.dumps(proof,indent=2)+'\n')
        raise SystemExit(0 if result.wasSuccessful() else 1)
    if out.exists():raise ValueError('FIRST component output already exists')
    if sys.platform=='linux':
        F=E/'autonomous-optimization-12h-20261028/chunk4096-v1/activation-v1'
        sys.path.insert(0,str(F));import activate_chunk4096 as a
        state=json.loads((E/'STATE.json').read_text())
        if any(state.get(k) for k in ('active_private_phase','active_GPU_phase','active_gpu_experiment','active_cpu_build',
                                     'private_window','production_restore_in_progress','production_verification_pending')):
            raise ValueError('Another phase/build; untouched')
        selected=state.get('decode_optimization_current',{}).get('selected_identity') or state['chunk4096_activation']['selected_identity']
        host=a.ChunkProductionHost();host.start_binding=selected['start_binding']
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
            r=subprocess.run([sys.executable,'-B',str(P/'qualify_fixture_cpu.py'),'--child','--out',str(out),*(['--delta'] if args.delta else [])],
                cwd=P,env=env,preexec_fn=limits,timeout=90,stdout=log,stderr=subprocess.STDOUT);code=r.returncode
        except subprocess.TimeoutExpired:code=None
    (out/'child.json').write_text(json.dumps({'returncode':code,'CPU_s':30,'wall_s':90,'nice':15,
        'Linux_AS_MiB':512 if sys.platform=='linux' else None,'CUDA_hidden':True})+'\n')
    if code!=0:raise SystemExit('FIRST fixture CPU proof failed; preserve output')
    if inputs()!=before:raise ValueError('Input changed across CPU proof')
    original_proof()
    print(json.dumps({'passed':True,'controls':2 if args.delta else 63,'manifest_sha256':sha(out/'manifest.json')}))
if __name__=='__main__':main()
