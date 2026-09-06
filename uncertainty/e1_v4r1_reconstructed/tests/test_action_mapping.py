import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cross_action_metrics import ACTION_INDICES, CROSS_ACTION_PAIRS


class TestActionMapping(unittest.TestCase):
    def test_dimensions_and_order(self):
        self.assertEqual(ACTION_INDICES["P"], list(range(5)))
        self.assertEqual(ACTION_INDICES["C"], list(range(5, 11)))
        self.assertEqual(ACTION_INDICES["T"], list(range(11, 17)))
        self.assertEqual(ACTION_INDICES["R"], list(range(17, 23)))

    def test_C_T_same_action_exclusion(self):
        self.assertNotIn(("C", "T"), CROSS_ACTION_PAIRS)
        self.assertEqual(len(CROSS_ACTION_PAIRS), 5)


if __name__ == "__main__":
    unittest.main()
