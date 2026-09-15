"""ORBIT-DYNAMICS-R2: full degree-12 gravity and published varying EOP.

Independent Python gravity uses complex-step differentiation of the scalar
Cunningham potential. The fitting accelerator uses explicit Cartesian dual
gradients. The native backend implements its own scalar recurrence.
"""
from __future__ import annotations
import copy,math
from pathlib import Path
import numpy as np
try:
    from numba import njit
    HAVE_NUMBA=True
except ImportError:
    HAVE_NUMBA=False
    def njit(*args,**kwargs):
        """Replay requires no JIT; construction may use the slow Python path."""
        return lambda function:function
from orbit_dynamics import segment_value,fit_chebyshev,_polar


def validate_precision_model(model):
    from orbit_dynamics import validate_model
    force_fields={'mu_m3_s2','radius_m','gravity_degree','gravity_c','gravity_s',
        'sun_mu_m3_s2','moon_mu_m3_s2','au_m','srp_m_s2_at_au','shadow',
        'empirical_rtn_m_s2','relativity','c_m_s'}
    frame_fields={'era0_rad','era_rate_rad_s','q_segments','eop_segments'}
    for label,required in [('force',force_fields),('frame',frame_fields)]:
        value=model.get(label)
        if not isinstance(value,dict) or set(value)!=required:
            raise ValueError(f'R2 {label}: exact fields required: {sorted(required)}')
    proxy=copy.deepcopy(model);proxy['profile']='ORBIT-DYNAMICS-R1'
    f=proxy['force'];degree=f.pop('gravity_degree');c=f.pop('gravity_c');s=f.pop('gravity_s')
    relativity=f.pop('relativity');light=f.pop('c_m_s')
    if type(degree) is not int or not 0<=degree<=12:raise ValueError('gravity degree0..12 required')
    for table in (c,s):
        if not isinstance(table,list) or len(table)!=degree+1:raise ValueError('gravity coefficient rows required')
        for n,row in enumerate(table):
            if not isinstance(row,list) or len(row)!=degree+1 or any(type(x) not in (int,float) or not math.isfinite(x) for x in row):raise ValueError('finite square gravity array required')
            if any(row[m]!=0 for m in range(n+1,degree+1)):raise ValueError('upper gravity triangle must be zero')
    if c[0][0]!=1 or s[0][0]!=0:raise ValueError('gravity C00=1 S00=0 required')
    if any(row[0]!=0 for row in s):raise ValueError('all unused Sn0 coefficients must be zero')
    if type(relativity) is not bool or type(light) not in (int,float) or not math.isfinite(light) or light<=0:raise ValueError('explicit relativity flag and positive speed of light required')
    f.update(j2=0.,j3=0.,j4=0.,c22=0.,s22=0.)
    eop=proxy['frame'].pop('eop_segments');proxy['frame'].update(xp_rad=0.,yp_rad=0.)
    validate_model(proxy)
    proxy['forcing']['sun']=eop;validate_model(proxy)
    return model


def precision_frame(model,t,derivative=False):
    f=model['frame'];eop=segment_value(f['eop_segments'],t)
    a=f['era0_rad']+f['era_rate_rad_s']*t+eop[0];xp,yp=eop[1:]
    c,s=np.cos(a),np.sin(a);r=np.array([[c,s,0],[-s,c,0],[0,0,1.]])
    p=_polar(xp,yp);q=segment_value(f['q_segments'],t).reshape(3,3)
    if not derivative:return p@r@q
    rates=segment_value(f['eop_segments'],t,True);da=f['era_rate_rad_s']+rates[0]
    cx,sx,cy,sy=np.cos(xp),np.sin(xp),np.cos(yp),np.sin(yp)
    px=np.array([[-sx,0,cx],[sy*cx,0,sy*sx],[-cy*cx,0,-cy*sx]])
    py=np.array([[0,0,0],[cy*sx,-sy,-cy*cx],[sy*sx,cy,-sy*cx]])
    dp=px*rates[1]+py*rates[2]
    dr=da*np.array([[-s,c,0],[-c,-s,0],[0,0,0.]])
    dq=segment_value(f['q_segments'],t,True).reshape(3,3)
    return dp@r@q+p@dr@q+p@r@dq


