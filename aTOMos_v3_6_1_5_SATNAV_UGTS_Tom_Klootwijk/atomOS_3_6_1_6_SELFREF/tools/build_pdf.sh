#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python tools/build_pdf.py "$@"
