from pathlib import Path
import gzip,json,math,csv,io,datetime,sys,hashlib
root=Path('atomOS_3_6_1_9_ORBIT_SEED/source/orbit_data/confirmation_20250202');sys.path.insert(0,'tmp/orbit_model_deps');import erfa
origin=datetime.datetime(1980,1,6);epoch=1422489600.0;summary=dict(schema='ORBIT-CONFIRMATION-COVERAGE-1',cutoff_gpst_seconds=epoch,prediction_errors_computed=False,model_fitting_performed=False,coverage_only=True,files={},targets={})
for role in ('training','holdout','holdout_wum'):
 unions={sat:set() for sat in ('G05','C03','C06')}
 for p in sorted((root/role).glob('*_ORB.SP3.gz')):
  lines=gzip.decompress(p.read_bytes()).decode('ascii').splitlines();frame=lines[0][46:51].strip();assert frame in ('IGS20','IGb20');assert 'GPS' in next(x for x in lines if x.startswith('%c'));info=dict(frame=frame,time_system='GPS',targets={})
  all_epochs=[];counts={sat:0 for sat in unions};flags={sat:0 for sat in unions}
  for line in lines:
   if line.startswith('*'):
    x=line[1:].split();dt=datetime.datetime(*map(int,x[:5]),int(float(x[5])));t=(dt-origin).total_seconds();all_epochs.append(t)
   if line.startswith(('PG05','PC03','PC06')):
    sat=line[1:4];xyz=[float(line[a:a+14]) for a in (4,18,32)];assert all(math.isfinite(x) for x in xyz) and not all(x==0 for x in xyz);counts[sat]+=1;flags[sat]+=int(len(line)>79 and line[79]=='P')
    if (role=='training' and epoch-8*86400<=t<=epoch) or (role in ('holdout','holdout_wum') and epoch<t<=epoch+7*86400):unions[sat].add(t)
  assert len(all_epochs) in (288,289) and all(all_epochs[i+1]-all_epochs[i]==300 for i in range(len(all_epochs)-1))
  for sat in unions:
   assert counts[sat] in (0,len(all_epochs)) and flags[sat]==0
   if role=='training' or sat in ('G05','C06'):assert counts[sat]==len(all_epochs)
   info['targets'][sat]=dict(position_records=counts[sat],position_prediction_flags=flags[sat])
  info.update(raw_epoch_count=len(all_epochs),first_gpst_seconds=all_epochs[0],last_gpst_seconds=all_epochs[-1]);summary['files'][p.relative_to(root).as_posix()]=info
 for sat,times in unions.items():
  t=sorted(times);expected=2305 if role=='training' else 2016
  if role=='training' or (role=='holdout' and sat in ('G05','C06')):assert len(t)==expected and all(t[i+1]-t[i]==300 for i in range(len(t)-1))
  gaps=[dict(previous_t_s=a-epoch,next_t_s=b-epoch,gap_s=b-a) for a,b in zip(t,t[1:]) if b-a>300]
  summary['targets'].setdefault(sat,{})[role]=dict(unique_eligible_epochs=len(t),expected_grid_epochs=expected,missing_grid_epochs=expected-len(t),first_t_s=t[0]-epoch,last_t_s=t[-1]-epoch,maximum_gap_s=max(b-a for a,b in zip(t,t[1:])),gaps=gaps)
def read_hz(p):
 txt=p.read_text(encoding='ascii');raw=txt.split('$$SOE')[1].split('$$EOE')[0].strip();rows=list(csv.reader(io.StringIO(raw)));times=[]
 for row in rows:
  dt=datetime.datetime.strptime(row[1].strip().removeprefix('A.D. '),'%Y-%b-%d %H:%M:%S.%f');assert all(math.isfinite(float(x)) for x in row[2:8]);jd=2444244.5+(dt-origin).total_seconds()/86400;tdb_tt=erfa.dtdb(jd,0.0,0.0,0.0,0.0,0.0);times.append((dt-origin).total_seconds()-51.184-tdb_tt)
 return txt,rows,times
