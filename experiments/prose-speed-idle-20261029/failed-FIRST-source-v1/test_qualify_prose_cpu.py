"""Pure CPU input custody controls; no subprocess, native, service or tokenizer."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import qualify_prose_cpu as d

class InputCustody(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()/'e';self.root.mkdir()
        (self.root/'old/child').mkdir(parents=True)
        self.file=self.root/'source.py';self.file.write_text('pinned synthetic source')
        self.pin=d.c.sha(self.file);self.alias='old/child/../../source.py'
        self.prior={self.alias:self.pin}
    def test_exact_inherited_alias_returns_same_canonical_file(self):
        self.assertEqual(d.input_path(self.alias,self.pin,self.prior,self.root),self.file)
    def test_unreviewed_alias_refused_even_for_identical_target(self):
        with self.assertRaisesRegex(ValueError,'Unreviewed'):
            d.input_path('old/../source.py',self.pin,self.prior,self.root)
    def test_changed_pin_on_reviewed_raw_alias_refused(self):
        with self.assertRaisesRegex(ValueError,'Unreviewed'):
            d.input_path(self.alias,'f'*64,self.prior,self.root)
    def test_new_canonical_input_allowed_without_traversal(self):
        self.assertEqual(d.input_path('source.py',self.pin,{},self.root),self.file)
    def test_absolute_and_even_reviewed_escape_refused_before_metadata(self):
        for name in ('/foreign/source.py','../source.py','old/../../../source.py'):
            with patch.object(Path,'is_symlink',side_effect=AssertionError('No metadata access')):
                with self.assertRaises(ValueError):d.input_path(name,self.pin,{name:self.pin},self.root)
    def test_symlink_prefix_refused_before_descendant_inspection(self):
        (self.root/'alias').symlink_to(self.root/'old',target_is_directory=True)
        name='alias/child/../../source.py';seen=[];original=Path.is_symlink
        def observe(path):seen.append(path);return original(path)
        with patch.object(Path,'is_symlink',observe):
            with self.assertRaisesRegex(ValueError,'symlink'):d.input_path(name,self.pin,{name:self.pin},self.root)
        self.assertIn(self.root/'alias',seen);self.assertNotIn(self.root/'alias/child',seen)
    def fixture(self):
        prior=self.root/'prior';prior.mkdir()
        source={'source_input_sha256':self.prior};path=prior/'numerical-CPU-source-review.json'
        path.write_text(json.dumps(source));inputs=dict(self.prior)
        for host in ('darwin','linux'):
            folder=prior/('numerical-CPU-'+host);folder.mkdir()
            for name in ('receipt.json','child.json','child.log'):
                f=folder/name;f.write_text('frozen raw '+host+'/'+name)
                inputs[str(f.relative_to(self.root))]=d.c.sha(f)
        return prior,d.c.sha(path),{'source_input_sha256':inputs}
    def test_actual_input_map_preserves_raw_key_and_checks_bytes_and_closure(self):
        prior,pin,review=self.fixture()
        with patch.object(d,'E',self.root),patch.object(d,'PRIOR',prior),patch.object(d,'PRIOR_REVIEW',pin):
            self.assertEqual(d.input_pins(review),review['source_input_sha256'])
            missing={'source_input_sha256':dict(review['source_input_sha256'])};del missing['source_input_sha256'][self.alias]
            with self.assertRaisesRegex(ValueError,'closure incomplete'):d.input_pins(missing)
            self.file.write_text('tampered')
            with self.assertRaisesRegex(ValueError,'dependency changed'):d.input_pins(review)
    def test_prior_inventory_tamper_refused_before_input_metadata(self):
        prior,pin,review=self.fixture()
        (prior/'numerical-CPU-source-review.json').write_text('changed')
        with patch.object(d,'E',self.root),patch.object(d,'PRIOR',prior),patch.object(d,'PRIOR_REVIEW',pin), \
             patch.object(d,'input_path',side_effect=AssertionError('Must reject first')):
            with self.assertRaisesRegex(ValueError,'inventory changed'):d.input_pins(review)

if __name__=='__main__':unittest.main()
