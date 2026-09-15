# Exact affine events and atomic hinge continuation

Profile: `ATOMOS-EXACT-AFFINE-EVENTS-R1`.

Implementation: [`python/atomos_events.py`](../python/atomos_events.py), with the additive `Engine.affine_plane_binding` and `Engine.step_certified_crossing` entry points in [`python/atomos_hinge.py`](../python/atomos_hinge.py). Checks: [`tests/test_events.py`](../tests/test_events.py).

This specialization closes an actual gap in the inherited endpoint-driven hinge: it discovers intervening plane crossings, commits the existing ASA/NA and JK bodies at the exact root, and continues the declared world with atomic state and rate edits. It uses exact rational arithmetic on the host. It does not discover arbitrary nonlinear roots, refit a GPU BVH, or infer an actual physical trajectory from an uncalibrated model.

## Source lineage and concrete corrections

The reviewed source is Tom Klootwijk's TOM World Query Kernel package, specifically `spec/TOM_WORLD_QUERY_KERNEL_0_4_REBUILT.md`, `src/python/tom_world04r/solver.py`, `transition.py`, `rational.py`, and the earlier `tom_world03` expression/interval solver. The source package is retained independently; this is a newly bound aTOMos adapter, not an assertion that a separate integer-time TOMAGI VM executes this world algorithm.

The useful imported structure is an immutable affine epoch, finite relation set, exact root candidates, complete simultaneous event set, and continuation from one common pre-event snapshot. R16 addresses three concrete issues observed in the reviewed source paths:

1. The source solver admits a root at the horizon, but its transition path then attempts a zero-width successor OpenSegment, which the model rejects. R16 commits a terminal point snapshot at the horizon.
2. The source rational dictionary parser applies `int()` to limbs if a separate JSON schema has not run; a floating limb such as `1.9` can be truncated. R16 requires actual integer limbs before constructing a rational.
3. The reviewed application/replay paths check receipts and linkages without recomputing the full earliest event semantics. R16 regenerates the expected complete certificate against the owned current epoch and semantically replays packed sessions.

The earlier general interval solver's endpoint/sign-change path also does not establish arbitrary earliest-event completeness. R16 makes a narrower, provable affine claim and does not inherit that broader claim.

## Admitted state, time, and guard

An initial profile declares a positive-width finite rational horizon `[t0,H]`, a nominal frame identity, a time-convention identity, scalar state fields with seven integer SI dimension exponents, initial values, and constant rates. Between accepted events the conditional continuation is

\[
x_j(t)=x_{j,0}+v_j(t-t_0),\qquad t\in[t_0,H].
\]

`state_at(t)` evaluates this current-epoch prediction. It does not claim that the entire interval to `H` has already been realized: an earlier accepted event replaces the future continuation. A transition records the actually advanced interval and both pre- and post-event state/rates. Each rate has the corresponding field's units divided by the declared time unit. State-update literals inherit the field's units; rate-update literals inherit its rate units.

Exact numeric inputs are actual Python integers, `Fraction`, or dictionaries with exactly the keys `num` and `den`, both actual integers and `den > 0`. Boolean aliases, floats, strings, extra fields, and nonpositive denominators reject. Non-reduced rational records are reduced exactly, without changing their values.

Each relation binds three declared length fields to one existing hinge's literal plane graph:

\[
g(p)=n\cdot p-d,
\quad
a=n\cdot v,
\quad
c=n\cdot p_0-d,
\quad
g(p(t))=a(t-t_0)+c.
\]

The admitted graph has a `plane_guard` export whose point is a typed `vec3` input and whose normal and offset are literal rational values. The normal is dimensionless, nonzero, and in the same nominal frame; the offset has length dimension. The binding is derived from the actual seed graph and checked with the existing graph evaluator. Relations cannot substitute another independent normal, offset, or guard equation. General scalar expressions, sphere/quadratic guards, algebraic-irrational coefficients, and unrecognized graph shapes are explicitly unsupported in this first event profile. A literal normal need not be unit length unless the seed requests an actual SDF; a nonunit plane residual provides the correct zero set and signs but is not Euclidean signed distance.

The profile admits at most 4,096 fields, 4,096 hinges, and 4,096 once-only relations. The event-set budget is an integer in `0..4096`. These are finite-domain admission limits, not a bound on arbitrary-size rational bit complexity or execution time.

## Exact earliest event set

Each unconsumed relation declares a closed active interval `[alpha,beta]`, inclusive scalar support intervals, and scalar equality gates. Its forward search window is

