"""Independent source-atlas/Klein replay, reusing the existing scalar word oracle.

The SDF compiler must be verified separately. This checker binds its exact binary
bytes, verifies every packed texture plane, independently scatters cell transport,
and checks every downloaded GPU epoch before accepting the exported commit.
"""
from reference import *


def read_atlas(path, rows, angles):
    raw=Path(path).read_bytes()
    words=(angles+31)//32
    if len(raw)!=16+16*rows*words or raw[:8]!=b'AOSDF01\n':
        raise ValueError('invalid atlas format or exact byte count')
    if struct.unpack_from('<II',raw,8)!=(rows,angles):
        raise ValueError('atlas dimensions differ')
    values=[v[0] for v in struct.iter_unpack('<I',raw[16:])]
    planes=[values[i*rows*words:(i+1)*rows*words] for i in range(4)]
    for plane in planes:
        for i,value in enumerate(plane):
            valid=(1<<min(32,angles-(i%words)*32))-1
            if value & ~valid: raise ValueError('atlas contains invalid angular tail')
    return planes, hashlib.sha256(raw).hexdigest()


def transport_cells(state, rows, angles, carrier):
    if carrier=='direct':return state
    words=(angles+31)//32
    out=[0]*(rows*words)
    step=1 if carrier=='klein-plus' else -1
    for i,(value,_) in enumerate(state):
        r,w=divmod(i,words)
        while value:
            lowest=value & -value
            b=lowest.bit_length()-1
            destination=32*w+b+step
            winding,j=divmod(destination,angles)
            rr=rows-1-r if winding%2 else r
            out[rr*words+j//32]|=1<<(j%32)
            value^=lowest
    return [(value,state[i][1]) for i,value in enumerate(out)]


def verify_source_run(directory:Path, atlas_path:Path, *, expected_device:dict|None=None)->dict:
    directory=Path(directory)
    if not (directory/'COMMITTED').is_file():raise ValueError('run lacks its commit marker')
    s=json.loads((directory/'summary.json').read_text())
    if s['schema']!='atomOS-source-atlas-K1-run-v1':raise ValueError('unsupported source-atlas schema')
    if s.get('mask_source')!='external_sdf_atlas':raise ValueError('source atlas metadata required')
    if Path(s['atlas_path']).resolve()!=Path(atlas_path).resolve():raise ValueError('atlas path differs from requested input')
    source_planes, atlas_hash = read_atlas(atlas_path,s['rows'],s['angles'])
    carrier=s.get('carrier','direct')
    if carrier not in ('direct','klein-plus','klein-minus'):raise ValueError('unknown source-atlas carrier')
    if s.get('layout') not in ('linear','morton8'):raise ValueError('unknown source-atlas layout')
    receipt=s.get('bulk_receipt',{})
    for key in ('carrier','carrier_buffer_bytes','atlas_cap_texels','mask_source','dictionary_encoding','atlas_path','atlas_encoding','atlas_file_bytes'):
        if key not in s or type(s[key]) is not type(receipt.get(key)) or s[key]!=receipt[key]:
            raise ValueError('source-atlas receipt binding: '+key)
    if s['atlas_file_bytes']!=Path(atlas_path).stat().st_size:raise ValueError('source atlas byte count metadata')
    verify_execution_metadata(s,expected_backend='cuda',expected_read='texture-packed',expected_device=expected_device)
    if s.get('chart')!={'r_min':.25,'r_max':64,'angular_sampling':'periodic_nodes'}:raise ValueError('chart metadata differs from K1')
    for key in ('rows','angles','words','padded_rows','padded_words','epochs','seed'):
        if type(s[key]) is not int:raise ValueError('integer metadata required')
    r,p=s['rows'],s['angles'];w=(p+31)//32;pr=(r+7)//8*8;pw=(w+7)//8*8
    if not (1<=r<=65536 and 1<=p<=65536 and 1<=s['epochs']<=4096 and 0<=s['seed']<=U32):raise ValueError('metadata bounds')
    atlas_cap=s.get('atlas_cap_texels',2**18)
    if type(atlas_cap) is not int or not 2**18<=atlas_cap<=2**20:raise ValueError('source-atlas capacity profile')
    if pr*pw>atlas_cap or r*w*s['epochs']>2**20 or (s['words'],s['padded_rows'],s['padded_words'])!=(w,pr,pw):raise ValueError('layout/record bounds')
    if s['mode'] not in ('provided','recurrent','shift-xor','shift-or') or s['profile'] not in ('source','directed','mixed') or type(s['fringe']) is not bool:raise ValueError('profile metadata')
    planes=[]
    for name in MASKS:
        raw=(directory/name).read_bytes()
        if len(raw)!=pr*pw*4:raise ValueError('plane size: '+name)
        planes.append([v[0] for v in struct.iter_unpack('<I',raw)])
    for rr in range(pr):
        for ww in range(pw):
            if rr>=r or ww>=w:
                k=address(rr,ww,pw,s['layout'])
                if any(m[k] for m in planes):raise ValueError('padding is not zero')
    lanes=[];logical_masks=[]
    with (directory/'inputs.csv').open(newline='') as f:
        reader=csv.DictReader(f)
        for i,row in enumerate(reader):
            if i>=r*w:raise ValueError('too many input rows')
            rr,ww=divmod(i,w);_,lane=fixture(s,rr,ww);m=[plane[i] for plane in source_planes];k=address(rr,ww,pw,s['layout'])
            if m!=[a[k] for a in planes]:raise ValueError(f'source atlas plane mismatch at lane {i}')
            if set(row)!=set(lane):raise ValueError('input schema mismatch')
            for key,value in lane.items():
                actual=float(row[key]) if key in ('dr','dp','alpha','interval') else int(row[key])
                if actual!=value:raise ValueError(f'fixture input {key} at lane {i}')
            lanes.append(lane);logical_masks.append(m)
    if len(lanes)!=r*w:raise ValueError('input count mismatch')
    state=[(v['initial_word'],v['initial_q']) for v in lanes];counts=[0,0,0];max_error=0.;rows_checked=0
    integer_digest=hashlib.sha256(b'atomOS:SDF:Klein:integer-semantic\0'+canonical({**{k:s[k] for k in ('rows','angles','epochs','seed','mode','profile','fringe')},'carrier':carrier,'atlas_sha256':atlas_hash}))
    def equal_float(raw,expected,label):
        nonlocal max_error
        if expected is None:
            if raw!='':raise ValueError('undefined field has a numeric value: '+label)
            return
        actual=float(raw)
        if not math.isfinite(actual):raise ValueError('nonfinite exported field')
        error=abs(actual-expected);max_error=max(max_error,error)
        if error>TOL:raise ValueError(f'numeric mismatch {label}: {actual} != {expected}')
    with (directory/'trace.csv').open(newline='') as f:
        reader=csv.DictReader(f)
        for epoch in range(s['epochs']):
            next_state=[]
            transported=transport_cells(state,r,p,carrier)
            occupancy=dict(epoch=epoch,input_active_cells=sum(x.bit_count() for x,q in state),
                           transported_active_cells=sum(x.bit_count() for x,q in transported),
                           output_active_cells=0,absorbed_words=0,seam_crossing_cells=r if carrier!='direct' else 0,
                           occupied_seam_crossings=0)
            if carrier=='klein-plus':
                occupancy['occupied_seam_crossings']=sum((state[rr*w+w-1][0]>>((p-1)%32))&1 for rr in range(r))
            elif carrier=='klein-minus':
                occupancy['occupied_seam_crossings']=sum(state[rr*w][0]&1 for rr in range(r))
            for i,lane in enumerate(lanes):
                row=next(reader,None)
                if row is None:raise ValueError('truncated epoch')
                x,q=transported[i];produced=producer(x,lane,s['mode']);valid=(1<<min(32,p-(i%w)*32))-1
                am,nm,bm,fm=logical_masks[i];a,n,h,y=bit_core(produced,am,nm,bm,valid,fm if s['fringe'] else valid)
                occupancy['output_active_cells']+=y.bit_count()
                occupancy['absorbed_words']+=int(h>0)
                q_next={(0,0):q,(1,0):1,(0,1):0,(1,1):1-q}[(lane['j'],lane['k'])]
                blend=(lane['north']+lane['axis']+lane['kinematic'])%2 if lane['blend_known'] else 0
                o=observe(lane);checks=bank(lane,o)
                expected=dict(epoch=epoch,lane=i,input_word=x,q_before=q,produced=produced,asa=a,na=n,hits=h,output=y,q_after=q_next,blend=blend,blend_known=lane['blend_known'],beta_status=o['beta_status'],angle_status=o['status'])
                for key,value in expected.items():
                    if int(row[key])!=value:raise ValueError(f'{key} mismatch, epoch {epoch}, lane {i}')
                integer_digest.update(struct.pack('<14I',*expected.values()))
                for key in ('beta','raw','principal','line'):equal_float(row[key],o[key],key)
                for name,c in zip(NAMES,checks):
                    if int(row[name+'_state'])!=c['state'] or int(row[name+'_reason'])!=c['reason']:raise ValueError('invariant state/reason mismatch')
                    equal_float(row[name+'_error'],c['error'],name);counts[c['state']]+=1
                    integer_digest.update(struct.pack('<2I',c['state'],c['reason']))
                next_state.append((y,q_next));rows_checked+=1
            records=receipt.get('epoch_occupancy',[])
            if len(records)!=s['epochs'] or records[epoch]!=occupancy:raise ValueError('occupancy/absorption/seam receipt mismatch')
            state=next_state
        if next(reader,None) is not None:raise ValueError('extra trace rows')
    with (directory/'final_state.csv').open(newline='') as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=len(state):raise ValueError('final-state count')
    for i,(row,(x,q)) in enumerate(zip(rows,state)):
        if (int(row['lane']),int(row['word']),int(row['q']))!=(i,x,q):raise ValueError('final commit mismatch')
    if [s['checks_pass'],s['checks_fail'],s['checks_undefined']]!=counts or s['committed_lane_epochs']!=rows_checked:raise ValueError('summary counts')
    verify_memory_metadata(s)
    if len(s['compute_ms'])!=s['epochs'] or any(not math.isfinite(t) or t<0 for t in s['compute_ms']):raise ValueError('invalid timing metadata')
    return dict(status='passed',lane_epochs=rows_checked,integer_semantic_sha256=integer_digest.hexdigest(),max_float_difference_radians=max_error,tolerance_radians=TOL,invariant_counts=counts,backend_recorded=s['backend'],atlas_sha256=atlas_hash,carrier=carrier)
