#!/usr/bin/env python3
"""Execute focused device fixtures and independently check every saved case."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.reference import verify_directory

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--executable', type=Path, required=True)
a = p.parse_args()
with tempfile.TemporaryDirectory(prefix='asa_cuda_boundaries_') as tmp:
    output = Path(tmp)/'run'
    result = subprocess.run([str(a.executable.resolve()), '--out', str(output)],
                            text=True, capture_output=True)
    print(result.stdout, end='')
    if result.returncode:
        raise RuntimeError(result.stderr)
    directories = sorted(output.glob('case_*/run.json'))
    if not directories:
        raise RuntimeError('focused CUDA fixture emitted no independently checkable cases')
    cases = []
    matching_records = {}
    for metadata_path in directories:
        meta = json.loads(metadata_path.read_text())
        if meta['gpu_executed'] is not True or meta['samples'] == 0:
            raise RuntimeError('focused case did not record device execution')
        key = (json.dumps(meta['config'],sort_keys=True),meta['samples'])
        records = ((metadata_path.parent/'samples.f64x2').read_bytes(),(metadata_path.parent/'results.bin').read_bytes())
        if key in matching_records:
            previous_order, previous_records = matching_records.pop(key)
            if {previous_order, meta['sample_order']} != {'natural','locality'} or previous_records != records:
                raise RuntimeError('focused natural/locality sample or result bytes differ')
        else:
            matching_records[key] = (meta['sample_order'], records)
        cases.append({'case': metadata_path.parent.name, 'config': meta['config'], 'sample_order':meta['sample_order'],
                      **verify_directory(metadata_path.parent)})
    if matching_records:
        raise RuntimeError('focused cases must include both natural and locality scheduling for every configuration')
    print(json.dumps({'status': 'pass', 'cases': cases}, indent=2))
