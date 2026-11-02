import unittest
import batch
class Batches(unittest.TestCase):
    def test_partition_no_missing_duplicates_or_reorder(self):
        rows=list(range(1386));parts=[batch.subset(rows,i) for i in range(22)]
        self.assertEqual(sum(parts,[]),rows);self.assertTrue(all(0<len(v)<=64 for v in parts))
    def test_negative_bool_float_and_overrun_refused(self):
        for i in [-1,True,0.0,2]:
            with self.subTest(i=i),self.assertRaises(ValueError):batch.subset(list(range(70)),i)
    def test_empty_rows_refused(self):
        with self.assertRaises(ValueError):batch.subset([],0)
    def test_full_bound_and_final_tail_exact(self):
        self.assertEqual(batch.subset(list(range(70)),0),list(range(64)));self.assertEqual(batch.subset(list(range(70)),1),list(range(64,70)))
    def test_inputs_not_mutated(self):
        rows=list(range(70));v=batch.subset(rows,0);v.clear();self.assertEqual(rows,list(range(70)))
