from __future__ import annotations
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))
sys.path.insert(0, str(ROOT / "scripts"))
import atomos_ref as a
from verify_journal import verify

class Mathematics(unittest.TestCase):
    def test_children_are_not_right_shifts(self):
        self.assertEqual(a.children(1), (2, 3))
        self.assertEqual(1 >> 1, 0)
    def test_lineage_injective(self):
        ids = [c for p in range(1,1000) for c in a.children(p)]
        self.assertEqual(len(ids), len(set(ids)))
    def test_lineage_overflow(self):
        for p in (0, -1, 1 << 63):
            with self.assertRaises(ValueError): a.children(p)
    def test_zero_is_absorbing(self):
        self.assertEqual(a.word_step(0,a.MASK32,0),0)
    def test_or_xor_distinct(self):
        self.assertEqual(a.word_step(5,0,0),8)
        self.assertEqual(a.word_step(5,0,0,True),10)
    def test_mask_requires_same_index_space(self):
        self.assertEqual(a.word_step(1,0,2),0)
        self.assertEqual(a.word_step(1,0,1),2)
    def test_word_range(self):
        with self.assertRaises(ValueError): a.word_step(1<<32,0,0)
    def test_bitpacking_word_crossings(self):
        bits=[int(i in (0,31,32,63,64,99)) for i in range(100)]
        packed=a.pack_bits(bits)
        self.assertEqual([a.get_bit(packed,i,100) for i in range(100)],bits)
    def test_bitpacking_bounds(self):
        with self.assertRaises(IndexError):a.get_bit([0],32,32)
    def test_hash_width(self):
        self.assertEqual(len(hashlib.sha256(b"atomOS").digest()),32)
    def test_jitter_threshold(self):
        root=hashlib.sha256(b"seed").digest()
        for child in range(2,100):
            self.assertEqual(a.jitter_bit(root,0,child,0),0)
            self.assertEqual(a.jitter_bit(root,0,child,256),1)
    def test_jitter_replay(self):
        root=hashlib.sha256(b"seed").digest()
        x=[a.jitter_bit(root,3,c) for c in range(8,16)]
        self.assertEqual(x,[a.jitter_bit(root,3,c) for c in range(8,16)])
    def test_klein_deck_relation(self):
        for k in range(-9,10):
            rho,phi,orientation=a.klein(0.25+3*k,0.4,-1,2)
            self.assertAlmostEqual(rho,.25)
            self.assertAlmostEqual(phi,(-.4 if k%2 else .4)%a.TAU)
            self.assertEqual(orientation,k&1)
    def test_klein_two_wraps(self):
        self.assertEqual(a.klein(6.25,1,-1,2),(.25,1,0))
    def test_invalid_klein(self):
        with self.assertRaises(ValueError):a.klein(0,0,1,1)
    def test_rk4_fourth_order_smooth_control(self):
        errors=[]
        for n in (10,20,40,80):
            y=1.
            for i in range(n):y=a.rk4(lambda t,z:z,i/n,y,1/n)
            errors.append(abs(y-math.e))
        for e,f in zip(errors,errors[1:]):self.assertGreater(e/f,15)
    def test_divergence_constant_cartesian_field(self):
        # Orthornormal polar components: ur=cos(phi), uphi=-sin(phi).
        for phi in (.3,.6,1.2):
            derivative_phi=-math.cos(phi)
            self.assertAlmostEqual(math.cos(phi)+derivative_phi,0)
    def test_jk_truth_table(self):
        for q in (0,1):
            self.assertEqual(a.jk(q,0,0),q)
            self.assertEqual(a.jk(q,1,0),1)
            self.assertEqual(a.jk(q,0,1),0)
            self.assertEqual(a.jk(q,1,1),1-q)
    def test_vm_unary(self):
        p=[a.instruction(1,1,0),a.instruction(0,1,1),0,0]
        m=a.Machine(2,1,p,{i:1 for i in range(8)})
        m.run(100)
        self.assertEqual((m.status,m.head,m.steps),(1,8,9))
        self.assertEqual(m.tape,{i:1 for i in range(9)})
    def test_vm_capacity_no_commit(self):
        m=a.Machine(2,1,[a.instruction(0,1,-1),0,0,0],{})
        m.step();self.assertEqual((m.status,m.steps,m.tape),(2,0,{}))
    def test_vm_bad_program(self):
        m=a.Machine(2,1,[0,0,0,0],{})
        m.step();self.assertEqual(m.status,3)
    def test_vm_pause_continue(self):
        p=[a.instruction(1,1,0),a.instruction(0,1,1),0,0]
        m=a.Machine(2,1,p,{i:1 for i in range(8)})
        m.run(4);self.assertEqual((m.status,m.steps),(0,4))
        m.run(10);self.assertEqual((m.status,m.steps),(1,9))

