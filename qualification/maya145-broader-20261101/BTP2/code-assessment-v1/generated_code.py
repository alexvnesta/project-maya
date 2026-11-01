import copy
import unittest


def _require_integer_endpoint(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("range endpoints must be integers and not bool")


def coalesce_ranges(ranges):
    intervals = []

    for index, item in enumerate(ranges):
        try:
            if len(item) != 2:
                raise TypeError
            start = item[0]
            end = item[1]
        except (TypeError, ValueError, IndexError, KeyError):
            raise TypeError(
                f"range at index {index} must be a pair of integer endpoints"
            ) from None

        _require_integer_endpoint(start)
        _require_integer_endpoint(end)

        if start > end:
            raise ValueError("range start must not be greater than end")

        if start != end:
            intervals.append((start, end))

    intervals.sort(key=lambda interval: (interval[0], interval[1]))

    merged = []
    for start, end in intervals:
        if not merged:
            merged.append((start, end))
            continue

        previous_start, previous_end = merged[-1]
        if start <= previous_end:
            if end > previous_end:
                merged[-1] = (previous_start, end)
        else:
            merged.append((start, end))

    return merged


class CoalesceRangesTests(unittest.TestCase):
    def test_empty_input_returns_empty_list(self):
        self.assertEqual(coalesce_ranges([]), [])

    def test_returns_sorted_disjoint_tuples(self):
        result = coalesce_ranges([[5, 7], [1, 2], [3, 4]])
        self.assertEqual(result, [(1, 2), (3, 4), (5, 7)])
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(interval, tuple) for interval in result))

    def test_merges_overlapping_ranges(self):
        self.assertEqual(coalesce_ranges([[1, 5], [2, 6]]), [(1, 6)])

    def test_merges_touching_ranges(self):
        self.assertEqual(coalesce_ranges([[1, 3], [3, 5]]), [(1, 5)])

    def test_merges_contained_range(self):
        self.assertEqual(coalesce_ranges([[1, 10], [3, 4]]), [(1, 10)])

    def test_merges_chain_of_touching_and_overlapping_ranges(self):
        self.assertEqual(
            coalesce_ranges([[1, 3], [5, 7], [3, 5], [10, 11]]),
            [(1, 7), (10, 11)],
        )

    def test_drops_zero_length_ranges(self):
        self.assertEqual(
            coalesce_ranges([[3, 3], [1, 2], [2, 2], [5, 6], [4, 4]]),
            [(1, 2), (5, 6)],
        )

    def test_supports_negative_bounds(self):
        self.assertEqual(
            coalesce_ranges([[-10, -5], [-5, 0], [-20, -15], [2, 3]]),
            [(-20, -15), (-10, 0), (2, 3)],
        )

    def test_supports_large_integers(self):
        big = 10 ** 100
        self.assertEqual(
            coalesce_ranges([(big + 5, big + 10), (big, big + 5)]),
            [(big, big + 10)],
        )

    def test_does_not_mutate_input_on_success(self):
        ranges = [[5, 7], [1, 3], [3, 5]]
        original = copy.deepcopy(ranges)
        result = coalesce_ranges(ranges)
        self.assertEqual(ranges, original)
        self.assertEqual(result, [(1, 7)])

    def test_rejects_bool_start_with_type_error_without_mutation(self):
        ranges = [[True, 5], [1, 2]]
        original = copy.deepcopy(ranges)
        with self.assertRaises(TypeError):
            coalesce_ranges(ranges)
        self.assertEqual(ranges, original)

    def test_rejects_bool_end_with_type_error_without_mutation(self):
        ranges = [[1, False], [2, 3]]
        original = copy.deepcopy(ranges)
        with self.assertRaises(TypeError):
            coalesce_ranges(ranges)
        self.assertEqual(ranges, original)

    def test_rejects_bool_even_for_zero_length_range(self):
        ranges = [[True, True]]
        original = copy.deepcopy(ranges)
        with self.assertRaises(TypeError):
            coalesce_ranges(ranges)
        self.assertEqual(ranges, original)

    def test_rejects_non_integer_endpoints_with_type_error_without_mutation(self):
        cases = [
            [[1.5, 2]],
            [[1, 2.5]],
            [["1", 2]],
            [[1, "2"]],
            [[None, 2]],
            [[1, None]],
        ]
        for ranges in cases:
            with self.subTest(ranges=ranges):
                original = copy.deepcopy(ranges)
                with self.assertRaises(TypeError):
                    coalesce_ranges(ranges)
                self.assertEqual(ranges, original)

    def test_rejects_start_greater_than_end_with_value_error_without_mutation(self):
        cases = [
            [[5, 4]],
            [[-1, -2]],
            [[0, 1], [10, 9]],
        ]
        for ranges in cases:
            with self.subTest(ranges=ranges):
                original = copy.deepcopy(ranges)
                with self.assertRaises(ValueError):
                    coalesce_ranges(ranges)
                self.assertEqual(ranges, original)

    def test_rejects_malformed_ranges_with_type_error_without_mutation(self):
        cases = [
            [[1, 2, 3]],
            [[1]],
            [1],
            [[1, 2], [3]],
        ]
        for ranges in cases:
            with self.subTest(ranges=ranges):
                original = copy.deepcopy(ranges)
                with self.assertRaises(TypeError):
                    coalesce_ranges(ranges)
                self.assertEqual(ranges, original)


if __name__ == "__main__":
    unittest.main()