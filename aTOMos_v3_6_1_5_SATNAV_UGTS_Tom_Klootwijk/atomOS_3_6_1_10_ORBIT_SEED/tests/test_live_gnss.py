"""LIVE-R1 equation, parser, and failure-path checks (stdlib unittest)."""
from dataclasses import replace
import io
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.live_gnss import (C,MU,OMEGA_E,RELATIVITY_F,GPS_WEEK,GPSEphemeris,
    GPSEpoch,GPSObservation,RinexObservationReader,calendar_to_gpst,resolve_week,
    satellite_state,rotate_to_reception,klobuchar_delay,saastamoinen_delay,
    prepare_epoch,select_ephemeris,read_rinex_nav,iter_rinex_obs)


def circular(**kw):
    values=dict(prn=1,toe=GPS_WEEK*2200,toc=GPS_WEEK*2200,sqrt_a=math.sqrt(26560000),
        ecc=0,i0=0,omega0=0,w=0,m0=0,delta_n=0,idot=0,omega_dot=0,
        cuc=0,cus=0,crc=0,crs=0,cic=0,cis=0,af0=0,af1=0,af2=0,tgd=0)
    values.update(kw)
    return GPSEphemeris(**values)


def header(value,label):
    return value.ljust(60)+label+'\n'


def obsfield(value):
    return (' '*14 if value is None else f'{value:14.3f}')+'  '


def obs3(types='C1C L1C D1C S1C C2W',count=5):
    return (header('     3.05           OBSERVATION DATA    M','RINEX VERSION / TYPE')+
        header(f'G  {count:3d} '+''.join(f'{s:4}' for s in types.split()),'SYS / # / OBS TYPES')+
        header('','END OF HEADER'))


