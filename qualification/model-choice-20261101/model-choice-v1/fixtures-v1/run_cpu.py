"""FIRST exact CPU encoding qualification of two completed candidate packs."""
import argparse,ast,hashlib,importlib.util,json,os
from pathlib import Path
import sys,unittest
P=Path(__file__).resolve().parent
E=P.parents[2]
DRIVER=P.parents[1]/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
NAMES=('fixtures.py','test_fixtures.py','run_cpu.py','PACKS_FROZEN.json')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def input_paths():
    helper=E/'decode-optimization-20261028/maya-s-comparison-v1/model-v1/ms_fixtures.py'
    tree=ast.parse(helper.read_text());pins=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SUPPORT_PINS' for t in n.targets))
    rows={'original/ms_fixtures.py':helper,'original/prose-fixtures-B.json':helper.parent/'prose-fixtures-B.json'}
    rows.update({n:E/n for n in pins})
    for candidate,r in json.loads((P/'PACKS_FROZEN.json').read_text()).items():
        root=E/r['pack_relative_to_E']
        for n in r['metadata_sha256']:rows[candidate+'/'+n]=root/n
        for n in r['tokenizer_sha256']:rows[candidate+'/tokenizer/'+n]=root/'tokenizer'/n
    return rows
def checked(pin):
    f=P/'ROOT_SOURCE_REVIEW_R2.json';r=json.loads(f.read_text())
    if sha(f)!=pin or {n:sha(P/n) for n in NAMES}!=r['source_sha256'] or {n:sha(v) for n,v in input_paths().items()}!=r['input_sha256'] or r['entire_source_tests_read'] is not True or sha(DRIVER)!='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71':raise ValueError('Exact reviewed fixture source/input/supervisor changed')
    return r
def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--review-sha256',required=True);a.add_argument('--child',action='store_true');a.add_argument('--parent',type=int);v=a.parse_args();r=checked(v.review_sha256)
    s=importlib.util.spec_from_file_location('bounded_fixture_cpu',DRIVER);d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
    out=P/('CPU-R2-FIRST-'+sys.platform)
    if not v.child:
        out.mkdir();result=d.supervise([sys.executable,'-B',str(Path(__file__).resolve()),'--review-sha256',v.review_sha256,'--child','--parent',str(os.getpid())],out);print(json.dumps(result));return 0 if result['returncode']==0 and result['error'] is None and result['cleanup']==[] else 1
    observed=d.observed();d.bounds(observed,os.getpid(),v.parent);sys.path.insert(0,str(P));import test_fixtures
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_fixtures)
    if d.flatten(suite)!=r['test_ids']:raise ValueError('Exact fixture test IDs changed')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(v.review_sha256)!=r or d.observed()!=observed:raise ValueError('Source/bounds drift')
    hashes={}
    if result.wasSuccessful():
        if set(test_fixtures.MANIFESTS)!={'HGU','UNSLOTH'}:raise ValueError('Both actual source encodings required')
        for candidate,manifest in test_fixtures.MANIFESTS.items():
            f=out/('manifest-'+candidate+'.json');f.open('x').write(json.dumps(manifest,indent=2)+'\n');hashes[candidate]=sha(f)
    (out/'receipt.json').open('x').write(json.dumps({'passed':result.wasSuccessful(),'controls':result.testsRun,'test_ids':r['test_ids'],'source_sha256':r['source_sha256'],'input_sha256':r['input_sha256'],'manifest_sha256':hashes,'observed':observed,'python_isolated':bool(sys.flags.isolated),'frontend_dependencies':{name:{'path':sys.modules[name].__file__,'sha256':sha(sys.modules[name].__file__)} for name in ('jinja2','markupsafe')},'CPU_only':True,'native_or_service_actions':False},indent=2)+'\n');return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
