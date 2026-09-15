"""ORBIT-DYNAMICS-R1: explicit SI orbital forces and independent DOP853 replay.

The JSON model contains every time-varying coefficient used at replay. ERFA and
DE440 are construction dependencies only; replay uses NumPy and SciPy.
"""
from __future__ import annotations

import copy
import math
import numpy as np
from numpy.polynomial import chebyshev as cheb


def validate_model(model):
    """Reject incomplete, nonfinite, ambiguous or unbounded replay models.

    Metadata belongs beside the physical model, not among its numerical inputs.
    This checks the executable format; it does not certify a satellite forecast.
    """
    if isinstance(model,dict) and model.get('profile')=='ORBIT-DYNAMICS-R2':
        from orbit_precision import validate_precision_model
        return validate_precision_model(model)
    def fields(value,required,label):
        if not isinstance(value,dict) or set(value)!=set(required):
            raise ValueError(f'{label}: exact fields required: {sorted(required)}')
    def number(value,label):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError(f'{label}: finite number required')
        return float(value)
    def vector(value,count,label):
        if not isinstance(value,list) or len(value)!=count:raise ValueError(f'{label}: list of {count} numbers required')
        return [number(v,label) for v in value]
    fields(model,['profile','epoch_gpst_s','epoch_jd_tt','state_gcrs','domain_s','frame','force','forcing','integration'],'model')
    if model['profile']!='ORBIT-DYNAMICS-R1':raise ValueError('unsupported dynamics profile')
    epoch=number(model['epoch_gpst_s'],'epoch_gpst_s');jd=number(model['epoch_jd_tt'],'epoch_jd_tt')
    if epoch<0 or abs(jd-(2444244.5+(epoch+51.184)/86400))>1e-8:raise ValueError('epoch GPST/TT mismatch')
    state=vector(model['state_gcrs'],6,'state_gcrs');domain=vector(model['domain_s'],2,'domain_s')
    if not domain[0]<=0<=domain[1] or domain[0]>=domain[1]:raise ValueError('domain must contain epoch and have positive width')
    frame=model['frame'];fields(frame,['era0_rad','era_rate_rad_s','xp_rad','yp_rad','q_segments'],'frame')
    for key in ['era0_rad','era_rate_rad_s','xp_rad','yp_rad']:number(frame[key],'frame.'+key)
    if abs(frame['era_rate_rad_s'])>1 or abs(frame['xp_rad'])>math.pi/2 or abs(frame['yp_rad'])>math.pi/2:
        raise ValueError('frame rotation parameter outside supported range')
    force=model['force'];fields(force,['mu_m3_s2','radius_m','j2','j3','j4','c22','s22','sun_mu_m3_s2','moon_mu_m3_s2','au_m','srp_m_s2_at_au','shadow','empirical_rtn_m_s2'],'force')
    for key in ['mu_m3_s2','radius_m','au_m']:
        if number(force[key],'force.'+key)<=0:raise ValueError(f'force.{key} must be positive')
    for key in ['sun_mu_m3_s2','moon_mu_m3_s2','srp_m_s2_at_au']:
        if number(force[key],'force.'+key)<0:raise ValueError(f'force.{key} must be nonnegative')
    for key in ['j2','j3','j4','c22','s22']:number(force[key],'force.'+key)
    if type(force['shadow']) is not bool:raise ValueError('force.shadow must be Boolean')
    vector(force['empirical_rtn_m_s2'],3,'force.empirical_rtn_m_s2')
    if np.linalg.norm(state[:3])<=force['radius_m']:raise ValueError('epoch position must be outside reference Earth')
    if any(force['empirical_rtn_m_s2']) and np.linalg.norm(np.cross(state[:3],state[3:]))==0:
        raise ValueError('RTN acceleration requires nonzero angular momentum')
    fields(model['forcing'],['sun','moon'],'forcing')
    for label,segments,rows in [('frame.q_segments',frame['q_segments'],9),('forcing.sun',model['forcing']['sun'],3),('forcing.moon',model['forcing']['moon'],3)]:
        if not isinstance(segments,list) or not 1<=len(segments)<=4096:raise ValueError(f'{label}: one to4096 segments required')
        previous=None
        for segment in segments:
            fields(segment,['t0_s','t1_s','coefficients'],label)
            start=number(segment['t0_s'],label);end=number(segment['t1_s'],label)
            if start>=end:raise ValueError(f'{label}: positive segment width required')
            if previous is not None and start!=previous:raise ValueError(f'{label}: segments must be ordered and exactly contiguous')
            previous=end;coeff=segment['coefficients']
            if not isinstance(coeff,list) or len(coeff)!=rows or not isinstance(coeff[0],list) or not 1<=len(coeff[0])<=33:
                raise ValueError(f'{label}: {rows} coefficient rows of degree0..32 required')
            for row in coeff:vector(row,len(coeff[0]),label+'.coefficients')
        if segments[0]['t0_s']>domain[0] or segments[-1]['t1_s']<domain[1]:raise ValueError(f'{label}: coefficients do not cover query domain')
    integration=model['integration'];fields(integration,['step_s','checkpoint_stride_steps','max_checkpoints','max_steps_per_query'],'integration')
    step=number(integration['step_s'],'integration.step_s')
    if step<=0:raise ValueError('integration.step_s must be positive')
    for key,maximum in [('checkpoint_stride_steps',10000000),('max_checkpoints',1000000),('max_steps_per_query',10000000)]:
        value=integration[key]
        if type(value) is not int or not 1<=value<=maximum:raise ValueError(f'integration.{key}: integer in1..{maximum} required')
    if math.ceil(max(abs(domain[0]),abs(domain[1]))/step)>integration['max_steps_per_query']:
        raise ValueError('declared timestamp domain exceeds cold-query step budget')
    return model


