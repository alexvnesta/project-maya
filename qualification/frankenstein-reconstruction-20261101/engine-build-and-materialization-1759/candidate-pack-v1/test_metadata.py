import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import metadata as m

HERE = Path(__file__).resolve().parent


class Metadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = json.loads((HERE / 'BASE_METADATA_PINS.json').read_text())
        cls.blobs = {n: (HERE / 'base-metadata' / n).read_bytes() for n in cls.pins}
        path = HERE.parent / 'iq3s-overlay-v1/overlay.py'
        cls.module = importlib.util.module_from_spec(importlib.util.spec_from_file_location('frozen_overlay', path))
        cls.module.__spec__.loader.exec_module(cls.module)
        cls.plan = json.loads((HERE.parent / 'iq3s-overlay-v1/SOURCE_PLAN.json').read_text())

    def test_actual_complete_metadata_rewrite_and_exact_target_coverage(self):
        result = m.construct(self.blobs, self.pins, self.plan, self.module)
        old = {r.split()[1]: r for r in self.blobs['tensors.txt'].decode().splitlines() if r.startswith('t ')}
        new = {r.split()[1]: r for r in result['tensors.txt'].decode().splitlines() if r.startswith('t ')}
        self.assertEqual(set(old), set(new)); self.assertEqual(len(old), 48795)
        changed = [n for n in old if old[n] != new[n]]
        expected = {f'layers.{l}.ffn.experts.{e}.{r}.weight' for l in range(24, 29)
                    for e in range(384) for r in ('w1', 'w3')}
        self.assertEqual(set(changed), expected)
        for n in changed:
            row = new[n].split(); self.assertEqual(row[2:4], ['IQ3_S', '8'])
            self.assertEqual(row[5:], ['5068800', '2304', '5120'])
        files = [r for r in result['tensors.txt'].decode().splitlines() if r.startswith('file ')]
        self.assertEqual(len(files), 9)
        self.assertIn('model_dir ' + m.REMOTE_Q + '\n', result['ds4.txt'].decode())

    def test_every_unchanged_asset_points_to_retained_actual_source(self):
        result = m.construct(self.blobs, self.pins, self.plan, self.module)
        files = {int(r.split()[1]): r.split()[2] for r in result['tensors.txt'].decode().splitlines() if r.startswith('file ')}
        for i in range(6): self.assertEqual(files[i], 'base-acquisition-v1/assets/Maya-S/DeepSeek-V4.1-Flash-1017-Maya-S-IQ2_XXS-%05d-of-00006.gguf' % (i + 1))
        self.assertEqual(files[6], 'base-acquisition-v1/assets/dspark/dspark.bin')
        self.assertEqual(files[7], '../../vision-assets-1017/vision.bin')
        self.assertEqual(files[8], 'iq3s-bulk-v1/conversion-FIRST/overlay.iq3s')

    def test_tokenizer_template_and_engram_index_are_byte_identical(self):
        result = m.construct(self.blobs, self.pins, self.plan, self.module)
        for n in self.blobs:
            if n not in ('ds4.txt', 'tensors.txt'): self.assertEqual(result[n], self.blobs[n])

    def test_changed_metadata_refused(self):
        wrong = dict(self.blobs, **{'ds4.txt': self.blobs['ds4.txt'] + b'changed'})
        with self.assertRaises(ValueError): m.construct(wrong, self.pins, self.plan, self.module)

    def test_missing_metadata_refused(self):
        wrong = dict(self.blobs); wrong.pop('engram.bin')
        with self.assertRaises(ValueError): m.construct(wrong, self.pins, self.plan, self.module)

    def test_missing_original_role_or_wrong_offset_refused(self):
        for mutate in ('missing', 'offset'):
            plan = copy.deepcopy(self.plan)
            if mutate == 'missing': plan['records'].pop()
            else: plan['records'][2]['target_offset'] += 1
            with self.assertRaises(ValueError): m.construct(self.blobs, self.pins, plan, self.module)


if __name__ == '__main__': unittest.main()
