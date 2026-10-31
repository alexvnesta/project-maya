"""First bounded proof of lossless offline overlay construction; synthetic source bytes only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
NAMES = ('construct_native.py','test_construct_native.py','run_construct_cpu.py')
DRIVER = HERE.parent / 'cpu-iq2xs-upstream623-v1/model-v1/cpu_driver.py'
PACK=HERE.parent/'maya-s-comparison-v1/pack-v1/pack-FIRST'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_paths(root):
    paths={'acquisition-source':HERE/'acquire_native.py','acquisition-qualified':HERE/'acquire-qualification.json','acquisition-state':HERE/'ACQUIRE_STATE.json','plan':HERE/'hybrid_plan_r2.py','plan-review':HERE/'PLAN_R2_SOURCE_ROOT_REVIEW.json','codec-source':HERE/'mxpack.cpp','codec-review':HERE/'CODEC_SOURCE_ROOT_REVIEW.json','CPU-supervisor':DRIVER,'manifest':HERE/'NATIVE_GU_SOURCE_MANIFEST.json','index':HERE/'official-1017-safetensors-index-FIRST.json'}
    for f in ('model-00028-of-00048.safetensors','model-00029-of-00048.safetensors'):paths['header-'+f]=HERE/('official-header-'+f+'.json')
    for mode in ('PLAN-R2','CODEC'):
        for host in ('darwin','linux'):
            for n in ('receipt.json','child.json','child.log'):paths[mode+'-'+host+'-'+n]=HERE/(mode+'-CPU-FIRST-'+host)/n
    for n in ('ds4.txt','tensors.txt','engram.bin','tokenizer/tokenizer.json','tokenizer/merges.txt','tokenizer/chat_template.jinja','tokenizer/token_type.json','tokenizer/vocab.json'):
        paths['base-'+n]=PACK/n
    for n in ('test_hybrid_plan_r2.py','run_plan_cpu_r2.py','test_mxpack.py','run_codec_cpu.py','CODEC-CPU-FIRST-linux/compile.json','CODEC-CPU-FIRST-linux/mxpack'):
        paths['prerequisite-'+n]=HERE/n
    return paths


def checked(pin, root):
    path = HERE / 'CONSTRUCT_SOURCE_ROOT_REVIEW.json'
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
    folder = HERE / ('CONSTRUCT-CPU-FIRST-' + sys.platform)
    if not a.child:
        folder.mkdir()
        result = d.supervise([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
            '--review-sha256', a.review_sha256, '--input-root', str(a.input_root),
            '--child', '--parent', str(os.getpid())], folder)
        print(json.dumps(result), flush=True)
        return 0 if result['returncode'] == 0 and result['error'] is None and not result['cleanup'] else 1
    observed = d.observed(); d.bounds(observed, os.getpid(), a.parent)
    sys.path.insert(0, str(HERE))
    import test_construct_native as tests
    import construct_native as profile
    if Path(tests.__file__).resolve() != HERE / 'test_construct_native.py' or Path(profile.__file__).resolve() != HERE / 'construct_native.py':
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
