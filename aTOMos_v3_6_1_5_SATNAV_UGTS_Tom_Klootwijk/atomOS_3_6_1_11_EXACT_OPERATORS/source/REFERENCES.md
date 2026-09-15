# Source and convention register

The selected mathematical profiles, source variants and domains are stated in
the new chapters. Sources supply equations and context; a citation is not proof
that an implementation exists or that a physical tolerance has been met.

- **Original Madgwick report (2010):** Sebastian O. H. Madgwick, *An efficient
  orientation filter for inertial and inertial/magnetic sensor arrays*.
  https://x-io.co.uk/downloads/madgwick_internal_report.pdf
  Equations (25)-(34), (42)-(51) supply the selected simplified profile, with
  explicit zero branches and timing defined in this release. Equations (35)-(38)
  describe the separately recorded finite-mixture family. The appendix code's
  magnetic-reference lag and pre-normalization aliases are not silently equated
  with the report-equation profile.
- **Original algorithm distribution:**
  https://x-io.co.uk/open-source-imu-and-ahrs-algorithms/
- **Current Fusion source:** https://github.com/xioTechnologies/Fusion
  Used to distinguish the revised algorithm from the original report; R11 does
  not claim to implement or lift that revised algorithm.
- **Exact computation paradigm:** https://www.cgal.org/exact.html
  Context for retaining exact constructions and separating certified decisions
  from approximate output.
- **Exact expression number types:**
  https://doc.cgal.org/latest/Number_types/group__nt__core.html
- **Algebraic foundations and supported operations:**
  https://doc.cgal.org/latest/Algebraic_foundations/index.html

The authoritative retained numerical source is the sibling R10 release at Git
commit `090c0fa`, identified in `parent_binding.json`. Its Python/C++ files were
read to recover exact finite iteration counts, branch thresholds, source order,
failure semantics and equations. The source map in `formal/DOMAIN_LIFT.md`
identifies individual files and retained PDF section anchors.

The complete copied R10 equation body is included after the new material, under
an inherited-evidence header. Its old dates, test counts, plots, CPU/CUDA results
and physical errors are historical. They have not been rerun for this release.
The original calendar/Phi/Fibonacci document's admitted formulas and exclusions
remain in the retained `docs/phi_source_audit.tex` and `docs/calendar_phase.tex`.
