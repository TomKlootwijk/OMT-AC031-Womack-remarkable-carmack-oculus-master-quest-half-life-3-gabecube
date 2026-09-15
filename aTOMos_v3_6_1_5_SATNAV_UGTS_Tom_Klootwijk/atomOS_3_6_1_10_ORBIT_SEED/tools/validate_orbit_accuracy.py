#!/usr/bin/env python3
"""Measure frozen orbital models against strictly later external target samples.

No fitted model fields are modified. Thresholds are reported, never used to pick
or refit models. Distinguish forecast/reference error from integration agreement.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timedelta
import gzip
import glob
import hashlib
import json
import math
import re
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from orbit_dynamics import propagate, state_to_ecef, frame_matrix
from orbit_seed import digest as canonical_physical_digest

OBJECTS = {'G05':'MEO', 'C03':'GEO', 'C06':'IGSO', 'CHANDRA':'HEO'}
GPS_EPOCH = datetime(1980, 1, 6)
THRESHOLDS_M = [10., 100., 1000., 10000.]
INTERVAL_HOURS = [0., .25, 1., 6., 12., 24., 48., 72., 168.]
BENCHMARK_ROLES = {
    'retrospective_baseline': 'Retrospective baseline measurement; no claim of a previously uninspected confirmation set.',
    'reused_development': 'Reused development benchmark: previous prediction errors on these dates informed the revision. Past-only fitting does not make this an untouched confirmation set.',
    'independent_confirmation': 'Declared separate confirmation date. The selection procedure must be frozen before these prediction errors are read; this label records the evaluation design, not an automated proof of independence.',
}
IGB20_NOTICE = 'https://lists.igs.org/pipermail/igsmail/2024/008539.html'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite_array(value, shape, name):
    a=np.asarray(value,dtype=float)
    if a.shape != shape or not np.all(np.isfinite(a)):
        raise ValueError(f'{name}: require finite shape {shape}; got {a.shape}')
    return a


def parse_sp3(paths, satellite):
    """Independent fixed-column SP3 reader; chronological source first wins."""
    records={};duplicates=[];sources=[]
    for path in sorted(paths):
        text=gzip.decompress(path.read_bytes()).decode('ascii') if path.suffix=='.gz' else path.read_text('ascii')
        lines=text.splitlines(); timestamp=None; count=0
        if not lines or lines[0][0:2] not in ('#c','#d'):
            raise ValueError(f'Unsupported SP3 header: {path}')
        frame=lines[0][46:51].strip()
        time_lines=[l for l in lines if l.startswith('%c')]
        if not time_lines or time_lines[0][9:12] != 'GPS' or frame not in ('IGS20','IGb20'):
            raise ValueError(f'Require documented IGS20 or IGb20 / GPS SP3: {path}')
        if not any(l.strip()=='EOF' for l in lines):raise ValueError(f'Truncated SP3: {path}')
        for line in lines:
            if line.startswith('*'):
                f=line[1:].split()
                dt=datetime(*map(int,f[:5]))+timedelta(seconds=float(f[5]))
                timestamp=(dt-GPS_EPOCH).total_seconds()
            elif line.startswith('P'+satellite):
                if timestamp is None:raise ValueError('Position before SP3 epoch')
                xyz=finite_array([float(line[k:k+14])*1000 for k in (4,18,32)],(3,),'SP3 position')
                if not np.any(xyz):continue
                if np.linalg.norm(xyz)<6378137:raise ValueError('Reference position inside Earth')
                if len(line)>79 and line[79]=='P':raise ValueError('Predicted SP3 target samples cannot serve as the selected precise reference')
                item={'gpst_s':timestamp,'position':xyz,'frame':frame+'_ECEF','source':path.name,'maneuver_flag':len(line)>78 and line[78]=='M'}
                if timestamp in records:
                    duplicates.append({'gpst_s':timestamp,'later_source':path.name,'disagreement_m':float(np.linalg.norm(xyz-records[timestamp]['position']))})
                else:records[timestamp]=item
                count+=1
        sources.append({'file':path.name,'sha256':sha(path),'selected_records':count,'frame':frame})
    if not records:raise ValueError(f'No reference data for {satellite}')
    reference={'sources':sources,'duplicate_convention':'Earlier filename wins','duplicate_details':duplicates,
               'frames':sorted({s['frame'] for s in sources})}
    if 'IGb20' in reference['frames']:
        reference['frame_alignment']={'source':IGB20_NOTICE,'published_date':'2024-12-09',
            'convention':'IGS20 and IGb20 retain the same origin, scale and orientation; IGSMAIL-8543 specifies zero transformation parameters. No fitted alignment is applied.',
            'qualification':'IGb20 updates individual reference-station coordinates. Preserve source realization labels; product alignment effects are not independently bounded here.'}
    return [records[t] for t in sorted(records)], reference


def bulletin_metadata(path, epoch_gpst_s):
    text=path.read_text('ascii')
    match=re.search(r'^\s*(\d{1,2}\s+[A-Za-z]+\s+20\d{2})\s+Vol\.',text,re.MULTILINE)
    if not match:raise ValueError('Cannot identify IERS bulletin publication date')
    published=datetime.strptime(match.group(1),'%d %B %Y')
    cutoff_utc=GPS_EPOCH+timedelta(seconds=float(epoch_gpst_s)-18.)
    if published.date()>=cutoff_utc.date():
        raise ValueError('IERS publication date must precede the cutoff UTC date; same-day release time is not established')
    return {'file':str(path),'sha256':sha(path),'published_date':published.date().isoformat(),
            'cutoff_utc':cutoff_utc.isoformat()+'Z','published_before_cutoff':True}


def chronology(role, bulletin):
    return (BENCHMARK_ROLES[role]+' Target fitting uses only samples at/before the cutoff, but the provider products are retrospective and may use later observations internally. '
            +'This is not proof of real-time seed availability. The EOP bulletin was published '+bulletin['published_date']+'. Later target rows are validation only.')


def parse_chandra(path):
    """Convert calendar TDB to GPST with SOFA geocentric TDB-TT correction.

    Calendar labels preserve the exact five-minute grid; the printed decimal
    Julian dates round to microseconds and are consistency checked, not used to
    perturb that grid. Conversion is construction/validation only.
    """
    import erfa
    text=path.read_text('ascii')
    for required in ('Reference frame : ICRF','Output units    : KM-S','Output type     : GEOMETRIC cartesian states','$$SOE','$$EOE'):
        if required not in text:raise ValueError('Chandra header missing '+required)
    rows=[]; max_jd_rounding_s=0.
    for fields in csv.reader(text.split('$$SOE',1)[1].split('$$EOE',1)[0].strip().splitlines()):
        if len(fields)<8:raise ValueError('Truncated Horizons vector row')
        calendar=fields[1].strip()
        if not calendar.startswith('A.D. '):raise ValueError('Unsupported Horizons calendar')
        date=datetime.strptime(calendar[5:],'%Y-%b-%d %H:%M:%S.%f')
        tdb_seconds=(date-GPS_EPOCH).total_seconds()
        tdb_jd=2444244.5+tdb_seconds/86400.
        max_jd_rounding_s=max(max_jd_rounding_s,abs(float(fields[0])-tdb_jd)*86400.)
        tt_seconds=tdb_seconds
        for _ in range(3):
            tt_jd_offset=(2444244.5-2451545.)+tt_seconds/86400.
            correction=float(erfa.dtdb(2451545.,tt_jd_offset,0.,0.,0.,0.))
            tt_seconds=tdb_seconds-correction
        gpst=tt_seconds-51.184
        position=finite_array([float(x)*1000 for x in fields[2:5]],(3,),'Chandra position')
        velocity=finite_array([float(x)*1000 for x in fields[5:8]],(3,),'Chandra velocity')
        rows.append({'gpst_s':gpst,'position':position,'velocity':velocity,'frame':'ICRF_geocentric','source':path.name,'maneuver_flag':False})
    if len(rows)<2 or any(b['gpst_s']<=a['gpst_s'] for a,b in zip(rows,rows[1:])):
        raise ValueError('Chandra timestamps missing or unordered')
    if max_jd_rounding_s>.001:raise ValueError('Horizons calendar/JDTDB disagree')
    return rows, {'sources':[{'file':path.name,'sha256':sha(path),'selected_records':len(rows)}],
        'time_conversion':'Geocentric SOFA/ERFA dtdb iterative TDB->TT; GPST=TT-51.184s',
        'printed_JDTDB_max_rounding_s':max_jd_rounding_s,'reference_accuracy':'No state covariance or certified positional bound supplied',
        'frame_qualification':'Horizons geocentric ICRF axes compared with the model GCRS orientation; omitted geocentric relativistic coordinate distinctions are not certified by this test'}


def frame_approximation(model, times, states, bulletin_path):
    """Separate frozen-frame approximation from a published EOP forecast table.

    This comparison has no measured future EOP lookup and is not total frame
    uncertainty. The bulletin predates the seed cutoff.
    """
    import erfa
    publication=bulletin_metadata(bulletin_path,model['epoch_gpst_s'])
    rows=[]
    for line in bulletin_path.read_text('ascii').splitlines():
        fields=line.split()
        if len(fields)==7 and re.fullmatch(r'20[0-9]{2}',fields[0]):
            try:rows.append([float(x) for x in fields[3:7]])
            except ValueError:pass
    if len(rows)<2:raise ValueError('Missing published EOP forecast rows')
    table=np.asarray(rows);x=table[:,0]
    gpst=model['epoch_gpst_s']+times
    utc_mjd=44244.+(gpst-18.)/86400.
    if utc_mjd.min()<x.min() or utc_mjd.max()>x.max():raise ValueError('EOP forecast does not cover validation interval')
    xp=np.interp(utc_mjd,x,table[:,1])*np.pi/(180*3600)
    yp=np.interp(utc_mjd,x,table[:,2])*np.pi/(180*3600)
    dut=np.interp(utc_mjd,x,table[:,3])
    errors=[]
    for t,g,u,dx,dy,du,y in zip(times,gpst,utc_mjd,xp,yp,dut,states):
        exact=erfa.c2t06a(2400000.5,44244.+(g+51.184)/86400.,2400000.5,u+du/86400.,dx,dy)
        errors.append(float(np.linalg.norm((exact-frame_matrix(model,float(t)))@y[:3])))
    return {'comparison':'Embedded seed frame versus SOFA full Q and linearly interpolated daily predictions from IERS Bulletin A published '+publication['published_date'],
        'source':bulletin_path.name,'source_sha256':sha(bulletin_path),
        'publication':publication,
        'qualification':'Frame approximation disagreement only. Both use published predictions; disagreement with actual future Earth orientation and station uncertainty are not measured here.',
        'position_displacement':stats(errors)}


def stats(values):
    v=np.asarray(values,dtype=float)
    if not len(v):return {'count':0,'rms_m':None,'max_m':None,'median_m':None,'p95_m':None}
    if not np.all(np.isfinite(v)):raise ValueError('Nonfinite error statistics')
    return {'count':len(v),'rms_m':float(np.sqrt(np.mean(v*v))), 'max_m':float(v.max()),
        'median_m':float(np.median(v)),'p95_m':float(np.quantile(v,.95))}


def threshold_horizons(times, errors):
    out=[]
    for threshold in THRESHOLDS_M:
        indices=np.flatnonzero(errors>threshold)
        if len(indices):
            i=int(indices[0]);out.append({'threshold_m':threshold,'observed_exceedance':True,
                'first_sample_seconds':float(times[i]),'first_sample_error_m':float(errors[i]),
                'previous_sample_seconds':float(times[i-1]) if i else None,
                'previous_sample_error_m':float(errors[i-1]) if i else None,
                'qualification':'First sampled exceedance, not a proven first continuous crossing; errors can cross and return between samples'})
        else:out.append({'threshold_m':threshold,'observed_exceedance':False,
            'tested_through_seconds':float(times[-1]),'qualification':'No exceedance at tested samples; no continuous-time or later-time guarantee'})
    return out


def native_states(binary, model, times, backend):
    from orbit_native import NativeOrbit
    started=time.perf_counter()
    with NativeOrbit(binary,model,backend=backend) as worker:
        replies=worker.batch([float(t) for t in times])
    if len(replies)!=len(times):raise ValueError('Native reply count mismatch')
    out=[]
    for reply in replies:
        if not isinstance(reply,dict) or 'state_gcrs' not in reply:raise ValueError('Native reply lacks state_gcrs')
        if reply.get('status') not in (None,'OK','ok','success'):raise ValueError('Native query failed: '+str(reply))
        out.append(finite_array(reply['state_gcrs'],(6,),'native state'))
    return np.asarray(out),time.perf_counter()-started


def validate_one(object_id, model_path, data, binary, backend, out, python_checks,
                 chandra_reference=None, bulletin=None, benchmark_role='retrospective_baseline',
                 sp3_paths=None, procedure_manifest=None):
    model_bytes=model_path.read_bytes(); model_hash=hashlib.sha256(model_bytes).hexdigest()
    envelope=json.loads(model_bytes);model=envelope.get('model',envelope)
    epoch=float(model['epoch_gpst_s']); domain=finite_array(model['domain_s'],(2,),'domain')
    fit=envelope.get('fit',{})
    if not fit or not math.isfinite(float(fit.get('training_end_s',math.inf))) or float(fit['training_end_s'])>0:
        raise ValueError('Missing or invalid training cutoff metadata')
    if fit.get('future_target_rows_used') != 0:
        raise ValueError('Frozen-model contract requires zero future-target training rows')
    training_path=ROOT/fit.get('training_source','')
    if not training_path.is_file() or sha(training_path)!=fit.get('training_source_sha256'):
        raise ValueError('Training source provenance/hash mismatch')
    for source in fit.get('training_sources',[]):
        source_path=ROOT/source['path']
        if not source_path.is_file() or sha(source_path)!=source['sha256']:
            raise ValueError('Additional training source provenance/hash mismatch: '+str(source_path))
    if not domain[0]<=0<domain[1]:raise ValueError('Model has no future domain')
    bulletin=bulletin or data/'bulletina-xxxvii-052.txt'
    publication=bulletin_metadata(bulletin,epoch)
    if object_id=='CHANDRA': rows,reference=parse_chandra(chandra_reference or data/'HORIZONS_CHANDRA_20250101_20250109_ICRF_TDB.txt')
    else:rows,reference=parse_sp3(sp3_paths if sp3_paths is not None else list(data.glob('GBM0MGXRAP_*_ORB.SP3.gz')),object_id)
    # No target label at or before the seed/cutoff participates in the forecast curve.
    holdout=[r for r in rows if r['gpst_s']>epoch and r['gpst_s']-epoch<=domain[1]+1e-7]
    if len(holdout)<2:raise ValueError(f'{object_id}: missing strictly future holdout')
    times=np.array([r['gpst_s']-epoch for r in holdout]);times=np.minimum(times,domain[1])
    if not np.all(times>0) or np.any(np.diff(times)<=0):raise ValueError('Holdout ordering or cutoff failure')
    native_hash=sha(binary)
    states,elapsed=native_states(binary,model,times,backend)
    if sha(binary)!=native_hash:raise ValueError('Native binary changed during validation')
    reference_positions=np.array([r['position'] for r in holdout])
    if object_id=='CHANDRA':predicted=states[:,:3]
    else:predicted=np.array([state_to_ecef(model,float(t),y)[:3] for t,y in zip(times,states)])
    differences=predicted-reference_positions;errors=np.linalg.norm(differences,axis=1)
    if not np.all(np.isfinite(errors)):raise ValueError('Nonfinite holdout error')
    gaps=np.diff(times)
    summary={'object_id':object_id,'orbit_class':OBJECTS[object_id], 'model_file':model_path.name,
        'model_sha256':model_hash,'model_file_sha256':model_hash,
        'model_sha256_semantics':'Legacy alias for SHA256 of entire model JSON envelope file',
        'physical_model_sha256':canonical_physical_digest(model),
        'model_binding':{'physical_model_sha256':canonical_physical_digest(model),'method':'orbit_seed.digest(model)','scope':'Exact canonical physical model; report eligibility for a custom packed seed requires this digest to match'},
        'native_binary_sha256':native_hash,'cutoff_gpst_s':epoch,'selection_policy':'Frozen model; all reference samples strictly after seed epoch and inside declared model domain',
        'benchmark_role':benchmark_role,'chronology':chronology(benchmark_role,publication),
        'procedure_manifest':procedure_manifest,'earth_orientation_publication':publication,
        'excluded_samples_at_or_before_cutoff':sum(r['gpst_s']<=epoch for r in rows),
        'first_holdout_seconds':float(times[0]),'last_holdout_seconds':float(times[-1]),
        'maximum_sample_gap_seconds':float(gaps.max()), 'backend':backend,'native_batch_wall_seconds':elapsed,
        'position_error':stats(errors),'threshold_horizons':threshold_horizons(times,errors),
        'reference':reference,'training_metadata':envelope.get('fit',{}),'construction_metadata':envelope.get('construction',{}),
        'requested_horizon_nearest_samples':[
            {'requested_seconds':float(h*3600),'sample_seconds':float(times[int(np.argmin(abs(times-h*3600)))]),
             'sample_offset_seconds':float(times[int(np.argmin(abs(times-h*3600)))]-h*3600),
             'position_error_m':float(errors[int(np.argmin(abs(times-h*3600)))])}
            for h in (.25,1.,6.,24.,72.,168.)],
        'intervals':[],'frame_error_scope':'ECEF comparison includes declared seed EOP/frame approximations; independent EOP uncertainty is not removed from orbit error'}
    for lo,hi in zip(INTERVAL_HOURS,INTERVAL_HOURS[1:]):
        selection=(times>lo*3600)&(times<=hi*3600)
        summary['intervals'].append({'lower_open_hours':lo,'upper_closed_hours':hi,**stats(errors[selection])})
    if object_id=='CHANDRA':
        velocity_errors=np.linalg.norm(states[:,3:]-np.array([r['velocity'] for r in holdout]),axis=1)
        summary['velocity_error_m_s']={'rms':float(np.sqrt(np.mean(velocity_errors**2))),'max':float(velocity_errors.max())}
    summary['frame_approximation']=frame_approximation(model,times,states,bulletin)
    checks=np.unique(np.linspace(0,len(times)-1,min(python_checks,len(times)),dtype=int))
    if len(checks):
        reference_states=propagate(model,times[checks],method='DOP853')
        finite_array(reference_states,(len(checks),6),'DOP853 states')
        integration_error=np.linalg.norm(states[checks,:3]-reference_states[:,:3],axis=1)
        summary['native_vs_independent_DOP853']={'scope':'Same forces and initial seed; integration arithmetic comparison, not orbit truth',
            'method':'Adaptive SciPy DOP853, rtol2e-12,atol1e-6,maxstep300s',
            'samples':len(checks),'position_error':stats(integration_error),
            'times_seconds':times[checks].tolist(),'position_errors_m':integration_error.tolist()}
    if sha(model_path)!=model_hash:raise ValueError('Frozen model changed during validation')
    csv_path=out/(object_id+'_holdout.csv')
    with csv_path.open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['object','seconds_after_cutoff','gpst_s','reference_frame','reference_x_m','reference_y_m','reference_z_m','predicted_x_m','predicted_y_m','predicted_z_m','position_error_m','reference_source'])
        for t,r,p,e in zip(times,holdout,predicted,errors):writer.writerow([object_id,format(t,'.17g'),format(r['gpst_s'],'.17g'),r['frame'],*r['position'],*p,e,r['source']])
    summary['curve_file']=csv_path.name;summary['curve_sha256']=sha(csv_path)
    (out/(object_id+'_accuracy.json')).write_text(json.dumps(summary,indent=2,allow_nan=False))
    print(json.dumps({'object':object_id,'samples':len(times),'max_error_m':float(errors.max()),'complete':True}),flush=True)
    return summary,(times,errors)


def render_plot(curves,path,max_hours=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(11,7.5))
    fig.subplots_adjust(left=.08,right=.98,bottom=.09,top=.90,hspace=.44,wspace=.25)
    for ax,object_id in zip(axes.flat,OBJECTS):
        if object_id not in curves:ax.set_visible(False);continue
        times,errors=curves[object_id]
        if max_hours is not None:
            selected=times<=max_hours*3600;times,errors=times[selected],errors[selected]
        # A missing reference arc must remain visibly blank, not a joined line.
        plot_times=times.copy();plot_errors=np.maximum(errors,1e-8)
        if len(times)>2:
            gaps=np.flatnonzero(np.diff(times)>1.5*np.median(np.diff(times)))+1
            plot_times=np.insert(plot_times,gaps,np.nan)
            plot_errors=np.insert(plot_errors,gaps,np.nan)
        ax.semilogy(plot_times/3600,plot_errors,color='#17628c',linewidth=1.3)
        for threshold in THRESHOLDS_M:ax.axhline(threshold,color='#999999',linewidth=.65,alpha=.6,linestyle=':')
        ax.set(title=f'{object_id} / {OBJECTS[object_id]}',xlabel='Hours after frozen seed cutoff',ylabel='Position discrepancy (m)')
        ax.grid(alpha=.18,which='both');ax.set_xlim(left=0)
        ax.tick_params(labelsize=9);ax.title.set_fontsize(11);ax.xaxis.label.set_fontsize(10);ax.yaxis.label.set_fontsize(10)
    fig.suptitle('Frozen-seed forecast versus later external trajectory samples',fontsize=13,y=.98)
    fig.savefig(path,dpi=180);fig.savefig(path.with_suffix('.pdf'));plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models',type=Path,default=ROOT/'examples/orbit/models')
    parser.add_argument('--data',type=Path,default=ROOT/'source/orbit_data')
    parser.add_argument('--chandra-reference',type=Path,help='Explicit Horizons Chandra reference file; default retains the January baseline filename under --data')
    parser.add_argument('--bulletin',type=Path,help='Explicit IERS Bulletin A text; its publication date must precede each model cutoff')
    parser.add_argument('--sp3-source',nargs=2,action='append',metavar=('OBJECT','PATH_GLOB'),default=[],help='Per-object SP3 override, e.g. C03 ".../holdout_wum/WUM*_ORB.SP3.gz"')
    parser.add_argument('--benchmark-role',choices=BENCHMARK_ROLES,default='retrospective_baseline')
    parser.add_argument('--procedure-manifest',type=Path,help='Optional already-frozen selection-procedure manifest to bind into the report by SHA256')
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--backend',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--objects',nargs='+',choices=OBJECTS,default=list(OBJECTS))
    parser.add_argument('--python-checks',type=int,default=9)
    args=parser.parse_args()
    if args.python_checks<1:parser.error('--python-checks must be positive')
    if len(set(args.objects))!=len(args.objects):parser.error('Duplicate objects')
    if not args.binary.is_file():parser.error('Native binary missing')
    if args.out.exists():parser.error('Output directory must be new')
    sp3_overrides={}
    for sid,pattern in args.sp3_source:
        if sid not in OBJECTS or sid=='CHANDRA':parser.error('--sp3-source object must be G05, C03 or C06')
        if sid in sp3_overrides:parser.error('Duplicate SP3 source override for '+sid)
        sp3_overrides[sid]=[Path(p) for p in sorted(glob.glob(pattern))]
        if not sp3_overrides[sid]:parser.error('SP3 source pattern matches no files: '+pattern)
    procedure=None
    if args.procedure_manifest:
        if not args.procedure_manifest.is_file():parser.error('Procedure manifest missing')
        procedure={'file':str(args.procedure_manifest),'sha256':sha(args.procedure_manifest)}
    paths={sid:args.models/(sid+'.json') for sid in args.objects}
    for path in paths.values():
        if not path.is_file():parser.error('Missing frozen model '+str(path))
    args.out.mkdir(parents=True)
    reports=[];curves={}
    try:
        for sid,path in paths.items():
            report,curve=validate_one(sid,path,args.data,args.binary,args.backend,args.out,args.python_checks,
                args.chandra_reference,args.bulletin,args.benchmark_role,sp3_overrides.get(sid),procedure)
            reports.append(report);curves[sid]=curve
        render_plot(curves,args.out/'forecast_error_curves.png')
        render_plot(curves,args.out/'forecast_error_first_day.png',max_hours=24.)
        with (args.out/'horizon_samples.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['object','requested_seconds','sample_seconds','sample_offset_seconds','position_error_m'])
            for obj in reports:
                for row in obj['requested_horizon_nearest_samples']:writer.writerow([obj['object_id'],row['requested_seconds'],row['sample_seconds'],row['sample_offset_seconds'],row['position_error_m']])
        with (args.out/'sampled_threshold_horizons.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['object','threshold_m','observed_exceedance','first_sample_seconds','previous_sample_seconds','first_sample_error_m','tested_through_seconds'])
            for obj in reports:
                for row in obj['threshold_horizons']:writer.writerow([obj['object_id'],row['threshold_m'],row['observed_exceedance'],row.get('first_sample_seconds'),row.get('previous_sample_seconds'),row.get('first_sample_error_m'),obj['last_holdout_seconds']])
        with (args.out/'interval_statistics.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['object','lower_open_hours','upper_closed_hours','count','rms_m','max_m','median_m','p95_m'])
            for obj in reports:
                for row in obj['intervals']:writer.writerow([obj['object_id'],*[row[k] for k in ('lower_open_hours','upper_closed_hours','count','rms_m','max_m','median_m','p95_m')]])
        report={'schema':'ORBIT-FORECAST-VALIDATION-R1','status':'measured','objects_requested':args.objects,
            'complete_four_class_scope':set(args.objects)==set(OBJECTS),'backend':args.backend,
            'native_binary_sha256':sha(args.binary),'reference_product_disagreement_file':str(args.data/'reference_data_inspection.json') if (args.data/'reference_data_inspection.json').is_file() else None,
            'thresholds_m':THRESHOLDS_M,'accuracy_thresholds_are_pass_criteria':False,
            'qualification':'Descriptive sampled error statistics for these objects and dates. Samples are temporally correlated. No confidence interval, certified uncertainty, continuous-time bound, future operational accuracy or successful threshold horizon is inferred.',
            'benchmark_role':args.benchmark_role,'chronology':chronology(args.benchmark_role,reports[0]['earth_orientation_publication']),
            'procedure_manifest':procedure,
            'objects':reports}
        if args.procedure_manifest and sha(args.procedure_manifest)!=procedure['sha256']:
            raise ValueError('Frozen selection-procedure manifest changed during validation')
        summary_bytes=json.dumps(report,indent=2,allow_nan=False)
        (args.out/'accuracy_summary.json').write_text(summary_bytes,encoding='utf8')
        (args.out/'summary.json').write_text(summary_bytes,encoding='utf8')
    except Exception as exc:
        (args.out/'failure.json').write_text(json.dumps({'status':'failed','error':str(exc),'objects_completed':[r['object_id'] for r in reports]},indent=2))
        raise


if __name__=='__main__':main()