for role in ('training','holdout','forcing'):
 for p in sorted((root/role).glob('HORIZONS*.txt')):
  txt,rows,times=read_hz(p);assert all(abs(times[i+1]-times[i]-300)<1e-4 for i in range(len(times)-1))
  info=dict(raw_epoch_count=len(rows),frame='Earth-centered ICRF geometric',source_time_scale='TDB',position_units='km',velocity_units='km/s',first_calendar_tdb=rows[0][1].strip(),last_calendar_tdb=rows[-1][1].strip(),first_t_s=times[0]-epoch,last_t_s=times[-1]-epoch)
  if role!='forcing':
   eligible=[t for t in times if ((epoch-8*86400<=t<=epoch) if role=='training' else (epoch<t<=epoch+7*86400))];assert len(eligible)==(2304 if role=='training' else 2016);assert (max(times)<epoch if role=='training' else min(times)>epoch)
   summary['targets'].setdefault('CHANDRA',{})[role]=dict(unique_eligible_epochs=len(eligible),first_t_s=eligible[0]-epoch,last_t_s=eligible[-1]-epoch)
  else:assert len(rows)==4897
  summary['files'][p.relative_to(root).as_posix()]=info
p=root/'eop'/'bulletina-xxxviii-005.txt';text=p.read_text(encoding='ascii');eop=[]
for line in text.splitlines():
 f=line.split()
 try:
  if len(f)==7 and f[0]=='2025':
   year,month,day,mjd=map(int,f[:4]);xp,yp,dut1=map(float,f[4:]);kind='prediction';sx=sy=.00068*(mjd-60705)**.8;st=.00025*(mjd-60705)**.75
  elif len(f)==10 and f[0]=='25' and f[1]=='1':
   year=2025;month,day,mjd=map(int,f[1:4]);xp,sx,yp,sy,dut1,st=map(float,f[4:]);kind='rapid_combination'
  else:continue
  if 60699<=mjd<=60716:eop.append(dict(utc_date=f'{year:04d}-{month:02d}-{day:02d}',mjd_utc=mjd,xp_arcsec=xp,yp_arcsec=yp,dut1_s=dut1,kind=kind,xp_error_arcsec=sx,yp_error_arcsec=sy,dut1_error_s=st))
 except ValueError:continue
assert len(eop)==18 and [r['mjd_utc'] for r in eop]==list(range(60699,60717))
eopinfo=dict(schema='IERS-BULLETINA-20250130-EOP-TABLE-1',published_date='2025-01-30',source='bulletina-xxxviii-005.txt',source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source_url='https://datacenter.iers.org/data/6/bulletina-xxxviii-005.txt',time_scale='UTC MJD',prediction_uncertainties='Sxy=0.00068*(MJD-60705)^0.80 arcsec; St=0.00025*(MJD-60705)^0.75 s; estimates, not guaranteed bounds',lod_note='No observed LOD column; derivatives from DUT1 must be identified as derived.',rows=eop)
(root/'eop'/'published_eop_20250124_20250210.json').write_text(json.dumps(eopinfo,indent=2)+'\n',encoding='utf-8');(root/'coverage.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary['targets'],indent=2));print('Published-before-cutoff EOP rows:',len(eop))
manifest=json.loads((root/'download_manifest.json').read_text(encoding='utf-8'));manifest['derived_files']=[dict(file=name,bytes=(root/name).stat().st_size,sha256=hashlib.sha256((root/name).read_bytes()).hexdigest()) for name in ('coverage.json','eop/published_eop_20250124_20250210.json')]
for row in manifest['files']+manifest['derived_files']:
 p=root/row['file'];assert len(p.read_bytes())==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
(root/'download_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print('All22 original/derived file hashes verified; no prediction errors computed.')
