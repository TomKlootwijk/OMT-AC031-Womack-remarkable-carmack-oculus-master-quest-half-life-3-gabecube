# LIVE-R1 GPS observation model, 3.6.1.8

`python/live_gnss.py` supplies the missing GPS L1 C/A preparation layer before the
native four-state SATNAV solver. It accepts GPS LNAV ephemerides and raw code from
RINEX 2/3 or the RTCM adapter. All orbital angles are radians, distances metres,
and times full GPS seconds since 1980-01-06. Calendar fields already labelled GPS
receive no UTC/leap-second conversion. A broadcast 10-bit week needs an explicit
reception-date reference; ephemeris age uses unwrapped time.

## Orbit and satellite clock

Let $A=(\sqrt A)^2$, $t_k=t-t_{oe}$, and
$M=M_0+(\sqrt{\mu/A^3}+\Delta n)t_k$, with
$\mu=3.986005\,10^{14}\;\mathrm{m^3s^{-2}}$.
Newton iteration solves $E-e\sin E=M$ to an increment below $10^{-14}$ rad
(maximum 30 iterations). Define

\[
\nu=\operatorname{atan2}(\sqrt{1-e^2}\sin E,\cos E-e),\quad \phi=\nu+\omega,
\]
\[
u=\phi+C_{us}\sin2\phi+C_{uc}\cos2\phi,\quad
r=A(1-e\cos E)+C_{rs}\sin2\phi+C_{rc}\cos2\phi,
\]
\[
i=i_0+\dot i\,t_k+C_{is}\sin2\phi+C_{ic}\cos2\phi,
\quad \Omega=\Omega_0+(\dot\Omega-\omega_e)t_k-\omega_e(t_{oe}\bmod604800).
\]

For $x'=r\cos u,y'=r\sin u$, emission ECEF is
$(x'\cos\Omega-y'\cos i\sin\Omega,
x'\sin\Omega+y'\cos i\cos\Omega,y'\sin i)$.
The L1 code clock is

\[
\delta t_{s,L1}=a_{f0}+a_{f1}(t-t_{oc})+a_{f2}(t-t_{oc})^2
-4.442807633\,10^{-10}e\sqrt A\sin E-T_{GD}.
\]

These are the LNAV orbit, relativity and L1 group-delay equations in
[IS-GPS-200N, sections 20.3.3.3.3 and 20.3.3.4.3](https://www.gps.gov/sites/default/files/2025-07/IS-GPS-200N.pdf).
The implementation follows their physical units and signs; constants are explicit.

## Emission time and Earth rotation

Raw receiver time $t_r^{tag}$ and code $P$ share the same receiver-clock convention.
Thus $t_s^{tag}=t_r^{tag}-P/c$ cancels receiver-clock bias. Three clock iterations
use $t_s=t_s^{tag}-\delta t_{s,L1}(t_s)$. The subsequent receiver clock estimate
must not be subtracted from this expression again.

With $\omega_e=7.2921151467\,10^{-5}\;\mathrm{rad/s}$, rotate emission ECEF into
reception axes using

\[
R(\omega_e\tau)=\begin{pmatrix}\cos a&\sin a&0\\-\sin a&\cos a&0\\0&0&1\end{pmatrix},
\qquad \tau=\|R(\omega_e\tau)x_s-x_r\|/c.
\]

Four range iterations determine $\tau$. The native kernel receives rotated
coordinates and never rotates them again. See ESA's
[emission-time algorithm](https://gssc.esa.int/navipedia/index.php/Emission_Time_Computation)
and [reception-frame satellite coordinates](https://gssc.esa.int/navipedia/index.php/Satellite_Coordinates_Computation).

## Atmosphere, weighting and native equation

Latitude/longitude come from WGS84 ECEF, and the ENU line of sight supplies azimuth
$A_z$ and elevation $E_l$. GPS Klobuchar uses semicircle arguments $\varphi/\pi$,
$\lambda/\pi$ and $E_l/\pi$. It computes the pierce point, geomagnetic latitude,
local time, amplitude and period, then

\[
I=cF\begin{cases}5\,10^{-9}+A_I(1-X^2/2+X^4/24),&|X|<1.57,\\
5\,10^{-9},&\text{otherwise},\end{cases}\quad
F=1+16(0.53-E_l/\pi)^3.
\]

Missing alpha/beta coefficients are explicitly labelled
`klobuchar_zero_coefficients_5ns_baseline`; this is a positive baseline delay,
not a measured calibration or zero ionosphere. The full coefficient computation
is in [ESA's Klobuchar model](https://gssc.esa.int/navipedia/index.php/Klobuchar_Ionospheric_Model).

The standard-atmosphere Saastamoinen implementation uses relative humidity 0.7,
$h_0=\max(h,0)$ metres, $p=1013.25(1-2.2557\,10^{-5}h_0)^{5.2568}$ hPa,
$T=288.16-0.0065h_0$ K, and
$e_w=6.108(0.7)\exp[(17.15T-4684)/(T-38.45)]$ hPa:

\[
T_d=\frac{0.0022768p}{(1-0.00266\cos2\varphi-0.00028h_0/1000)\sin E_l}
+\frac{0.002277(1255/T+0.05)e_w}{\sin E_l}.
\]

Its terrestrial domain is $-100\leq h\leq10000$ m and $E_l>0$. The equations and
constants match the pinned independent [RTKLIB `tropmodel` implementation](https://github.com/tomojitakasu/RTKLIB/blob/71db0ffa/src/rtkcmn.c).
The profile uses nominal $\sigma=\sigma_0/\max(\sin E_l,0.1)$, default
$\sigma_0=3$ m. CN0 is retained without inventing a calibrated variance conversion.

The native observation is exactly

\[
P_{corr}=P+c\delta t_{s,L1}-I-T_d=\|x_r-x_s^{rx}\|+b_r+\epsilon.
\]

The outer loop recomputes orbit-frame/atmospheric geometry after each native
position solution. Initial ECEF zero enables orbit/clock preparation with all
available satellites and explicitly uninitialized atmosphere; the solved Earth
position enables the elevation mask and atmosphere on the next pass. The header
approximate coordinate and RTCM reference ARP are metadata, not truth. A strong
cold-start validation must not use either as its seed.

## Data decisions and evidence

Only GPS C1/C1C is selected. Alternate L1 codes require an explicit differential
code-bias treatment and are rejected here. RINEX GPS time, receiver-clock-offset
flags, original pseudoranges, available CN0 and station metadata are preserved.
RINEX 2/3 observation records are streamed, including wrapped RINEX 3 lines,
header updates and cycle-slip events. Other constellations are consumed and
excluded. Formats follow [IGS RINEX 2.11](https://files.igs.org/pub/data/format/rinex211.txt)
and [IGS RINEX 3.05](https://files.igs.org/pub/data/format/rinex305.pdf).

Ephemeris selection requires matching PRN, consistent IODE/IODC, healthy status,
and both clock and orbit age within 7200 seconds; a shorter declared half-fit
interval tightens the orbit limit. A nearer unhealthy issue does not revive an
older healthy issue. Rejections and all correction components remain explicit.
This is single-point GPS code positioning: no carrier-phase ambiguities, RTK,
PPP, calibrated receiver/antenna code biases or protection-level certification.

Validation is separated into analytic equations, independent orbit/clock answers,
recorded real observations, and actual internet receiver stream execution.
`results/gnss_math_oracle.json` compares eight first-epoch emission states against
the pinned RTKLIB trace; complete native and network execution evidence belongs
to the runtime validation reports. No coordinate from a remote reference station
locates the user's computer.
