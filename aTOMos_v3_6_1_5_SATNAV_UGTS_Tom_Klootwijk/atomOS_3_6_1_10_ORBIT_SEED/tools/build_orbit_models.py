"""Build four independent training-only orbital seeds from delivered reference data.

Optional construction dependencies: scipy, numba, pyerfa, jplephem. DE440s is a
construction input; its compressed forcing is embedded in each delivered model.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from orbit_dynamics import build_compact_environment,frame_matrix,propagate,validate_model
from orbit_fitting import read_sp3_training,horizons_training,fit_model,fast_propagate
import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--de440',type=Path,required=True)
    parser.add_argument('--objects',nargs='+',default=['G05','C03','C06','CHANDRA'])
    parser.add_argument('--out',type=Path,default=ROOT/'examples/orbit/models')
    parser.add_argument('--max-nfev',type=int,default=35)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    epoch=1419811200.
    # Bulletin A 26 December 2024. Epoch GPST is UTC Jan1 23:59:42;
    # interpolate the two already-published Jan1/Jan2 forecasts at that instant.
    fraction=1-18/86400
    eop={'dut1_s':.04641+fraction*(.04656-.04641),'xp_arcsec':.1431+fraction*(.1418-.1431),
         'yp_arcsec':.3053,'lod_s':-(.04656-.04641)}
    environment,audit=build_compact_environment(epoch,args.de440,eop)
    construction={'planetary_source':'NASA/JPL DE440s, published 2020-12-21',
       'planetary_sha256':hashlib.sha256(args.de440.read_bytes()).hexdigest(),
       'planetary_url':'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp',
       'earth_orientation_source':'IERS Bulletin A XXXVII 052, published 2024-12-26',
       'earth_orientation_url':'https://datacenter.iers.org/data/6/bulletina-xxxvii-052.txt',
       'earth_orientation_policy':'frozen xp/yp at epoch from published Jan1/Jan2 forecasts; constant UT1 slope from same forecasts; no later measured EOP',
       'eop_at_epoch':eop,'frame':'GCRS-like geocentric axes with IAU2006/2000A Q; ITRF/IGS20 compared using approximate EOP prediction',
       'time':'full GPST seconds since1980-01-06; TT=GPST+51.184s; geocentric Fairhead-Bretagnon TT/TDB periodic correction for DE440 and Horizons',
       'coefficient_compression_checks':audit,
       'force_model_selection':'fixed for all four objects before future-target comparisons',
       'replay_dependencies':'all numerical forcing and frame coefficients embedded in model; no DE440 or ERFA lookup at replay'}
    classes={'G05':'MEO','C03':'GEO','C06':'IGSO','CHANDRA':'HEO'}
    for name in args.objects:
        start=time.monotonic();model=copy.deepcopy(environment)
        if name=='CHANDRA':
            path=ROOT/'source/orbit_data/HORIZONS_CHANDRA_20250101_20250109_ICRF_TDB.txt'
            values=horizons_training(path,model['epoch_jd_tt']);values=values[values[:,0]>=model['domain_s'][0]]
            times=values[:,0];positions=values[:,1:4];velocities=values[:,4:7]
        else:
            path=ROOT/'source/orbit_data/GBM0MGXRAP_20250010000_01D_05M_ORB.SP3.gz'
            values=read_sp3_training(path,name,epoch);times=values[:,0]
            positions=np.array([frame_matrix(model,float(t)).T@p for t,p in zip(times,values[:,1:4])]);velocities=None
        print(f'{name}: fitting {len(times)} training rows {times.min():.3f}..{times.max():.3f}s',flush=True)
        model,fit=fit_model(model,times,positions,velocities,args.max_nfev)
        if name=='CHANDRA':
            # Numerical convergence against independent DOP853, without using
            # future target data, requires finer RK4 near HEO perigee. The fitted
            # initial state and physical parameters stay unchanged.
            model['integration'].update(step_s=7.5,checkpoint_stride_steps=480,max_steps_per_query=100000)
        validate_model(model)
        fit.update({'satellite':name,'orbit_class':classes[name],'training_source':str(path.relative_to(ROOT)).replace('\\','/'),
             'training_source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'elapsed_s':time.monotonic()-start})
        # Held-out future data is never opened here. Check independent dynamics
        # on the training interval only; its result cannot select a force model.
        checktimes=np.array([float(times.min()),float(times[len(times)//2]),0.])
        independent=propagate(model,checktimes)
        fast=fast_propagate(model,checktimes[::-1])[::-1]
        fit['rk4_vs_dop853_training_max_m']=float(np.max(np.linalg.norm(independent[:,:3]-fast[:,:3],axis=1)))
        payload={'model':model,'fit':fit,'construction':construction}
        (args.out/(name+'.json')).write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
        print(f'{name}: RMS {fit["training_rms_3d_m"]:.3f}m max {fit["training_max_3d_m"]:.3f}m; SRP {model["force"]["srp_m_s2_at_au"]:.4g}; RTN {model["force"]["empirical_rtn_m_s2"]}; {time.monotonic()-start:.1f}s',flush=True)


if __name__=='__main__':main()
