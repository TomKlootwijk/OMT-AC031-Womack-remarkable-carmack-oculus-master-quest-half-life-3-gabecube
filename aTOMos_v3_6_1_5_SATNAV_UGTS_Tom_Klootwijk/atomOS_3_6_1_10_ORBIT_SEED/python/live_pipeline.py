"""Raw GPS code -> updated broadcast corrections -> persistent native position.

Reference coordinates are never read as a seed or as a measurement. Warm starts
use only this worker's last complete position. Full outer-loop evidence is kept.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict
import csv, json, math, statistics, time
from pathlib import Path
from live_gnss import prepare_epoch

def write_json(path, data):
    Path(path).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')

class LivePipeline:
    def __init__(self,worker,out,ephemerides=(),iono_alpha=None,iono_beta=None,
                 metadata=None,max_outer=8,min_elevation_deg=10.):
        if not isinstance(max_outer,int) or isinstance(max_outer,bool) or max_outer<1:
            raise ValueError('max_outer must be a positive integer')
        self.worker=worker;self.out=Path(out)
        self.out.mkdir(parents=True,exist_ok=False)
        self.ephemerides=list(ephemerides);self.alpha=iono_alpha;self.beta=iono_beta
        self.max_outer=max_outer;self.min_elevation=min_elevation_deg
        self.seed=[0.,0.,0.,0.];self.last_time=None;self.last_station=None
        self.counts=Counter();self.latencies=[];self.fixes=[];self.closed=False
        self.metadata=dict(metadata or {},version='3.6.1.8',profile='LIVE-GPS-L1-R1',
            initial_seed_ecef_clock_m=list(self.seed),reference_coordinates_used=False,
            worker_command=worker.command,worker_pid=worker.process.pid,
            worker_sha256=worker.binary_sha256,worker_greeting=worker.ready,
            correction_outer_limit=max_outer,correction_tolerance_m=.001,
            iono_alpha=iono_alpha,iono_beta=iono_beta,min_elevation_deg=min_elevation_deg)
        write_json(self.out/'run_metadata.json',self.metadata)
        self.journal=(self.out/'trace.jsonl').open('x',encoding='utf-8')
        self.events=(self.out/'events.jsonl').open('x',encoding='utf-8')
        self.csv_folder=self.out/'prepared';self.csv_folder.mkdir()
        self.epoch_file=(self.csv_folder/'epochs.csv').open('x',newline='',encoding='ascii')
        self.obs_file=(self.csv_folder/'observations.csv').open('x',newline='',encoding='ascii')
        self.epoch_csv=csv.writer(self.epoch_file);self.obs_csv=csv.writer(self.obs_file)
        self.epoch_csv.writerow(['epoch_id','t_rx_gpst_s','x0_m','y0_m','z0_m','b0_m','asa_mask','na_mask','boundary_mask'])
        self.obs_csv.writerow(['epoch_id','channel','satellite_id','sx_rx_m','sy_rx_m','sz_rx_m','code_m','add_correction_m','sigma_m','ready'])
        write_json(self.csv_folder/'profile.json',dict(version='3.6.1.8',profile='LIVE-GPS-L1-R1',
            observation_origin=self.metadata.get('source_kind'),geometry='emission_satellites_in_reception_ECEF',
            correction='c*satellite_L1_clock-ionosphere-troposphere',time_scale='GPST',
            provenance='../run_metadata.json',scope='real decoded GPS observations; per-epoch final outer-loop inputs'))

    def event(self,event):
        self.events.write(json.dumps(event,allow_nan=False)+'\n');self.events.flush()

    def add_ephemeris(self,eph):
        # Bound a long-running stream to recent records, preserving new IOD values.
        key=(eph.prn,eph.toe,eph.toc,eph.iode,eph.iodc)
        self.ephemerides=[e for e in self.ephemerides if (e.prn,e.toe,e.toc,e.iode,e.iodc)!=key and e.toe>=eph.toe-86400]
        self.ephemerides.append(eph)

    def process(self,epoch,reception_gpst_s=None):
        started=time.perf_counter();epoch_id=sum(self.counts.values())
        station=epoch.source_metadata.get('station_id')
        if station is not None and self.last_station is not None and station!=self.last_station:
            self.seed=[0.,0.,0.,0.];self.last_time=None
            self.event(dict(type='receiver_change',old_station=self.last_station,new_station=station,seed_reset=True))
        if station is not None:self.last_station=station
        if self.last_time is not None and epoch.time_gpst_s<=self.last_time:
            self.counts['STALE_EPOCH']+=1
            result=dict(epoch_id=epoch_id,time_gpst_s=epoch.time_gpst_s,status='STALE_EPOCH',position_available=False)
            self.event(result);return result
        self.last_time=epoch.time_gpst_s
        seed=list(self.seed);passes=[];outer_status='OUTER_LIMIT';position_available=False
        for outer in range(self.max_outer):
            prepared=prepare_epoch(epoch,self.ephemerides,seed[:3],seed[3],self.alpha,self.beta,
                                   min_elevation_deg=self.min_elevation)
            solution=self.worker.solve(epoch_id,epoch.time_gpst_s,seed,prepared['observations'])
            item=dict(outer=outer,prepared=prepared,solution=solution);passes.append(item)
            if solution['status']!='CONVERGED':outer_status=solution['status'];break
            next_seed=solution['state']
            position_delta=math.dist(seed[:3],next_seed[:3]);clock_delta=abs(seed[3]-next_seed[3])
            item.update(position_delta_m=position_delta,clock_delta_m=clock_delta)
            if prepared['model']['receiver_geometry_initialized'] and max(position_delta,clock_delta)<.001:
                outer_status='CONVERGED';position_available=True;self.seed=list(next_seed);break
            seed=list(next_seed)
        latency_ms=(time.perf_counter()-started)*1000
        self.latencies.append(latency_ms);self.counts[outer_status]+=1
        final=passes[-1];solution=final['solution'];prepared=final['prepared']
        completed_unix=time.time()
        result=dict(epoch_id=epoch_id,time_gpst_s=epoch.time_gpst_s,status=outer_status,
            position_available=position_available,fit=solution['fit'],used=solution['used'],
            state_ecef_clock_m=solution['state'] if position_available else None,
            estimated_reception_gpst_s=epoch.time_gpst_s-solution['state'][3]/299792458. if position_available else None,
            rms_m=solution['rms_m'],outer_passes=len(passes),processing_ms=latency_ms,
            reception_gpst_s=reception_gpst_s,solution_emitted_utc_unix_s=completed_unix,
            observation_to_reception_s=None if reception_gpst_s is None else reception_gpst_s-epoch.time_gpst_s,
            native_status=solution['status'],native_backend=solution['backend'])
        self.journal.write(json.dumps(dict(result=result,raw_epoch=asdict(epoch),passes=passes),allow_nan=False)+'\n');self.journal.flush()
        self.epoch_csv.writerow([epoch_id,epoch.time_gpst_s,*prepared['receiver_seed_ecef_m'],prepared['receiver_seed_clock_m'],4294967295,4294967295,0])
        for o in prepared['observations']:
            self.obs_csv.writerow([epoch_id,*[o[k] for k in ('channel','satellite_id','sx_rx_m','sy_rx_m','sz_rx_m','code_m','add_correction_m','sigma_m','ready')]])
        self.epoch_file.flush();self.obs_file.flush()
        if position_available:self.fixes.append(result)
        return result

    def close(self,extra=None):
        if self.closed:return
        self.closed=True
        for stream in (self.journal,self.events,self.epoch_file,self.obs_file):stream.close()
        summary=dict(self.metadata,epoch_status_counts=dict(self.counts),epochs=sum(self.counts.values()),
            positions=len(self.fixes),processing_ms=dict(median=statistics.median(self.latencies) if self.latencies else None,
                p95=sorted(self.latencies)[int(.95*(len(self.latencies)-1))] if self.latencies else None,
                maximum=max(self.latencies,default=None),scope='completed-epoch correction preparation, native worker, and response parsing; excludes transport and RTCM parsing'),
            first_position=self.fixes[0] if self.fixes else None,last_position=self.fixes[-1] if self.fixes else None)
        if extra:summary.update(extra)
        write_json(self.out/'summary.json',summary)
        return summary