def segment_value(segments, t, derivative=False):
    for i in range(len(segments)-1,-1,-1):
        s=segments[i]
        if s['t0_s'] <= t <= s['t1_s']:
            c = np.asarray(s['coefficients'], dtype=float)
            u = (2*t-s['t0_s']-s['t1_s'])/(s['t1_s']-s['t0_s'])
            if derivative:
                c = cheb.chebder(c, axis=1)*2/(s['t1_s']-s['t0_s'])
            return np.array([cheb.chebval(u, row) for row in c])
    raise ValueError(f'timestamp {t} outside embedded coefficient domain')


def _polar(xp, yp):
    # SOFA/ERFA pom00(xp, yp, s_prime=0): Rx(-yp) Ry(-xp).
    cx,sx,cy,sy=math.cos(xp),math.sin(xp),math.cos(yp),math.sin(yp)
    return np.array([[cx,0,sx],[sy*sx,cy,-sy*cx],[-cy*sx,sy,cy*cx]])


def frame_matrix(model, t, derivative=False):
    if model['profile']=='ORBIT-DYNAMICS-R2':
        from orbit_precision import precision_frame
        return precision_frame(model,t,derivative)
    f=model['frame']; a=f['era0_rad']+f['era_rate_rad_s']*t
    c,s=math.cos(a),math.sin(a)
    r=np.array([[c,s,0],[-s,c,0],[0,0,1]])
    q=segment_value(f['q_segments'],t).reshape(3,3)
    p=_polar(f['xp_rad'], f['yp_rad'])
    if not derivative:
        return p@r@q
    dr=f['era_rate_rad_s']*np.array([[-s,c,0],[-c,-s,0],[0,0,0]])
    dq=segment_value(f['q_segments'],t,True).reshape(3,3)
    return p@(dr@q+r@dq)


def state_to_ecef(model, t, y):
    y=np.asarray(y,dtype=float); m=frame_matrix(model,t)
    return np.concatenate((m@y[:3],m@y[3:]+frame_matrix(model,t,True)@y[:3]))


