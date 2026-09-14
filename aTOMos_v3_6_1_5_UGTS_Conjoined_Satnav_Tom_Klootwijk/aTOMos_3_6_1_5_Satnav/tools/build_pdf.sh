#!/bin/sh
set -eu
cd "$(dirname "$0")/../docs"
mkdir -p .build
latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=.build conjoined.tex
cp .build/conjoined.pdf ../aTOMos_v3_6_1_5_UGTS_Conjoined_Satnav_Tom_Klootwijk.pdf
