import unittest


def _is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def coalesce_ranges(ranges):
    """Coalesce half-open integer intervals into sorted disjoint tuples."""
    try:
        iterator = iter(ranges)
    except TypeError:
        raise TypeError("ranges must be an iterable of pairs") from None

    checked = []
    for index, pair in enumerate(iterator):
        try:
            start, end = pair
        except (TypeError, ValueError):
            raise TypeError(f"range at index {index} must be a pair of integers") from None

        if not _is_integer(start) or not _is_integer(end):
            raise TypeError(f"range at index {index} must have integer endpoints")

        start = int(start)
        end = int(end)

        if start > end:
            raise ValueError(f"range at index {index} has start greater than end")

        if start != end:
            checked.append((start, end))

    checked.sort()

    merged = []
    for start, end in checked:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        elif end > merged[-1][1]:
            merged[-1] = (merged[-1][0], end)

    return merged


class CoalesceRangesTests(unittest.TestCase):
    def test_overlap_merges(self):
        self.assertEqual(
            coalesce_ranges([(1, 4), (2, 6)]),
            [(1, 6)],
        )

    def test_touching_merges(self):
        self.assertEqual(
            coalesce_ranges([(1, 2), (2, 3)]),
            [(1, 3)],
        )
        self.assertEqual(
            coalesce_ranges([(-5, -3), (-3, 0)]),
            [(-5, 0)],
        )

    def test_disjoint_ranges_are_sorted(self):
        self.assertEqual(
            coalesce_ranges([(8, 10), (1, 2), (4, 5)]),
            [(1, 2), (4, 5), (8, 10)],
        )

    def test_zero_length_ranges_are_dropped(self):
        self.assertEqual(
            coalesce_ranges([(1, 1), (3, 4), (5, 5), (-2, -2)]),
            [(3, 4)],
        )

    def test_empty_input(self):
        self.assertEqual(coalesce_ranges([]), [])
        self.assertIsInstance(coalesce_ranges([]), list)

    def test_output_items_are_tuples(self):
        result = coalesce_ranges([[1, 2]])
        self.assertEqual(result, [(1, 2)])
        self.assertIsInstance(result[0], tuple)

    def test_bool_endpoints_are_rejected(self):
        for pair in [(True, 2), (1, False), (False, False)]:
            with self.subTest(pair=pair):
                with self.assertRaises(TypeError):
                    coalesce_ranges([pair])

    def test_non_integer_endpoints_are_rejected(self):
        for pair in [(1.0, 2), (1, 2.0), ("1", 2), (1, None), (2, b"3")]:
            with self.subTest(pair=pair):
                with self.assertRaises(TypeError):
                    coalesce_ranges([pair])

    def test_start_greater_than_end_is_rejected(self):
        with self.assertRaises(ValueError):
            coalesce_ranges([(5, 4)])

    def test_input_is_not_mutated_on_success(self):
        ranges = [[5, 8], [1, 4], [3, 6]]
        snapshot = [pair[:] for pair in ranges]

        self.assertEqual(coalesce_ranges(ranges), [(1, 8)])
        self.assertEqual(ranges, snapshot)

    def test_input_is_not_mutated_on_value_error(self):
        ranges = [[5, 3], [1, 4]]
        snapshot = [pair[:] for pair in ranges]

        with self.assertRaises(ValueError):
            coalesce_ranges(ranges)

        self.assertEqual(ranges, snapshot)

    def test_input_is_not_mutated_on_type_error(self):
        ranges = [[1.5, 2], [3, 4]]
        snapshot = [pair[:] for pair in ranges]

        with self.assertRaises(TypeError):
            coalesce_ranges(ranges)

        self.assertEqual(ranges, snapshot)

    def test_negative_and_large_integers(self):
        large = 10**120
        ranges = [
            (-large, -large + 5),
            (-large + 3, -large + 8),
            (large, large + 2),
            (large + 1, large + 9),
        ]

        self.assertEqual(
            coalesce_ranges(ranges),
            [(-large, -large + 8), (large, large + 9)],
        )

    def test_half_open_gap_does_not_merge(self):
        self.assertEqual(
            coalesce_ranges([(1, 2), (3, 4)]),
            [(1, 2), (3, 4)],
        )


if __name__ == "__main__":
    unittest.main()
