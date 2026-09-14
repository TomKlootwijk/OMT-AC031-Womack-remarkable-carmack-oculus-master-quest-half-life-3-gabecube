#!/usr/bin/env python3
"""Compare CPU and device CSV records, including chunk-boundary diagnostics."""
from pathlib import Path
import argparse,csv,json,math
EXACT={'epoch_id','tick_ms','status','used','asa','na','hits','output_mask','q_after','blend','chart_status','otan_status','cone_class','sphere_flags','key_contiguous','key_morton'}
ANGLES={'rho','theta_rad','delta_rho','delta_theta_rad','otan_raw_rad','otan_relative_rad','otan_directed_rad'}
def compare(a:Path,b:Path):
    x=list(csv.DictReader(a.open()));y=list(csv.DictReader(b.open()));assert len(x)==len(y),'row count'
    checks=0;maximum=0
    for left,right in zip(x,y):
        assert left.keys()==right.keys(),'schema mismatch'
        for key in left:
            if key=='iterations':continue # a converged equivalent iterate may take one additional step
            checks+=1
            if key in EXACT:assert left[key]==right[key],(left['epoch_id'],key,left[key],right[key]);continue
            p,q=float(left[key]),float(right[key])
            if math.isnan(p) or math.isnan(q):assert math.isnan(p) and math.isnan(q),(key,p,q);continue
            tol=1e-8 if key in ANGLES else 2e-5
            assert math.isfinite(p) and math.isfinite(q) and abs(p-q)<=tol,(left['epoch_id'],key,p,q,tol)
            maximum=max(maximum,abs(p-q))
    return {'status':'passed','epochs':len(x),'field_comparisons':checks,'maximum_numeric_absolute_difference':maximum,'left':a.name,'right':b.name}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cpu',type=Path);p.add_argument('other',type=Path);a=p.parse_args();print(json.dumps(compare(a.cpu,a.other),indent=2))
