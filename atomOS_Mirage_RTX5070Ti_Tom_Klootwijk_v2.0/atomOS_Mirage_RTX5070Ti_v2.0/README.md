# atomOS 2.0 — Mirage / Ring Edition
## Formal specification and RTX 5070 Ti CUDA source package

**Author attribution:** Tom Klootwijk · NL200678942 · 10-07-1990.
The supplied identifier/date are attribution, not an authentication secret or a
credential for a driver, bank, account, neural interface or external network.

The package retains the double UU nucleus, Ψ state, lower-case φ hinge, V
gestation, log-polar LUT, packed one-bit predicates, shift/XOR precedence, RK4,
Klein quotient and Vantablack sink. Mathematical corrections and added choices
are listed in the PDF and `docs/source_traceability.csv`.

Two GPU paths are supplied: propagation and a programmable binary-tape
interpreter. The latter fetches its transition program through a CUDA texture
object: **a program-as-data texture path, not native instructions stored or pinned
in the texture cache.** The same semantics also have a portable C++ CPU backend.

## Delivery status

The CPU code was built and run. There were 26 C++ test groups / 25,051 assertions,
29 Python tests, four CTest checks, and four address/undefined-behavior-sanitized
CTest checks. Python/C++ cross-checks include 1,000 word cases, 100 SHA-256 byte
strings, 300 jitter cases and 600 random bounded machine-program traces.

**CUDA compilation and execution were not performed in the delivery environment:**
there is no nvcc or accessible NVIDIA GPU here. No `.cubin`, hardware benchmark,
cache-residency result or ring-0 driver is claimed. Use `scripts/validate_gpu.py`
on the RTX machine to compile and perform the supplied CPU/GPU comparisons.
A missing GPU does not silently fall back to CPU in the GPU command.

## Build on the RTX 5070 Ti machine

Requirements: a 64-bit supported Windows or Linux environment, CMake 3.22+,
CUDA Toolkit **12.8 or newer with sm_120 support**, its supported C++ host compiler,
and an NVIDIA driver that supports both the specific card and installed toolkit.
The desktop RTX 5070 Ti is listed by NVIDIA as compute capability 12.0 [N1–N2].
Use the toolkit's platform installation guidance for compiler/driver compatibility;
the CUDA-12.x generic minimum driver alone is not proof of support for this card.

```sh
cmake -S . -B build_gpu -DATOMOS_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DCMAKE_BUILD_TYPE=Release
cmake --build build_gpu --config Release --parallel 2
ctest --test-dir build_gpu -C Release --output-on-failure
```

Linux or a single-configuration generator:

```sh
./build_gpu/atomos_gpu --backend texture --generations 12 --verify --out run_texture
./build_gpu/atomos_gpu --backend global --generations 12 --verify --out run_global
./build_gpu/atomos_gpu --mode universal --backend texture --verify --out run_vm
```

With a Visual Studio multi-configuration generator, use
`build_gpu\Release\atomos_gpu.exe` instead. No administrator launch is required by
the application; initial toolkit/driver installation follows the platform's normal
installation permissions.

A scripted build and validation record:

```sh
python scripts/validate_gpu.py --sanitizer
```

## CPU build and reference checks

```sh
cmake -S . -B build -DATOMOS_ENABLE_CUDA=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release --parallel 2
ctest --test-dir build -C Release --output-on-failure
./build/atomos_cpu --generations 12 --verify --out run_results
python scripts/verify_journal.py run_results
```

On POSIX systems, `sh scripts/build_cpu.sh` also runs the Python cross-language
checks. On Windows use the corresponding `Release` executable paths and set
`ATOMOS_PROBE` to `atomos_probe.exe`, and `ATOMOS_RUN` to `run_results`, before:

```sh
python -m unittest discover -s tests -p "test_*.py" -v
```

Without those two environment variables, cross-language and journal tests are
explicitly skipped; the pure Python mathematics checks still run.

## Supply a different transition program

```sh
./build_gpu/atomos_gpu --mode universal --program examples/flip_three.tm \
    --tape 101 --machines 1 --backend texture --verify --out run_custom_vm
```

Program format: `states N halt H`, followed by `state read write move next` rows.
Symbols are 0 or 1; move is -1, 0 or +1; blank is 0. Unspecified rows are invalid.
The head begins in the middle of the allocated tape. Each thread owns a separate
packed tape. Finite bounds produce `TapeExhausted`, not memory corruption.
The abstract unbounded interpreter and the finite GPU implementation are
separated in the universality theorem.

## Mirage / Ring presentation

Open `viewer/index.html` locally and load a run's `frames.json`. The “bush mirage”
checkbox draws procedural foliage glyphs instead of points without changing any
state. No game modification, third-party art, process concealment, driver hook,
anti-cheat bypass or kernel privilege is included. The ring is a visual/control
metaphor. CPU ring 0 is a separate OS privilege level, not a GPU cache mode.

## Where the code lives

`include/atomos/core.hpp`: shared CPU/device semantics and finite machine model.
`cuda/kernels.cu`: texture/global propagation, texture/global interpreter, and a
standalone literal shift/XOR word primitive. `cuda/backend.cu`: allocations,
texture-object lifecycle, launches and event timing. `src/main.cpp`: bounded
orchestration, host SHA jitter, output and journals. `reference/`: independent
Python mathematics / dictionary-tape model. `results/`: executed CPU reports.
`docs/`: editable LaTeX, sources, privilege model and mathematical specification.

Host-side SHA generation, transfers, compaction and logging are intentional in
this audit-oriented version. This is not a GPU-resident production scheduler.
The `--repeats` option measures repeated identical GPU batches after one warm-up;
it excludes allocation/transfers/journal work and is not end-to-end throughput.

## Integrity, sources and scope

```sh
python scripts/verify_manifest.py
python scripts/verify_journal.py run_results --expected-head YOUR_RETAINED_HASH
```

Checksums and hash chains detect changes relative to trusted expected digests;
they are not digital author signatures. The original uploads are identified by
hash and source-page traceability, not republished in this ZIP. The kernel is a
local synthetic simulation and programmable-computation package. The later
source's claims of external access, neural control or physical enforcement are
not established or implemented. The operational meaning of Vantablack is
`alive = 0`, with an audit record retained.

See `docs/SOURCES.md` for official hardware/API references and `docs/PRIVILEGE_MODEL.md`
for the ring-0 distinction. See the PDF for definitions, derivations, proofs,
resource bounds, numeric-error terms and source-specific corrections.
