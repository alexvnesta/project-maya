"""One fresh bounded child, exact manual source map and actual unittest IDs."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
NAMES = ('build_current.py', 'test_build_current.py', 'run_build_cpu.py')
DRIVER = HERE.parent / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(pin):
    path = HERE / 'ROOT_BUILD_SOURCE_REVIEW.json'
    if sha(path) != pin:
        raise ValueError('Manual review bytes changed')
    review = json.loads(path.read_text())
    rows = {n: sha(HERE / n) for n in NAMES}
    if rows != review['source_sha256'] or review['entire_new_source_tests_read'] is not True:
        raise ValueError('Exact manually read source required')
    if sha(DRIVER) != DRIVER_SHA:
        raise ValueError('Bounded supervisor changed')
    return review


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--review-sha256', required=True)
    ap.add_argument('--child', action='store_true')
    ap.add_argument('--parent', type=int)
    a = ap.parse_args()
    review = checked(a.review_sha256)
    spec = importlib.util.spec_from_file_location('bounded_build_supervisor', DRIVER)
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    folder = HERE / ('CPU-BUILD-FIRST-' + sys.platform)
    if not a.child:
        folder.mkdir()
        result = d.supervise([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
                              '--review-sha256', a.review_sha256, '--child', '--parent', str(os.getpid())], folder)
        print(json.dumps(result), flush=True)
        return 0 if result['returncode'] == 0 and result['error'] is None and not result['cleanup'] else 1
    observed = d.observed()
    d.bounds(observed, os.getpid(), a.parent)
    sys.path.insert(0, str(HERE))
    import test_build_current as tests
    import build_current as build
    if Path(tests.__file__).resolve() != HERE / 'test_build_current.py' or Path(build.__file__).resolve() != HERE / 'build_current.py':
        raise ValueError('Actual module origin changed')
    suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
    ids = d.flatten(suite)
    if ids != review['test_ids']:
        raise ValueError('Actual ordered test IDs changed')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(a.review_sha256) != review or d.observed() != observed:
        raise ValueError('Source or bounded child resources changed')
    receipt = {'passed': result.wasSuccessful(), 'controls': result.testsRun, 'test_ids': ids,
               'source_sha256': review['source_sha256'], 'observed': observed,
               'compiler_executed': False, 'device_executed': False, 'production_changed': False}
    (folder / 'receipt.json').open('x').write(json.dumps(receipt, indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
