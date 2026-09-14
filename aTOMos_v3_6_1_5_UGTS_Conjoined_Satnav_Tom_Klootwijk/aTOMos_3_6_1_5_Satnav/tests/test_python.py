from pathlib import Path
import sys,unittest,math,random
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import sclp as s
class TestSCLP(unittest.TestCase):
 def test_keys_reference(self):
  q=(949111,0,1920,227);self.assertEqual(s.pack(q),0xe7b77000007800e3);self.assertEqual(s.pack(q,'morton'),0x88823bb88099128b)
 def test_roundtrip(self):
  r=random.Random(5)
  for _ in range(1000):
   q=tuple(r.randrange(1<<w)for w in s.WIDTHS)
   for layout in ('contiguous','morton'):self.assertEqual(s.unpack(s.pack(q,layout),layout),q)
 def test_prefix_refines(self):
  key=s.pack((949111,100,1920,227),'morton');previous=s.prefix_bounds(0,0)
  for n in range(1,65):
   current=s.prefix_bounds(key>>(64-n),n)
   self.assertTrue(all(a>=pa and b<=pb for (a,b),(pa,pb)in zip(current,previous)));self.assertTrue(any(b-a<pb-pa for (a,b),(pa,pb)in zip(current,previous)));previous=current
 def test_time_source(self):self.assertEqual(s.phase_clock(1920,1135,256),{'winding':3,'phase':.06640625,'parity':1})
 def test_negative_time(self):self.assertEqual(s.phase_clock(0,1,256)['winding'],-1)
 def test_topology(self):
  a=s.topology(.25,0,.34906585,1,'half_turn');b=s.topology(.25,.2,.35,1,'klein_reflection');self.assertAlmostEqual(a[0],-19.75);self.assertAlmostEqual(a[1],-math.pi);self.assertEqual(a[3],-1);self.assertAlmostEqual(b[1],math.pi-.2)
 def test_metric_and_exact_step(self):
  self.assertAlmostEqual(s.metric(math.log(.15),1),.0225);self.assertAlmostEqual(s.radial_step(2,math.log(2)),2)
 def test_velocity_acceleration_circle(self):
  v,a=s.kinematics(0,0,0,2,0,0);self.assertEqual(v,(0.,2.));self.assertEqual(a,(-4.,0.))
 def test_tangent(self):self.assertEqual(s.tangent((1,2,3),(0,0,1)),(1.,2.,0.))
 def test_constraint(self):self.assertEqual(s.release_constraint([[1,0,0],[0,1,0]],1),(1,2,1))
 def test_redundant_constraint(self):self.assertEqual(s.release_constraint([[1,0,0],[1,0,0]],1),(2,2,0))
 def test_grammar(self):
  g=s.grammar(4);self.assertEqual(len(g),76);self.assertEqual(g.count('F'),16);self.assertEqual(g.count('['),g.count(']'));self.assertEqual(s.grammar(1,0,-1),s.grammar(1,1,1))
 def test_grammar_capacity(self):
  with self.assertRaises(ValueError):s.grammar(30)
 def test_jitter_distinct_intervals(self):
  a=s.jitter_intervals(3.,.1,1);self.assertNotEqual(a['nominal_uncertainty'],a['recovery_interval']);self.assertTrue(a['recovery_interval'][0]<=3<=a['recovery_interval'][1])
 def test_invalid(self):
  for q in [(-1,0,0,0),(1<<20,0,0,0)]:
   with self.assertRaises(ValueError):s.pack(q)
if __name__=='__main__':unittest.main(verbosity=2)
