"""FIRST bounded selected-hosted prose controls and actual prompt encoding; no model."""
import argparse
import ast
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import unittest

import hashlib
BUILD_PIN='e8dcd79bd3a80cba931885149438f107d6d840693e508f738fd616fd6885f9ff'
Q=Path(__file__).resolve().parent.parent/'iq2s-persistent-v1'
if hashlib.sha256((Q/'iq2s_build.py').read_bytes()).hexdigest()!=BUILD_PIN:
    raise ValueError('Qualified CPU guard source changed')
existing=sys.modules.get('iq2s_build')
if existing is not None and Path(existing.__file__).resolve()!=Q/'iq2s_build.py':
    raise ValueError('Foreign CPU guard module')
sys.path.insert(0,str(Q))
import iq2s_build as c

HERE = Path(__file__).resolve().parent


def source_pins(review):
    return {name: c.sha(HERE / name) for name in review['source_sha256']}


MODULES=('test_prose_measure','test_transport','test_qualify_prose_cpu')
E=HERE.parents[1]
PRIOR=Q/'model-v1'
PRIOR_REVIEW='ecb2858a17059551b285edf487d3e2d584004371ed8492f9b1003db1dba632e7'

def test_ids():
    result=[]
    for module in MODULES:
        tree=ast.parse((HERE/(module+'.py')).read_text())
        result.extend(sorted(module+'.'+cls.name+'.'+fun.name for cls in tree.body
            if isinstance(cls,ast.ClassDef) for fun in cls.body
            if isinstance(fun,ast.FunctionDef) and fun.name.startswith('test_')))
    return result

def input_path(name,pin,inherited,root):
    """Only prior exact lexical aliases; inspect no path outside the real root."""
    c.require(type(name) is str and type(pin) is str,'Typed CPU input identity required')
    rel=Path(name);root=Path(root)
    c.require(root.is_absolute() and '..' not in root.parts and not rel.is_absolute()
              and name not in ('','.'),'Foreign CPU input path')
    if '..' in rel.parts:
        c.require(inherited.get(name)==pin,'Unreviewed lexical CPU alias')
    # Lexical containment is established BEFORE any filesystem access. Do not
    # resolve an arbitrary symlink and only then discover that it escaped E.
    target=Path(os.path.normpath(str(root/rel)))
    c.require(target!=root and target.is_relative_to(root),'CPU input escapes evidence root')
    for ancestor in [*reversed(root.parents),root]:
        c.require(not ancestor.is_symlink() and ancestor.is_dir(),'Real CPU evidence root required')
    current=root
    for i,part in enumerate(rel.parts):
        current=current.parent if part=='..' else current/part
        c.require(current.is_relative_to(root),'CPU alias traverses outside evidence root')
        c.require(not current.is_symlink(),'CPU input symlink refused')
        if i<len(rel.parts)-1:c.require(current.is_dir(),'CPU input ancestor missing')
    c.require(current==target and current.is_file(),'Exact existing CPU input file required')
    return current


def input_pins(review):
    # No new discovery or directory scans: exact manually frozen existing closure.
    c.require(c.sha(PRIOR/'numerical-CPU-source-review.json')==PRIOR_REVIEW,'Prior helper source inventory changed')
    old=json.loads((PRIOR/'numerical-CPU-source-review.json').read_text())
    inherited=old['source_input_sha256']
    actual={}
    for name,pin in review['source_input_sha256'].items():
        path=input_path(name,pin,inherited,E)
        actual[name]=c.sha(path)
        c.require(actual[name]==pin,'Frozen CPU dependency changed: '+name)
    c.require(all(actual.get(name)==pin for name,pin in old['source_input_sha256'].items()),'Prior helper source closure incomplete')
    for host in ('darwin','linux'):
        for name in ('receipt.json','child.json','child.log'):
            c.require(str((PRIOR/('numerical-CPU-'+host)/name).relative_to(E)) in actual,'Prior actual CPU proof omitted')
    return actual


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    os.nice(15)

