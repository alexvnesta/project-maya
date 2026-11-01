"""FIRST actual two-profile CPU tokenizer encoding, under existing supervisor."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
DRIVER=HERE.parents[1]/'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA='3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
NAMES=('fixtures.py','test_fixtures.py','run_cpu.py')
ENV={'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
     'NUMEXPR_NUM_THREADS':'1','MALLOC_ARENA_MAX':'1','PYTHONDONTWRITEBYTECODE':'1',
     'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def sources():return {n:sha(HERE/n) for n in NAMES}


def module():
    # The source bytes are checked by checked() before this local pure import.
    sys.path.insert(0,str(HERE))
    import fixtures
    if Path(fixtures.__file__)!=HERE/'fixtures.py':raise ValueError('Exact local encoding source')
    return fixtures


def inputs():return dict(module().input_map(),qualified_supervisor=sha(DRIVER))


def checked(pin):
    path=HERE/'ROOT_SOURCE_REVIEW.json'
    if sha(path)!=pin or sha(DRIVER)!=DRIVER_SHA:raise ValueError('Prior entire manual source/supervisor review')
    row=json.loads(path.read_text())
    if row.get('entire_source_tests_driver_manually_read') is not True or row.get('source_map')!=sources():
        raise ValueError('Reviewed source drift before imports')
    if row.get('input_map')!=inputs():raise ValueError('Reviewed actual source/pack/tokenizer/picker input drift')
    return row


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--review-sha256',required=True)
    parser.add_argument('--child',action='store_true');parser.add_argument('--parent',type=int)
    args=parser.parse_args()
    if not sys.flags.isolated or not sys.dont_write_bytecode:raise ValueError('Use Python -I -B')
    review=checked(args.review_sha256)
    spec=importlib.util.spec_from_file_location('essential_fixture_CPU_supervisor',DRIVER)
    d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
    folder=HERE/('CPU-FIRST-'+sys.platform)
    if not args.child:
        folder.mkdir();d.environment=lambda:dict(ENV)
        result=d.supervise([sys.executable,'-I','-B',str(HERE/'run_cpu.py'),'--review-sha256',args.review_sha256,
                            '--child','--parent',str(os.getpid())],folder)
        print(json.dumps(result),flush=True)
        return 0 if result['returncode']==0 and result['error'] is None and not result['cleanup'] else 1
    observed=d.observed();d.bounds(observed,os.getpid(),args.parent)
    # Python -I intentionally excludes user-site. These unchanged previously
    # installed Darwin tokenizer dependencies live here; add the one explicit
    # dependency directory only inside the already bounded CPU child. No site
    # processing, .pth execution, installation or parent environment mutation.
    if sys.platform=='darwin':
        dependencies=Path('/Users/alex/Library/Python/3.14/lib/python/site-packages')
        if not dependencies.is_dir() or dependencies.is_symlink():raise ValueError('Existing Darwin dependency directory')
        sys.path.append(str(dependencies))
    sys.path.insert(0,str(HERE));f=module()
    import test_fixtures
    if Path(test_fixtures.__file__)!=HERE/'test_fixtures.py':raise ValueError('Exact focused control module')
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_fixtures);ids=d.flatten(suite)
    if ids!=review['test_ids']:raise ValueError('Exact ordered focused encoding controls')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(args.review_sha256)!=review or d.observed()!=observed:raise ValueError('Source/input/resource drift')
    manifests={}
    if result.wasSuccessful():
        for arm in ('B0','A0'):
            value=getattr(test_fixtures.EssentialFixtures,arm)
            path=folder/('manifest-'+arm+'.json');f.write_manifest(path,value)
            manifests[arm]={'sha256':sha(path),'canonical_sha256':f.digest(value),
                            'prompt_counts':[c['prompt_tokens'] for c in value['cases']],
                            'prompt_ids_sha256':[c['prompt_ids_sha256'] for c in value['cases']]}
    row={'passed':result.wasSuccessful(),'returncode':0 if result.wasSuccessful() else 1,
         'failures':len(result.failures),'errors':len(result.errors),'controls':result.testsRun,'test_ids':ids,
         'source_map':sources(),'input_map':inputs(),'observed':observed,'supervisor_pid':args.parent,
         'isolated':bool(sys.flags.isolated),'manifests':manifests,
         'scope':'Actual frozen B0/A0 CPU prompt/tokenizer/picker encoding only; no model/GPU/capacity runtime qualification'}
    with (HERE/('CPU-FIRST-'+sys.platform+'.json')).open('x') as stream:json.dump(row,stream,indent=2);stream.write('\n')
    return row['returncode']


if __name__=='__main__':raise SystemExit(main())
