import unittest

import copy


def _is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def coalesce_ranges(ranges):
    """Merge half-open integer ranges, returning sorted disjoint tuples."""
    intervals = []

    for item in ranges:
        try:
            start, end = item
        except (TypeError, ValueError):
            raise TypeError("each range must be a pair of endpoints") from None

        if not _is_integer(start) or not _is_integer(end):
            raise TypeError("range endpoints must be integers and not bool")

        if start > end:
            raise ValueError("range start must not be greater than range end")

        if start == end:
            continue

        intervals.append((start, end))

    if not intervals:
        return []

    intervals.sort()
    merged = []

    for start, end in intervals:
        if not merged:
            merged.append((start, end))
            continue

        last_start, last_end = merged[-1]

        if start <= last_end:
            if end > last_end:
                merged[-1] = (last_start, end)
        else:
            merged.append((start, end))

    return merged


class TestCoalesceRangesMerging(unittest.TestCase):
    def test_merges_overlapping_ranges(self):
        self.assertEqual(
            coalesce_ranges([[1, 3], [7, 9], [2, 5]]),
            [(1, 5), (7, 9)],
        )

    def test_merges_touching_half_open_ranges(self):
        self.assertEqual(
            coalesce_ranges([[0, 2], [2, 4], [4, 5]]),
            [(0, 5)],
        )

    def test_sorts_input_ranges(self):
        self.assertEqual(
            coalesce_ranges([[10, 12], [1, 2], [-5, -4]]),
            [(-5, -4), (1, 2), (10, 12)],
        )

    def test_keeps_gapped_half_open_ranges_separate(self):
        self.assertEqual(
            coalesce_ranges([[3, 4], [1, 2]]),
            [(1, 2), (3, 4)],
        )

    def test_merges_nested_and_duplicate_ranges(self):
        self.assertEqual(
            coalesce_ranges([[1, 10], [2, 3], [2, 3], [4, 5], [1, 10]]),
            [(1, 10)],
        )

    def test_drops_zero_length_ranges(self):
        self.assertEqual(
            coalesce_ranges([[3, 3], [-1, -1], [0, 0]]),
            [],
        )

    def test_drops_zero_length_ranges_but_keeps_non_empty(self):
        self.assertEqual(
            coalesce_ranges([[-2, -2], [5, 6], [6, 6]]),
            [(5, 6)],
        )

    def test_zero_length_ranges_are_ignored_when_merging(self):
        self.assertEqual(
            coalesce_ranges([[1, 2], [2, 2], [3, 4]]),
            [(1, 2), (3, 4)],
        )

    def test_returns_sorted_list_of_tuples(self):
        result = coalesce_ranges([[10, 20], [1, 5], [5, 6], [15, 18]])

        self.assertEqual(result, [(1, 6), (10, 20)])
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(pair, tuple) for pair in result))


class TestCoalesceRangesValidation(unittest.TestCase):
    def test_rejects_non_integer_endpoints(self):
        cases = [
            [[0, 1.0]],
            [["0", "1"]],
            [[None, 1]],
            [[1, None]],
            [[0, object()]],
            [[2, 2.0]],
        ]

        for ranges in cases:
            with self.assertRaises(TypeError):
                coalesce_ranges(ranges)

    def test_rejects_bool_start_endpoints(self):
        cases = [
            [[True, 1]],
            [[True, False]],
            [[False, False]],
        ]

        for ranges in cases:
            with self.assertRaises(TypeError):
                coalesce_ranges(ranges)

    def test_rejects_bool_end_endpoints(self):
        cases = [
            [[0, False]],
            [[1, True]],
            [[False, True]],
        ]

        for ranges in cases:
            with self.assertRaises(TypeError):
                coalesce_ranges(ranges)

    def test_rejects_reversed_bounds(self):
        cases = [
            [[2, 1]],
            [[-1, -2]],
            [[5, 4]],
        ]

        for ranges in cases:
            with self.assertRaises(ValueError):
                coalesce_ranges(ranges)

    def test_equal_bounds_are_allowed_and_dropped(self):
        self.assertEqual(
            coalesce_ranges([[5, 5], [-3, -3], [0, 0]]),
            [],
        )


class TestCoalesceRangesMutation(unittest.TestCase):
    def test_does_not_mutate_input_on_success(self):
        ranges = [[4, 7], [1, 3], [3, 5], [9, 9]]
        original = copy.deepcopy(ranges)

        self.assertEqual(coalesce_ranges(ranges), [(1, 7)])
        self.assertEqual(ranges, original)

    def test_does_not_mutate_input_on_value_error(self):
        ranges = [[1, 2], [5, 4], [3, 3]]
        original = copy.deepcopy(ranges)

        with self.assertRaises(ValueError):
            coalesce_ranges(ranges)

        self.assertEqual(ranges, original)

    def test_does_not_mutate_input_on_type_error(self):
        ranges = [[1, 2], [3, "4"], [5, 6]]
        original = copy.deepcopy(ranges)

        with self.assertRaises(TypeError):
            coalesce_ranges(ranges)

        self.assertEqual(ranges, original)


class TestCoalesceRangesBoundaryValues(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(coalesce_ranges([]), [])

    def test_negative_bounds(self):
        self.assertEqual(
            coalesce_ranges([[-5, -2], [-2, 0], [-10, -5], [-1, 1]]),
            [(-10, 1)],
        )

    def test_negative_bounds_can_stay_disjoint(self):
        self.assertEqual(
            coalesce_ranges([[-4, -3], [-2, -1]]),
            [(-4, -3), (-2, -1)],
        )

    def test_large_integers(self):
        big = 10 ** 150

        self.assertEqual(
            coalesce_ranges([
                (big, big + 2),
                (big + 2, big + 5),
                (big + 10, big + 11),
            ]),
            [(big, big + 5), (big + 10, big + 11)],
        )

        negative_big = -(10 ** 200)

        self.assertEqual(
            coalesce_ranges([
                (negative_big, negative_big + 1),
                (negative_big + 1, negative_big + 3),
            ]),
            [(negative_big, negative_big + 3)],
        )


if __name__ == "__main__":
    unittest.main()