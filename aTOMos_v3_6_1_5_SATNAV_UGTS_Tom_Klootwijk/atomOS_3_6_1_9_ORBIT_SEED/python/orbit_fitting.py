"""Training-only orbital seed estimation; never reads withheld target positions."""
from __future__ import annotations
import copy
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from numba import njit
from orbit_dynamics import frame_matrix,propagate


def read_sp3_training(path,satellite,epoch_gpst_s):
    """Read exactly the caller's declared training product; positions in metres."""
    import datetime as dt
    op=gzip.open if str(path).endswith('.gz') else open
    rows=[];gps_epoch=dt.datetime(1980,1,6)
    with op(path,'rt',encoding='ascii') as source:
        for line in source:
            if line.startswith('* '):
                v=line.split();instant=dt.datetime(*map(int,v[1:6]))+dt.timedelta(seconds=float(v[6]))
                t=(instant-gps_epoch).total_seconds()-epoch_gpst_s
            elif line.startswith('P'+satellite):
                xyz=np.array([float(line[4:18]),float(line[18:32]),float(line[32:46])])*1000
                if not np.any(np.abs(xyz)>9e8) and t<=0:rows.append((t,*xyz))
    return np.array(rows)


def horizons_training(path,epoch_jd_tt):
    import erfa
    rows=[];inside=False
    for line in Path(path).read_text().splitlines():
        if line=='$$SOE':inside=True;continue
        if line=='$$EOE':break
        if not inside:continue
        v=line.split(',');tdb=float(v[0]);tt=tdb
        for _ in range(2):tt=tdb-erfa.dtdb(2451545.,tt-2451545.,0.,0.,0.,0.)/86400.
        t=(tt-epoch_jd_tt)*86400.
        if t<=0:rows.append((t,*[float(x)*1000 for x in v[2:8]]))
    return np.array(rows)


def prepare_numba(model):
    f=model['force'];fr=model['frame']
    constants=np.array([f['mu_m3_s2'],f['radius_m'],f['j2'],f['j3'],f['j4'],f['c22'],f['s22'],f['sun_mu_m3_s2'],f['moon_mu_m3_s2'],f['au_m'],f['srp_m_s2_at_au'],float(f['shadow']),*f['empirical_rtn_m_s2'],fr['era0_rad'],fr['era_rate_rad_s'],fr['xp_rad'],fr['yp_rad']])
    groups=[fr['q_segments'],model['forcing']['sun'],model['forcing']['moon']]
    if any(len(g)!=1 for g in groups):raise ValueError('fitting optimizer accepts one segment per forcing; replay supports multiple')
    bounds=np.array([[g[0]['t0_s'],g[0]['t1_s']] for g in groups])
    arrays=[np.ascontiguousarray(g[0]['coefficients'],dtype=float) for g in groups]
    return constants,bounds,*arrays


@njit(cache=True)
def _cheb(c,t,t0,t1):
    u=(2*t-t0-t1)/(t1-t0);out=np.empty(c.shape[0])
    for row in range(c.shape[0]):
        b1=0.;b2=0.
        for j in range(c.shape[1]-1,0,-1):
            b0=2*u*b1-b2+c[row,j];b2=b1;b1=b0
        out[row]=u*b1-b2+c[row,0]
    return out