class CrossLanguage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe=os.environ.get("ATOMOS_PROBE")
        if not cls.probe: raise unittest.SkipTest("set ATOMOS_PROBE to the compiled atomos_probe executable")
    def query(self, lines):
        result=subprocess.run([self.probe],input="\n".join(lines)+"\n",text=True,capture_output=True,check=True)
        return result.stdout.splitlines()
    def test_1000_unsigned_word_cases(self):
        r=random.Random(511);lines=[];expected=[]
        for _ in range(1000):
            x,j,m=[r.getrandbits(32) for _ in range(3)];mode=r.randrange(2)
            # Add clear masks often enough to exercise nonzero outputs.
            if r.randrange(3)==0:m=0
            lines.append(f"word {x} {j} {m} {mode}");expected.append(str(a.word_step(x,j,m,bool(mode))))
        self.assertEqual(self.query(lines),expected)
    def test_100_sha256_byte_strings(self):
        r=random.Random(130);samples=[bytes(r.randrange(256) for _ in range(n)) for n in range(100)]
        self.assertEqual(self.query(["sha "+(x.hex() or "-") for x in samples]),[hashlib.sha256(x).hexdigest() for x in samples])
    def test_300_jitter_cases(self):
        r=random.Random(7);root=hashlib.sha256(b"independent test").digest();lines=[];expected=[]
        for _ in range(300):
            tick,child,threshold=r.randrange(100),r.randrange(1,1<<63),r.randrange(257)
            lines.append(f"jitter {root.hex()} {tick} {child} {threshold}");expected.append(str(a.jitter_bit(root,tick,child,threshold)))
        self.assertEqual(self.query(lines),expected)
    def test_600_random_program_traces(self):
        r=random.Random(381);lines=[];expected=[]
        for _ in range(600):
            states=5;halt=4;program=[a.instruction(r.randrange(states),r.randrange(2),r.randrange(-1,2)) for _ in range(states*2)]
            if r.randrange(3)==0:program[r.randrange(len(program))]=0
            tape=r.getrandbits(32);head=r.randrange(32);budget=r.randrange(1,100)
            m=a.Machine(states,halt,program,{i:1 for i in range(32) if tape>>i&1},head=head)
            m.run(budget);word=sum(1<<i for i in m.tape)
            lines.append(f"vm {states} {halt} {budget} 0 {head} {tape} "+" ".join(map(str,program)))
            expected.append(f"{m.state} {m.head} {m.status} {m.steps} {word}")
        self.assertEqual(self.query(lines),expected)

class Journal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_path=os.environ.get("ATOMOS_RUN")
        if not cls.run_path: raise unittest.SkipTest("set ATOMOS_RUN to a generated propagation run")
    def test_journal_hashes(self):self.assertGreater(verify(Path(self.run_path))["verified_events"],0)
    def test_tampering_detected(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(self.run_path,Path(d)/"run")
            p=Path(d)/"run"/"journal.jsonl";lines=p.read_text().splitlines();v=json.loads(lines[0]);v["event_json"]+=" ";lines[0]=json.dumps(v);p.write_text("\n".join(lines)+"\n")
            with self.assertRaises(ValueError):verify(Path(d)/"run")
    def test_wrong_anchor_detected(self):
        with self.assertRaises(ValueError):verify(Path(self.run_path),"0"*64)

if __name__=="__main__":unittest.main(verbosity=2)
