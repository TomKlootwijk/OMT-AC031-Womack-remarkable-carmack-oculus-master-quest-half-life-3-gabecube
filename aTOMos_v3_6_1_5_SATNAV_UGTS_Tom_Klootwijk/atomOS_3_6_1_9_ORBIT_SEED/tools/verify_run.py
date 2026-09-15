#!/usr/bin/env python3
"""Compare a CPU/GPU run with independent Python Householder solves."""
from pathlib import Path
import argparse,csv,json,math,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
from reference import load,solve

def verify(input_dir,run_dir):
    epochs=load(input_dir)
    with (run_dir/'solutions.csv').open() as f:rows=list(csv.DictReader(f))
    if len(rows)!=len(epochs):raise AssertionError('epoch count mismatch')
    max_state=0.;max_cov=0.;comparisons=0;statuses={};fit_counts={};truth_metrics={}
    for e,row in zip(epochs,rows):
        ref=solve(e);assert int(row['epoch_id'])==e['id'];assert row['status']==ref['status'],(e['id'],row['status'],ref['status']);comparisons+=2
        statuses[row['status']]=statuses.get(row['status'],0)+1
        for key in ('asa','na','hits','active','used'):assert int(row[key])==ref[key];comparisons+=1
        if ref['status']=='CONVERGED':
            fit_counts[row['fit']]=fit_counts.get(row['fit'],0)+1
            assert row['fit']==ref['fit'];comparisons+=1
            for key,value in zip(('x_m','y_m','z_m','clock_bias_m'),ref['state']):
                err=abs(float(row[key])-value);max_state=max(max_state,err);assert err<=1e-4,(e['id'],key,err);comparisons+=1
            for key,value in zip(('var_x_m2','var_y_m2','var_z_m2','var_clock_m2'),ref['variance']):
                err=abs(float(row[key])-value);max_cov=max(max_cov,err);assert err<=1e-6+1e-7*abs(value),(e['id'],key,err);comparisons+=1
            for key in ('rms_m','weighted_sse','max_normalized'):
                assert abs(float(row[key])-ref[key])<=1e-5+1e-6*abs(ref[key]),(e['id'],key);comparisons+=1
    if (input_dir/'truth.csv').exists():
        with (input_dir/'truth.csv').open()as f:truth={int(t['epoch_id']):t for t in csv.DictReader(f)}
        grouped={}
        for row in rows:
            if row['status']!='CONVERGED':continue
            t=truth[int(row['epoch_id'])];error=math.sqrt(sum((float(row[k])-float(t[k]))**2 for k in ('x_m','y_m','z_m')))
            grouped.setdefault(t['fixture_class'],[]).append(error)
        for cls,errors in grouped.items():truth_metrics[cls]={'epochs':len(errors),'position_rmse_m':math.sqrt(sum(e*e for e in errors)/len(errors)),'max_position_error_m':max(errors)}
    report={'status':'passed','epochs':len(epochs),'counted_comparisons':comparisons,'statuses':statuses,'fit_counts':fit_counts,
            'max_absolute_state_difference_m':max_state,'max_covariance_diagonal_difference_m2':max_cov,
            'synthetic_truth_metrics':truth_metrics,'scope':'Independent Householder check of supplied corrected-code geometry and native position/clock. Raw-data and physical-model validation are recorded separately.',
            'input_profile':json.loads((input_dir/'profile.json').read_text()) if (input_dir/'profile.json').exists() else None}
    (run_dir/'independent_verification.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--run',type=Path,required=True);a=p.parse_args();print(json.dumps(verify(a.input,a.run),indent=2))
