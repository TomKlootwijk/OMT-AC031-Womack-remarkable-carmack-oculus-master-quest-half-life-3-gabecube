from pathlib import Path
import datetime,urllib.request,hashlib,gzip,json,concurrent.futures
root=Path('atomOS_3_6_1_9_ORBIT_SEED/source/orbit_data/confirmation_20250202');out=root/'holdout_wum';out.mkdir(exist_ok=True)
def fetch(day):
 name=f'WUM0MGXFIN_2025{day:03d}0000_01D_05M_ORB.SP3.gz';url=f'ftp://igs.gnsswhu.cn/pub/gnss/products/mgex/2352/{name}'
 with urllib.request.urlopen(url,timeout=50) as r:data=r.read();resolved=r.geturl()
 raw=gzip.decompress(data);assert raw.startswith(b'#d') and raw.rstrip().endswith(b'EOF');(out/name).write_bytes(data)
 return dict(file=f'holdout_wum/{name}',role='holdout_alternate_C03_chosen_for_complete_coverage_before_any_prediction_errors',url=url,resolved_url=resolved,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),uncompressed_sha256=hashlib.sha256(raw).hexdigest(),retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:rows=list(ex.map(fetch,range(33,40)))
p=root/'download_manifest.json';m=json.loads(p.read_text(encoding='utf-8'));m['files']+=rows;m['files'].sort(key=lambda x:x['file']);p.write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8');print('Acquired seven WUM final holdout sources, coverage inspection pending; no errors evaluated.')
