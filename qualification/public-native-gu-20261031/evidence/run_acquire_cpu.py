"""First bounded proof of native-source acquisition; fake HTTP, no serving/model action."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
NAMES = ('acquire_native.py','test_acquire_native.py','run_acquire_cpu.py')
DRIVER = HERE.parent / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_paths(root):
    dc=HERE.parent;t=dc/'maya-s-comparison-v1/acquisition-authorized-v2'
    return {'manifest':HERE/'NATIVE_GU_SOURCE_MANIFEST.json','transport':t/'acquire.py',
            'transport-qualification':t/'acquisition-qualification.json',
            'other-manifest':dc/'unsloth-v31-iq2xxs-download-v1/ASSET_MANIFEST.json',
            'selected-runtime':dc/'iq2s-persistent-v1/model-v1/iq2s_model_runtime.py',
            'selected-config':dc/'iq2s-persistent-v1/model-v1/iq2s_config.py',
            'CPU-supervisor':DRIVER}


def checked(pin, root):
    path = HERE / 'ACQUIRE_SOURCE_ROOT_REVIEW.json'
    if sha(path) != pin or sha(DRIVER) != DRIVER_SHA:
        raise ValueError('Manual review or supervisor changed')
    review = json.loads(path.read_text())
    rows = {n: sha(HERE / n) for n in NAMES}
    inputs = {n: sha(p) for n,p in input_paths(root).items()}
    if rows != review['source_sha256'] or inputs != review['input_sha256'] or review['root_source_read'] is not True or review['sol_source_read'] is not True:
        raise ValueError('Reviewed source/config/native schema changed')
    return review


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--review-sha256', required=True)
    ap.add_argument('--input-root', type=Path, required=True)
    ap.add_argument('--child', action='store_true')
    ap.add_argument('--parent', type=int)
    a = ap.parse_args()
    if not a.input_root.is_absolute() or a.input_root.resolve() != a.input_root:
        raise ValueError('Exact source root required')
    review = checked(a.review_sha256, a.input_root)
    spec = importlib.util.spec_from_file_location('bounded_profile_supervisor', DRIVER)
    d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
    folder = HERE / ('ACQUIRE-CPU-FIRST-' + sys.platform)
    if not a.child:
        folder.mkdir()
        result = d.supervise([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
            '--review-sha256', a.review_sha256, '--input-root', str(a.input_root),
            '--child', '--parent', str(os.getpid())], folder)
        print(json.dumps(result), flush=True)
        return 0 if result['returncode'] == 0 and result['error'] is None and not result['cleanup'] else 1
    observed = d.observed(); d.bounds(observed, os.getpid(), a.parent)
    sys.path.insert(0, str(HERE))
    import test_acquire_native as tests
    import acquire_native as profile
    if Path(tests.__file__).resolve() != HERE / 'test_acquire_native.py' or Path(profile.__file__).resolve() != HERE / 'acquire_native.py':
        raise ValueError('Actual profile/test import origin changed')
    suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
    ids = d.flatten(suite)
    if ids != review['test_ids']:
        raise ValueError('Actual ordered controls changed')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(a.review_sha256, a.input_root) != review or d.observed() != observed:
        raise ValueError('Source or resource drift')
    receipt = {'passed': result.wasSuccessful(), 'controls': result.testsRun, 'test_ids': ids,
        'source_sha256': review['source_sha256'], 'input_sha256': review['input_sha256'], 'observed': observed,
        'native_executed': False, 'device_executed': False, 'model_quality_or_speed_proof': False}
    (folder / 'receipt.json').open('x').write(json.dumps(receipt, indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
