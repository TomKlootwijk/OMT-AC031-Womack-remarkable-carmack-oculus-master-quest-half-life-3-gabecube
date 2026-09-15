#!/usr/bin/env python3
"""Build the complete editable LaTeX source using Tectonic or latexmk."""
from pathlib import Path
import argparse, shutil, subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', help='Path to tectonic or latexmk (auto-detected otherwise)')
    args = parser.parse_args()
    engine = args.engine or shutil.which('tectonic') or shutil.which('latexmk')
    if not engine:
        parser.error('Install Tectonic or latexmk, or supply --engine PATH')
    build = ROOT/'docs'/'.build'
    output = ROOT/'output'/'pdf'
    build.mkdir(exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    if 'tectonic' in Path(engine).name.lower():
        command = [engine, '--keep-logs', '--keep-intermediates', '--outdir', str(build), 'satnav.tex']
    else:
        command = [engine, '-pdf', '-interaction=nonstopmode', '-halt-on-error', '-outdir='+str(build), 'satnav.tex']
    subprocess.run(command, cwd=ROOT/'docs', check=True)
    target = output/'aTOMos_v3_6_1_10_Orbital_Seed_Kernel_UGTS_Tom_Klootwijk.pdf'
    shutil.copy2(build/'satnav.pdf', target)
    print(target)

if __name__ == '__main__':
    main()
