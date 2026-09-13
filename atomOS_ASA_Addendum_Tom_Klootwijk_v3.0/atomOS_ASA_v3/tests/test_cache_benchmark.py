"""Prevent locale-driven false cache measurements in the benchmark reader."""
import unittest
from scripts.benchmark_cache import METRICS, profiler_number, validate_metrics


class CacheMetricLocale(unittest.TestCase):
    def test_percentage_is_not_a_grouped_integer(self):
        self.assertEqual(profiler_number('67,82', True), 67.82)
        self.assertEqual(profiler_number('67.82', True), 67.82)
        self.assertEqual(profiler_number('100', True), 100)

    def test_sector_counts_accept_both_locales(self):
        for text in ('167.449', '167,449', '167449'):
            self.assertEqual(profiler_number(text, False), 167449)

    def test_nonfinite_or_empty_texture_work_cannot_pass(self):
        good = dict(zip(METRICS, (75., 75., 25., 100., 10.)))
        validate_metrics(good)
        for key, bad in ((METRICS[0], float('nan')), (METRICS[0], 101.),
                         (METRICS[3], 0.), (METRICS[4], 0.), (METRICS[1], 74.)):
            values = {**good, key: bad}
            with self.assertRaises(ValueError):
                validate_metrics(values)


if __name__ == '__main__':
    unittest.main()
