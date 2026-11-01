"""Compile/run actual native routing helpers without CUDA or model weights."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'CUDA_VISIBLE_DEVICES': '',
       'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1'}


class NativeRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = HERE / ('routing-FIRST-' + sys.platform)
        assert not cls.exe.exists()
        r = subprocess.run(['/usr/bin/c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-I', str(HERE), str(HERE / 'routing_fixture.cpp'), '-o', str(cls.exe)],
                           capture_output=True, text=True, timeout=30, env=ENV)
        with (HERE / ('compile-FIRST-' + sys.platform + '.json')).open('x') as f:
            json.dump({'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}, f, indent=2)
        assert r.returncode == 0, r.stderr

    def check(self, control):
        r = subprocess.run([str(self.exe), str(control)], capture_output=True, timeout=5, env=ENV)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_mixed_native_iq_preserves_slots_tokens_all_roles_and_source(self): self.check(0)
    def test_all_native_entries(self): self.check(1)
    def test_all_ordinary_entries(self): self.check(2)
    def test_cpu_rows_are_trailing_without_streamed_holes(self): self.check(3)
    def test_all_cpu_prompt_rows(self): self.check(4)
    def test_all_gpu_streamed_prompt_rows(self): self.check(5)
    def test_speculative_prefix_preserved(self): self.check(6)

    def test_descriptor_parser_is_the_previously_qualified_implementation(self):
        old = (HERE.parent / 'native-lane-v1/cpu_native_plan.hpp').read_text()
        new = (HERE / 'ds4_cpu_native.hpp').read_text()
        a = old[old.index('class Plan {'):old.index('} // namespace s2native')]
        b = new[new.index('class Plan {'):new.index('// Copy entries')]
        self.assertEqual(a.rstrip(), b.rstrip())

    def test_invalid_fixture_control_fails_without_success(self):
        r = subprocess.run([str(self.exe), '99'], capture_output=True, timeout=5, env=ENV)
        self.assertEqual(r.returncode, 2)


if __name__ == '__main__': unittest.main()
