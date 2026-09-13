# Tom Klootwijk atomOS: programmable word-plus-U profile

`atomos_engine` implements the M1 word-plus-U profile (source pages 25 and 31-32).
The word/JK/observation state and programmable machine have separate inputs and
share one checked commit. Optional geometric profiles are disabled.

## Build and run

```powershell
cmake -S . -B C:/Users/Tom/.cache/ak1/universal_final -T cuda=12.8 -DATOMOS_ENABLE_CUDA=ON
cmake --build C:/Users/Tom/.cache/ak1/universal_final --config Release --target atomos_engine atomos_universal_stress atomos_universal_tests
output/bin/atomos_engine.exe --program examples/universal/binary_increment.atomos --steps-per-epoch 8 --epochs 1 --out new_counter_run
python tools/verify_universal.py new_counter_run
```

Use a new output directory. The binary increment program changes 31 into 32 in
six transitions. Other editable examples increment unary numbers, replace symbols,
erase a sequence, cross zero, continue without halting, or encounter a missing rule.

## Editable program

```text
atomos-universal 1
states 2
alphabet 2
start 0 0
halt 1
cell 0 1
rule 0 1 0 0 R
rule 0 0 1 1 S
```

States and symbols start at zero; zero is blank. `start` supplies program control
and signed head address. `cell` supplies initial memory; absent cells are blank.
A rule lists current state, read symbol, next state, written symbol and movement
(`L`, `S`, `R`). Missing rules are errors, not halts. Duplicates and out-of-domain
values are rejected. Lines may contain `#` comments.

Rules are immutable while execution reads them. Writable tape symbols can cross
32-bit word boundaries. A one-symbol alphabet uses one storage bit explicitly.
Negative logical addresses use a checked origin; they never alias positive ones.

## Checked epochs and resources

The GPU proposes both K1 and U. An independent host map interpreter checks every
U step and all packed bits. The existing K1 oracle checks word, JK and diagnostic
results. Only accepted proposals advance both states and time. A missing-rule or
range failure preserves the prior combined state, even if a proposed prefix exists.

`--steps-per-epoch` accepts 0..65536; further epochs continue a running machine.
Budget exhaustion means `running`; entry into a declared halt means `halted`.
The tape grows between epochs. `--origin` and `--cells` select a fixed window.
Growth saturates at signed-64-bit endpoints; actual outward transitions return
`tape_range` before writing. Resource failures are explicit and do not imply halt.

Default admission uses 85% of currently free GPU memory with a 512 MiB reserve.
`--memory-mib` and `--reserve-mib` make this configurable. The parser also checks
available Windows host RAM before allocating a dense table. Byte arithmetic and
allocation limits are checked before constructing the tape or launching work.

## Outputs and replay

`engine.json` records resources, epochs, statuses and per-kernel timings;
`epochs.jsonl` streams records. `u_trace.csv` contains actual GPU steps and
`trace.csv` K1 candidates. Each epoch retains before/candidate/committed states
and packed tapes. Successful runs publish `COMMITTED`; a rejected attempt
publishes `PREFIX_VERIFIED` and `rejection.json` for the accepted prefix.

The independent Python verifier checks transitions, packing, K1 outputs, time,
rollback and resource accounting. The validation runner then adds a separate U1
post-run hash seal. Its accepted-state chain and rejected-attempt receipt differ.
This is a local audit profile, not a native crash-consistent hash database.

## Parallel capacity exercise

```powershell
output/bin/atomos_universal_stress.exe --memory-fraction 0.85 --steps-per-launch 16384 --rounds 32 --out new_stress.json
```

This separate target executes independent rule machines in parallel, checks each
machine after every launch, then compares the complete allocation through at most
a 64 MiB host readback buffer. Allocation, verified bytes and program-touched bytes
are separate metrics. Capacity stops are distinct from program halts. This stress
target is not the combined transactional K1+U runner.

The universality theorem assumes logical addresses and enough storage for each
finite prefix. Tests establish finite execution results, not arbitrary termination,
arbitrary speedup, unlimited hardware, or residency of the combined engine's cache.
