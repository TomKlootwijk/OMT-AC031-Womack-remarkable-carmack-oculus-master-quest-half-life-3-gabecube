"""Prevent locale-driven false cache measurements in the benchmark reader."""
import unittest
from scripts.benchmark_cache import profiler_number


class CacheMetricLocale(unittest.TestCase):
    def test_percentage_is_not_a_grouped_integer(self):
        self.assertEqual(profiler_number('67,82', True), 67.82)
        self.assertEqual(profiler_number('67.82', True), 67.82)
        self.assertEqual(profiler_number('100', True), 100)

    def test_sector_counts_accept_both_locales(self):
        for text in ('167.449', '167,449', '167449'):
            self.assertEqual(profiler_number(text, False), 167449)


if __name__ == '__main__':
    unittest.main()
