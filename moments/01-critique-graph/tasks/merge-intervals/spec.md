Write `merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]`. Each interval is `(start, end)`
with `start <= end`, closed on both ends. Return the union as non-overlapping intervals sorted by start. Intervals
that overlap or touch (`(1, 2)` and `(2, 3)`) merge into one. The input may be unsorted and must not be modified.
