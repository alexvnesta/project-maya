"""First bounded source-bound public panel encoding, CPU only on each physical host."""
import argparse,ast,hashlib,importlib.util,json,os,sys,unittest
from pathlib import Path
P=Path(__file__).resolve().parent;E=P.parents[2];PRIOR=P.parent/'fixtures-v1'
DRIVER=P.parents[1]/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
NAMES=('panels.py','test_panels.py','run_cpu.py')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def input_paths():
    # Only already-reviewed stdlib metadata mapper is imported, not its test entry.
    f=PRIOR/'run_cpu.py';require(sha(f)==PRIOR_DRIVER_SHA,'Prior exact input mapper')
    s=importlib.util.spec_from_file_location('panels_prior_map',f);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    rows=m.input_paths();rows.update({'qualified-fixtures/'+n:PRIOR/n for n in ('fixtures.py','run_cpu.py','PACKS_FROZEN.json','ROOT_SOURCE_REVIEW_R2.json')})
    helper=E/'decode-optimization-20261028/maya-s-comparison-v1/model-v1/ms_fixtures.py'
    tree=ast.parse(helper.read_text());pins=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('IMAGE_SOURCE','PROSE_SOURCE','CODE_SOURCE') for t in n.targets)];require(len(pins)==3 and all(type(x) is str for x in pins),'Three exact public request source paths');rows.update({n:E/n for n in pins})
    for host in ('darwin','linux'):
        for n in ('receipt.json','child.json','child.log'):rows['qualified-fixtures/'+host+'/'+n]=PRIOR/('CPU-R2-FIRST-'+host)/n
    return rows
PRIOR_DRIVER_SHA='8de71a194b7aa93f72372ae3034c8f927b74ee9bd295a158b18d2273fde8e359'
def require(ok,msg):
    if not ok:raise ValueError(msg)
def checked(pin):
    f=P/'ROOT_SOURCE_REVIEW.json';require(sha(f)==pin,'Exact manual review');r=json.loads(f.read_text())
    require(r['entire_source_tests_read'] is True and {n:sha(P/n) for n in NAMES}==r['source_sha256'] and {n:sha(v) for n,v in input_paths().items()}==r['input_sha256'],'Exact new sources and public dependencies')
    require(sha(DRIVER)=='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71','Existing bounded CPU supervisor');return r

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review-sha256',required=True);ap.add_argument('--child',action='store_true');ap.add_argument('--parent',type=int);a=ap.parse_args();r=checked(a.review_sha256)
    s=importlib.util.spec_from_file_location('bounded_panel_cpu',DRIVER);d=importlib.util.module_from_spec(s);s.loader.exec_module(d);out=P/('CPU-FIRST-'+sys.platform)
    if not a.child:
        out.mkdir();v=d.supervise([sys.executable,'-B',str(P/'run_cpu.py'),'--review-sha256',a.review_sha256,'--child','--parent',str(os.getpid())],out);print(json.dumps(v));return 0 if v['returncode']==0 and v['error'] is None and not v['cleanup'] else 1
    observed=d.observed();d.bounds(observed,os.getpid(),a.parent);sys.path.insert(0,str(P));import test_panels
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_panels);require(d.flatten(suite)==r['test_ids'],'Exact discovered controls');v=unittest.TextTestRunner(verbosity=2).run(suite)
    require(checked(a.review_sha256)==r and d.observed()==observed,'Source/resource drift');hashes={}
    if v.wasSuccessful():
        require(len(test_panels.MANIFESTS)==8,'All exact candidate panels')
        for name,m in test_panels.MANIFESTS.items():
            f=out/('manifest-'+name+'.json');f.open('x').write(json.dumps(m,indent=2)+'\n');hashes[name]=sha(f)
    receipt={'passed':v.wasSuccessful(),'controls':v.testsRun,'source_sha256':r['source_sha256'],'input_sha256':r['input_sha256'],'test_ids':r['test_ids'],'manifest_sha256':hashes,'observed':observed,'CPU_only':True,'native_or_service_actions':False,'cold_bounds_model_quality_or_speed_proof':False,'frontend_dependencies':{n:{'path':sys.modules[n].__file__,'sha256':sha(sys.modules[n].__file__)} for n in ('jinja2','markupsafe')}}
    (out/'receipt.json').open('x').write(json.dumps(receipt,indent=2)+'\n');return 0 if v.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
