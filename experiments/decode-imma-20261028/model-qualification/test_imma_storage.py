"""Pure source-derived storage/limit controls; limit calls are mocked only."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import imma_storage as s


def geom():
    return s.geometry((Path(__file__).parent / 'pack-geometry.ds4.txt').read_bytes())


def entry(n, size=s.ROW_BYTES):
    return {'path': '/owned/dumps/logits.' + str(n) + '.f32', 'bytes': size,
            'regular': True, 'symlink': False, 'nlink': 1}


class StorageContracts(unittest.TestCase):
    def test_geometry_pin_and_selected_dimensions(self):
        g = geom()
        self.assertEqual(g['layers'], 43)
        self.assertEqual(g['kv_sources'], (2, 8, 14, 20))
        self.assertEqual(g['ratios'], (0, 0) + (2,) * 18 + (1,) * 20 + (0,) * 3)
        with self.assertRaises(ValueError): s.geometry(b'num_hidden_layers 40\n')

    def test_selected_row_packing_exact(self):
        self.assertEqual(s.row_bytes('fp8', 512), 528)
        self.assertEqual(s.row_bytes('fp4', 512), 288)
        self.assertEqual(s.row_bytes('fp4p', 128), 80)
        for fmt, dim in [('unknown', 512), ('fp8', 0), ('fp8', 511), ('fp8', True)]:
            with self.assertRaises(ValueError): s.row_bytes(fmt, dim)

    def test_check_bytes_only_three_source_partial_groups(self):
        self.assertEqual(s.check_bytes(geom()), 2930704)
        self.assertEqual(s.check_bytes(geom()), 16 + 43 * 128 * 528 + 3 * 2 * 2 * 512 * 4)

    def test_slot_worst_case_independent_closed_form(self):
        g = geom(); pos = 12000 + 32768
        # Independent explicit counts: three ratio2 sources, one ratio1 source.
        expected = 24 + 1048576 + pos * 4 + 43 * 16 + 43 * 128 * 528 + 3 * 8192
        expected += 4 * 8 + (3 * (pos // 2) + pos) * (288 + 80)
        expected += 8 + 3 * 2930704 + 8
        self.assertEqual(s.slot_bytes(g, pos, 1048576), 54137768)
        self.assertEqual(s.slot_bytes(g, pos, 1048576), expected)
        self.assertLess(expected, s.HARD_FILE_BYTES)

    def test_meta_profile_and_temporary_file_bounds(self):
        self.assertEqual(s.meta_bytes(44768, 1048576), 1227720)
        b = s.storage_bound(geom(), 'pinned-test-version', ['pack0.bin', 'pack1.bin'])
        self.assertEqual(b['native_owned_file_bounds']['expert_profile_or_tmp'], 66048)
        self.assertEqual(b['max_position'], 44768)
        self.assertTrue(all(v < 512 * 1048576 for v in b['native_owned_file_bounds'].values()))
        self.assertEqual(b['hard_dump_aggregate'], 2 * 1024 ** 3)
        self.assertEqual(b['soft_dump_aggregate'], 1024 ** 3)

    def test_slot_floor_rows_and_checkpoint_increment(self):
        g = geom()
        # At odd position only ratio1 source adds a row; at even all four add rows.
        self.assertEqual(s.slot_bytes(g, 101, 100) - s.slot_bytes(g, 100, 100), 4 + 368)
        self.assertEqual(s.slot_bytes(g, 102, 100) - s.slot_bytes(g, 101, 100), 4 + 4 * 368)
        self.assertEqual(s.slot_bytes(g, 100, 100, 3) - s.slot_bytes(g, 100, 100, 2), s.check_bytes(g))

    def test_geometry_changes_and_bool_ratio_rejected(self):
        for key, value in [('layers', 40), ('head_dim', 1024), ('window', 256),
                           ('kv_sources', (2, 8, 14)), ('ratios', (0, 0) + (2,) * 18 + (True,) * 20 + (0,) * 3)]:
            g = geom(); g[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): s.check_bytes(g)

    def test_position_identity_checkpoint_outside_proven_bounds_rejected(self):
        for pos, identity, checkpoints in [(44769, 100, 3), (-1, 100, 3), (1, 0, 3), (1, 1048577, 3),
                                            (1, 100, 4), (True, 100, 3), (1, True, 3), (1, 100, True)]:
            with self.assertRaises(ValueError): s.slot_bytes(geom(), pos, identity, checkpoints)

    def test_identity_upper_bound_unicode_names_sizes_and_version(self):
        a = s.identity_upper_bound('v1', ['file.bin'])
        b = s.identity_upper_bound('v1', ['file.bin', 'é.bin'])
        self.assertEqual(b - a, len(' é.bin:'.encode()) + 20)
        self.assertEqual(s.identity_upper_bound('v123', ['file.bin']) - a, 2)
        self.assertLess(b, 1048576)

    def test_actual_pinned_seven_pack_names_preserve_relative_identity_strings(self):
        metadata = json.loads((Path(__file__).parent / 'pack-files.json').read_text())
        self.assertEqual(metadata['engine_version'], '0.1.27')
        self.assertEqual(len(metadata['pk_files']), 7)
        names = [record['name'] for record in metadata['pk_files']]
        self.assertEqual(names[4], '../shared/DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf')
        self.assertEqual(names[6], '../../reliability-optimization-20261025/vision-assets-1017/vision.bin')
        before = names[:]
        bound = s.storage_bound(geom(), metadata['engine_version'], names)
        self.assertEqual(names, before)
        self.assertLess(bound['identity_bytes_upper_bound'], 1048576)
        self.assertLess(bound['native_owned_file_bounds']['slot_bin_or_tmp'], 54137768)
        self.assertEqual(bound['native_owned_file_bounds']['expert_profile_or_tmp'], 66048)

    def test_identity_missing_duplicate_oversize_and_wrong_types_rejected(self):
        for version, names in [('', ['f']), ('v', []), ('v', ['f', 'f']), ('v', [None]),
                               ('v', ['x' * 4097]), ('v' * 4097, ['f']), ('v', ['f\x00'])]:
            with self.assertRaises(ValueError): s.identity_upper_bound(version, names)
        with self.assertRaises(ValueError):
            s.identity_upper_bound('v', [str(i) + 'x' * 4000 for i in range(300)])

    def test_preexec_factory_has_no_limit_or_signal_side_effect(self):
        with patch.object(s.resource, 'setrlimit') as limit, patch.object(s.signal, 'signal') as signal:
            fn = s.native_fsize_preexec(geom(), 'v', ['file.bin'], process_kind='UNMEASURED_NUMERICAL_NATIVE')
            self.assertTrue(callable(fn)); limit.assert_not_called(); signal.assert_not_called()

    def test_preexec_sets_only_child_fsize_and_default_overflow_signal(self):
        fn = s.native_fsize_preexec(geom(), 'v', ['file.bin'], process_kind='UNMEASURED_NUMERICAL_NATIVE')
        with patch.object(s.resource, 'getrlimit', return_value=(s.resource.RLIM_INFINITY, s.resource.RLIM_INFINITY)), \
             patch.object(s.resource, 'setrlimit') as limit, patch.object(s.signal, 'signal') as signal:
            fn()
            limit.assert_called_once_with(s.resource.RLIMIT_FSIZE, (s.HARD_FILE_BYTES, s.HARD_FILE_BYTES))
            signal.assert_called_once_with(s.signal.SIGXFSZ, s.signal.SIG_DFL)

    def test_preexec_never_relaxes_stricter_limits(self):
        fn = s.native_fsize_preexec(geom(), 'v', ['file.bin'], process_kind='UNMEASURED_NUMERICAL_NATIVE')
        for limits in [(1024, s.resource.RLIM_INFINITY), (s.resource.RLIM_INFINITY, 1024), (0, 0)]:
            with patch.object(s.resource, 'getrlimit', return_value=limits), \
                 patch.object(s.resource, 'setrlimit') as setter, patch.object(s.signal, 'signal') as signal:
                with self.assertRaises(ValueError): fn()
                setter.assert_not_called(); signal.assert_not_called()

    def test_preexec_rejects_api_timed_production_and_missing_pack_inventory(self):
        for kind in ('API', 'TIMED_NATIVE', 'PRODUCTION', None, True):
            with self.assertRaises(ValueError):
                s.native_fsize_preexec(geom(), 'v', ['file.bin'], process_kind=kind)
        with self.assertRaises(ValueError):
            s.native_fsize_preexec(geom(), 'v', [], process_kind='UNMEASURED_NUMERICAL_NATIVE')

    def test_dump_valid_active_and_complete_are_size_only(self):
        self.assertEqual(s.dump_policy('/owned/dumps', [])['status'], 'WITHIN_BUDGET')
        entries = [entry(i) for i in range(1, 5)]; before = copy.deepcopy(entries)
        r = s.dump_policy('/owned/dumps', entries, complete=True)
        self.assertEqual(r['status'], 'COMPLETE_SIZE_ONLY')
        self.assertEqual(r['total_bytes'], 4 * 517120)
        self.assertFalse(r['numerical_quality_or_equivalence_pass'])
        self.assertEqual(entries, before)

    def test_dump_soft_limit_exact_boundary_is_hold(self):
        entries = [entry(i, 256 * 1048576) for i in range(1, 5)]
        r = s.dump_policy('/owned/dumps', entries)
        self.assertEqual(r['status'], 'INCOMPLETE_HOLD')
        self.assertTrue(r['soft_limit_reached']); self.assertFalse(r['hard_limit_reached'])
        self.assertFalse(r['retry_allowed'])
        entries[3]['bytes'] -= 1
        self.assertEqual(s.dump_policy('/owned/dumps', entries)['status'], 'WITHIN_BUDGET')

    def test_dump_hard_limit_at_or_over_boundary_is_hold(self):
        for size in (s.HARD_FILE_BYTES, s.HARD_FILE_BYTES + 1):
            r = s.dump_policy('/owned/dumps', [entry(1, size)])
            self.assertTrue(r['hard_limit_reached'])
            self.assertEqual(r['status'], 'INCOMPLETE_HOLD')

    def test_dump_wrong_path_traversal_symlink_and_hardlink_rejected(self):
        for field, value in [('path', '/foreign/logits.1.f32'), ('path', '/owned/dumps/../logits.1.f32'),
                             ('symlink', True), ('regular', False), ('nlink', 2), ('nlink', True)]:
            e = entry(1); e[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): s.dump_policy('/owned/dumps', [e])
        for root in ('relative', '/owned/../dumps', '/owned//dumps', '/owned/dumps/', '//owned/dumps'):
            with self.assertRaises(ValueError): s.dump_policy(root, [])

    def test_dump_fifth_missing_duplicate_gapped_and_malformed_rejected(self):
        for entries in ([entry(i) for i in range(1, 6)], [entry(1), entry(1)], [entry(2)], [{'bytes': 0}]):
            with self.assertRaises(ValueError): s.dump_policy('/owned/dumps', entries)
        with self.assertRaises(ValueError): s.dump_policy('/owned/dumps', [entry(1)], complete=True)

    def test_dump_byte_types_negative_and_incomplete_rows_rejected(self):
        for size in (True, -1, 1.0):
            with self.assertRaises(ValueError): s.dump_policy('/owned/dumps', [entry(1, size)])
        for size in (0, s.ROW_BYTES - 1, s.ROW_BYTES + 4):
            entries = [entry(i) for i in range(1, 5)]; entries[0]['bytes'] = size
            with self.assertRaises(ValueError): s.dump_policy('/owned/dumps', entries, complete=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
