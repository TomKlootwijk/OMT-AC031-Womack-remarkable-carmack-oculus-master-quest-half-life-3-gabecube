"""Independent finite UGTS/SCLP mathematical helpers. No navigation actuator API."""
from __future__ import annotations
import math
TAU=2*math.pi
WIDTHS=(20,18,14,12)
SCHEDULE=tuple((field,width-1-depth) for depth in range(20) for field,width in enumerate(WIDTHS) if depth<width)

def wrap(x,period=TAU):
    if not math.isfinite(x) or not math.isfinite(period) or period<=0:raise ValueError('finite angle/positive period required')
    value=x%period
    return value-period if value>=period/2 else value

def pack(fields,layout='contiguous'):
    if len(fields)!=4 or any(type(v) is not int or not 0<=v<(1<<w) for v,w in zip(fields,WIDTHS)):raise ValueError('four bounded integer fields required')
    if layout=='contiguous':return fields[0]<<44|fields[1]<<26|fields[2]<<12|fields[3]
    if layout!='morton':raise ValueError('layout')
    key=0
    for field,bit in SCHEDULE:key=key<<1|((fields[field]>>bit)&1)
    return key

def unpack(key,layout='contiguous'):
    if type(key) is not int or not 0<=key<1<<64:raise ValueError('uint64 key required')
    if layout=='contiguous':return (key>>44,(key>>26)&((1<<18)-1),(key>>12)&16383,key&4095)
    if layout!='morton':raise ValueError('layout')
    fields=[0]*4
    for out,(field,bit) in zip(range(63,-1,-1),SCHEDULE):fields[field]|=((key>>out)&1)<<bit
    return tuple(fields)

def quantize(rho,theta,tick,phi):
    if not all(math.isfinite(v) for v in (rho,theta,phi)) or not -20<=rho<=0:raise ValueError('chart domain')
    if type(tick) is not int or tick<0:raise ValueError('nonnegative full tick')
    return (math.floor((rho+20)/20*((1<<20)-1)+.5),math.floor((theta%TAU)/TAU*(1<<18))%(1<<18),tick%16384,math.floor((phi%TAU)/TAU*4096)%4096)

def prefix_bounds(prefix,bits):
    if type(bits) is not int or not 0<=bits<=64 or type(prefix) is not int or not 0<=prefix<1<<bits:raise ValueError('prefix domain')
    lo=[0]*4;remaining=list(WIDTHS)
    for i,(field,bit) in enumerate(SCHEDULE[:bits]):
        lo[field]|=((prefix>>(bits-1-i))&1)<<bit;remaining[field]-=1
    return tuple((v,v+(1<<r)-1) for v,r in zip(lo,remaining))

def phase_clock(tick,reference,period):
    if any(type(v) is not int for v in (tick,reference,period)) or period<=0:raise ValueError('integer clock arguments')
    wind,rem=divmod(tick-reference,period);return {'winding':wind,'phase':rem/period,'parity':wind%2}

def topology(rho,theta,phi,orientation=1,profile='half_turn'):
    if not all(math.isfinite(v)for v in (rho,theta,phi)) or orientation not in (-1,1):raise ValueError('state domain')
    if profile not in ('half_turn','klein_reflection'):raise ValueError('profile')
    turns=math.floor((rho+20)/20);rho-=20*turns
    if turns%2:theta=theta+math.pi if profile=='half_turn' else math.pi-theta;phi=-phi;orientation=-orientation
    return rho,wrap(theta),wrap(phi),orientation,turns

def metric(rho,r0):
    if not math.isfinite(rho) or not math.isfinite(r0) or r0<=0:raise ValueError('chart parameters')
    return (r0*math.exp(rho))**2

def radial_step(r,delta_rho):return r*math.expm1(delta_rho)

def kinematics(rho,theta,rho_dot,theta_dot,rho_ddot,theta_ddot,r0=1.):
    r=r0*math.exp(rho);c,s=math.cos(theta),math.sin(theta)
    v=(r*(rho_dot*c-theta_dot*s),r*(rho_dot*s+theta_dot*c))
    ar=rho_ddot+rho_dot*rho_dot-theta_dot*theta_dot;at=theta_ddot+2*rho_dot*theta_dot
    a=(r*(ar*c-at*s),r*(ar*s+at*c));return v,a

def tangent(velocity,normal):
    n=math.sqrt(sum(x*x for x in normal))
    if len(velocity)!=len(normal) or n==0:raise ValueError('normal domain')
    unit=[x/n for x in normal];dot=sum(x*y for x,y in zip(velocity,unit));return tuple(x-dot*y for x,y in zip(velocity,unit))

def rank(matrix,tolerance=1e-12):
    if not matrix:return 0
    n=len(matrix[0]);a=[list(map(float,row))for row in matrix]
    if any(len(row)!=n for row in a)or not all(math.isfinite(v)for row in a for v in row):raise ValueError('matrix shape')
    r=0
    for c in range(n):
        pivot=max(range(r,len(a)),key=lambda k:abs(a[k][c]),default=None)
        if pivot is None or abs(a[pivot][c])<=tolerance:continue
        a[r],a[pivot]=a[pivot],a[r];s=a[r][c];a[r]=[x/s for x in a[r]]
        for j in range(r+1,len(a)):
            q=a[j][c];a[j]=[x-q*y for x,y in zip(a[j],a[r])]
        r+=1
        if r==len(a):break
    return r

def release_constraint(matrix,row):
    if not matrix or not 0<=row<len(matrix):raise ValueError('constraint row')
    n=len(matrix[0]);before=n-rank(matrix);after=n-rank(matrix[:row]+matrix[row+1:]);return before,after,after-before

def grammar(depth,branch=0,orientation=1,max_depth=12,max_symbols=32768):
    if type(depth) is not int or not 0<=depth<=max_depth or branch not in (0,1)or orientation not in (-1,1):raise ValueError('grammar arguments')
    if 5*(1<<depth)-4>max_symbols:raise ValueError('symbol capacity')
    turn='+' if (1 if branch==0 else -1)*orientation>0 else '-'
    words=['F']
    for _ in range(depth):
        next_words=[]
        for w in words:next_words.extend(['F','[',turn,'F',']','J'] if w=='F' else [w])
        words=next_words
    return words

def jitter_intervals(f,epsilon,bit):
    if not math.isfinite(f)or not math.isfinite(epsilon)or epsilon<0 or bit not in (0,1):raise ValueError('jitter domain')
    perturbed=f+epsilon*(2*bit-1)
    return {'nominal_uncertainty':(f-epsilon,f+epsilon),'perturbed':perturbed,'recovery_interval':(perturbed-epsilon,perturbed+epsilon)}
