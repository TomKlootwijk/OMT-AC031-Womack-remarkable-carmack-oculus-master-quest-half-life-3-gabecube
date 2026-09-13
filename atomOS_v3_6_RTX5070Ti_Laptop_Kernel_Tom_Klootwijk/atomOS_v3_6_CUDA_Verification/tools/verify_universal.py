"""Independently replay an exported Tom Klootwijk atomOS word-plus-U run."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from universal_reference import verify_export
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
args=parser.parse_args()
try:
    result=verify_export(args.directory)
except Exception as error:
    print(json.dumps(dict(status='failed',reason=str(error))))
    raise SystemExit(1)
print(json.dumps(result,indent=2))