def acceleration(model, t, state):
    """Independent vector implementation; native uses scalar device arithmetic."""
    if model['profile']=='ORBIT-DYNAMICS-R2':
        from orbit_precision import precision_acceleration
        return precision_acceleration(model,t,state)
    f=model['force']; r=np.asarray(state[:3]); v=np.asarray(state[3:])
    m=frame_matrix(model,t); p=m@r; radius=np.linalg.norm(p)
    if radius < f['radius_m']:
        raise ValueError('orbit penetrates reference Earth')
    s=p[2]/radius; mu=f['mu_m3_s2']; re=f['radius_m']
    a=-mu*p/radius**3
    polynomials=[((3*s*s-1)/2,3*s),((5*s**3-3*s)/2,(15*s*s-3)/2),((35*s**4-30*s*s+3)/8,(140*s**3-60*s)/8)]
    for n,(pn,dp) in enumerate(polynomials,2):
        k=mu*f[f'j{n}']*re**n/radius**(n+3)
        a+=k*((n+1)*pn+s*dp)*p
        a[2]-=k*radius*dp
    x,y,z=p; c22,s22=f['c22'],f['s22']
    tess=3*c22*(x*x-y*y)+6*s22*x*y
    gradient=np.array([6*c22*x+6*s22*y,-6*c22*y+6*s22*x,0.])
    a+=mu*re*re/radius**5*(gradient-5*tess/radius**2*p)
    a=m.T@a
    sun=None
    for name in ('sun','moon'):
        if f[f'{name}_mu_m3_s2']==0 and not(name=='sun' and f['srp_m_s2_at_au']!=0):continue
        body=segment_value(model['forcing'][name],t); d=body-r
        a+=f[f'{name}_mu_m3_s2']*(d/np.linalg.norm(d)**3-body/np.linalg.norm(body)**3)
        if name=='sun': sun=body
    # The cylindrical Earth umbra is deliberately explicit; no hidden penumbra.
    if f['srp_m_s2_at_au']!=0:
        away=r-sun; distance=np.linalg.norm(away); sunhat=sun/np.linalg.norm(sun)
        projection=np.dot(r,sunhat)
        eclipsed=f.get('shadow',True) and projection<0 and np.linalg.norm(r-projection*sunhat)<re
        if not eclipsed:
            a+=f['srp_m_s2_at_au']*(f['au_m']/distance)**2*away/distance
    empirical=np.asarray(f.get('empirical_rtn_m_s2',[0,0,0]))
    if np.any(empirical):
        radial=r/np.linalg.norm(r); normal=np.cross(r,v); normal/=np.linalg.norm(normal)
        transverse=np.cross(normal,radial)
        a+=empirical[0]*radial+empirical[1]*transverse+empirical[2]*normal
    return a


def derivative(model, t, state):
    return np.concatenate((state[3:],acceleration(model,t,state)))


def propagate(model, times, method='DOP853', rtol=2e-12, atol=1e-6, max_step=300.):
    """Query arbitrary ordered/repeated timestamps from the explicit epoch state.

    DOP853 is an independently adaptive numerical reference. RK4 is a debugging
    counterpart, not used as the independent numerical accuracy oracle.
    """
    from scipy.integrate import solve_ivp
    times=np.asarray(times,dtype=float)
    if times.ndim!=1 or not np.all(np.isfinite(times)): raise ValueError('finite one-dimensional timestamps required')
    if len(times)==0:return np.empty((0,6))
    if times.min()<model['domain_s'][0] or times.max()>model['domain_s'][1]:raise ValueError('query outside model domain')
    state=np.asarray(model['state_gcrs'],dtype=float); result=np.empty((len(times),6))
    result[times==0]=state
    for sign in (1,-1):
        indices=np.flatnonzero(times*sign>0)
        if len(indices)==0:continue
        values=np.unique(times[indices]); values=np.sort(values)[::sign]
        if method=='RK4':
            t=0.;y=state.copy(); lookup={}
            for target in values:
                while sign*(target-t)>1e-9:
                    h=sign*min(model['integration']['step_s'],abs(target-t))
                    k1=derivative(model,t,y);k2=derivative(model,t+h/2,y+h*k1/2)
                    k3=derivative(model,t+h/2,y+h*k2/2);k4=derivative(model,t+h,y+h*k3)
                    y=y+h*(k1+2*k2+2*k3+k4)/6;t+=h
                lookup[float(target)]=y.copy()
            result[indices]=[lookup[float(t)] for t in times[indices]]
        else:
            sol=solve_ivp(lambda t,y:derivative(model,t,y),(0.,float(values[-1])),state,
                          method=method,t_eval=values,rtol=rtol,atol=atol,max_step=max_step)
            if not sol.success:raise RuntimeError(sol.message)
            lookup={float(t):y for t,y in zip(sol.t,sol.y.T)}
            result[indices]=[lookup[float(t)] for t in times[indices]]
    return result


def model_with_state(model,state):
    result=copy.deepcopy(model);result['state_gcrs']=np.asarray(state).tolist();return result


