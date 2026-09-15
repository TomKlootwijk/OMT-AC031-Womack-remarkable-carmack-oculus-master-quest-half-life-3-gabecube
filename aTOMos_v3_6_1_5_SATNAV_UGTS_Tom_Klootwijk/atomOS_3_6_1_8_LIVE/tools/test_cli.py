#!/usr/bin/env python3
from pathlib import Path
import argparse,csv,json,shutil,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
def run(binary):
    cases=[]
    with tempfile.TemporaryDirectory()as t:
        work=Path(t)
        def command(label,args,expected):
            p=subprocess.run([str(binary),*map(str,args)],capture_output=True,text=True)
            assert p.returncode==expected,(label,p.returncode,p.stderr)
            cases.append({'case':label,'exit_code':p.returncode})
        command('help',['--help'],0)
        command('unknown option',['--wrong'],1)
        command('invalid backend',['--backend','auto'],1)
        command('zero iterations',['--max-iterations','0'],1)
        command('missing file',['--input',work/'absent','--out',work/'new'],1)
        command('existing output',['--input',ROOT/'examples/demo','--out',work],1)
        for label,change in [('duplicate_channel',lambda lines:lines+[lines[1]]),('negative_sigma',lambda lines:[lines[0],','.join(lines[1].split(',')[:8]+['-1','1']),*lines[2:]]),('nan_coordinate',lambda lines:[lines[0],lines[1].replace(lines[1].split(',')[3],'nan',1),*lines[2:]])]:
            folder=work/label;shutil.copytree(ROOT/'examples/demo',folder)
            p=folder/'observations.csv';p.write_text('\n'.join(change(p.read_text().splitlines()))+'\n')
            command(label,['--input',folder,'--out',work/(label+'_out')],1)
        command('valid run',['--input',ROOT/'examples/demo','--out',work/'valid','--backend','cpu','--verify'],0)
        command('iteration status recorded',['--input',ROOT/'examples/demo','--out',work/'limit','--max-iterations','1'],0)
        with (work/'limit/solutions.csv').open()as f:
            assert any(x['status']=='ITERATION_LIMIT'for x in csv.DictReader(f))
    report={'status':'passed','cases':len(cases),'details':cases};(ROOT/'results/cli_tests.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.binary),indent=2))
