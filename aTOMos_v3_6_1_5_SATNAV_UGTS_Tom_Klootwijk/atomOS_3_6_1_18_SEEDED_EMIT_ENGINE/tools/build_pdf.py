#!/usr/bin/env python3
"""Verify authored R18 inputs and compile the PDF; runtime evidence is separate."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
from prepare_document import NAME, digest, document_records, verify_release_sources

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True)
    args = parser.parse_args()
    verify_release_sources()
    inputs = document_records()
    build = ROOT / 'docs/.build'
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(Path(args.engine).resolve()), '--keep-logs', '--keep-intermediates',
                    '--outdir', str(build), 'unified.tex'], cwd=ROOT / 'docs', check=True)
    if document_records() != inputs:
        raise ValueError('Authored TeX changed during compilation; rebuild the final sources')
    output = ROOT / 'output/pdf' / (NAME + '.pdf')
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(build / 'unified.pdf', output)
    (build / 'source_inputs.json').write_text(json.dumps({
        'version': '3.6.1.18', 'pdf_sha256': digest(output), 'tex_inputs': inputs,
    }, indent=2) + '\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
