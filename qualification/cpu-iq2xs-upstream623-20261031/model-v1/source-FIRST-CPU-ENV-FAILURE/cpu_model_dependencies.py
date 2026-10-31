"""Exact prior synthetic helpers only; no prior controller or outcomes imported."""
import hashlib
import importlib
from pathlib import Path
import sys
BASE = Path(__file__).resolve().parents[2] / 'model-v1'
PINS = {'imma_config': '18691963f89027fd169877c0cd6307f54954de1353a577d4c8935c015ea84986', 'imma_fixtures': 'c70d008d3277166b8ff5276f22cb4547ab76a6688eab4647ff2d1a024ec89e4a', 'imma_storage': 'd03c8f6d69e198e648014b15a00a4a7c3dd986815dac4a391b747924239e0143', 'imma_numeric_controls': 'cb3252d95fdbeef733b7f14a1dea1629f59f2d7f6b741709b95b4ac654eab323'}

def load_helpers(base=BASE):
    result = {}
    for name, pin in PINS.items():
        path = base / (name + '.py')
        if hashlib.sha256(path.read_bytes()).hexdigest() != pin:
            raise ValueError('Frozen synthetic helper changed: ' + name)
        module = sys.modules.get(name)
        if module is not None and Path(module.__file__).resolve() != path.resolve():
            raise ValueError('Foreign synthetic helper origin: ' + name)
        sys.path.insert(0, str(base))
        try: module = importlib.import_module(name)
        finally: sys.path.pop(0)
        if Path(module.__file__).resolve() != path.resolve():
            raise ValueError('Unexpected imported synthetic helper: ' + name)
        result[name] = module
    return result

helpers = load_helpers()
fixtures = helpers['imma_fixtures']
storage = helpers['imma_storage']
controls = helpers['imma_numeric_controls']


FENCE_BASE = BASE.parent / 'adaptive-expert-cache-v1/performance-v1'
FENCE_PINS = {'ae_config': 'e31a30b829be090a13e518f3a6ab1a4cb5600286261c0bc6457854c7bc021d20', 'ae_runtime': 'b5c5be169e58ddeae399a2226cf1f5985c303c84c2973780f839add448de52e7', 'ae_controls': '2ffec310fffaf166ac243826c91fd733fd4bb8a3a8ac903632b93d92132d5465'}

def load_fence(base=FENCE_BASE):
    for name,pin in FENCE_PINS.items():
        path=base/(name+'.py')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=pin:
            raise ValueError('Qualified fence source changed: '+name)
        module=sys.modules.get(name)
        if module is not None and Path(module.__file__).resolve()!=path.resolve():
            raise ValueError('Foreign fence helper origin: '+name)
    sys.path.insert(0,str(base))
    try:module=importlib.import_module('ae_controls')
    finally:sys.path.pop(0)
    for name,pin in FENCE_PINS.items():
        imported=sys.modules.get(name);path=base/(name+'.py')
        if imported is None or Path(imported.__file__).resolve()!=path.resolve() or hashlib.sha256(path.read_bytes()).hexdigest()!=pin:
            raise ValueError('Fence helper origin/hash changed: '+name)
    return module
