#!/usr/bin/env python3
"""Independent NumPy least-squares oracle for the prepared observation contract."""
from pathlib import Path
import argparse,csv,json,math,sys
import numpy as np
from make_fixture import anchor
from sclp import quantize,pack

def verify(dataset:Path,result:Path):
    meta=list(csv.DictReader((dataset/'epochs.csv').open()))
    results=list(csv.DictReader(result.open()));obs={int(e['epoch_id']):[]for e in meta}
    for r in csv.DictReader((dataset/'observations.csv').open()):obs[int(r['epoch_id'])].append(r)
    if len(results)!=len(meta):raise AssertionError('result length mismatch')
    for a,b in zip(meta,results):assert a['epoch_id']==b['epoch_id'] and a['tick_ms']==b['tick_ms']
    o,e,n,u=map(np.array,anchor());rotation=np.vstack([e,n,u]);checks=0;max_state=0.;max_sigma=0.;ok=0;status_counts={}
    def check(condition,message):
        nonlocal checks
        checks+=1
        if not condition:raise AssertionError(message)
    for m,out in zip(meta,results):
        rows=sorted(obs[int(m['epoch_id'])],key=lambda v:int(v['slot']));count=len(rows);valid=(1<<count)-1
        asa=valid&int(m['asa_mask']);na=asa&int(m['na_mask']);hits=(na&int(m['boundary_mask'])).bit_count();mask=0 if hits else na
        for key,value in [('asa',asa),('na',na),('hits',hits),('output_mask',mask),('used',mask.bit_count())]:check(int(out[key])==value,key)
        q,j,k=map(lambda key:int(m[key]),['q_before','j','k']);check(int(out['q_after'])==((j&(1-q))|((1-k)&q)),'JK')
        check(int(out['blend'])==(int(m['blend_bits']).bit_count()%2),'blend')
        selected=[r for i,r in enumerate(rows) if mask&(1<<i)]
        expected='whole_word_absorbed' if hits else 'insufficient_observations' if len(selected)<4 else None
        if expected is None:
            sat=np.array([[float(r[k])for k in ('sat_rxframe_x_m','sat_rxframe_y_m','sat_rxframe_z_m')]for r in selected]);code=np.array([float(r['corrected_code_m'])for r in selected]);sigma=np.array([float(r['sigma_m'])for r in selected])
            x=np.array([float(m[k])for k in ('initial_x_m','initial_y_m','initial_z_m','initial_clock_m')]);converged=False
            for _ in range(20):
                d=x[:3]-sat;ranges=np.linalg.norm(d,axis=1);G=np.column_stack((d/ranges[:,None],np.ones(len(sat))));A=G/sigma[:,None];b=(code-ranges-x[3])/sigma
                delta,_,rank,_=np.linalg.lstsq(A,b,rcond=1e-11)
                if rank<4:expected='rank_deficient';break
                x+=delta
                if np.linalg.norm(delta[:3])<=1e-4 and abs(delta[3])<=1e-4:converged=True;break
            if expected is None:expected='ok' if converged else 'iteration_limit'
        check(out['status']==expected,'status: '+out['status']+' vs '+str(expected));status_counts[expected]=status_counts.get(expected,0)+1
        if expected!='ok':continue
        ok+=1;actual=np.array([float(out[k])for k in ('x_m','y_m','z_m','clock_m')]);error=float(np.max(np.abs(actual-x)));max_state=max(max_state,error);check(error<2e-5,'four-state independent error')
        d=x[:3]-sat;ranges=np.linalg.norm(d,axis=1);G=np.column_stack((d/ranges[:,None],np.ones(len(sat))));A=G/sigma[:,None]
        cov=np.linalg.inv(A.T@A);sd=np.sqrt(np.diag(cov));actual_sd=np.array([float(out[k])for k in ('sigma_x_m','sigma_y_m','sigma_z_m','sigma_clock_m')]);serr=float(np.max(np.abs(sd-actual_sd)));max_sigma=max(max_sigma,serr);check(serr<1e-7,'formal covariance')
        residual=code-np.linalg.norm(sat-actual[:3],axis=1)-actual[3]
        check(abs(float(out['rms_m'])-float(np.sqrt(np.mean(residual**2))))<1e-7,'postfit RMS')
        local=rotation@(actual[:3]-o);check(np.max(np.abs(local-np.array([float(out[k])for k in ('east_m','north_m','up_m')])))<1e-8,'ENU')
        rho=math.log(math.hypot(local[0],local[1])/10000);theta=math.atan2(local[1],local[0])
        if .01<=math.hypot(local[0],local[1])<=10000 and rho>=-20:
            fields=quantize(rho,theta,int(m['tick_ms']),float(m['hinge_rad']))
            for key,layout in [('key_contiguous','contiguous'),('key_morton','morton')]:check(int(out[key])==pack(fields,layout),'key integer identity '+key)
        else:check(int(out['chart_status'])!=0,'out-of-chart status')
    truth=list(csv.DictReader((dataset/'truth.csv').open())) if (dataset/'truth.csv').exists() else []
    errors=[]
    for t,r in zip(truth,results):
        if r['status']=='ok':errors.append(math.dist([float(t[k])for k in ['x_m','y_m','z_m']],[float(r[k])for k in ['x_m','y_m','z_m']]))
    return {'status':'passed','epochs':len(meta),'solved':ok,'checks':checks,'status_counts':status_counts,'max_independent_state_difference_m':max_state,'max_formal_sigma_difference_m':max_sigma,'max_fixture_position_error_m':max(errors,default=None),'fixture_position_rmse_m':math.sqrt(sum(x*x for x in errors)/len(errors))if errors else None,'oracle':'NumPy lstsq (independent of C++ streaming Givens QR)','dataset':dataset.name,'result':result.name}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',type=Path);p.add_argument('result',type=Path);p.add_argument('--report',type=Path);a=p.parse_args();report=verify(a.dataset,a.result);text=json.dumps(report,indent=2)+'\n';print(text,end='');
    if a.report:a.report.write_text(text)
