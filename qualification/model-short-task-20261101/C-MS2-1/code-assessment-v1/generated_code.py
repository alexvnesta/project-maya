import unittest
from copy import deepcopy


def coalesce_ranges(ranges):
    intervals = []

    for item in ranges:
        try:
            start, end = item
        except (TypeError, ValueError):
            raise TypeError("each range must be a pair of endpoints") from None

        if isinstance(start, bool) or not isinstance(start, int):
            raise TypeError("range endpoints must be integers")
        if isinstance(end, bool) or not isinstance(end, int):
            raise TypeError("range endpoints must be integers")

        if start > end:
            raise ValueError("range start must not be greater than range end")

        if start == end:
            continue

        intervals.append((start, end))

    intervals.sort(key=lambda interval: interval[0])

    if not intervals:
        return []

    merged = []
    current_start, current_end = intervals[0]

    for start, end in intervals[1:]:
        if start <= current_end:
            if end > current_end:
                current_end = end
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start, end

    merged.append((current_start, current_end))
    return merged


class TestCoalesceRanges(unittest.TestCase):
    def test_empty_input_returns_empty_list(self):
        self.assertEqual(coalesce_ranges([]), [])

    def test_single_nonzero_range_is_returned_as_tuple(self):
        self.assertEqual(coalesce_ranges([[1, 4]]), [(1, 4)])

    def test_overlapping_ranges_are_merged(self):
        self.assertEqual(coalesce_ranges([[1, 4], [2, 5]]), [(1, 5)])

    def test_touching_half_open_ranges_are_merged(self):
        self.assertEqual(coalesce_ranges([[1, 3], [3, 5]]), [(1, 5)])
        self.assertEqual(coalesce_ranges([[3, 5], [1, 3]]), [(1, 5)])

    def test_zero_length_ranges_are_dropped(self):
        self.assertEqual(coalesce_ranges([[4, 4], [1, 2], [9, 9]]), [(1, 2)])
        self.assertEqual(coalesce_ranges([[3, 3], [7, 7]]), [])

    def test_output_is_sorted_and_disjoint(self):
        result = coalesce_ranges([[10, 12], [1, 3], [7, 8], [5, 6]])
        self.assertEqual(result, [(1, 3), (5, 6), (7, 8), (10, 12)])
        for left, right in zip(result, result[1:]):
            self.assertLess(left[1], right[0])

    def test_contained_ranges_merge(self):
        self.assertEqual(coalesce_ranges([[1, 10], [2, 3], [5, 8]]), [(1, 10)])

    def test_negative_integers(self):
        self.assertEqual(
            coalesce_ranges([[-5, -1], [-10, -7], [-3, 2]]),
            [(-10, -7), (-5, 2)],
        )

    def test_large_integers(self):
        big = 10 ** 100
        self.assertEqual(
            coalesce_ranges([(big, big + 10), (big + 5, big + 20), (-big, -big + 2)]),
            [(-big, -big + 2), (big, big + 20)],
        )

    def test_returns_list_of_tuples(self):
        result = coalesce_ranges([[1, 2], [3, 4]])
        self.assertIsInstance(result, list)
        for interval in result:
            self.assertIsInstance(interval, tuple)

    def test_bool_endpoints_raise_type_error(self):
        for bad_range in ((True, 2), (1, False), (False, True)):
            with self.assertRaises(TypeError):
                coalesce_ranges([bad_range])

    def test_non_integer_endpoints_raise_type_error(self):
        for bad_range in (
            (1.0, 2),
            (1, "2"),
            ("1", 2),
            (None, 2),
            (1, None),
            (1, object()),
        ):
            with self.assertRaises(TypeError):
                coalesce_ranges([bad_range])

    def test_start_greater_than_end_raises_value_error(self):
        with self.assertRaises(ValueError):
            coalesce_ranges([[5, 2]])

    def test_malformed_pairs_raise_type_error(self):
        for bad_item in ([], [1], [1, 2, 3], 5):
            with self.assertRaises(TypeError):
                coalesce_ranges([bad_item])

    def test_does_not_mutate_input_on_success(self):
        ranges = [[7, 9], [1, 4], [2, 3], [4, 8], [10, 10]]
        original = deepcopy(ranges)
        result = coalesce_ranges(ranges)
        self.assertEqual(result, [(1, 9)])
        self.assertEqual(ranges, original)

    def test_does_not_mutate_input_on_bool_type_error(self):
        ranges = [[2, 4], [1, 3], [True, 5]]
        original = deepcopy(ranges)
        with self.assertRaises(TypeError):
            coalesce_ranges(ranges)
        self.assertEqual(ranges, original)

    def test_does_not_mutate_input_on_non_integer_type_error(self):
        ranges = [[2, 4], [1, 3], [5, 6.0]]
        original = deepcopy(ranges)
        with self.assertRaises(TypeError):
            coalesce_ranges(ranges)
        self.assertEqual(ranges, original)

    def test_does_not_mutate_input_on_value_error(self):
        ranges = [[10, 20], [3, 1], [0, 5]]
        original = deepcopy(ranges)
        with self.assertRaises(ValueError):
            coalesce_ranges(ranges)
        self.assertEqual(ranges, original)


if __name__ == "__main__":
    unittest.main()