# Kernel contract

Version label: aTOMos 3.6.1.6. Base-engine version: 3.6.1. Imported prototype:
UGTS-KC 3.6.2 SCLP. These are distinct component/release labels, not semver ordering.

Input: fixed corrected-code observations, common epoch and receive-time ECEF axes.
Unknowns: (x,y,z,b), all expressed in metres. Whiten each Jacobian/residual row by
its supplied positive sigma. Update via streaming Givens QR, not normal equations.
Retain the source channel mask and all four ASA results. Preserve one output per
input epoch in input-epoch order. Thread-local QR state cannot be shared across epochs.

Default numeric choices: 12 iterations; 1e-4 m position and clock increment tolerances;
QR relative diagonal threshold 1e-10; residual/sigma budget 6. No fast-math mode.
Converged numerical solution and residual-fit classification are separate outputs.
Exactly four observations do not provide residual redundancy. The solver does not
exclude satellites based on residuals and does not emit a protection level.

Device memory: readonly double SoA observation buffer, immutable epoch metadata and
separate result buffer. Flatten observation address (channel*6+field)*batch_count+e.
Texture path transports double bits as an int2 pair and reconstructs them exactly.
Global path reads double values directly. Chunk at most 65536 independent epochs,
within budget/free-memory/reserve checks. Report kernel-only timing separately.

Geometry: U's cone and translation helpers are source-derived; fixed-position scope
and floating-bound qualification retained. Both 64-bit codecs and their exact tuple
are tested. Key IDs never replace floating positions, full time or uncertainty.

Input schemas and reader semantics are in INPUT.md. Source corrections/choices are
in SOURCE_DECISIONS.md. Every executed versus unexecuted backend is recorded in
results/validation_status.json and per-run logs.

SRK-R1 adds the explicit word-state recurrence in SELF_REFERENCE.md. Its equation
inputs and trace replay are independent of SATNAV-R1 numerical admission. All J/K
operands read the old q synchronously and qnext is projected onto the present mask.

