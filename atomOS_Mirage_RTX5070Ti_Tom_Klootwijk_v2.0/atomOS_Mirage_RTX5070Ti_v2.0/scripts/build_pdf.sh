#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../docs"
pdflatex -interaction=nonstopmode -halt-on-error specification.tex
pdflatex -interaction=nonstopmode -halt-on-error specification.tex
cp specification.pdf ../atomOS_Mirage_RTX5070Ti_Tom_Klootwijk.pdf
