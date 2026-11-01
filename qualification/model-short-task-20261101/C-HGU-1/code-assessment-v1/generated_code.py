import unittest


def _is_integer_endpoint(value):
    return isinstance(value, int) and not isinstance(value, bool)


def coalesce_ranges(ranges):
    normalized = []

    for index, item in enumerate(ranges):
        if not isinstance(item, (list, tuple)):
            raise TypeError(
                "range at index {} must be a pair".format(index)
            )
        if len(item) != 2:
            raise TypeError(
                "range at index {} must have exactly two endpoints".format(index)
            )

        start, end = item

        if not _is_integer_endpoint(start):
            raise TypeError(
                "start endpoint at index {} must be an integer, not bool".format(index)
            )
        if not _is_integer_endpoint(end):
            raise TypeError(
                "end endpoint at index {} must be an integer, not bool".format(index)
            )
        if start > end:
            raise ValueError(
                "start endpoint at index {} must not exceed end".format(index)
            )

        if start != end:
            normalized.append((start, end))

    normalized.sort()
    merged = []

    for start, end in normalized:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            last_start, last_end = merged[-1]
            if end > last_end:
                merged[-1] = (last_start, end)

    return merged


class CoalesceRangesTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(coalesce_ranges([]), [])

    def test_single_range_is_returned_as_tuple(self):
        result = coalesce_ranges([(4, 9)])
        self.assertEqual(result, [(4, 9)])
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], tuple)

    def test_zero_length_ranges_are_dropped(self):
        self.assertEqual(coalesce_ranges([(3, 3), (1, 1), (2, 2)]), [])

    def test_zero_length_range_does_not_affect_others(self):
        self.assertEqual(
            coalesce_ranges([(5, 5), (1, 3), (7, 7), (10, 12)]),
            [(1, 3), (10, 12)],
        )

    def test_result_is_sorted(self):
        self.assertEqual(
            coalesce_ranges([(10, 12), (1, 2), (5, 7)]),
            [(1, 2), (5, 7), (10, 12)],
        )

    def test_overlaps_are_merged(self):
        self.assertEqual(coalesce_ranges([(1, 5), (3, 9)]), [(1, 9)])

    def test_nested_range_is_absorbed(self):
        self.assertEqual(
            coalesce_ranges([(1, 10), (3, 5), (2, 4)]),
            [(1, 10)],
        )

    def test_touching_ranges_are_merged(self):
        self.assertEqual(coalesce_ranges([(3, 5), (1, 3)]), [(1, 5)])

    def test_disjoint_ranges_remain_separate(self):
        self.assertEqual(
            coalesce_ranges([(1, 2), (4, 5)]),
            [(1, 2), (4, 5)],
        )

    def test_multiple_chains_merge(self):
        self.assertEqual(
            coalesce_ranges([(8, 10), (1, 5), (4, 8), (10, 12), (20, 21)]),
            [(1, 12), (20, 21)],
        )

    def test_duplicate_ranges_are_merged(self):
        self.assertEqual(coalesce_ranges([(1, 3), (1, 3)]), [(1, 3)])

    def test_success_does_not_mutate_input(self):
        ranges = [[5, 7], [1, 3], [3, 5]]
        original = [list(pair) for pair in ranges]

        result = coalesce_ranges(ranges)

        self.assertEqual(result, [(1, 7)])
        self.assertEqual(ranges, original)
        self.assertEqual(ranges, [[5, 7], [1, 3], [3, 5]])

    def test_type_error_does_not_mutate_input(self):
        ranges = [[1, 2], [True, 4], [5, 1]]
        original = [list(pair) for pair in ranges]

        with self.assertRaises(TypeError):
            coalesce_ranges(ranges)

        self.assertEqual(ranges, original)

    def test_value_error_does_not_mutate_input(self):
        ranges = [[1, 2], [5, 1], [0, 2]]
        original = [list(pair) for pair in ranges]

        with self.assertRaises(ValueError):
            coalesce_ranges(ranges)

        self.assertEqual(ranges, original)

    def test_rejects_bool_start(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([(True, 2)])

    def test_rejects_bool_end(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([(1, False)])

    def test_rejects_float_start(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([(1.0, 2)])

    def test_rejects_float_end(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([(1, 2.0)])

    def test_rejects_string_endpoint(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([("1", 2)])

    def test_rejects_none_endpoint(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([(1, None)])

    def test_start_greater_than_end_raises_value_error(self):
        with self.assertRaises(ValueError):
            coalesce_ranges([(10, 5)])

    def test_start_equal_end_is_allowed_and_dropped(self):
        self.assertEqual(coalesce_ranges([(4, 4)]), [])

    def test_negative_integers_sort_and_merge(self):
        self.assertEqual(
            coalesce_ranges([(-1, 2), (-5, -1), (-10, -8), (-8, -6)]),
            [(-10, -6), (-5, 2)],
        )

    def test_large_integers(self):
        huge = 10 ** 200
        self.assertEqual(
            coalesce_ranges([
                (huge, huge + 4),
                (huge + 2, huge + 10),
                (huge + 10, huge + 20),
                (huge - 10, huge - 5),
            ]),
            [(huge - 10, huge - 5), (huge, huge + 20)],
        )


if __name__ == "__main__":
    unittest.main()