"""FIRST native payload metadata/I/O/composition controls; no1870 materialization."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
NAMES = ('payload.py', 'test_payload.py', 'run_cpu.py')
DRIVER = HERE.parents[1] / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs():
    q = HERE.parent
    names = {'bounded_hash_helper': 'bounded-sha256-v1/fork_hash.py', 'recipe': 'recipe-v1/reconstruction.py', 'header': 'native-lane-v1/native_header.py',
        'conversion': 'iq3s-conversion-v1/convert.py', 'codec_source': 'native-codec-v2/mxpack.cpp',
        'codec_proof': 'native-codec-v2/BOTH_HOST_CPU_FIRST.json',
        'index': 'source-plan-v1/inputs/official-index-FIRST.json',
        'metadata': 'source-plan-v1/inputs/official-HF-metadata-FIRST.json',
        'fixture_weight': 'iq3s-real-matrix-v1/original-weight.bin',
        'fixture_scale': 'iq3s-real-matrix-v1/original-scale.bin'}
    return {name: sha(q / relative) for name, relative in names.items()}


def sources(): return {name: sha(HERE / name) for name in NAMES}


def checked(pin):
    path = HERE / 'ROOT_SOURCE_REVIEW.json'
    if sha(path) != pin: raise ValueError('Exact manual review required')
    review = json.loads(path.read_text())
    if review.get('entire_source_tests_driver_manually_read') is not True or review.get('sources') != sources() or \
            review.get('inputs') != inputs() or sha(DRIVER) != DRIVER_SHA:
        raise ValueError('Reviewed source/input/supervisor changed')
    return review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-sha256', required=True); parser.add_argument('--child', action='store_true')
    parser.add_argument('--parent', type=int); args = parser.parse_args()
    if not sys.flags.isolated or not sys.dont_write_bytecode: raise ValueError('Use Python -I -B')
    review = checked(args.review_sha256)
    spec = importlib.util.spec_from_file_location('native_payload_cpu_supervisor', DRIVER)
    d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
    # Keep the qualified supervisor/cleanup mechanics, but do not inherit loader
    # or Python startup variables into this new CPU proof child.
    clean = dict(d.ENV, PATH='/usr/bin:/bin', LANG='C', LC_ALL='C')
    d.environment = lambda: dict(clean)
    folder = HERE / ('CPU-FIRST-' + sys.platform)
    if not args.child:
        folder.mkdir()
        result = d.supervise([sys.executable, '-I', '-B', str(HERE / 'run_cpu.py'), '--review-sha256',
            args.review_sha256, '--child', '--parent', str(os.getpid())], folder)
        print(json.dumps(result), flush=True)
        return 0 if result['returncode'] == 0 and result['error'] is None and not result['cleanup'] else 1
    observed = d.observed(); d.bounds(observed, os.getpid(), args.parent)
    sys.path.insert(0, str(HERE))
    import payload
    import test_payload
    if Path(payload.__file__).resolve() != HERE / 'payload.py' or Path(test_payload.__file__).resolve() != HERE / 'test_payload.py':
        raise ValueError('Exact reviewed local modules')
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_payload); ids = d.flatten(suite)
    if ids != review['test_ids']: raise ValueError('Exact ordered payload controls')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if checked(args.review_sha256) != review or d.observed() != observed:
        raise ValueError('Source/inputs/resources changed during FIRST controls')
    receipt = {'passed': result.wasSuccessful(), 'physical_platform': sys.platform,
        'tests_run': result.testsRun, 'test_ids': ids, 'sources': sources(), 'inputs': inputs(), 'observed': observed,
        'returncode': 0 if result.wasSuccessful() else 1, 'failures': len(result.failures), 'errors': len(result.errors),
        'controls': {'CPU_seconds': 30, 'AS_bytes': [512 * 2**20] * 2 if sys.platform == 'linux' else None,
                     'wall_seconds': 90, 'nice': 15},
        'process_environment': dict(os.environ), 'isolated': bool(sys.flags.isolated),
        'supervisor_pid': args.parent, 'supervisor_sha256': DRIVER_SHA,
        'source_review_sha256': args.review_sha256,
        'scope': 'Pure native1870 metadata, small I/O/ownership and one3role codec composition; no whole native payload, model or GPU'}
    with (folder / 'receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2); stream.write('\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__': raise SystemExit(main())
