"""First bounded proof of the new engine current-native compatibility owner; no native use."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
NAMES = ('current_audit.py', 'engine_profile.py', 'current_config.py', 'current_runtime.py', 'current_controls.py', 'current_compat.py', 'short_tasks.py', 'SHORT_SOURCES_FROZEN.json', 'numeric_lineage.py', 'NUMERICAL_LINEAGE_FROZEN.json', 'current_skip.py', 'test_current_skip.py', 'selected92_observer.py', 'test_selected92_observer.py', 'baseline_lineage.py', 'test_baseline_lineage.py', 'BASELINE_LINEAGE_FROZEN.json', 'FORMAL_PREFILL_PLAN_FROZEN.json', 'test_task_mode.py', 'test_core_lifecycle.py', 'test_short_tasks.py', 'test_numeric_lineage.py', 'baseline_identity.py', 'direct_io.py', 'candidate_assets.py', 'test_candidate_assets.py', 'test_direct_io.py', 'test_baseline_identity.py', 'run_current_cpu.py')
DRIVER = HERE.parent / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_paths(root):
    path=HERE.parent/'maya145-modelchoice-v1/run_current_cpu.py'
    if sha(path)!='a8662c38ed41e5e5f5a9bddc3cd1be7579807c03bdb8fec1a5587fa2013f9030':raise ValueError('Reviewed prior stdlib metadata mapper changed')
    spec=importlib.util.spec_from_file_location('task_prior_metadata_map',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    rows=m.input_paths(root);rows['prior-exact-metadata-mapper']=path
    rows['profile-base-config.json']=HERE/'profile-base-config.json';rows['CURRENT_BASELINE_RECOVERY_SNAPSHOT.json']=HERE/'CURRENT_BASELINE_RECOVERY_SNAPSHOT.json'
    for n in ('engine.log','native-ready.json','startup-health.json','startup-models.json'):
        rows['saved-startup/'+n]=HERE/'recorded-startup-RTP2-failed'/n;rows['saved-TP1/'+n]=HERE/'recorded-startup-MSTP1'/n
    data=HERE.parent/'model-choice-v1/panels-v1'
    for n in ('panels.py','test_panels.py','run_cpu.py','ROOT_SOURCE_REVIEW.json','FIRST_BOTH_HOST_RESULTS.json'):rows['actual-panels/'+n]=data/n
    for host in ('darwin','linux'):
        folder=data/('CPU-FIRST-'+host)
        for n in ('receipt.json','child.json','child.log'):rows['actual-panels/'+host+'/'+n]=folder/n
        receipt=json.loads((folder/'receipt.json').read_text())
        for name in receipt['manifest_sha256']:rows['actual-panels/'+host+'/manifest-'+name]=folder/('manifest-'+name+'.json')
    e=HERE.parents[1]
    for doc in json.loads((HERE/'SHORT_SOURCES_FROZEN.json').read_text()).values():rows['short-source/'+doc['source_relative_to_E']]=e/doc['source_relative_to_E']
    for row in json.loads((HERE/'NUMERICAL_LINEAGE_FROZEN.json').read_text()).values():
        for entry in row['files'].values():rows['closed-numerical/'+entry['relative_to_E']]=e/entry['relative_to_E']
    pack=HERE.parent/'maya-s-comparison-v1/pack-v1/pack-FIRST'
    for n in ('ds4.txt','tensors.txt','engram.bin'):rows['original-MayaS/'+n]=pack/n
    for n in ('vocab.json','merges.txt','token_type.json','tokenizer.json','chat_template.jinja'):rows['original-MayaS/tokenizer/'+n]=pack/'tokenizer'/n
    for path in (HERE/'saved-QTP2').iterdir():
        if path.is_file():rows['actual-TP2-skip-source/'+path.name]=path
    for name in ('vocab.json','merges.txt','token_type.json','tokenizer.json','chat_template.jinja'):rows['actual-selected92-tokenizer/'+name]=e/'native-vision-v2/tokenizer'/name
    for relative in ('native-vision-v2/runtime/serve/dsml.py','native-vision-v2/runtime/serve/fixtures/deepseek41/chat_template.jinja'):rows['actual-selected92-picker/'+relative]=e/relative
    for name in ('ds4_main.cpp','ds4_model.cu'):rows['selected92-source/'+name]=HERE/'selected92-source'/name
    for path in (HERE/'recorded-native92-stat').iterdir():
        if path.is_file():rows['actual-native92-STAT/'+path.name]=path
    for name in ('engine.log','native-ready.json','startup-health.json','startup-models.json','startup-audit.json'):rows['actual-selected92-startup/'+name]=HERE/'recorded-startup-SELECTED92'/name
    for row in json.loads((HERE/'BASELINE_LINEAGE_FROZEN.json').read_text()).values():rows['selected92-lineage/'+row['relative_to_E']]=e/row['relative_to_E']
    for relative in ('hosting-1m-output256k-v3-20261027/capacity_observer.py','q8-batch-v1/q8_configuration.py','fork-bundle-v1/bundle_mode.py','prefill-cache-improvements-20261027/performance-v1/performance_mode.py'):rows['actual-pure-startup/'+relative]=e/relative
    return rows


def checked(pin, root):
    path = HERE / 'ROOT_CURRENT_SOURCE_REVIEW.json'
    if sha(path) != pin or sha(DRIVER) != DRIVER_SHA:
        raise ValueError('Manual review or supervisor changed')
    review = json.loads(path.read_text())
    rows = {n: sha(HERE / n) for n in NAMES}
    inputs = {n: sha(p) for n,p in input_paths(root).items()}
    if rows != review['source_sha256'] or inputs != review['input_sha256'] or review['entire_new_source_tests_read'] is not True:
        raise ValueError('Reviewed source/config/native schema changed')
    return review


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--review-sha256', required=True)
    ap.add_argument('--native-source-root', type=Path, required=True)
    ap.add_argument('--child', action='store_true')
    ap.add_argument('--parent', type=int)
    a = ap.parse_args()
    if not a.native_source_root.is_absolute() or a.native_source_root.resolve() != a.native_source_root:
        raise ValueError('Exact source root required')
    review = checked(a.review_sha256, a.native_source_root)
    spec = importlib.util.spec_from_file_location('bounded_profile_supervisor', DRIVER)
    d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
    folder = HERE / ('CPU-TASK-R2-FIRST-' + sys.platform)
    if not a.child:
        folder.mkdir()
        result = d.supervise([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
            '--review-sha256', a.review_sha256, '--native-source-root', str(a.native_source_root),
            '--child', '--parent', str(os.getpid())], folder)
        print(json.dumps(result), flush=True)
        return 0 if result['returncode'] == 0 and result['error'] is None and not result['cleanup'] else 1
    observed = d.observed(); d.bounds(observed, os.getpid(), a.parent)
    sys.path.insert(0, str(HERE))
    import test_task_mode as tests
    import current_compat as profile
    if Path(tests.__file__).resolve()!=HERE/'test_task_mode.py' or Path(profile.__file__).resolve()!=HERE/'current_compat.py':raise ValueError('Actual new task/test import origin')
    import test_core_lifecycle,test_short_tasks,test_numeric_lineage,test_direct_io,test_baseline_identity,test_candidate_assets,test_selected92_observer,test_baseline_lineage,test_current_skip
    test_direct_io.NATIVE_SOURCE_ROOT=a.native_source_root
    modules=[tests,test_core_lifecycle,test_short_tasks,test_numeric_lineage,test_direct_io,test_baseline_identity,test_candidate_assets,test_selected92_observer,test_baseline_lineage,test_current_skip]
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(m) for m in modules])
    ids = d.flatten(suite)
    if ids != review['test_ids']:
        raise ValueError('Actual ordered controls changed')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(a.review_sha256, a.native_source_root) != review or d.observed() != observed:
        raise ValueError('Source or resource drift')
    receipt = {'passed': result.wasSuccessful(), 'controls': result.testsRun, 'test_ids': ids,
        'source_sha256': review['source_sha256'], 'input_sha256': review['input_sha256'], 'observed': observed,
        'native_executed': False, 'device_executed': False, 'model_quality_or_speed_proof': False}
    (folder / 'receipt.json').open('x').write(json.dumps(receipt, indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
