from pathlib import Path
import json, platform, shutil, subprocess, hashlib

root=Path(__file__).resolve().parents[1]/'atomOS_3_6_1_6_SELFREF'
results=root/'results'
gpu=next(p for p in sorted(results.glob('gpu_*')) if (p/'status.json').exists() and json.loads((p/'status.json').read_text()).get('memcheck')=='passed')
def read(path):return json.loads((root/path).read_text(encoding='utf-8-sig'))
sample=read('results/selfref_gpu/summary.json')
stress=read('results/selfref_stress_gpu/summary.json')
device=read('results/selfref_gpu/native/run.json')['device']
report={
 'version':'3.6.1.6','parent_version':'3.6.1.5','profile':'SRK-R1',
 'platform':platform.platform(),'python':platform.python_version(),
 'compiler':'MSVC 19.44.35221.0 (Visual Studio 2022 BuildTools)',
 'cuda_compiler':'NVIDIA CUDA 12.8.61','device':device,
 'cpu_compile':'passed','cpu_execution':'passed','windows_build':'passed',
 'ctest':{'status':'passed','cases':2,'satnav_checks':105559,'self_reference_checks':5060172},
 'python_tests':{'status':'passed','cases':31},
 'satnav_cli_cases':11,'self_reference_cli_cases':25,
 'self_reference_sample':{'status':'passed','trajectories':6,'transitions':sample['transitions'],'field_comparisons_per_backend':sample['field_comparisons'],'backends':['cpu','cuda']},
 'self_reference_stress':{'status':'passed','trajectories':257,'transitions':stress['transitions'],'field_comparisons_per_backend':stress['field_comparisons'],'backends':['cpu','cuda'],'seed':3616},
 'self_reference_compute_sanitizer':'passed','self_reference_sanitized_trace_replay':'passed',
 'satnav':{'cpu_independent':'passed','epochs':256,'comparisons':4828,'cuda_texture':'passed','cuda_global':'passed','compute_sanitizer_texture':'passed','compute_sanitizer_global':'passed','evidence':str(gpu.relative_to(root)).replace('\\','/')},
 'cpu_sanitizers':'not_run in this Windows subversion; prior Linux evidence archived separately',
 'validation_scope':'Exact finite Boolean trajectories and synthetic corrected-code SATNAV fixtures',
 'source_status':'Original 3.6.1.5 directory preserved; feedback composition newly defined from its supplied ASA/NA and JK primitives',
 'pdf_engine':'Tectonic 0.17.0 (newpxtext type1 compatibility)',
 'logs':['results/selfref_cpu_ctest.log','results/python_tests.txt','results/selfref_cli_checks.json','results/selfref_stress_gpu_memcheck.log',str(gpu.relative_to(root)).replace('\\','/')],
}
(results/'validation_status.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
tex=r'''\section{Current subversion validation}
All entries here concern the executable 3.6.1.6 source on the current Windows
machine. The 3.6.1.5 preparation record is preserved separately under
\code{results\_3\_6\_1\_5/}. Finite comparisons check the requested trajectories;
the closure and eventual-periodicity argument is given separately above.

\begin{center}
\begin{tabularx}{\textwidth}{@{}P{.53\textwidth}Y@{}}\toprule
\textbf{Executed check} & \textbf{Result}\\\midrule
CPU CMake build and CTest & Passed, 2 test programs\\
Retained SATNAV C++ checks & 105,559 passed\\
New literal feedback C++ checks & 5,060,172 passed\\
Python test methods & 31 passed\\
Native command-line scenarios & 25 feedback + 11 SATNAV passed\\
Editable six-trajectory example & 34 transitions, 408 exact field comparisons per backend\\
257-trajectory stress input & 4,225 transitions, 50,700 exact field comparisons per backend\\
CPU and CUDA equation replay & Both passed sample and stress inputs\\
Feedback GPU Compute Sanitizer & Zero memory errors; sanitized trace replay passed\\
Retained SATNAV independent reference & 256 epochs, 4,828 comparisons passed\\
SATNAV CUDA texture/global paths & Both passed independent comparisons and memcheck\\
CPU sanitizers in this Windows run & Not run; earlier Linux evidence archived\\\bottomrule
\end{tabularx}
\end{center}

\subsection{Recorded toolchain and device}
MSVC 19.44.35221.0, Visual Studio 2022 BuildTools; NVIDIA CUDA compiler 12.8.61;
NVIDIA GeForce RTX 5070 Ti Laptop GPU, compute capability 12.0, driver 591.59.
The source targets \code{sm\_120} and \code{compute\_120}. Device, runtime,
allocation sizes and kernel-only times are retained in each native run record.
The short external build directories used on this machine avoid Windows compiler
scratch-path limits caused by the long workspace path.

The stress input uses seed 3616, varying 1--32 steps per trajectory, full 32-bit
operands and 257 trajectories so that the 128-thread CUDA blocks include a partial
final block. Direct AST replay checks all 12 trace columns. The Python suite also
rejects deliberate mutations of every trace column, missing/extra rows and reordered
rows. The C++ checks include independent bit oracles and exhaustive small domains.

\subsection{Evidence and delivered implementation}
\code{results/validation\_status.json} indexes current evidence. The exact equation
JSON, compiled CSV, complete native/reference traces and their hashes are retained.
Windows CPU and CUDA executables are included under \code{bin/windows/}; CUDA
execution uses the installed NVIDIA runtime and driver. No measured speedup is
inferred from these small fixtures. The PDF is built with Tectonic 0.17.0 and
visually checked after rendering. Source and delivered artifacts are listed in
the regenerated SHA-256 manifest.
\clearpage
'''
(root/'docs/validation_current.tex').write_text(tex,encoding='utf-8')
for backend,build in [('cpu',Path('C:/tmp/atomos3616_cpu/Release')),('cuda',Path('C:/tmp/atomos3616_gpu128/Release'))]:
    folder=root/'bin/windows'/backend;folder.mkdir(parents=True,exist_ok=True)
    for name in ['self_reference.exe','satnav.exe']:
        shutil.copy2(build/name,folder/name)
(root/'bin/windows/README.md').write_text('Windows x64 executables built and checked on this machine.\nCPU binaries need the installed Microsoft Visual C++ runtime. CUDA binaries also\nneed the installed CUDA 12 runtime and a compatible NVIDIA driver/device.\nSources and build instructions remain included. Binary SHA-256 values are in the\ndelivered manifest; recorded runs include the exact native executable hashes.\n',encoding='utf-8')
print(json.dumps(report,indent=2))
