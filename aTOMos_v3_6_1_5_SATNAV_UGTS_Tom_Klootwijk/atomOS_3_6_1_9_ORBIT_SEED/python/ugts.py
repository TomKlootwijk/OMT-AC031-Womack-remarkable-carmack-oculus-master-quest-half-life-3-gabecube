"""Source-mapped UGTS/SCLP helpers. These are not a GNSS measurement model."""
from __future__ import annotations
import hashlib,json,math

WIDTHS=(20,18,14,12)
SCHEDULE=tuple((field,WIDTHS[field]-1-depth) for depth in range(max(WIDTHS)) for field in range(4) if depth<WIDTHS[field])

def validate_tuple(q):
    if len(q)!=4 or any(type(v) is not int or not 0<=v<1<<w for v,w in zip(q,WIDTHS)):raise ValueError('20/18/14/12 unsigned tuple required')

def contiguous(q):
    validate_tuple(q);return (q[0]<<44)|(q[1]<<26)|(q[2]<<12)|q[3]
def decode_contiguous(k):
    if type(k) is not int or not 0<=k<1<<64:raise ValueError('uint64 required')
    return ((k>>44)&((1<<20)-1),(k>>26)&((1<<18)-1),(k>>12)&((1<<14)-1),k&4095)
def morton(q):
    validate_tuple(q);out=0
    for f,b in SCHEDULE:out=(out<<1)|((q[f]>>b)&1)
    return out
def decode_morton(k):
    if type(k) is not int or not 0<=k<1<<64:raise ValueError('uint64 required')
    q=[0]*4
    for j,(f,b) in enumerate(SCHEDULE):q[f]|=((k>>(63-j))&1)<<b
    return tuple(q)
def prefix_bounds(prefix,length):
    if type(length)is not int or not 0<=length<=64 or type(prefix)is not int or not 0<=prefix<1<<length:raise ValueError('prefix/range')
    lows=[0]*4;known=[0]*4
    for j,(f,b)in enumerate(SCHEDULE[:length]):
        value=(prefix>>(length-1-j))&1;lows[f]|=value<<b;known[f]|=1<<b
    return [(lows[i],lows[i]|(((1<<WIDTHS[i])-1)^known[i]))for i in range(4)]
def wrap(x,period=2*math.pi):
    if not math.isfinite(x)or not math.isfinite(period)or period<=0:raise ValueError('finite angle/period')
    r=math.fmod(x,period)
    if r>=period/2:r-=period
    if r< -period/2:r+=period
    return 0.0 if r==0 else r

def quantize(rho,theta,tick,phi):
    if not all(math.isfinite(v)for v in (rho,theta,phi))or not -20<=rho<=0 or type(tick)is not int:raise ValueError('quantization domain')
    def angle(a,w):return int(math.floor((a%(2*math.pi))*(1<<w)/(2*math.pi)+.5))% (1<<w)
    q=(int(math.floor((rho+20)/20*((1<<20)-1)+.5)),angle(theta,18),tick%(1<<14),angle(phi,12));validate_tuple(q);return q

def phase_winding(tick,reference,period):
    if any(type(v)is not int for v in (tick,reference,period))or period<=0:raise ValueError('integer ticks and positive period')
    w,remainder=divmod(tick-reference,period);return w,remainder/period

def segment_distance(p,a,b):
    d=[b[i]-a[i]for i in range(len(p))];den=sum(v*v for v in d)
    t=0 if den==0 else max(0.,min(1.,sum((p[i]-a[i])*d[i]for i in range(len(p)))/den))
    return math.sqrt(sum((p[i]-a[i]-t*d[i])**2 for i in range(len(p))))

def cone_sdf(point,apex,axis,slant,half_angle):
    if len(point)!=3 or len(apex)!=3 or len(axis)!=3 or not all(math.isfinite(x)for x in (*point,*apex,*axis,slant,half_angle)):raise ValueError('finite cone input')
    if slant<=0 or not 0<half_angle<math.pi/2 or abs(sum(x*x for x in axis)-1)>1e-10:raise ValueError('cone/axis domain')
    v=[point[i]-apex[i]for i in range(3)];z=sum(v[i]*axis[i]for i in range(3));q=math.sqrt(sum((v[i]-z*axis[i])**2 for i in range(3)))
    h=slant*math.cos(half_angle);radius=slant*math.sin(half_angle);verts=[(-radius,h),(radius,h),(0.,0.)]
    distance=min(segment_distance((q,z),verts[i],verts[(i+1)%3])for i in range(3))
    inside=0<=z<=h and q<=z*math.tan(half_angle)
    return -distance if inside else distance

def translated_sweep_interval(point,apex,axis,slant,angle,start,end,samples):
    if type(samples)is not int or samples<2:raise ValueError('at least two samples')
    values=[]
    for i in range(samples):
        s=[start[j]+i*(end[j]-start[j])/(samples-1)for j in range(3)]
        values.append(cone_sdf([point[j]-s[j]for j in range(3)],apex,axis,slant,angle))
    length=math.sqrt(sum((end[j]-start[j])**2 for j in range(3)));m=min(values)
    return {'lower':m-length/(2*(samples-1)),'upper':m,'scope':'analytic translation bound evaluated in float; not directed-rounding interval arithmetic'}

def perturbation_records(f,epsilon,bit):
    if not math.isfinite(f)or not math.isfinite(epsilon)or epsilon<0 or type(bit)is not int or bit not in (0,1):raise ValueError('perturbation domain')
    perturbed=f+epsilon*(2*bit-1)
    return {'f':f,'f_j':perturbed,'family_interval':[f-epsilon,f+epsilon],
            'measurement_centered_interval':[perturbed-epsilon,perturbed+epsilon]}

def topology(rho,theta,phi,orientation,profile,lo=-20.,hi=0.):
    if not all(math.isfinite(v)for v in (rho,theta,phi,lo,hi))or hi<=lo or orientation not in (-1,1):raise ValueError('topology domain')
    wraps=math.floor((rho-lo)/(hi-lo));r=rho-wraps*(hi-lo)
    if profile not in ('source_half_turn','reflective_klein'):raise ValueError('separate topology profile required')
    if wraps%2:theta=theta+math.pi if profile=='source_half_turn' else math.pi-theta;phi=-phi;orientation=-orientation
    return r,wrap(theta),wrap(phi),orientation,wraps

def otan2_source(delta_phase,delta_rho,axis=0.):
    if not all(math.isfinite(v)for v in (delta_phase,delta_rho,axis)):return {'status':'nonfinite_input','value':None}
    if delta_phase==delta_rho==0:return {'status':'zero_increment','value':None}
    if delta_rho==0:return {'status':'ratio_undefined','value':None}
    q=delta_phase/delta_rho
    if not math.isfinite(q)or (q==0 and delta_phase!=0):return {'status':'numerical_range','value':None}
    return {'status':'defined','value':math.atan(q)-axis}

def digest(record,domain='atomOS:SATNAV:3.6.1.6'):
    b=json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return hashlib.sha256(domain.encode()+b'\0'+len(b).to_bytes(8,'big')+b).hexdigest()