def harmonic_potential(position,force):
    p=np.asarray(position);r2=np.sum(p*p);re=force['radius_m'];nmax=force['gravity_degree']
    c=np.asarray(force['gravity_c']);s=np.asarray(force['gravity_s'])
    v=np.zeros((nmax+1,nmax+1),dtype=p.dtype);w=v.copy();v[0,0]=re/np.sqrt(r2)
    xx,yy,zz=re*p/r2;rr=re*re/r2
    for m in range(nmax+1):
        if m:
            v[m,m]=(2*m-1)*(xx*v[m-1,m-1]-yy*w[m-1,m-1])
            w[m,m]=(2*m-1)*(xx*w[m-1,m-1]+yy*v[m-1,m-1])
        for n in range(m+1,nmax+1):
            factor=(2*n-1)/(n-m)
            v[n,m]=factor*zz*v[n-1,m];w[n,m]=factor*zz*w[n-1,m]
            if n>m+1:
                factor=(n+m-1)/(n-m);v[n,m]-=factor*rr*v[n-2,m];w[n,m]-=factor*rr*w[n-2,m]
    return force['mu_m3_s2']/re*np.sum(c*v+s*w)


def precision_acceleration(model,t,state):
    f=model['force'];r=np.asarray(state[:3]);v=np.asarray(state[3:]);mat=precision_frame(model,t);p=mat@r
    if np.linalg.norm(p)<f['radius_m']:raise ValueError('orbit penetrates reference Earth')
    gradient=np.empty(3)
    for j in range(3):
        trial=p.astype(complex);trial[j]+=1e-6j;gradient[j]=harmonic_potential(trial,f).imag/1e-6
    acc=mat.T@gradient;sun=segment_value(model['forcing']['sun'],t)
    for name in ['sun','moon']:
        if f[name+'_mu_m3_s2']==0:continue
        body=sun if name=='sun' else segment_value(model['forcing'][name],t);delta=body-r
        acc+=f[name+'_mu_m3_s2']*(delta/np.linalg.norm(delta)**3-body/np.linalg.norm(body)**3)
    if f['srp_m_s2_at_au']!=0:
        unit=sun/np.linalg.norm(sun);projection=r@unit
        shadow=f['shadow'] and projection<0 and np.linalg.norm(r-projection*unit)<f['radius_m']
        if not shadow:
            d=r-sun;distance=np.linalg.norm(d);acc+=f['srp_m_s2_at_au']*(f['au_m']/distance)**2*d/distance
    if any(f['empirical_rtn_m_s2']):
        radial=r/np.linalg.norm(r);normal=np.cross(r,v);normal/=np.linalg.norm(normal);transverse=np.cross(normal,radial)
        empirical=f['empirical_rtn_m_s2'];acc+=empirical[0]*radial+empirical[1]*transverse+empirical[2]*normal
    if f['relativity']:
        radius=np.linalg.norm(r);acc+=f['mu_m3_s2']/(f['c_m_s']**2*radius**3)*((4*f['mu_m3_s2']/radius-v@v)*r+4*(r@v)*v)
    return acc


