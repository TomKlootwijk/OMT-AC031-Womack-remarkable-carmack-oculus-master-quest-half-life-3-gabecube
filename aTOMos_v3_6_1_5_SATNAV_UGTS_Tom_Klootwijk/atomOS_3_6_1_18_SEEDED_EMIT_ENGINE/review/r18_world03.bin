# TOM World & Query Kernel 0.3.0

## Certified interval events and simultaneous event sets

TOM 0.3 continues the persistent world/query work with the first exact between-tick event layer. It adds exact rational values, closed rational intervals, continuous relation expressions over affine trajectories, sign-change certificates, derivative-based uniqueness certificates, exact affine roots, simultaneous event sets, deterministic event order, conflict-checked transition merge, and an independent trusted baseline.

No TOMAGI opcode or ABI field changed.

## Implemented chain

```text
TOMAGI integer anchors
-> exact affine rational trajectory
-> typed SDF0@Def relation expression
-> exact endpoint residuals
-> interval residual and derivative enclosure
-> sign-change/exact-endpoint existence certificate
-> exact affine root or rational bisection bracket
-> support and compatibility gates
-> earliest simultaneous event set
-> deterministic conflict-checked transition
-> content-addressed certificates
```

## Canonical demonstration

The reference trajectory is `x(t)=2t`, `clock(t)=t`, `mode(t)=1` over `0<=t<=10`. Three relations meet at the same exact rational time:

```text
time - 5/2 = 0
3*x - 15   = 0
x - 5      = 0
```

The crossing bracket `[2,3]` for `x-5` has endpoint residuals `-1` and `+1`, residual interval `[-1,+1]`, derivative interval `[2,2]`, and exact unique root `5/2`.

The deterministic simultaneous order is priority first and then relation/event identity. All operations read the common pre-event state. Two `add` operations merge to `counter += 3`; one independent `set` operation produces `output=25`.

A later accepted event `x-10=0` occurs at time `5`. Deliberately inactive, unsupported, and incompatible roots are retained as rejection evidence rather than silently accepted.

## Independent baseline

The baseline uses `fractions.Fraction` and a separate affine linearizer. It does not import the 0.3 interval solver. Its accepted relation IDs and exact root times must match the solver's canonical event list.

## Files

- `spec/TOM_WORLD_QUERY_KERNEL_0_3.md` — normative profile.
- `spec/tom_world_query_kernel_0_3.schema.json` — strict world schema.
- `src/python/tom_world03/` — exact arithmetic, expression, model, solver, transition, baseline, and CLI implementation.
- `examples/world03/interval_event_world.json` — authoritative literal world source.
- `examples/world03/affine_reference.tmg` — one-cell TOMAGI integer-anchor program.
- `validation/world03/certified_crossing_x5.json` — crossing certificate.
- `validation/world03/next_event_set.json` — simultaneous event-set certificate.
- `validation/world03/simultaneous_transition.json` — atomic merge certificate.
- `validation/world03/trusted_baseline_comparison.json` — solver/baseline equality.
- `validation/world03/tomagi_trajectory_baseline.json` — TOMAGI anchor and Python/C evidence.
- `validation/world03/validation_report.json` — final release checks.
- `TOM_AGI_ROADMAP_AND_STARTER_0_3.md` — updated research path.

## Current boundary

The implementation certifies continuous roots only over exact rational affine trajectories using finite expressions with `+`, `-`, and `*`. It does not claim a general validated ODE solver or AGI.

The next milestone is 0.4: piecewise validated dynamics, interval candidate indexes, simultaneous event-set commits into the persistent world, and post-event trajectory continuation.