def cleanup_child(process):
    errors = []
    for sig, seconds in ((signal.SIGTERM, 3), (signal.SIGKILL, 5)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except BaseException as exc:
            errors.append(repr(exc))
        try:
            process.wait(timeout=seconds)
        except BaseException as exc:
            errors.append(repr(exc))
        deadline = time.monotonic() + seconds
        while True:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return errors
            except BaseException as exc:
                errors.append(repr(exc))
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
    errors.append('Owned CPU process group still exists after cleanup')
    return errors


def encode_fixtures():
    """CPU-only selected API template. Never shorten, fit, infer or launch native."""
    import copy,importlib,tempfile
    path=E/'decode-optimization-20261028/model-v1'
    sys.path.insert(0,str(path))
    f=importlib.import_module('imma_fixtures')
    c.require(Path(f.__file__).resolve()==path/'imma_fixtures.py','Foreign fixture helper')
    source=HERE/'prose-fixtures.json'
    c.require(c.sha(source)=='8039ba7415335710ab481c5cd29f3c2c1bffb19b223d83ec586baf759a336faf','Prose request bytes changed')
    manifest=json.loads(source.read_text());support=f.load_support();s=support.server;tok=support.tokenizer()
    with tempfile.TemporaryDirectory(prefix='prose-cpu-')as tmp:
        vision=support.ds4_vision.Vision(support.ds4_vision.Geometry(),Path(tmp),s.Vision.load)
        try:
            svc=s.Service(s.MockEngine(tok,['CPU'],max_context=1048576),tok,
                s.ChatTemplate(support.dsml.pick_template(f.V/'tokenizer/chat_template.jinja')[0]),
                vision=vision,fit_max_tokens=False)
            svc.set_family('deepseek41');svc.answer_room=False;svc.reasoning_budget_configured=True
            svc.reasoning_budget_tokens=0;svc.reasoning_loop_recovery=False;svc.repeat_stop_tokens=0
            for case in manifest['cases']:
                body=copy.deepcopy(case['request']);messages,tools,kwargs=s.openai_to_messages(body)
                messages,_=s.prepare_format(body.get('response_format'),messages,with_tools=bool(tools))
                ids=svc.encode_prompt(messages,tools,kwargs,store=False)
                c.require(64<=len(ids)<=1024 and not tools and 129264 not in ids,'Actual prose prompt outside frozen short bounds')
                case.update(prompt_ids=ids,prompt_tokens=len(ids),prompt_ids_sha256=f.digest(f.packed(ids)),request_sha256=f.digest(f.packed(body)))
            c.require('torch'not in sys.modules,'GPU framework unexpectedly imported')
            manifest.update(API_sha256=f.SERVER_SHA,CPU_only=True,model_execution=False,fixture_sha256=c.sha(source))
            return manifest
        finally:vision.shutdown()


def main(child=False):
    guard = None
    if sys.platform == 'linux' and not child:
        _, runtime, _, host, binding = c.support()
        guard = lambda: c.guard(runtime, host, binding)
        guard()
    review = json.loads((HERE / 'prose-CPU-source-review.json').read_text())
    pins = source_pins(review)
    inputs = input_pins(review)
    ids = test_ids()
    c.require(review.get('all_source_and_tests_read') is True
              and review.get('source_sha256') == pins and review['test_ids'] == ids
              and c.sha(HERE / 'qualify_prose_cpu.py') == review['driver_sha256']
              and c.sha(Q / 'iq2s_build.py') == review['build_support_sha256'],
              'Exact manual source/test review absent')
    out = HERE / ('prose-CPU-FIRST-' + sys.platform)
    if child:
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(module) for module in MODULES)
        def names(s):
            for item in s:
                if isinstance(item, unittest.TestSuite):
                    yield from names(item)
                else:
                    yield item.id()
        c.require(list(names(suite)) == ids, 'Actual test inventory differs')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        c.require(source_pins(review) == pins and input_pins(review) == inputs, 'Source/input changed during CPU proof')
        if result.wasSuccessful():c.emit_new(out/'encoded-fixture.json',encode_fixtures())
        c.emit_new(out / 'receipt.json', {'passed': result.wasSuccessful(),
            'controls': result.testsRun, 'test_ids': ids, 'source_sha256': pins, 'source_input_sha256': inputs, 'input_sha256': inputs,
            'GPU_execution': False, 'compiler_execution': False, 'native_execution': False, 'fixture_sha256': c.sha(HERE/'prose-fixtures.json'),
            'encoded_fixture_sha256': c.sha(out/'encoded-fixture.json') if (out/'encoded-fixture.json').exists() else None})
        return 0 if result.wasSuccessful() else 1
    c.require(sys.platform in ('darwin', 'linux'), 'Physical Mac or Ubuntu only')
    if guard:
        guard()
    c.fresh(out)
    if guard:
        guard()
    out.mkdir()
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1', MALLOC_ARENA_MAX='1', PYTHONDONTWRITEBYTECODE='1')
    argv = [sys.executable, '-B', str(HERE / 'qualify_prose_cpu.py'), '--child']
    process = None
    error = None
    code = None
    cleanup = []
    started = time.monotonic()
    with (out / 'child.log').open('x') as log:
        try:
            process = subprocess.Popen(argv, cwd=HERE, env=env, preexec_fn=limits,
                start_new_session=True, stdout=log, stderr=subprocess.STDOUT)
            while True:
                if guard:
                    guard()
                if time.monotonic() - started >= 90:
                    raise TimeoutError('CPU proof wall90')
                if (out / 'child.log').stat().st_size > 4 * 2**20:
                    raise ValueError('CPU proof output4MiB')
                code = process.poll()
                if code is not None:
                    break
                time.sleep(0.2)
        except BaseException as exc:
            error = repr(exc)
            if process is not None:
                cleanup = cleanup_child(process)
                code = process.returncode
    c.emit_new(out / 'child.json', {'argv': argv, 'pid': process.pid if process else None,
        'returncode': code, 'CPU_s': 30, 'wall_s': 90, 'nice': 15, 'CUDA_hidden': True,
        'Linux_AS_MiB': 512 if sys.platform == 'linux' else None, 'error': error,
        'cleanup_errors': cleanup})
    c.require(code == 0 and error is None and not cleanup, 'FIRST CPU proof HOLD, preserve raw')
    if guard:
        guard()
    c.require(source_pins(review) == pins and input_pins(review) == inputs, 'Source/input changed after CPU proof')
    print(json.dumps({'passed': True, 'controls': len(ids), 'host': sys.platform}))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    raise SystemExit(main(args.child))

