#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../docs"
pdflatex -interaction=nonstopmode -halt-on-error addendum.tex
pdflatex -interaction=nonstopmode -halt-on-error addendum.tex
cp addendum.pdf ../atomOS_ASA_Addendum_Tom_Klootwijk.pdf
