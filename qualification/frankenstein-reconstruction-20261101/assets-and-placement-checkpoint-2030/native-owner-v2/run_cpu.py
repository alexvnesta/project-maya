"""FIRST focused native source custody/receipt controls; no GPU or model execution."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
DRIVER = HERE.parents[1] / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
NAMES = ('owner.py', 'test_owner.py', 'run_cpu.py')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs():
    q = HERE.parent
    paths = {'payload': q / 'native-payload-v2/payload.py',
             'bounded_hash_helper': q / 'bounded-sha256-v1/fork_hash.py',
             'build_custody': q / 'placement-native-build-v1/build_current.py',
             'bulk_verifier': q / 'iq3s-bulk-v1/bulk.py',
             'shared_driver': DRIVER}
    return {name: sha(path) for name,path in paths.items()}


def source_map(): return {name: sha(HERE / name) for name in NAMES}


def checked(pin):
    path = HERE / 'ROOT_SOURCE_REVIEW.json'
    if sha(path) != pin: raise ValueError('Exact manual review required')
    review = json.loads(path.read_text())
    if review.get('entire_source_tests_driver_manually_read') is not True or \
            review.get('source_map') != source_map() or review.get('input_map') != inputs() or \
            sha(DRIVER) != DRIVER_SHA:
        raise ValueError('Reviewed source/input/supervisor changed')
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
    spec = importlib.util.spec_from_file_location('original_expert_cpu_supervisor', DRIVER)
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
    import owner
    import test_owner
    if Path(owner.__file__).resolve() != HERE / 'owner.py' or Path(test_owner.__file__).resolve() != HERE / 'test_owner.py':
        raise ValueError('Exact reviewed local modules only')
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_owner)
    ids = d.flatten(suite)
    if ids != review['test_ids']: raise ValueError('Exact ordered new controls')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(args.review_sha256) != review or d.observed() != observed:
        raise ValueError('Source/inputs/resources changed during FIRST controls')
    label = {'darwin': 'mac', 'linux': 'ubuntu'}[sys.platform]
    receipt = {'passed': result.wasSuccessful(), 'physical_host': label,
               'controls': result.testsRun, 'test_ids': ids, 'source_sha256': source_map(),
               'input_sha256': inputs(), 'observed': observed, 'failures': len(result.failures),
               'errors': len(result.errors), 'returncode': 0 if result.wasSuccessful() else 1,
               'scope': 'New native source custody/receipt controls only; no GPU allocation, inference or service actions'}
    with (HERE / ('CPU-FIRST-' + label + '.json')).open('x') as stream:
        json.dump(receipt, stream, indent=2); stream.write('\n')
    return receipt['returncode']


if __name__ == '__main__': raise SystemExit(main())
