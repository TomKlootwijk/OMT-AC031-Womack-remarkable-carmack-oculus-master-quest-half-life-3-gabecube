#!/usr/bin/env python3
"""Create the 3.6.1.9 main document while retaining the prior equation body."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent / "atomOS_3_6_1_8_LIVE"


def main():
    old = (PARENT / "docs/satnav.tex").read_text(encoding="utf-8")
    preamble = old.split(r"\begin{document}", 1)[0]
    preamble = preamble.replace("3.6.1.8", "3.6.1.9").replace("14 September 2026", "15 September 2026")
    preamble = preamble.replace("LIVE GPS / LITERAL STATE", "ORBIT SEEDS / LITERAL STATE")
    preamble = preamble.replace("Live GPS Receiver and Self-Referential Kernel", "Orbital Seeds, Timestamp Queries and Literal Kernel")
    preamble = preamble.replace("SATNAV-R1 corrected-code positioning; UGTS SCLP source integration and SM120 CUDA kernel", "Compact orbital seeds; two ASA/NA sets; synchronous JK; ground-station horizons and held-out forecast accuracy")
    start = old.index(r"\input{live.tex}")
    end = old.rindex("\\vfill\n\\begin{panel}")
    body = old[start:end]
    body = body.replace("Current 3.6.1.8 evidence", "Retained 3.6.1.8 evidence")
    (ROOT / "docs/retained_satnav_body.tex").write_text(body, encoding="utf-8")
    front = r"""\begin{document}
\begin{titlepage}\thispagestyle{empty}
{\sffamily\color{accent}\large AC031 / AC130 ATOMOS \hfill ORBIT-SEED-R1}\par
\vspace{18mm}
{\sffamily\bfseries\fontsize{51}{58}\selectfont\color{ink}aTOMos v3.6.1.9}\par
\vspace{10mm}
{\sffamily\fontsize{28}{34}\selectfont Orbital seeds and\par timestamp queries}\par
\vspace{7mm}
{\sffamily\fontsize{21}{27}\selectfont\color{gold}Ground-station horizons\par with the literal self-referential kernel}\par
\vspace{12mm}
{\large MEO / GEO / inclined geosynchronous / high elliptical\par
Two ASA/NA sets \;\textperiodcentered\; synchronous JK \;\textperiodcentered\; CPU / CUDA}\par
\vspace{16mm}
{\sffamily\bfseries\Large Tom Klootwijk}\par
\begin{tabular}{@{}ll@{}}
Author-supplied identifier & \textbf{NL200678942}\\
Author-supplied date & \textbf{10-07-1990}\\
Source lineage & aTOMos 3.6.1 / UGTS-KC 3.6.2 SCLP\\
Preserved parent & 3.6.1.8 LIVE-GPS-L1-R1\\
Target & RTX 5070 Ti Laptop / SM120 / FP64\\
Release & 3.6.1.9 / 15 September 2026\\
\end{tabular}
\vfill
\begin{panel}
\textbf{4.27--4.29 KiB per complete demonstration seed}\par
Reconstruct physical satellite states at requested timestamps. Keep full state,
time, Up and model dependencies. Measure forecast error against later withheld
orbit data and report when each accuracy budget is exceeded.
\end{panel}
{\small\color{muted}Editable equations, native binaries, packed examples, a local
timeline interface and verified evidence. Prepared with AI assistance.}
\end{titlepage}
\setcounter{page}{2}
\section*{Release and implementation record}
\addcontentsline{toc}{section}{Release and implementation record}
This subversion implements \textbf{ORBIT-SEED-R1}. It packs a complete physical
model and reconstructs a satellite's ground-station-relative position at an
arbitrary supported timestamp. The examples cover real MEO, GEO, IGSO and high
elliptical targets. Two explicit ASA/NA mask sets feed the existing synchronous
JK operation; the resulting state changes the ordered query schedule.

