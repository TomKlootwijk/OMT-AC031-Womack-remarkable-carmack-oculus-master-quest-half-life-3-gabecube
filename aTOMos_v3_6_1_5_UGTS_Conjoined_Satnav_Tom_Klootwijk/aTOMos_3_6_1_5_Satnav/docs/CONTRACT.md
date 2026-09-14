# Conjoined definition / aTOMos 3.6.1.5 × UGTS 3.6.2

## Mathematically retained
- aTOMos ASA -> NA -> POPCNT -> whole-word disposition, explicit JK/encoded blend.
- Literal OTAN2 atan(delta_angle/delta_log_radius) and raw axis subtraction.
- Separately named directed completion; missing direction remains unavailable.
- UGTS finite cone from slant plus half-angle, paired spheres, conformal metric,
  exact expm1 radial step, separate spatial theta and hinge phi.
- Two independent 64-bit layouts with widths 20/18/14/12 and the source MSB
  round-robin Morton schedule; full time/third coordinate remain external to the key.
- Source half-turn and reflective Klein are separate chart profiles, not world ECEF maps.
- Translation-only sweep interval, finite grammar and constraint rank/nullity relation.

## New specialization SN1
Prepared code-observation positioning in ECEF with one receiver-clock state in metres.
Weighted nonlinear least squares solved by streaming Givens QR, not by inverting
normal equations. Four formal standard deviations are computed from the final R.
The metric interpretation assumes supplied independent observation variances.
No prior is silently added when fewer than four independent measurements are present.

The conjoined GPU path has a solve kernel and an enrichment kernel. A batch contains
ordered epochs of one receiver; solves are independent and parallel, while enrichment
compares adjacent solved epochs. Across device chunks the previous result is passed
explicitly so `--chunk 1` has the same declared semantics as larger chunks.

## Coordinate binding
ENU uses a fixed WGS84 ellipsoid anchor. The runnable example chooses latitude 52°,
longitude 5°, height 20 m. Spatial theta=atan2(N,E), east-zero and counterclockwise.
It is not north-referenced bearing. rho=ln(hypot(E,N)/10000 m). Up is a separate output.
The explicit origin core is r<0.01 m. Packed rho must be in [-20,0]. No clamp converts
an out-of-range solution into a valid key. Time index is tick_ms modulo 16384; the
full timestamp is retained. Hinge phi is the supplied epoch hinge, not OTAN2 or clock.

The default cone is a numerical local-support example: apex (0,0,-100) m, unit up axis,
slant 1000 m and half-angle pi/3. Spheres have centres (0,0,0) and (200,0,0) m,
radius 500 m. Point-relation margin is 0.001 m. These are SN1 worked values, not
antenna calibration, satellite visibility, collision avoidance or commanded routes.
Support results annotate the estimate and do not alter its coordinates or J/K inputs.

## Source equation distinctions
The UGTS printed jitter equality equates intervals about f and f_j=f+epsilon*sigma.
These intervals are generally different. The conjoined helper preserves both named
intervals and the exact relation f=f_j-epsilon*sigma; it does not silently adopt the
incorrect equality. Jitter is not injected into pseudorange observations.

The translation-sweep bound is retained. Arbitrarily denser nonnested sample sets
need not yield nested numerical certificates, although the error-radius formula
shrinks. Nested grids or intersected prior intervals are needed for a nested sequence.
No angular-sweep bound is fabricated from a translation-only proof.

## GPU data contract
FP64 observations stored as five planes, each containing 32 slot-major arrays with
consecutive epochs. Linear index=(component*32+slot)*chunk_epochs+epoch_index.
Global reads fetch doubles. Texture reads fetch int2 and reinterpret the exact same
64 bits. This specifies data access, not pinned cache residence or code-in-texture.
The measured host ABI is Epoch 88 B, Solution 112 B, Diagnostic 136 B, Observation 40 B.
GPU upload payload is 1616 bytes/epoch (five padded observation planes plus metadata
and the two outputs), excluding host copies and small runtime overheads.
