"""Pin public Orekit runtime/source dependencies in an external build directory."""
from pathlib import Path
import argparse,datetime,hashlib,json,urllib.request
ROOT=Path(__file__).resolve().parents[1]
MAVEN='https://repo.maven.apache.org/maven2/'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=Path('C:/aTOMosBuild/orbitdeps/java'));a=p.parse_args()
    a.directory.mkdir(parents=True,exist_ok=True)
    specs=[('org.orekit','orekit','13.1.8')]+[('org.hipparchus','hipparchus-'+s,'4.0.3') for s in ('core','geometry','ode','fitting','optim','filtering','stat')]+[('com.google.code.gson','gson','2.13.2')]
    records=[]
    for group,name,version in specs:
        for suffix in ('.jar','.pom')+ (('-sources.jar',) if name in ('orekit','hipparchus-geometry') else ()):
            filename=f'{name}-{version}{suffix}';url=MAVEN+group.replace('.','/')+f'/{name}/{version}/'+filename
            path=a.directory/filename
            if not path.exists():
                with urllib.request.urlopen(url,timeout=45) as response:path.write_bytes(response.read())
            raw=path.read_bytes()
            # Repository-provided digest identifies distribution bytes; it is
            # additional transport checking, not independent source auditing.
            with urllib.request.urlopen(url+'.sha1',timeout=45) as response:expected=response.read().decode().split()[0]
            if hashlib.sha1(raw).hexdigest()!=expected:raise ValueError('Maven digest mismatch: '+filename)
            records.append(dict(url=url,path=str(path.resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),maven_sha1=expected))
    report=dict(profile='ATOMOS-ORBIT-COMPARISON-DEPENDENCIES-R1',retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),orekit_version='13.1.8',hipparchus_version='4.0.3',gson_version='2.13.2',files=records)
    (ROOT/'review/r18_orbit_java_dependencies.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Verified',len(records),'runtime/source artifacts in',a.directory)
if __name__=='__main__':main()
