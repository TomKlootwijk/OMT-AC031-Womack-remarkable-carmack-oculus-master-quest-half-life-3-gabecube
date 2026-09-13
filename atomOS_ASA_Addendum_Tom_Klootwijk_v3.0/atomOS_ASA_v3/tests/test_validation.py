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

NORMAL_POLICY = {'l2_policy':'normal','l2_policy_active':False,'l2_requested_bytes':0,
                 'l2_accepted_bytes':0,'l2_window_bytes':0,'l2_hit_ratio':0,
                 'l2_window_base_address':0,'l2_hit_property':0,'l2_miss_property':0,
                 'l2_cache_bytes':0,'persisting_l2_max_bytes':0,'access_policy_max_window_bytes':0}


class ValidationContract(unittest.TestCase):
    def test_backend_defaults_are_recorded_correctly(self):
        meta = {**NORMAL_POLICY,'samples':257,'gpu_executed':True,'sample_order':'locality','block_size':512,
                'warmup_runs_per_path':0,'timed_runs_per_path':1,'compute_ms':1,
                'reorder_ms':.5,'restore_ms':.2,'texture_mean_ms':1,'texture_min_ms':1,
                'global_mean_ms':1.2,'global_min_ms':1.2}
        verify_execution_metadata(meta,[],True)
        for key,value in (('sample_order','natural'),('block_size',256)):
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                verify_execution_metadata({**meta,key:value},[],True)
        cpu = {**meta,'gpu_executed':False,'sample_order':'natural','block_size':0,'timed_runs_per_path':0,
               **{key:0 for key in ('texture_mean_ms','texture_min_ms','global_mean_ms','global_min_ms')}}
        verify_execution_metadata(cpu,[],False)

    def test_empty_run_cannot_claim_kernel_timing_or_launches(self):
        meta = {**NORMAL_POLICY,'samples':0,'gpu_executed':False,'sample_order':'locality',
                'warmup_runs_per_path':0,'timed_runs_per_path':0,'compute_ms':0,'block_size':0,
                **{key:0 for key in ('reorder_ms','restore_ms','texture_mean_ms','texture_min_ms','global_mean_ms','global_min_ms')}}
        args = ['--sample-order','locality','--warmup','2','--repeat','3','--block-size','1024']
        verify_execution_metadata(meta,args,True)
        for key,value in (('gpu_executed',True),('timed_runs_per_path',3),('texture_mean_ms',1),('block_size',1024)):
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                verify_execution_metadata({**meta,key:value},args,True)

    def test_timing_metadata_matches_measured_repetitions_and_order(self):
        meta = {**NORMAL_POLICY,'samples':257,'gpu_executed':True,'sample_order':'locality',
                'warmup_runs_per_path':2,'timed_runs_per_path':3,'compute_ms':1,'block_size':512,
                'reorder_ms':.5,'restore_ms':.2,'texture_mean_ms':1,'texture_min_ms':.9,
                'global_mean_ms':1.2,'global_min_ms':1.1}
        args = ['--sample-order','locality','--warmup','2','--repeat','3','--block-size','512']
        verify_execution_metadata(meta,args,True)
        for key,value in (('timed_runs_per_path',1),('sample_order','natural'),('restore_ms',float('nan')),('compute_ms',4),('block_size',256)):
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                verify_execution_metadata({**meta,key:value},args,True)

    def test_persisting_policy_requires_real_execution_and_supported_window(self):
        meta = {**NORMAL_POLICY,'samples':257,'gpu_executed':True,'sample_order':'locality','block_size':512,
                'warmup_runs_per_path':0,'timed_runs_per_path':1,'compute_ms':1,
                'reorder_ms':.5,'restore_ms':.2,'texture_mean_ms':1,'texture_min_ms':1,
                'global_mean_ms':1.2,'global_min_ms':1.2,'config':{'rho_bins':8,'phi_bins':8},
                'l2_policy':'persist-image','l2_policy_active':True,'l2_requested_bytes':256,
                'l2_accepted_bytes':256,'l2_window_bytes':256,'l2_hit_ratio':1,
                'l2_window_base_address':4096,'l2_hit_property':2,'l2_miss_property':0,
                'l2_cache_bytes':4096,'persisting_l2_max_bytes':2048,'access_policy_max_window_bytes':8192}
        args = ['--l2-policy','persist-image']
        verify_execution_metadata(meta,args,True)
        for key,value in (('l2_policy_active',False),('l2_window_bytes',257),('l2_accepted_bytes',0),
                          ('l2_hit_ratio',float('nan')),('l2_requested_bytes',4096),('l2_window_base_address',0),
                          ('l2_hit_property',0),('l2_miss_property',1)):
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                verify_execution_metadata({**meta,key:value},args,True)
        empty = {**meta,'samples':0,'gpu_executed':False,'block_size':0,'timed_runs_per_path':0,
                 'compute_ms':0,'l2_policy_active':False,
                 **{key:0 for key in ('texture_mean_ms','texture_min_ms','global_mean_ms','global_min_ms',
                                      'l2_requested_bytes','l2_accepted_bytes','l2_window_bytes','l2_hit_ratio',
                                      'l2_window_base_address','l2_hit_property','l2_miss_property')}}
        verify_execution_metadata(empty,args,True)
        with self.assertRaises(RuntimeError):
            verify_execution_metadata({**empty,'l2_accepted_bytes':256},args,True)

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
            self.assertIn(name+'_persist_image', stages)
            self.assertIn(name+'_boundaries', stages)
            self.assertIn('--repeat', stages[name+'_locality'])
            self.assertIn('locality', stages[name+'_locality'])
            self.assertIn('natural', stages[name])
            self.assertIn('persist-image', stages[name+'_persist_image'])
            for step in (name,name+'_locality',name+'_persist_image'):
                self.assertEqual(stages[step][stages[step].index('--block-size')+1], '512')
            for step in (name, name+'_locality', name+'_persist_image', name+'_boundaries'):
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
