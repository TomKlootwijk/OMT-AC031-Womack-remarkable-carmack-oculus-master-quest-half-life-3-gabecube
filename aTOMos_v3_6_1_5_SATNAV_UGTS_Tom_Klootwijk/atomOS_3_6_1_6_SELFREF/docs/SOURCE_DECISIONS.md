# Source and specialization decisions

U = supplied UGTS-KC 3.6.2 SCLP, 19 physical pages. Printed main page p corresponds
to physical page p+3. A = aTOMos 3.6.1 M2 project contract. N = new SATNAV-R1.

N01: SATNAV-R1 is a passive corrected-code navigation-observation profile. The user
asked for satnav; U supplies no pseudorange observation equation or ephemeris model.
These are new and explicitly attributed to primary GNSS references in the PDF.

N02: GNSS state is 3D ECEF position plus a clock bias. The planar UGTS log chart is
an indexed diagnostic after ENU conversion. Up, full time, clock, covariance and
original coordinates are retained outside the 64-bit key. No dimension is discarded.

N03: The default kernel uses iterative weighted Givens QR; Python uses independently
written Householder QR. No normal-equation inversion is used for the update. The
rank screen is an unpivoted triangular-diagonal numerical threshold, not a complete
condition-number estimate. No claim of global nonlinear convergence is made.

N04: ASA/NA maps one epoch's up to 32 observation channels to a retained whole-word
selection. An intersecting boundary absorbs the whole selected group. Individual
observation exclusion belongs to a selector mask, not that boundary operation.

N05: U's contiguous and MSB-round-robin Morton layouts stay separate and reproduce
its golden pair. Quantization is a specified nearest-node extension where U gives
only widths/ranges. The 12-bit field is the declared hoop phase; it is not a second
unrecorded arbitrary matrix/grammar payload.

N06: U printed p.5 writes [f_j-eps,f_j+eps]=[f-eps,f+eps] with f_j=f+eps*sigma.
That equality is generally false for nonzero eps. The source equation is discussed
in the PDF and retained as source text; this package exposes two different intervals:
(1) family interval around f containing possible f_j, and (2) measurement-centered
interval around f_j containing f for |f_j-f|<=eps. Jitter never alters GNSS observations.

N07: U's translation-sweep bound is retained. Its width shrinks with more samples;
intervals for arbitrary nonnested sample grids need not be nested. The helper is
floating evaluation of an analytic bound, not a hardware-directed-rounding proof.
Rotating swept cones are not supplied by this helper.

N08: Source half-turn bundle and reflective Klein quotient remain separate optional
helpers. Neither is applied to the receiver's global ECEF state, GNSS signal paths or
physical Earth topology. Mechanical constraint release and grammar are source-domain
contracts, not a GNSS solution algorithm substituted for observability.

N09: The UGTS event is a local computational observation record. The residual budget,
sphere bound and event state do not constitute RAIM/ARAIM, certified integrity,
anti-spoofing authentication, a navigation action or a real protection level.

N10: CUDA is source-targeted at the requested SM120 laptop. Compilation/execution is
not_run in preparation. The CUDA validation script must supply the on-device result;
prior source test counts are not claimed as new validation of this release.

N11: SRK-R1 (3.6.1.6) explicitly composes the retained ASA/NA and JK primitives with
user-supplied Boolean equation inputs and persistent state feedback. The expression
bindings, present-mask projection, table compiler and trajectory execution are new
definitions. Original M2/OTAN2/UGTS PDFs are not mounted in this subversion run; the
source basis is the preserved 3.6.1.5 package and its transcribed equations.