@njit(cache=True)
def _force(t,state,c,bounds,qcoef,scoef,mcoef):
    q=_cheb(qcoef,t,bounds[0,0],bounds[0,1]).reshape((3,3))
    a=c[15]+c[16]*t;ca=np.cos(a);sa=np.sin(a);cx=np.cos(c[17]);sx=np.sin(c[17]);cy=np.cos(c[18]);sy=np.sin(c[18])
    rot=np.array([[ca,sa,0.],[-sa,ca,0.],[0.,0.,1.]])
    polar=np.array([[cx,0.,sx],[sy*sx,cy,-sy*cx],[-cy*sx,sy,cy*cx]])
    m=polar@rot@q;r=state[:3];v=state[3:];p=m@r
    rad=np.sqrt(np.dot(p,p));s=p[2]/rad;mu=c[0];re=c[1]
    acc=-mu*p/rad**3
    pol=np.array([(3*s*s-1)/2,(5*s**3-3*s)/2,(35*s**4-30*s*s+3)/8])
    deriv=np.array([3*s,(15*s*s-3)/2,(140*s**3-60*s)/8])
    for n in range(2,5):
        k=mu*c[n]*re**n/rad**(n+3)
        acc+=k*((n+1)*pol[n-2]+s*deriv[n-2])*p;acc[2]-=k*rad*deriv[n-2]
    x,y,z=p;f=3*c[5]*(x*x-y*y)+6*c[6]*x*y
    grad=np.array([6*c[5]*x+6*c[6]*y,-6*c[5]*y+6*c[6]*x,0.])
    acc+=mu*re*re/rad**5*(grad-5*f/rad**2*p);acc=m.T@acc
    sun=_cheb(scoef,t,bounds[1,0],bounds[1,1]);moon=_cheb(mcoef,t,bounds[2,0],bounds[2,1])
    for j in range(2):
        if c[7+j]==0:continue
        body=sun if j==0 else moon;delta=body-r
        acc+=c[7+j]*(delta/np.sqrt(np.dot(delta,delta))**3-body/np.sqrt(np.dot(body,body))**3)
    if c[10]!=0:
        away=r-sun;dist=np.sqrt(np.dot(away,away));sunhat=sun/np.sqrt(np.dot(sun,sun));projection=np.dot(r,sunhat)
        perpendicular=r-projection*sunhat
        shadow=c[11]>0 and projection<0 and np.dot(perpendicular,perpendicular)<re*re
        if not shadow:acc+=c[10]*(c[9]/dist)**2*away/dist
    if c[12]!=0 or c[13]!=0 or c[14]!=0:
        radial=r/np.sqrt(np.dot(r,r));normal=np.cross(r,v);normal/=np.sqrt(np.dot(normal,normal));transverse=np.cross(normal,radial)
        acc+=c[12]*radial+c[13]*transverse+c[14]*normal
    out=np.empty(6);out[:3]=v;out[3:]=acc;return out


@njit(cache=True)
def _rk4(state,start,times,step,c,bounds,qcoef,scoef,mcoef):
    out=np.empty((len(times),6));y=state.copy();t=start
    for i in range(len(times)):
        target=times[i]
        sign=1. if target>=t else -1.
        while sign*(target-t)>1e-9:
            h=sign*min(step,abs(target-t))
            k1=_force(t,y,c,bounds,qcoef,scoef,mcoef)
            k2=_force(t+h/2,y+h*k1/2,c,bounds,qcoef,scoef,mcoef)
            k3=_force(t+h/2,y+h*k2/2,c,bounds,qcoef,scoef,mcoef)
            k4=_force(t+h,y+h*k3,c,bounds,qcoef,scoef,mcoef)
            y=y+h*(k1+2*k2+2*k3+k4)/6;t+=h
        out[i]=y
    return out


def fast_propagate(model,times,state=None,start=0.,step=None):
    if model['profile']=='ORBIT-DYNAMICS-R2':
        from orbit_precision import precision_fast_propagate
        return precision_fast_propagate(model,times,state,start,step)
    return _rk4(np.array(model['state_gcrs'] if state is None else state,dtype=float),float(start),np.asarray(times,dtype=float),float(step or model['integration']['step_s']),*prepare_numba(model))


