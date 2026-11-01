"""FIRST focused40-shard/coexistence CPU controls; no download/kernel reruns."""
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
NAMES = ('acquire.py', 'test_acquire.py', 'run_cpu.py', 'ASSET_MANIFEST.json')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs():
    q = HERE.parent
    paths = {'index': q / 'source-plan-v1/inputs/official-index-FIRST.json',
             'metadata': q / 'source-plan-v1/inputs/official-HF-metadata-FIRST.json',
             'legacy_transport': q / 'iq3s-source-acquisition-v1/acquire.py',
             'legacy_qualification': q / 'iq3s-source-acquisition-v1/acquisition-qualification.json',
             'legacy_health': q / 'iq3s-source-acquisition-v1/healthy_guard.py',
             'lease_owner': HERE.parents[1] / 'cpu-iq2xs-upstream623-v1/build-v3/build.py'}
    return {name: sha(path) for name, path in paths.items()}


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
    import acquire
    import test_acquire
    if Path(acquire.__file__).resolve() != HERE / 'acquire.py' or Path(test_acquire.__file__).resolve() != HERE / 'test_acquire.py':
        raise ValueError('Exact reviewed local modules only')
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_acquire)
    ids = d.flatten(suite)
    if ids != review['test_ids']: raise ValueError('Exact ordered new controls')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(args.review_sha256) != review or d.observed() != observed:
        raise ValueError('Source/inputs/resources changed during FIRST controls')
    label = {'darwin': 'mac', 'linux': 'ubuntu'}[sys.platform]
    receipt = {'passed': result.wasSuccessful(), 'physical_host': label,
               'tests_run': result.testsRun, 'test_ids': ids, 'source_map': source_map(),
               'input_map': inputs(), 'observed': observed, 'failures': len(result.failures),
               'errors': len(result.errors), 'returncode': 0 if result.wasSuccessful() else 1,
               'scope': 'New40-trunk closure and exact qualified CPU-conversion coexistence only; no downloads, kernel suites or model/GPU actions'}
    with (HERE / ('CPU-FIRST-' + label + '.json')).open('x') as stream:
        json.dump(receipt, stream, indent=2); stream.write('\n')
    return receipt['returncode']


if __name__ == '__main__': raise SystemExit(main())
