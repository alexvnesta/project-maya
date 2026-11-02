import argparse,hashlib,importlib.util,json,os,sys,unittest
from pathlib import Path
H=Path(__file__).resolve().parent
D=H.parents[1]/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--review',required=True);parser.add_argument('--child',action='store_true');parser.add_argument('--parent',type=int);args=parser.parse_args()
    assert sys.flags.isolated and sys.dont_write_bytecode and sha(H/'REVIEW.json')==args.review
    r=json.loads((H/'REVIEW.json').read_text());assert sha(H/'run.py')==r['driver']
    def sources():return {n:sha(H/'repo'/n) for n in r['sources']}
    assert sources()==r['sources'] and sha(D)=='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
    s=importlib.util.spec_from_file_location('bounded',D);d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
    if not args.child:
        folder=H/('CPU-FIRST-'+sys.platform);folder.mkdir()
        d.environment=lambda:{'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1','PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}
        result=d.supervise([sys.executable,'-I','-B',str(H/'run.py'),'--review',args.review,'--child','--parent',str(os.getpid())],folder)
        print(json.dumps(result));return int(result['returncode']!=0 or result['error'] is not None or bool(result['cleanup']))
    ob=d.observed();d.bounds(ob,os.getpid(),args.parent);sys.path.insert(0,str(H/'repo/tests'));import test_hosted_capacity_profile as tests
    suite=unittest.defaultTestLoader.loadTestsFromModule(tests);ids=d.flatten(suite);assert ids==r['ids']
    result=unittest.TextTestRunner(verbosity=2).run(suite);assert sources()==r['sources']
    with (H/('CPU-FIRST-'+sys.platform+'.json')).open('x') as f:json.dump({'passed':result.wasSuccessful(),'controls':result.testsRun,'ids':ids,'sources':sources(),'observed':ob,'supervisor_pid':args.parent},f,indent=2)
    return int(not result.wasSuccessful())
if __name__=='__main__':raise SystemExit(main())
