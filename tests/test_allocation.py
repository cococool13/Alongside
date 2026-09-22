import unittest
from allocation import cap_weights


class AllocationTests(unittest.TestCase):
    def test_caps_concentrated_book(self):
        capped = cap_weights({'A': .5, 'B': .1, 'C': .1, 'D': .1, 'E': .1, 'F': .1})
        self.assertAlmostEqual(sum(capped.values()), 1)
        self.assertLessEqual(max(capped.values()), .2000001)
        self.assertAlmostEqual(capped['A'], .2)

    def test_refuses_book_too_small_for_cap(self):
        with self.assertRaisesRegex(ValueError, 'enough holdings'):
            cap_weights({'A': .7, 'B': .3})
