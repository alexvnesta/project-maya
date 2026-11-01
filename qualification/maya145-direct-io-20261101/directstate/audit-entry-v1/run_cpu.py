"""First exact both-host CPU proof of the isolated saved-audit entry only."""
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
import sys,unittest
P=Path(__file__).resolve().parent
DRIVER=P.parents[1]/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
NAMES=('bootstrap.py','test_bootstrap.py','run_cpu.py')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def checked(pin):
    f=P/'ROOT_SOURCE_REVIEW.json';r=json.loads(f.read_text())
    if sha(f)!=pin or {n:sha(P/n) for n in NAMES}!=r['source_sha256'] or r['entire_source_tests_read'] is not True or sha(DRIVER)!='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71':raise ValueError('Reviewed exact entry/supervisor source changed')
    return r
def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--review-sha256',required=True);a.add_argument('--child',action='store_true');a.add_argument('--parent',type=int);v=a.parse_args();r=checked(v.review_sha256)
    s=importlib.util.spec_from_file_location('bounded_entry_cpu',DRIVER);d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
    out=P/('CPU-FIRST-'+sys.platform)
    if not v.child:
        out.mkdir();result=d.supervise([sys.executable,'-I','-B',str(Path(__file__).resolve()),'--review-sha256',v.review_sha256,'--child','--parent',str(os.getpid())],out);print(json.dumps(result));return 0 if result['returncode']==0 and result['error'] is None and result['cleanup']==[] else 1
    observed=d.observed();d.bounds(observed,os.getpid(),v.parent);sys.path.insert(0,str(P));import test_bootstrap
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_bootstrap)
    if d.flatten(suite)!=r['test_ids']:raise ValueError('Exact entry test IDs changed')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(v.review_sha256)!=r or d.observed()!=observed:raise ValueError('Source/bounds drift')
    (out/'receipt.json').open('x').write(json.dumps({'passed':result.wasSuccessful(),'controls':result.testsRun,'test_ids':r['test_ids'],'source_sha256':r['source_sha256'],'observed':observed,'CPU_only':True,'native_or_service_actions':False},indent=2)+'\n');return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
