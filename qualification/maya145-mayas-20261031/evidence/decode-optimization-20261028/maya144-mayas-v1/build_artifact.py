"""Independent saved-build completion audit. Never builds, retries or changes hosting.

The original supervisor rc1 remains a failure. Only its post-build progress-file
observer defect is classified here; this is no GPU/model qualification.
"""
import hashlib
import json
from pathlib import Path

P = '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/maya144-mayas-v1/'
Q = '58fd0cc88f53bf0c329690548dbff8635e084d58bdb80aee91af3193c056e3e9'
MUTABLE = P + 'native-build-r2-FIRST/CMakeFiles/Progress/count.txt'
NATIVE = '6c25ea8ab364ae52e306b3e8aeea2a30708252eb943bfea6e79519c3dd21aed7'
CPU = 'd5e443b5b0e5135fe2ab41c366d35732e86dcfc0ccc44628bd2484f757b7d059'
ERROR = "ValueError('Pinned input changed: " + MUTABLE + "')"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def validate(s):
    require(s['qualification_sha256'] == Q and s['pins'] == 5768 and s['verified_unchanged'] == 5767,
            'Exact original build input inventory required')
    require(s['differences'] == [{'path': MUTABLE, 'before':
            '90d7ec0f0acef104d8b6252794295f661a0149634868d02a1ae0c358099638f5', 'after': None}],
            'Only the exact removed CMake progress counter may differ')
    c, v = s['child'], s['supervision']
    require(c['argv'] == ['/usr/bin/cmake', '--build', P+'native-build-r2-FIRST', '--target', 'maya-ds4', '--', '-j1']
            and type(c['returncode']) is int and c['returncode'] == 0 and c['error'] is None and c['cleanup'] == []
            and 0 < c['elapsed_seconds'] < 870, 'Actual compiler exit0 and bounded owned cleanup required')
    require(v == {'passed': False, 'owned_claim_released': True, 'error': ERROR},
            'Preserve the original failed supervision without regrading')
    require(s['active_cpu_build'] is False and s['owned_group_members'] == [], 'Owned CPU closure required')
    require(s['cmake_terminal_progress_command'] == '\t$(CMAKE_COMMAND) -E cmake_progress_start '+P+'native-build-r2-FIRST/CMakeFiles 0',
            'Actual pinned Makefile terminal progress cleanup required')
    require(s['outputs'] == {'maya-ds4': {'sha256': NATIVE, 'bytes': 44669336, 'magic': '7f454c46'},
            'libstrata_kernels_cpu.a': {'sha256': CPU, 'bytes': 4206302, 'magic': '213c617263683e0a'}},
            'Exact independently observed ELF and rebuilt CPU archive required')
    return {'passed': True, 'scope': 'Independent build artifact completion only',
            'compiler_exit': 0, 'original_supervision_regraded': False,
            'classification': 'post-build observer defect: mutable CMake progress count pinned as immutable input',
            'native_sha256': NATIVE, 'new_CPU_archive_sha256': CPU,
            'GPU_or_model_qualified': False, 'production_changed': False}


def inspect(root):
    root = Path(root)
    require(str(root)+'/' == P, 'Exact physical Ubuntu artifact root')
    qpath = root/'compile-r4-qualification.json'
    require(digest(qpath) == Q, 'Original qualification changed')
    q = json.loads(qpath.read_text()); differences = []
    for name, pin in q['files'].items():
        p = Path(name)
        require(p.is_absolute() and p.resolve() == p and not p.is_symlink(), 'Pinned input alias')
        after = digest(p) if p.is_file() else None
        if after != pin: differences.append({'path': name, 'before': pin, 'after': after})
    state = json.loads((root.parents[1]/'STATE.json').read_text())
    child = json.loads((root/'compile-r4-FIRST/child.json').read_text())
    members = []
    for p in Path('/proc').iterdir():
        if not p.name.isdecimal(): continue
        try:
            fields = (p/'stat').read_text().rsplit(') ',1)[1].split()
            if int(fields[2]) == child['pid']: members.append(int(p.name))
        except FileNotFoundError: pass
    make = (root/'native-build-r2-FIRST/Makefile').read_text().splitlines()
    terminal = '\t$(CMAKE_COMMAND) -E cmake_progress_start '+P+'native-build-r2-FIRST/CMakeFiles 0'
    require(terminal in make, 'Actual progress terminal command missing')
    outputs = {}
    for name, size in [('maya-ds4',4), ('libstrata_kernels_cpu.a',8)]:
        p = root/'native-build-r2-FIRST'/name
        require(p.is_file() and not p.is_symlink(), 'Artifact absent or alias')
        with p.open("rb") as stream: magic = stream.read(size).hex()
        outputs[name] = {'sha256':digest(p),'bytes':p.stat().st_size,'magic':magic}
    return {'qualification_sha256':Q, 'pins':len(q['files']), 'verified_unchanged':len(q['files'])-len(differences),
        'differences':differences,'child':child,'supervision':json.loads((root/'compile-r4-FIRST/supervision.json').read_text()),
        'active_cpu_build':state.get('active_cpu_build'),'owned_group_members':sorted(members),
        'cmake_terminal_progress_command':terminal,'outputs':outputs}
