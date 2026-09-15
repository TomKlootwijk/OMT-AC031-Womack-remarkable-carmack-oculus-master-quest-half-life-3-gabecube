"""Independent standard-library Householder GNSS reference, not shared C++ math."""
from __future__ import annotations
import csv,math
from pathlib import Path

C=299792458.0

def load(folder: Path):
    epochs=[]
    with (folder/'epochs.csv').open() as f:
        for row in csv.DictReader(f):
            e={'id':int(row['epoch_id']),'time':float(row['t_rx_gpst_s']),
               'seed':[float(row[k])for k in ['x0_m','y0_m','z0_m','b0_m']],
               'asa':int(row['asa_mask']),'na':int(row['na_mask']),'boundary':int(row['boundary_mask']),'observations':{}}
            epochs.append(e)
    by_id={e['id']:e for e in epochs}
    with (folder/'observations.csv').open() as f:
        for row in csv.DictReader(f):
            by_id[int(row['epoch_id'])]['observations'][int(row['channel'])]={
                'sat':[float(row[k])for k in ['sx_rx_m','sy_rx_m','sz_rx_m']],
                'corrected':float(row['code_m'])+float(row['add_correction_m']),
                'sigma':float(row['sigma_m']),'ready':int(row['ready'])}
    return epochs

def householder(a,b):
    m=len(a);r=[list(row)for row in a];z=list(b)
    for k in range(4):
        length=math.sqrt(sum(r[i][k]**2 for i in range(k,m)))
        if length==0:raise ValueError('rank')
        alpha=-math.copysign(length,r[k][k]);v=[r[i][k] for i in range(k,m)];v[0]-=alpha
        denom=sum(q*q for q in v)
        if denom==0:raise ValueError('rank')
        for j in range(k,4):
            beta=2*sum(v[i-k]*r[i][j]for i in range(k,m))/denom
            for i in range(k,m):r[i][j]-=beta*v[i-k]
        beta=2*sum(v[i-k]*z[i]for i in range(k,m))/denom
        for i in range(k,m):z[i]-=beta*v[i-k]
    largest=max(abs(r[i][i])for i in range(4))
    if any(abs(r[i][i])<=1e-10*largest for i in range(4)):raise ValueError('rank')
    def back(rhs):
        x=[0.]*4
        for i in range(3,-1,-1):x[i]=(rhs[i]-sum(r[i][j]*x[j]for j in range(i+1,4)))/r[i][i]
        return x
    x=back(z[:4]);cols=[back([float(i==j)for i in range(4)])for j in range(4)]
    variance=[sum(cols[j][i]**2 for j in range(4))for i in range(4)]
    return x,variance

def solve(epoch,max_iterations=12):
    present=sum(1<<i for i in epoch['observations']);ready=sum(1<<i for i,v in epoch['observations'].items()if v['ready'])
    a=present&ready&epoch['asa'];n=a&epoch['na'];hits=(n&epoch['boundary']).bit_count();active=0 if hits else n
    result={'asa':a,'na':n,'hits':hits,'active':active,'used':active.bit_count(),'state':list(epoch['seed'])}
    if hits:result['status']='MASK_ABSORBED';return result
    if active.bit_count()<4:result['status']='TOO_FEW';return result
    rows=[(i,o)for i,o in sorted(epoch['observations'].items())if active&(1<<i)]
    def build(state):
        matrix=[];rhs=[];residuals=[]
        for i,o in rows:
            delta=[state[j]-o['sat'][j]for j in range(3)];distance=math.sqrt(sum(x*x for x in delta))
            r=o['corrected']-distance-state[3];sigma=o['sigma']
            matrix.append([*(d/distance/sigma for d in delta),1/sigma]);rhs.append(r/sigma);residuals.append((i,r))
        return matrix,rhs,residuals
    state=list(epoch['seed'])
    try:
        for it in range(max_iterations):
            a,b,_=build(state);delta,_=householder(a,b);state=[x+d for x,d in zip(state,delta)]
            if math.sqrt(sum(d*d for d in delta[:3]))<=1e-4 and abs(delta[3])<=1e-4:break
        else:result.update(status='ITERATION_LIMIT',state=state);return result
        a,b,res=build(state);_,variance=householder(a,b)
    except ValueError:result['status']='RANK_DEFICIENT';return result
    maximum=max(abs(x)for x in b)
    result.update(status='CONVERGED',state=state,variance=variance,residuals=res,
                  rms_m=math.sqrt(sum(r*r for _,r in res)/len(rows)),max_normalized=maximum,
                  weighted_sse=sum(r*r for r in b),fit='NO_REDUNDANCY' if len(rows)==4 else 'WITHIN_RESIDUAL_BUDGET' if maximum<=6 else 'RESIDUAL_ALERT')
    return result
