"""Exact existing bounded CPU supervisor; only child environment/entry injected."""
import argparse,hashlib,importlib.util,json,os,sys,unittest
from pathlib import Path
H=Path(__file__).resolve().parent
D=H.parent/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--review',required=True);p.add_argument('--child',action='store_true');p.add_argument('--parent',type=int);p.add_argument('--execute');p.add_argument('--index',type=int,default=0);args=p.parse_args()
    assert sys.flags.isolated and sys.dont_write_bytecode
    assert sha(D)=='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
    assert sha(H/'SOURCE_REVIEW_FIRST.json')==args.review
    review=json.loads((H/'SOURCE_REVIEW_FIRST.json').read_text())
    assert review['source_sha256']==sha(H/'batch.py') and review['test_sha256']==sha(H/'test_batch.py') and review['driver_sha256']==sha(H/'run_controls.py')
    spec=importlib.util.spec_from_file_location('existing_supervisor',D);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
    if not args.child:
        folder=H/(('BATCH-%03d'%args.index) if args.execute else 'CPU-FIRST-'+sys.platform);folder.mkdir()
        d.environment=lambda:{'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1','PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}
        command=[sys.executable,'-I','-B',str(H/'run_controls.py'),'--review',args.review,'--child','--parent',str(os.getpid())]
        if args.execute:command+=['--execute',args.execute,'--index',str(args.index)]
        result=d.supervise(command,folder);print(json.dumps(result));return int(result['returncode']!=0 or result['error'] is not None or bool(result['cleanup']))
    observed=d.observed();d.bounds(observed,os.getpid(),args.parent);sys.path.insert(0,str(H));import batch as c
    if args.execute:c.execute(args.execute,args.parent,args.index);return 0
    import test_batch
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_batch);ids=d.flatten(suite);assert ids==review['test_ids']
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    proof={'passed':result.wasSuccessful(),'controls':result.testsRun,'ids':ids,'source_sha256':sha(H/'batch.py'),'test_sha256':sha(H/'test_batch.py'),'driver_sha256':sha(H/'run_controls.py'),'observed':observed,'supervisor_pid':args.parent}
    with (H/('CPU-FIRST-'+sys.platform+'.json')).open('x') as f:json.dump(proof,f,indent=2)
    return int(not result.wasSuccessful())
if __name__=='__main__':raise SystemExit(main())
