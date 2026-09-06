import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reconstruct_e1_v4r1 import build_channels, build_nominal, load_config


class TestZRCancellation(unittest.TestCase):
    def test_C_and_T_cancel_structurally(self):
        cfg = load_config(ROOT / "e1_v4r1_config.yaml")
        zR = build_channels(cfg, build_nominal(cfg))["zR"]
        J = np.vstack([x["J_fault"] for x in zR])
        np.testing.assert_array_equal(J[:, 5:17], np.zeros_like(J[:, 5:17]))
        self.assertGreater(np.linalg.norm(J[:, :5]), 0.0)
        self.assertGreater(np.linalg.norm(J[:, 17:23]), 0.0)


if __name__ == "__main__":
    unittest.main()