class BroadcastMath(unittest.TestCase):
    def test_circular_orbit_closed_form(self):
        e=circular()
        for dt in (0,1,1200,7100):
            state=satellite_state(e,e.toe+dt)
            angle=(math.sqrt(MU/26560000**3)-OMEGA_E)*dt
            expected=(26560000*math.cos(angle),26560000*math.sin(angle),0)
            for got,want in zip(state['position_ecef_m'],expected):self.assertAlmostEqual(got,want,places=7)
            self.assertEqual(state['clock_l1_s'],0)

    def test_kepler_residual_clock_relativistic_tgd(self):
        e=circular(ecc=.15,m0=1.2,af0=2e-4,af1=-2e-12,af2=3e-18,tgd=-7e-9)
        dt=2345
        state=satellite_state(e,e.toe+dt)
        eccentric=state['eccentric_anomaly_rad']
        mean=e.m0+math.sqrt(MU/(e.sqrt_a**2)**3)*dt
        self.assertAlmostEqual(eccentric-e.ecc*math.sin(eccentric),mean,places=13)
        expected=e.af0+e.af1*dt+e.af2*dt**2+RELATIVITY_F*e.ecc*e.sqrt_a*math.sin(eccentric)-e.tgd
        self.assertAlmostEqual(state['clock_l1_s'],expected,places=17)
        self.assertEqual(state['tgd_s'],e.tgd)

    def test_harmonics_and_inclination_at_perigee(self):
        e=circular(ecc=.1,i0=.7,crc=100,cuc=.002,cic=.003)
        state=satellite_state(e,e.toe)
        radius=26560000*.9+100
        expected=(radius*math.cos(.002),radius*math.sin(.002)*math.cos(.703),radius*math.sin(.002)*math.sin(.703))
        for got,want in zip(state['position_ecef_m'],expected):self.assertAlmostEqual(got,want,places=7)

    def test_reception_rotation_sign_and_norm(self):
        original=(23000000.,12000000.,6000000.)
        rotated=rotate_to_reception(original,.08)
        self.assertLess(rotated[1],original[1])
        self.assertGreater(rotated[0],original[0])
        self.assertAlmostEqual(math.dist((0,0,0),rotated),math.dist((0,0,0),original),places=7)
        restored=rotate_to_reception(rotated,-.08)
        for got,want in zip(restored,original):self.assertAlmostEqual(got,want,places=7)

    def test_zero_iono_is_not_zero_delay(self):
        for elevation in (.2,.7,math.pi/2):
            expected=C*5e-9*(1+16*(.53-elevation/math.pi)**3)
            self.assertAlmostEqual(klobuchar_delay(12345,.8,.4,1.7,elevation,[0]*4,[0]*4),expected,places=12)

    def test_iono_daily_period_and_negative_amplitude(self):
        args=(.8,.4,1.7,.6,[1e-8,2e-8,3e-8,4e-8],[90000,10000,0,0])
        self.assertAlmostEqual(klobuchar_delay(12345,*args),klobuchar_delay(12345+86400,*args),places=12)
        self.assertAlmostEqual(klobuchar_delay(12345,.8,.4,1.7,.6,[-1]*4,[0]*4),
                               klobuchar_delay(12345,.8,.4,1.7,.6,[0]*4,[0]*4),places=12)

    def test_troposphere_height_elevation_and_domain(self):
        zenith=saastamoinen_delay(.8,0,math.pi/2)
        self.assertTrue(2.3<zenith<2.7)
        self.assertAlmostEqual(saastamoinen_delay(.8,0,math.pi/6),2*zenith,places=12)
        self.assertLess(saastamoinen_delay(.8,1000,math.pi/2),zenith)
        self.assertEqual(saastamoinen_delay(.8,-50,math.pi/2),zenith)
        for height in (-101,10001):
            with self.assertRaises(ValueError):saastamoinen_delay(.8,height,.4)

    def test_full_week_not_modular_stale(self):
        e=circular()
        self.assertEqual(select_ephemeris([e],1,e.toe+100),e)
        with self.assertRaisesRegex(ValueError,'stale'):select_ephemeris([e],1,e.toe+GPS_WEEK)
        with self.assertRaisesRegex(ValueError,'unhealthy'):select_ephemeris([replace(e,health=1)],1,e.toe)
        with self.assertRaisesRegex(ValueError,'issue'):select_ephemeris([replace(e,iodc=1)],1,e.toe)
        self.assertEqual(resolve_week(1,2049*GPS_WEEK),2049)
        self.assertEqual(calendar_to_gpst(1980,1,6,0,0,0),0)

    def test_nominal_fit_interval_and_no_healthy_resurrection(self):
        e=circular()
        with self.assertRaisesRegex(ValueError,'stale'):select_ephemeris([e],1,e.toe+7201,10000)
        newer=replace(e,toe=e.toe+100,toc=e.toc+100,health=1)
        with self.assertRaisesRegex(ValueError,'unhealthy'):select_ephemeris([e,newer],1,e.toe+99)

    def test_prep_coldstart_explicit_and_correction_sign(self):
        e=circular(af0=2e-4,tgd=2e-9)
        epoch=GPSEpoch(e.toe,(GPSObservation(1,2.1e7),))
        result=prepare_epoch(epoch,[e],(0,0,0))
        self.assertFalse(result['model']['receiver_geometry_initialized'])
        self.assertIn('5ns',result['model']['iono'])
        row=result['observations'][0]
        self.assertAlmostEqual(row['add_correction_m'],C*(e.af0-e.tgd),places=8)
        self.assertEqual(row['diagnostics']['iono_m'],0)
        self.assertEqual(row['channel'],0)
        self.assertEqual(row['code_m'],2.1e7)
        # Receiver clock seed does not get subtracted twice from raw P or tx.
        again=prepare_epoch(epoch,[e],(0,0,0),500000)
        self.assertEqual(row,again['observations'][0])

    def test_rejections_and_duplicate_instead_of_silent_overwrite(self):
        e=circular()
        epoch=GPSEpoch(e.toe,(GPSObservation(1,2.1e7,'C1W'),GPSObservation(2,2.1e7),GPSObservation(3,float('nan'))))
        result=prepare_epoch(epoch,[e],(0,0,0))
        self.assertEqual([row['reason'] for row in result['rejected']],
            ['unsupported_code_requires_bias_model','missing_ephemeris','invalid_pseudorange'])
        with self.assertRaisesRegex(ValueError,'duplicate'):
            prepare_epoch(GPSEpoch(e.toe,(GPSObservation(1,2e7),GPSObservation(1,2e7))),[e],(0,0,0))


