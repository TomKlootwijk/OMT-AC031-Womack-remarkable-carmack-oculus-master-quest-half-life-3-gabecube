"""Fit R2 using past samples and the final past day as internal holdout.

The frozen selection rule chooses among 1, 3 and 7 past days by the smallest
maximum internal-day position error, then refits that window through the epoch.
No post-epoch target samples enter fitting or window selection.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from orbit_dynamics import frame_matrix,validate_model
from orbit_fitting import fit_model,read_sp3_training,horizons_training,fast_propagate
from orbit_precision import build_precision_environment


def source_label(path):
    try:return str(path.resolve().relative_to(ROOT.resolve())).replace('\\','/')
    except ValueError:return str(path.resolve())


def training_rows(model,name,training_dir=None):
    base=ROOT/'source/orbit_data';paths=[];rows={}
    if name=='CHANDRA':
        paths=sorted(training_dir.glob('HORIZONS_CHANDRA_*_ICRF_TDB.txt')) if training_dir else [base/'earlier_training/HORIZONS_CHANDRA_20241225_20250101_ICRF_TDB.txt',base/'HORIZONS_CHANDRA_20250101_20250109_ICRF_TDB.txt']
        for p in paths:
            for row in horizons_training(p,model['epoch_jd_tt']):
                if model['domain_s'][0]<=row[0]<=0:rows[float(row[0])]=row[1:]
    else:
        paths=sorted(training_dir.glob('GBM*SP3.gz')) if training_dir else sorted((base/'earlier_training').glob('GBM*SP3.gz'))+[base/'GBM0MGXRAP_20250010000_01D_05M_ORB.SP3.gz']
        for p in paths:
            for row in read_sp3_training(p,name,model['epoch_gpst_s']):
                if model['domain_s'][0]<=row[0]<=0:rows[float(row[0])]=frame_matrix(model,float(row[0])).T@row[1:4]
    values=np.array([(t,*rows[t]) for t in sorted(rows)])
    if not paths or not len(values):raise ValueError(f'no past training samples for {name}')
    provenance=[{'path':source_label(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
    return values,provenance


def fit_slice(environment,values,start,end,max_nfev):
    selected=values[(values[:,0]>=start)&(values[:,0]<=end)]
    if len(selected)<24:raise ValueError('training arc too short')
    m=copy.deepcopy(environment)
    fit,details=fit_model(m,selected[:,0],selected[:,1:4],selected[:,4:7] if selected.shape[1]==7 else None,max_nfev)
    return fit,details


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--de440',type=Path,required=True)
    p.add_argument('--objects',nargs='+',default=['G05','C03','C06','CHANDRA']);p.add_argument('--out',type=Path,default=ROOT/'examples/orbit/precision_models')
    p.add_argument('--windows-days',type=float,nargs='+',default=[1.,3.,7.]);p.add_argument('--max-nfev',type=int,default=35)
    p.add_argument('--epoch-gpst-s',type=float,default=1419811200.)
    p.add_argument('--training-dir',type=Path,help='Directory containing only the past SP3/Horizons source arc')
    p.add_argument('--bulletin',type=Path,default=ROOT/'source/orbit_data/bulletina-xxxvii-052.txt')
    p.add_argument('--benchmark-status',choices=['reused','fresh'],default='reused')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    if any(not np.isfinite(w) or w<=0 or w>7 for w in args.windows_days):p.error('window lengths must be finite, positive and at most 7 days')
    if args.epoch_gpst_s!=1419811200. and args.training_dir is None:p.error('a non-default epoch requires an explicit past training directory')
    gravity=ROOT/'source/orbit_data/gravity_reference/EGM96_degree12.gfc';bulletin=args.bulletin
    env,audit=build_precision_environment(args.epoch_gpst_s,args.de440,bulletin,gravity)
    policy={'profile':'R2-PAST-WINDOW-SELECTION-1','windows_days':args.windows_days,
        'internal_holdout_s':[-86400.,0.],'candidate_cutoff_s':-86400.,
        'score':'maximum 3D position error; ties choose the shorter window',
        'final_refit':'selected window ending at epoch; target rows strictly after epoch excluded',
        'parameters':'Cartesian state6 + SRP1 + constant RTN3; fixed degree/order12 EGM96, Schwarzschild, published EOP',
        'max_nfev':args.max_nfev,'fitting_step_s':30.,'replay_step_s':{'G05':30.,'C03':30.,'C06':30.,'CHANDRA':7.5}}
    policy_hash=hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (args.out/'selection_policy.json').write_text(json.dumps({'policy':policy,'policy_sha256':policy_hash},indent=2)+'\n')
    for name in args.objects:
        start=time.monotonic();values,sources=training_rows(env,name,args.training_dir);scores=[];selection_end=-86400.
        validation=values[(values[:,0]>selection_end)&(values[:,0]<=0)]
        for window in args.windows_days:
            print(f'{name} past-only candidate {window:g} days',flush=True)
            model,fit=fit_slice(env,values,selection_end-window*86400,selection_end,args.max_nfev)
            predicted=fast_propagate(model,validation[:,0],fit['anchor_state_gcrs'],fit['fit_reference_anchor_s'])
            errors=np.linalg.norm(predicted[:,:3]-validation[:,1:4],axis=1)
            item={'window_days':window,'training_fit':fit,'internal_holdout_start_s':float(validation[0,0]),
               'internal_holdout_end_s':float(validation[-1,0]),'internal_holdout_rows':len(validation),
               'internal_holdout_rms_m':float(np.sqrt(np.mean(errors**2))),'internal_holdout_max_m':float(errors.max()),
               'internal_holdout_endpoint_m':float(errors[-1]),'future_target_rows_used':0}
            scores.append(item);print(f'{name} {window:g}d internal-day RMS/max/end {item["internal_holdout_rms_m"]:.3f}/{item["internal_holdout_max_m"]:.3f}/{item["internal_holdout_endpoint_m"]:.3f}m',flush=True)
            (args.out/(name+'_selection.json')).write_text(json.dumps({'status':'running','candidates':scores},indent=2)+'\n')
        selected=min(scores,key=lambda row:(row['internal_holdout_max_m'],row['window_days']))
        days=selected['window_days'];model,fit=fit_slice(env,values,-days*86400,0.,args.max_nfev)
        if name=='CHANDRA':model['integration'].update(step_s=7.5,checkpoint_stride_steps=480,max_steps_per_query=100000)
        validate_model(model)
        fit.update({'satellite':name,'orbit_class':{'G05':'MEO','C03':'GEO','C06':'IGSO','CHANDRA':'HEO'}[name],
            'training_sources':sources,'training_source':sources[-1]['path'],'training_source_sha256':sources[-1]['sha256'],
            'selected_window_days':days,'internal_selection':'minimize maximum last-past-day residual; all post-epoch target rows excluded',
            'selection_policy_sha256':policy_hash,'selection_candidates':scores,
            'outer_benchmark':'Previously inspected R1 comparative benchmark; not blind new data' if args.benchmark_status=='reused' else 'Fresh confirmation target arc; no post-epoch target inspection before model freeze',
            'elapsed_s':time.monotonic()-start})
        construction={'gravity_source':source_label(gravity),'gravity_sha256':hashlib.sha256(gravity.read_bytes()).hexdigest(),
           'gravity_normalization':'EGM96 fully normalized converted to unnormalized C/S without Condon-Shortley phase; full degree/order12',
           'earth_orientation_source':source_label(bulletin),'earth_orientation_sha256':hashlib.sha256(bulletin.read_bytes()).hexdigest(),
           'earth_orientation_policy':'Piecewise linear xp,yp,DUT1 from all relevant rows of the supplied pre-epoch bulletin; no post-cutoff observed EOP',
           'planetary_source':'DE440s published2020','planetary_sha256':hashlib.sha256(args.de440.read_bytes()).hexdigest(),
           'coefficient_compression_checks':audit,'selection_chronology':'Final past day selects the prior training window; final fit uses only t<=epoch',
           'replay_dependencies':'all numerical dependencies embedded, including full gravity and varying EOP'}
        # Detailed selection evidence stays outside each compact seed payload.
        selection=fit.pop('selection_candidates')
        fit['selection_report']=name+'_selection.json'
        (args.out/(name+'_selection.json')).write_text(json.dumps({'status':'selected','selected_window_days':days,'candidates':selection},indent=2)+'\n')
        (args.out/(name+'.json')).write_text(json.dumps({'model':model,'fit':fit,'construction':construction},indent=2)+'\n')
        print(f'{name} selected{days:g}d; final training RMS/max {fit["training_rms_3d_m"]:.3f}/{fit["training_max_3d_m"]:.3f}m; {time.monotonic()-start:.1f}s',flush=True)


if __name__=='__main__':main()
