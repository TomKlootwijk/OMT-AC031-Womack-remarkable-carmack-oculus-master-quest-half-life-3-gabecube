import datetime,json,concurrent.futures,gzip,hashlib,urllib.request,urllib.parse
from pathlib import Path
out=Path('atomOS_3_6_1_9_ORBIT_SEED/source/orbit_data/confirmation_20250202')
for name in ('training','holdout','forcing','eop'):(out/name).mkdir(parents=True,exist_ok=True)
base=json.loads(Path('tmp/orbital_reference_data/horizons_downloads.json').read_text(encoding='utf-8'))[0]['parameters']
epoch=datetime.datetime(2025,2,2);gps_seconds=(epoch-datetime.datetime(1980,1,6)).total_seconds();jobs=[]
for i in range(15):
 d=datetime.datetime(2025,1,25)+datetime.timedelta(days=i);doy=d.timetuple().tm_yday;week=(d-datetime.datetime(1980,1,6)).days//7
 name=f'GBM0MGXRAP_2025{doy:03d}0000_01D_05M_ORB.SP3.gz';role='training' if d<epoch else 'holdout'
 jobs.append((f'{role}/{name}',f'ftp://ftp.gfz-potsdam.de/GNSS/products/mgex/{week}_IGS20/{name}',None,role))
for role,name,command,start,stop in [('training','CHANDRA','-151','2025-01-25 00:00','2025-02-02 00:00'),('holdout','CHANDRA','-151','2025-02-02 00:05','2025-02-09 00:00'),('forcing','SUN','10','2025-01-24 00:00','2025-02-10 00:00'),('forcing','MOON','301','2025-01-24 00:00','2025-02-10 00:00')]:
 params=dict(base,COMMAND=f"'{command}'",START_TIME=f"'{start}'",STOP_TIME=f"'{stop}'")
 url='https://ssd.jpl.nasa.gov/api/horizons.api?'+urllib.parse.urlencode(params)
 filename=f'HORIZONS_{name}_{start[:10].replace("-","")}_{stop[:10].replace("-","")}_ICRF_TDB.txt'
 jobs.append((f'{role}/{filename}',url,params,role))
jobs.append(('eop/bulletina-xxxviii-005.txt','https://datacenter.iers.org/data/6/bulletina-xxxviii-005.txt',None,'external_published_eop'))
def fetch(job):
 name,url,params,role=job;p=out/name
 for attempt in range(2):
  try:
   with urllib.request.urlopen(url,timeout=45) as r:data=r.read();resolved=r.geturl()
   break
  except Exception:
   if attempt:raise
 if name.endswith('.gz'):
  raw=gzip.decompress(data);assert raw.startswith(b'#dP') and raw.rstrip().endswith(b'EOF')
 elif 'HORIZONS' in name:
  raw=data;assert b'$$SOE' in data and b'$$EOE' in data
 else:
  raw=data;assert b'30 January 2025' in data and b'XXXVIII No. 005' in data
 p.write_bytes(data)
 row=dict(file=name,role=role,url=url,resolved_url=resolved,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 if name.endswith('.gz'):row['uncompressed_sha256']=hashlib.sha256(raw).hexdigest()
 if params:row['parameters']=params
 return row
manifest=dict(schema='ORBIT-INDEPENDENT-CONFIRMATION-SOURCES-1',cutoff_gpst_label='2025-02-02 00:00:00',cutoff_gpst_seconds=gps_seconds,training_gpst_range_s=[gps_seconds-8*86400,gps_seconds],holdout_gpst_range_s=[gps_seconds,gps_seconds+7*86400],holdout_lower_bound_exclusive=True,prediction_errors_computed=False,model_fitting_performed=False,files=[],errors=[])
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 futures={ex.submit(fetch,job):job for job in jobs}
 for fut in concurrent.futures.as_completed(futures):
  try:
   row=fut.result();manifest['files'].append(row);print(row['file'],row['bytes'],'bytes',flush=True)
  except Exception as e:
   manifest['errors'].append(dict(file=futures[fut][0],error=str(e)));print('ERROR',futures[fut][0],str(e),flush=True)
  manifest['files'].sort(key=lambda x:x['file']);(out/'download_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
assert not manifest['errors'],manifest['errors']
print('Complete:',len(manifest['files']),'original files. Cutoff GPST seconds:',gps_seconds,flush=True)