\[
W=(t_0,H]\cap[\alpha,\beta].
\]

Roots at the current start are excluded, including zeros created by a reset at that same timestamp. There is no implicit instantaneous cascade. Point active intervals are admitted if the point is strictly after `t0` and at or before `H`.

For a scalar affine field, the exact range on a closed enclosing interval `[l,u]` is

\[
I_j=[\min(x_j(l),x_j(u)),\max(x_j(l),x_j(u))].
\]

A disjoint required support interval, or a required equality value absent from this range, excludes the relation throughout its window. Including the open lower endpoint in this enclosure is conservative. Failure of this sufficient exclusion does not prove that several gates are jointly satisfiable.

For `a != 0`, the only possible root is

\[
\tau=t_0-\frac{c}{a}.
\]

It is admitted only if it belongs to `W` and every support/equality gate holds exactly at `x(tau)`. For `a=0,c!=0` there is no root. For `a=c=0` the guard is identically zero and has no isolated crossing: discovery reports `UNKNOWN`, unless an exact window or gate exclusion already proved it irrelevant throughout that window. This intentionally conservative case can block continuation; it is not silently converted to an absent event.

The engine enumerates the finite unconsumed relation set, then selects

\[
\tau_* = \min_r\tau_r,
\qquad
\mathcal E_* = \{r:\tau_r=\tau_*\}.
\]

Every eligible relation must resolve or be excluded before completeness is claimed. Exact root time, then integer priority, then relation identity gives deterministic certificate ordering. Priority does not authorize sequential partial execution of a simultaneous set. The certificate records all admitted current-epoch candidates and the complete earliest group; future candidates are recomputed after any intervening edit.

Completeness follows within this admitted domain because a nonconstant affine residual has precisely the displayed root, all gates are evaluated exactly there, exclusions are sound, and every remaining relation is considered. There is no sampling interval, spatial raster, numerical epsilon, or unit-time bracket in this solver.

## Root commit through the inherited word equations

At a nonzero-slope root,

\[
g(p(\tau+s))=as,
\qquad
\sigma_-=-\operatorname{sgn}(a),
\qquad
\sigma_+=\operatorname{sgn}(a).
\]

`Engine.step_certified_crossing` validates the exact origin/rate trajectory, same frame, seed binding, `tau > t0`, and nonzero slope, then evaluates the actual original guard graph at the submitted root and requires exact zero. It applies any already stored chart orientation to both sides once. This fixed-frame event introduces no new seam, orientation reversal, or winding change.

With old word `q`, the corrected post-side drives the selected lane. The declared word expression `x` is evaluated, followed by the two independently stored ASA/NA mask stages, then the declared `J` and `K` expressions from the same old state. The existing JK body commits

\[
q^+=\bigl[(J\land\neg q)\lor(\neg K\land q)\bigr]\land P.
\]

Complements use the declared finite word width. An optional seam lane holds for this non-seam event, as in ordinary `step`. The branch event parity toggles once; the stored side becomes the corrected algebraic post-side and the stored guard value is the exact root zero.

The low-level certified entry point proves that the supplied path crosses the bound plane. Its source-epoch digest is an immutable provenance identity, not by itself evidence that a submitted trajectory belongs to a particular world. `EventEngine` supplies that stronger binding by generating and revalidating the path from its owned current epoch and verifying earliest-set completeness. Existing `Engine.step`, its boundary-ownership rules, and the packed hinge envelope are unchanged. An ordinary zero-valued sample can still hold at the boundary; the distinct certified entry point possesses an explicit isolated-crossing proof.

## Common-prestate atomic continuation

All selected relations read the same `x^- = x(tau*)` and old rates. For each independently updated state or rate field:

- Equal `set` values coalesce; unequal `set` values conflict.
- All `add` values sum once onto the common prestate.
- All `xor` values combine once with the common prestate, only for nonnegative dimensionless integer state. XOR is not admitted for rates.
- Mixed update modes conflict. Unmentioned fields retain their pre-event values.

Thus a rate edit affects only the successor segment. Simultaneous relations naming the same hinge coalesce one crossing pulse only if their complete origin, velocity, root, and plane-seed bindings agree. Different trajectories targeting the same hinge at one timestamp conflict; timestamp equality alone is insufficient.

The implementation computes world edits and hinge edits on independent snapshots and constructs the successor, transition, certificate history and accepted-receipt mapping before publishing them. Domain, validation, conflict, and explicit resource failures produce no partial world/hinge commit. This is a serial API; concurrent calls to one instance are outside its contract.

