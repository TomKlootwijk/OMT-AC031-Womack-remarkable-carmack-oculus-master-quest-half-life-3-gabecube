"""Explicit SATNAV-R1 WGS84/ECEF/ENU additions, not UGTS source definitions."""
import math
A=6378137.0
F=1/298.257223563
E2=F*(2-F)
def geodetic_to_ecef(lat,lon,height):
    if not all(math.isfinite(v)for v in (lat,lon,height))or not -math.pi/2<=lat<=math.pi/2:raise ValueError('geodetic domain')
    n=A/math.sqrt(1-E2*math.sin(lat)**2)
    return ((n+height)*math.cos(lat)*math.cos(lon),(n+height)*math.cos(lat)*math.sin(lon),(n*(1-E2)+height)*math.sin(lat))
def ecef_to_geodetic(x,y,z):
    p=math.hypot(x,y)
    if not all(math.isfinite(v)for v in (x,y,z))or math.hypot(p,z)<1:raise ValueError('ECEF origin/invalid')
    lon=math.atan2(y,x)
    if p<1e-10:return math.copysign(math.pi/2,z),0.,abs(z)-A*(1-F)
    lat=math.atan2(z,p*(1-E2))
    for _ in range(20):
        n=A/math.sqrt(1-E2*math.sin(lat)**2);new=math.atan2(z+E2*n*math.sin(lat),p)
        if abs(new-lat)<1e-14:lat=new;break
        lat=new
    n=A/math.sqrt(1-E2*math.sin(lat)**2);height=p/math.cos(lat)-n if abs(math.cos(lat))>.01 else z/math.sin(lat)-n*(1-E2)
    return lat,lon,height

def enu_matrix(lat,lon):
    s,c=math.sin,math.cos
    return ((-s(lon),c(lon),0.),(-s(lat)*c(lon),-s(lat)*s(lon),c(lat)),(c(lat)*c(lon),c(lat)*s(lon),s(lat)))
def ecef_to_enu(x,origin,lat,lon):
    d=[x[i]-origin[i]for i in range(3)]
    return tuple(sum(row[j]*d[j]for j in range(3))for row in enu_matrix(lat,lon))
def enu_to_ecef(v,origin,lat,lon):
    r=enu_matrix(lat,lon)
    return tuple(origin[j]+sum(r[i][j]*v[i]for i in range(3))for j in range(3))
