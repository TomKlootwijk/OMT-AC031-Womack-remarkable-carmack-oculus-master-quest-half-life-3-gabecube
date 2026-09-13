; Tom Klootwijk atomOS U1: local packed-symbol update obligations.
; A 64-bit window contains the two possible 32-bit backing words.
; This proves the stated bit-vector equation, not C++ or GPU instructions.
(set-logic QF_BV)
(declare-fun old () (_ BitVec 64))
(declare-fun symbol () (_ BitVec 64))
(declare-fun width () (_ BitVec 64))
(declare-fun offset () (_ BitVec 64))
(assert (bvuge width (_ bv1 64)))
(assert (bvule width (_ bv32 64)))
(assert (bvule offset (_ bv31 64)))
(define-fun lowmask () (_ BitVec 64) (bvsub (bvshl (_ bv1 64) width) (_ bv1 64)))
(assert (= (bvand symbol lowmask) symbol))
(define-fun mask () (_ BitVec 64) (bvshl lowmask offset))
(define-fun updated () (_ BitVec 64)
  (bvor (bvand old (bvnot mask)) (bvshl symbol offset)))
; Reading the overwritten block returns exactly the supplied symbol.
(push)
(assert (not (= (bvand (bvlshr updated offset) lowmask) symbol)))
(check-sat)
(pop)
; Every bit outside the symbol block remains unchanged.
(push)
(assert (not (= (bvand updated (bvnot mask)) (bvand old (bvnot mask)))))
(check-sat)
(pop)