def build_precision_environment(epoch_gpst_s,de440_path,bulletin_path,gravity_path,domain_s=(-691200.,604800.)):
    import erfa
    from jplephem.spk import SPK
    rows={}
    for line in Path(bulletin_path).read_text().splitlines():
        parts=line.split()
        try:
            if len(parts)==10 and len(parts[0])==2:
                mjd=int(parts[3]);rows[mjd]=(float(parts[4]),float(parts[6]),float(parts[8]))
            elif len(parts)==7 and len(parts[0])==4:
                mjd=int(parts[3]);rows[mjd]=(float(parts[4]),float(parts[5]),float(parts[6]))
        except ValueError:continue
    epoch_utc_mjd=44244.+(epoch_gpst_s-18)/86400.;tt_jd=2444244.5+(epoch_gpst_s+51.184)/86400.
    lo=math.floor(epoch_utc_mjd);weight=epoch_utc_mjd-lo;dut0=(1-weight)*rows[lo][2]+weight*rows[lo+1][2]
    rate=2*math.pi*1.00273781191135448/86400.;era0=float(erfa.era00(2400000.5,epoch_utc_mjd+dut0/86400.))
    eop=[];rad=math.pi/(180*3600)
    for day in range(math.floor(epoch_utc_mjd+domain_s[0]/86400),math.ceil(epoch_utc_mjd+domain_s[1]/86400)):
        begin=(day-epoch_utc_mjd)*86400.;end=begin+86400.
        left=np.array([rate*(rows[day][2]-dut0),rows[day][0]*rad,rows[day][1]*rad])
        right=np.array([rate*(rows[day+1][2]-dut0),rows[day+1][0]*rad,rows[day+1][1]*rad])
        eop.append({'t0_s':begin,'t1_s':end,'coefficients':np.array([(left+right)/2,(right-left)/2]).T.tolist()})
    # Construct shared endpoints once to avoid tiny noncontiguity from JD subtraction.
    for i in range(1,len(eop)):eop[i]['t0_s']=eop[i-1]['t1_s']
    degree=12;c=np.zeros((degree+1,degree+1));s=c.copy();mu=re=None
    for line in Path(gravity_path).read_text().splitlines():
        p=line.split()
        if not p:continue
        if p[0]=='earth_gravity_constant':mu=float(p[1])
        elif p[0]=='radius':re=float(p[1])
        elif p[0]=='gfc':
            n,m=int(p[1]),int(p[2])
            if n>degree:continue
            norm=math.sqrt((1 if m==0 else 2)*(2*n+1)*math.factorial(n-m)/math.factorial(n+m))
            c[n,m]=float(p[3])*norm;s[n,m]=float(p[4])*norm
    kernel=SPK.open(str(de440_path))
    def body(name,t):
        tt=tt_jd+t/86400.;jd=tt+erfa.dtdb(2451545.,tt-2451545.,0.,0.,0.,0.)/86400.
        emb=kernel[0,3].compute(jd);earth=emb+kernel[3,399].compute(jd)
        value=kernel[0,10].compute(jd) if name=='sun' else emb+kernel[3,301].compute(jd)
        return (value-earth)*1000.
    a,b=domain_s
    q=[fit_chebyshev(lambda t:erfa.c2i06a(2451545.,tt_jd-2451545.+t/86400.).reshape(9),a,b,18,9)]
    forcing={name:[fit_chebyshev(lambda t,name=name:body(name,t),a,b,30 if name=='moon' else 16,3)] for name in ['sun','moon']}
    points=np.linspace(a,b,257)[1:-1]+.03125
    audit={name+'_forcing_max_m':max(float(np.linalg.norm(segment_value(forcing[name],t)-body(name,t))) for t in points) for name in ['sun','moon']}
    audit['q_max_entry']=max(float(np.max(np.abs(segment_value(q,t).reshape(3,3)-erfa.c2i06a(2451545.,tt_jd-2451545.+t/86400.)))) for t in points)
    kernel.close()
    model={'profile':'ORBIT-DYNAMICS-R2','epoch_gpst_s':float(epoch_gpst_s),'epoch_jd_tt':tt_jd,'domain_s':list(domain_s),'state_gcrs':[0.]*6,
      'frame':{'era0_rad':era0,'era_rate_rad_s':rate,'q_segments':q,'eop_segments':eop},
      'force':{'mu_m3_s2':mu,'radius_m':re,'gravity_degree':degree,'gravity_c':c.tolist(),'gravity_s':s.tolist(),
       'sun_mu_m3_s2':1.3271244004193938e20,'moon_mu_m3_s2':4.90280011845755e12,'au_m':149597870700.,
       'srp_m_s2_at_au':1e-7,'shadow':True,'empirical_rtn_m_s2':[0.,0.,0.],'relativity':True,'c_m_s':299792458.},
      'forcing':forcing,'integration':{'step_s':30.,'checkpoint_stride_steps':120,'max_checkpoints':256,'max_steps_per_query':100000}}
    return model,audit


@njit(cache=True)
def _cmul(a,b):
    out=np.empty(4);out[0]=a[0]*b[0]
    for j in range(3):out[j+1]=a[j+1]*b[0]+a[0]*b[j+1]
    return out


