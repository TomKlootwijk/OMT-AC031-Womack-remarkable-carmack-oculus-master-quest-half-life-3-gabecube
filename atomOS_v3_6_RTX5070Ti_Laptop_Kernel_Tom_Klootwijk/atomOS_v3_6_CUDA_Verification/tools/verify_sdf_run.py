"""Replay an actual SDF-atlas / Klein CUDA trace against independent scalar rules."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from sdf_reference import verify_source_run

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
parser.add_argument('--atlas',type=Path,required=True)
args=parser.parse_args()
print(json.dumps(verify_source_run(args.directory,args.atlas),indent=2))