def fit_model(model,times,positions,velocities=None,max_nfev=35):
    """Fixed predeclared 10-parameter fit: initial6, SRP1, constant RTN3.

    All target rows must precede or equal the seed epoch. Fitting bounds exclude
    invented large thrust. No future metrics are consulted to select parameters.
    """
    times=np.asarray(times);positions=np.asarray(positions)
    if times.max()>1e-8:raise ValueError('future target data forbidden in seed fit')
    order=np.argsort(times);times=times[order];positions=positions[order]
    if velocities is not None:velocities=np.asarray(velocities)[order]
    # Center the initial state within training to reduce position/velocity covariance.
    anchor=len(times)//2;tanchor=float(times[anchor]);r0=positions[anchor]
    if velocities is None:
        nearby=slice(max(0,anchor-5),min(len(times),anchor+6));x=(times[nearby]-tanchor)/3600
        coeff=np.polynomial.polynomial.polyfit(x,positions[nearby],7)
        v0=coeff[1]/3600
    else:v0=velocities[anchor]
    initial=np.r_[r0,v0]
    # Fit every 30 minutes, keeping all rows for the final training residual audit.
    chosen=np.unique(np.r_[np.arange(0,len(times),6),len(times)-1,anchor]).astype(int)
    fit_times=times[chosen];fit_pos=positions[chosen]
    scales=np.array([100.,100.,100.,.1,.1,.1,1e-7,1e-7,1e-7,1e-7])
    def unpack(parameters):
        m=copy.deepcopy(model);m['force']['srp_m_s2_at_au']=parameters[6]*scales[6]
        m['force']['empirical_rtn_m_s2']=(parameters[7:10]*scales[7:10]).tolist()
        state=initial+parameters[:6]*scales[:6]
        return m,state
    def at_training(m,state,requested):
        out=np.empty((len(requested),6));before=np.flatnonzero(requested<tanchor);after=np.flatnonzero(requested>=tanchor)
        if len(before):out[before]=fast_propagate(m,requested[before][::-1],state,tanchor)[::-1]
        if len(after):out[after]=fast_propagate(m,requested[after],state,tanchor)
        return out
    def residual(p):
        m,state=unpack(p);predicted=at_training(m,state,fit_times)
        # Weak physical regularization; deterministic and chosen before validation.
        return np.r_[(predicted[:,:3]-fit_pos).ravel(), p[7:]*.1]
    p0=np.zeros(10);p0[6]=model['force']['srp_m_s2_at_au']/1e-7
    lo=np.full(10,-np.inf);hi=np.full(10,np.inf);lo[6]=0.;hi[6]=50.;lo[7:]=-20.;hi[7:]=20.
    def jacobian(p):
        base=residual(p);jac=np.empty((len(base),len(p)));increment=1e-3
        for j in range(len(p)):
            pp=p.copy();pp[j]+=increment;jac[:,j]=(residual(pp)-base)/increment
        return jac
    solution=least_squares(residual,p0,jac=jacobian,method='trf',bounds=(lo,hi),
                           xtol=1e-9,ftol=1e-9,gtol=1e-7,max_nfev=max_nfev,x_scale='jac')
    fitted,anchor_state=unpack(solution.x)
    fitted['state_gcrs']=fast_propagate(fitted,[0.],anchor_state,tanchor)[0].tolist()
    residuals=at_training(fitted,anchor_state,times)[:,:3]-positions
    errors=np.linalg.norm(residuals,axis=1)
    details={'method':'bounded least_squares; fixed initial6 + SRP1 + constant RTN3',
       'training_start_s':float(times.min()),'training_end_s':float(times.max()),'training_rows':len(times),
       'fitted_rows':len(chosen),'fit_reference_anchor_s':tanchor,'solver_success':bool(solution.success),
       'solver_message':solution.message,'nfev':solution.nfev,'training_rms_3d_m':float(np.sqrt(np.mean(errors**2))),
       'training_max_3d_m':float(errors.max()),'parameter_values_scaled':solution.x.tolist(),
       'selection_policy':'fixed model and parameter bounds chosen before any future-target comparison',
       'optimizer_step_s':fitted['integration']['step_s'],'future_target_rows_used':0,
       'anchor_state_gcrs':anchor_state.tolist()}
    return fitted,details
