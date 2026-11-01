from __future__ import annotations

from collections.abc import Sequence
import unittest


def _is_integer_endpoint(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def coalesce_ranges(ranges):
    intervals = []

    for pair in ranges:
        if not isinstance(pair, Sequence) or isinstance(pair, (str, bytes, bytearray)):
            raise TypeError("each range must be a pair of integer endpoints")
        if len(pair) != 2:
            raise TypeError("each range must be a pair of integer endpoints")

        start = pair[0]
        end = pair[1]

        if not _is_integer_endpoint(start) or not _is_integer_endpoint(end):
            raise TypeError("range endpoints must be integers; bool is not accepted")

        if start > end:
            raise ValueError("range start must not exceed range end")

        if start == end:
            continue

        intervals.append((start, end))

    intervals.sort()

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


class CoalesceRangesTests(unittest.TestCase):
    def test_empty_input_returns_empty_list(self):
        self.assertEqual(coalesce_ranges([]), [])

    def test_single_nonempty_range_is_returned_as_tuple(self):
        self.assertEqual(coalesce_ranges([(3, 7)]), [(3, 7)])

    def test_overlapping_ranges_merge(self):
        self.assertEqual(coalesce_ranges([(1, 4), (3, 6)]), [(1, 6)])

    def test_touching_ranges_merge(self):
        self.assertEqual(coalesce_ranges([(1, 2), (2, 5)]), [(1, 5)])

    def test_nested_range_is_absorbed(self):
        self.assertEqual(coalesce_ranges([(1, 10), (3, 4)]), [(1, 10)])

    def test_disjoint_ranges_are_sorted_and_kept_separate(self):
        self.assertEqual(coalesce_ranges([(7, 9), (1, 3)]), [(1, 3), (7, 9)])

    def test_zero_length_ranges_are_dropped(self):
        self.assertEqual(coalesce_ranges([(2, 2), (5, 5)]), [])

    def test_zero_length_does_not_prevent_touching_merge(self):
        self.assertEqual(coalesce_ranges([(1, 2), (2, 2), (2, 3)]), [(1, 3)])

    def test_negative_bounds(self):
        self.assertEqual(
            coalesce_ranges([(-2, 3), (-10, -7), (-5, -2)]),
            [(-10, -7), (-5, 3)],
        )

    def test_very_large_positive_and_negative_integers(self):
        h = 10**100
        self.assertEqual(
            coalesce_ranges(
                [
                    (h + 5, h + 10),
                    (h, h + 6),
                    (-h - 10, -h - 5),
                    (-h - 5, -h - 1),
                ]
            ),
            [(-h - 10, -h - 1), (h, h + 10)],
        )

    def test_bool_start_endpoint_is_rejected_with_type_error(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([(True, 3)])

    def test_bool_end_endpoint_is_rejected_with_type_error(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([(1, False)])

    def test_float_start_endpoint_is_rejected_with_type_error(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([(1.5, 3)])

    def test_string_end_endpoint_is_rejected_with_type_error(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([(1, "3")])

    def test_none_endpoint_is_rejected_with_type_error(self):
        with self.assertRaises(TypeError):
            coalesce_ranges([(None, 3)])

    def test_start_greater_than_end_raises_value_error(self):
        with self.assertRaises(ValueError):
            coalesce_ranges([(5, 2)])

    def test_input_is_not_mutated_on_success(self):
        ranges = [[5, 8], [1, 4], [3, 6]]
        snapshot = [[5, 8], [1, 4], [3, 6]]
        result = coalesce_ranges(ranges)
        self.assertEqual(ranges, snapshot)
        self.assertEqual(result, [(1, 8)])

    def test_input_is_not_mutated_on_type_error(self):
        ranges = [[3, 7], [1, 5], [True, 9]]
        snapshot = [[3, 7], [1, 5], [True, 9]]
        with self.assertRaises(TypeError):
            coalesce_ranges(ranges)
        self.assertEqual(ranges, snapshot)

    def test_input_is_not_mutated_on_value_error(self):
        ranges = [[8, 9], [1, 2], [6, 4]]
        snapshot = [[8, 9], [1, 2], [6, 4]]
        with self.assertRaises(ValueError):
            coalesce_ranges(ranges)
        self.assertEqual(ranges, snapshot)

    def test_mixed_list_and_tuple_pairs_are_accepted(self):
        self.assertEqual(
            coalesce_ranges([(1, 3), [2, 5], (7, 9)]),
            [(1, 5), (7, 9)],
        )

    def test_returns_only_tuples(self):
        result = coalesce_ranges([(9, 10), (1, 2)])
        self.assertTrue(all(isinstance(item, tuple) for item in result))


if __name__ == "__main__":
    unittest.main()