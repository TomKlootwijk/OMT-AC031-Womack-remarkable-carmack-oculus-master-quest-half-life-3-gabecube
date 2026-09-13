"""Independent exact-bit-set and scalar-math checker for exported K1 word epochs.

Standard library only. It reconstructs the synthetic inputs instead of trusting
exported fixture bytes, and checks every recorded epoch before accepting a run.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any
U32=(1<<32)-1
PI=math.pi
TAU=2*PI
TOL=2e-11
NAMES=('R','W','P','S','F','V')
MASKS=('asa.u32le','na.u32le','boundary.u32le','fringe.u32le')

def canonical(x: Any)->bytes:
    return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')

def mix(x:int)->int:
    x&=U32;x^=x>>16;x=(x*0x7feb352d)&U32;x^=x>>15;x=(x*0x846ca68b)&U32;return x^(x>>16)

def address(r:int,w:int,pw:int,layout:str)->int:
    if layout=='linear':return r*pw+w
    if layout!='morton8':raise ValueError('unknown layout')
    z=sum(((r>>i)&1)*(1<<(2*i))+((w>>i)&1)*(1<<(2*i+1)) for i in range(3))
    return 64*((r//8)*(pw//8)+w//8)+z

def fixture(summary:dict,r:int,w:int)->tuple[list[int],dict]:
    p=summary['angles'];i=r*summary['words']+w;v=(1<<min(32,p-32*w))-1
    z=mix(summary['seed']^((i*0x9e3779b9)&U32))
    masks=[(mix(z+1)|mix(z+7))&v,(mix(z+11)|mix(z+19))&v,
           (mix(z+31)&mix(z+37)&mix(z+41)&mix(z+43))&v,mix(z+53)&v]
    lane=dict(lane=i,initial_word=mix(z+71)&v,initial_q=(i>>2)&1,jitter=mix(z+73),j=i&1,k=(i>>1)&1,
              north=i&1,axis=(i>>1)&1,kinematic=(i>>2)&1,blend_known=int(i%31!=0),
              dr=((z%63)-31)/8,dp=(((z>>8)%63)-31)/8,alpha=(((z>>16)%31)-15)/8,interval=.125,
              profile=(i&1) if summary['profile']=='mixed' else int(summary['profile']=='directed'),
              axis_known=1,frame_known=1,increment_known=1)
    if i%29==0:lane.update(dr=0.,dp=0.)
    elif i%29==1:lane.update(dr=0.,dp=1.)
    elif i%29==2:lane.update(dr=-1.,dp=0.)
    if i%97==4:lane['axis_known']=0
    if i%97==5:lane['frame_known']=0
    if i%97==6:lane['increment_known']=0
    if i%97==7:lane['interval']=0.
    return masks,lane

def bit_core(x:int,a:int,n:int,b:int,valid:int,fringe:int)->tuple[int,int,int,int]:
    aset={k for k in range(32) if all((v>>k)&1 for v in (x,a,valid,fringe))}
    nset={k for k in aset if (n>>k)&1}
    count=sum((b>>k)&1 for k in nset)
    aa=sum(1<<k for k in aset);nn=sum(1<<k for k in nset)
    return aa,nn,count,0 if count else nn

def producer(x:int,lane:dict,mode:str)->int:
    if mode=='provided':return lane['initial_word']
    if mode=='recurrent':return x
    if mode not in ('shift-xor','shift-or'):raise ValueError('unknown producer')
    if x==0:return 0
    a=(x*2)&U32;b=x//2
    merged=(a^b) if mode=='shift-xor' else (a|b)
    return merged^lane['jitter']

def wrap(x:float,period:float=TAU)->float:
    x=math.fmod(x,period)
    if x>=period/2:x-=period
    if x< -period/2:x+=period
    return 0. if x==0 else x

def observe(a:dict)->dict:
    o=dict(status=0,beta_status=0,beta=None,raw=None,principal=None,line=None)
    def bad(status):return dict(o,status=status,beta_status=status)
    dr,dp=a['dr'],a['dp']
    if not all(math.isfinite(x) for x in (dr,dp)):return bad(3)
    if dr==dp==0:return bad(1)
    if a['profile']==0:
        if dr==0:return bad(2)
        ratio=dp/dr
        if not math.isfinite(ratio) or (dp!=0 and ratio==0):return bad(4)
        beta=math.atan(ratio)
    else:beta=wrap(math.atan2(dp,dr))
    o['beta']=0. if beta==0 else beta
    if not a['increment_known']:o['status']=7;return o
    if not a['frame_known']:o['status']=6;return o
    if not a['axis_known']:o['status']=5;return o
    if not math.isfinite(a['alpha']):o['status']=3;return o
    residual=beta-a['alpha']
    if not math.isfinite(residual):o['status']=4;return o
    o.update(raw=residual,principal=wrap(residual),line=wrap(residual,PI));return o

def bank(a:dict,o:dict)->list[dict]:
    def undefined(reason):return dict(state=2,reason=reason,error=None)
    def compare(x,y,space=0):
        d=x-y
        if not all(math.isfinite(v) for v in (x,y,d)):return undefined(4)
        error=abs(d if space==0 else wrap(d,PI if space==1 else TAU))
        return dict(state=0 if error<=1e-10 else 1,reason=0,error=error)
    def probe(patch,space=0):
        n=observe(dict(a,**patch))
        if n['status']!=0:return undefined(n['status'])
        field=('raw','line','principal')[space]
        return compare(n[field],o[field],space)
    if o['status']!=0:return [undefined(o['status']) for _ in range(6)]
    dr,dp=a['dr'],a['dp']
    out=[probe(dict(dr=((.75+dr)+1.25)-(.75+1.25)))]
    w=a['interval']
    if not math.isfinite(w) or w<=0:out.append(undefined(100))
    else:
        nr,np=dr/w,dp/w
        out.append(undefined(4) if (dr!=0 and nr==0) or (dp!=0 and np==0) else probe(dict(dr=nr,dp=np)))
    out.append(probe(dict(dp=((.25+dp)+.75)-(.25+.75))))
    nr,np=dr*3,dp*3
    out.append(undefined(4) if (dr!=0 and nr==0) or (dp!=0 and np==0) else probe(dict(dr=nr,dp=np)))
    c,s=math.cos(.4),math.sin(.4);nr,np=c*dr-s*dp,s*dr+c*dp
    if a['profile']==0 and abs(nr)<=64*2**-52*math.hypot(dr,dp):out.append(undefined(101))
    else:out.append(probe(dict(dr=nr,dp=np,alpha=a['alpha']+.4),1 if a['profile']==0 else 2))
    rev=observe(dict(a,dr=-dr,dp=-dp))
    if rev['beta_status']!=0:out.append(undefined(rev['beta_status']))
    elif a['profile']==0:out.append(compare(rev['beta'],o['beta']))
    else:out.append(compare(wrap(rev['beta']-o['beta']),-PI,2))
    return out

def verify_execution_metadata(s:dict,*,expected_backend:str|None=None,expected_read:str|None=None,expected_device:dict|None=None)->None:
    """Check recorded execution context, optionally against the invoking runner.

    These checks reject contradictory metadata; self-reported JSON alone is not
    proof that a CUDA binary ran. The validation runner supplies its probe record.
    """
    backend=s.get('backend');read=s.get('read');device=s.get('device')
    if s.get('candidate_verification')!='passed':raise ValueError('candidate verification was not passed')
    if backend=='cpu':
        if read!='host' or device is not None:raise ValueError('CPU execution requires host reads and no CUDA device')
    elif backend=='cuda':
        if read not in ('texture','texture-packed','global') or not isinstance(device,dict):raise ValueError('CUDA execution metadata missing or invalid')
        if not isinstance(device.get('name'),str) or not device['name'].strip():raise ValueError('CUDA device name missing')
        fields=('cc_major','cc_minor','total_bytes','free_bytes_at_start','runtime','driver','max_texture_1d_linear')
        if any(type(device.get(k)) is not int for k in fields):raise ValueError('integer CUDA device metadata required')
        if not (device['cc_major']>0 and device['cc_minor']>=0 and device['total_bytes']>0 and
                0<=device['free_bytes_at_start']<=device['total_bytes'] and device['runtime']>0 and
                device['driver']>0 and device['max_texture_1d_linear']>0):raise ValueError('CUDA device metadata bounds')
    else:raise ValueError('unknown execution backend')
    if expected_backend is not None and backend!=expected_backend:raise ValueError('execution backend differs from requested backend')
    if expected_read is not None and read!=expected_read:raise ValueError('execution read path differs from requested read path')
    if expected_device is not None:
        # Free memory can change between the probe and launch; device identity and
        # capabilities must still agree with the actual invocation's probe.
        keys=('name','cc_major','cc_minor','total_bytes','runtime','driver','max_texture_1d_linear')
        if backend!='cuda' or any(device[k]!=expected_device.get(k) for k in keys):raise ValueError('execution device differs from probed device')

def verify_memory_metadata(s:dict)->None:
    """Validate the exact known allocation profile; metadata is not execution proof."""
    rows,words,pr,pw=s['rows'],s['words'],s['padded_rows'],s['padded_words']
    stored,logical=pr*pw,rows*words
    allocation=s.get('allocation_layout')
    if allocation is None:
        if 'execution_profile' in s or 'bulk_receipt' in s:raise ValueError('incomplete bulk allocation profile')
        payload=16*stored+256*logical
    else:
        if (allocation!='bulk-padded-row-major-v1' or s.get('execution_profile')!='bulk-warm-work-probe-v1' or
                s.get('backend')!='cuda' or s.get('read')!='texture-packed'):
            raise ValueError('unsupported bulk allocation profile')
        receipt=s.get('bulk_receipt')
        if not isinstance(receipt,dict):raise ValueError('bulk receipt missing')
        grid=receipt.get('grid_blocks')
        if type(grid) is not int or not (1<=grid<=U32//512):raise ValueError('bulk grid bounds')
        diagnostic=16*grid*(2*512+2)
        payload=272*stored+diagnostic
        chunk=((stored+grid*64-1)//(grid*64))*64
        expected={
            'status':'passed','scope':'experimental_bulk_io_warm_work_retention_probe',
            'device':s['device'],'rows':rows,'angles':s['angles'],'epochs':s['epochs'],'seed':s['seed'],
            'layout':s['layout'],'mode':s['mode'],'fringe':s['fringe'],'profile':s['profile'],
            'io':'native_cp_async_bulk_1d','barrier':'grid','phase_order_scope':'whole_cooperative_grid',
            'padding_and_tails_supported':True,'device_records':'padded_row_major','results':'canonical_row_major',
            'padded_rows':pr,'padded_words':pw,'block_size':512,'tile_texels':64,'multiprocessors':grid,
            'active_blocks_per_sm_limit':1,'shared_union_bytes':10752,'input_tile_bytes':5632,
            'result_tile_bytes':10752,'bulk_barrier_bytes':8,'max_l1_requested':True,
            'stored_texels':stored,'logical_texels':logical,'padding_texels':stored-logical,'chunk_texels':chunk,
            'maximum_assigned_mask_bytes':min(chunk,stored)*16,'warm_texel_reads_per_epoch':stored,
            'work_texel_reads_per_epoch':logical,'post_texel_reads_per_epoch':stored,
            'expected_total_texel_reads_per_epoch':2*stored+logical,'tiles_per_epoch':stored//64,
            'bulk_input_bytes_per_epoch':88*stored,'bulk_result_bytes_per_epoch':168*stored,
            'bulk_diagnostic_bytes_per_epoch':diagnostic,'mask_bytes':16*stored,'payload_bytes':payload,
            'diagnostic_bytes':diagnostic,'planned_bytes':payload+64*2**20,'verified_lane_epochs':logical*s['epochs'],
            'candidate_verification':'passed','checksum_scheme':'per_thread_componentwise_xor',
            'checksum_components':4,'checksum_disagreements':0,'sm_mapping_verified':True,
            'setup_launches':1,'setup_launch_verified':True,'setup_checksum_verified':True,
            'host_tile_coverage_verified':True,'padding_output_verified_zero':True,
            'timing_scope':'entire_warm_bulk_io_work_probe_kernel_including_barriers_and_diagnostics',
            'compute_ms':s['compute_ms'],
        }
        for key,value in expected.items():
            if key not in receipt or type(receipt[key]) is not type(value) or receipt[key]!=value:
                raise ValueError('bulk receipt mismatch: '+key)
        for key,lower in (('registers_per_thread',1),('local_bytes_per_thread',0),('static_shared_bytes',10760),('binary_version',90)):
            if type(receipt.get(key)) is not int or receipt[key]<lower:raise ValueError('bulk resource metadata: '+key)
        if type(receipt.get('preferred_shared_carveout')) is not int:raise ValueError('bulk carveout metadata')
        if s['device'].get('cc_major',0)<9:raise ValueError('bulk device capability')
        mappings=receipt.get('sm_mappings')
        if not isinstance(mappings,list) or len(mappings)!=s['epochs']+1:raise ValueError('bulk SM mapping count')
        for index,mapping in enumerate(mappings):
            if (not isinstance(mapping,dict) or type(mapping.get('launch')) is not int or mapping['launch']!=index or
                    type(mapping.get('setup')) is not bool or mapping['setup']!=(index==0)):
                raise ValueError('bulk SM mapping launch')
            before,after=mapping.get('before'),mapping.get('after')
            if (not isinstance(before,list) or not isinstance(after,list) or len(before)!=grid or
                    any(type(v) is not int or not (0<=v<U32) for v in before+after) or
                    before!=after or len(set(before))!=grid):
                raise ValueError('bulk SM mapping identity')
    if (type(s.get('payload_bytes')) is not int or s['payload_bytes']!=payload or
            type(s.get('planned_bytes')) is not int or s['planned_bytes']!=payload+64*2**20):
        raise ValueError('memory summary')

def verify_run(directory:Path,*,expected_backend:str|None=None,expected_read:str|None=None,expected_device:dict|None=None)->dict:
    directory=Path(directory)
    if not (directory/'COMMITTED').is_file():raise ValueError('run lacks its commit marker')
    s=json.loads((directory/'summary.json').read_text())
    if s['schema']!='atomOS-v3.6-K1-run':raise ValueError('unsupported schema')
    verify_execution_metadata(s,expected_backend=expected_backend,expected_read=expected_read,expected_device=expected_device)
    if s.get('chart')!={'r_min':.25,'r_max':64,'angular_sampling':'periodic_nodes'}:raise ValueError('chart metadata differs from K1')
    for key in ('rows','angles','words','padded_rows','padded_words','epochs','seed'):
        if type(s[key]) is not int:raise ValueError('integer metadata required')
    r,p=s['rows'],s['angles'];w=(p+31)//32;pr=(r+7)//8*8;pw=(w+7)//8*8
    if not (1<=r<=65536 and 1<=p<=65536 and 1<=s['epochs']<=16 and 0<=s['seed']<=U32):raise ValueError('metadata bounds')
    if pr*pw>2**18 or r*w*s['epochs']>2**20 or (s['words'],s['padded_rows'],s['padded_words'])!=(w,pr,pw):raise ValueError('layout/record bounds')
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
            rr,ww=divmod(i,w);m,lane=fixture(s,rr,ww);k=address(rr,ww,pw,s['layout'])
            if m!=[a[k] for a in planes]:raise ValueError(f'fixture plane mismatch at lane {i}')
            if set(row)!=set(lane):raise ValueError('input schema mismatch')
            for key,value in lane.items():
                actual=float(row[key]) if key in ('dr','dp','alpha','interval') else int(row[key])
                if actual!=value:raise ValueError(f'fixture input {key} at lane {i}')
            lanes.append(lane);logical_masks.append(m)
    if len(lanes)!=r*w:raise ValueError('input count mismatch')
    state=[(v['initial_word'],v['initial_q']) for v in lanes];counts=[0,0,0];max_error=0.;rows_checked=0
    integer_digest=hashlib.sha256(b'atomOS:K1:integer-semantic\0'+canonical({k:s[k] for k in ('rows','angles','epochs','seed','mode','profile','fringe')}))
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
            for i,lane in enumerate(lanes):
                row=next(reader,None)
                if row is None:raise ValueError('truncated epoch')
                x,q=state[i];produced=producer(x,lane,s['mode']);valid=(1<<min(32,p-(i%w)*32))-1
                am,nm,bm,fm=logical_masks[i];a,n,h,y=bit_core(produced,am,nm,bm,valid,fm if s['fringe'] else valid)
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
    return dict(status='passed',lane_epochs=rows_checked,integer_semantic_sha256=integer_digest.hexdigest(),max_float_difference_radians=max_error,tolerance_radians=TOL,invariant_counts=counts,backend_recorded=s['backend'])
