"""Supplement the main memcheck matrix with the new launch settings."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from reference import verify_run
from validate import find_compute_sanitizer

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--exe',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    exe=a.exe.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    sanitizer=find_compute_sanitizer()
    records=[]
    result={'status':'running','runs':records}
    def save():(out/'supplemental.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    if not sanitizer:
        result.update(status='not_run',reason='native Compute Sanitizer unavailable');save();return 3
    try:
        for layout in ('linear','morton8'):
            for read,block in (('texture',64),('texture-packed',64),('texture-packed',128)):
                label=f'{read}_{layout}_{block}';run=out/label
                cmd=[str(sanitizer),'--tool','memcheck','--error-exitcode','2',str(exe),'--rows','17','--angles','257','--epochs','3','--mode','shift-or','--fringe','on','--layout',layout,'--read',read,'--block-size',str(block),'--cache','max-l1','--out',str(run)]
                with (out/(label+'.log')).open('w',encoding='utf-8') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
                rec={'command':cmd,'exit_code':r.returncode,'log':label+'.log'};records.append(rec);save()
                if r.returncode:raise RuntimeError(f'{label} failed')
                rec['verification']=verify_run(run,expected_backend='cuda',expected_read=read)
                s=json.loads((run/'summary.json').read_text());k=s['device']['kernel']
                if k['block_size']!=block or not k['max_l1_requested']:raise ValueError('launch metadata differs')
                save()
        result['status']='passed';save();return 0
    except (OSError,ValueError,RuntimeError) as exc:
        result.update(status='failed',reason=str(exc));save();return 1
if __name__=='__main__':raise SystemExit(main())
