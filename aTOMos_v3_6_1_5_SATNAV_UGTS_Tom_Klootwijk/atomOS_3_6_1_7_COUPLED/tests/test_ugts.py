import math,random,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from ugts import *
from geodesy import *
class SourceContracts(unittest.TestCase):
 def test_golden_key(self):
  q=(949111,0,1920,227)
  self.assertEqual(contiguous(q),0xe7b77000007800e3);self.assertEqual(morton(q),0x88823bb88099128b)
 def test_random_key_roundtrips(self):
  r=random.Random(3615)
  for _ in range(5000):
   q=tuple(r.randrange(1<<w)for w in WIDTHS)
   self.assertEqual(decode_contiguous(contiguous(q)),q);self.assertEqual(decode_morton(morton(q)),q)
 def test_key_overflow(self):
  for q in [(1<<20,0,0,0),(-1,0,0,0),(0,0,0,4096),(True,0,0,0)]:
   with self.assertRaises(ValueError):contiguous(q)
 def test_all_prefixes(self):
  q=(949111,0,1920,227);k=morton(q);old=[(0,(1<<w)-1)for w in WIDTHS]
  for n in range(65):
   bounds=prefix_bounds(k>>(64-n),n)
   for i,(a,b)in enumerate(bounds):self.assertLessEqual(a,q[i]);self.assertGreaterEqual(b,q[i]);self.assertGreaterEqual(a,old[i][0]);self.assertLessEqual(b,old[i][1])
   old=bounds
 def test_tick_winding_source(self):
  self.assertEqual(phase_winding(1920,1135,256),(3,.06640625))
 def test_negative_tick(self):self.assertEqual(phase_winding(-1,0,256),(-1,255/256))
 def test_quantization_widths(self):
  self.assertEqual(quantize(-20,0,16384,0),(0,0,0,0));self.assertEqual(quantize(0,2*math.pi,0,2*math.pi),((1<<20)-1,0,0,0))
 def test_topology_separate(self):
  a=topology(.25,.2,.3,1,'source_half_turn');b=topology(.25,.2,.3,1,'reflective_klein')
  self.assertEqual(a[0],-19.75);self.assertEqual(b[3],-1);self.assertNotEqual(a[1],b[1])
 def test_cone_axis(self):
  c=cone_sdf((0,0,1),(0,0,0),(0,0,1),2,math.pi/6)
  self.assertAlmostEqual(c,-.5,places=12)
 def test_cone_base_apex(self):
  self.assertEqual(cone_sdf((0,0,0),(0,0,0),(0,0,1),2,math.pi/6),0)
  self.assertAlmostEqual(cone_sdf((0,0,math.sqrt(3)),(0,0,0),(0,0,1),2,math.pi/6),0,places=12)
 def test_cone_exterior(self):
  self.assertAlmostEqual(cone_sdf((0,0,-1),(0,0,0),(0,0,1),2,math.pi/6),1)
 def test_zero_length_sweep(self):
  b=translated_sweep_interval((0,0,1),(0,0,0),(0,0,1),2,math.pi/6,(0,0,0),(0,0,0),5)
  self.assertEqual(b['lower'],b['upper'])
 def test_sweep_bound_against_dense(self):
  args=((.2,0,1),(0,0,0),(0,0,1),2,math.pi/6,(0,0,0),(.75,0,0))
  coarse=translated_sweep_interval(*args,17);fine=translated_sweep_interval(*args,1025)
  self.assertLessEqual(coarse['lower'],fine['upper']);self.assertGreaterEqual(coarse['upper'],fine['upper']-1e-12)
 def test_jitter_interval_distinction(self):
  r=perturbation_records(2,.1,1)
  self.assertNotEqual(r['family_interval'],r['measurement_centered_interval']);self.assertLessEqual(r['measurement_centered_interval'][0],2);self.assertGreaterEqual(r['measurement_centered_interval'][1],2)
 def test_geodesy_roundtrip(self):
  for la in [-89,-52,0,52,89]:
   for lo in [-179,5,179]:
    lat,lon,h=math.radians(la),math.radians(lo),234.5;r=ecef_to_geodetic(*geodetic_to_ecef(lat,lon,h));self.assertAlmostEqual(r[0],lat,places=12);self.assertAlmostEqual(r[1],lon,places=12);self.assertAlmostEqual(r[2],h,places=6)
 def test_enu_inverse(self):
  lat,lon=.9,.1;origin=geodetic_to_ecef(lat,lon,100);v=(300,-200,7);e=ecef_to_enu(enu_to_ecef(v,origin,lat,lon),origin,lat,lon)
  for x,y in zip(v,e):self.assertAlmostEqual(x,y,places=7)
 def test_otan2_source_is_not_heading(self):
  self.assertEqual(otan2_source(1,1)['value'],otan2_source(-1,-1)['value']);self.assertEqual(otan2_source(1,0)['status'],'ratio_undefined')
 def test_digest_changes(self):self.assertNotEqual(digest({'a':1}),digest({'a':2}))
if __name__=='__main__':unittest.main(verbosity=2)
