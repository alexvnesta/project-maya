"""Prospective D0 then separately admitted A2, with no automatic promotion.

Source only until ROOT has read all three files and qualified their focused CPU
controls on both physical hosts. All artifact/placement/admission pins are future
inputs; this module deliberately supplies no qualification or admission receipt.
Generated code is saved for a full manual read and a separate CPU-only grader.
The unchanged pinned API does not publish OpenAI logprobs; no unsupported LP
request or numerical-equivalence claim is made. Arithmetic gates are actual
GPU Q8/projection startup checks and original-native CPU finite bitmatches.
"""
import argparse
import array
import copy
import datetime
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
Q = HERE.parent
DC = Q.parent
E = DC.parent
R = E.parent
D = Path('/home/alex/deepseek-hosted-20261025')
P2 = Q / 'placement-v2/placement.py'
BASE_SHA = 'c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa'
BASE_NATIVE = '92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1'
PANEL_SHA = '7fd8da9db5ebc42ab67c5d1f07d7f9300b214a101f16fd2749dd7a8c9a760034'
WINDOW_SHA = '170722b54e0245e7268bffe2f39f8e30bee2fc79c056544f4f9b03942c48f25f'
DRIVER_SHA = '3cbcf0ce9e000035c893d033b2a6fe09e8d555a831d12a08681f5fdbb0de6b71'
SELECTED92_SOURCE = {'ds4_main.cpp': '1efa69ff5e2b7615b4f522bd695e0feecf5849df6e070eeb35cc9f900a92a2da',
                     'ds4_model.cu': 'dfe326d6a60d77354c8c92fb14ec423a92afff76b91f0810104f0a54a51a6350'}
SOURCES = ('runtime.py', 'ram_runtime.py', 'ram_controls.py', 'test_runtime.py', 'test_ram.py', 'run_cpu.py')
MODE = 's2-essential4'
RUNNING = 'S2_ESSENTIAL4_PRIVATE_RUNNING'
COMPLETE = 'S2_ESSENTIAL4_SELECTED4096_RESTORED'
PHASE_KEYS = ('active_private_phase', 'active_GPU_phase', 'active_gpu_experiment', 'private_window',
              'active_cpu_build', 'production_restore_in_progress', 'production_verification_pending',
              'production_temporarily_stopped')
CPU_ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
           'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1',
           'PYTHONDONTWRITEBYTECODE': '1', 'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}


def require(ok, why):
    if not ok: raise ValueError(why)


def packed(row): return json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def digest(row): return hashlib.sha256(packed(row)).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(2**20), b''): h.update(block)
    return h.hexdigest()


def fingerprint(path):
    p = Path(path)
    require(p.is_absolute() and p.resolve() == p and not p.is_symlink() and p.is_file(), 'Real absolute input')
    s = p.stat(); require(s.st_nlink == 1, 'No input hardlink alias')
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def emit(path, value):
    path = Path(path); require(path.parent.resolve() == path.parent and not path.is_symlink(), 'Owned real receipt')
    temp = path.with_name(path.name + '.tmp'); require(not temp.exists() and not temp.is_symlink(), 'Preserve residue')
    with temp.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
    temp.replace(path)


def exact(name, path, pin):
    fingerprint(path); require(sha(path) == pin, 'Exact helper source: ' + name)
    old = sys.modules.get(name)
    require(old is None or Path(old.__file__).resolve() == path, 'Foreign cached module: ' + name)
    if old is not None: return old
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    try: spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]; raise
    return module


def panel(): return exact('s2_essential_panel', Q / 'essential-panel-v1/panel.py', PANEL_SHA)


def prerequisite(arm, registry, closure=None):
    require(arm in ('D0', 'A2') and type(registry) is dict and arm not in registry, 'Fresh explicit arm, no replay')
    require(set(registry) == (set() if arm == 'D0' else {'D0'}), 'D0 first; separate A2 admission only')
    if arm == 'A2':
        require(type(closure) is dict and closure.get('arm') == 'D0' and closure.get('fully_manually_read') is True and
                closure.get('source_numerical_core_passed') is True and closure.get('natural_two_tasks_passed') is True and
                closure.get('independent_code_grade_passed') is True and closure.get('prose_facts_accepted') is True and
                closure.get('owned_execution_closed') is True and closure.get('selected_restored') is True and
                closure.get('output') == registry['D0']['output'] and closure.get('promotion_performed') is False,
                'Candidate full independent acceptance/restoration required before baseline')


def paths(output, arm, present=False):
    output = Path(output)
    require(arm in ('D0', 'A2') and output.parent == E / 'results' and
            re.fullmatch('s2-essential4-' + arm + r'-\d{8}T\d{6}Z', output.name), 'Fresh essential namespace')
    meta = E / 'maintenance' / output.name
    for p in (output.parent, meta.parent): require(p.is_dir() and p.resolve() == p, 'Real existing parents')
    require(not output.is_symlink() and not meta.is_symlink() and
            (output.is_dir() if present else not output.exists()), 'Fresh/present private output')
    return output, meta


