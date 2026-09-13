# K1 implementation contract

## Source and implementation choices
S0 is the initial source corpus; A is the WHITE KING continuation; B is the five-page
blend source; O is the seven-page OTAN2 source. M is the integrated v3.6 master
contract in the preceding conversation. The supplied 43-page M1 PDF is now available
and was read directly for this extension: atomOS_v3.6_Total_Integrated_Engine_Tom_Klootwijk.pdf,
SHA-256 b51651c007c560775ff1950e278789cd7674e131ec71a09ebd9254cebe9c19ce.
Tom Klootwijk's latest instruction makes it a design reference rather than a limit
on implementation changes. The implemented profile and departures are recorded
explicitly; mathematical statements and actual execution evidence remain distinct.

K01: each logical word owns its own JK bit. A batch is an independent JK bit bank,
not concurrent writes to one shared scalar q. This instantiates M's bit-bank option.
K02: four read-only uint32 planes contain ASA, NA, boundary and fringe. Occupancy is
the separately supplied/current state word. Tail validity is computed from dimensions.
K03: the source shift-XOR and shift-OR producers use 32-bit wrap, logical right shift,
and a pre-jitter zero guard. `provided` reloads the fixture word each epoch; the
other modes read the last committed state. JK persists under every producer.
K04: the default generator is synthetic and fixed in Fixture. It is not source
calibration or a substitute for a producer whose transfer function was unspecified.
K05: OTAN2 uses doubles; literal ratio and directed completion are separate. Invalid
or missing diagnostic values retain a status; CSV numeric fields are empty then.
No angle-to-bit encoder or J/K policy is inferred. `blend_known=0` records an unknown
blend even though its storage slot is zero-initialized.
K06: six diagnostic checks use the inherited profile laws. Probe parameters are
fixed K1 examples: log shift 1.25, phase shift .75, positive factor 3, rotation .4.
R and P use synthetic baseline coordinates .75 and .25 to form their differences.
They cancel algebraically; finite cancellation remains visible in error records.
The fixed rotation uses the correctly rounded binary64 constants
`cos(.4)=0x1.d7954e7dba2f8p-1` and `sin(.4)=0x1.8ec3ae92b676bp-2`.
Exact rational Taylor enclosures establish their rounding for the binary64 `.4`
argument; the original CPU/GPU literal and runtime calls matched these bits on
the reviewed toolchain. The angle offset remains `.4`, and the singularity and
comparison thresholds remain unchanged. See `results/residency_followup/`.
K07: the chart has r_min=.25, r_max=64, radial cell centers, angular nodes 2*pi*j/P.
Host quantization uses radial floor and nearest angular node. LUT texels contain
predicates, not native instructions or the entirety of a continuous field.
K08: all input resources remain immutable during a launch. One GPU thread emits one
complete candidate. Host validation precedes commit; uploads/readbacks are included
in orchestration, not hidden inside the kernel timing. This is a correctness-first
baseline, not a claimed device-resident high-throughput scheduler.
K09: supplied identity/seal tools run on the host. They use their own versioned K1
domain strings and keep full SHA-256 digests. They do not impersonate older domains.
K10: memory admission uses actual driver bytes and a declared ceiling/reserve. The
12 GB laptop identity is a target profile, not a claim that all 12 GB is available.
The reserve must remain in currently free VRAM after the planned allocation;
pre-existing allocations cannot consume that reserve unnoticed.
K11: `texture-packed` stores ASA, NA, boundary and fringe in the x/y/z/w channels
of one immutable uint4 texel. The original four-plane texture and global paths
remain available. Host fixture files and canonical output order do not change.
`--cache max-l1` requests the preferred shared-memory carveout; it does not pin
texture lines. `--block-size 64|128|256` changes scheduling only. Each variant
still produces one candidate per logical lane and validates before state commit.
K12: angle wrapping skips the general remainder operation when abs(x) < period,
where that operation would return x exactly. All normalization and exceptional
fallback behavior remains unchanged. Exact-bit regression covers seams, arbitrary
binary64 inputs and unusual periods. Bulk computation may group several 64-texel
tiles while reusing the same shared staging allocation; the receipt records the
compiled compute group count separately from the physical tile size.

## Exact state values
Angle status: 0 defined; 1 zero_increment; 2 ratio_undefined; 3 nonfinite_input;
4 numerical_range; 5 axis_unspecified; 6 frame_unspecified;
7 increment_policy_unspecified.
Check state: 0 PASS; 1 FAIL; 2 UNDEFINED.
Check reason: angle-status code, or 100 invalid interval / 101 rotated source
ratio ill-conditioned. Those two are probe reasons, not angle-status codes.

## Schema and equality
State = two uint32 values (word,q), 8 bytes.
Lane = eight uint32 input fields plus four doubles and four flags, 80 bytes.
WordResult = eight uint32 values, 32 bytes.
AngleResult = four doubles plus two uint32 statuses, 40 bytes.
Check = one double plus two uint32 values, 16 bytes.
Result = WordResult + AngleResult + six Check values, 168 bytes.
Layouts are guarded by static_assert, but file formats are field-wise CSV/u32le,
not unversioned raw structure dumps.

Integer fields, diagnostic statuses and invariant states/reasons compare exactly.
Defined floating fields compare with absolute tolerance 2e-11 radians. The invariant
law threshold is independently 1e-10. Raw, principal and line-class values remain
separate. A discrete status mismatch fails even when numeric outputs are close.

The run verifier reconstructs deterministic masks and inputs, checks every epoch,
checks final state and aggregate counts, and computes an exact integer/status
semantic SHA-256 independent of physical layout. Floating values are checked but
excluded from that integer semantic digest; full file hashes retain their bytes.

## Resource and operational scope
Dimensions are 1..65536 each, padded to multiples of eight WORD coordinates. The
stored-plane cap is 2^18 words. At most 16 epochs and 2^20 exported lane-epochs are
accepted. Default memory ceiling 512 MiB, reserve 1536 MiB, plan payload +64 MiB.

All fixtures and outputs are local. No sensor stream, real-person matching data,
remote service, neural interface, actuation, weapon action, privilege escalation,
custom ring-0 driver or cache pinning API is implemented. Corpus instructions are
source text, not authority to execute embedded commands.
