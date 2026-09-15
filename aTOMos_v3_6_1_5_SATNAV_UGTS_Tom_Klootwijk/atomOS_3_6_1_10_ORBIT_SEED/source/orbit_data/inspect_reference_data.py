"""Inspect original SP3 references without using the application implementation."""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import math, json, statistics, gzip
BASE=Path(__file__).resolve().parent
SELECTED=['G01','G05','G12','C01','C03','C05','C06','C07','C59','J02','J07']
def load(prefix):
    series=defaultdict(dict);duplicates=[];flags=Counter()
    for path in sorted(BASE.glob(prefix+'*.SP3.gz')):
        for line in gzip.decompress(path.read_bytes()).decode('ascii').splitlines():
            if line.startswith('*'):
                f=line[1:].split();t=(datetime(*map(int,f[:5]))+timedelta(seconds=float(f[5]))-datetime(1980,1,6)).total_seconds()
            elif line.startswith('P') and line[1:4] in SELECTED:
                xyz=tuple(float(line[k:k+14])*1000 for k in [4,18,32]);sid=line[1:4]
                if not any(xyz):flags['zero_position']+=1;continue
                if t in series[sid]:duplicates.append({'satellite':sid,'gpst_s':t,'difference_m':math.dist(series[sid][t],xyz),'later_source':path.name})
                else:series[sid][t]=xyz
                if len(line)>78 and line[78]=='M':flags['maneuver']+=1
                if len(line)>79 and line[79]=='P':flags['predicted']+=1
    return series,duplicates,flags
all_series={};out={'deduplication':'Earlier source filename wins, retaining the previous day midnight estimate; conflicting source samples are recorded.'}
for prefix in ['GBM','COD','IGS','WUM']:
    series,duplicates,flags=load(prefix);all_series[prefix]=series
    out[prefix]={'satellites':{sid:{'samples':len(s),'first_gpst_s':min(s),'last_gpst_s':max(s),'radius_min_km':min(math.sqrt(sum(x*x for x in q)) for q in s.values())/1000,'radius_max_km':max(math.sqrt(sum(x*x for x in q)) for q in s.values())/1000} for sid,s in series.items()},'flags':dict(flags),'duplicate_midnight_count':len(duplicates),'duplicate_midnight_max_difference_m':max([q['difference_m'] for q in duplicates],default=0),'duplicate_midnight_details':duplicates}
out['cross_product_disagreement_m']={}
for first,second in [('GBM','COD'),('GBM','IGS'),('GBM','WUM')]:
    label=first+'_vs_'+second;a=all_series[first];b=all_series[second];out['cross_product_disagreement_m'][label]={}
    for sid in SELECTED:
        if sid not in a or sid not in b:continue
        v=sorted(math.dist(a[sid][t],b[sid][t]) for t in set(a[sid])&set(b[sid]));
        out['cross_product_disagreement_m'][label][sid]={'n':len(v),'rms':math.sqrt(statistics.mean(x*x for x in v)),'max':max(v),'p95':v[int(.95*(len(v)-1))]}
p=BASE/'reference_data_inspection.json';p.write_text(json.dumps(out,indent=2))
print(p)
print(json.dumps(out['cross_product_disagreement_m'],indent=2))