def cpu_contract(proof, child, review, platform):
    require(proof.get('passed') is True and proof.get('returncode') == 0 and
            proof.get('failures') == proof.get('errors') == 0 and
            proof.get('source_map') == review['source_map'] and proof.get('input_map') == review['input_map'] and
            proof.get('test_ids') == review['test_ids'] and len(set(review['test_ids'])) == len(review['test_ids']) > 0 and
            proof.get('controls') == len(review['test_ids']), 'Exact complete focused CPU controls')
    observed = proof['observed']
    require(observed['platform'] == platform and observed['cpu'] == [30, 30] and observed['nice'] == 15 and
            observed['as'] == ([512*2**20]*2 if platform == 'linux' else None) and
            observed['pid'] == observed['pgid'] == child['pid'] and observed['ppid'] == proof['supervisor_pid'] and
            observed['dont_write_bytecode'] is True and observed['environment'] ==
            {k: CPU_ENV[k] for k in ('CUDA_VISIBLE_DEVICES', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                                   'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'MALLOC_ARENA_MAX', 'PYTHONDONTWRITEBYTECODE')} and
            proof.get('isolated') is True and child.get('returncode') == 0 and child.get('error') is None and
            child.get('cleanup') == [] and 0 <= child['elapsed_seconds'] <= 90, 'Actual bounded isolated physical CPU child')


def asset_contract(q, validate):
    """Published acquisition bytes and newly built bytes have distinct evidence.

    validate is prospective ROOT-owned, source/CPU-qualified chain code, NOT a
    generic passed.json reader. It must validate exact raw controller exits,
    acquisition/construct or join/finalize groups, postpublication fingerprints
    and actual owned writer-lock freedom. This adapter never rehashes347GB.
    """
    chains, assets = q['artifact_chains'], q['large_verified']
    require(chains and assets, 'Actual publication/build chains required')
    for key, group in chains.items():
        require(group['kind'] in ('base-acquisition-publication', 'selected-publication',
                                 'bounded-overlay-join', 'bounded-native-finalize') and
                group['raw_paths'] and len(set(group['raw_paths'])) == len(group['raw_paths']) and
                all(p in q['files'] for p in group['raw_paths']), 'Pinned exact raw terminal/build group')
        if group['kind'] == 'base-acquisition-publication':
            mp, tp = Q/'base-acquisition-v2/ASSET_MANIFEST.json', Q/'base-acquisition-v2/acquisition-state.json'
            require(str(mp) in group['raw_paths'] and str(tp) in group['raw_paths'] and
                    q['files'][str(mp)] == '22ecce3e7085e29520fadaa67d603beb8cc0905f834ff3563029f6038825034b',
                    'Exact published ALL8 manifest/terminal, no replacement full-hash demand')
            manifest, terminal = json.loads(mp.read_text()), json.loads(tp.read_text())
            require(manifest['repo'] == 'peasantsmith/DeepSeek-V4.1-Flash-1017-Maya-GGUF' and
                    manifest['revision'] == 'd1fc01009f21e26157acb6858c315d0365483b72' and
                    manifest['total_bytes'] == 347445667721 and len(manifest['files']) == len(terminal['files']) == 8 and
                    sum(spec['size'] for spec in manifest['files']) == manifest['total_bytes'] and
                    terminal['status'] == 'ALL_EIGHT_ASSETS_VERIFIED_NO_MODEL_RUN' and terminal['returncode'] == 0 and
                    terminal['manifest_sha256'] == q['files'][str(mp)] and
                    terminal['asset_root'] == str(Q/'base-acquisition-v1/assets'), 'Actual streamed-published ALL8 chain')
            for row, spec in zip(terminal['files'], manifest['files']):
                name = str(Q/'base-acquisition-v1/assets'/spec['path'])
                require(row['path'] == spec['path'] and row['status'] in ('VERIFIED_EXISTING','DOWNLOADED_VERIFIED') and
                        row['bytes'] == spec['size'] and row['sha256'] == spec['sha256'] and
                        name in assets and assets[name]['chain'] == key and assets[name]['sha256'] == spec['sha256'] and
                        assets[name]['fingerprint'][2] == spec['size'], 'Exact published LFS SHA/size and actual final fingerprint')
    # The validator receives the exact reviewed group schema and pin map. Its
    # return is derived evidence, not an independently trusted summary receipt.
    actual = validate(publication_context(q))
    require(set(actual) == set(assets), 'Exact asset closure from qualified chain validator')
    for name, expected in assets.items():
        require(expected['chain'] in chains and actual[name] == {
            'chain': expected['chain'], 'sha256': expected['sha256'], 'fingerprint': expected['fingerprint'],
            'raw_paths': chains[expected['chain']]['raw_paths'], 'owned_writer_lock_free': True} and
            fingerprint(name) == expected['fingerprint'], 'Stable exact published/built artifact, writer closed')


def publication_context(q):
    # Original immutable asset-publication binding remains historical. The
    # current action-time owner is separately q['selected_binding'] and is
    # checked against the actual unit/native before drain and at every phase.
    binding = q['publication_selected_binding']
    require(type(binding) is dict and set(binding) == {'invocation','main_pid','native_pid','native_start_ticks'} and
            type(binding['invocation']) is str and re.fullmatch('[0-9a-f]{32}', binding['invocation']) and
            all(type(binding[k]) is int and binding[k] > 1 for k in ('main_pid','native_pid','native_start_ticks')),
            'Exact original publication owner binding')
    return dict(q, selected_binding=copy.deepcopy(binding))


def qualified(pin, arm):
    path = HERE / 'qualification.json'; require(sha(path) == pin, 'Exact future qualification')
    q = json.loads(path.read_text())
    require(q['mode'] == MODE and q['root_entire_source_tests_driver_read'] is True and
            q['policy'] == {'context': 1048576, 'output': 262144, 'effort': 100, 'cap': 32768,
                            'chunk': 4096, 'cpu_threads': 24, 'static_tp': 1, 'all_cpu_RAM': True} and
            q['old_arms_closed'] is True and q['prospective_owned_restore_qualified'] is True and
            q['weight_materialization_closed'] is True and q['all_bulk_source_workers_closed'] is True,
            'Full capacity/source/closure/recovery qualification')
    require(q['memory_policy'] == {'private_max': 88*2**30, 'host_reserve': 4*2**30, 'post_stop_floor': 92*2**30, 'private_swap': 0}, 'Explicit user-authorized host memory policy')
    for name, pin0 in q['files'].items():
        require(fingerprint(name)[2] <= 512*2**20 and sha(name) == pin0, 'Exact source/binary/proof input: ' + name)
    required = {str(HERE / n): sha(HERE / n) for n in SOURCES}
    required.update({str(Q / 'essential-panel-v1/panel.py'): PANEL_SHA,
                     str(D / 'config.json'): BASE_SHA, str(R / 'window.py'): WINDOW_SHA})
    require(all(q['files'].get(n) == v for n, v in required.items()), 'Required source/config/window pins')
    review = json.loads(Path(q['CPU_review']).read_text())
    require(review['entire_source_tests_driver_manually_read'] is True and
            review['source_map'] == {n: sha(HERE / n) for n in SOURCES} and
            review['input_map'] == {'qualified_supervisor': DRIVER_SHA, 'essential_panel': PANEL_SHA,
                'original_controls': '1038fad719fb7ed7516ab3e07d88d40fb3b5cd7408f6ed19ddc2296f13052cf5',
                'original_runtime': '1811228e83217b961ae4ffed9c430f49edf10c3af999b4fd6753518a25001e58',
                'native_helper': sha(Q/'native-engine-v3/ds4_cpu_native.hpp')}, 'Manual source/input review binding')
    require(str(q['CPU_review']) in q['files'] and set(q['CPU']) == {'darwin', 'linux'}, 'Pinned both physical CPU chains')
    for platform, paths0 in q['CPU'].items():
        require(set(paths0) == {'receipt', 'child', 'log'} and all(n in q['files'] for n in paths0.values()), 'Raw CPU proofs pinned')
        cpu_contract(json.loads(Path(paths0['receipt']).read_text()), json.loads(Path(paths0['child']).read_text()), review, platform)
    validator = q['artifact_chain_validator']
    require(validator['path'] in q['files'] and validator['both_physical_CPU_qualified'] is True and
            validator['source_and_raw_group_schema_manually_read'] is True and
            validator['qualification_path'] in q['files'] and validator['raw_CPU_paths'] and
            all(p in q['files'] for p in validator['raw_CPU_paths']), 'Prospective source-qualified raw-chain validator')
    chain = exact('s2_essential_publication_chain', Path(validator['path']), q['files'][validator['path']])
    asset_contract(q, chain.validate_publications)
    profile = q['profiles'][arm]
    require(q['profiles']['A2']['native_sha256'] == BASE_NATIVE and
            q['profiles']['A2']['exe'] == str(D / 'bin/maya-ds4') and
            q['profiles']['D0']['exe'] == str(Q / 'native-build-v3/native-build-FIRST/maya-ds4') and
            q['profiles']['D0']['pack'] == str(Q / 'candidate-pack-v1/pack-FIRST'), 'Exact selected/candidate source families')
    for f in q['profiles'].values():
        require(q['files'].get(f['exe']) == f['native_sha256'] and f['manifest'] in q['files'] and
                f['manifest_CPU_encoding_actual_pack_qualified'] is True and f['pack_constructor_proof'] in q['files'] and
                f['asset_paths'] and all(n in q['large_verified'] for n in f['asset_paths']),
                'Exact executable/actual-pack constructor/assets/encoded fixtures')
    b = q['profiles']['D0']; native = q['large_verified'][b['native_payload']]
    require(native['sha256'] == b['native_artifact_sha256'] and native['fingerprint'][2] == 35157299200 and
            q['native_payload_source_three_role_CPU_qualified'] is True and q['actual_P0_selection_frozen'] is True and
            b['map_path'] in q['files'], 'Original1870 full3role payload/map/source prequalification')
    require(q['artifact_chains'][native['chain']]['kind'] == 'bounded-native-finalize' and
            q['artifact_chains'][q['large_verified'][b['overlay_path']]['chain']]['kind'] == 'bounded-overlay-join',
            'New native/overlay keep actual bounded finalize/join proofs')
    if arm == 'A2':
        require(q['D0_closure'] in q['files'], 'Independently pinned D0 closure')
        oldroot = DC/'maya145-formal-prefill-v1/selected92-source'
        lineage = DC/'iq2s-persistent-v1/gpu-qualification.json'
        require(q['files'].get(str(lineage)) == 'cd146a86438054e664b6dfb953341fc65ecb34d9ab6d9d22851009c239713580',
                'Selected92 exact qualified source/binary lineage')
        oldproof = json.loads(lineage.read_text())
        for name, pin0 in SELECTED92_SOURCE.items():
            require(q['files'].get(str(oldroot/name)) == pin0 and
                    oldproof['files'].get(str(R/'maya-ablate469-v2/src/ds4'/name)) == pin0,
                    'Exact selected92 source check, distinct from newer native145')
        require(oldproof['files'].get(str(D/'bin/maya-ds4')) == BASE_NATIVE,
                'Selected92 source belongs to exact selected binary')
        adapter = q['profiles']['A2']['startup_adapter']
        require(adapter in q['files'] and q['profiles']['A2']['startup_adapter_CPU_source_qualified'] is True,
                'Prospective pinned actual-baseline startup adapter; no newnative parser assumption')
    require(sha(path) == pin, 'Qualification stable through checks')
    return q


def helpers(q):
    # placement-v2 is a FUTURE reviewed dependency. Its support() must own the
    # exact transitive origin/hash checks identified in the placement-v1 review.
    import_origins(q)
    p2 = exact('s2_essential_placement2', P2, q['files'][str(P2)])
    a, old, base, legacy, startup, fence = p2.support()
    root = DC / 'maya-s-comparison-v1'
    for name, relative in (('pv_runtime', 'performance-v2/pv_runtime.py'),
                           ('pv_controls', 'performance-v2/pv_controls.py'),
                           ('ms_fixtures', 'model-v1/ms_fixtures.py')):
        exact(name, root / relative, q['files'][str(root / relative)])
    pv, controls, fixtures = (sys.modules[n] for n in ('pv_runtime', 'pv_controls', 'ms_fixtures'))
    statdir = DC / 'adaptive-expert-cache-v1/performance-v1'
    for name in ('ae_config', 'ae_runtime', 'ae_controls'):
        exact(name, statdir / (name + '.py'), q['files'][str(statdir / (name + '.py'))])
    import_origins(q)
    # Original modules stay immutable. New memory policy and fence are local to this new mode.
    ram = exact('ram_runtime', HERE/'ram_runtime.py', q['files'][str(HERE/'ram_runtime.py')])
    owned = exact('s2_ram_controls', HERE/'ram_controls.py', q['files'][str(HERE/'ram_controls.py')])
    require(owned.runtime is ram and ram.MEMORY_MAX == q['memory_policy']['private_max'] and
            ram.HOST_MARGIN == q['memory_policy']['host_reserve'], 'Exact new fence/policy object binding')
    return p2, a, old, base, legacy, startup, owned, ram, owned, fixtures, sys.modules['ae_controls']


def import_origins(q):
    # The reviewed qualification enumerates the inherited import closure, rather
    # than assuming sys.path insertion replaces an already cached module.
    require({'pv_runtime', 'pv_config', 'pv_controls', 'ae_runtime', 'ae_config', 'ae_controls',
             'imma_config', 'imma_fixtures', 'imma_storage', 'protocol', 'skip_controls', 'q8_phase'} <=
            set(q['import_origins']), 'Explicit prospective inherited import closure')
    for name, path in q['import_origins'].items():
        require(path in q['files'] and sha(path) == q['files'][path], 'Pinned transitive import source')
        module = sys.modules.get(name)
        require(module is None or Path(getattr(module, '__file__', '')).resolve() == Path(path), 'Foreign cached helper: ' + name)


def native_env(env): return {k: v for k, v in env.items() if k.startswith(('DS4_', 'STRATA_DS4_', 'MAYA_DS4_'))}


def make_config(base, folder, arm, profile):
    require(arm in ('D0', 'A2') and base['args'].count('--serve') == 1, 'Exact selected serve argument')
    c = copy.deepcopy(base); c.update(exe=profile['exe'], port=18041, log=str(folder / 'engine.log'))
    args = c['args']
    for flag, value in (('--max-context', '1048576'), ('--prefill-chunk', '4096'), ('--dspark', 'on'),
                        ('--cpu-threads', '24'), ('--mmap-experts', 'off'), ('--dspark-conf', '0.65'),
                        ('--ablate-scale', '1'), ('--ablate', str(D / 'runtime-direction-L22.gguf'))):
        require(args.count(flag) == 1 and args[args.index(flag)+1] == value, 'Unchanged policy: ' + flag)
    require(not any(flag in args for flag in ('--cpu-native', '--placement-plan', '--expert-cache', '--profile-out',
                                              '--layer-split', '--ids', '--ssd-cache', '--parallel')),
            'No foreign placement/state/inference mode')
    for flag, value in (('--pack', profile['pack']), ('--expert-profile', str(folder / 'expert-profile.bin'))):
        require(args.count(flag) == 1, 'Unique base option'); args[args.index(flag)+1] = value
    require(args.count('--tp') == 1, 'Unique original TP')
    if arm == 'D0': args[args.index('--tp')+1] = '1'
    require(args[args.index('--tp')+1] == '1', 'StaticTP1 in both explicit profiles')
    require(c['env'].get('DS4_REQUIRE_ALL_RAM') == '1' and c['env'].get('DS4_STREAM') == '0' and
            c['env'].get('DS4_YOCO') == c['env'].get('STRATA_DS4_PROMPT_SKIP') == '1' and
            c['env'].get('STRATA_DS4_Q8_BATCH') == c['env'].get('DS4_Q8_CHECK') == '1', 'Selected Q8/mode1/allRAM')
    forbidden = ('HELPER', 'STORE', 'FLOW', 'COPY_SWAP', 'SERVE_DUMP', 'ROUND_LOG',
                 'DENSE_REQ', 'RAM_TIER', 'RAM_GB', 'STREAM_GB', 'DRAFT_VRAM')
    effective = native_env(c['env'])
    require(not any(any(part in key for part in forbidden) for key in effective if not key.endswith('LT_STORE')) and
            all(value == '0' for key, value in effective.items() if 'SKIP_W' in key or 'SKIP_AUTO' in key),
            'No skip/drop/helper/tier/dump factors')
    for key, tail in (('STRATA_DS4_SLOT_DIR', 'cache'), ('DS4_LANE_CAL', 'lane.txt'), ('DS4_LT_STORE', 'lt.txt')):
        c['env'][key] = str(folder / tail)
    if '--verbose' not in args: args.append('--verbose')
    if arm == 'D0':
        args += ['--profile-readonly', '--profile-out', str(folder / 'routing.bin')]
        c.update(tokenizer=str(Path(profile['pack']) / 'tokenizer'))
        c['env']['DS4_COPY_DIRECT'] = '1'
        args += ['--no-expert-cache', '--cpu-native', profile['native_payload'],
                 '--cpu-native-map', profile['native_map_sha256'], '--cpu-native-identity', profile['native_artifact_sha256']]
    return c


def process_contract(c, argv, env, cgroup, same):
    require(same is True and argv == [c['exe'], '--serve', *c['args'], '--layer-split', 'auto', ''] and
            native_env(env) == native_env(c['env']) and 'strata-deepseek-window.service' in cgroup.strip().split('/'),
            'Actual executable/argv/effective native environment/owned cgroup')
    return {'actual_argv': argv, 'actual_native_env': native_env(env), 'same_executable': True, 'cgroup': cgroup}


def profile_snapshot(path):
    path = Path(path)
    if not path.exists(): return [0] * (43*384)
    raw = path.read_bytes(); require(len(raw) == 43*384*4, 'Exact trunk plus three-drafter run-only profile')
    out = array.array('I'); out.frombytes(raw)
    if sys.byteorder != 'little': out.byteswap()
    return list(out)


def profile_generation(path):
    path = Path(path)
    if not path.exists(): return None
    s = path.stat(); return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def saved_profile(path, previous, *, clock=time.monotonic, pause=time.sleep):
    # Native DONE is flushed before save_profile(). Observe its atomic rename,
    # rather than accidentally attributing the preceding request's old file.
    deadline = clock()+5
    while profile_generation(path) == previous:
        require(clock() < deadline, 'Run-only profile was not saved after this request')
        pause(.02)
    before = profile_generation(path); out = profile_snapshot(path)
    require(profile_generation(path) == before, 'Profile changed while snapshotted')
    return out


def participation(before, after, selected, slots):
    require(len(before) == len(after) == 43*384 and len(slots) == 40 and
            all(type(a) is int and type(b) is int and 0 <= a <= b < 2**32 for a, b in zip(before, after)),
            'Exact routing snapshot dimensions; no counter overflow/regression')
    rows = []
    for layer, expert in selected:
        require(0 <= layer < 40 and 0 <= expert < 384 and slots[layer][expert] == -1, 'Selected original CPU-only IDs')
        if not 24 <= layer <= 28: continue
        i = layer*384+expert; require(after[i] >= before[i], 'Run profile counter overflow/regression')
        if after[i] > before[i]: rows.append([layer, expert, after[i]-before[i]])
    return {'sensitive_selected_CPU_hits': rows, 'positive': bool(rows),
            'evidence': 'Source-backed dispatch participation inference under static/no-skip/no-helper flags',
            'direct_native_counter_telemetry': False, 'outside_sensitive_hits_not_counted': True}


def finite_logprobs(response):
    # Pure parser control retained for provenance; pinned API does not supply
    # these fields and this function is NOT an actual essential phase gate.
    values = []
    for event in response.get('events', []):
        for choice in event.get('choices', []):
            for token in (choice.get('logprobs') or {}).get('content') or []:
                values.append(token.get('logprob'))
                values.extend(x.get('logprob') for x in token.get('top_logprobs') or [])
    require(values and all(type(v) in (int, float) and math.isfinite(v) for v in values), 'Finite returned native logprobs required')
    return {'returned_values': len(values), 'finite': True, 'full_vocabulary_or_equivalence_claim': False}


def stat_activity(trace, pid, required=False, candidate=True):
    """Existing exact observer output, distinct from native-specific telemetry."""
    trace = Path(trace); receipt = json.loads((trace / 'stat-receipt.json').read_text())
    require(receipt.get('native_pid') == pid and receipt.get('trace_number') == int(trace.name[-3:]) and
            receipt.get('complete') is True and receipt.get('DONE_observed') is True and
            receipt.get('capture_error') is None and receipt.get('primary_error') is None,
            'Exact complete owned native STAT receipt')
    path = trace / 'stat-lines.jsonl'; require(path.stat().st_size <= 4*2**20, 'Bounded request STAT')
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    require(len(rows) == receipt['samples'] and len(rows) <= 100000, 'Exact STAT samples')
    h = hashlib.sha256(); last = {}; sec = -1.; rounds = -1
    for row in rows:
        raw = row['raw']; require(row['native_pid'] == pid and row['trace_number'] == receipt['trace_number'] and
            type(row['seconds']) in (int, float) and math.isfinite(row['seconds']) and row['seconds'] >= sec and
            type(raw) is str and raw.startswith('STAT ') and len(raw) <= 4096 and '\n' not in raw and '\r' not in raw,
            'STAT actual identity/clock/line')
        sec = row['seconds']; h.update((raw+'\n').encode()); pairs = [x.split('=', 1) for x in raw.split()[1:]]
        require(all(len(x) == 2 for x in pairs) and len({x[0] for x in pairs}) == len(pairs), 'Unique STAT fields')
        fields = dict(pairs); last = {k: float(fields[k]) for k in (('cpu', 'ram', 'draft_ms', 'verify_ms') if candidate else ('cpu', 'ram'))}
        require(all(math.isfinite(v) and v >= 0 for v in last.values()), 'Finite CPU/RAM activity')
        if candidate:
            require(fields['draft_rounds'].isdecimal() and int(fields['draft_rounds']) >= rounds, 'Native DSpark activity')
            rounds = int(fields['draft_rounds'])
    require(h.hexdigest() == receipt['raw_lines_sha256'], 'Exact observed raw STAT')
    require(not required or (last and last['cpu'] > 0 and last['ram'] > 0 and
                            (not candidate or (rounds > 0 and last['draft_ms'] > 0))),
            'Actual CPU/RAM and DSpark activity required on each timed task')
    return dict(last, draft_rounds=rounds, samples=len(rows), direct_native_counter_telemetry=False)


def expected_cases(fixtures, arm):
    p = panel(); frozen = p.fixture()
    require(arm in ('D0','A2'), 'Explicit essential fixture arm')
    if arm == 'A2':
        # Same final cold recovery/known-answer request immediately before the
        # same two mains. No new-model numerical/image/tool/cancel campaign.
        cases = [dict(fixtures.lifecycle_cases()[-1])]; cases[0].pop('dependency', None)
    else:
        numeric = fixtures.request('Return exactly FINITE and nothing else.')
        urls, _ = fixtures.source_images()
        cases = [{'id': 's2-source-known-answer', 'kind': 'literal', 'request': numeric, 'expected': 'FINITE', 'expected_reuse': 'zero'}]
        cases += fixtures.quality_cases(urls) + fixtures.lifecycle_cases()
    for row in frozen['cases']:
        cases.append({'id': row['id'], 'kind': row['kind'], 'request': row['request'], 'expected_reuse': 'zero'})
    return cases


def fixture_contract(manifest, fixtures, arm='D0'):
    cases = expected_cases(fixtures, arm)
    require(manifest['context_total'] == 1048576 and manifest['output_allowance'] == 262144 and
            len(manifest['cases']) == len(cases), 'Minimal frozen essential schedule')
    for actual, expected in zip(manifest['cases'], cases):
        require(all(actual.get(k) == v for k, v in expected.items()) and
                actual['request_sha256'] == digest(actual['request']) and
                actual['prompt_ids_sha256'] == digest(actual['prompt_ids']) and
                actual['prompt_tokens'] == len(actual['prompt_ids']) and 0 < actual['prompt_tokens'] < 12000 and
                all(type(x) is int and 0 <= x < 129280 for x in actual['prompt_ids']), 'Exact request/source/CPU encoded prompt')
    return manifest['cases']


def phase_proof(output, arm, proofpath, present=False):
    output, meta = paths(output, arm, present)
    require(Path(proofpath) == meta / 'proof.json', 'Exact private proof path')
    proof = json.loads(Path(proofpath).read_text()); state = json.loads((E / 'STATE.json').read_text())
    saved = json.loads((meta / 'state.json').read_text()); active = state['decode_optimization_current']
    reg = json.loads((HERE / 'arms.json').read_text())[arm]
    for row in (proof, saved, active, reg):
        require(row.get('mode') == MODE and row.get('arm') == arm and row.get('output') == str(output) and
                row.get('qualification_sha256') == proof['qualification_sha256'] and
                row.get('controller_pid') == proof['controller_pid'], 'Exact proof/state/registry identity')
    require(saved['status'] == active['status'] == RUNNING and reg['attempted'] is True and
            state['active_private_phase'] == str(meta) and state['maintenance_controller'] == str(meta / 'state.json') and
            state['active_gpu_experiment'] is True and not state.get('active_cpu_build'), 'Exact sole owned phase')
    return proof


def window(old, output, arm, proofpath):
    path, row = old.owned_window()
    expected = [str(R / 'venv/bin/python3.14'), '-B', str(HERE / 'runtime.py'), '--phase', '--arm', arm,
                '--output', str(output), '--proof', str(proofpath)]
    require(row['command'] == expected and row.get('continued_from') and row.get('test_returncode') is None and
            row.get('maintenance_held') is not True and row.get('restored') is False, 'Exact canonical owned window')
    return path


def entry(args):
    folder = Path(args.folder); output = folder.parent; proofpath = E / 'maintenance' / output.name / 'proof.json'
    proof = phase_proof(output, args.arm, proofpath, True); q = qualified(proof['qualification_sha256'], args.arm)
    p2, a, old, base, legacy, startup, fence, pv, controls, fixtures, observer = helpers(q)
    w = window(old, output, args.arm, proofpath)
    path = output / 'candidate-config.json'; require(sha(path) == args.config_sha256, 'Private config hash')
    c = json.loads(path.read_text())
    require(c == make_config(json.loads((D / 'config.json').read_text()), folder, args.arm, q['profiles'][args.arm]), 'Exact whole private config')
    serverpath = D / 'runtime-native-vision-v2/serve/server.py'
    # Check all cached serve submodule origins BEFORE importing the unchanged API.
    for name, module in tuple(sys.modules.items()):
        if name == 'serve' or name.startswith('serve.'):
            origin = Path(getattr(module, '__file__', ''))
            require(origin.is_relative_to(serverpath.parent), 'Foreign private API module')
    sys.path.insert(0, str(serverpath.parent.parent)); server = importlib.import_module('serve.server')
    require(Path(server.__file__) == serverpath and sha(serverpath) == q['files'][str(serverpath)], 'Exact unchanged private API')
    defaults = exact('s2_essential_defaults', D / 'hosting_defaults.py', q['files'][str(D / 'hosting_defaults.py')])
    audit = old.prepare_server(server, c, folder, defaults.install)
    server.StrataEngine = observer.stat_trace_class(server.StrataEngine, folder)
    import_origins(q)
    emit(folder / 'entry-audit.json', dict(audit, server_pid=os.getpid(), owned_window=str(w), config_sha256=args.config_sha256))
    return server.main(['--engine', 'strata', '--config', str(path), '--host', '127.0.0.1', '--port', '18041', '--shutdown-timeout', '60'])


def phase(output, arm, proofpath):
    began = time.monotonic(); proof = phase_proof(output, arm, proofpath); q = qualified(proof['qualification_sha256'], arm)
    p2, a, old, base, legacy, startup, fence, pv, controls, fixtures, observer = helpers(q)
    output = Path(output); window(old, output, arm, proofpath)
    w = old.q8_phase.admission(proof, arm, output, qualification_key='qualified_for_owned_s2_essential')
    manifest = json.loads(Path(q['profiles'][arm]['manifest']).read_text()); cases = fixture_contract(manifest, fixtures, arm)
    output.mkdir(); folder = output / 'native'; folder.mkdir()
    for n in ('cache', 'tmp', 'cuda-cache'): (folder / n).mkdir()
    shutil.copyfile(D / 'profile-seed.bin', folder / 'expert-profile.bin')
    require(sha(folder / 'expert-profile.bin') == old.q8_phase.SEED_SHA, 'Frozen profile seed')
    c = make_config(json.loads((D / 'config.json').read_text()), folder, arm, q['profiles'][arm])
    emit(output / 'candidate-config.json', c); emit(output / 'candidate-config.shared-settings.json', {'max_tokens': 262144})
    emit(output / 'fixtures.json', manifest)
    command = [str(R / 'venv/bin/python3.14'), '-u', '-B', str(HERE / 'runtime.py'), '--entry', '--arm', arm,
               '--folder', str(folder), '--config-sha256', sha(output / 'candidate-config.json')]
    with fence.fenced_phase(output) as (limits, handles):
        with (folder / 'server.log').open('x') as log:
            proc = subprocess.Popen(command, cwd=HERE, env=old.q8_phase.environment(folder, w), stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            handles.append(proc)
            def body():
                emit(output / 'API-start.json', {'pid': proc.pid, 'argv': command})
                ready, health, models = old.q8_phase.wait_startup(proc, folder, began+800)
                pid = ready['pid']; text = (folder / 'engine.log').read_text(errors='replace')
                info = ready['info']
                require(ready['context'] == health['max_context'] == 1048576 and
                        health['loaded'] is True and health['images'] is True, 'Actual full-capacity private endpoint')
                native = Path('/proc') / str(pid)
                env = dict(x.split('=', 1) for x in (native / 'environ').read_bytes().decode().split('\0') if '=' in x)
                actual = process_contract(c, (native / 'cmdline').read_bytes().decode().split('\0'), env,
                                          (native / 'cgroup').read_text(), os.path.samefile(native / 'exe', c['exe']))
                require(sha(c['exe']) == q['profiles'][arm]['native_sha256'], 'Live exact native')
                # The existing source-specific startup parser checks published
                # drafter blocks, projection L22/all40, Q8 and scale policy.
                if arm == 'D0':
                    require(info['kv_resident'] == 1048576 and info['engine_kind'] == 'ds4' and
                            info['cpu_experts'] == info['ram_experts'] > 0 and
                            info['expert_slots'] + info['cpu_experts'] == 15360 and info['cpu_threads'] == 24 and
                            ready['can_stop'] is True and re.findall(r'prompts in chunks of (\d+)', text) and
                            set(re.findall(r'prompts in chunks of (\d+)', text)) == {'4096'} and 'no disk fallback' in text,
                            'Candidate actual allCPU RAM/chunk/native cancel support')
                    parserpath = DC / 'maya145-directstate-v1/engine_profile.py'
                    parser = exact('s2_essential_startup_parser', parserpath, q['files'][str(parserpath)])
                    parsed = parser.startup(text, 'TP1')
                else:
                    parserpath = Path(q['profiles']['A2']['startup_adapter'])
                    parser = exact('s2_essential_selected92_startup', parserpath, q['files'][str(parserpath)])
                    parsed = parser.startup(ready, health, models, text, q['profiles']['A2'])
                if arm == 'D0':
                    require(info.get('native_cpu_experts') == 1870 and info.get('native_cpu_bytes') == 35157196800 and
                            'native CPU check:8 experts,3roles,1/4rows,strided; original MXFP4 path bit for bit' in text,
                            'Actual original CPU payload/startup all3role math check')
                emit(output / 'startup-audit.json', {'ready': ready, 'health': health, 'models': models,
                    'process': actual, 'parsed_startup': parsed, 'native_rows_startup_only': True})
                return run_cases(cases, folder, pid, began+1000, arm, q, old, pv, controls, fixtures)
            result = old.body_and_cleanup(body, lambda: old.stop_server(proc, folder, timeout=100))
            end = fence.fence_terminal(limits)
        emit(output / 'receipt.json', {'arm': arm, 'result': result, 'private_resources': end,
            'manual_code_and_prose_review_pending': True, 'promotion_performed': False})
    return 0


def run_cases(cases, folder, pid, deadline, arm, q, old, pv, controls, fixtures):
    # Existing issue/cancel helpers preserve SSE, native tokens, cache and DONE.
    cancellation = pv.lifecycle_helper()
    from protocol import Stream, json_get, wait_for
    import skip_controls
    numericalpath = DC / 'model-v1/imma_numeric_controls.py'
    import_origins(q)
    numerical = exact('s2_essential_numerical_storage', numericalpath, q['files'][str(numericalpath)])
    import_origins(q)
    profile = q['profiles'][arm]; rows = []; responses = {}; scores = [{'id': c['id'], 'status': 'UNRUN'} for c in cases]
    plan = json.loads(Path(q['profiles']['D0']['map_path']).read_text())
    emit(folder.parent / 'case-progress.json', {'scores': scores, 'rows': rows})
    for i, frozen in enumerate(cases):
        case = copy.deepcopy(frozen)
        if case['id'] == 'ms-prose-tool-followup': case = controls.followup_case(case, responses[case['dependency']], fixtures)
        scores[i]['status'] = 'ISSUED_REVIEW_PENDING'; emit(folder.parent / 'case-progress.json', {'scores': scores, 'rows': rows})
        if arm == 'D0':
            before = profile_snapshot(folder / 'routing.bin'); generation = profile_generation(folder / 'routing.bin')
            emit(folder / ('profile-before-%02d.json' % i), before)
        traces_before = set(old.q8_phase.native_paths(folder))
        def requester(url, request, end):
            return controls.bounded_request(url, request, end, folder, False, stream_class=Stream, observe=json_get,
                wait_for=wait_for, dump_snapshot=numerical.dump_snapshot, storage_snapshot=numerical.owned_storage_snapshot)
        if case['kind'] == 'prefill-cancel':
            destination = folder / 'skip-controls' / case['id']; destination.mkdir(parents=True)
            emit(destination / 'request.json', case['request'])
            def guard_resource():
                require(numerical.owned_storage_snapshot(folder)['status'] != 'INCOMPLETE_HOLD' and
                        pv.memory_available() >= pv.HOST_MARGIN and time.monotonic() < deadline, 'Cancel resource/deadline')
            def observe(url, path): guard_resource(); return cancellation.json_get(url, path)
            def progress(url): guard_resource(); return cancellation.progress(url)
            response = cancellation.prefill_cancel(old.q8_phase.BASE, case['request'], deadline, folder / 'engine.log', 1,
                                                    observe=observe, observe_progress=progress)
            emit(destination / 'response.json', response)
            traces = set(old.q8_phase.native_paths(folder))-traces_before; require(len(traces) == 1, 'One cancelled native trace')
            trace = next(iter(traces)); old.q8_phase.await_trace(trace, max(deadline, time.monotonic()+5))
            proof = cancellation.reconcile(trace, case, response.get('transport') or {}, pid, cancelled=True)
            row = controls.cancel_score(case, response, proof); emit(destination / 'native-audit.json', proof)
        else:
            response, proof = skip_controls.issue(case, folder, pid, deadline, requester=requester)
            scoring = dict(case, kind='prose') if case['kind'] == 'coding' else case
            row = controls.score(scoring, response, proof, quality=False)
            traces = set(old.q8_phase.native_paths(folder))-traces_before; require(len(traces) == 1, 'One issued native trace')
            trace = next(iter(traces))
        row['tokens'] = controls.token_contract(trace / 'tokens.jsonl', proof['observed_tokens'])
        row['activity'] = stat_activity(trace, pid, required=case['id'].startswith('s2-essential-'), candidate=arm == 'D0')
        if arm == 'D0':
            after = saved_profile(folder / 'routing.bin', generation); emit(folder / ('profile-after-%02d.json' % i), after)
            row['original_CPU_participation'] = participation(before, after, plan['selected'], plan['slots'])
            if i == 0: row['arithmetic_scope'] = {'startup_Q8_projection_and_native_CPU_finite_checks_required': True,
                'known_answer_checked': True, 'full_vocabulary_finiteness_or_equivalence_proved': False}
        if case['id'].startswith('s2-essential-'):
            if arm == 'A2':
                # Exact selected92 source increments d_off only from DSpark
                # round(...try_spec...), with no lookup/suffix drafter path.
                offered, accepted = proof['native'].get('drafts_offered'), proof['native'].get('drafts_accepted')
                require(type(offered) is int and type(accepted) is int and 0 <= accepted <= offered and offered > 0,
                        'Selected92 timed task must actually offer native DSpark drafts')
                row['drafter_execution_basis'] = 'Selected92 source-bound native DONE drafts_offered>0; not new STAT draft_rounds'
            if arm == 'D0': require(row['original_CPU_participation']['positive'],
                                    'Each natural task must route sensitive selected original CPU experts')
            if case['kind'] == 'coding':
                code = panel().code_source(response.get('content', ''))
                with (folder.parent / 'generated-code.py').open('x') as f: f.write(code + '\n')
                row['generated_code_executed'] = False
            else: row['prose'] = panel().prose_shape(response.get('content', ''))
            row['manual_acceptance_pending'] = True
        responses[case['id']] = response; rows.append(row); scores[i]['status'] = 'NATURAL_SOURCE_CHECKED_MANUAL_PENDING'
        emit(folder.parent / 'case-progress.json', {'scores': scores, 'rows': rows})
    require(len(old.q8_phase.native_paths(folder)) == len(cases), 'Exact minimal native request count')
    if arm == 'D0': require(any(row.get('original_CPU_participation', {}).get('positive') for row in rows),
                            'Sensitive selected original CPU routing participation required')
    return {'complete': True, 'scores': scores, 'rows': rows, 'manual_review_pending': True,
            'generated_code_execution_pending': True, 'automatic_next_arm': False, 'promotion_performed': False}


def controller(arm, run, admission_pin):
    # Each --run needs a separate immutable action-time admission. No arm loop.
    pin = sha(HERE / 'qualification.json'); q = qualified(pin, arm)
    p2, a, old, base, legacy, startup, fence, pv, controls, fixtures, observer = helpers(q)
    current = json.loads((E / 'STATE.json').read_text()); require(not any(current.get(k) for k in PHASE_KEYS), 'Other work active')
    registry = json.loads((HERE / 'arms.json').read_text())
    closure = json.loads(Path(q['D0_closure']).read_text()) if arm == 'A2' else None
    prerequisite(arm, registry, closure)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out, meta = paths(E / 'results' / ('s2-essential4-' + arm + '-' + stamp), arm)
    require(not meta.exists(), 'Fresh metadata'); meta.mkdir()
    if run:
        path = HERE / (arm + '-admission.json'); require(sha(path) == admission_pin, 'Separate exact action-time admission')
        admission = json.loads(path.read_text())
        require(admission['arm'] == arm and admission['qualification_sha256'] == pin and
                admission['selected_binding'] == base.current_binding(current) and admission['run_authorized'] is True and
                admission['no_replay'] is True, 'Exact current independently admitted arm')
    class Host(legacy.host_class(a), startup.guarded_host(a)):
        def idle(self): return self.baseline_reader().idle() if self.restored_pid is None else super().idle()
        def preflight(self, output):
            require(self.idle(), 'Selected busy; production unchanged')
            now = json.loads((E / 'STATE.json').read_text())
            require(not any(now.get(k) for k in PHASE_KEYS) and base.current_binding(now) == self.baseline_binding == q['selected_binding'], 'Exact healthy selected binding')
            require(shutil.disk_usage('/').free >= 132*2**30, 'Root132 reserve')
            qualified(pin, arm); prerequisite(arm, json.loads((HERE / 'arms.json').read_text()), closure)
            reader = self.baseline_reader(); reader.guard_binding(self.baseline_pid); identity = reader.target_identity()
            reader.guard_binding(self.baseline_pid); self.previous()
            return {'qualified_for_owned_s2_essential': True, 'files': q['files'], 'qualification_sha256': pin,
                    'mode': MODE, 'arm': arm, 'output': str(output), 'controller_pid': os.getpid(), 'baseline_identity': identity}
        def free(self):
            super().free()
            if self.private_attempted: fence.fence_collected(out, meta)
            else: pv.memory_floor(pv.memory_available)
        def launch(self, prior, output, proofpath):
            qualified(pin, arm); require(Path(proofpath) == meta / 'proof.json', 'Owned proof path')
            reg = json.loads((HERE / 'arms.json').read_text()); prerequisite(arm, reg, closure)
            reg[arm] = {'mode': MODE, 'arm': arm, 'attempted': True, 'output': str(output),
                        'controller_pid': os.getpid(), 'qualification_sha256': pin}
            emit(HERE / 'arms.json', reg); self.private_attempted = True
            return self.launch_owned(prior, [str(R / 'venv/bin/python3.14'), '-B', str(HERE / 'runtime.py'), '--phase',
                '--arm', arm, '--output', str(output), '--proof', str(proofpath)], 1200)
    host = Host(); host.audit_dir = meta; host.baseline_binding = base.current_binding(current)
    host.baseline_pid = host.baseline_binding['native_pid']; host.start_binding = None; host.restored_pid = None
    host.private_attempted = False; host.old_close_verified = False
    state = {'utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
             'mode': MODE, 'arm': arm, 'output': str(out), 'proof_path': str(meta / 'proof.json'),
             'qualification_sha256': pin, 'controller_pid': os.getpid(), 'running_status': RUNNING,
             'complete_status': COMPLETE, 'completion_scope': 'Essential source/functionality/two-task capture; separate manual grade, no promotion'}
    def save(value):
        value = dict(value, start_binding=host.start_binding)
        emit(meta / 'state.json', value)
        if value['status'] in ('PREFLIGHT_OK', 'DEFERRED_NO_PRODUCTION_MUTATION', 'DEFERRED_BUSY_OR_MANUAL_MODEL_NO_MUTATION'): return
        now = json.loads((E / 'STATE.json').read_text()); before = copy.deepcopy(now)
        if value['status'] == 'DRAINING_ROUTER':
            require(not any(now.get(k) for k in PHASE_KEYS) and base.current_binding(now) == host.baseline_binding, 'Binding before drain')
        else: require(now.get('maintenance_controller') == str(meta / 'state.json') and
                      now['decode_optimization_current']['controller_pid'] == os.getpid(), 'Exact own save')
        verified = value.get('verified', {}); value['selected_identity'] = verified.get('selected_identity', now['decode_optimization_current']['selected_identity'])
        active = value['status'] in ('DRAINING_ROUTER', RUNNING, 'CLEAN_PHASE_RESTORING_SELECTED_DS', 'DEFERRED_BEFORE_PRIVATE_WINDOW_RESTORING_SELECTED_DS')
        now.update(decode_optimization_current=value, maintenance_controller=str(meta / 'state.json'),
                   active_private_phase=str(meta) if active else None, active_gpu_experiment=active,
                   production_temporarily_stopped=active or value['status'] == 'STOPPED_FOR_OFFLINE_DIAGNOSIS')
        if host.old_close_verified and host.start_binding is None: now['current_native_pid'] = None
        if verified.get('pending_public_probe'): now['production_verification_pending'] = str(meta / 'state.json')
        elif verified.get('passed') is True:
            now['production_verification_pending'] = False; now['current_native_pid'] = value['selected_identity']['native_pid']
        emit(meta / 'state.json', value)
        require(json.loads((E / 'STATE.json').read_text()) == before, 'Canonical state changed; no overwrite')
        emit(E / 'STATE.json', now)
    try:
        result = old.coordinate(host, out, state, save, preflight_only=not run,
                                post_drain_root_free_bytes=lambda: shutil.disk_usage('/').free)
    except (p2.ResourceDeferred, pv.ResourceDeferred) as exc:
        require(not host.private_attempted and host.old_close_verified and host.start_binding is None, 'Exact pre-window no-attempt refusal')
        save(dict(state, status='CLEAN_PHASE_RESTORING_SELECTED_DS', resource_refused=True, reason=str(exc)))
        host.restore_ds(); host.restore_router(); verified = host.verify()
        result = dict(state, status='RESOURCE_DEFERRED_SELECTED_RESTORED', verified=verified, private_attempted=False)
        save(result)
    emit(meta / 'result.json', result); return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--arm', choices=['D0', 'A2'], required=True)
    for flag in ('run', 'phase', 'entry'): parser.add_argument('--' + flag, action='store_true')
    for flag in ('output', 'proof', 'folder', 'config-sha256', 'admission-sha256'): parser.add_argument('--' + flag)
    args = parser.parse_args(); require(sum((args.run, args.phase, args.entry)) <= 1, 'One explicit action')
    if args.phase: return phase(args.output, args.arm, args.proof)
    if args.entry: return entry(args)
    print(json.dumps(controller(args.arm, args.run, args.admission_sha256))); return 0


if __name__ == '__main__': raise SystemExit(main())
