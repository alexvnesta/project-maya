"""Small native metadata/I/O controls and one qualified three-role composition.

No original shard,1870-payload allocation, model, GPU or global CPU claim is used.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import payload as p


class NativePayload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipe, cls.writer = p.dependencies()

    def metadata(self):
        r = self.recipe
        counts = [[1] * 384 for _ in range(40)]
        slots = [list(range(320)) + [-1] * 64 for _ in range(40)]
        placement = {'schema': 'ds4-actual-placement-v1', 'context_total': 1048576, 'prefill_chunk': 4096,
            'expert_cache': False, 'inference_executed': False, 'routed_experts_loaded': False,
            'drafter_blocks': 3, 'layers': [{'layer': layer, 'members': 1, 'counts': counts[layer],
                                          'slots': slots[layer]} for layer in range(40)]}
        selection = r.select_native(counts, [list(range(320)) for _ in range(40)])
        index, headers = {'weight_map': {}}, {}
        for row in r.native_records(selection):
            layer, expert, role = row['layer'], row['expert'], row['role']
            name = 'model-%05d-of-00048.safetensors' % (layer + 3)
            h = headers.setdefault(name, {'header_bytes': 1024, 'file_bytes': 8 + 1024 + 384 * 3 * p.MATRIX_BYTES,
                'header_sha256': '1' * 64, 'source_revision': r.OFFICIAL_REVISION,
                'source_file': name, 'source_file_sha256': '%064x' % (layer + 1), 'tensors': {}})
            n, k = row['shape']; at = (expert * 3 + r.ROLES.index(role)) * p.MATRIX_BYTES
            for kind, dtype, divisor, offset, size in (
                    ('weight', 'I8', 2, at, n * k // 2),
                    ('scale', 'F8_E8M0', 32, at + n * k // 2, n * k // 32)):
                key = row['source_' + kind]; index['weight_map'][key] = name
                h['tensors'][key] = {'dtype': dtype, 'shape': [n, k // divisor], 'data_offsets': [offset, offset + size]}
        metadata = {'id': 'deepseek-ai/DeepSeek-V4.1-Flash-1017', 'sha': r.OFFICIAL_REVISION,
            'siblings': [{'rfilename': name, 'size': h['file_bytes'],
                          'lfs': {'size': h['file_bytes'], 'sha256': h['source_file_sha256']}}
                         for name, h in headers.items()]}
        return placement, selection, index, headers, metadata

    def test_pure1870_plan_full_three_role_geometry_header_and_external_map(self):
        inputs = self.metadata(); plan = p.make_plan(*inputs); header = p.validate_plan(plan)
        p.official_contract(plan, inputs[2], inputs[4])
        self.assertEqual(len(plan['records']), 1870 * 3)
        self.assertEqual(plan['payload_bytes'], 35157196800)
        self.assertEqual(plan['file_bytes'], 35157299200)
        self.assertEqual(len(header), 102400)
        self.assertEqual(hashlib.sha256(header).hexdigest(), plan['header_sha256'])
        self.assertEqual(header[88:120].hex(), plan['source_map_sha256'])
        self.assertEqual(plan['records'][2]['shape'], [5120, 2304])
        self.assertEqual(plan['records'][-1]['output_offset'] + p.MATRIX_BYTES, p.PAYLOAD_BYTES)

    def test_official_contract_rejects_source_file_mismatch(self):
        inputs = self.metadata(); plan = p.make_plan(*inputs)
        p.official_contract(plan, inputs[2], inputs[4])
        wrong = copy.deepcopy(inputs[2])
        wrong['weight_map'][plan['records'][0]['source_weight']] = 'model-00048-of-00048.safetensors'
        with self.assertRaises(ValueError): p.official_contract(plan, wrong, inputs[4])

    def test_original_lowbit_dtype_bad_shape_and_range_are_refused(self):
        _, selection, index, headers, _ = self.metadata()
        record = self.recipe.native_records(selection)[0]
        name = index['weight_map'][record['source_weight']]
        for mode in ('dtype', 'shape', 'range'):
            wrong = copy.deepcopy(headers); tensor = wrong[name]['tensors'][record['source_weight']]
            if mode == 'dtype': tensor['dtype'] = 'IQ2_XXS'
            elif mode == 'shape': tensor['shape'] = [2304, 5120]
            else: tensor['data_offsets'][1] -= 1
            with self.assertRaises(ValueError): self.recipe.original_range(record, index, wrong)

    def test_placement_estimate_or_altered_selection_cannot_form_plan(self):
        data = self.metadata(); placement = copy.deepcopy(data[0]); placement['expert_cache'] = True
        with self.assertRaises(ValueError): p.make_plan(placement, *data[1:])
        placement = copy.deepcopy(data[0]); placement['prefill_chunk'] = 2048
        with self.assertRaises(ValueError): p.make_plan(placement, *data[1:])
        changed = copy.deepcopy(data[1]); changed['selected'][0][1] -= 1
        with self.assertRaises(ValueError): p.make_plan(data[0], changed, *data[2:])

    def test_disjoint_output_ranges_reject_holes_duplicates_and_role_deferral(self):
        rows = [{'layer': 0, 'expert': expert, 'role': role, 'output_offset': (expert * 3 + i) * 17,
                 'output_bytes': 17} for expert in range(2) for i, role in enumerate(('w1', 'w3', 'w2'))]
        p.validate_ranges(rows, 12, 17, 2)
        for mode in ('hole', 'duplicate', 'role', 'short'):
            wrong = copy.deepcopy(rows)
            if mode == 'hole': wrong[2]['output_offset'] += 17
            elif mode == 'duplicate': wrong[3]['expert'] = 0
            elif mode == 'role': wrong[2]['role'] = 'w3'
            else: wrong.pop()
            with self.assertRaises(ValueError): p.validate_ranges(wrong, 12, 17, 2)

    def test_pwrite_handles_short_writes_without_changing_shared_cursor(self):
        with tempfile.TemporaryFile() as stream:
            stream.write(bytes(64)); stream.seek(29)
            def short(fd, data, offset): return os.pwrite(fd, data[:2], offset)
            p.pwrite_all(stream.fileno(), b'abcdefg', 11, write=short)
            self.assertEqual(stream.tell(), 29)
            self.assertEqual(os.pread(stream.fileno(), 7, 11), b'abcdefg')
            with self.assertRaises(ValueError): p.pwrite_all(stream.fileno(), b'x', 0, write=lambda *args: 0)

    def test_pread_short_source_never_silently_pads(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t).resolve()/'small-hash';path.write_bytes(b'bounded original SHA smoke')
            self.assertEqual(p.hash_helper().file_sha256(path,hop_bytes=11)['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        with tempfile.TemporaryFile() as stream:
            stream.write(b'abc'); stream.flush()
            with self.assertRaises(ValueError): p.pread_exact(stream.fileno(), 4, 0)

    def test_source_receipt_rejects_changed_inode_content_and_map(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); name = 'model-00003-of-00048.safetensors'
            source = root / name; source.write_bytes(b'original')
            plan = {'official_revision': 'r', 'source_map_sha256': 'm',
                    'source_headers': {name: {'source_file_sha256': p.sha(source), 'file_bytes': 8}}}
            receipt = {'root': str(root), 'official_revision': 'r', 'source_map_sha256': 'm',
                       'files': {name: {'full_sha_verified': True, 'sha256': p.sha(source),
                                              'fingerprint': p.regular(source)}}}
            p.source_contract(plan, receipt, root)
            source.write_bytes(b'changed!')
            with self.assertRaises(ValueError): p.source_contract(plan, receipt, root)
            receipt['source_map_sha256'] = 'other'
            with self.assertRaises(ValueError): p.source_contract(plan, receipt, root)

    def test_exact_raw_header_and_tiny_original_plane_reads(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve(); name = 'model-00003-of-00048.safetensors'
            raw = p.canonical({'w': {'dtype': 'I8', 'shape': [2, 16], 'data_offsets': [0, 32]},
                               's': {'dtype': 'F8_E8M0', 'shape': [2, 1], 'data_offsets': [32, 34]}})
            path = root / name; path.write_bytes(len(raw).to_bytes(8, 'little') + raw + bytes(range(32)) + b'\x7f\x7f')
            base = 8 + len(raw)
            row = {'shape': [2, 32], 'source_weight': 'w', 'source_scale': 's', 'source_ranges': {
                'weight': {'file': name, 'offset': base, 'bytes': 32},
                'scale': {'file': name, 'offset': base + 32, 'bytes': 2}}}
            receipt = {'files': {name: {'fingerprint': p.regular(path)}}}
            descriptors = {name: {'header_bytes': len(raw), 'header_sha256': hashlib.sha256(raw).hexdigest()}}
            fake_recipe = types.SimpleNamespace(original_range=lambda *args: row['source_ranges'])
            self.assertEqual(p.read_role(row, root, receipt, descriptors, fake_recipe), (bytes(range(32)), b'\x7f\x7f'))
            wrong = copy.deepcopy(descriptors); wrong[name]['header_sha256'] = '0' * 64
            with self.assertRaises(ValueError): p.read_role(row, root, receipt, wrong, fake_recipe)
            path.write_bytes(path.read_bytes() + b'x')
            with self.assertRaises(ValueError): p.read_role(row, root, receipt, descriptors, fake_recipe)

    def test_codec_fault_short_output_and_short_plane_stop_without_retry(self):
        for mode in ('exit', 'short'):
            run = Mock(return_value=types.SimpleNamespace(returncode=1 if mode == 'exit' else 0, stdout=b''))
            with self.assertRaises(ValueError): p.pack_role(bytes(32), bytes(2), [2, 32], 'codec', runner=run)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.kwargs['env'], p.CLEAN_ENV)
        run = Mock()
        with self.assertRaises(ValueError): p.pack_role(b'', b'', [2, 32], 'codec', runner=run)
        run.assert_not_called()

    def test_full_three_role_exact_codec_composition_into_disjoint_output(self):
        root = p.Q / 'iq3s-real-matrix-v1'
        weight, scale = (root / 'original-weight.bin').read_bytes(), (root / 'original-scale.bin').read_bytes()
        self.assertEqual(hashlib.sha256(weight).hexdigest(), 'baf5ebb0c98ef3d38b03f62ac1702dc4658bde4bfcb6f1268deeefa8dd176319')
        self.assertEqual(hashlib.sha256(scale).hexdigest(), '2cd9b4c35666281251c0218ec7bbe998f0d351436fa375cd7020cef43a8c385b')
        codec = p.codec_path()
        # Same flat original block fixture deliberately exercises both complete
        # matrix orientations and all3 ordered offsets. It is not a new claim
        # that one real expert's three trained matrices have identical values.
        with tempfile.TemporaryFile() as stream:
            stream.truncate(3 * p.MATRIX_BYTES)
            for number, role in enumerate(('w1', 'w3', 'w2')):
                data = p.pack_role(weight, scale, self.recipe.geometry(role), codec)
                self.assertEqual(hashlib.sha256(data).hexdigest(), 'a61f4f32ef4b63f137f5afb72c62959a7bac3429cfb912eb36e80f289515ba57')
                p.pwrite_all(stream.fileno(), data, number * p.MATRIX_BYTES)
                self.assertEqual(p.pread_exact(stream.fileno(), len(data), number * p.MATRIX_BYTES), data)

    def test_queue_fault_prevents_new_work_without_retry(self):
        queue = p.exact('payload_test_queue', p.CONVERSION, p.CONVERSION_SHA); seen = []
        def task(index): seen.append(index); raise ValueError('intentional')
        with self.assertRaises(ValueError): queue.convert_queue(list(range(12)), task, lambda: None, workers=1)
        self.assertEqual(seen, [0])

    def test_capture_handle_before_return_and_cleanup_failure_is_preserved(self):
        events = []; process = types.SimpleNamespace(pid=12345, returncode=0, poll=lambda: 0)
        registry = types.SimpleNamespace(children=[], starting=lambda n: events.append('starting'), cleanup_failed=Mock())
        def register(proc, name):
            registry.children.append((name, proc, proc.pid)); events.append('registered')
        registry.registered = register; children = p.Children(registry)
        with patch.object(p.subprocess, 'Popen', return_value=process):
            self.assertIs(children.spawn(['reviewed']), process)
        self.assertEqual(events, ['starting', 'registered'])
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t).resolve()
            p.emit(folder / '0000.observed.json', {'pid': process.pid, 'ppid': os.getpid(), 'pgid': process.pid,
                'cpu': [30, 30], 'as': [512 * 2**20] * 2, 'nice': 15, 'environment': p.CLEAN_ENV, 'isolated': True})
            owner = types.SimpleNamespace(cleanup=Mock(side_effect=ValueError('owned cleanup fault')))
            with patch.object(children, 'spawn', return_value=process), self.assertRaises(ValueError):
                p.run_child(0, folder, 'qualification', 'pin', children, owner, lambda: None, time_now() + 120)
            row = json.loads((folder / '0000.child.json').read_text())
            self.assertIsNone(row['error'])
            self.assertEqual(len(row['cleanup']), 1); self.assertEqual(registry.cleanup_failed.call_count, 1)

    def test_actual_child_limits_and_identity_must_match(self):
        row = {'pid': 1001, 'ppid': 1000, 'pgid': 1001, 'cpu': [30, 30], 'as': [512 * 2**20] * 2,
               'nice': 15, 'environment': p.CLEAN_ENV, 'isolated': True}
        p.actual_limits(row, 1001, 1000)
        for key, value in (('cpu', [120, 120]), ('nice', 30), ('pgid', 1002), ('environment', {})):
            with self.assertRaises(ValueError): p.actual_limits(dict(row, **{key: value}), 1001, 1000)

    def test_passed_only_or_mismatched_physical_cpu_proof_never_qualifies(self):
        sources, inputs, ids, review = {'payload.py': 'x'}, {'header': 'h'}, ['one'], 'a' * 64
        environment = {key: p.CPU_ENV[key] for key in ('CUDA_VISIBLE_DEVICES', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
            'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'MALLOC_ARENA_MAX', 'PYTHONDONTWRITEBYTECODE')}
        observed = {'pid': 1001, 'ppid': 1000, 'pgid': 1001, 'cpu': [30, 30], 'as': [512 * 2**20] * 2,
                    'nice': 15, 'platform': 'linux', 'dont_write_bytecode': True, 'environment': environment}
        proof = {'passed': True, 'physical_platform': 'linux', 'sources': sources, 'inputs': inputs,
            'test_ids': ids, 'tests_run': 1, 'returncode': 0, 'failures': 0, 'errors': 0,
            'controls': {'CPU_seconds': 30, 'AS_bytes': [512 * 2**20] * 2, 'wall_seconds': 90, 'nice': 15},
            'isolated': True, 'process_environment': p.CPU_ENV, 'supervisor_sha256': p.SUPERVISOR_SHA,
            'source_review_sha256': review, 'supervisor_pid': 1000, 'observed': observed}
        supervision = {'pid': 1001, 'returncode': 0, 'error': None, 'cleanup': [], 'elapsed_seconds': .1,
            'argv': ['python', '-I', '-B', '/reviewed/run_cpu.py', '--review-sha256', review, '--child', '--parent', '1000']}
        p.cpu_proof_contract(proof, supervision, sources, inputs, ids, 'linux', review)
        for mode in ('passed-only', 'count', 'exit', 'failure', 'errors', 'cpu', 'as', 'nice', 'cuda',
                     'isolated', 'bytecode', 'group', 'parent', 'supervisor-pid', 'supervisor-exit', 'cleanup'):
            wrong, closure = copy.deepcopy(proof), copy.deepcopy(supervision)
            if mode == 'passed-only': wrong = {'passed': True}
            elif mode == 'count': wrong['tests_run'] = 0
            elif mode == 'exit': wrong['returncode'] = 1
            elif mode == 'failure': wrong['failures'] = 1
            elif mode == 'errors': wrong['errors'] = 1
            elif mode == 'cpu': wrong['observed']['cpu'] = [120, 120]
            elif mode == 'as': wrong['observed']['as'] = None
            elif mode == 'nice': wrong['observed']['nice'] = 0
            elif mode == 'cuda': wrong['observed']['environment']['CUDA_VISIBLE_DEVICES'] = '0'
            elif mode == 'isolated': wrong['isolated'] = False
            elif mode == 'bytecode': wrong['observed']['dont_write_bytecode'] = False
            elif mode == 'group': wrong['observed']['pgid'] = 1002
            elif mode == 'parent': wrong['supervisor_pid'] = 1002
            elif mode == 'supervisor-pid': closure['pid'] = 1002
            elif mode == 'supervisor-exit': closure['returncode'] = 1
            else: closure['cleanup'] = ['owned group survived']
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                p.cpu_proof_contract(wrong, closure, sources, inputs, ids, 'linux', review)


def time_now():
    import time
    return time.monotonic()


if __name__ == '__main__': unittest.main(verbosity=2)
