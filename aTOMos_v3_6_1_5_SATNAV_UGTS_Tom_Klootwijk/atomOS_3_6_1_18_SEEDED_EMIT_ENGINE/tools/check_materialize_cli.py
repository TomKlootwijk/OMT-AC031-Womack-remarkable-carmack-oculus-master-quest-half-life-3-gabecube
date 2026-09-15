"""Exercise real materializer dispatch paths and failure publication contracts."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from build_seeded_fixtures import ROOT,FIXTURES,SPECS,imports,sha
from verify_seeded_runtime import replay_reference,compare_native

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--binary',type=Path,required=True);a=p.parse_args()
    report={'profile':'ATOMOS-MATERIALIZE-CLI-CHECK-R1','binary_sha256':sha(a.binary.read_bytes()),'script_sha256':sha(Path(__file__).read_bytes()),'completed_cases':[],'admission_cases':[]}
    with tempfile.TemporaryDirectory(prefix='atomos_materialize_cli_') as directory:
        folder=Path(directory)
        for fixture,spec in SPECS.items():
            program=FIXTURES/fixture/Path(spec['source']).name.replace('.literal.json','.tmg')
            reference=replay_reference(fixture);ticks=reference['executed_steps']+3
            for fetch in ['texture','global']:
                for dispatch in ['fused','reference']:
                    artifact=folder/'output.bin';metadata=folder/'report.json'
                    args=[str(a.binary),'--program',str(program),'--output',str(artifact),'--report',str(metadata),'--steps',str(ticks),'--chunk','32','--fetch',fetch,'--dispatch',dispatch]
                    subprocess.run(args,check=True,capture_output=True,text=True)
                    result=compare_native(reference,json.loads(metadata.read_text()),artifact.read_bytes(),ticks)
                    report['completed_cases'].append(dict(fetch=fetch,dispatch=dispatch,**result))
        # Prefixes and errors must preserve an existing artifact byte-for-byte.
        sentinel=b'existing artifact must survive incomplete execution'
        artifact.write_bytes(sentinel)
        for ticks in [0,1,10]:
            result=subprocess.run([str(a.binary),'--program',str(program),'--output',str(artifact),'--report',str(metadata),'--steps',str(ticks)],capture_output=True,text=True)
            data=json.loads(metadata.read_text())
            if result.returncode!=2 or data['status']!='prefix' or data['artifact_written'] is not False or artifact.read_bytes()!=sentinel:raise ValueError('Prefix publication contract failed')
            report['admission_cases'].append({'case':'prefix_preserves_existing_artifact','ticks':ticks,'exit_code':result.returncode})
        _,core,fmt,_,_,_=imports()
        noemit=folder/'noemit.tmg'
        noemit.write_bytes(fmt.dumps(core.Program(cells=[core.Cell(0,0,int(core.Opcode.HALT))],entry=0,seed=0,default_ticks=1,initial_state=core.State(),flags=3)))
        result=subprocess.run([str(a.binary),'--program',str(noemit),'--output',str(artifact)],capture_output=True,text=True)
        if result.returncode!=1 or 'no EMIT' not in result.stderr or artifact.read_bytes()!=sentinel:raise ValueError('No-EMIT admission failed')
        report['admission_cases'].append({'case':'complete_without_emit_refused','exit_code':1})
        original=noemit.read_bytes()
        for options in [['--output',str(noemit)],['--output',str(artifact),'--report',str(noemit)],['--output',str(artifact),'--report',str(artifact)]]:
            result=subprocess.run([str(a.binary),'--program',str(noemit),*options],capture_output=True,text=True)
            if result.returncode!=1 or 'aliases' not in result.stderr or noemit.read_bytes()!=original or artifact.read_bytes()!=sentinel:raise ValueError('Aliasing admission failed')
            report['admission_cases'].append({'case':'source_or_report_alias_refused','exit_code':1})
    report['complete']=True
    (ROOT/'review/r18_materialize_cli_checks.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Verified',len(report['completed_cases']),'complete path/fixture cases and',len(report['admission_cases']),'publication/admission cases')

if __name__=='__main__':main()
