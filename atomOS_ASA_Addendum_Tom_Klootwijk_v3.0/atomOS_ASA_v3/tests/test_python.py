from pathlib import Path
import json,math,struct,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from python.reference import address,signed_angle,wrap,f32,evaluate
from python.timeline import schedule,latest_frame
from python.provenance import canonical,genesis,seal,verify
class Contract(unittest.TestCase):
    def test_morton_known(self):
        self.assertEqual([address(1,0,8,1),address(0,1,8,1),address(7,7,8,1)],[1,2,63])
    def test_morton_dense(self):
        self.assertEqual({address(r,p,24,1) for r in range(16) for p in range(24)},set(range(384)))
    def test_wrap(self):self.assertEqual(wrap(2*math.pi),0)
    def test_antipode(self):self.assertEqual(signed_angle(math.pi),-math.pi)
    def test_large_phase(self):self.assertTrue(0<=wrap(sys.float_info.max)<2*math.pi)
    def test_float32_roundtrip(self):self.assertEqual(f32(f32(.1)),f32(.1))
    def test_clock_common_base(self):self.assertEqual(schedule()['base_hz'],16000)
    def test_clock_source_period(self):self.assertEqual(schedule()['frame_ticks'],64)
    def test_clock_engine_period(self):self.assertEqual(schedule()['engine_ticks'],125)
    def test_clock_half_second(self):
        c=schedule();self.assertEqual((c['frames_per_period'],c['steps_per_period'],c['period_denominator']),(125,64,2))
    def test_clock_causality(self):
        for k in range(1000):
            j=latest_frame(k);self.assertLessEqual(j*128,k*250);self.assertGreater((j+1)*128,k*250)
    def test_clock_bad_rate(self):
        with self.assertRaises(ValueError):schedule(0,128)
    def test_clock_bad_tick(self):
        with self.assertRaises(ValueError):latest_frame(-1)
    def test_genesis_full_digest(self):self.assertEqual(len(genesis()['sha256']),64)
    def test_genesis_role_separation(self):
        g=genesis()['record'];self.assertEqual(g['operator_label'],'>O< / ASA');self.assertNotIn('coordinates',g)
    def test_genesis_determinism(self):self.assertEqual(genesis(),genesis())
    def test_genesis_fixture_domain(self):self.assertNotEqual(genesis('a')['sha256'],genesis('b')['sha256'])
    def test_canonical_keys(self):self.assertEqual(canonical({'b':1,'a':2}),canonical({'a':2,'b':1}))
    def test_canonical_nan(self):
        with self.assertRaises(ValueError):canonical({'x':math.nan})
    def test_seal_tamper_and_anchor(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'run.json').write_text(json.dumps({'config':{'x':1}}))
            for name in ('image.f32','mask.u32','warp.f32x2','samples.f64x2'):(p/name).write_bytes(b'\0'*8)
            (p/'results.bin').write_bytes(b'\0'*64);(p/'results.csv').write_text('fixture\n')
            s=seal(p);self.assertTrue(verify(p,s['head']));self.assertFalse(verify(p,'0'*64))
            (p/'results.bin').write_bytes(b'\1'+b'\0'*63);self.assertFalse(verify(p))
    def test_double_seal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'seal.json').write_text('{}')
            with self.assertRaises(FileExistsError):seal(p)
if __name__=='__main__':unittest.main()
