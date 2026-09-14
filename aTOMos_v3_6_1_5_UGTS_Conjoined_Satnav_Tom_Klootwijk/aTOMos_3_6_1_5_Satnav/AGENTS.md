# Review aTOMos 3.6.1.5 conjoined satnav

Read README.md and docs/CONTRACT.md / INPUT.md before editing.
Retain source-ratio OTAN2, whole-word absorption, theta/hinge separation and exact key
layout tags. Do not call this a raw GNSS receiver or silently add missing corrections.
All input satellite positions must already be in the reception-time ECEF frame.

Run tools/validate.py for CPU review; --gpu builds and executes both read paths,
checks independent equations and compares chunks 1/7/8192. Record actual results.
The preparation environment did not contain nvcc or an accessible NVIDIA GPU.
Never substitute CPU success for CUDA execution or reduce comparison strictness to
hide a defect. Add a failing test before changing semantics.

The source GPU computation is receive-only positioning and local geometry annotation.
No route generation, mission planning, actuation or targeting module is part of it.
No runtime provenance chain or external telemetry service is required.
