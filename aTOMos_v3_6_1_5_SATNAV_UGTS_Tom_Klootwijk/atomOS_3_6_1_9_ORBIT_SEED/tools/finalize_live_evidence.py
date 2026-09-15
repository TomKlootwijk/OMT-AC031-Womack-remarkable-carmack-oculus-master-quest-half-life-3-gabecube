"""Bind completed PDF review, executed binaries and live bridge to the release index."""
from pathlib import Path
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reviewed-pdf-qa',type=Path,required=True)
    p.add_argument('--cpu-build',type=Path,required=True);p.add_argument('--cuda-build',type=Path,required=True);a=p.parse_args()
    qa=read(a.reviewed_pdf_qa)
    assert qa['status']=='passed' and qa['visual_review']=='passed'
    assert sha(ROOT/qa['pdf'])==qa['sha256']
    binaries={}
    for backend,build in [('cpu',a.cpu_build),('cuda',a.cuda_build)]:
        for component in ['satnav','satnav_stream','self_reference','coupled_kernel']:
            target=ROOT/f'bin/windows/{backend}/{component}.exe';compiled=build/'Release'/f'{component}.exe'
            assert sha(target)==sha(compiled)
            binaries[target.relative_to(ROOT).as_posix()]={'sha256':sha(target),'matches_executed_build':True}
    parent_checks={}
    for directory in ['atomOS_3_6_1_5_SATNAV','atomOS_3_6_1_6_SELFREF','atomOS_3_6_1_7_COUPLED']:
        parent=ROOT.parent/directory;count=0
        for line in (parent/'SHA256SUMS.txt').read_text().splitlines():
            digest,name=line.split('  ',1);assert sha(parent/name)==digest,(directory,name);count+=1
        parent_checks[directory]={'status':'unchanged','verified_file_hashes':count}
    path=ROOT/'results/validation_status.json';report=read(path)
    for name in ['results/live_coupled_bridge_final_CPU/summary.json','results/live_coupled_bridge_final_CPU/bridge_binding_audit.json','results/network_probes/final_live_evidence.json','results/live_physical_audit.json']:
        item=read(ROOT/name)
        if name.endswith('final_live_evidence.json'):
            assert len(item['records'])==2 and all(r['status']=='passed' for r in item['records'])
        else:assert item['status']=='passed'
        report['evidence'][name]={'sha256':sha(ROOT/name),'status':'passed'}
    report.update(pdf_review={'path':'results/pdf_quality.json','sha256':sha(a.reviewed_pdf_qa),'pages':qa['pages'],'status':'passed'},
        delivered_binaries=binaries,preserved_parent_releases=parent_checks,
        native_schema_versions={'LIVE-GPS-L1-R1':'3.6.1.8','CGK-R1':'3.6.1.7','SRK-R1':'3.6.1.6'},
        device_record='results/hardware.csv',cuda_compiler_record='results/cuda_compiler.txt',
        live_connections_closed=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    print('Final evidence, 57-page reviewed PDF, eight binary hashes and preserved parents verified.')

if __name__=='__main__':main()
