"""FIRST bounded real-temp-file housekeeping controls; no real payload operation."""
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
import sys,unittest
HERE=Path(__file__).resolve().parent
NAMES=('remove_exact_payloads_admitted.py','test_payload_removal.py','run_cleanup_cpu.py')
DRIVER=HERE.parent/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
INPUTS={'CLEANUP_PLAN.json':HERE/'CLEANUP_PLAN.json','DEPENDENCY_AUDIT_FIRST.json':HERE/'DEPENDENCY_AUDIT_FIRST.json','SELECTED_PRODUCTION_LOCK_DRAFT.json':HERE/'SELECTED_PRODUCTION_LOCK_DRAFT.json','qualified-unchanged-current-runtime':HERE.parent/'maya145-formal-prefill-v1/current_runtime.py','qualified-full-native-owner-source-map':HERE.parent/'maya145-formal-prefill-v1/task-qualification.json','actual-single-comparison-result':HERE.parent/'maya145-formal-prefill-v1/FORMAL_PREFILL_FIRST_PAIR_RESULT.json'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def checked(pin):
    review=HERE/'CLEANUP_SOURCE_ROOT_REVIEW.json'
    if sha(review)!=pin or sha(DRIVER)!=DRIVER_SHA:raise ValueError('Exact source review/supervisor')
    r=json.loads(review.read_text())
    if r['entire_source_and_tests_read'] is not True or r['source_sha256']!={n:sha(HERE/n) for n in NAMES} or r['input_sha256']!={n:sha(p) for n,p in INPUTS.items()}:raise ValueError('Exact source/input changed')
    return r

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--review-sha256',required=True);parser.add_argument('--child',action='store_true');parser.add_argument('--parent',type=int);args=parser.parse_args();review=checked(args.review_sha256)
    spec=importlib.util.spec_from_file_location('existing_bounded_supervisor',DRIVER);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
    folder=HERE/('CPU-CLEANUP-FIRST-'+sys.platform)
    if not args.child:
        folder.mkdir();result=d.supervise([sys.executable,'-I','-B',str(Path(__file__).resolve()),'--review-sha256',args.review_sha256,'--child','--parent',str(os.getpid())],folder);print(json.dumps(result));return 0 if result['returncode']==0 and result['error'] is None and result['cleanup']==[] else 1
    observed=d.observed();d.bounds(observed,os.getpid(),args.parent);sys.path.insert(0,str(HERE));import test_payload_removal as tests;import remove_exact_payloads_admitted as operation
    if Path(tests.__file__).resolve()!=HERE/'test_payload_removal.py' or Path(operation.__file__).resolve()!=HERE/'remove_exact_payloads_admitted.py':raise ValueError('Actual source origins')
    suite=unittest.defaultTestLoader.loadTestsFromModule(tests);ids=d.flatten(suite)
    if ids!=review['test_ids']:raise ValueError('Exact ordered controls')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(args.review_sha256)!=review or d.observed()!=observed:raise ValueError('Source/input/limits drift')
    (folder/'receipt.json').open('x').write(json.dumps({'passed':result.wasSuccessful(),'controls':result.testsRun,'test_ids':ids,'source_sha256':review['source_sha256'],'input_sha256':review['input_sha256'],'observed':observed,'real_payload_deleted':False,'native_or_service_executed':False},indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