class RinexReaders(unittest.TestCase):
    def test_rinex3_long_and_wrapped_and_missing_last_fields(self):
        text=obs3()+'> 2022 03 06 00 00 00.0000000  0  2\n'
        text+='G01'+''.join(obsfield(v) for v in (21000000,1,2,45,None))+'\n'
        text+='G02'+''.join(obsfield(v) for v in (22000000,1,2,46))+'\n'
        text+='   '+obsfield(23000000)+'\n'
        text+='> 2022 03 06 00 00 01.0000000  0  1\n'
        text+='G03'+obsfield(24000000)+'\n'
        reader=RinexObservationReader(io.StringIO(text))
        epochs=list(reader)
        self.assertEqual(len(epochs),2)
        self.assertEqual([x.prn for x in epochs[0].observations],[1,2])
        self.assertEqual(epochs[0].observations[1].cn0_dbhz,46)
        self.assertEqual(epochs[1].observations[0].pseudorange_m,24000000)

    def test_rinex3_nonseekable_incremental_input(self):
        class Stream(io.StringIO):
            def seek(self,*args):raise AssertionError('must not seek')
            def tell(self):raise AssertionError('must not tell')
            def seekable(self):return False
        text=obs3()+'> 2022 03 06 00 00 00.0000000  0  1\nG01'+obsfield(21000000)+'\n'
        text+='> 2022 03 06 00 00 01.0000000  0  1\nG02'+obsfield(22000000)+'\n'
        epochs=list(RinexObservationReader(Stream(text)))
        self.assertEqual([e.observations[0].prn for e in epochs],[1,2])

    def test_reject_other_timescale(self):
        text=obs3().replace(header('','END OF HEADER'),
            header(' '*48+'UTC','TIME OF FIRST OBS')+header('','END OF HEADER'))
        with self.assertRaisesRegex(ValueError,'time scale'):RinexObservationReader(io.StringIO(text))

    def test_independent_rtklib_emission_vectors(self):
        nav=ROOT/'source/live_data/07590920.05n';obs=ROOT/'source/live_data/07590920.05o'
        if not nav.exists() or not obs.exists():self.skipTest('pinned public GSI fixture unavailable')
        # RTKLIB 2.4.2 p13 -x5 independent first-epoch output: source file hash
        # and per-satellite errors are recorded in results/gnss_math_oracle.json.
        expected={3:((-24595184.341,-10320589.582,1244218.674),96721.355),
          7:((10026487.690,18601864.069,16597421.854),-136066.263),
          8:((-683949.793,26351230.765,79787.480),-25143.048),
          11:((-14822915.660,8930208.368,20079386.097),210127.473),
          19:((-23358517.500,-5407967.004,11505396.179),-17455.662),
          20:((-23036169.086,13172079.739,766984.165),-75357.307),
          24:((-4410870.939,25703724.499,4806330.195),5949.333),
          28:((-2383676.578,17483698.398,19982740.575),46887.234)}
        navigation=read_rinex_nav(nav);epoch=next(iter_rinex_obs(obs))
        prepared=prepare_epoch(epoch,navigation.ephemerides,(0,0,0))
        for row in prepared['observations']:
            d=row['diagnostics'];e=select_ephemeris(navigation.ephemerides,d['prn'],d['transmit_time_gpst_s'])
            state=satellite_state(e,d['transmit_time_gpst_s']);position,clock_ns=expected[d['prn']]
            self.assertLess(math.dist(state['position_ecef_m'],position),0.001)
            self.assertLess(abs((state['clock_l1_s']+state['tgd_s'])*1e9-clock_ns),0.0005)

    def test_recorded_gsi_fixture_when_present(self):
        obs=ROOT/'source/live_data/07590920.05o';nav=ROOT/'source/live_data/07590920.05n'
        if not obs.exists() or not nav.exists():self.skipTest('pinned public GSI fixture unavailable')
        navigation=read_rinex_nav(nav);epochs=list(iter_rinex_obs(obs))
        self.assertEqual(len(epochs),120)
        self.assertEqual(len(navigation.ephemerides),162)
        self.assertEqual(epochs[0].observations[0].prn,3)
        self.assertEqual(epochs[0].observations[0].pseudorange_m,24767686.375)
        self.assertEqual(epochs[0].source_metadata['approx_ecef_role'],'seed_only_not_truth')
        self.assertEqual(navigation.iono_alpha,(1.118e-8,1.49e-8,-5.96e-8,-5.96e-8))
        prepared=prepare_epoch(epochs[0],navigation.ephemerides,epochs[0].source_metadata['approx_ecef_m'],
            iono_alpha=navigation.iono_alpha,iono_beta=navigation.iono_beta)
        self.assertEqual(len(prepared['observations']),7)
        self.assertEqual(prepared['rejected'][0]['prn'],3)
        self.assertEqual(prepared['model']['iono'],'broadcast_klobuchar')
        self.assertTrue(all(row['diagnostics']['iono_m']>0 and row['diagnostics']['tropo_m']>0 for row in prepared['observations']))


if __name__=='__main__':unittest.main(verbosity=2)
