"""Materialize only the exact metadata transform already proved on both hosts."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
Q = HERE.parent
sys.path.insert(0, str(Q.parent / 'maya-s-comparison-v1'))
import acquire
sys.path.insert(0, str(HERE))
import metadata


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    gate = acquire.SelectedGate()
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20)); os.nice(15)
    proofs = [json.loads((HERE / ('CPU-FIRST-' + p + '.json')).read_text()) for p in ('mac', 'ubuntu')]
    assert all(p['passed'] and p['controls'] == 6 and p['returncode'] == 0 for p in proofs)
    for field in ('source_sha256', 'input_sha256', 'test_ids'): assert proofs[0][field] == proofs[1][field]
    for name, pin in proofs[0]['source_sha256'].items(): assert sha(HERE / name) == pin
    for name, pin in proofs[0]['input_sha256'].items():
        path = Q / name.removeprefix('shared/') if name.startswith('shared/') else HERE / name
        assert sha(path) == pin
    terminal_path = Q / 'base-acquisition-v2/acquisition-state.json'
    terminal = json.loads(terminal_path.read_text())
    assert terminal['status'] == 'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN' and terminal['returncode'] == 0
    manifest = json.loads((Q / 'base-acquisition-v2/ASSET_MANIFEST.json').read_text())
    assert len(terminal['files']) == len(manifest['files']) == 8
    for row, spec in zip(terminal['files'], manifest['files']):
        assert row['path'] == spec['path'] and row['sha256'] == spec['sha256'] and row['bytes'] == spec['size']
        asset = Q / 'base-acquisition-v1/assets' / row['path']
        assert asset.is_file() and not asset.is_symlink() and asset.stat().st_size == spec['size']
    pins = json.loads((HERE / 'BASE_METADATA_PINS.json').read_text())
    blobs = {n: (HERE / 'base-metadata' / n).read_bytes() for n in pins}
    spec = importlib.util.spec_from_file_location('exact_overlay_metadata', Q / 'iq3s-overlay-v1/overlay.py')
    overlay = importlib.util.module_from_spec(spec); spec.loader.exec_module(overlay)
    result = metadata.construct(blobs, pins, json.loads((Q / 'iq3s-overlay-v1/SOURCE_PLAN.json').read_text()), overlay)
    gate()
    out = HERE / 'pack-FIRST'; out.mkdir()
    for name, data in result.items():
        path = out / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f: f.write(data)
    receipt = {'passed': True, 'metadata_only': True, 'weights_ready': False,
               'all8_base_terminal_sha256': sha(terminal_path),
               'outputs': {n: {'bytes': len(data), 'sha256': sha(out / n)} for n, data in result.items()},
               'selected_binding': gate.host.start_binding,
               'source_sha256': proofs[0]['source_sha256'], 'CPU_test_ids': proofs[0]['test_ids'],
               'scope': 'Base metadata plus exact3840IQ3S tensor offsets. Actual overlay, native payload and GPU qualification still required.'}
    with (HERE / 'CONSTRUCTION_FIRST.json').open('x') as f: json.dump(receipt, f, indent=2); f.write('\n')
    print(json.dumps(receipt))


if __name__ == '__main__': main()