\begin{tabularx}{\textwidth}{@{}P{.28\textwidth}Y@{}}\toprule
\textbf{Delivered capability} & \textbf{Concrete implementation}\\\midrule
Compact seeds & 4,371--4,391 bytes, including all per-seed physical, frame, forcing, station, query and word parameters.\\
Timestamp scrubbing & Native CPU canonical checkpoints, bounded memory, exact fractional query time and query-order-independent states.\\
Physical prediction & Truncated Earth gravity, Sun/Moon forcing, radiation pressure, fitted RTN acceleration and explicit frame/time model.\\
Literal state & Two ordered whole-word ASA/NA stages, editable X/J/K equations, synchronous JK and a trace of the selected next timestamp.\\
Station geometry & Full ECEF/ENU position and velocity, Up, range/range rate, azimuth/elevation, original UGTS keys and complete time/winding.\\
Both horizons & Refined visibility events and sampled prediction-error horizons against withheld later orbit data.\\
Execution evidence & Native CPU/CUDA, independent equations and propagation, isolated packed-only replay, physical reference comparisons and actual-device sanitizer.\\
User interface & Local timeline, exact timestamp input, satellite/station selection, pass search and ordered feedback replay.\\\bottomrule
\end{tabularx}

The seed epoch is 2 January 2025, with one earlier training day and seven withheld
forecast days. Small seed size does not imply unlimited accuracy. The GEO example
starts near its reference but reaches about 533 m maximum disagreement over the
week; the high elliptical example reaches about 19.4 km. The complete curves and
sampled threshold intervals follow the equations.

The prior LIVE-GPS-L1-R1, CGK-R1, SRK-R1 and SATNAV-R1 equations remain in the
second part of this volume. Their previous receiver-position measurements are
historical component evidence, not satellite forecast accuracy. Fresh retained
component regressions are recorded for this subversion. The parent release and
its delivered files are preserved separately.
\clearpage
\tableofcontents\clearpage
\input{orbit.tex}
\section*{Retained receiver, geometry and source contracts}
\addcontentsline{toc}{section}{Retained receiver, geometry and source contracts}
The following sections retain the earlier executable mathematical profiles and
their dated measurements. References to the 3.6.1.8 live receiver are historical.
The current orbital seed profile, timestamp queries and satellite forecast
evidence are in Section~\ref{sec:orbit}. Fresh regression results link these
retained implementations to the 3.6.1.9 binaries without relabelling the earlier
receiver measurements as orbital accuracy.
\input{retained_satnav_body.tex}
\vfill\begin{panel}
\textbf{aTOMos v3.6.1.9 --- Orbital seeds and literal state}\par
Tom Klootwijk \quad NL200678942 \quad 10-07-1990\par
\textbf{Profiles:} ORBIT-SEED-R1, LIVE-GPS-L1-R1, CGK-R1, SRK-R1 and SATNAV-R1.\par
\textbf{Release date:} 15 September 2026.\par
Compact explicit state, timestamp reconstruction, two ASA/NA sets, synchronous
JK, ground-station horizons and measured forecast limits.
\end{panel}
\end{document}
"""
    sizes = json.loads((ROOT / "examples/orbit/seeds/seed_sizes.json").read_text())
    low, high = min(r["file_bytes"] for r in sizes), max(r["file_bytes"] for r in sizes)
    front = front.replace("4.27--4.29 KiB", f"{low/1024:.2f}--{high/1024:.2f} KiB")
    front = front.replace("4,371--4,391 bytes", f"{low:,}--{high:,} bytes")
    front = front.replace("Truncated Earth gravity, Sun/Moon forcing, radiation pressure, fitted RTN acceleration and explicit frame/time model.",
        "Full degree/order-12 Earth gravity, Sun/Moon forcing, radiation pressure, fitted RTN acceleration, varying EOP and Schwarzschild correction.")
    front = front.replace("The seed epoch is 2 January 2025, with one earlier training day and seven withheld\nforecast days. Small seed size does not imply unlimited accuracy. The GEO example\nstarts near its reference but reaches about 533 m maximum disagreement over the\nweek; the high elliptical example reaches about 19.4 km. The complete curves and\nsampled threshold intervals follow the equations.",
        "The seed epoch is 2 January 2025. A fixed rule chooses among one-, three- and\nseven-day earlier training windows using an earlier validation day. R2 keeps all\nfour January examples below 10 metres at every tested first-day reference sample.\nLonger intervals still have failures. January is a reused development benchmark;\na separate February confirmation follows in the evidence. The default codec\nuses lossless one-bit planes in machine words. Propagation still uses binary64\narithmetic, with measured CPU/GPU and independent integration differences.")
    front = front.replace("time, Up and model dependencies. Measure forecast error against later withheld", "time, Up and model dependencies. Measure forecast error against later reference")
    front = front.replace("orbit data and report when each accuracy budget is exceeded.", "orbit data and report when each accuracy budget is exceeded.")
    (ROOT / "docs/satnav.tex").write_text(preamble + front, encoding="utf-8")


if __name__ == "__main__": main()
