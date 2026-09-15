#!/usr/bin/env python3
"""Materialize a reproducible large Cell48 operator table, not VM results."""
from pathlib import Path
import hashlib
import json
import math
import struct

ROOT=Path(__file__).resolve().parents[1]
MASK=(1<<32)-1


def mix(x):
    x^=x>>16; x=(x*0x7feb352d)&MASK
    x^=x>>15; x=(x*0x846ca68b)&MASK
    return x^(x>>16)


def main():
    recipe=ROOT/'examples/mixed_workload.json'
    p=json.loads(recipe.read_text(encoding='utf-8'))
    assert p['profile']=='ATOMOS-TOMAGI-MIXED-WORKLOAD-R1'
    count=p['cells']; assert type(count) is int and count==1048576
    assert p['successors']==[65537,524287]
    assert all(math.gcd(x,count)==1 for x in p['successors'])
    out=ROOT/'review/workloads/mixed_1048576.tmg';out.parent.mkdir(parents=True,exist_ok=True)
    header=bytearray(128);header[:8]=b'TOMAGI1\0'
    struct.pack_into('<8I',header,8,0x10000,0,count,0,p['seed'],p['ticks'],48,64)
    struct.pack_into('<16I',header,64,*p['initial_state_words'])
    digest=hashlib.sha256();counts=[0]*16
    with out.open('wb') as f:
        f.write(header);digest.update(header)
        for first in range(0,count,8192):
            block=bytearray()
            for i in range(first,min(first+8192,count)):
                op=i%15;counts[op]+=1
                flags=0;args=[0,0,0,0]
                if op==1: flags=4+(i%4);args=[mix(i),0,0,0]
                elif op==2: flags=(i>>4)%8;args=[(i%257)-128,0,0,0]
                elif op==3: args=[3,-5,7,-11]
                elif op==4: flags=48;args=[4097+(i%31),0,0,0]
                elif op==5: args=[16385+(i%31),0,0,0]
                elif op==7: args=[0,524287,i%262144,32768]
                elif op==8: args=[524288,262144,i%4096,1024]
                elif op==9: flags=3
                elif op==10: args=[44+i%20,0,0,0]
                elif op==11: flags=3;args=[-17,19,-23,29]
                elif op==12: args=[127,2,0,0]
                words=[0,i,op,flags,*args,(i+65537)%count,(i+524287)%count,mix(i),mix(i^p['seed'])]
                block.extend(struct.pack('<12I',*(w&MASK for w in words)))
            f.write(block);digest.update(block)
    receipt={'profile':p['profile'],'recipe':recipe.relative_to(ROOT).as_posix(),
             'recipe_sha256':hashlib.sha256(recipe.read_bytes()).hexdigest(),
             'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'derived_path':out.relative_to(ROOT).as_posix(),'bytes':out.stat().st_size,
             'sha256':digest.hexdigest(),'cell_count':count,'opcode_counts':counts,
             'program_only':True,'precomputed_vm_outputs':False,
             'inventory_note':'The derived binary is reproducible and excluded from Git and release archives.'}
    (ROOT/'review/mixed_workload_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