@njit(cache=True)
def _gravity(p,mu,re,c,s):
    nmax=c.shape[0]-1;r2=np.dot(p,p);radius=np.sqrt(r2)
    factors=np.empty((4,4))
    for j in range(3):
        factors[j,0]=re*p[j]/r2
        for k in range(3):factors[j,k+1]=re*((1. if j==k else 0.)/r2-2*p[j]*p[k]/r2**2)
    factors[3,0]=re*re/r2
    for k in range(3):factors[3,k+1]=-2*re*re*p[k]/r2**2
    v=np.zeros((nmax+1,nmax+1,4));w=np.zeros_like(v);v[0,0,0]=re/radius
    for k in range(3):v[0,0,k+1]=-re*p[k]/radius**3
    for m in range(nmax+1):
        if m:
            v[m,m,0]=(2*m-1)*(factors[0,0]*v[m-1,m-1,0]-factors[1,0]*w[m-1,m-1,0])
            w[m,m,0]=(2*m-1)*(factors[0,0]*w[m-1,m-1,0]+factors[1,0]*v[m-1,m-1,0])
            for k in range(1,4):
                v[m,m,k]=(2*m-1)*(factors[0,k]*v[m-1,m-1,0]+factors[0,0]*v[m-1,m-1,k]-factors[1,k]*w[m-1,m-1,0]-factors[1,0]*w[m-1,m-1,k])
                w[m,m,k]=(2*m-1)*(factors[0,k]*w[m-1,m-1,0]+factors[0,0]*w[m-1,m-1,k]+factors[1,k]*v[m-1,m-1,0]+factors[1,0]*v[m-1,m-1,k])
        for n in range(m+1,nmax+1):
            fac=(2*n-1)/(n-m);v[n,m,0]=fac*factors[2,0]*v[n-1,m,0];w[n,m,0]=fac*factors[2,0]*w[n-1,m,0]
            for k in range(1,4):
                v[n,m,k]=fac*(factors[2,k]*v[n-1,m,0]+factors[2,0]*v[n-1,m,k])
                w[n,m,k]=fac*(factors[2,k]*w[n-1,m,0]+factors[2,0]*w[n-1,m,k])
            if n>m+1:
                fac=(n+m-1)/(n-m);v[n,m,0]-=fac*factors[3,0]*v[n-2,m,0];w[n,m,0]-=fac*factors[3,0]*w[n-2,m,0]
                for k in range(1,4):
                    v[n,m,k]-=fac*(factors[3,k]*v[n-2,m,0]+factors[3,0]*v[n-2,m,k])
                    w[n,m,k]-=fac*(factors[3,k]*w[n-2,m,0]+factors[3,0]*w[n-2,m,k])
    acc=np.zeros(3)
    for n in range(nmax+1):
        for m in range(n+1):
            for k in range(3):acc[k]+=c[n,m]*v[n,m,k+1]+s[n,m]*w[n,m,k+1]
    return mu/re*acc


@njit(cache=True)
def _chebrows(c,t,t0,t1):
    u=2*(t-t0)/(t1-t0)-1;out=np.empty(c.shape[0])
    for row in range(c.shape[0]):
        b1=0.;b2=0.
        for j in range(c.shape[1]-1,0,-1):b0=2*u*b1-b2+c[row,j];b2=b1;b1=b0
        out[row]=u*b1-b2+c[row,0]
    return out


