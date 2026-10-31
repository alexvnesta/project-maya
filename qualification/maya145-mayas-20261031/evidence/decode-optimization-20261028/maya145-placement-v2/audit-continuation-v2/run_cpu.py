"""Bounded first six pure receipt-continuation controls, no native or service action."""
import argparse,ast,hashlib,importlib.util,json,os,sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
P=HERE.parent
DRIVER=HERE.parents[1]/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
NAMES=('continuation.py','test_continuation.py','run_cpu.py')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs():
    return {'original/current_audit.py':P/'current_audit.py','original/current_runtime.py':P/'current_runtime.py','original/current_config.py':P/'current_config.py','original/engine_profile.py':P/'engine_profile.py','original/qualification.json':P/'compatibility-qualification.json','original/failed-child.json':P/'DTP2/child.json','original/failed-child.log':P/'DTP2/child.log','PREFIX_ROOT_REVIEW.json':HERE/'PREFIX_ROOT_REVIEW.json','lc_audit.py':P.parent/'maya-s-comparison-v1/long-cold-v1/lc_audit.py'}
def checked(pin):
    path=HERE/'ROOT_SOURCE_REVIEW.json'
    if sha(path)!=pin or sha(DRIVER)!=DRIVER_SHA:raise ValueError('Manual source/supervisor changed')
    r=json.loads(path.read_text())
    if r['manual_source_tests_read'] is not True or r['source_sha256']!={n:sha(HERE/n) for n in NAMES} or r['input_sha256']!={n:sha(p) for n,p in inputs().items()}:raise ValueError('Exact source/input map')
    return r

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review-sha',required=True);ap.add_argument('--child',action='store_true');ap.add_argument('--parent',type=int);a=ap.parse_args();review=checked(a.review_sha)
    spec=importlib.util.spec_from_file_location('bounded_continuation_controls',DRIVER);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d);folder=HERE/('CPU-FIRST-'+sys.platform)
    if not a.child:
        folder.mkdir();result=d.supervise([sys.executable,'-I','-B',str(HERE/'run_cpu.py'),'--review-sha',a.review_sha,'--child','--parent',str(os.getpid())],folder);print(json.dumps(result));return 0 if result['returncode']==0 and result['error'] is None and not result['cleanup'] else 1
    observed=d.observed();d.bounds(observed,os.getpid(),a.parent);sys.path.insert(0,str(HERE));import test_continuation as tests
    suite=unittest.defaultTestLoader.loadTestsFromModule(tests)
    if d.flatten(suite)!=review['test_ids']:raise ValueError('Exact test IDs')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(a.review_sha)!=review or observed!=d.observed():raise ValueError('Post source/CPU drift')
    with (folder/'receipt.json').open('x') as out:json.dump({'passed':result.wasSuccessful(),'controls':result.testsRun,'test_ids':review['test_ids'],'source_sha256':review['source_sha256'],'input_sha256':review['input_sha256'],'observed':observed,'native_or_service_executed':False},out,indent=2)
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':sys.exit(main())
