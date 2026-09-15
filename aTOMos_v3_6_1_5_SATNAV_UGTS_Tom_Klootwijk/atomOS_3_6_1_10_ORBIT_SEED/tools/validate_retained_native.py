"""Execute retained native components on current release binaries and record lineage."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
NAMES=('satnav.exe','satnav_stream.exe','self_reference.exe','coupled_kernel.exe','orbit_worker.exe')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cpu-build',type=Path,required=True)
    p.add_argument('--cuda-build',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--copy-binaries',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    report={'release':'3.6.1.9','status':'running','scope':'Fresh retained-component regression; fixture and component schema versions remain distinct','commands':[],'binaries':{}}
    def run(args,name):
        command=list(map(str,args));log=a.out/(name+'.log')
        with log.open('w',encoding='utf-8') as f:result=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        report['commands'].append({'name':name,'command':command,'returncode':result.returncode,'log':str(log)})
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        if result.returncode:raise RuntimeError(name+' failed; see '+str(log))
    for backend,build in [('cpu',a.cpu_build),('cuda',a.cuda_build)]:
        binaries=build.resolve()/'Release';target=a.out/backend;target.mkdir()
        run(['ctest','--test-dir',build.resolve(),'-C','Release','--output-on-failure'],backend+'_ctest')
        run([binaries/'satnav.exe','--input',ROOT/'examples/demo','--out',target/'satnav','--backend',backend,'--verify'],backend+'_satnav')
        run([sys.executable,ROOT/'tools/verify_run.py','--input',ROOT/'examples/demo','--run',target/'satnav'],backend+'_satnav_independent')
        run([sys.executable,ROOT/'tools/self_reference.py','--input',ROOT/'examples/self_reference/stress_equations.json',
             '--out',target/'self_reference','--binary',binaries/'self_reference.exe','--backend',backend],backend+'_self_reference')
        run([sys.executable,ROOT/'tools/validate_coupled.py','--out',target/'coupled','--binary',binaries/'coupled_kernel.exe','--backend',backend],backend+'_coupled')
        run([sys.executable,ROOT/'tools/validate_live_native.py','--out',target/'live_worker','--binary',binaries/'satnav_stream.exe','--backend',backend],backend+'_live_worker')
        report['binaries'][backend]={name:{'source':str(binaries/name),'sha256':sha(binaries/name),'bytes':(binaries/name).stat().st_size} for name in NAMES}
        print(backend,'retained checks passed',flush=True)
    if a.copy_binaries:
        for backend,items in report['binaries'].items():
            folder=ROOT/'bin'/backend;folder.mkdir(parents=True,exist_ok=True)
            for name,meta in items.items():
                destination=folder/name;shutil.copy2(meta['source'],destination)
                if sha(destination)!=meta['sha256']:raise RuntimeError('Copied binary digest mismatch')
                meta['delivered']=str(destination.relative_to(ROOT))
    report['status']='passed';(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(a.out/'summary.json')
if __name__=='__main__':main()
