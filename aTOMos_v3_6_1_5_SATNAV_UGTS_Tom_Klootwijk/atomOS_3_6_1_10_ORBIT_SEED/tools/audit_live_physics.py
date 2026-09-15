#!/usr/bin/env python3
"""Persist physical-model and native-inner-solve audits of closed live runs.

Reads traces; does not change receiver data, source code, or solved positions.
The report distinguishes executed algebra checks from source inspection.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from live_gnss import C
from compare_live_reference import solve_numpy


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit_run(folder):
    folder=Path(folder)
    if not (folder/'summary.json').exists():raise ValueError(f'run has not closed: {folder}')
    summary=json.loads((folder/'summary.json').read_text())
    trace=folder/'trace.jsonl';raw_bytes=trace.read_bytes()
    records=[json.loads(s) for s in raw_bytes.decode().splitlines() if s.strip()]
    events=[json.loads(s) for s in (folder/'events.jsonl').read_text().splitlines() if s.strip()]
    received_ephemerides={(e['ephemeris']['prn'],e['ephemeris']['toe'],e['ephemeris']['toc'],e['ephemeris']['iode'],e['ephemeris']['iodc'])
                         for e in events if e['type']=='ephemeris'}
    available_before_epoch={};known=set()
    for event in events:
        if event['type']=='ephemeris':
            e=event['ephemeris'];known.add((e['prn'],e['toe'],e['toc'],e['iode'],e['iodc']))
        elif event['type']=='epoch':
            available_before_epoch[(event['station_id'],event['time_gpst_s'])]=set(known)
    failures=[];counts=Counter();differences=[];last=[0.]*4;last_station=None
    def check(condition,kind,epoch_id,detail=None):
        counts[kind]+=1
        if not condition:failures.append(dict(check=kind,epoch_id=epoch_id,detail=detail))
    for record in records:
        raw=record['raw_epoch'];result=record['result'];epoch_id=result['epoch_id']
        station=raw['source_metadata'].get('station_id')
        if station is not None and last_station is not None and station!=last_station:last=[0.]*4
        if station is not None:last_station=station
        initial=record['passes'][0]['prepared'];seed=[*initial['receiver_seed_ecef_m'],initial['receiver_seed_clock_m']]
        check(seed==last,'cold_or_prior_valid_seed',epoch_id)
        source={o['prn']:o['pseudorange_m'] for o in raw['observations']}
        check('ecef_arp_m' not in raw['source_metadata'],'epoch_has_no_arp_coordinate',epoch_id)
        for item in record['passes']:
            p=item['prepared'];solution=item['solution'];current=[*p['receiver_seed_ecef_m'],p['receiver_seed_clock_m']]
            check(current==seed,'outer_seed_continuity',epoch_id)
            for row in p['observations']:
                d=row['diagnostics'];prn=d['prn']
                check(row['code_m']==source[prn],'original_code_unchanged',epoch_id,prn)
                check(row['add_correction_m']==C*d['clock_l1_s']-d['iono_m']-d['tropo_m'],'single_additive_correction',epoch_id,prn)
                check(d['clock_l1_s']==d['clock_polynomial_s']+d['relativity_s']-d['tgd_s'],'l1_clock_relativity_tgd_sign',epoch_id,prn)
                key=(prn,d['ephemeris_toe_gpst_s'],d['ephemeris_toc_gpst_s'],d['iode'],d['iodc'])
                check(d['ephemeris_source']=='RTCM1019' and key in received_ephemerides,'ephemeris_matches_received_1019_issue',epoch_id,prn)
                check(key in available_before_epoch.get((station,raw['time_gpst_s']),set()),'ephemeris_received_before_epoch',epoch_id,prn)
                check(d['health']==0 and d['iode']==(d['iodc']&255),'health_issue_consistency',epoch_id,prn)
            if solution['status']=='CONVERGED':
                independent=solve_numpy(p,current)
                difference=float(max(abs(independent-np.array(solution['state']))));differences.append(difference)
                check(difference<1e-5,'numpy_native_inner_state',epoch_id,difference)
            seed=solution['state']
        if result['position_available']:
            last=result['state_ecef_clock_m'];counts['valid_positions']+=1
            check(result['estimated_reception_gpst_s']==raw['time_gpst_s']-last[3]/C,'estimated_reception_time',epoch_id)
            check(all(math.isfinite(v) for v in last),'finite_published_state',epoch_id)
            final=record['passes'][-1]
            check(final['prepared']['model']['receiver_geometry_initialized'],'initialized_published_geometry',epoch_id)
            check(max(final['position_delta_m'],final['clock_delta_m'])<.001,'converged_outer_corrections',epoch_id)
    return dict(status='passed' if records and not failures else 'failed',run=str(folder),
        source_kind=summary['source_kind'],backend=summary['worker_greeting']['backend'],
        observation_session_utc_date=datetime.fromtimestamp(summary['capture']['started_utc_unix_s'],timezone.utc).date().isoformat(),
        trace_sha256=hashlib.sha256(raw_bytes).hexdigest(),events_sha256=sha(folder/'events.jsonl'),
        summary_sha256=sha(folder/'summary.json'),capture_sha256=sha(folder/'capture.rtcm3'),
        worker_sha256=summary['worker_sha256'],epochs=len(records),
        native_epoch_statuses=dict(Counter(r['result']['status'] for r in records)),counts=dict(counts),
        numpy_native_max_component_difference_m=max(differences,default=None),
        numpy_native_component_tolerance_m=1e-5,failures=failures)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,action='append',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();runs=[audit_run(path) for path in args.run]
    report=dict(status='passed' if all(r['status']=='passed' for r in runs) else 'failed',
        title='LIVE-R1 physical-model audit: 14 September 2026 UTC receiver sessions',
        date_basis='Receiver acquisition date in UTC; host local calendar may be 15 September.',
        audited_utc=datetime.now(timezone.utc).isoformat(),
        scope='Executed trace algebra, original-code retention, cold/warm/outer state continuity, received ephemeris issue membership and arrival before the epoch, corrected time, and independent NumPy native-inner solves.',
        formulations=dict(corrected_code_m='P + c*(clock_polynomial_s + relativity_s - TGD_s) - ionosphere_m - troposphere_m',
            estimated_reception_gpst_s='raw_receiver_time_tag_gpst_s - receiver_clock_bias_m / 299792458',
            outer_convergence_m='initialized_receiver_geometry and max(norm(delta_xyz),abs(delta_clock_m)) < 0.001',
            native_independence='numpy.linalg.lstsq on whitened geometry and corrected code; no native QR reuse'),
        source_inspection=dict(reference_arp='RTCM1005/1006 events are journaled; tools/live_satnav.py dispatches only ephemeris and epoch events into the estimator. No station coordinate is read by LivePipeline.',
            initialization='LivePipeline initializes all four receiver state values to zero and warm-starts only from its last valid native result.',
            ionosphere_file='RTCM mode loads GPSA/GPSB coefficients only; its navigation-file ephemerides are not passed to LivePipeline.',
            document_consistency='docs/live.tex and docs/live_equations.tex were checked against the current physical signs, units, correction feedback and receiver-time convention.',
            sha256={name:sha(ROOT/name) for name in ('python/live_gnss.py','python/live_pipeline.py','python/live_rtcm.py','tools/live_satnav.py','docs/live.tex','docs/live_equations.tex')}),
        notes=['An ARP is stream metadata, not independently surveyed truth.','This audit does not establish moving-receiver field accuracy or calibrated host/network latency.'],runs=runs)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=report['status'],runs=[{k:r[k] for k in ('run','backend','epochs','counts','numpy_native_max_component_difference_m','failures')} for r in runs]),indent=2))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
