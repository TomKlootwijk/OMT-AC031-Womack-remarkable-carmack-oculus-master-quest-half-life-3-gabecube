#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 tools/validate.py --gpu --sanitizer "$@"
