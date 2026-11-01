"""Independent bounded recipe/mapping controls. No weights, network, or inference."""
import struct
import unittest
import reconstruction as r


class Reconstruction(unittest.TestCase):
    def counts(self):
        return [[e + 1 for e in range(384)] for _ in range(40)]

    def gpus(self):
        return [list(range(300)) for _ in range(40)]

    def selection(self):
        return r.select_native(self.counts(), self.gpus())

    def test_recipe_preserves_capacity_effort_drafter(self):
        d = r.recipe()
        self.assertEqual((d['total_context'], d['output_allowance'], d['effort']), (1048576, 262144, 100))
        self.assertIn('on', d['drafter'])
        self.assertEqual(d['benchmark_cap'], 32768)
        self.assertFalse(d['exact_private_S2'])

    def test_newer_iq3_s_supersedes_t16(self):
        d = r.recipe()
        self.assertEqual(d['gate_up']['layers'], [24, 25, 26, 27, 28])
        self.assertEqual(d['gate_up']['dtype'], 'IQ3_S')
        self.assertIn('original MXFP4', d['gate_up']['source'])

    def test_not_prefill_only_selection(self):
        self.assertIn('no independent prefill-only veto', r.recipe()['selection_metric'])

    def test_profile_trunk_and_drafter(self):
        raw = struct.pack('<15360I', *([1] * 15360))
        self.assertEqual(r.profile(raw), r.profile(raw + b'\0' * (3 * 384 * 4)))

    def test_wrong_profile_lengths(self):
        for raw in (b'', b'\0' * (40 * 384 * 4 - 1), b'\0' * (41 * 384 * 4)):
            with self.assertRaises(ValueError): r.profile(raw)

    def test_empty_profile_not_fake_placement(self):
        with self.assertRaisesRegex(ValueError, 'routing'): r.profile(b'\0' * (40 * 384 * 4))

    def test_exact_native_count_and_no_gpu_overlap(self):
        s = self.selection()
        self.assertEqual(len(s['selected']), 1870)
        self.assertEqual(len({tuple(p) for p in s['selected']}), 1870)
        self.assertTrue(all(e >= 300 for _, e in s['selected']))
        self.assertFalse(s['private_author_map_reproduced'])
        self.assertFalse(s['adaptive_cache'])
        self.assertFalse(s['decode_streaming'])

    def test_every_sensitive_ram_expert_included(self):
        s = self.selection()
        selected = {tuple(p) for p in s['selected']}
        self.assertEqual(s['sensitive_cpu_count'], 420)
        self.assertTrue(all((l, e) in selected for l in range(24, 29) for e in range(300, 384)))

    def test_remainder_ranked_by_count_then_layer_expert(self):
        c, g = self.counts(), self.gpus()
        s = r.select_native(c, g, target=421)
        other = [p for p in s['selected'] if p[0] not in r.SENSITIVE]
        self.assertEqual(other, [[0, 383]])

    def test_selection_deterministic_and_source_bound(self):
        a, b = self.selection(), self.selection()
        self.assertEqual(a, b)
        c = self.counts(); c[0][383] += 1
        self.assertNotEqual(a['profile_sha256'], r.select_native(c, self.gpus())['profile_sha256'])

    def test_missing_actual_gpu_map_refused(self):
        for g in (None, [], self.gpus()[:-1]):
            with self.assertRaises(ValueError): r.select_native(self.counts(), g)

    def test_duplicate_invalid_or_boolean_gpu_ids(self):
        for bad in ([0, 0], [384], [-1], [True], [1.0]):
            g = self.gpus(); g[0] = bad
            with self.assertRaises(ValueError): r.select_native(self.counts(), g)

    def test_bad_count_types_shapes_and_zero_rows(self):
        for bad in ([0] * 384, [1] * 383, [True] * 384, [2**32] * 384, [-1] * 384):
            c = self.counts(); c[0] = bad
            with self.assertRaises(ValueError): r.select_native(c, self.gpus())

    def test_sensitive_set_cannot_be_truncated(self):
        with self.assertRaisesRegex(ValueError, 'budget'):
            r.select_native(self.counts(), [[] for _ in range(40)])

    def test_insufficient_cpu_set_refused(self):
        with self.assertRaises(ValueError): r.select_native(self.counts(), [list(range(384)) for _ in range(40)])

    def test_target_not_boolean_zero_or_overbudget(self):
        for target in (True, 0, 1871):
            with self.assertRaises(ValueError): r.select_native(self.counts(), self.gpus(), target)

    def test_all_three_native_roles_and_exact_bytes(self):
        records = r.native_records(self.selection())
        self.assertEqual(len(records), 5610)
        self.assertEqual({x['role'] for x in records}, {'w1', 'w3', 'w2'})
        self.assertEqual(records[-1]['output_offset'] + records[-1]['output_bytes'], 35157196800)
        self.assertEqual(records[0]['source_scale'], 'layers.0.ffn.experts.342.w1.scale')

    def test_native_record_geometry_and_contiguous_offsets(self):
        records = r.native_records({'selected': [[24, 0]], 'count': 1})
        self.assertEqual([x['shape'] for x in records], [[2304, 5120], [2304, 5120], [5120, 2304]])
        self.assertEqual([x['output_offset'] for x in records], [0, 6266880, 12533760])

    def test_native_record_duplicate_unordered_or_drafter_refused(self):
        for ids in ([[0, 0], [0, 0]], [[1, 0], [0, 0]], [[40, 0]], [[0, True]]):
            with self.assertRaises(ValueError): r.native_records({'selected': ids, 'count': len(ids)})

    def test_native_coverage_count_not_inferred(self):
        for count in (True, 2):
            with self.assertRaises(ValueError): r.native_records({'selected': [[0, 0]], 'count': count})

    def source(self):
        x = r.native_records({'selected': [[24, 0]], 'count': 1})[0]
        w, s = x['source_weight'], x['source_scale']
        filename = 'model-00027-of-00048.safetensors'
        header = {'header_bytes': 128, 'file_bytes': 10000000, 'tensors': {
            w: {'dtype': 'I8', 'shape': [2304, 2560], 'data_offsets': [0, 5898240]},
            s: {'dtype': 'F8_E8M0', 'shape': [2304, 160], 'data_offsets': [5898240, 6266880]}}}
        return x, {'weight_map': {w: filename, s: filename}}, {filename: header}

    def test_exact_original_weight_scale_range(self):
        x, index, headers = self.source(); d = r.original_range(x, index, headers)
        self.assertEqual(d['weight']['offset'], 136)
        self.assertEqual(d['weight']['bytes'], 5898240)
        self.assertEqual(d['scale']['bytes'], 368640)

    def test_wrong_original_shape_dtype_or_bool(self):
        for changes in ({'dtype': 'BF16'}, {'shape': [2304, 5120]}, {'shape': [True, 2560]}):
            x, index, headers = self.source()
            headers[next(iter(headers))]['tensors'][x['source_weight']].update(changes)
            with self.assertRaises(ValueError): r.original_range(x, index, headers)

    def test_misaligned_source_identity_refused(self):
        for changes in ({'layer': 25}, {'expert': 1}, {'role': 'w2'}, {'dtype': 'IQ3_S'}):
            x, index, headers = self.source(); x.update(changes)
            with self.assertRaises(ValueError): r.original_range(x, index, headers)

    def test_outside_file_or_overlapping_planes_refused(self):
        x, index, headers = self.source(); headers[next(iter(headers))]['file_bytes'] = 6266880
        with self.assertRaises(ValueError): r.original_range(x, index, headers)
        x, index, headers = self.source()
        headers[next(iter(headers))]['tensors'][x['source_scale']]['data_offsets'] = [0, 368640]
        with self.assertRaisesRegex(ValueError, 'Distinct'): r.original_range(x, index, headers)

    def test_nonofficial_shard_refused(self):
        x, index, headers = self.source(); index['weight_map'][x['source_weight']] = '../foreign'
        with self.assertRaises(ValueError): r.original_range(x, index, headers)

    def test_budget_native_and_iq3_s_growth(self):
        b = r.overlay_budget()
        self.assertEqual(b['native_packed_bytes'], 35157196800)
        self.assertEqual(b['iq3_s_gate_up_matrices'], 3840)
        self.assertEqual(b['iq3_s_gate_up_bytes'], 19464192000)
        self.assertEqual(b['iq3_s_growth_over_maya_s_gate_up_bytes'], 7785676800)
        self.assertFalse(b['RAM_VRAM_fit_proven'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
