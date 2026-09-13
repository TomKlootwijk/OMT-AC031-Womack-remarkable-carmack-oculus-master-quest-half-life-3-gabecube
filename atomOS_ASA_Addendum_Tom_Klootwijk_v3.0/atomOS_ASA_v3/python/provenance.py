"""Local genesis metadata and record seals. No identity-to-position mapping."""
from __future__ import annotations
import hashlib
import json
import struct
from pathlib import Path
FILES=('image.f32','mask.u32','warp.f32x2','samples.f64x2','results.bin','results.csv','run.json')
AUTHOR={'name':'Tom Klootwijk','identifier':'NL200678942','date_verbatim':'10-07-1990'}

def canonical(data: object) -> bytes:
    return json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

def genesis(fixture_id: str='ASA-symbolic-fixture-v3') -> dict:
    if not isinstance(fixture_id,str) or not fixture_id:
        raise ValueError('fixture_id must be a nonempty string')
    record={'schema':'atomOS.ASA.v3.genesis','author':AUTHOR,'operator_label':'>O< / ASA','fixture_id':fixture_id}
    return {'record':record,'sha256':hashlib.sha256(b'atomOS.ASA.genesis.v3\0'+canonical(record)).hexdigest()}

def file_hash(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()

def compute_seal(directory: Path) -> dict:
    g=genesis()
    config=json.loads((directory/'run.json').read_text())['config']
    inputs={name:file_hash(directory/name) for name in FILES[:4]}
    h=hashlib.sha256(b'atomOS.ASA.run.v3\0'+bytes.fromhex(g['sha256'])+canonical(config)+canonical(inputs)).digest()
    rows=0
    with (directory/'results.bin').open('rb') as f:
        while raw:=f.read(32):
            if len(raw)!=32:raise ValueError('truncated result record')
            h=hashlib.sha256(b'atomOS.ASA.row.v3\0'+h+struct.pack('<Q',rows)+raw).digest()
            rows+=1
    return {'schema':'atomOS.ASA.v3.seal','genesis':g,'config':config,'records':rows,'head':h.hex(),
            'files':{name:file_hash(directory/name) for name in FILES}}

def seal(directory: Path) -> dict:
    target=directory/'seal.json'
    if target.exists():raise FileExistsError('seal already exists')
    value=compute_seal(directory)
    target.write_text(json.dumps(value,indent=2)+'\n')
    return value

def verify(directory: Path, expected_head: str | None=None) -> bool:
    stored=json.loads((directory/'seal.json').read_text())
    return stored==compute_seal(directory) and (expected_head is None or expected_head==stored['head'])
