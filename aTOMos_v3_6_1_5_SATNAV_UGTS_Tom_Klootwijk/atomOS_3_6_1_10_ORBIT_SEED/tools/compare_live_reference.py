"""Audit LIVE-R1 traces and compare real positions with independent RTKLIB XYZ.

The optional weight experiment changes weights only, uses NumPy lstsq, and is
reported separately from the native result. Comparison coordinates are metadata,
never observations/seeds, and are not assumed surveyed truth.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from live_gnss import (C,GPSEpoch,GPSObservation,calendar_to_gpst,prepare_epoch,
                       read_rinex_nav,select_ephemeris)


def metrics(values):
    return {'count':len(values),'mean':statistics.mean(values) if values else None,
            'median':statistics.median(values) if values else None,
            'rms':math.sqrt(statistics.mean(v*v for v in values)) if values else None,
            'max':max(values,default=None)}


def solve_numpy(prepared,initial,sigmas=None):
    observations=prepared['observations']
    satellites=np.array([[o[k] for k in ('sx_rx_m','sy_rx_m','sz_rx_m')] for o in observations],dtype=float)
    codes=np.array([o['code_m']+o['add_correction_m'] for o in observations],dtype=float)
    sigma=np.array(sigmas if sigmas is not None else [o['sigma_m'] for o in observations])
    state=np.array(initial,dtype=float)
    for _ in range(20):
        delta=state[:3]-satellites;distance=np.linalg.norm(delta,axis=1)
        matrix=np.column_stack([delta/distance[:,None],np.ones(len(observations))])
        residual=codes-distance-state[3]
        step,_,rank,_=np.linalg.lstsq(matrix/sigma[:,None],residual/sigma,rcond=None)
        if rank != 4:raise ValueError('independent NumPy solve is rank deficient')
        state+=step
        if max(abs(step))<1e-7:return state
    raise ValueError('independent NumPy solve did not converge')


def rtklib_sigma(row,navigation):
    d=row['diagnostics'];sine=math.sin(math.radians(d['elevation_deg']))
    eph=select_ephemeris(navigation.ephemerides,d['prn'],d['transmit_time_gpst_s'])
    # RINEX accuracy maps to the upper bound of the broadcast URA index.
    values=(2.4,3.4,4.85,6.85,9.65,13.65,24.,48.,96.,192.,384.,768.,1536.,3072.,6144.)
    ura=next((value for value in values if eph.ura_m<=value),6144.)
    return math.sqrt(.09*(1+1/sine)+ura*ura+.09+(.5*d['iono_m'])**2+(.3/(sine+.1))**2)


def audit(trace,oracle,out,navigation_path=None,comparison_coordinate=None):
    records=[json.loads(line) for line in Path(trace).read_text().splitlines() if line.strip()]
    reference=[]
    for line in Path(oracle).read_text().splitlines():
        if not line.strip() or line.startswith('%'):continue
        p=line.split();year,month,day=map(int,p[0].split('/'));hour,minute,second=map(float,p[1].split(':'))
        reference.append({'time':calendar_to_gpst(year,month,day,int(hour),int(minute),second),
                          'position':[float(v) for v in p[2:5]],'quality':int(p[5]),'used':int(p[6])})
    navigation=read_rinex_nav(navigation_path) if navigation_path else None
    rows=[];failures=[];numpy_differences=[];correction_comparisons=0;pass_comparisons=0;weight_differences=[]
    previous_state=[0.,0.,0.,0.];previous_station=None
    for record in records:
        r=record['result'];raw=record['raw_epoch'];passes=record['passes']
        station=raw['source_metadata'].get('station_id')
        if station is not None and previous_station is not None and station!=previous_station:previous_state=[0.]*4
        if station is not None:previous_station=station
        first=passes[0]['prepared']
        if [*first['receiver_seed_ecef_m'],first['receiver_seed_clock_m']] != previous_state:
            failures.append({'epoch_id':r['epoch_id'],'reason':'warm/cold seed did not equal prior native valid state'})
        raw_observations={o['prn']:o for o in raw['observations']}
        expected_seed=previous_state
        for item in passes:
            p=item['prepared'];solution=item['solution'];actual_seed=[*p['receiver_seed_ecef_m'],p['receiver_seed_clock_m']]
            if actual_seed != expected_seed:failures.append({'epoch_id':r['epoch_id'],'reason':'outer seed continuity'})
            for o in p['observations']:
                d=o['diagnostics'];prn=d['prn'];correction=C*d['clock_l1_s']-d['iono_m']-d['tropo_m']
                correction_comparisons+=1
                if o['code_m'] != raw_observations[prn]['pseudorange_m'] or o['add_correction_m'] != correction or o['channel']!=prn-1 or d['health']!=0:
                    failures.append({'epoch_id':r['epoch_id'],'prn':prn,'reason':'raw code/correction/channel/health mismatch'})
            if solution['status']=='CONVERGED':
                independent=solve_numpy(p,actual_seed)
                difference=max(abs(independent-np.array(solution['state'])))
                numpy_differences.append(float(difference));pass_comparisons+=1
                if difference>1e-5:failures.append({'epoch_id':r['epoch_id'],'reason':'NumPy/native state discrepancy','max_difference_m':float(difference)})
            expected_seed=solution['state']
        if not r['position_available']:continue
        final=passes[-1]
        if not final['prepared']['model']['receiver_geometry_initialized'] or max(final['position_delta_m'],final['clock_delta_m'])>=.001:
            failures.append({'epoch_id':r['epoch_id'],'reason':'published without initialized converged corrections'})
        previous_state=r['state_ecef_clock_m']
        corrected_time=r['time_gpst_s']-r['state_ecef_clock_m'][3]/C
        matched=min(reference,key=lambda ref:abs(ref['time']-corrected_time))
        time_delta=corrected_time-matched['time']
        if abs(time_delta)>.02:
            failures.append({'epoch_id':r['epoch_id'],'reason':'no contemporaneous RTKLIB position','time_difference_s':time_delta});continue
        row={'epoch_id':r['epoch_id'],'raw_receiver_time_gpst_s':r['time_gpst_s'],
             'estimated_reception_gpst_s':corrected_time,'oracle_time_gpst_s':matched['time'],
             'oracle_quality':matched['quality'],'time_difference_s':time_delta,
             'native_position_ecef_m':r['state_ecef_clock_m'][:3],'rtklib_position_ecef_m':matched['position'],
             'native_vs_rtklib_3d_m':math.dist(r['state_ecef_clock_m'][:3],matched['position']),
             'native_used':r['used'],'rtklib_used':matched['used']}
        if comparison_coordinate:
            row['native_vs_comparison_coordinate_3d_m']=math.dist(r['state_ecef_clock_m'][:3],comparison_coordinate)
            row['rtklib_vs_comparison_coordinate_3d_m']=math.dist(matched['position'],comparison_coordinate)
        if navigation:
            epoch=GPSEpoch(raw['time_gpst_s'],tuple(GPSObservation(**o) for o in raw['observations']))
            state=np.array(r['state_ecef_clock_m'])
            for _ in range(4):
                p=prepare_epoch(epoch,navigation.ephemerides,state[:3],state[3],navigation.iono_alpha,navigation.iono_beta)
                state=solve_numpy(p,state,[rtklib_sigma(o,navigation) for o in p['observations']])
            row['weight_experiment_vs_rtklib_3d_m']=math.dist(state[:3],matched['position'])
            weight_differences.append(row['weight_experiment_vs_rtklib_3d_m'])
        rows.append(row)
    hashes={str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (trace,oracle,*([navigation_path] if navigation_path else []))}
    report={'status':'passed' if not failures and rows else 'failed','scope':'replay algebra/continuity plus independent RTKLIB position comparison; no certified accuracy claim',
        'native_trace_epochs':len(records),'oracle_epochs':len(reference),'matched_valid_positions':len(rows),
        'cold_start_seed_m':[0.,0.,0.,0.],'raw_code_and_correction_comparisons':correction_comparisons,
        'independent_numpy_converged_passes':pass_comparisons,'numpy_native_max_component_difference_m':max(numpy_differences,default=None),
        'native_vs_rtklib_3d_m':metrics([r['native_vs_rtklib_3d_m'] for r in rows]),
        'comparison_coordinate_ecef_m':comparison_coordinate,'comparison_coordinate_role':'metadata comparison, not assumed surveyed truth; never used as input',
        'native_vs_comparison_coordinate_3d_m':metrics([r['native_vs_comparison_coordinate_3d_m'] for r in rows]) if comparison_coordinate else None,
        'rtklib_vs_comparison_coordinate_3d_m':metrics([r['rtklib_vs_comparison_coordinate_3d_m'] for r in rows]) if comparison_coordinate else None,
        'weight_experiment':{'performed':bool(navigation),'same_model_with_rtklib_variance':'0.09*(1+1/sinE)+URA^2+0.09+(I/2)^2+(0.3/(sinE+0.1))^2',
                             'role':'diagnostic NumPy re-solve, not the executed native profile','vs_rtklib_3d_m':metrics(weight_differences)},
        'time_matching':'RTKLIB position tags corrected by its estimated receiver clock and rounded to 0.001 s; candidate raw tag minus b/c matched within 0.02 s',
        'input_sha256':hashes,'failures':failures,'rows':rows}
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace',required=True);parser.add_argument('--oracle',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--nav');parser.add_argument('--comparison-coordinate',nargs=3,type=float)
    args=parser.parse_args();report=audit(args.trace,args.oracle,args.out,args.nav,args.comparison_coordinate)
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','input_sha256')},indent=2))
    raise SystemExit(0 if report['status']=='passed' else 1)
