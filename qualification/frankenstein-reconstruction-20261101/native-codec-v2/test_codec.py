"""Independent original-FP4 to ggml-MXFP4 layout and safety checks, all roles."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent


def reference(weights, scales):
    output = bytearray()
    for block, scale in enumerate(scales):
        codes = []
        for value in weights[block * 16:(block + 1) * 16]:
            codes.extend([value & 15, value >> 4])
        output.append(scale)
        output.extend(codes[i] | (codes[i + 16] << 4) for i in range(16))
    return bytes(output)


class NativeCodec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = Path(shutil.which('c++')).resolve()
        cls.exe = HERE / ('mxpack-FIRST-' + sys.platform)
        assert not cls.exe.exists() and not cls.exe.is_symlink(), 'Preserve converter artifact'
        argv = [str(compiler), '-std=c++17', '-O2', str(HERE / 'mxpack.cpp'), '-o', str(cls.exe)]
        result = subprocess.run(argv, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        cls.artifact = {'compiler': str(compiler), 'argv': argv, 'returncode': result.returncode,
                        'converter_sha256': hashlib.sha256(cls.exe.read_bytes()).hexdigest(),
                        'source_sha256': hashlib.sha256((HERE / 'mxpack.cpp').read_bytes()).hexdigest()}
        with (HERE / ('compile-FIRST-' + sys.platform + '.json')).open('x') as f:
            json.dump(cls.artifact, f, indent=2); f.write('\n')

    def codec(self, rows, k, data, *, args=None):
        return subprocess.run([str(self.exe), *(args if args is not None else ['--rows', str(rows), '--k', str(k)])],
                              input=data, capture_output=True, timeout=20)

    def geometry(self, rows, k):
        blocks = rows * k // 32
        weights = (bytes(range(256)) * ((blocks * 16 + 255) // 256))[:blocks * 16]
        scales = (bytes(range(255)) * ((blocks + 254) // 255))[:blocks]
        result = self.codec(rows, k, weights + scales)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b'')
        self.assertEqual(len(result.stdout), blocks * 17)
        self.assertEqual(hashlib.sha256(result.stdout).digest(), hashlib.sha256(reference(weights, scales)).digest())

    def test_full_gate_up_original_geometry(self):
        self.geometry(2304, 5120)

    def test_full_down_original_geometry(self):
        self.geometry(5120, 2304)

    def test_all_nibbles_and_finite_scale_bytes(self):
        weights, scales = bytes(range(256)) * 16, bytes(range(255)) + b'\0'
        result = self.codec(256, 32, weights + scales)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, reference(weights, scales))

    def test_multiple_rows_and_block_boundaries(self):
        for rows, k in ((1, 32), (2, 64), (7, 128), (13, 256)):
            self.geometry(rows, k)

    def test_effective_fp4_e8m0_values_unchanged(self):
        original = [0, .5, 1, 1.5, 2, 3, 4, 6, 0, -.5, -1, -1.5, -2, -3, -4, -6]
        ggml = [0, 1, 2, 3, 4, 6, 8, 12, 0, -1, -2, -3, -4, -6, -8, -12]
        weights, scales = bytes(range(16)) * 6, bytes([0, 1, 126, 127, 128, 254])
        result = self.codec(6, 32, weights + scales)
        self.assertEqual(result.returncode, 0)
        for block, exponent in enumerate(scales):
            for i in range(32):
                a = (weights[block * 16 + i // 2] >> (4 * (i % 2))) & 15
                b = (result.stdout[block * 17 + 1 + i % 16] >> (4 * (i // 16))) & 15
                self.assertEqual(a, b)
                self.assertEqual(math.ldexp(original[a], exponent - 127), math.ldexp(ggml[b], exponent - 128))

    def test_nan_scale_refused_before_output(self):
        result = self.codec(2, 32, b'\0' * 32 + b'\x7f\xff')
        self.assertEqual(result.returncode, 4)
        self.assertEqual(result.stdout, b'')

    def test_incomplete_and_overlong_source_never_emitted(self):
        for data in (b'', b'\0' * 15, b'\0' * 16, b'\0' * 18):
            result = self.codec(1, 32, data)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(result.stdout, b'')

    def test_invalid_geometry_refused_before_read(self):
        for rows, k in ((0, 32), (5121, 32), (1, 0), (1, 31), (1, 5121), (-1, 32), (1, -32), ('99999999999999999999', 32)):
            result = self.codec(rows, k, b'')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b'')

    def test_wrong_argument_names_and_trailing_junk_refused(self):
        for args in (['--other', '1', '--k', '32'], ['--rows', '1x', '--k', '32'], ['--rows', '1', '--k', '32', 'extra']):
            result = self.codec(1, 32, b'', args=args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b'')


if __name__ == '__main__':
    unittest.main(verbosity=2)
