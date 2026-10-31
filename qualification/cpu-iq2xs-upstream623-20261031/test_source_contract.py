"""Portable controls only; physical AVX2 numerical proof is a separate gate."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import source_contract as s

HERE = Path(__file__).resolve().parent


class Custody(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in ('base', 'candidate'):
            shutil.copytree(HERE / name, self.root / name)

    def test_exact_selected_base_and_candidate(self):
        self.assertEqual(s.source_contract(self.root), {'base': s.BASE, 'candidate': s.CANDIDATE})

    def test_missing_selected_source_refused(self):
        (self.root / 'base/src/ds4/ds4_iq_cpu.cpp').unlink()
        with self.assertRaisesRegex(ValueError, 'inventory'):
            s.source_contract(self.root)

    def test_candidate_mutation_refused(self):
        p = self.root / 'candidate/src/kernels/cpu/iq_avx2.cpp'
        p.write_text(p.read_text().replace('0.125f * hsum_ggml', '0.25f * hsum_ggml'))
        with self.assertRaisesRegex(ValueError, 'inventory'):
            s.source_contract(self.root)

    def test_unrelated_candidate_file_refused(self):
        (self.root / 'candidate/model.cpp').write_text('unrelated')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            s.source_contract(self.root)

    def test_missing_accessor_refused(self):
        p = self.root / 'candidate/src/kernels/cpu/native_expert.cpp'
        p.write_text(p.read_text().replace('bool native_rows1_exact(int type)', 'bool renamed(int type)'))
        with self.assertRaisesRegex(ValueError, 'inventory'):
            s.source_contract(self.root)

    def test_symlink_refused(self):
        p = self.root / 'candidate/src/kernels/cpu/iq_avx2.cpp'
        p.unlink(); p.symlink_to(HERE / 'candidate/src/kernels/cpu/iq_avx2.cpp')
        with self.assertRaisesRegex(ValueError, 'alias'):
            s.source_contract(self.root)

    def test_hardlink_refused(self):
        p = self.root / 'candidate/src/kernels/cpu/iq_avx2.cpp'
        os.link(p, self.root / 'extra-link')
        with self.assertRaisesRegex(ValueError, 'hardlink'):
            s.source_contract(self.root)

    def test_root_alias_refused(self):
        shutil.rmtree(self.root / 'candidate')
        (self.root / 'candidate').symlink_to(HERE / 'candidate', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'regular source'):
            s.source_contract(self.root)


class Scope(unittest.TestCase):
    def test_native_runtime_unchanged_except_observer(self):
        rel = 'src/kernels/cpu/native_expert.cpp'
        before = (HERE / 'base' / rel).read_text()
        after = (HERE / 'candidate' / rel).read_text()
        added = '\nbool native_rows1_exact(int type) { return exact_rows1(type) != nullptr; }\n'
        self.assertEqual(after.count(added), 1)
        self.assertEqual(after.replace(added, ''), before)

    def test_iq1m_and_all_float_recurrence_tail_unchanged(self):
        rel = 'src/kernels/cpu/iq_avx2.cpp'
        before = (HERE / 'base' / rel).read_text()
        after = (HERE / 'candidate' / rel).read_text()
        start = '// IQ1_M follows'; end = '// ---- one token'
        self.assertEqual(before.split(start)[1].split(end)[0], after.split(start)[1].split(end)[0])
        start = '                    acc[t][h & 1] ='
        end = '// ggml\'s unpack'
        self.assertEqual(before.split(start)[1].split(end)[0], after.split(start)[1].split(end)[0])

    def test_no_new_pdep_cpuid_or_runtime_option(self):
        rel = 'src/kernels/cpu/iq_avx2.cpp'
        before = (HERE / 'base' / rel).read_text()
        after = (HERE / 'candidate' / rel).read_text()
        for text in ('std::getenv', 'pdep64', '<cpuid.h>', 'Sc8Tab'):
            self.assertEqual(after.count(text), before.count(text))
        self.assertIn('constexpr Sc16Tab sc16_4;', after)

    def test_exact_upstream_iq2xs_hunks_only(self):
        import re
        patch_file = HERE.parent / 'adaptive-expert-cache-v1/upstream-PR623-files-20261031T0438.json'
        patch = next(f['patch'] for f in json.loads(patch_file.read_text())
                     if f['filename'] == 'src/kernels/cpu/iq_avx2.cpp')
        reconstructed = (HERE / 'base/src/kernels/cpu/iq_avx2.cpp').read_text()
        selected = []
        for chunk in re.split(r'(?=^@@ )', patch, flags=re.M)[1:]:
            start = int(re.match(r'@@ -(\d+)', chunk).group(1))
            if start not in (57, 221, 240, 275, 629):
                continue
            selected.append(start)
            lines = chunk.splitlines(keepends=True)[1:]
            old = ''.join(x[1:] for x in lines if x.startswith((' ', '-')))
            new = ''.join(x[1:] for x in lines if x.startswith((' ', '+')))
            if not old.endswith('\n'):
                old += '\n'; new += '\n'
            self.assertEqual(reconstructed.count(old), 1)
            reconstructed = reconstructed.replace(old, new, 1)
        self.assertEqual(selected, [57, 221, 240, 275, 629])
        reconstructed = reconstructed.replace('constexpr, as sc8_3: this TU is', 'constexpr: this TU is')
        self.assertEqual(reconstructed, (HERE / 'candidate/src/kernels/cpu/iq_avx2.cpp').read_text())


if __name__ == '__main__':
    unittest.main()
