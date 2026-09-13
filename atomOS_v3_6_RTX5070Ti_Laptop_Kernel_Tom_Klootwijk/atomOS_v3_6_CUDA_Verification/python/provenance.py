"""Full-width identity binding and retained-reference integrity, no external services."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import unicodedata
from reference import canonical
FILES=('summary.json','inputs.csv','trace.csv','final_state.csv','asa.u32le','na.u32le','boundary.u32le','fringe.u32le','COMMITTED')

def identity(labels:list[str])->dict:
    if not labels or any(not isinstance(x,str) or not x for x in labels):raise ValueError('nonempty symbolic labels required')
    normalized=sorted({unicodedata.normalize('NFC',x) for x in labels},key=lambda x:x.encode('utf-8'))
    record={'schema':'atomOS-v3.6-K1-genesis','members':normalized}
    raw=canonical(record);digest=hashlib.sha256(b'atomOS:K1:genesis\0'+len(raw).to_bytes(8,'big')+raw).hexdigest()
    return {'record':record,'digest256':digest}

def digest_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def seal_run(directory:Path,labels:list[str])->dict:
    directory=Path(directory)
    if (directory/'run_seal.json').exists():raise ValueError('refusing to replace an existing run seal')
    header={'schema':'atomOS-v3.6-K1-seal','genesis':identity(labels),'files':{n:digest_file(directory/n) for n in FILES}}
    raw=canonical(header);head=hashlib.sha256(b'atomOS:K1:header\0'+len(raw).to_bytes(8,'big')+raw).digest();count=0
    with (directory/'trace.csv').open('rb') as f:
        for count,line in enumerate(f,1):head=hashlib.sha256(b'atomOS:K1:row\0'+head+len(line).to_bytes(8,'big')+line).digest()
    result={'header':header,'rows_including_csv_header':count,'head256':head.hex()}
    (directory/'run_seal.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def verify_seal(directory:Path)->bool:
    directory=Path(directory);r=json.loads((directory/'run_seal.json').read_text());h=r['header']
    if h['schema']!='atomOS-v3.6-K1-seal' or set(h['files'])!=set(FILES):return False
    if h['genesis']!=identity(h['genesis']['record']['members']):return False
    if any(digest_file(directory/n)!=h['files'][n] for n in FILES):return False
    raw=canonical(h);head=hashlib.sha256(b'atomOS:K1:header\0'+len(raw).to_bytes(8,'big')+raw).digest();count=0
    with (directory/'trace.csv').open('rb') as f:
        for count,line in enumerate(f,1):head=hashlib.sha256(b'atomOS:K1:row\0'+head+len(line).to_bytes(8,'big')+line).digest()
    return count==r['rows_including_csv_header'] and head.hex()==r['head256']
