#!/usr/bin/env python3
"""Execute GPS L1 positioning from RINEX, captured RTCM, or a live Internet feed."""
from pathlib import Path
import argparse,hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
from live_gnss import read_rinex_nav,iter_rinex_obs
from live_native import NativeSolver
from live_pipeline import LivePipeline
from live_rtcm import RTCMDecoder,ephemeris_from_event,epoch_from_event,capture,unix_to_gpst,redact_url

def fingerprint(path):
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--backend',choices=['cpu','cuda'],default='cpu')
    p.add_argument('--out',type=Path,required=True)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--rinex-obs',type=Path);source.add_argument('--rtcm',type=Path);source.add_argument('--url')
    p.add_argument('--nav',type=Path,help='GPS RINEX ephemeris for RINEX observations only')
    p.add_argument('--iono-nav',type=Path,help='RINEX header GPSA/B only; its ephemerides are NOT loaded')
    p.add_argument('--reference-gpst',type=float,help='full GPST second for archived RTCM week resolution')
    p.add_argument('--seconds',type=float,default=180);p.add_argument('--max-bytes',type=int,default=8*1024*1024)
    p.add_argument('--timeout',type=float,default=10);p.add_argument('--reconnects',type=int,default=2)
    p.add_argument('--gps-utc-offset',type=int,default=18);p.add_argument('--quiet',action='store_true')
    a=p.parse_args()
    if a.rinex_obs and not a.nav:p.error('--rinex-obs requires --nav')
    if not a.rinex_obs and a.nav:p.error('--nav is only for RINEX; RTCM positioning uses streamed1019')
    if a.rtcm and a.reference_gpst is None:p.error('--rtcm requires --reference-gpst')
    nav=read_rinex_nav(a.nav) if a.nav else None
    iono=read_rinex_nav(a.iono_nav) if a.iono_nav else nav
    metadata=dict(source_kind='live_internet_rtcm' if a.url else 'recorded_rtcm' if a.rtcm else 'recorded_rinex',
        implementation={name:fingerprint(ROOT/name) for name in ('tools/live_satnav.py','python/live_pipeline.py','python/live_native.py','python/live_gnss.py','python/live_rtcm.py')},
        inputs={name:fingerprint(value) for name,value in [('rinex_obs',a.rinex_obs),('nav',a.nav),('iono_nav',a.iono_nav),('rtcm',a.rtcm)] if value},
        source_url=redact_url(a.url) if a.url else None,gps_utc_offset_s=a.gps_utc_offset,
        measurement_origin='remote_GNSS_receiver',ephemeris_origin='RINEX_NAV' if nav else 'streamed_RTCM1019',
        iono_source_role='GPSA/B_header_only' if a.iono_nav else 'RINEX_NAV_header' if nav else 'explicit_model_fallback',
        laptop_position_measured=False)
    with NativeSolver(a.binary,a.backend) as worker:
        pipeline=LivePipeline(worker,a.out,nav.ephemerides if nav else (),iono.iono_alpha if iono else None,iono.iono_beta if iono else None,metadata)
        count=0;extra={};decoder=None
        def emit_fix(epoch,reception=None):
            nonlocal count
            result=pipeline.process(epoch,reception);count+=1
            if not a.quiet and (count<=3 or count%30==0):print(json.dumps(result,allow_nan=False),flush=True)
        def events(items):
            for event in items:
                pipeline.event(event)
                if event['type']=='ephemeris':
                    try:pipeline.add_ephemeris(ephemeris_from_event(event))
                    except ValueError as exc:pipeline.event(dict(type='ephemeris_rejected',reason=str(exc)))
                elif event['type']=='epoch':emit_fix(epoch_from_event(event),event['reception_gpst_s'] if a.url else None)
        try:
            if a.rinex_obs:
                for epoch in iter_rinex_obs(a.rinex_obs):emit_fix(epoch)
            else:
                reference=a.reference_gpst if a.rtcm else unix_to_gpst(time.time(),a.gps_utc_offset)
                decoder=RTCMDecoder(reference,gps_utc_offset_s=a.gps_utc_offset)
                if a.rtcm:
                    with a.rtcm.open('rb') as stream:
                        while data:=stream.read(4096):events(decoder.feed(data))
                else:
                    def transport_event(event):
                        pipeline.event(event)
                        if event['type']=='reconnecting':events(decoder.reset('transport_reconnect'))
                    extra['capture']=capture(a.url,a.out/'capture.rtcm3',a.seconds,a.max_bytes,a.timeout,a.reconnects,a.gps_utc_offset,
                        on_chunk=lambda data,gpst:events(decoder.feed(data,gpst)),on_event=transport_event)
                events(decoder.finish());extra['rtcm_message_counts']=dict(decoder.counts)
        except BaseException as exc:
            extra['termination_error']=type(exc).__name__;pipeline.close(extra);raise
        summary=pipeline.close(extra)
    print(json.dumps(summary,indent=2,allow_nan=False))
    return 0 if summary['positions'] else 2

if __name__=='__main__':raise SystemExit(main())
