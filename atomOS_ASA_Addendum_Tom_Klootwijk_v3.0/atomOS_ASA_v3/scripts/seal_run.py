#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from python.provenance import seal
p=argparse.ArgumentParser(description='Seal local ASA result records')
p.add_argument('directory',type=Path);a=p.parse_args()
print(json.dumps(seal(a.directory),indent=2))
