"""FIRST small bulk-controller controls only. ROOT must read all new files first."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
NAMES = ('bulk.py', 'test_bulk.py', 'run_cpu.py')
DRIVER = HERE.parents[1] / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def input_pins():
    q = HERE.parent
    names = ('iq3s-conversion-v1/convert.py', 'iq3s-conversion-v1/SOURCE_PLAN.json',
             'iq3s-conversion-v1/PLATFORM_ARTIFACTS.json', 'iq3s-conversion-v1/BOTH_HOST_CPU_FIRST.json',
             'placement-native-build-v1/build_current.py', 'base-acquisition-v2/ASSET_MANIFEST.json')
    return {name: sha(q / name) for name in names} | {'shared_driver': sha(DRIVER)}


def checked(pin):
    path = HERE / 'ROOT_SOURCE_REVIEW.json'
    if sha(path) != pin: raise ValueError('Exact manual review required')
    review = json.loads(path.read_text())
    if review.get('entire_source_tests_driver_manually_read') is not True or \
            review.get('source_sha256') != {n: sha(HERE / n) for n in NAMES} or \
            review.get('input_sha256') != input_pins() or sha(DRIVER) != DRIVER_SHA:
        raise ValueError('Manual source/input/driver bytes changed')
    return review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--parent', type=int)
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('Use isolated Python -I -B')
    review = checked(args.review_sha256)
    spec = importlib.util.spec_from_file_location('bulk_cpu_supervisor', DRIVER)
    d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
    folder = HERE / ('CPU-FIRST-' + sys.platform)
    if not args.child:
        folder.mkdir()
        result = d.supervise([sys.executable, '-I', '-B', str(HERE / 'run_cpu.py'),
            '--review-sha256', args.review_sha256, '--child', '--parent', str(os.getpid())], folder)
        print(json.dumps(result), flush=True)
        return 0 if result['returncode'] == 0 and result['error'] is None and not result['cleanup'] else 1
    observed = d.observed(); d.bounds(observed, os.getpid(), args.parent)
    sys.path.insert(0, str(HERE))
    import bulk
    import test_bulk
    if Path(bulk.__file__).resolve() != HERE / 'bulk.py' or Path(test_bulk.__file__).resolve() != HERE / 'test_bulk.py':
        raise ValueError('Reviewed local modules only')
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_bulk)
    ids = d.flatten(suite)
    if ids != review['test_ids']: raise ValueError('Exact ordered CPU controls')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(args.review_sha256) != review or d.observed() != observed:
        raise ValueError('Source/inputs/resources changed during FIRST controls')
    receipt = {'passed': result.wasSuccessful(), 'physical_platform': sys.platform,
               'controls': result.testsRun, 'test_ids': ids, 'source_sha256': review['source_sha256'],
               'returncode': 0 if result.wasSuccessful() else 1,
               'failures': len(result.failures), 'errors': len(result.errors),
               'input_sha256': review['input_sha256'], 'observed': observed,
               'scope': 'Small bulk receipt/ordering/source/ownership controls only; no assets, conversion or model execution'}
    with (folder / 'receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2); stream.write('\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__': raise SystemExit(main())