If `tau* < H`, the successor is a new `open_affine_epoch`. If `tau* == H`, the event is committed to a `terminal_state` point snapshot and the engine finalizes. No zero-width open segment or subsequent evolved interval is created. At `H`, `sigma+` denotes the sign of the algebraic affine extension; it is not an observed future interval. If there are no admitted events, the engine advances to `H` without a crossing pulse and finalizes.

Relations are once-only. Every successful event occurs strictly after the current start and consumes at least one previously unconsumed relation, so at most the initial number of relations can yield successful event sets, plus at most one event-free finalization. Repeated crossings can be represented by distinct gated relation identities, as in the fixture below. Automatic rearming, dynamically created relations, infinite/Zeno event chains, tangencies and instantaneous reset cascades require a separately specified extension.

## Semantic certificates, duplicate holds, and packed replay

`seal(record)` supplies a canonical byte receipt, not a mathematical proof. Admission regenerates the full expected certificate against the current immutable epoch and compares canonical bytes. This verifies the profile and epoch binding, exact roots, gate outcomes, all current candidates and complete earliest simultaneous membership. Update bodies come from the bound profile; a submitted certificate does not choose arbitrary new edits.

Rehashing a false root, substituting a different plane identity, removing an earlier event, omitting a tied event, or claiming `NONE` does not pass semantic admission. A stale unaccepted certificate fails against a successor epoch. An identical previously accepted certificate returns `DUPLICATE` with no second effect, even after the world has advanced. A receipt reused with changed bytes rejects.

`pack()` uses the existing lossless document envelope under the distinct session profile `ATOMOS-EXACT-AFFINE-SESSION-R1`. It preserves the definition, admitted certificates, transitions, derived epoch and terminal state. `unpack()` constructs a fresh engine, semantically replays every certificate, then compares the entire derived epoch, transition history and finalization state. A correctly rehashed serialized final state cannot replace this replay.

API:

```python
engine = EventEngine(profile)
certificate = engine.next_event_set()   # May raise UnresolvedEvent.
result = engine.apply_event_set(certificate)
result = engine.advance()               # Discover + admit one complete set.
results = engine.run()                  # Stops at finalization or a failed set.
resumed = EventEngine.unpack(engine.pack())
```

`EventResult` contains `status`, an independent epoch snapshot, optional transition and a reason. Statuses are `APPLIED`, `FINALIZED`, `DUPLICATE`, `UNKNOWN`, `UNDEFINED`, `INVALID`, or `RESOURCE_LIMIT`. `next_event_set()` and `advance()` are not called after finalization; `run()` on a finalized engine returns an empty list. Profile, epoch, history, transitions, and `hinge(name)` accessors return independent copies or clones.

## Independent checks and useful result

The turnaround fixture declares `x(0)=-1`, initial rate `+4`, a zero-plane enter relation, a plane at `x=1` that changes the rate to `-4`, and a separately gated zero-plane exit relation. Its independent closed form is

\[
x(t)=\begin{cases}-1+4t,&0\le t\le1/2,\\3-4t,&1/2\le t\le1.\end{cases}
\]

Both endpoints have `x=-1`. Nevertheless the event engine discovers the two zero-plane crossings at `1/4` and `3/4`, with the turnaround event at `1/2`. The zero hinge's default body takes `q:1 -> 0 -> 1`; two retained event records remain even though the final word and parity return to their initial values. Independent counter/state assertions also check the atomic updates and final continuation.

The event suite additionally constructs 100 rational roots independently from known root times, slopes and offsets, then verifies the engine's roots. It covers an event exactly at `H`, fractional and point active windows, support/equality gates, initial and reset-created zero ownership, unresolved zero planes, update conflicts, same-hinge path conflicts, literal mask/JK arithmetic, orientation and seam-lane behavior, exact-root rejection at a residual of `1/10^80`, duplicates, stale epochs, false/rehashed/incomplete certificates, and packed semantic replay.

Observed validation on this implementation: **27 event tests passed**, including those 100 known-root subcases; **22 inherited hinge tests passed unchanged**. These checks establish behavior of the admitted finite exact model. They do not measure orbit prediction accuracy, prove photonic hardware performance, or make an accelerating real-world process exactly affine. The immediate applications are deterministic event-driven kinematics, planar contact/threshold schedules, exact digital state transitions tied to those schedules, and replayable calibration or simulation fixtures with explicitly declared models and units.
