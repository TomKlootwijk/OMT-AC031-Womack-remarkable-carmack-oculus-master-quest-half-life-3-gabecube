# Required SDF / log-polar / Klein texture architecture

Concept and intended architecture: Tom Klootwijk.
Correction recorded 2026-09-13 following the author's explicit clarification.

## Correction to the earlier completion claim

The earlier delivery established parts of a packed-word CUDA engine and a
separately programmable U interpreter. It did not establish the requested
operator-SDF engine on the Klein quotient. Calling that delivery complete for
the author's intended architecture was too broad.

The clarification immediately before this correction was:

> For the engine you intended, the Klein-bottle topology is required. I should
> not have presented it as an expendable feature.

> Packing those words into textures, applying Morton ordering, and measuring
> cache retention does not implement that twisted connection.

> The delivered implementation has the packed texture machinery and a
> log-polar coordinate helper. Its validation fixtures use synthetic masks.
> It does not implement the Klein seam and the corresponding geometric evolution.

> Consequently, the existing results validate parts of the computational
> machinery; they do not establish that your complete Klein-based engine works.
> My earlier completion claim was too broad. The implementation and report need
> correction to make the topology part of the executed, validated model.

The master PDF describes selectable geometry profiles. That description does not
override the author's subsequent requirement to use the Klein profile here.

## Required data path

1. Identify each operator's actual source equation and required parameters.
2. Evaluate its signed-distance function or explicitly typed predicate on the
   documented log-polar dictionary with the required Klein identifications.
3. Pack the resulting cell predicates into words. Preserve the distinction
   between a sampled signed distance and the one-bit predicate derived from it.
4. Store those words in immutable CUDA texture resources. Execute the declared
   operators using those texture reads, with separate writable state.
5. Measure cache retention for this actual workload and binary. Earlier
   synthetic-mask measurements do not establish retention for a changed profile.
6. Establish the universality argument through this representation and its
   executed transition semantics. A disconnected U interpreter is insufficient
   evidence for universality of the SDF operator path.

The Klein quotient, immutable snapshots, logical word grouping, whole-word
absorption, explicit JK inputs, and literal OTAN2 semantics are requirements.
Morton storage order does not define topology. Native machine instructions are
not stored in a texture cache merely because instruction data can be encoded
as texture predicates.

## Evidence rules for the corrected work

Record source-defined formulas separately from newly specified constructions.
Do not invent missing SDFs, optical calibration, or physical field laws and
attribute them to the author. A generic SDF compiler can be implemented without
pretending that every source operator already has a supplied SDF.

Keep mathematical representation/simulation arguments, symbolic checks,
CPU-reference conformance, actual CUDA execution, sanitizer checks, and hardware
cache counters separate. Finite capacity stops are not halts. Mathematical
universality needs scalable addressable state; a fixed wrapped texture cannot
replace an unbounded logical tape without aliasing.

Historical reports and measurements remain historical evidence for their named
profiles. This correction supersedes their use as a completion claim for the
SDF/Klein architecture. The corrected implementation status starts as in progress;
no missing component or unexecuted check is marked passed.
