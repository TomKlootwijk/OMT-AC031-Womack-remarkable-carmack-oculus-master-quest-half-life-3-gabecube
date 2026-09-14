#!/usr/bin/env python3
"""Passive UGTS support/compatibility/guard/event/transition/lineage adapter."""
from pathlib import Path
import argparse,csv,json,math,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
from geodesy import ecef_to_enu,ecef_to_geodetic
from ugts import quantize,contiguous,morton,phase_winding,otan2_source,wrap,digest

def process(input_dir,run_dir):
    cfg=json.loads((input_dir/'profile.json').read_text())
    if cfg['frame']!='ECEF_reception_axes_satellite_at_emission' or cfg['time_scale']!='GPST':raise ValueError('Explicit frame/time adapter required')
    lat,lon,_=cfg['anchor_geodetic_rad_m'];origin=cfg['anchor_ecef_m'];r0=cfg['chart_r0_m'];core=cfg['chart_core_m'];phi=cfg['hoop_phi_rad']
    if not r0>core>0:raise ValueError('positive ordered chart radii required')
    tick_period=cfg['epoch_tick_period_s'];tick_origin=cfg['tick_origin_gpst_s']
    if tick_period<=0 or any(cfg[k]<0 for k in ['support_position_bound_m','code_residual_bound_m','code_residual_budget_m']):raise ValueError('invalid period/bounds')
    with (run_dir/'solutions.csv').open()as f:rows=list(csv.DictReader(f))
    head='0'*64;records=[];previous_chart=None;previous_time=None;events={};seen=set()
    for row in rows:
        eid=int(row['epoch_id']);t=float(row['t_rx_gpst_s'])
        if eid in seen:raise ValueError('duplicate epoch result')
        seen.add(eid)
        record={'version':'3.6.1.6','epoch_id':eid,'t_gpst_s':t,'solver_status':row['status'],
                'stages':['support','compatibility','guard','verified_event','transition','lineage'],
                'previous_hash':head,'frame_id':digest({'origin':origin,'lat':lat,'lon':lon}),
                'jk':{'before':0,'j':0,'k':0,'after':0,'meaning':'explicit hold; no navigation action'},
                'author':'Tom Klootwijk','quantity':'receiver_position_candidate'}
        event='NO_SOLUTION';compat=previous_time is None or t>previous_time
        if row['status']=='CONVERGED':
            xyz=[float(row[k])for k in ('x_m','y_m','z_m')]
            if not all(math.isfinite(v)for v in xyz):raise ValueError('nonfinite solution')
            enu=ecef_to_enu(xyz,origin,lat,lon);lla=ecef_to_geodetic(*xyz)
            margins=[s['radius']-math.dist(enu,s['center'])-cfg['support_position_bound_m'] for s in cfg['support_spheres_enu_m']]
            support=any(x>=0 for x in margins);overlap=sum(x>=0 for x in margins)>1
            max_residual=0
            # CSV holds RMS and max normalized; use the raw per-channel residual file below for a metre-domain guard.
            record.update(ecef_m=xyz,enu_m=enu,geodetic_rad_m=lla,clock_bias_m=float(row['clock_bias_m']),
                          formal_sigma3d_m=math.sqrt(sum(float(row[k])for k in ('var_x_m2','var_y_m2','var_z_m2'))),
                          support={'admitted':support,'sphere_margins_m':margins,'overlap':overlap,'bound_origin':cfg['bounds_origin']},
                          compatibility={'increasing_linear_time':compat,'frame':'fixed_local_ENU','estimator_clock_unknowns':1},
                          fit=row['fit'])
            horizontal=math.hypot(enu[0],enu[1])
            if horizontal<core:record['chart']={'status':'origin_core'}
            else:
                rho=math.log(horizontal/r0);theta=math.atan2(enu[1],enu[0]);record['chart']={'rho':rho,'theta':theta,'up_m':enu[2],'hoop_phi':phi,'status':'defined' if -20<=rho<=0 else 'out_of_key_range'}
                tick_float=(t-tick_origin)/tick_period;tick=round(tick_float)
                if abs(tick_float-tick)>1e-6:record['chart']['status']='tick_not_on_declared_lattice'
                if record['chart']['status']=='defined':
                    q=quantize(rho,theta,tick,phi);wind,phase=phase_winding(tick,0,16384)
                    record['packing']={'fields':q,'contiguous_hex':f'{contiguous(q):016x}','morton_hex':f'{morton(q):016x}','linear_tick':tick,'winding':wind,'phase':phase,'not_a_complete_navigation_state':True}
                if previous_chart is None:record['otan2']={'status':'first_observation','value':None}
                elif not compat:record['otan2']={'status':'nonmonotonic_time','value':None}
                else:record['otan2']={**otan2_source(wrap(theta-previous_chart[1]),rho-previous_chart[0],0.),'increment_policy':'principal_difference_of_local_theta','quantity':'chart_motion_slope_not_geodetic_heading'}
                if compat:previous_chart=(rho,theta)
            event='CANDIDATE_PENDING_RESIDUAL_GUARD' if support and compat else 'DOMAIN_OR_TIME_UNRESOLVED'
        record['event']=event;record['transition']='publish_observation_only';records.append(record);previous_time=t
    residuals={}
    with (run_dir/'residuals.csv').open()as f:
        for row in csv.DictReader(f):residuals.setdefault(int(row['epoch_id']),[]).append(float(row['residual_m']))
    head='0'*64
    for record in records:
        if record['solver_status']=='CONVERGED':
            values=residuals.get(record['epoch_id'],[])
            if not values:raise ValueError('missing residuals for converged epoch')
            m=max(abs(r)for r in values);u=cfg['code_residual_bound_m'];budget=cfg['code_residual_budget_m']
            lower=max(0.,m-u);upper=m+u
            classification='WITHIN' if upper<=budget else 'EXCEEDS' if lower>budget else 'UNRESOLVED'
            record['guard']={'max_abs_residual_m':m,'model_interval_m':[lower,upper],'budget_m':budget,'classification':classification,'conditional_on_declared_bound':True}
            if record['event']=='CANDIDATE_PENDING_RESIDUAL_GUARD':
                record['event']='POSITION_CANDIDATE_VERIFIED' if classification=='WITHIN' and record['fit']=='WITHIN_RESIDUAL_BUDGET' else 'POSITION_CANDIDATE_UNRESOLVED'
        record['previous_hash']=head;head=digest(record);record['record_hash']=head;events[record['event']]=events.get(record['event'],0)+1
    path=run_dir/'ugts_events.jsonl'
    with path.open('x')as f:
        for record in records:f.write(json.dumps(record,separators=(',',':'),allow_nan=False)+'\n')
    summary={'version':'3.6.1.6','events':events,'head_sha256':head,'scope':'UGTS computational event criteria only. Supplied bounds are not GNSS integrity/protection guarantees.'}
    (run_dir/'ugts_summary.json').write_text(json.dumps(summary,indent=2)+'\n');return summary
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--run',type=Path,required=True);a=p.parse_args();print(json.dumps(process(a.input,a.run),indent=2))

