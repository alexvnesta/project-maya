"""Actual immutable official metadata controls, no weights/network/GPU."""
import copy
from pathlib import Path
import unittest
import source_plan as s


class OfficialPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index, cls.headers = s.load_inputs(Path(__file__).parent / 'inputs')
        cls.plan = s.make(cls.index, cls.headers)

    def test_complete_real_original_coverage(self):
        p = self.plan
        self.assertEqual(p['matrix_count'], 3840)
        self.assertEqual(len({(d['layer'], d['expert'], d['role']) for d in p['records']}), 3840)
        self.assertEqual({d['layer'] for d in p['records']}, set(range(24, 29)))
        self.assertEqual({d['role'] for d in p['records']}, {'w1', 'w3'})

    def test_exact_source_and_target_bytes(self):
        self.assertEqual(self.plan['source_native_mxfp4_bytes'], 24064819200)
        self.assertEqual(self.plan['target_iq3_s_bytes'], 19464192000)
        self.assertEqual(self.plan['source_full_shards_bytes'], 36959958872)

    def test_each_output_slot_contiguous(self):
        previous = 0
        for d in self.plan['records']:
            self.assertEqual(d['target_offset'], previous)
            previous += d['target_bytes']
        self.assertEqual(previous, 19464192000)

    def test_no_cpu_map_or_calibration_invented(self):
        self.assertEqual(self.plan['CPU_1870_expert_ids'], 'UNFROZEN')
        self.assertFalse(self.plan['encoder_calibration_qualified'])

    def test_missing_scale_blocks_entire_plan(self):
        index = dict(self.index)
        index['weight_map'] = dict(index['weight_map'])
        del index['weight_map']['layers.24.ffn.experts.0.w1.scale']
        with self.assertRaises(KeyError): s.make(index, self.headers)

    def test_wrong_plane_dtype_blocks_entire_plan(self):
        headers = copy.deepcopy(self.headers)
        name = 'layers.24.ffn.experts.0.w1.weight'
        headers[self.index['weight_map'][name]]['tensors'][name]['dtype'] = 'BF16'
        with self.assertRaises(ValueError): s.make(self.index, headers)

    def test_out_of_file_plane_blocks_entire_plan(self):
        headers = copy.deepcopy(self.headers)
        name = 'layers.24.ffn.experts.0.w1.weight'
        h = headers[self.index['weight_map'][name]]
        h['tensors'][name]['data_offsets'] = [h['file_bytes'], h['file_bytes'] + 5898240]
        with self.assertRaises(ValueError): s.make(self.index, headers)


if __name__ == '__main__':
    unittest.main(verbosity=2)
