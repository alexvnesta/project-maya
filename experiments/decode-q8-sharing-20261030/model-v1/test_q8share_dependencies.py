"""Pinned immutable synthetic helper import controls; no model process."""
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import q8share_dependencies as d

class FrozenHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.pins={};self.modules={}
        for name in d.PINS:
            path=self.base/(name+'.py');path.write_text('synthetic '+name)
            self.pins[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            self.modules[name]=SimpleNamespace(__file__=str(path))
    def test_exact_helpers_and_import_path_restored(self):
        before=list(d.sys.path)
        with patch.object(d,'PINS',self.pins),patch.dict(d.sys.modules,self.modules),patch.object(d.importlib,'import_module',side_effect=lambda name:self.modules[name]):
            self.assertEqual(d.load_helpers(self.base),self.modules)
        self.assertEqual(d.sys.path,before)
    def test_changed_helper_refused_before_import(self):
        (self.base/'imma_config.py').write_text('changed')
        with patch.object(d,'PINS',self.pins),patch.object(d.importlib,'import_module',side_effect=AssertionError('no import')):
            with self.assertRaises(ValueError):d.load_helpers(self.base)
    def test_foreign_existing_module_refused(self):
        modules=dict(self.modules,imma_config=SimpleNamespace(__file__='/foreign/imma_config.py'))
        with patch.object(d,'PINS',self.pins),patch.dict(d.sys.modules,modules),patch.object(d.importlib,'import_module',side_effect=AssertionError('no import')):
            with self.assertRaises(ValueError):d.load_helpers(self.base)
    def test_foreign_import_result_and_import_error_restore_path(self):
        before=list(d.sys.path)
        for result in [SimpleNamespace(__file__='/foreign/imma_config.py'),RuntimeError('import failed')]:
            with patch.object(d,'PINS',self.pins),patch.dict(d.sys.modules,self.modules),patch.object(d.importlib,'import_module',side_effect=result if isinstance(result,Exception) else lambda name:result):
                with self.assertRaises((ValueError,RuntimeError)):d.load_helpers(self.base)
            self.assertEqual(d.sys.path,before)

if __name__=='__main__':unittest.main()
