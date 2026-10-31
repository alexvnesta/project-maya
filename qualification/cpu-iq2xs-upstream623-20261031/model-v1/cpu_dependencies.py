"""Pinned test-only dependencies for the isolated CPU child; no installations.

prepare() runs after the child's resource/source checks and before test imports.
witness() runs again after the suite. External package files are selected by a
hash-pinned per-platform manifest; their bytes are never claimed cross-platform.
"""
import hashlib
import importlib
from importlib.machinery import PathFinder
import json
import os
from pathlib import Path
import stat
import sys

MODULES = ('jinja2', 'jinja2.sandbox', 'markupsafe', 'regex',
           'PIL', 'PIL.Image', 'PIL.ImageOps', 'numpy')
TOPS = frozenset(x.split('.')[0] for x in MODULES)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(),
            'Dependency path alias refused')
    st = path.stat()
    require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, 'One regular dependency file required')
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def pin(value):
    require(isinstance(value, str) and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value), 'SHA256 required')
    return value


def relative(value):
    require(isinstance(value, str) and value and not Path(value).is_absolute() and
            '..' not in Path(value).parts and str(Path(value)) == value,
            'Canonical relative dependency path required')
    require('__pycache__' not in Path(value).parts and not value.endswith(('.pyc', '.pyo')),
            'Bytecode dependency refused')
    return value


def tree_files(root):
    require(root.is_dir() and root.resolve() == root and not root.is_symlink(),
            'Exact dependency directory required')
    found = set()
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            require(not (Path(parent) / name).is_symlink(), 'Dependency directory alias refused')
        for name in files:
            path = Path(parent) / name
            require(not path.is_symlink(), 'Dependency file alias refused')
            found.add(str(path.relative_to(root)))
    return found


def read_contract(manifest_path, expected_sha256, expected_files):
    manifest_path = Path(manifest_path)
    require(sha(manifest_path) == pin(expected_sha256) and
            expected_files.get(str(manifest_path)) == expected_sha256,
            'Pinned dependency manifest required')
    data = json.loads(manifest_path.read_text())
    require(type(data.get('schema')) is int and data['schema'] == 1 and
            set(data.get('platforms', {})) == {'darwin', 'linux'}, 'Both platform inventories required')
    base = manifest_path.parent / 'cpu-dependencies'
    local_maps = {}
    for host, item in data['platforms'].items():
        require(set(item) == {'python', 'local_files', 'external_files', 'modules'},
                'Exact platform contract fields required')
        require(isinstance(item['local_files'], dict) and item['local_files'],
                'Nonempty platform package inventory required')
        root = base / host
        require(tree_files(root) == set(item['local_files']), 'Exact dependency tree inventory required')
        paths = {}
        for rel, value in item['local_files'].items():
            path = root / relative(rel)
            require(expected_files.get(str(path)) == pin(value) and sha(path) == value,
                    'Local dependency membership or bytes changed')
            paths[str(path)] = value
        require(set(item['modules']) == set(MODULES), 'Exact real dependency imports required')
        require(isinstance(item['external_files'], dict), 'External inventory required')
        for path, value in item['external_files'].items():
            require(Path(path).is_absolute() and '..' not in Path(path).parts,
                    'Absolute external dependency path required')
            pin(value)
        local_maps[host] = paths
    require(sys.platform in data['platforms'], 'Supported physical platform required')
    item = data['platforms'][sys.platform]
    python = item['python']
    require(set(python) == {'executable', 'sha256', 'cache_tag'} and
            str(Path(sys.executable).resolve()) == python['executable'] and
            sha(Path(python['executable'])) == pin(python['sha256']) and
            sys.implementation.cache_tag == python['cache_tag'], 'Exact physical interpreter required')
    require(sys.flags.isolated == 1 and sys.dont_write_bytecode is True,
            'Isolated no-bytecode interpreter required')
    inventory = dict(local_maps[sys.platform])
    for path, value in item['external_files'].items():
        require(path not in inventory and sha(Path(path)) == value,
                'External dependency bytes changed or overlap')
        inventory[path] = value
    root = base / sys.platform
    origins = {}
    for name, value in item['modules'].items():
        require(isinstance(value, str), 'Module origin string required')
        path = root / relative(value[6:]) if value.startswith('local:') else Path(value)
        require(str(path) in inventory, 'Module origin outside pinned inventory')
        origins[name] = str(path)
    return data, root, inventory, origins


def module_origins(inventory, origins):
    observed = {}
    for name, module in list(sys.modules.items()):
        if name.split('.')[0] not in TOPS:
            continue
        require(module is not None, 'Incomplete dependency module refused')
        file = getattr(module, '__file__', None)
        spec = getattr(module, '__spec__', None)
        require(isinstance(file, str) and spec is not None and spec.origin == file and
                file in inventory and sha(Path(file)) == inventory[file],
                'Imported dependency origin or bytes changed')
        package_paths = getattr(module, '__path__', None)
        if package_paths is not None:
            require(list(package_paths) == [str(Path(file).parent)], 'Foreign dependency package search path')
        observed[name] = {'path': file, 'sha256': inventory[file]}
    require(all(observed.get(name, {}).get('path') == path for name, path in origins.items()),
            'Required dependency import missing or foreign')
    return observed


def prepare(manifest_path, expected_sha256, expected_files):
    """Verify all bytes before exposing only this host's package root and importing."""
    data, root, inventory, origins = read_contract(manifest_path, expected_sha256, expected_files)
    require(not any(name.split('.')[0] in TOPS for name in sys.modules),
            'Dependency was imported before pinned setup')
    roots = {str(Path(manifest_path).parent / 'cpu-dependencies' / p) for p in ('darwin', 'linux')}
    require(not any(x in roots for x in sys.path), 'Dependency root already exposed')
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    # Check top-level resolver origins without executing package code first.
    for name in sorted(TOPS):
        spec = PathFinder.find_spec(name, sys.path)
        require(spec is not None and spec.origin == origins[name], 'Dependency resolver selected foreign origin')
    for name in MODULES:
        importlib.import_module(name)
    session = {'manifest_path': str(manifest_path), 'manifest_sha256': expected_sha256,
               'expected_files': dict(expected_files), 'platform': sys.platform,
               'root': str(root), 'contract': data}
    session['before'] = module_origins(inventory, origins)
    return session


def witness(session):
    """Recheck source bytes and every loaded dependency submodule after the suite."""
    data, root, inventory, origins = read_contract(session['manifest_path'], session['manifest_sha256'],
                                                 session['expected_files'])
    require(data == session['contract'] and sys.platform == session['platform'] and
            str(root) == session['root'] and sys.path.count(str(root)) == 1 and
            str(root.parent / ('linux' if sys.platform == 'darwin' else 'darwin')) not in sys.path,
            'Dependency setup changed during suite')
    after = module_origins(inventory, origins)
    require(all(after.get(name) == value for name, value in session['before'].items()),
            'Previously imported dependency changed')
    return {'python':data['platforms'][sys.platform]['python'],'platform': sys.platform, 'manifest_sha256': session['manifest_sha256'],
            'root': str(root), 'before': session['before'], 'after': after,
            'all_inventory_rehashed': True}
