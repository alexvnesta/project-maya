"""Dependency custody controls. Synthetic packages test setup, not HTTP behavior.

The CPU driver separately calls prepare/witness on the real pinned packages
before and after all controls, including the unchanged real HTTP fixture.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import cpu_dependencies as d


class Dependencies(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.manifest = self.base / 'DEPENDENCIES.json'
        self.data = {'schema': 1, 'platforms': {}}
        self.pins = {}
        for host in ('darwin', 'linux'):
            root = self.base / 'cpu-dependencies' / host
            files = {}
            origins = {}
            for name in d.MODULES:
                rel = name.replace('.', '/') + ('/__init__.py' if '.' not in name else '.py')
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('VALUE = 7\n')
                files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
                origins[name] = 'local:' + rel
                self.pins[str(path)] = files[rel]
            self.data['platforms'][host] = {
                'python': {'executable': str(Path(sys.executable).resolve()),
                           'sha256': d.sha(Path(sys.executable).resolve()),
                           'cache_tag': sys.implementation.cache_tag},
                'local_files': files, 'external_files': {}, 'modules': origins}
        self.refresh()

    def refresh(self):
        self.manifest.write_text(json.dumps(self.data, sort_keys=True))
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.pins[str(self.manifest)] = self.pin

    @contextmanager
    def isolated(self):
        # Restore all dependency module objects and search paths even on refusal.
        prior = {k: v for k, v in sys.modules.items() if k.split('.')[0] in d.TOPS}
        for name in prior:
            del sys.modules[name]
        try:
            flags = {name: getattr(sys.flags, name) for name in dir(sys.flags)
                     if not name.startswith('_')}
            flags['isolated'] = 1
            with patch.object(d.sys, 'path', list(sys.path)), \
                 patch.object(d.sys, 'flags', types.SimpleNamespace(**flags)), \
                 patch.object(d.sys, 'dont_write_bytecode', True):
                yield
        finally:
            for name in list(sys.modules):
                if name.split('.')[0] in d.TOPS:
                    del sys.modules[name]
            sys.modules.update(prior)

    def contract(self):
        return d.read_contract(self.manifest, self.pin, self.pins)

    def start(self):
        return d.prepare(self.manifest, self.pin, self.pins)

    def test_real_import_of_pinned_synthetic_packages_and_post_witness(self):
        with self.isolated():
            session = self.start()
            result = d.witness(session)
            self.assertEqual(set(result['after']), set(d.MODULES))
            self.assertTrue(result['all_inventory_rehashed'])
            self.assertEqual(sys.modules['jinja2'].VALUE, 7)
            self.assertIn('/' + sys.platform + '/', result['after']['numpy']['path'])

    def test_manifest_hash_refused_before_import(self):
        with self.isolated(), patch.object(d.importlib, 'import_module') as importer:
            with self.assertRaisesRegex(ValueError, 'manifest'):
                d.prepare(self.manifest, '0' * 64, self.pins)
            importer.assert_not_called()

    def test_missing_manifest_membership(self):
        del self.pins[str(self.manifest)]
        with self.isolated(), self.assertRaisesRegex(ValueError, 'manifest'):
            self.contract()

    def test_missing_package_membership(self):
        key = next(k for k in self.pins if k.endswith('jinja2/__init__.py'))
        del self.pins[key]
        with self.isolated(), self.assertRaisesRegex(ValueError, 'membership'):
            self.contract()

    def test_changed_other_platform_bytes_are_refused(self):
        other = 'linux' if sys.platform == 'darwin' else 'darwin'
        (self.base / 'cpu-dependencies' / other / 'jinja2/__init__.py').write_text('changed')
        with self.isolated(), self.assertRaisesRegex(ValueError, 'bytes changed'):
            self.contract()

    def test_extra_file_refused(self):
        (self.base / 'cpu-dependencies/darwin/extra.py').write_text('')
        with self.isolated(), self.assertRaisesRegex(ValueError, 'tree inventory'):
            self.contract()

    def test_missing_file_refused(self):
        (self.base / 'cpu-dependencies/linux/jinja2/__init__.py').unlink()
        with self.isolated(), self.assertRaisesRegex(ValueError, 'tree inventory'):
            self.contract()

    def test_symlink_file_refused(self):
        path = self.base / 'cpu-dependencies/linux/alias'
        path.symlink_to(self.manifest)
        with self.isolated(), self.assertRaisesRegex(ValueError, 'alias'):
            self.contract()

    def test_symlink_directory_refused(self):
        (self.base / 'cpu-dependencies/linux/alias').symlink_to(self.base, target_is_directory=True)
        with self.isolated(), self.assertRaisesRegex(ValueError, 'alias'):
            self.contract()

    def test_path_traversal_refused(self):
        with self.assertRaisesRegex(ValueError, 'relative'):
            d.relative('../foreign.py')

    def test_bytecode_refused(self):
        with self.assertRaisesRegex(ValueError, 'Bytecode'):
            d.relative('jinja2/__pycache__/x.pyc')

    def test_schema_bool_and_missing_platform_refused(self):
        for mutate in (lambda x: x.update(schema=True),
                       lambda x: x['platforms'].pop('linux')):
            saved = copy.deepcopy(self.data)
            mutate(self.data); self.refresh()
            with self.isolated(), self.assertRaisesRegex(ValueError, 'platform inventories'):
                self.contract()
            self.data = saved; self.refresh()

    def test_wrong_interpreter_hash_refused(self):
        self.data['platforms'][sys.platform]['python']['sha256'] = '0' * 64
        self.refresh()
        with self.isolated(), self.assertRaisesRegex(ValueError, 'interpreter'):
            self.contract()

    def test_wrong_cache_tag_refused(self):
        self.data['platforms'][sys.platform]['python']['cache_tag'] = 'wrong-abi'
        self.refresh()
        with self.isolated(), self.assertRaisesRegex(ValueError, 'interpreter'):
            self.contract()

    def test_nonisolated_and_bytecode_enabled_refused(self):
        with self.isolated():
            with patch.object(d.sys, 'flags', types.SimpleNamespace(isolated=0)), \
                 self.assertRaisesRegex(ValueError, 'Isolated'):
                self.contract()
            with patch.object(d.sys, 'dont_write_bytecode', False), \
                 self.assertRaisesRegex(ValueError, 'Isolated'):
                self.contract()

    def test_required_module_omitted(self):
        del self.data['platforms'][sys.platform]['modules']['PIL.ImageOps']
        self.refresh()
        with self.isolated(), self.assertRaisesRegex(ValueError, 'real dependency imports'):
            self.contract()

    def test_foreign_module_origin_refused(self):
        self.data['platforms'][sys.platform]['modules']['numpy'] = str(self.base / 'foreign.py')
        self.refresh()
        with self.isolated(), self.assertRaisesRegex(ValueError, 'outside pinned inventory'):
            self.contract()

    def test_preloaded_module_refused(self):
        with self.isolated():
            sys.modules['numpy'] = types.ModuleType('numpy')
            with self.assertRaisesRegex(ValueError, 'before pinned setup'):
                self.start()

    def test_other_platform_path_exposure_refused(self):
        with self.isolated():
            other = 'linux' if sys.platform == 'darwin' else 'darwin'
            sys.path.append(str(self.base / 'cpu-dependencies' / other))
            with self.assertRaisesRegex(ValueError, 'already exposed'):
                self.start()

    def test_foreign_resolver_refused_before_import(self):
        with self.isolated(), patch.object(d.PathFinder, 'find_spec', return_value=None), \
             patch.object(d.importlib, 'import_module') as importer:
            with self.assertRaisesRegex(ValueError, 'resolver'):
                self.start()
            importer.assert_not_called()

    def test_post_suite_source_change_refused(self):
        with self.isolated():
            session = self.start()
            Path(sys.modules['jinja2'].__file__).write_text('VALUE = 8\n')
            with self.assertRaisesRegex(ValueError, 'bytes changed'):
                d.witness(session)

    def test_post_suite_unpinned_submodule_refused(self):
        with self.isolated():
            session = self.start()
            foreign = types.ModuleType('numpy.foreign')
            foreign.__file__ = str(self.manifest)
            foreign.__spec__ = types.SimpleNamespace(origin=str(self.manifest))
            sys.modules['numpy.foreign'] = foreign
            with self.assertRaisesRegex(ValueError, 'origin'):
                d.witness(session)

    def test_post_suite_package_path_mutation_refused(self):
        with self.isolated():
            session = self.start()
            sys.modules['jinja2'].__path__.append(str(self.base))
            with self.assertRaisesRegex(ValueError, 'package search path'):
                d.witness(session)

    def test_post_suite_required_module_missing_refused(self):
        with self.isolated():
            session = self.start()
            del sys.modules['PIL.ImageOps']
            with self.assertRaisesRegex(ValueError, 'import missing'):
                d.witness(session)

    def test_external_file_verified_before_import(self):
        external = self.base / 'external-library.so'
        external.write_bytes(b'fixture-only-no-dlopen')
        self.data['platforms'][sys.platform]['external_files'][str(external)] = d.sha(external)
        self.refresh()
        with self.isolated():
            self.contract()
            external.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'External dependency bytes'):
                self.contract()


if __name__ == '__main__':
    unittest.main()