def fit_chebyshev(function, t0, t1, degree, rows):
    """Fit at Chebyshev nodes; caller validates at independent off-node times."""
    nodes=np.cos(np.pi*(np.arange(degree+1)+.5)/(degree+1))
    times=(t0+t1)/2+(t1-t0)*nodes/2
    values=np.array([function(float(t)) for t in times]).reshape(len(times),rows)
    coefficients=cheb.chebfit(nodes,values,degree).T
    return {'t0_s':float(t0),'t1_s':float(t1),'coefficients':coefficients.tolist()}


def build_compact_environment(epoch_gpst_s, de440_path, eop, domain_s=(-86400.,604800.)):
    """Construction only. Requires pyerfa and jplephem, not needed by a seed."""
    import erfa
    from jplephem.spk import SPK
    gps_jd=2444244.5+epoch_gpst_s/86400.;tt_jd=gps_jd+51.184/86400.
    utc_jd=gps_jd-18./86400.;ut1_jd=utc_jd+eop['dut1_s']/86400.
    kernel=SPK.open(str(de440_path))
    def tdb_jd(t):
        tt=tt_jd+t/86400.
        # Geocentric TT->TDB periodic correction (SOFA Fairhead-Bretagnon).
        return tt+erfa.dtdb(2451545.,tt-2451545.,0.,0.,0.,0.)/86400.
    def body(name,t):
        jd=tdb_jd(t);emb=kernel[0,3].compute(jd);earth=emb+kernel[3,399].compute(jd)
        pos=kernel[0,10].compute(jd) if name=='sun' else emb+kernel[3,301].compute(jd)
        return (pos-earth)*1000.
    def q(t):return erfa.c2i06a(2451545.,tt_jd-2451545.+t/86400.).reshape(9)
    t0,t1=domain_s
    q_segments=[fit_chebyshev(q,t0,t1,8,9)]
    forcing={name:[fit_chebyshev(lambda t,n=name:body(n,t),t0,t1,16 if name=='moon' else 10,3)] for name in ('sun','moon')}
    checks=np.linspace(t0,t1,129)+.137
    checks=checks[(checks>=t0)&(checks<=t1)]
    audit={'q_matrix_max_abs':max(float(np.max(np.abs(segment_value(q_segments,t)-q(t)))) for t in checks)}
    for name in ('sun','moon'):
        audit[name+'_forcing_max_m']=max(float(np.linalg.norm(segment_value(forcing[name],t)-body(name,t))) for t in checks)
    kernel.close()
    model={'profile':'ORBIT-DYNAMICS-R1','epoch_gpst_s':float(epoch_gpst_s),'epoch_jd_tt':tt_jd,
       'state_gcrs':[0.]*6,'domain_s':list(domain_s),'frame':{
        'era0_rad':float(erfa.era00(2451545.,ut1_jd-2451545.)),
        'era_rate_rad_s':2*np.pi*1.00273781191135448/86400.*(1-eop.get('lod_s',0)/86400.),
        'xp_rad':float(eop['xp_arcsec']*np.pi/(180*3600)),
        'yp_rad':float(eop['yp_arcsec']*np.pi/(180*3600)), 'q_segments':q_segments},
       'force':{'mu_m3_s2':3.986004418e14,'radius_m':6378136.3,
        'j2':1.0826266835531513e-3,'j3':-2.5326564853322355e-6,'j4':-1.619621591367e-6,
        'c22':2.43938357328313e-6*math.sqrt(5/12),'s22':-1.40027370385934e-6*math.sqrt(5/12),
        'sun_mu_m3_s2':1.3271244004193938e20,'moon_mu_m3_s2':4.90280011845755e12,
        'au_m':149597870700.,'srp_m_s2_at_au':1e-7,'shadow':True,'empirical_rtn_m_s2':[0.,0.,0.]},
       'forcing':forcing,'integration':{'step_s':30.,'checkpoint_stride_steps':120,'max_checkpoints':256,'max_steps_per_query':25000}}
    # Verify our explicitly implemented polar convention against SOFA.
    if np.max(np.abs(_polar(model['frame']['xp_rad'],model['frame']['yp_rad'])-erfa.pom00(model['frame']['xp_rad'],model['frame']['yp_rad'],0.)))>1e-15:
        raise AssertionError('polar rotation convention mismatch')
    return model,audit
