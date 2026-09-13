#!/usr/bin/env python3
"""Build, test and record real tool outcomes. Run from any working directory."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_SANITIZER_UNAVAILABLE = 'ASA_HOST_SANITIZER_UNAVAILABLE'


class StageFailure(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def resolve_tool(name: str) -> str | None:
    found = shutil.which(name)
    if name == 'compute-sanitizer' and found and Path(found).suffix.lower() in ('.bat', '.cmd'):
        # NVIDIA's Windows bin wrapper cannot be launched as a bare program by Popen.
        # Use the executable in the same toolkit, without shell parsing of arguments.
        native = Path(found).parent.parent/'compute-sanitizer'/'compute-sanitizer.exe'
        return str(native) if native.is_file() else None
    return found


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gpu', action='store_true')
    p.add_argument('--sanitizer', action='store_true')
    p.add_argument('--build-dir', type=Path)
    p.add_argument('--report-dir', type=Path, default=Path('local_validation'))
    p.add_argument('--cmake-arg', action='append', default=[],
                   help='Extra configure argument; repeat as --cmake-arg=VALUE (for example --cmake-arg=-G then --cmake-arg=Ninja).')
    a = p.parse_args(argv)
    report = a.report_dir.resolve()
    report.mkdir(parents=True, exist_ok=True)
    record = {'schema': 'atomOS.ASA.v3.validation', 'gpu_requested': a.gpu,
              'sanitizer_requested': a.sanitizer, 'steps': []}

    def done(code: int, reason: str) -> int:
        record['status'] = 'pass' if code == 0 else ('unavailable' if code == 2 else 'fail')
        record['message'] = reason
        (report/'status.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
        print(reason)
        return code

    def run(name, cmd):
        cmd = list(map(str, cmd))
        try:
            result = subprocess.run(cmd, cwd=ROOT, text=True, encoding='utf-8', errors='replace',
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as error:
            (report/(name+'.log')).write_text(str(error)+'\n', encoding='utf-8')
            record['steps'].append({'name': name, 'command': cmd, 'returncode': None,
                                    'status': 'unavailable', 'error': str(error)})
            raise StageFailure(2, name+' could not start; see '+str(report/(name+'.log'))) from error
        (report/(name+'.log')).write_text(result.stdout, encoding='utf-8')
        record['steps'].append({'name': name, 'command': cmd, 'returncode': result.returncode})
        if result.returncode:
            if name == 'configure' and HOST_SANITIZER_UNAVAILABLE in result.stdout:
                raise StageFailure(2, 'Requested host ASan/UBSan is unavailable with this compiler; no sanitizer pass is claimed. See '+str(report/'configure.log'))
            raise StageFailure(1, name+' failed; see '+str(report/(name+'.log')))

    required = ['cmake', 'ctest']
    if a.gpu:
        required.append('nvcc')
        if a.sanitizer:
            required.append('compute-sanitizer')
    tool_paths = {tool: resolve_tool(tool) for tool in required}
    for tool in required:
        if not tool_paths[tool]:
            return done(2, tool+' is not available; requested validation was not executed.')
    record['tools'] = tool_paths
    build = (a.build_dir or ROOT/('build_gpu' if a.gpu else ('build_sanitize' if a.sanitizer else 'build'))).resolve()
    configure = [tool_paths['cmake'], '-S', ROOT, '-B', build, '-DCMAKE_BUILD_TYPE=Release', *a.cmake_arg,
                 '-DPython3_EXECUTABLE='+sys.executable]
    if a.gpu:
        configure += ['-DASA_ENABLE_CUDA=ON', '-DASA_SANITIZE=OFF', '-DCMAKE_CUDA_ARCHITECTURES=120-real;120-virtual']
    else:
        configure += ['-DASA_ENABLE_CUDA=OFF', '-DASA_SANITIZE='+('ON' if a.sanitizer else 'OFF')]

    def executable(name):
        path = build/(name+'.exe' if os.name == 'nt' else name)
        return path if path.exists() else build/'Release'/(name+'.exe')

    try:
        run('configure', configure)
        run('build', [tool_paths['cmake'], '--build', build, '--config', 'Release', '--parallel', '2'])
        run('ctest', [tool_paths['ctest'], '--test-dir', build, '-C', 'Release', '--output-on-failure'])
        if a.gpu:
            exe = executable('asa_cuda')
            run('device', [exe, '--device-info'])
            if a.sanitizer:
                for tool in ('memcheck', 'initcheck', 'racecheck', 'synccheck'):
                    with tempfile.TemporaryDirectory(prefix='asa_cuda_'+tool+'_') as name:
                        run(tool, [tool_paths['compute-sanitizer'], '--tool', tool, '--error-exitcode', '1',
                                   exe, '--samples', '4097', '--out', Path(name)/'run'])
                        run(tool+'_locality', [tool_paths['compute-sanitizer'], '--tool', tool, '--error-exitcode', '1',
                                              exe, '--samples', '4097', '--sample-order', 'locality',
                                              '--warmup', '2', '--repeat', '3', '--out', Path(name)/'locality'])
                        run(tool+'_boundaries', [tool_paths['compute-sanitizer'], '--tool', tool, '--error-exitcode', '1',
                                              executable('asa_cuda_tests')])
    except StageFailure as error:
        return done(error.code, str(error))
    return done(0, 'All requested build and test stages passed. Reports: '+str(report))


if __name__ == '__main__':
    raise SystemExit(main())
