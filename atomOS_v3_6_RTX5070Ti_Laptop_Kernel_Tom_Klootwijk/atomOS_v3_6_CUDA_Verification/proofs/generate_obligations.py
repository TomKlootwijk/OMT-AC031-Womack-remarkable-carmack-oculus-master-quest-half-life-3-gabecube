#!/usr/bin/env python3
"""Generate standalone SMT-LIB obligations for the documented exact-word algebra."""
from pathlib import Path
import json
root=Path(__file__).resolve().parent
base='''(set-logic QF_BV)
(set-option :timeout 30000)
(declare-const x (_ BitVec 32))
(declare-const a (_ BitVec 32))
(declare-const n (_ BitVec 32))
(declare-const b (_ BitVec 32))
(declare-const v (_ BitVec 32))
(declare-const f (_ BitVec 32))
(define-fun selected ((xx (_ BitVec 32)) (aa (_ BitVec 32)) (nn (_ BitVec 32)) (vv (_ BitVec 32))) (_ BitVec 32)
 (bvand xx aa nn vv))
(define-fun final ((xx (_ BitVec 32)) (aa (_ BitVec 32)) (nn (_ BitVec 32)) (bb (_ BitVec 32)) (vv (_ BitVec 32))) (_ BitVec 32)
 (ite (= (bvand (selected xx aa nn vv) bb) #x00000000) (selected xx aa nn vv) #x00000000))
'''
ob=[]
def add(name,body,desc,prelude=base):
 path=root/(name+'.smt2');path.write_text(prelude+'\n'+body+'\n(check-sat)\n',encoding='utf-8')
 ob.append({'id':name,'file':path.name,'expected':'unsat','claim':desc})
add('P01_neutral_fringe','(assert (not (= (final x (bvand a v) n b v) (final x a n b v))))','Neutral fringe preserves the 32-bit final output.')
add('P02_idempotent_output','(assert (not (= (final (final x a n b v) a n b v) (final x a n b v))))','Final-word idempotence for all 32-bit masks and inputs.')
add('P03_output_support','(assert (not (= (bvand (final x a n b v) (bvnot x)) #x00000000)))','Final output cannot introduce an input-zero bit.')
add('P04_zero_fixed_point','(assert (not (= (final #x00000000 a n b v) #x00000000)))','Zero remains zero under the complete aperture rule.')
add('P05_tail_isolation','(assert (not (= (final x a n b v) (final x a n (bvand b v) v))))','Boundary bits outside the valid mask do not affect output.')
add('P06_fringe_contraction','(assert (not (= (bvand (selected x (bvand a f) n v) (bvnot (selected x a n v))) #x00000000)))','Pre-absorption NA support contracts under the fringe intersection.')
add('P07_asa_neutral','(assert (not (= (bvand x a v v) (bvand x a v))))','Neutral fringe preserves the recorded ASA stage itself.')
add('P08_mask_order','(assert (not (= (bvand (bvand x a v) n) (selected x a n v))))','Recorded ASA then NA gives the declared selected support.')
# SWAR expression is the same fixed-width integer formula used by the CPU fallback.
base_pop=base+'''
(define-fun p1 ((z (_ BitVec 32))) (_ BitVec 32) (bvsub z (bvand (bvlshr z #x00000001) #x55555555)))
(define-fun p2 ((z (_ BitVec 32))) (_ BitVec 32) (bvadd (bvand (p1 z) #x33333333) (bvand (bvlshr (p1 z) #x00000002) #x33333333)))
(define-fun p3 ((z (_ BitVec 32))) (_ BitVec 32) (bvand (bvadd (p2 z) (bvlshr (p2 z) #x00000004)) #x0f0f0f0f))
(define-fun pc ((z (_ BitVec 32))) (_ BitVec 32) (bvlshr (bvmul (p3 z) #x01010101) #x00000018))
'''
terms=['((_ zero_extend 31) ((_ extract %d %d) x))'%(i,i) for i in range(32)]
add('P09_popcount_32','(assert (not (= (pc x) (bvadd '+' '.join(terms)+'))))','32-bit SWAR count equals the sum of all 32 bits.',base_pop)
add('P10_popcount_gate','(assert (not (= (= (pc x) #x00000000) (= x #x00000000))))','Population count is zero exactly for the zero word.',base_pop)
one='''(set-logic QF_BV)
(set-option :timeout 30000)
(declare-const q (_ BitVec 1)) (declare-const j (_ BitVec 1)) (declare-const k (_ BitVec 1))
(define-fun jk ((q (_ BitVec 1)) (j (_ BitVec 1)) (k (_ BitVec 1))) (_ BitVec 1)
 (bvor (bvand j (bvnot q)) (bvand (bvnot k) q)))
'''
add('P11_JK_truth_table','(assert (not (= (jk q j k) (ite (= j #b0) (ite (= k #b0) q #b0) (ite (= k #b0) #b1 (bvnot q))))))','JK equation equals the complete hold/set/reset/toggle truth table.',one)
add('P12_JK_toggle_twice','(assert (not (= (jk (jk q #b1 #b1) #b1 #b1) q)))','Two toggle events recover the initial JK bit.',one)
add('P13_blend_parity','(assert (not (= (bvxor q j k) (bvadd q j k))))','Three-way XOR equals binary parity, all encoded bit triples.',one)
morton='''(set-logic QF_BV)
(set-option :timeout 30000)
(declare-const r (_ BitVec 3)) (declare-const w (_ BitVec 3))
(define-fun z () (_ BitVec 6) (concat ((_ extract 2 2) w) ((_ extract 2 2) r) ((_ extract 1 1) w) ((_ extract 1 1) r) ((_ extract 0 0) w) ((_ extract 0 0) r)))
'''
add('P14_morton_inverse','(assert (or (not (= (concat ((_ extract 4 4) z) ((_ extract 2 2) z) ((_ extract 0 0) z)) r)) (not (= (concat ((_ extract 5 5) z) ((_ extract 3 3) z) ((_ extract 1 1) z)) w))))','The even/odd inverse recovers both coordinates of every 8x8 word tile.',morton)
add('P15_atomic_commit','''(declare-const before (_ BitVec 32)) (declare-const proposed (_ BitVec 32)) (declare-const accept Bool)
(assert (and (not accept) (not (= (ite accept proposed before) before))))''','The formal commit selector preserves the old word when validation rejects.')
(root/'obligations.json').write_text(json.dumps(ob,indent=2)+'\n')
print(f'Generated {len(ob)} obligations')
