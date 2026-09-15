#!/usr/bin/env python3
"""Create deterministic artificial corrected-code epochs; no RF signal synthesis."""
from pathlib import Path
import argparse,csv,json,math,random,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
from geodesy import geodetic_to_ecef,enu_to_ecef

def create(folder:Path,count:int=256):
    if count<16 or count>1000000:raise ValueError('demo count must be 16..1000000')
    folder.mkdir(parents=True,exist_ok=False);rng=random.Random(3615);lat=math.radians(52);lon=math.radians(5);anchor=geodetic_to_ecef(lat,lon,100)
    with (folder/'epochs.csv').open('w',newline='')as ef,(folder/'observations.csv').open('w',newline='')as of,(folder/'truth.csv').open('w',newline='')as tf:
        ew,ow,tw=csv.writer(ef),csv.writer(of),csv.writer(tf)
        ew.writerow(['epoch_id','t_rx_gpst_s','x0_m','y0_m','z0_m','b0_m','asa_mask','na_mask','boundary_mask'])
        ow.writerow(['epoch_id','channel','satellite_id','sx_rx_m','sy_rx_m','sz_rx_m','code_m','add_correction_m','sigma_m','ready'])
        tw.writerow(['epoch_id','x_m','y_m','z_m','clock_bias_m','fixture_class'])
        specials={count-6:'too_few',count-5:'absorbed',count-4:'rank_deficient',count-3:'outlier',count-2:'four_only',count-1:'channels32'}
        for e in range(count):
            label=specials.get(e,'noiseless' if e<count//2 else 'noisy')
            truth=enu_to_ecef((250+1.5*e,-120+.8*e,4*math.sin(e*.1)),anchor,lat,lon);bias=75000+.02*e
            seed=[truth[0]+130,truth[1]-90,truth[2]+70,0.]
            nsat=3 if label=='too_few' else 4 if label=='four_only' else 32 if label=='channels32' else 12
            ew.writerow([e,1400000000+e,*seed,4294967295,4294967295,1 if label=='absorbed' else 0])
            tw.writerow([e,*truth,bias,label])
            for ch in range(nsat):
                az=ch*2*math.pi/nsat+.07*math.sin(e*.05);el=math.radians(18+(ch%4)*18)
                if label=='rank_deficient':az=0;el=.5
                vec=(math.cos(el)*math.sin(az),math.cos(el)*math.cos(az),math.sin(el))
                distance=21000000+100000*ch
                sat=enu_to_ecef(tuple(distance*q for q in vec),truth,lat,lon)
                geometric=math.sqrt(sum((sat[i]-truth[i])**2 for i in range(3)));sigma=.75+(ch%3)*.5
                noise=0. if label in ('noiseless','rank_deficient','four_only','channels32')else rng.gauss(0,sigma)
                if label=='outlier'and ch==0:noise+=200
                correction=-2.+.1*math.sin(ch+e);code=geometric+bias+noise-correction
                ow.writerow([e,ch,'G'+str(ch+1).zfill(2),*sat,code,correction,sigma,1])
    profile={'version':'3.6.1.5','profile':'SATNAV-R1','data_origin':'synthetic_geometry_and_corrected_code; no live observations',
             'constellation':'single_receiver_clock_fixture','frame':'ECEF_reception_axes_satellite_at_emission','time_scale':'GPST',
             'corrections':'add_correction_m is added once; no other correction performed by kernel',
             'anchor_geodetic_rad_m':[lat,lon,100.],'anchor_ecef_m':anchor,'chart_r0_m':100000.,'chart_core_m':.1,
             'rho_interval':[-20.,0.],'hoop_phi_rad':math.radians(20),'epoch_tick_period_s':1.,'tick_origin_gpst_s':1400000000,
             'support_spheres_enu_m':[{'center':[0,0,0],'radius':10000},{'center':[100,100,0],'radius':10000}],
             'support_position_bound_m':5.,'code_residual_budget_m':20.,'code_residual_bound_m':.1,
             'bounds_origin':'declared demonstration bounds, not GNSS protection levels','jk_events':'none; hold previous record state'}
    (folder/'profile.json').write_text(json.dumps(profile,indent=2)+'\n')
    return profile
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--epochs',type=int,default=256);a=p.parse_args();create(a.out,a.epochs);print(a.out)
