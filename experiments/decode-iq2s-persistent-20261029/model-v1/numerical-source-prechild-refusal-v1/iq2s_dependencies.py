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
