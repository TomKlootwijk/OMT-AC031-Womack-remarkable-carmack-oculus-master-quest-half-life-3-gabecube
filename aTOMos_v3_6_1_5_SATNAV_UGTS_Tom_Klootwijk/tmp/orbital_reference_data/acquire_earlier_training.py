import datetime,json,concurrent.futures,gzip,hashlib,urllib.request,urllib.parse
from pathlib import Path
out=Path('atomOS_3_6_1_9_ORBIT_SEED/source/orbit_data/earlier_training');out.mkdir(parents=True,exist_ok=True)
base=json.loads(Path('tmp/orbital_reference_data/horizons_downloads.json').read_text(encoding='utf-8'))[0]['parameters']
jobs=[]
for day in range(25,32):
 d=datetime.datetime(2024,12,day);doy=d.timetuple().tm_yday;week=(d-datetime.datetime(1980,1,6)).days//7
 name=f'GBM0MGXRAP_2024{doy:03d}0000_01D_05M_ORB.SP3.gz'
 jobs.append((name,f'ftp://ftp.gfz-potsdam.de/GNSS/products/mgex/{week}_IGS20/{name}',None))
for name,command in [('CHANDRA','-151'),('SUN','10'),('MOON','301')]:
 params=dict(base,COMMAND=f"'{command}'",START_TIME="'2024-12-25 00:00'",STOP_TIME="'2025-01-01 00:00'")
 url='https://ssd.jpl.nasa.gov/api/horizons.api?'+urllib.parse.urlencode(params)
 jobs.append((f'HORIZONS_{name}_20241225_20250101_ICRF_TDB.txt',url,params))
def fetch(job):
 name,url,params=job;p=out/name
 with urllib.request.urlopen(url,timeout=55) as r:
  data=r.read();resolved=r.geturl()
 if name.endswith('.gz'):
  raw=gzip.decompress(data);assert raw.startswith(b'#dP') and raw.rstrip().endswith(b'EOF')
 else:
  raw=data;assert b'$$SOE' in data and b'$$EOE' in data
 p.write_bytes(data)
 row=dict(file=name,url=url,resolved_url=resolved,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 if name.endswith('.gz'):row['uncompressed_sha256']=hashlib.sha256(raw).hexdigest()
 if params:row['parameters']=params
 print(json.dumps(row),flush=True)
 return row
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 rows=list(ex.map(fetch,jobs))
(out/'download_manifest.json').write_text(json.dumps(dict(schema='ORBIT-EARLIER-TRAINING-1',files=rows),indent=2)+'\n',encoding='utf-8')
