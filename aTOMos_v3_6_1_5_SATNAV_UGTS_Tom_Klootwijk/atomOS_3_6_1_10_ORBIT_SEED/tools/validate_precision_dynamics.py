"""Independent R2 coefficient, force, frame and integration audit; no target labels."""
from __future__ import annotations
import argparse,copy,hashlib,json,math,sys,time
from pathlib import Path
import numpy as np
import erfa
from scipy.special import lpmv
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
from orbit_dynamics import acceleration,frame_matrix,propagate,segment_value
from orbit_precision import _gravity,_precision_force,precision_packet,precision_fast_propagate
from orbit_native import NativeOrbit

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def spherical_gravity(position,force):
    """Independent SciPy associated Legendre basis and spherical derivatives."""
    r=np.asarray(position);d=np.linalg.norm(r);s=r[2]/d;c=np.sqrt(1-s*s);lon=np.arctan2(r[1],r[0])
    ar=alat=alon=0.
    for n in range(force['gravity_degree']+1):
        for m in range(n+1):
            # scipy includes the Condon--Shortley phase; geodesy excludes it.
            p=(-1.)**m*lpmv(m,n,s)
            previous=(-1.)**m*lpmv(m,n-1,s) if n>m else 0.
            dp=(n*s*p-(n+m)*previous)/(s*s-1)
            cs,sn=np.cos(m*lon),np.sin(m*lon)
            cn,sncoef=force['gravity_c'][n][m],force['gravity_s'][n][m]
            amplitude=cn*cs+sncoef*sn;scale=force['mu_m3_s2']/d**2*(force['radius_m']/d)**n
            ar-=(n+1)*scale*p*amplitude;alat+=scale*dp*c*amplitude
            alon+=scale*p*m*(-cn*sn+sncoef*cs)/c
    cl,sl=np.cos(lon),np.sin(lon)
    return np.array([ar*c*cl-alat*s*cl-alon*sl,ar*c*sl-alat*s*sl+alon*cl,ar*s+alat*c])

