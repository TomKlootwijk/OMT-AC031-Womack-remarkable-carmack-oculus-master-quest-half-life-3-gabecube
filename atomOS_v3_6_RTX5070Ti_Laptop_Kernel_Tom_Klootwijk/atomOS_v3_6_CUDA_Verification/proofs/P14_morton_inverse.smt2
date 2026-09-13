(set-logic QF_BV)
(set-option :timeout 30000)
(declare-const r (_ BitVec 3)) (declare-const w (_ BitVec 3))
(define-fun z () (_ BitVec 6) (concat ((_ extract 2 2) w) ((_ extract 2 2) r) ((_ extract 1 1) w) ((_ extract 1 1) r) ((_ extract 0 0) w) ((_ extract 0 0) r)))

(assert (or (not (= (concat ((_ extract 4 4) z) ((_ extract 2 2) z) ((_ extract 0 0) z)) r)) (not (= (concat ((_ extract 5 5) z) ((_ extract 3 3) z) ((_ extract 1 1) z)) w))))
(check-sat)
