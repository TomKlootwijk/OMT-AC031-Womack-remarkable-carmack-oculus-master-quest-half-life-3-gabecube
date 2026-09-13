"""Regression checks for truthful validation status and Windows tool discovery."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import validate
from scripts.integration import expect_exit, verify_execution_metadata


class ValidationContract(unittest.TestCase):
    def test_empty_run_cannot_claim_kernel_timing_or_launches(self):
        meta = {'samples':0,'gpu_executed':False,'sample_order':'locality',
                'warmup_runs_per_path':0,'timed_runs_per_path':0,'compute_ms':0,
                **{key:0 for key in ('reorder_ms','restore_ms','texture_mean_ms','texture_min_ms','global_mean_ms','global_min_ms')}}
        args = ['--sample-order','locality','--warmup','2','--repeat','3']
        verify_execution_metadata(meta,args,True)
        for key,value in (('gpu_executed',True),('timed_runs_per_path',3),('texture_mean_ms',1)):
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                verify_execution_metadata({**meta,key:value},args,True)

    def test_timing_metadata_matches_measured_repetitions_and_order(self):
        meta = {'samples':257,'gpu_executed':True,'sample_order':'locality',
                'warmup_runs_per_path':2,'timed_runs_per_path':3,'compute_ms':1,
                'reorder_ms':.5,'restore_ms':.2,'texture_mean_ms':1,'texture_min_ms':.9,
                'global_mean_ms':1.2,'global_min_ms':1.1}
        args = ['--sample-order','locality','--warmup','2','--repeat','3']
        verify_execution_metadata(meta,args,True)
        for key,value in (('timed_runs_per_path',1),('sample_order','natural'),('restore_ms',float('nan')),('compute_ms',4)):
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                verify_execution_metadata({**meta,key:value},args,True)

    def test_crash_is_not_a_clean_rejection(self):
        expect_exit(subprocess.CompletedProcess([], 1, '', 'rejected'), False)
        for returncode in (-11, 0xc0000005, 2, 0):
            with self.subTest(returncode=returncode), self.assertRaises(RuntimeError):
                expect_exit(subprocess.CompletedProcess([], returncode, '', ''), False)

    def invoke(self, args=(), outcomes=None, tool_resolver=None):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(validate, 'resolve_tool', side_effect=tool_resolver or (lambda name: name)), \
                    patch.object(validate.subprocess, 'run', side_effect=outcomes) as runner, \
                    redirect_stdout(StringIO()):
                if outcomes is None:
                    runner.return_value = subprocess.CompletedProcess([], 0, 'passed\n')
                code = validate.main(['--report-dir', str(Path(tmp)/'report'), '--build-dir', str(Path(tmp)/'build'), *args])
            status = json.loads((Path(tmp)/'report'/'status.json').read_text())
            return code, status, runner.call_args_list

    def test_cpu_sanitizer_unavailable_is_not_pass(self):
        code, status, calls = self.invoke(['--sanitizer'], [
            subprocess.CompletedProcess([], 1, validate.HOST_SANITIZER_UNAVAILABLE+': MSVC\n')])
        self.assertEqual((code, status['status']), (2, 'unavailable'))
        self.assertEqual(len(calls), 1)
        self.assertTrue(status['sanitizer_requested'])

    def test_compiler_failure_is_not_tool_unavailable(self):
        code, status, calls = self.invoke(outcomes=[subprocess.CompletedProcess([], 1, 'compile error\n')])
        self.assertEqual((code, status['status']), (1, 'fail'))
        self.assertEqual(len(calls), 1)

    def test_launch_failure_leaves_a_status_record(self):
        code, status, calls = self.invoke(outcomes=[FileNotFoundError('program missing')])
        self.assertEqual((code, status['status']), (2, 'unavailable'))
        self.assertIsNone(status['steps'][0]['returncode'])
        self.assertEqual(status['steps'][0]['status'], 'unavailable')

    def test_missing_ctest_cannot_silently_omit_tests(self):
        code, status, calls = self.invoke(tool_resolver=lambda name: None if name == 'ctest' else name)
        self.assertEqual((code, status['status']), (2, 'unavailable'))
        self.assertEqual(calls, [])

    def test_python_and_configure_selection_are_recorded(self):
        arg = '-Tcuda=C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.8'
        code, status, calls = self.invoke(['--cmake-arg='+arg])
        self.assertEqual((code, status['status']), (0, 'pass'))
        command = status['steps'][0]['command']
        self.assertIn(arg, command)
        self.assertIn('-DPython3_EXECUTABLE='+sys.executable, command)

    def test_sanitizer_failure_stops_and_is_recorded(self):
        ok = subprocess.CompletedProcess([], 0, 'passed\n')
        code, status, calls = self.invoke(['--gpu', '--sanitizer'],
                                         [ok, ok, ok, ok, subprocess.CompletedProcess([], 1, 'ERROR SUMMARY: 1 error\n')])
        self.assertEqual((code, status['status']), (1, 'fail'))
        self.assertEqual(status['steps'][-1]['name'], 'memcheck')

    def test_all_sanitizers_cover_regular_and_focused_device_paths(self):
        code, status, calls = self.invoke(['--gpu', '--sanitizer'])
        self.assertEqual((code, status['status']), (0, 'pass'))
        stages = {step['name']: step['command'] for step in status['steps']}
        self.assertIn('-DASA_SANITIZE=OFF', stages['configure'])
        for name in ('memcheck', 'initcheck', 'racecheck', 'synccheck'):
            self.assertIn(name, stages)
            self.assertIn(name+'_locality', stages)
            self.assertIn(name+'_boundaries', stages)
            self.assertIn('--repeat', stages[name+'_locality'])
            self.assertIn('locality', stages[name+'_locality'])
            for step in (name, name+'_locality', name+'_boundaries'):
                self.assertIn('--error-exitcode', stages[step])
                self.assertEqual(stages[step][stages[step].index('--error-exitcode')+1], '1')

    def test_windows_sanitizer_wrapper_resolves_to_native_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            toolkit = Path(tmp)/'CUDA with spaces'
            wrapper = toolkit/'bin'/'compute-sanitizer.bat'
            native = toolkit/'compute-sanitizer'/'compute-sanitizer.exe'
            native.parent.mkdir(parents=True)
            native.write_bytes(b'fixture')
            with patch.object(validate.shutil, 'which', return_value=str(wrapper)):
                self.assertEqual(validate.resolve_tool('compute-sanitizer'), str(native))

    def test_broken_windows_sanitizer_wrapper_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrapper = Path(tmp)/'CUDA'/'bin'/'compute-sanitizer.bat'
            with patch.object(validate.shutil, 'which', return_value=str(wrapper)):
                self.assertIsNone(validate.resolve_tool('compute-sanitizer'))


if __name__ == '__main__':
    unittest.main()
