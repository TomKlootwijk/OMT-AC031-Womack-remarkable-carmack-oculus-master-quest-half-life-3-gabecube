#!/usr/bin/env python3
"""Generate operator inputs for exact phase comparisons; no VM answers stored."""
from pathlib import Path
import hashlib,json,struct
ROOT=Path(__file__).resolve().parents[1]
MASK=(1<<32)-1
VALUES=[0,1,-1,-(1<<31),(1<<31)-1,4095,4096,4097,-4096,-4097,
        16383,16384,16385,-16384,-16385,1048575,1048576,1048577,-1048576,-1048577]

def main():
    folder=ROOT/'examples/phase18';folder.mkdir(parents=True,exist_ok=True)
    records=[]
    for name,pattern in [('phase_sum',[4,5]),('seam_turn',[3,9,12,11])]:
        count=1024;header=bytearray(128);header[:8]=b'TOMAGI1\0'
        struct.pack_into('<8I',header,8,0x10000,0,count,0,0x19900710,256,48,64)
        initial=[0x80000001,0x7fffffff,0x80000000,0xffffffff,
                 0x80100001,0x7ff00001,17,31,3,1,2,0,0xfedcba98,0,0,0]
        struct.pack_into('<16I',header,64,*initial)
        out=bytearray(header);hist=[0]*16
        for i in range(count):
            op=pattern[i%len(pattern)];hist[op]+=1
            arg=VALUES[(i//len(pattern))%len(VALUES)];flags=0;args=[arg,0,0,0]
            if op==3:args=[arg,1048577,-16385,4097]
            elif op==4:flags=((i//2)%4)<<4
            elif op==9:flags=(i//4)%4
            elif op==12:args=[arg,(i//4)%31,0,0]
            elif op==11:flags=3;args=[arg,1048577,-16385,4097]
            words=[0,i,op,flags,*args,(i+137)%count,(i+349)%count,
                   (0x7feb352d*i)&MASK,(0x846ca68b*(i+1))&MASK]
            out.extend(struct.pack('<12I',*(x&MASK for x in words)))
        path=folder/(name+'.tmg');path.write_bytes(out)
        records.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(out).hexdigest(),bytes=len(out),cells=count,opcode_counts=hist,initial_state_words=initial,successor_offsets=[137,349]))
    recipe=dict(profile='ATOMOS-PHASE-WORKLOAD-R1',generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),argument_values=VALUES,precomputed_vm_outputs=False,workloads=records)
    (ROOT/'review/r18_phase_workloads.json').write_text(json.dumps(recipe,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(recipe,indent=2))
if __name__=='__main__':main()