def read_bulletin(path):
    rows={}
    for line in path.read_text().splitlines():
        p=line.split()
        try:
            if len(p)==10 and len(p[0])==2:rows[int(p[3])]=[float(p[4]),float(p[6]),float(p[8])]
            elif len(p)==7 and len(p[0])==4:rows[int(p[3])]=list(map(float,p[4:7]))
        except ValueError:pass
    return rows

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-binary',type=Path,required=True)
    parser.add_argument('--models-dir',type=Path,default=ROOT/'examples/orbit/models')
    parser.add_argument('--objects',nargs='+',default=['G05','C03','C06','CHANDRA'])
    parser.add_argument('--times',nargs='+',type=float,help='Explicit numerical query times; no target observations are loaded')
    parser.add_argument('--bulletin',type=Path,default=ROOT/'source/orbit_data/bulletina-xxxvii-052.txt')
    parser.add_argument('--gravity',type=Path,default=ROOT/'source/orbit_data/gravity_reference/EGM96_degree12.json')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    authority=json.loads(args.gravity.read_text());eop_table=read_bulletin(args.bulletin)
    report={'status':'running','scope':'Known gravity coefficients, independent spherical force, ERFA frame, derivatives and domain-wide numerical integration without target labels. No held-out target positions read.',
      'numeric_claim':'Measured sampled integration/reference differences; not a mathematical roundoff or global trajectory bound.',
      'pass_thresholds':{'coefficient_max_abs':1e-20,'force_max_m_s2':2e-12,'frame_max_abs':1e-10,'frame_derivative_max_abs_s_inv':2e-12,'sampled_native_vs_dop853_position_max_m':1.},
      'cpu_binary_sha256':digest(args.cpu_binary),'gravity_source_sha256':digest(args.gravity),
      'published_eop_bulletin_sha256':digest(args.bulletin),'models':{}}
    for name in args.objects:
        started=time.perf_counter();path=args.models_dir/f'{name}.json';envelope=json.loads(path.read_text());m=envelope.get('model',envelope)
        assert m['profile']=='ORBIT-DYNAMICS-R2';f=m['force'];degree=f['gravity_degree']
        expected_c=np.zeros((degree+1,degree+1));expected_s=expected_c.copy()
        for row in authority['rows']:
            n,k=row['n'],row['m']
            if n<=degree:
                normalization=math.sqrt((2 if k else 1)*(2*n+1)*math.factorial(n-k)/math.factorial(n+k))
                expected_c[n,k]=normalization*row['C_fully_normalized'];expected_s[n,k]=normalization*row['S_fully_normalized']
        coefficient_error=max(np.max(np.abs(expected_c-np.array(f['gravity_c']))),np.max(np.abs(expected_s-np.array(f['gravity_s']))))
        assert f['mu_m3_s2']==authority['mu_m3_s2'] and f['radius_m']==authority['radius_m']
        assert coefficient_error<1e-20,coefficient_error
        state=np.array(m['state_gcrs']);gravity=copy.deepcopy(m)
        for key in ['sun_mu_m3_s2','moon_mu_m3_s2','srp_m_s2_at_au']:gravity['force'][key]=0.
        gravity['force']['empirical_rtn_m_s2']=[0.,0.,0.];gravity['force']['relativity']=False
        spherical_error=native_force_error=numba_force_error=frame_error=frame_derivative_error=0.
        epoch_utc_mjd=44244.+(m['epoch_gpst_s']-18)/86400.
        sample_times=[-86400.,-12345.678,0.,43210.125,259259.3,604800.]
        with NativeOrbit(args.cpu_binary,m) as worker:
            for t in sample_times:
                mat=frame_matrix(m,t);p=mat@state[:3];oracle=spherical_gravity(p,f)
                spherical_error=max(spherical_error,float(np.linalg.norm(acceleration(gravity,t,state)-mat.T@oracle)))
                fast=_precision_force(t,state,*precision_packet(m))[3:];full=acceleration(m,t,state)
                numba_force_error=max(numba_force_error,float(np.linalg.norm(fast-full)))
                reply=worker.command('EVALUATE '+' '.join(format(x,'.17g') for x in [t,*state]))
                assert reply['status']=='ok'
                native_force_error=max(native_force_error,float(np.linalg.norm(np.array(reply['acceleration_gcrs'])-full)))
                # Fresh ERFA rotations and published bulletin interpolation.
                utc=epoch_utc_mjd+t/86400.;day=math.floor(utc);weight=utc-day
                xp,yp,dut1=(1-weight)*np.array(eop_table[day])+weight*np.array(eop_table[day+1])
                era=erfa.era00(2400000.5,utc+dut1/86400.)
                q=erfa.c2i06a(2451545.,m['epoch_jd_tt']-2451545.+t/86400.)
                direct=erfa.pom00(xp*np.pi/(180*3600),yp*np.pi/(180*3600),0.)@erfa.rz(era,np.eye(3))@q
                frame_error=max(frame_error,float(np.max(np.abs(mat-direct))))
                if m['domain_s'][0]+1<t<m['domain_s'][1]-1:
                    h=.25
                    numerical=(-frame_matrix(m,t+2*h)+8*frame_matrix(m,t+h)-8*frame_matrix(m,t-h)+frame_matrix(m,t-2*h))/(12*h)
                    frame_derivative_error=max(frame_derivative_error,float(np.max(np.abs(numerical-frame_matrix(m,t,True)))))
            times=np.array(args.times if args.times is not None else [m['domain_s'][0],-86400.,-21600.,0.,900.,3600.,21600.,86400.,259200.,432000.,604800.])
            rows=worker.batch(times.tolist());assert all(row['status']=='ok' for row in rows)
            native=np.array([row['state_gcrs'] for row in rows])
        # DOP853 uses Python complex-step forces, independent of fixed-step native RK4.
        reference=propagate(m,times,method='DOP853',rtol=2e-12,atol=1e-6,max_step=300.)
        tighter=propagate(m,times,method='DOP853',rtol=3e-13,atol=1e-7,max_step=150.)
        # The fitting helper advances in supplied order; evaluate each direction
        # monotonically from epoch to avoid an accidental orbit round trip.
        half=np.empty_like(reference)
        for direction in (-1,1):
            selected=np.flatnonzero(times<0) if direction<0 else np.flatnonzero(times>=0)
            order=selected[np.argsort(direction*times[selected])]
            half[order]=precision_fast_propagate(m,times[order],step=m['integration']['step_s']/2)
        native_errors=np.linalg.norm(native[:,:3]-reference[:,:3],axis=1)
        half_errors=np.linalg.norm(half[:,:3]-reference[:,:3],axis=1)
        item={'model_sha256':digest(path),'gravity_degree':degree,'coefficient_normalization_max_abs':float(coefficient_error),
          'complex_step_vs_scipy_legendre_force_max_m_s2':spherical_error,
          'native_vs_complex_step_force_max_m_s2':native_force_error,'numba_vs_complex_step_force_max_m_s2':numba_force_error,
          'published_eop_direct_erfa_frame_max_abs':frame_error,'analytic_frame_derivative_max_abs_s_inv':frame_derivative_error,
          'times_s':times.tolist(),'native_rk4_step_s':m['integration']['step_s'],
          'native_vs_dop853_position_m':native_errors.tolist(),'half_step_vs_dop853_position_m':half_errors.tolist(),
          'tighter_vs_default_dop853_position_m':np.linalg.norm(tighter[:,:3]-reference[:,:3],axis=1).tolist(),
          'native_vs_tighter_dop853_position_m':np.linalg.norm(native[:,:3]-tighter[:,:3],axis=1).tolist(),
          'half_step_vs_tighter_dop853_position_m':np.linalg.norm(half[:,:3]-tighter[:,:3],axis=1).tolist(),
          'states_gcrs':{'native_rk4':native.tolist(),'half_step_rk4':half.tolist(),'dop853_default':reference.tolist(),'dop853_tighter':tighter.tolist()},
          'elapsed_s':time.perf_counter()-started}
        item['pass']=bool(spherical_error<2e-12 and native_force_error<2e-12 and numba_force_error<2e-12 and frame_error<1e-10 and frame_derivative_error<2e-12 and max(native_errors)<1.)
        report['models'][name]=item;(args.out/'physical_audit.json').write_text(json.dumps(report,indent=2)+'\n');print(name,json.dumps(item),flush=True)
    report['status']='passed' if all(x['pass'] for x in report['models'].values()) else 'failed'
    (args.out/'physical_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['status']!='passed':raise SystemExit('R2 physical numerical audit failed')

if __name__=='__main__':main()
