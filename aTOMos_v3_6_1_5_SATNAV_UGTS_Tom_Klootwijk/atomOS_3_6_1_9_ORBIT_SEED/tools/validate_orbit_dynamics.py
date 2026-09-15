"""Independent potential/frame audit and training-only integration convergence."""
from __future__ import annotations
import argparse,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from orbit_dynamics import acceleration,frame_matrix,propagate,segment_value
from orbit_fitting import fast_propagate,read_sp3_training,fit_model,prepare_numba,_force


def potential(p,f):
    r=np.linalg.norm(p);s=p[2]/r;x,y,z=p
    return f['mu_m3_s2']/r*(1-f['j2']*(f['radius_m']/r)**2*(3*s*s-1)/2
        -f['j3']*(f['radius_m']/r)**3*(5*s**3-3*s)/2
        -f['j4']*(f['radius_m']/r)**4*(35*s**4-30*s*s+3)/8)+f['mu_m3_s2']*f['radius_m']**2/r**5*(3*f['c22']*(x*x-y*y)+6*f['s22']*x*y)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--refit-g05-15s',action='store_true');parser.add_argument('--heo-week-numerics',action='store_true')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    import erfa
    report={'scope':'independent force potential/frame and training-only numerical audit; no held-out target data read','models':{}}
    for name in ['G05','C03','C06','CHANDRA']:
        envelope=json.loads((ROOT/f'examples/orbit/models/{name}.json').read_text());m=envelope['model'];f=m['force']
        t=0.;state=np.array(m['state_gcrs']);mat=frame_matrix(m,t);p=mat@state[:3]
        h=100.;gradient=np.empty(3)
        for j in range(3):
            e=np.eye(3)[j]*h
            gradient[j]=(-potential(p+2*e,f)+8*potential(p+e,f)-8*potential(p-e,f)+potential(p-2*e,f))/(12*h)
        gravity=copy.deepcopy(m)
        for key in ['sun_mu_m3_s2','moon_mu_m3_s2','srp_m_s2_at_au']:gravity['force'][key]=0.
        gravity['force']['empirical_rtn_m_s2']=[0.,0.,0.]
        gravity_error=float(np.linalg.norm(acceleration(gravity,t,state)-mat.T@gradient))
        directq=erfa.c2i06a(2451545.,m['epoch_jd_tt']-2451545.)
        direct=erfa.pom00(m['frame']['xp_rad'],m['frame']['yp_rad'],0.)@erfa.rz(m['frame']['era0_rad'],np.eye(3))@directq
        frame_error=float(np.max(np.abs(mat-direct)))
        fnative=_force(t,state,*prepare_numba(m))
        implementation_error=float(np.linalg.norm(fnative[3:]-acceleration(m,t,state)))
        times=np.array([0.,-21600.,-43200.,-86400.])
        r30=fast_propagate(m,times,step=30.);r15=fast_propagate(m,times,step=15.);r75=fast_propagate(m,times,step=7.5)
        independent=propagate(m,times)
        item={'gravity_potential_gradient_error_m_s2':gravity_error,'direct_erfa_frame_max_abs':frame_error,
          'python_vector_vs_numba_scalar_force_m_s2':implementation_error,
          'rk4_30_vs_15_training_max_m':float(np.linalg.norm(r30[:,:3]-r15[:,:3],axis=1).max()),
          'rk4_15_vs_7_5_training_max_m':float(np.linalg.norm(r15[:,:3]-r75[:,:3],axis=1).max()),
          'rk4_30_vs_dop853_training_max_m':float(np.linalg.norm(r30[:,:3]-independent[:,:3],axis=1).max())}
        report['models'][name]=item
        if name=='CHANDRA' and args.heo_week_numerics:
            future=np.array([0.,900.,3600.,21600.,86400.,259200.,432000.,604800.])
            oracle=propagate(m,future)
            fine=propagate(m,future,rtol=3e-13,atol=1e-7,max_step=150.)
            values={}
            for step in [30.,15.,7.5]:
                trial=fast_propagate(m,future,step=step)
                values[str(step)]=np.linalg.norm(trial[:,:3]-oracle[:,:3],axis=1).tolist()
            item['week_numerics']={'times_s':future.tolist(),'rk4_vs_dop853_errors_m':values,
                  'dop853_tighter_vs_default_max_m':float(np.linalg.norm(fine[:,:3]-oracle[:,:3],axis=1).max()),
                  'selection':'replay step7.5s chosen from numerical oracle only; state and forces unchanged; no future target data opened'}
        if name=='G05' and args.refit_g05_15s:
            alternate=copy.deepcopy(m);alternate['integration']['step_s']=15.
            rows=read_sp3_training(ROOT/envelope['fit']['training_source'],name,m['epoch_gpst_s']);ts=rows[:,0]
            xyz=np.array([frame_matrix(m,t).T@p for t,p in zip(ts,rows[:,1:4])])
            fitted,details=fit_model(alternate,ts,xyz)
            (args.out/'G05_15s_training_only_model.json').write_text(json.dumps({'model':fitted,'fit':details},indent=2)+'\n')
            item['refit_15s_training_rms_m']=details['training_rms_3d_m'];item['refit_15s_training_max_m']=details['training_max_3d_m']
        print(name,json.dumps(item),flush=True)
    report['pass']=all(m['gravity_potential_gradient_error_m_s2']<1e-8 and m['direct_erfa_frame_max_abs']<1e-10 and m['python_vector_vs_numba_scalar_force_m_s2']<1e-12 for m in report['models'].values())
    (args.out/'physical_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit('physical audit failed')


if __name__=='__main__':main()
