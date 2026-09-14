#!/usr/bin/env python3
"""Generate deterministic corrected-code positioning records (synthetic, not RF signals)."""
from pathlib import Path
import argparse,csv,json,math
PI=math.pi

def anchor(lat=52.,lon=5.,height=20.):
    a=6378137.;f=1/298.257223563;e2=f*(2-f);p,l=math.radians(lat),math.radians(lon)
    n=a/math.sqrt(1-e2*math.sin(p)**2)
    origin=((n+height)*math.cos(p)*math.cos(l),(n+height)*math.cos(p)*math.sin(l),(n*(1-e2)+height)*math.sin(p))
    east=(-math.sin(l),math.cos(l),0.);north=(-math.cos(l)*math.sin(p),-math.sin(l)*math.sin(p),math.cos(p));up=(math.cos(l)*math.cos(p),math.sin(l)*math.cos(p),math.sin(p))
    return origin,east,north,up

def create(directory: Path,epochs:int=128,noise:float=0.,edges:bool=False):
    if epochs<1 or epochs>1000000 or not math.isfinite(noise) or noise<0:raise ValueError('invalid fixture size or noise')
    directory.mkdir(parents=True,exist_ok=True)
    for name in ('epochs.csv','observations.csv','truth.csv','fixture.json'):
        if (directory/name).exists():raise FileExistsError(directory/name)
    o,e,n,u=anchor()
    def ecef(v):return [o[j]+e[j]*v[0]+n[j]*v[1]+u[j]*v[2] for j in range(3)]
    az=[0,31,65,100,142,178,210,245,278,309,337,355]
    el=[16,53,32,70,24,45,12,60,35,20,76,40]
    satellites=[]
    for i,(a,h) in enumerate(zip(az,el)):
        a,h=math.radians(a),math.radians(h);rr=21e6+i*12000
        satellites.append(ecef((rr*math.sin(a)*math.cos(h),rr*math.cos(a)*math.cos(h),rr*math.sin(h))))
    with (directory/'epochs.csv').open('w',newline='') as ef,(directory/'observations.csv').open('w',newline='') as of,(directory/'truth.csv').open('w',newline='')as tf:
        ew,ow,tw=csv.writer(ef),csv.writer(of),csv.writer(tf)
        ew.writerow(['epoch_id','tick_ms','initial_x_m','initial_y_m','initial_z_m','initial_clock_m','hinge_rad','asa_mask','na_mask','boundary_mask','q_before','j','k','blend_bits'])
        ow.writerow(['epoch_id','slot','satellite_id','sat_rxframe_x_m','sat_rxframe_y_m','sat_rxframe_z_m','corrected_code_m','sigma_m'])
        tw.writerow(['epoch_id','x_m','y_m','z_m','clock_m','east_m','north_m','up_m','expected_status'])
        for i in range(epochs):
            p=(150+0.2*i, -75+6*math.sin(i/25),12+2*math.sin(i/50));truth=ecef(p);clock=23000+0.15*i;tick=1280000000000+1000*i
            mask=(1<<12)-1;boundary=0;expected='ok'
            if edges and i==2:boundary=1;expected='whole_word_absorbed'
            if edges and i==3:mask=7;expected='insufficient_observations'
            if edges and i==4:expected='rank_deficient'
            if i%7==6:mask&=~3 # ten observations, explicitly supplied selection
            ew.writerow([i,tick,truth[0]+80,truth[1]-50,truth[2]+25,0,0.35,mask,0xffffffff,boundary,i%2,1,0,5])
            tw.writerow([i,*truth,clock,*p,expected])
            for j,sv in enumerate(satellites):
                sat=satellites[0] if edges and i==4 else sv
                code=math.dist(truth,sat)+clock+noise*math.sin((i+1)*(j+2)*.31)
                ow.writerow([i,j,f'G{j+1:02d}',*sat,code,.7+.1*j])
    settings={'version':'3.6.1.5','dataset':'synthetic corrected-code geometric fixture','epochs':epochs,'satellites_per_epoch':12,'noise_amplitude_m':noise,'edge_cases':edges,'time_scale':'GPST','tick_unit':'millisecond','single_receiver':True,'anchor':{'lat_deg':52.,'lon_deg':5.,'height_m':20.},'satellite_coordinates':'transmit-epoch positions already expressed in receive-time ECEF; synthetic values','code':'corrected for all nonreceiver-clock terms by fixture construction','chart':{'r0_m':10000.,'core_radius_m':.01,'rho_min':-20.,'rho_max':0.,'theta':'atan2(north,east)','hinge':'explicit independent input','time_key':'full GPST tick_ms modulo 16384'}}
    (directory/'fixture.json').write_text(json.dumps(settings,indent=2)+'\n')
    return settings
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--epochs',type=int,default=128);p.add_argument('--noise-m',type=float,default=0);p.add_argument('--edge-cases',action='store_true');a=p.parse_args();print(json.dumps(create(a.out,a.epochs,a.noise_m,a.edge_cases),indent=2))
