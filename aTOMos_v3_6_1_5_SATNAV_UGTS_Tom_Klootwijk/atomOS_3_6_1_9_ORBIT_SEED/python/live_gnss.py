"""GPS L1 C/A observation preparation for SATNAV-R1 (LIVE-R1).

All times are full, unwrapped GPS seconds since 1980-01-06. Receiver epoch tags
and code must use the same receiver-clock convention. Sources and equations are
in docs/LIVE_GNSS_MODEL.md. This module does not use station coordinates as truth.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from collections.abc import Iterable, Iterator
import gzip
import math
from typing import TextIO
try:
    from .geodesy import ecef_to_geodetic, enu_matrix
except ImportError:
    from geodesy import ecef_to_geodetic, enu_matrix

C = 299792458.0
MU = 3.986005e14
OMEGA_E = 7.2921151467e-5
RELATIVITY_F = -4.442807633e-10
GPS_WEEK = 604800.0
GPS_EPOCH = datetime(1980, 1, 6)


@dataclass(frozen=True)
class GPSObservation:
    prn: int
    pseudorange_m: float
    code: str = 'C1C'
    sigma_m: float = 3.0
    cn0_dbhz: float | None = None


@dataclass(frozen=True)
class GPSEpoch:
    time_gpst_s: float
    observations: tuple[GPSObservation, ...]
    source_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GPSEphemeris:
    prn: int
    toe: float
    toc: float
    sqrt_a: float
    ecc: float
    i0: float
    omega0: float
    w: float
    m0: float
    delta_n: float
    idot: float
    omega_dot: float
    cuc: float
    cus: float
    crc: float
    crs: float
    cic: float
    cis: float
    af0: float
    af1: float
    af2: float
    tgd: float
    week: int = 0
    iode: int = 0
    iodc: int = 0
    health: int = 0
    ura_m: float = 2.4
    fit_interval_hours: float = 4.0
    source: str = ''


@dataclass
class GPSNavigation:
    ephemerides: list[GPSEphemeris]
    iono_alpha: tuple[float, float, float, float] | None = None
    iono_beta: tuple[float, float, float, float] | None = None
    metadata: dict = field(default_factory=dict)


def calendar_to_gpst(year: int, month: int, day: int, hour: int, minute: int, seconds: float) -> float:
    """RINEX GPS calendar fields: no UTC conversion and no leap-second subtraction."""
    if not math.isfinite(seconds) or not 0 <= seconds < 60:
        raise ValueError('invalid GPS seconds-of-minute')
    return (datetime(year, month, day, hour, minute) - GPS_EPOCH).total_seconds() + seconds


def gpst_to_calendar(time_gpst_s: float) -> str:
    return (GPS_EPOCH + timedelta(seconds=time_gpst_s)).isoformat(timespec='milliseconds') + ' GPST'


def resolve_week(week_mod: int, reference_gpst_s: float, modulus: int = 1024) -> int:
    """Resolve broadcast week using an explicit reception-date reference."""
    if not 0 <= week_mod < modulus or not math.isfinite(reference_gpst_s):
        raise ValueError('invalid broadcast week/reference')
    current = int(reference_gpst_s // GPS_WEEK)
    return week_mod + int(math.floor((current - week_mod) / modulus + 0.5)) * modulus


def _near_week(tow: float, reference: float) -> float:
    if not 0 <= tow < GPS_WEEK:
        raise ValueError('GPS time-of-week outside [0,604800)')
    return tow + GPS_WEEK * math.floor((reference - tow) / GPS_WEEK + 0.5)


def satellite_state(ephemeris: GPSEphemeris, time_gpst_s: float) -> dict:
    """Broadcast satellite ECEF at emission and L1 clock in seconds.

    The caller selects a non-stale ephemeris. Time differences are deliberately
    unwrapped: a record from last week must not masquerade as fresh this week.
    """
    e = ephemeris
    numeric = [getattr(e, k) for k in ('toe','toc','sqrt_a','ecc','i0','omega0','w','m0',
        'delta_n','idot','omega_dot','cuc','cus','crc','crs','cic','cis','af0','af1','af2','tgd')]
    if not all(math.isfinite(x) for x in numeric + [time_gpst_s]) or not 0 <= e.ecc < 1 or e.sqrt_a <= 0:
        raise ValueError('invalid broadcast ephemeris domain')
    a = e.sqrt_a * e.sqrt_a
    tk = time_gpst_s - e.toe
    mean_anomaly = math.remainder(e.m0 + (math.sqrt(MU / a**3) + e.delta_n) * tk, 2 * math.pi)
    eccentric_anomaly = mean_anomaly
    for _ in range(30):
        delta = (eccentric_anomaly - e.ecc * math.sin(eccentric_anomaly) - mean_anomaly) / (1 - e.ecc * math.cos(eccentric_anomaly))
        eccentric_anomaly -= delta
        if abs(delta) < 1e-14:
            break
    else:
        raise ValueError('Kepler iteration did not converge')
    sin_e, cos_e = math.sin(eccentric_anomaly), math.cos(eccentric_anomaly)
    true_anomaly = math.atan2(math.sqrt(1 - e.ecc**2) * sin_e, cos_e - e.ecc)
    phi = true_anomaly + e.w
    sin2, cos2 = math.sin(2*phi), math.cos(2*phi)
    u = phi + e.cus*sin2 + e.cuc*cos2
    radius = a*(1 - e.ecc*cos_e) + e.crs*sin2 + e.crc*cos2
    inclination = e.i0 + e.idot*tk + e.cis*sin2 + e.cic*cos2
    node = e.omega0 + (e.omega_dot - OMEGA_E)*tk - OMEGA_E*(e.toe % GPS_WEEK)
    xp, yp = radius*math.cos(u), radius*math.sin(u)
    cn, sn, ci, si = math.cos(node), math.sin(node), math.cos(inclination), math.sin(inclination)
    position = (xp*cn - yp*ci*sn, xp*sn + yp*ci*cn, yp*si)
    tc = time_gpst_s - e.toc
    polynomial = e.af0 + e.af1*tc + e.af2*tc*tc
    relativity = RELATIVITY_F*e.ecc*e.sqrt_a*sin_e
    return {'position_ecef_m': position, 'clock_polynomial_s': polynomial,
            'relativity_s': relativity, 'tgd_s': e.tgd,
            'clock_l1_s': polynomial + relativity - e.tgd,
            'eccentric_anomaly_rad': eccentric_anomaly, 'time_gpst_s': time_gpst_s}


def rotate_to_reception(position_ecef_m, travel_time_s: float) -> tuple[float, float, float]:
    angle = OMEGA_E*travel_time_s
    ca, sa = math.cos(angle), math.sin(angle)
    x,y,z = position_ecef_m
    return (ca*x + sa*y, -sa*x + ca*y, z)


def azimuth_elevation(receiver_ecef_m, satellite_ecef_m) -> tuple[float, float, tuple[float,float,float]]:
    llh = ecef_to_geodetic(*receiver_ecef_m)
    difference = [satellite_ecef_m[i] - receiver_ecef_m[i] for i in range(3)]
    east,north,up = (sum(row[i]*difference[i] for i in range(3)) for row in enu_matrix(llh[0],llh[1]))
    return math.atan2(east,north) % (2*math.pi), math.atan2(up,math.hypot(east,north)), llh


def klobuchar_delay(time_gpst_s: float, latitude_rad: float, longitude_rad: float,
                    azimuth_rad: float, elevation_rad: float, alpha, beta) -> float:
    """L1 delay in metres. Explicit all-zero coefficients give the 5 ns baseline."""
    if len(alpha) != 4 or len(beta) != 4 or not all(math.isfinite(v) for v in (*alpha,*beta)):
        raise ValueError('Klobuchar needs four finite alpha and beta coefficients')
    if elevation_rad <= 0:
        return 0.0
    lat,lon,el = latitude_rad/math.pi, longitude_rad/math.pi, elevation_rad/math.pi
    psi = 0.0137/(el+0.11)-0.022
    phi = max(-0.416,min(0.416,lat+psi*math.cos(azimuth_rad)))
    lam = lon + psi*math.sin(azimuth_rad)/math.cos(phi*math.pi)
    geomagnetic_lat = phi + 0.064*math.cos((lam-1.617)*math.pi)
    local_time = (43200*lam + time_gpst_s) % 86400
    amplitude = max(0.0,sum(alpha[n]*geomagnetic_lat**n for n in range(4)))
    period = max(72000.0,sum(beta[n]*geomagnetic_lat**n for n in range(4)))
    phase = 2*math.pi*(local_time-50400)/period
    factor = 1 + 16*(0.53-el)**3
    delay = 5e-9
    if abs(phase) < 1.57:
        delay += amplitude*(1 - phase*phase/2 + phase**4/24)
    return C*factor*delay


def saastamoinen_delay(latitude_rad: float, height_m: float, elevation_rad: float,
                       relative_humidity: float = 0.7) -> float:
    """Standard-atmosphere hydrostatic+wet delay, RTKLIB-compatible constants.

    Defined for terrestrial heights [-100,10000] m and positive elevation.
    Negative heights use sea-level weather, recorded by prepare_epoch.
    """
    if not -100 <= height_m <= 10000 or elevation_rad <= 0 or not 0 <= relative_humidity <= 1:
        raise ValueError('Saastamoinen terrestrial-height/elevation/humidity domain')
    h = max(height_m,0.0)
    pressure = 1013.25*(1 - 2.2557e-5*h)**5.2568
    temperature = 15.0 - 6.5e-3*h + 273.16
    vapour = 6.108*relative_humidity*math.exp((17.15*temperature-4684.0)/(temperature-38.45))
    hydro = 0.0022768*pressure/(1 - 0.00266*math.cos(2*latitude_rad) - 0.00028*h/1000)/math.sin(elevation_rad)
    wet = 0.002277*(1255/temperature+0.05)*vapour/math.sin(elevation_rad)
    return hydro+wet


def select_ephemeris(ephemerides: Iterable[GPSEphemeris], prn: int, time_gpst_s: float,
                     max_age_s: float = 7200.0) -> GPSEphemeris:
    records = [e for e in ephemerides if e.prn == prn]
    if not records:
        raise ValueError('missing_ephemeris')
    candidates = []
    for e in records:
        fit_age = e.fit_interval_hours*1800 if e.fit_interval_hours > 0 else max_age_s
        if abs(time_gpst_s-e.toe) <= min(max_age_s,fit_age) and abs(time_gpst_s-e.toc) <= max_age_s:
            candidates.append(e)
    if not candidates:
        raise ValueError('stale_ephemeris')
    # Use the nearest record, including its health. Do not revive an older healthy
    # issue when the nearest broadcast says the SV is unhealthy.
    e = min(candidates,key=lambda e:(abs(time_gpst_s-e.toe),-e.toc))
    if e.health != 0:
        raise ValueError('unhealthy_ephemeris')
    if (e.iodc & 255) != e.iode:
        raise ValueError('inconsistent_issue_of_data')
    return e


def prepare_epoch(epoch: GPSEpoch, ephemerides: Iterable[GPSEphemeris], receiver_ecef_m,
                  receiver_clock_m: float = 0.0, iono_alpha=None, iono_beta=None,
                  min_elevation_deg: float = 10.0, max_ephemeris_age_s: float = 7200.0) -> dict:
    """Prepare current geometry/corrections. Re-run after the native receiver solve.

    Dict observations contain exact existing observations.csv field names plus
    diagnostics. Missing/invalid satellites have explicit rejected records.
    """
    xyz = tuple(float(v) for v in receiver_ecef_m)
    if len(xyz) != 3 or not all(math.isfinite(v) for v in (*xyz, receiver_clock_m, epoch.time_gpst_s)):
        raise ValueError('nonfinite receiver state/time')
    if not 0 <= min_elevation_deg < 90 or max_ephemeris_age_s <= 0:
        raise ValueError('invalid preparation configuration')
    records = tuple(ephemerides)
    radius = math.sqrt(sum(v*v for v in xyz))
    terrestrial = 6e6 < radius < 7e6
    fallback = iono_alpha is None or iono_beta is None
    alpha,beta = (0.,)*4 if fallback else tuple(iono_alpha), (0.,)*4 if fallback else tuple(iono_beta)
    prepared, rejected, seen = [], [], set()
    for observation in sorted(epoch.observations,key=lambda o:o.prn):
        why = None
        if observation.prn in seen:
            raise ValueError(f'duplicate GPS PRN {observation.prn}')
        seen.add(observation.prn)
        if not 1 <= observation.prn <= 32:
            why = 'unsupported_prn'
        elif observation.code not in ('C1C','C1'):
            why = 'unsupported_code_requires_bias_model'
        elif not math.isfinite(observation.pseudorange_m) or observation.pseudorange_m <= 0:
            why = 'invalid_pseudorange'
        elif not math.isfinite(observation.sigma_m) or observation.sigma_m <= 0:
            why = 'invalid_sigma'
        if why:
            rejected.append({'prn':observation.prn,'reason':why});continue
        try:
            # t_rx_tag - raw P/c is the transmit satellite-clock tag. The
            # receiver clock cancels because the two use the same convention.
            transmit_tag = epoch.time_gpst_s - observation.pseudorange_m/C
            e = select_ephemeris(records,observation.prn,transmit_tag,max_ephemeris_age_s)
            transmit = transmit_tag
            for _ in range(3):
                state = satellite_state(e,transmit)
                transmit = transmit_tag - state['clock_l1_s']
            state = satellite_state(e,transmit)
            flight = observation.pseudorange_m/C
            for _ in range(4):
                sat_rx = rotate_to_reception(state['position_ecef_m'],flight)
                flight = math.sqrt(sum((sat_rx[i]-xyz[i])**2 for i in range(3)))/C
            sat_rx = rotate_to_reception(state['position_ecef_m'],flight)
            azimuth = elevation = None
            ionosphere = troposphere = 0.0
            atmosphere_status = 'uninitialized_receiver_geometry'
            if terrestrial:
                azimuth,elevation,llh = azimuth_elevation(xyz,sat_rx)
                if elevation < math.radians(min_elevation_deg):
                    rejected.append({'prn':observation.prn,'reason':'below_elevation_mask',
                                     'elevation_deg':math.degrees(elevation)});continue
                if -100 <= llh[2] <= 10000:
                    ionosphere = klobuchar_delay(epoch.time_gpst_s,llh[0],llh[1],azimuth,elevation,alpha,beta)
                    troposphere = saastamoinen_delay(llh[0],llh[2],elevation)
                    atmosphere_status = 'standard_atmosphere_sea_level_weather' if llh[2] < 0 else 'standard_atmosphere'
                else:
                    atmosphere_status = 'receiver_height_outside_atmosphere_domain'
            correction = C*state['clock_l1_s'] - ionosphere - troposphere
            # Conservative, explicit elevation weighting; CN0 is preserved but
            # has no calibrated sigma conversion in this profile.
            sigma = observation.sigma_m/max(math.sin(elevation),0.1) if elevation is not None else observation.sigma_m
            prepared.append({'channel':observation.prn-1,'satellite_id':f'G{observation.prn:02d}',
                'sx_rx_m':sat_rx[0],'sy_rx_m':sat_rx[1],'sz_rx_m':sat_rx[2],
                'code_m':observation.pseudorange_m,'add_correction_m':correction,'sigma_m':sigma,'ready':1,
                'diagnostics':{'prn':observation.prn,'code':observation.code,'cn0_dbhz':observation.cn0_dbhz,
                    'transmit_time_gpst_s':transmit,'flight_time_s':flight,'clock_l1_s':state['clock_l1_s'],
                    'clock_polynomial_s':state['clock_polynomial_s'],'relativity_s':state['relativity_s'],
                    'tgd_s':state['tgd_s'],'iono_m':ionosphere,'tropo_m':troposphere,
                    'azimuth_deg':None if azimuth is None else math.degrees(azimuth),
                    'elevation_deg':None if elevation is None else math.degrees(elevation),
                    'ephemeris_toe_gpst_s':e.toe,'ephemeris_toc_gpst_s':e.toc,'iode':e.iode,'iodc':e.iodc,
                    'health':e.health,'ephemeris_source':e.source,'ephemeris_age_s':transmit-e.toe,
                    'atmosphere_status':atmosphere_status}})
        except (ValueError,OverflowError,ZeroDivisionError) as exc:
            rejected.append({'prn':observation.prn,'reason':str(exc)})
    return {'time_gpst_s':epoch.time_gpst_s,'receiver_seed_ecef_m':xyz,
            'receiver_seed_clock_m':receiver_clock_m,'observations':prepared,'rejected':rejected,
            'model':{'profile':'LIVE-R1','signal':'GPS L1 C/A','time_scale':'GPST',
                     'iono':'klobuchar_zero_coefficients_5ns_baseline' if fallback else 'broadcast_klobuchar',
                     'tropo':'saastamoinen_standard_atmosphere_rh_0.7',
                     'receiver_geometry_initialized':terrestrial,'min_elevation_deg':min_elevation_deg,
                     'satellite_axes':'transmit_position_rotated_to_reception_ecef',
                     'sigma':'observation_sigma_m / max(sin(elevation),0.1)',
                     'external_differential_code_bias':'not_applied'},'source_metadata':epoch.source_metadata}


def _number(field: str, default: float | None = None) -> float:
    s = field.strip()
    if not s:
        if default is None:
            raise ValueError('missing required RINEX numeric field')
        return default
    value = float(s.replace('D','E').replace('d','e'))
    if not math.isfinite(value):
        raise ValueError('nonfinite RINEX numeric field')
    return value


def _open_text(path):
    return gzip.open(path,'rt',encoding='ascii') if str(path).lower().endswith('.gz') else open(path,encoding='ascii')


def _read_header(stream: TextIO) -> tuple[list[str],float]:
    first = stream.readline()
    if not first or 'RINEX VERSION / TYPE' not in first:
        raise ValueError('missing RINEX version header')
    version = float(first[:9])
    if not 2 <= version < 4:
        raise ValueError('only RINEX 2.x/3.x are supported')
    lines = [first.rstrip('\r\n')]
    for raw in stream:
        line = raw.rstrip('\r\n')
        lines.append(line)
        if line[60:].strip() == 'END OF HEADER':
            return lines,version
    raise ValueError('truncated RINEX header')


def read_rinex_nav(path) -> GPSNavigation:
    """Read GPS LNAV records; consume and explicitly count other GNSS records."""
    with _open_text(path) as stream:
        lines,version = _read_header(stream)
        alpha = beta = None
        metadata = {'source':str(path),'rinex_version':version,'ignored_other_gnss_records':0}
        for line in lines:
            label = line[60:].strip()
            if label in ('ION ALPHA','ION BETA'):
                values = tuple(_number(line[2+12*i:14+12*i]) for i in range(4))
                if label == 'ION ALPHA': alpha = values
                else: beta = values
            elif label == 'IONOSPHERIC CORR' and line[:4] in ('GPSA','GPSB'):
                values = tuple(_number(line[5+12*i:17+12*i]) for i in range(4))
                if line[:4] == 'GPSA': alpha = values
                else: beta = values
        records = []
        for raw in stream:
            first = raw.rstrip('\r\n')
            if not first.strip():continue
            system = first[0] if version >= 3 else 'G'
            following = 3 if system in ('R','S') else 7
            rest = [stream.readline().rstrip('\r\n') for _ in range(following)]
            if any(not line for line in rest):raise ValueError('truncated navigation record')
            if system != 'G':
                metadata['ignored_other_gnss_records'] += 1;continue
            if version >= 3:
                prn = int(first[1:3]); date = first[3:23].split(); offset=23; indent=4
                year,month,day,hour,minute = map(int,date[:5]);second=float(date[5])
            else:
                prn=int(first[:2]);date=first[2:22].split();offset=22;indent=3
                year,month,day,hour,minute = map(int,date[:5]);second=float(date[5])
                year += 2000 if year < 80 else 1900
            toc = calendar_to_gpst(year,month,day,hour,minute,second)
            clock=[_number(first[offset+19*i:offset+19*(i+1)]) for i in range(3)]
            values=[[_number(line[indent+19*i:indent+19*(i+1)],0.0) for i in range(4)] for line in rest]
            week=int(values[4][2])
            # RINEX GPS weeks are continuous. Historic writers sometimes emit
            # the 10-bit value, which is resolved from their absolute toc date.
            if week < 1024:week=resolve_week(week,toc)
            toe = week*GPS_WEEK + values[2][0]
            records.append(GPSEphemeris(prn=prn,toe=toe,toc=toc,sqrt_a=values[1][3],ecc=values[1][1],
                i0=values[3][0],omega0=values[2][2],w=values[3][2],m0=values[0][3],
                delta_n=values[0][2],idot=values[4][0],omega_dot=values[3][3],
                cuc=values[1][0],cus=values[1][2],crc=values[3][1],crs=values[0][1],
                cic=values[2][1],cis=values[2][3],af0=clock[0],af1=clock[1],af2=clock[2],
                tgd=values[5][2],week=week,iode=int(values[0][0]),iodc=int(values[5][3]),
                health=int(values[5][1]),ura_m=values[5][0],fit_interval_hours=values[6][1] or 4.0,
                source=str(path)))
        metadata['gps_records']=len(records)
        return GPSNavigation(records,alpha,beta,metadata)


class RinexObservationReader:
    """Incremental RINEX 2/3 observation reader, selecting C1 / C1C only.

    The caller owns the input stream. Non-GPS observations are consumed; no
    constellation timescale or alternate-signal bias is guessed.
    """
    def __init__(self, stream: TextIO, source: str = ''):
        self.stream=stream
        self._pending=None
        lines,self.version=_read_header(stream)
        self.obs_types={}
        self.metadata={'source':source,'rinex_version':self.version,'time_scale':'GPS',
                       'approx_ecef_role':'seed_only_not_truth','approx_ecef_m':None,
                       'receiver_clock_offsets_applied':0}
        self._apply_header(lines)

    def _apply_header(self, lines):
        reset_systems=set()
        for line in lines:
            label=line[60:].strip()
            if label == 'APPROX POSITION XYZ':
                self.metadata['approx_ecef_m']=tuple(_number(line[14*i:14*(i+1)]) for i in range(3))
            elif label == 'MARKER NAME':self.metadata['marker_name']=line[:60].strip()
            elif label == 'REC # / TYPE / VERS':self.metadata['receiver']=line[:60].strip()
            elif label == 'ANT # / TYPE':self.metadata['antenna']=line[:60].strip()
            elif label == 'ANTENNA: DELTA H/E/N':self.metadata['antenna_delta_hen_m']=tuple(_number(line[14*i:14*(i+1)],0) for i in range(3))
            elif label == 'RCV CLOCK OFFS APPL':self.metadata['receiver_clock_offsets_applied']=int(line[:6])
            elif label == 'TIME OF FIRST OBS':
                self.metadata['time_scale']=line[48:51].strip() or 'GPS'
            elif label == '# / TYPES OF OBSERV':
                if 'G' not in reset_systems:self.obs_types['G']=[];reset_systems.add('G')
                self.obs_types.setdefault('G',[]).extend(line[i:i+6].strip() for i in range(6,60,6) if line[i:i+6].strip())
            elif label == 'SYS / # / OBS TYPES':
                system=line[0]
                if system != ' ':last_system=system
                else:system=last_system
                if system not in reset_systems:self.obs_types[system]=[];reset_systems.add(system)
                self.obs_types.setdefault(system,[]).extend(line[i:i+4].strip() for i in range(7,59,4) if line[i:i+4].strip())
        if self.metadata['time_scale'] not in ('GPS','GPST'):
            raise ValueError('GPS observation epoch time scale required')
        if 'G' not in self.obs_types:raise ValueError('no GPS observation type header')

    def _observation(self, prn: int, types: list[str], fields: list[str]) -> GPSObservation | None:
        code='C1C' if 'C1C' in types else 'C1' if 'C1' in types else None
        if code is None:return None
        raw=fields[types.index(code)][:14]
        if not raw.strip():return None
        value=_number(raw)
        if value <= 0:return None
        signal='S1C' if code == 'C1C' else 'S1'
        cn0=None
        if signal in types:
            raw_cn0=fields[types.index(signal)][:14]
            if raw_cn0.strip():cn0=_number(raw_cn0)
        return GPSObservation(prn,value,code,3.0,cn0)

    def __iter__(self) -> Iterator[GPSEpoch]:
        return self._v3() if self.version >= 3 else self._v2()

    def _readline(self):
        if self._pending is not None:
            line,self._pending=self._pending,None
            return line
        return self.stream.readline()

    def _v3(self):
        while True:
            raw=self._readline()
            if not raw:return
            if not raw.strip():continue
            if not raw.startswith('>'):raise ValueError('missing RINEX 3 epoch marker')
            parts=raw[1:].split()
            year,month,day,hour,minute=map(int,parts[:5]);second=float(parts[5]);flag=int(parts[6]);count=int(parts[7])
            if flag not in (0,1,6):
                events=[self._readline() for _ in range(count)]
                if any(not row for row in events):raise ValueError('truncated RINEX event')
                if flag == 4:self._apply_header(events)
                continue
            observations=[]
            for _ in range(count):
                line=self._readline().rstrip('\r\n')
                if not line:raise ValueError('truncated RINEX 3 observations')
                satellite=line[:3];system=line[0];types=self.obs_types.get(system)
                if types is None:raise ValueError(f'missing observation types for {system}')
                payload=line[3:]
                # Full-width records and optional three-space-prefixed wrapped
                # records are both consumed without seeking a live input stream.
                while len(payload)<16*len(types):
                    following=self._readline()
                    if following.startswith('   '):
                        payload=payload.ljust(((len(payload)+15)//16)*16)
                        payload+=following.rstrip('\r\n')[3:]
                    else:
                        self._pending=following
                        break
                payload=payload.ljust(16*len(types))
                fields=[payload[i*16:(i+1)*16] for i in range(len(types))]
                if system == 'G' and flag != 6:
                    observation=self._observation(int(satellite[1:]),types,fields)
                    if observation:observations.append(observation)
            if flag == 6:continue
            metadata=dict(self.metadata);metadata['epoch_flag']=flag
            if len(parts)>8:metadata['reported_receiver_clock_offset_s']=float(parts[8])
            yield GPSEpoch(calendar_to_gpst(year,month,day,hour,minute,second),tuple(observations),metadata)

    def _v2(self):
        types=self.obs_types['G']
        for raw in self.stream:
            if not raw.strip():continue
            flag=int(raw[28:29]);count=int(raw[29:32])
            if flag not in (0,1,6):
                events=[self.stream.readline() for _ in range(count)]
                if any(not row for row in events):raise ValueError('truncated RINEX event')
                if flag == 4:self._apply_header(events);types=self.obs_types['G']
                continue
            year=int(raw[1:3]);year+=2000 if year<80 else 1900
            month,day,hour,minute=(int(raw[a:b]) for a,b in ((4,6),(7,9),(10,12),(13,15)))
            second=float(raw[15:26])
            satellites=[raw[i:i+3].strip() for i in range(32,min(68,32+count*3),3)]
            while len(satellites)<count:
                line=self.stream.readline()
                if not line:raise ValueError('truncated RINEX 2 satellite list')
                satellites.extend(line[i:i+3].strip() for i in range(32,min(68,32+(count-len(satellites))*3),3))
            observations=[]
            for satellite in satellites:
                payload=''
                for _ in range((len(types)+4)//5):
                    line=self.stream.readline()
                    if not line:raise ValueError('truncated RINEX 2 observation record')
                    payload+=line.rstrip('\r\n').ljust(80)
                fields=[payload[i*16:(i+1)*16] for i in range(len(types))]
                if satellite.startswith('G') or satellite.isdigit():
                    observation=self._observation(int(satellite.lstrip('G')),types,fields)
                    if observation:observations.append(observation)
            if flag == 6:continue
            metadata=dict(self.metadata);metadata['epoch_flag']=flag
            if raw[68:80].strip():metadata['reported_receiver_clock_offset_s']=_number(raw[68:80])
            yield GPSEpoch(calendar_to_gpst(year,month,day,hour,minute,second),tuple(observations),metadata)


def iter_rinex_obs(path) -> Iterator[GPSEpoch]:
    with _open_text(path) as stream:
        yield from RinexObservationReader(stream,source=str(path))
