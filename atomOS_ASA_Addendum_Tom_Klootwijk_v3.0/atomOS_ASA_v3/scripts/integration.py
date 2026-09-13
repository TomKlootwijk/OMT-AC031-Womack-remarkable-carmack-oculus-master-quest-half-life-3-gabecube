#!/usr/bin/env python3
"""Small executable cases in automatically cleaned temporary directories."""
from pathlib import Path
import argparse,json,subprocess,sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from python.reference import verify_directory
from python.provenance import seal,verify
p=argparse.ArgumentParser();p.add_argument('--executable',type=Path,required=True);p.add_argument('--gpu',action='store_true')
a=p.parse_args();exe=str(a.executable.resolve());results=[]
cases=[(['--samples','257','--layout','morton'],True),(['--samples','257','--layout','linear'],True),
       (['--samples','0'],True),(['--samples','1','--rho-bins','8','--phi-bins','8'],True),
       (['--rho-bins','9'],False),(['--samples','-1'],False),(['--budget-mib','1'],False),
       (['--layout','bad'],False),(['--samples','4194305'],False),(['--unknown','1'],False)]
for args,expected in cases:
    with tempfile.TemporaryDirectory(prefix='asa_case_') as tmp:
        directory=Path(tmp)/'run'
        run=subprocess.run([exe,'--out',str(directory),*args],text=True,capture_output=True)
        if (run.returncode==0)!=expected:raise RuntimeError(f'{args}: {run.stdout}\n{run.stderr}')
        if expected:
            oracle=verify_directory(directory);value=seal(directory)
            if not verify(directory,value['head']):raise RuntimeError('seal check failed')
            repeated=subprocess.run([exe,'--out',str(directory),*args],capture_output=True)
            if repeated.returncode==0:raise RuntimeError('existing result directory was overwritten')
        results.append({'arguments':args,'expected_success':expected,'status':'pass'})
print(json.dumps({'backend':'GPU' if a.gpu else 'CPU','cases':results},indent=2))
