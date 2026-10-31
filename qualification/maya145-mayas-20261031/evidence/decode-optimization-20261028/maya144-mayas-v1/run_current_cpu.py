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
NAMES = ('engine_profile.py', 'current_config.py', 'current_runtime.py', 'current_controls.py', 'current_compat.py', 'test_current_mode.py', 'run_current_cpu.py')
DRIVER = HERE.parent / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_paths(root):
    e=HERE.parents[1];q=HERE.parent/'maya-s-comparison-v1'
    rows={'profile-base-config.json':HERE/'profile-base-config.json'}
    for name in ('src/ds4/ds4_main.cpp','src/ds4/ds4_model.cu','src/ds4/ds4_gguf.cu'):
        rows[name]=root/name
    for relative in ('performance-v2/pv_runtime.py','performance-v2/pv_config.py','performance-v2/pv_controls.py',
        'model-v1/ms_config.py','model-v1/ms_runtime.py','model-v1/ms_fixtures.py','model-v1/ms_controls.py',
        'model-v1/ms_audit.py','model-v1/ms_quality_audit.py','model-v1/ms_compat_audit.py','model-v1/prose-fixtures-B.json'):
        rows['reuse/'+relative]=q/relative
    return rows


def checked(pin, root):
    path = HERE / 'ROOT_CURRENT_R2_SOURCE_REVIEW.json'
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
    folder = HERE / ('CPU-CURRENT-R2-FIRST-' + sys.platform)
    if not a.child:
        folder.mkdir()
        result = d.supervise([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
            '--review-sha256', a.review_sha256, '--native-source-root', str(a.native_source_root),
            '--child', '--parent', str(os.getpid())], folder)
        print(json.dumps(result), flush=True)
        return 0 if result['returncode'] == 0 and result['error'] is None and not result['cleanup'] else 1
    observed = d.observed(); d.bounds(observed, os.getpid(), a.parent)
    sys.path.insert(0, str(HERE))
    import test_current_mode as tests
    import current_compat as profile
    if Path(tests.__file__).resolve() != HERE / 'test_current_mode.py' or Path(profile.__file__).resolve() != HERE / 'current_compat.py':
        raise ValueError('Actual profile/test import origin changed')
    suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
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
