(set-logic QF_BV)
(set-option :timeout 30000)
(declare-const q (_ BitVec 1)) (declare-const j (_ BitVec 1)) (declare-const k (_ BitVec 1))
(define-fun jk ((q (_ BitVec 1)) (j (_ BitVec 1)) (k (_ BitVec 1))) (_ BitVec 1)
 (bvor (bvand j (bvnot q)) (bvand (bvnot k) q)))

(assert (not (= (jk q j k) (ite (= j #b0) (ite (= k #b0) q #b0) (ite (= k #b0) #b1 (bvnot q))))))
(check-sat)
