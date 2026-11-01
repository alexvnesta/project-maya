import unittest


def coalesce_ranges(ranges):
    """Merge overlapping and touching half-open integer ranges.

    Returns a sorted list of disjoint (start, end) tuples. Zero-length
    ranges are dropped.
    """
    intervals = []

    for item in ranges:
        try:
            start, end = item
        except (TypeError, ValueError) as exc:
            raise TypeError("each range must be a pair of endpoints") from exc

        if not (isinstance(start, int) and not isinstance(start, bool)):
            raise TypeError("range endpoints must be integers")
        if not (isinstance(end, int) and not isinstance(end, bool)):
            raise TypeError("range endpoints must be integers")

        if start > end:
            raise ValueError("range start must not exceed range end")
        if start == end:
            continue

        intervals.append((start, end))

    intervals.sort()
    merged = []

    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            previous_start, previous_end = merged[-1]
            if end > previous_end:
                merged[-1] = (previous_start, end)

    return merged


class CoalesceRangesTests(unittest.TestCase):
    def test_empty_input_returns_empty_list(self):
        self.assertEqual(coalesce_ranges([]), [])

    def test_single_range_is_returned_as_tuple(self):
        result = coalesce_ranges([[3, 7]])
        self.assertEqual(result, [(3, 7)])
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], tuple)

    def test_overlapping_ranges_merge(self):
        self.assertEqual(coalesce_ranges([[1, 5], [3, 9]]), [(1, 9)])
        self.assertEqual(coalesce_ranges([[1, 10], [2, 3], [7, 8]]), [(1, 10)])

    def test_touching_ranges_merge(self):
        self.assertEqual(coalesce_ranges([[1, 2], [2, 3], [3, 4]]), [(1, 4)])
        self.assertEqual(coalesce_ranges([[10, 11], [5, 10]]), [(5, 11)])

    def test_zero_length_ranges_are_dropped(self):
        self.assertEqual(coalesce_ranges([[1, 1], [2, 2], [-3, -3]]), [])
        self.assertEqual(coalesce_ranges([[1, 2], [2, 2], [2, 3]]), [(1, 3)])

    def test_disjoint_ranges_remain_separate_and_sorted(self):
        self.assertEqual(
            coalesce_ranges([[10, 20], [1, 3], [5, 7]]),
            [(1, 3), (5, 7), (10, 20)],
        )

    def test_output_is_sorted_disjoint_list_of_tuples(self):
        result = coalesce_ranges([[8, 10], [1, 4], [3, 6], [10, 12], [14, 15]])
        self.assertEqual(result, [(1, 6), (8, 12), (14, 15)])
        self.assertIsInstance(result, list)
        for interval in result:
            self.assertIsInstance(interval, tuple)
            self.assertEqual(len(interval), 2)
        self.assertEqual(result, sorted(result))
        for previous, current in zip(result, result[1:]):
            self.assertLess(previous[1], current[0])

    def test_negative_bounds_are_supported(self):
        self.assertEqual(
            coalesce_ranges([[-10, -5], [-7, -4], [-2, -1]]),
            [(-10, -4), (-2, -1)],
        )
        self.assertEqual(
            coalesce_ranges([[-5, -3], [-3, -1], [-10, -9]]),
            [(-10, -9), (-5, -1)],
        )

    def test_large_integer_bounds_are_supported(self):
        base = 10 ** 200
        self.assertEqual(
            coalesce_ranges([[base + 5, base + 10], [base, base + 6]]),
            [(base, base + 10)],
        )
        self.assertEqual(
            coalesce_ranges([[base, base + 1], [base + 2, base + 3]]),
            [(base, base + 1), (base + 2, base + 3)],
        )

    def test_bool_start_is_rejected(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([[True, 5]])

    def test_bool_end_is_rejected(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([[5, False]])

    def test_non_integer_float_endpoint_is_rejected(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([[1, 2.0]])

    def test_non_integer_string_endpoint_is_rejected(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([["1", 2]])

    def test_non_integer_none_endpoint_is_rejected(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([[1, None]])

    def test_start_greater_than_end_raises_value_error(self):
        with self.assertRaises(ValueError):
            coalesce_ranges([[7, 3]])
        with self.assertRaises(ValueError):
            coalesce_ranges([[-1, -2]])

    def test_equal_bounds_are_not_an_error(self):
        self.assertEqual(coalesce_ranges([[5, 5]]), [])

    def test_input_not_mutated_on_success(self):
        source = [[5, 9], [1, 6], [12, 13]]
        original = [pair[:] for pair in source]
        result = coalesce_ranges(source)
        self.assertEqual(source, original)
        self.assertEqual(result, [(1, 9), (12, 13)])

    def test_input_not_mutated_on_type_error(self):
        source = [[1, 3], [True, 4], [5, 6]]
        original = [pair[:] for pair in source]
        with self.assertRaises(TypeError):
            coalesce_ranges(source)
        self.assertEqual(source, original)

    def test_input_not_mutated_on_value_error(self):
        source = [[1, 3], [7, 5], [8, 9]]
        original = [pair[:] for pair in source]
        with self.assertRaises(ValueError):
            coalesce_ranges(source)
        self.assertEqual(source, original)


if __name__ == "__main__":
    unittest.main()