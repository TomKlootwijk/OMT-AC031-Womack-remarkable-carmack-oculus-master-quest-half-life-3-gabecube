# aTOMos 3.6.1.7 - geometry-coupled self-referential kernel

CGK-R1 completes the feedback connection between geometry, the literal ASA/NA + JK
word state, and evolving physical position/velocity. Geometry supplies alignment,
limit, fringe and support words. Editable equations produce the next q. That q
changes the mechanical stiffness and force; the resulting geometry is used on
the following step. The actual SATNAV/UGTS handoff executes this loop by default.

The profile defines the missing circle-plus blend, predicate encoders and physical
eigenmatrix explicitly. These are new mathematical definitions using the retained
source primitives, with units and execution order; unavailable original M2 equations
are not claimed to have been recovered.

## Run the coupled equations

Windows CPU/CUDA binaries are included under `bin/windows/`. Python with NumPy is
required for independent replay (`python -m pip install -r requirements.txt`).

```powershell
./tools/run_coupled.ps1 -Backend cpu
./tools/run_coupled.ps1 -Backend cuda
```

Use `-InputFile PATH` to select editable model JSON and `-OutputDirectory NEW_PATH`
to name the result. Inputs include the actual d/x/j/k expressions, initial 3D state,
phase, full time, mass/damping/stiffness, directional channel geometry, signed on/off
forces, supports and observation samples. Each native run is independently replayed.

## Execute the full SATNAV/UGTS connection

```powershell
./bin/windows/cpu/satnav.exe --input examples/demo --out results/my_satnav --backend cpu --verify
python tools/verify_run.py --input examples/demo --run results/my_satnav
python tools/ugts_handoff.py --input examples/demo --run results/my_satnav --backend cpu
```

The handoff publishes original receiver ECEF/clock/covariance alongside the distinct
modeled physical state, actual persistent JK before/after, physical matrices,
both key codecs, full time/winding/Up and hash lineage. `--legacy-hold` selects the
previous observation-only adapter explicitly. No residual-budget or undefined-angle
condition silently overrides the supplied coupled equations.

## Equations and implementation

- [Complete equation/interface contract](docs/COUPLED_CONTRACT.md)
- [Complete editable JSON schema, defaults, units and CLI](docs/COUPLED_INPUT.md)
- [Editable coupled model](examples/coupled/model.json)
- [SATNAV coupling parameters](profiles/COUPLED_R1.json)
- [Shared CPU/CUDA transition](include/coupled_kernel.hpp)
- [Independent Python mechanics and expression reference](python/coupled.py)
- [Formal PDF](output/pdf/aTOMos_v3_6_1_7_Coupled_Geometry_Physical_Kernel_UGTS_Tom_Klootwijk.pdf)
- [Current execution evidence](results/validation_status.json)

The mechanical realization is a signed mass-spring-damper state with backward Euler
integration. Its physical eigenmatrix is `M^(-1/2) K(q) M^(-1/2)`. Negative stiffness
modes are reported as such. Original SATNAV observations stay separate from modeled
motion; artificial fixture verification does not establish real-world receiver accuracy.

## Rebuild

This workspace has a long Windows path, so use a short build directory:

```powershell
cmake -S . -B C:/tmp/atomos3617_cpu -G "Visual Studio 17 2022" -A x64
cmake --build C:/tmp/atomos3617_cpu --config Release --parallel 2
ctest --test-dir C:/tmp/atomos3617_cpu -C Release --output-on-failure
cmake -S . -B C:/tmp/atomos3617_gpu128 -G "Visual Studio 17 2022" -A x64 -T cuda=12.8 -DSATNAV_ENABLE_CUDA=ON
cmake --build C:/tmp/atomos3617_gpu128 --config Release --parallel 2
python -m unittest discover -s tests -p "test_*.py" -v
```

The exact locally executed compiler/device versions and all validation scopes are
recorded in results. The pure Boolean SRK-R1 model and the SATNAV component remain
available. Prior release directories are preserved; their evidence is archived in
`results_3_6_1_6/` and `results_3_6_1_5/` and is not counted as current validation.

Rebuild the editable LaTeX with `python tools/build_pdf.py --engine PATH_TO_TECTONIC`
or an installed latexmk. `python tools/build_package.py --out NEW_RELEASE.zip`
regenerates the byte manifest and verifies the ZIP contents. `python tools/verify_package.py`
checks the delivered bytes. Native binaries use installed Visual C++/CUDA runtimes.

## Reproduce the completed-loop verification

```powershell
python tools/validate_coupled.py --binary bin/windows/cpu/coupled_kernel.exe --backend cpu --out results/my_cpu_validation
python tools/validate_coupled.py --binary bin/windows/cuda/coupled_kernel.exe --backend cuda --out results/my_cuda_validation
compute-sanitizer --tool memcheck --error-exitcode 99 bin/windows/cuda/coupled_kernel.exe --input results/my_cuda_validation/compiled --out results/my_memcheck --backend cuda
python tools/coupled.py --input results/my_cuda_validation/model.json --out results/my_memcheck_replay --verify results/my_memcheck
```

The executed suite contains 272 trajectories and 3,308 transitions, including
257 trajectories with different lengths across three CUDA blocks. Each backend
passes 320,876 independent field comparisons and 20 analytic/causal invariants.
Three deliberately singular/overflow trajectories emit the expected numeric
failures, followed by four frozen-state records. The other 3,301 steps advance.
Eight trace mutations are rejected. Compute Sanitizer reports zero memory errors;
the sanitized output also passes full independent replay. The actual 256-epoch
CPU and CUDA handoffs each pass 24,832 comparisons and a separate publication audit.
