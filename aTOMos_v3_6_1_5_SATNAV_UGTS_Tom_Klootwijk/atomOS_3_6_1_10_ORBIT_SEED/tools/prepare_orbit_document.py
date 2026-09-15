#!/usr/bin/env python3
"""Prepare R10 front matter while retaining the verified R9 equation body."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    parent = ROOT.parent / "atomOS_3_6_1_9_ORBIT_SEED"
    text = (parent / "docs/satnav.tex").read_text(encoding="utf-8")
    text = text.replace("3.6.1.9", "3.6.1.10")
    text = text.replace("fontsize{51}{58}", "fontsize{47}{55}")
    text = text.replace("Preserved parent & 3.6.1.8 LIVE-GPS-L1-R1", "Preserved parent & 3.6.1.9 ORBIT-SEED-R1")
    text = text.replace(r"\input{orbit.tex}", r"\input{seed_optimization.tex}" + "\n" + r"\input{phi_source_audit.tex}" + "\n" + r"\input{calendar_phase.tex}" + "\n" + r"\input{orbit.tex}")
    text = text.replace("Fresh retained\ncomponent regressions are recorded for this subversion.", "The inherited 3.6.1.9 measurements are distinguished from the new\n3.6.1.10 checks in the optimization chapter.")
    text = text.replace("Fresh regression results link these\nretained implementations to the 3.6.1.10 binaries", "The baseline regression results bind the preserved component binaries; the\noptimization chapter reports fresh checks of this release")
    (ROOT / "docs/satnav.tex").write_text(text, encoding="utf-8")

if __name__ == "__main__": main()
