"""Portable source-custody gate; does not compile or import candidate code."""
import hashlib
from pathlib import Path

BASE = {
    'src/ds4/ds4_iq_cpu.cpp': '7894f430fdfb48ba030ee9aff21414833e7f498052d322aeb33b53655da6118a',
    'src/kernels/cpu/native_expert.cpp': '29c706324adaf639e553f266bda6ca1c0c6d755746622e1e80f0af0dbafa3de4',
    'src/kernels/cpu/iq_avx2.cpp': 'e4dddd81e6c657d677fff4f92c8a1167f0634ed323301ec2396bf30f231b81d4',
    'include/strata/kernels/cpu/native_expert.hpp': 'c22c92c0d18a6c045f9534d52b8cad51a8c8f25c58b2e138991d1708a9cdd050',
    'include/strata/kernels/cpu/iq_avx2.hpp': '878cafbeef8144fd4e0b48f492f4812985ab4544dfb06c14523903a46821cd74',
}
CANDIDATE = {
    'src/kernels/cpu/iq_avx2.cpp': '0f2151cd0b1e4a77467e132ba92d2cea626f92fd079508ef393c5622b2d71edb',
    'src/kernels/cpu/native_expert.cpp': '614191b7aef3bf15dacb3b04c8ef5a1b390b8a28ffbb13e2195430c5f0be3120',
    'include/strata/kernels/cpu/native_expert.hpp': 'af881c474d3896b996de8068f7aaed6918ac2f303172c55d59d663a40cb2ac0e',
    'include/strata/kernels/cpu/iq_avx2.hpp': '669943775b48a05f87ff5984dd1c05df94185d7a7f73e693c830df67b9bc71c7',
}


def inventory(root, expected):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Owned regular source tree required')
    files = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Source alias refused')
        if path.is_file():
            if path.stat().st_nlink != 1:
                raise ValueError('Source hardlink refused')
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif not path.is_dir():
            raise ValueError('Nonregular source refused')
    if files != expected:
        raise ValueError('Exact source inventory mismatch')
    return files


def source_contract(root):
    """Only a metadata gate. Success is not numerical, build, or model admission."""
    root = Path(root)
    return {'base': inventory(root / 'base', BASE),
            'candidate': inventory(root / 'candidate', CANDIDATE)}
