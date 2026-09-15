#!/usr/bin/env python3
"""Compile the R11 formal document; this does not run the proposed algorithms."""
from pathlib import Path
import argparse
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True)
    args = parser.parse_args()
    build = ROOT / 'docs/.build'
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(Path(args.engine).resolve()), '--keep-logs', '--keep-intermediates',
                    '--outdir', str(build), 'satnav.tex'], cwd=ROOT / 'docs', check=True)
    output = ROOT / 'output/pdf/aTOMos_v3_6_1_11_Exact_Operator_Seed_Formalization_Tom_Klootwijk.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(build / 'satnav.pdf', output)
    print(output)


if __name__ == '__main__':
    main()
