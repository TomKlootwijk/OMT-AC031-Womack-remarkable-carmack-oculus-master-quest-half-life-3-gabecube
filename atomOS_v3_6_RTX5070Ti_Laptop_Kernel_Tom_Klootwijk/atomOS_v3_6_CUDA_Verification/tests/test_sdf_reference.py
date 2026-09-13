"""Independent replay checks for the missing twisted-seam behavior."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from sdf_reference import transport_cells

class KleinReplay(unittest.TestCase):
    def test_plus_seam_and_tail(self):
        state=[(0,i%2) for i in range(9)] # Three rows, 65 angular cells.
        state[2]=(1,0) # Row zero, angular 64.
        actual=transport_cells(state,3,65,'klein-plus')
        self.assertEqual([x for x,q in actual],[0,0,0,0,0,0,1,0,0])
        self.assertEqual([q for x,q in actual],[q for x,q in state])

    def test_minus_seam(self):
        state=[(0,0)]*9
        state[6]=(1,1) # Last row, angular zero.
        actual=transport_cells(state,3,65,'klein-minus')
        self.assertEqual([x for x,q in actual],[0,0,1,0,0,0,0,0,0])
        self.assertEqual(actual[6][1],1)

    def test_two_circuits_restore_location(self):
        state=[(1,0),(0,1),(0,0),(0,1),(0,0),(0,1)] # 3 x 33.
        initial=state[:]
        for _ in range(33):state=transport_cells(state,3,33,'klein-plus')
        self.assertEqual([x for x,q in state],[0,0,0,0,1,0])
        for _ in range(33):state=transport_cells(state,3,33,'klein-plus')
        self.assertEqual(state,initial)

    def test_inverse_preserves_full_support(self):
        state=[(0x12345678,0),(1,1),(0x87654321,1),(1,0),(0xfeedface,0),(0,0)]
        self.assertEqual(transport_cells(transport_cells(state,3,33,'klein-plus'),3,33,'klein-minus'),state)

if __name__=='__main__':unittest.main()
