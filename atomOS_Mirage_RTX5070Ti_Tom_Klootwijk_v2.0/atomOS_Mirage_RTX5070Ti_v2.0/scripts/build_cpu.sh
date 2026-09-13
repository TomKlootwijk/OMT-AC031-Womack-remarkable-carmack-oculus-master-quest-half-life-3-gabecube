#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DATOMOS_ENABLE_CUDA=OFF
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
./build/atomos_cpu --generations 12 --verify --out run_results
ATOMOS_PROBE="$PWD/build/atomos_probe" ATOMOS_RUN="$PWD/run_results" \
    python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/verify_journal.py run_results
