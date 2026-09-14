#!/bin/sh
set -eu
cd "$(dirname "$0")/../docs"
mkdir -p .build
latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=.build satnav.tex
cp .build/satnav.pdf ../aTOMos_v3_6_1_5_SATNAV_UGTS_Tom_Klootwijk.pdf