@njit(cache=True)
def _precision_force(t,state,k,bounds,qc,sc,mc,eopbounds,eopc,gc,gs):
    q=_chebrows(qc,t,bounds[0],bounds[1]).reshape((3,3));idx=0
    for i in range(len(eopbounds)):
        if t>=eopbounds[i,0]:idx=i
    eop=_chebrows(eopc[idx],t,eopbounds[idx,0],eopbounds[idx,1]);a=k[10]+k[11]*t+eop[0]
    ca=np.cos(a);sa=np.sin(a);cx=np.cos(eop[1]);sx=np.sin(eop[1]);cy=np.cos(eop[2]);sy=np.sin(eop[2])
    rot=np.array([[ca,sa,0.],[-sa,ca,0.],[0.,0.,1.]])
    polar=np.array([[cx,0.,sx],[sy*sx,cy,-sy*cx],[-cy*sx,sy,cy*cx]])
    mat=polar@rot@q;r=state[:3];v=state[3:];acc=mat.T@_gravity(mat@r,k[0],k[1],gc,gs)
    sun=_chebrows(sc,t,bounds[0],bounds[1]);moon=_chebrows(mc,t,bounds[0],bounds[1])
    for j in range(2):
        if k[2+j]==0:continue
        body=sun if j==0 else moon;d=body-r;acc+=k[2+j]*(d/np.sqrt(np.dot(d,d))**3-body/np.sqrt(np.dot(body,body))**3)
    if k[5]!=0:
        unit=sun/np.sqrt(np.dot(sun,sun));proj=np.dot(r,unit);perp=r-proj*unit
        shadow=k[6]!=0 and proj<0 and np.dot(perp,perp)<k[1]**2
        if not shadow:
            d=r-sun;dist=np.sqrt(np.dot(d,d));acc+=k[5]*(k[4]/dist)**2*d/dist
    if k[7]!=0 or k[8]!=0 or k[9]!=0:
        radial=r/np.sqrt(np.dot(r,r));normal=np.cross(r,v);normal/=np.sqrt(np.dot(normal,normal));trans=np.cross(normal,radial)
        acc+=k[7]*radial+k[8]*trans+k[9]*normal
    if k[12]!=0:
        radius=np.sqrt(np.dot(r,r));acc+=k[0]/(k[13]**2*radius**3)*((4*k[0]/radius-np.dot(v,v))*r+4*np.dot(r,v)*v)
    out=np.empty(6);out[:3]=v;out[3:]=acc;return out


@njit(cache=True)
def _precision_rk4(state,start,times,step,k,bounds,qc,sc,mc,eb,ec,gc,gs):
    y=state.copy();t=start;out=np.empty((len(times),6))
    for i in range(len(times)):
        target=times[i];direction=1. if target>=t else -1.
        while direction*(target-t)>1e-9:
            h=direction*min(step,abs(target-t))
            a=_precision_force(t,y,k,bounds,qc,sc,mc,eb,ec,gc,gs)
            b=_precision_force(t+h/2,y+h*a/2,k,bounds,qc,sc,mc,eb,ec,gc,gs)
            c=_precision_force(t+h/2,y+h*b/2,k,bounds,qc,sc,mc,eb,ec,gc,gs)
            d=_precision_force(t+h,y+h*c,k,bounds,qc,sc,mc,eb,ec,gc,gs)
            y=y+h*(a+2*b+2*c+d)/6;t+=h
        out[i]=y
    return out


def precision_packet(model):
    f=model['force'];fr=model['frame'];q=fr['q_segments'][0];sun=model['forcing']['sun'][0];moon=model['forcing']['moon'][0]
    if len(fr['q_segments'])!=1 or len(model['forcing']['sun'])!=1 or len(model['forcing']['moon'])!=1:raise ValueError('optimizer requires single Q/Sun/Moon segment')
    k=np.array([f['mu_m3_s2'],f['radius_m'],f['sun_mu_m3_s2'],f['moon_mu_m3_s2'],f['au_m'],f['srp_m_s2_at_au'],float(f['shadow']),*f['empirical_rtn_m_s2'],fr['era0_rad'],fr['era_rate_rad_s'],float(f['relativity']),f['c_m_s']])
    return (k,np.array([q['t0_s'],q['t1_s']]),np.array(q['coefficients']),np.array(sun['coefficients']),np.array(moon['coefficients']),
       np.array([[e['t0_s'],e['t1_s']] for e in fr['eop_segments']]),np.array([e['coefficients'] for e in fr['eop_segments']]),np.array(f['gravity_c']),np.array(f['gravity_s']))


def precision_fast_propagate(model,times,state=None,start=0.,step=None):
    if not HAVE_NUMBA:
        import warnings
        warnings.warn('Numba unavailable: using slow Python construction propagation; native packed replay is unaffected',RuntimeWarning,stacklevel=2)
    return _precision_rk4(np.array(model['state_gcrs'] if state is None else state,dtype=float),float(start),np.asarray(times,dtype=float),float(step or model['integration']['step_s']),*precision_packet(model))
