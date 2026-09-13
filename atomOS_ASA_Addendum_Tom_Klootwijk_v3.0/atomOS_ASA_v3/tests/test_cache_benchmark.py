"""Reject misleading cache captures without invoking a GPU or profiler."""
import contextlib
import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from scripts import benchmark_cache
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


class CacheCaptureValidation(unittest.TestCase):
    def run_benchmark(self, *, passes=1, kernel='asa_texture_kernel()',
                      mixed_identity=None, change_binary=False):
        """Feed realistic process records/CSV through the production reader."""
        with tempfile.TemporaryDirectory(prefix='asa_cache_reader_') as directory:
            root = Path(directory)
            executable = root/'asa_cuda.exe'
            executable.write_bytes(b'original executable')
            report = root/'report'
            calls = []

            def execute(command, **kwargs):
                calls.append(command)
                output = Path(command[command.index('--out')+1])
                output.mkdir()
                (output/'run.json').write_text(json.dumps({
                    'compute_ms':1., 'global_mean_ms':1., 'reorder_ms':0., 'restore_ms':0.
                }))
                (output/'results.bin').write_bytes(b'exact results')
                (output/'samples.f64x2').write_bytes(b'exact samples')
                stdout = 'synthetic subprocess output\n'
                if '--metrics' in command:
                    stream = io.StringIO()
                    writer = csv.DictWriter(stream, fieldnames=(
                        'ID', 'Process ID', 'Kernel Name', 'Context', 'Stream',
                        'Metric Name', 'Metric Unit', 'Metric Value'), quoting=csv.QUOTE_ALL)
                    writer.writeheader()
                    values = dict(zip(METRICS, (75., 75, 25, 100, 10)))
                    values[benchmark_cache.AGGREGATE_METRIC] = 75.
                    values['profiler__replayer_passes'] = passes
                    for index, name in enumerate(command[command.index('--metrics')+1].split(',')):
                        if values[name] is None:
                            continue
                        row = {'ID':'0', 'Process ID':'123', 'Kernel Name':kernel,
                               'Context':'1', 'Stream':'7', 'Metric Name':name,
                               'Metric Unit':'%' if name.endswith('.pct') else '',
                               'Metric Value':values[name]}
                        if mixed_identity and index == 1:
                            row[mixed_identity] = '999'
                        writer.writerow(row)
                    stdout += stream.getvalue()
                if change_binary and len(calls) == 1:
                    executable.write_bytes(b'replaced executable')
                return subprocess.CompletedProcess(command, 0, stdout=stdout)

            arguments = ['benchmark_cache.py', '--executable', str(executable),
                         '--ncu', str(root/'ncu.exe'), '--report-dir', str(report),
                         '--timing-runs', '1', '--profile-runs', '1']
            error = None
            with patch.object(benchmark_cache.sys, 'argv', arguments), \
                 patch.object(benchmark_cache.subprocess, 'run', side_effect=execute), \
                 patch.object(benchmark_cache, 'verify_directory', return_value={'status':'pass'}), \
                 patch.object(benchmark_cache, 'verify_execution_metadata'), \
                 contextlib.redirect_stdout(io.StringIO()):
                try:
                    benchmark_cache.main()
                except (RuntimeError, ValueError) as failure:
                    error = str(failure)
            return error, json.loads((report/'benchmark.json').read_text()), calls

    def test_single_capture_retains_existing_metrics(self):
        error, record, _ = self.run_benchmark()
        self.assertIsNone(error)
        self.assertEqual(record['status'], 'pass')
        for condition in record['conditions'].values():
            self.assertEqual(set(condition['profiles'][0]['metrics']), set(benchmark_cache.REQUESTED_METRICS))

    def test_missing_or_multiple_profiler_passes_cannot_pass(self):
        for passes in (None, 0, 2, 4):
            with self.subTest(passes=passes):
                error, record, _ = self.run_benchmark(passes=passes)
                self.assertIsNotNone(error)
                self.assertEqual(record['status'], 'fail')

    def test_wrong_texture_kernel_cannot_pass(self):
        for kernel in ('asa_global_kernel()', 'other_asa_texture_kernel()', ''):
            with self.subTest(kernel=kernel):
                error, record, _ = self.run_benchmark(kernel=kernel)
                self.assertIsNotNone(error)
                self.assertEqual(record['status'], 'fail')

    def test_metrics_from_different_captures_cannot_be_combined(self):
        for identity in ('ID', 'Process ID', 'Context', 'Stream'):
            with self.subTest(identity=identity):
                error, record, _ = self.run_benchmark(mixed_identity=identity)
                self.assertIsNotNone(error)
                self.assertEqual(record['status'], 'fail')

    def test_binary_replacement_stops_before_another_invocation(self):
        error, record, calls = self.run_benchmark(change_binary=True)
        self.assertIn('executable changed', error)
        self.assertEqual(record['status'], 'fail')
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
