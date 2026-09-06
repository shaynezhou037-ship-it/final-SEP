import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from se3_utils import adjoint, inv_transform, se3_exp, se3_log


class TestSE3Utils(unittest.TestCase):
    def test_exp_log_roundtrip(self):
        rng = np.random.default_rng(7)
        for _ in range(30):
            xi = rng.normal(size=6) * np.r_[np.full(3, 0.05), np.full(3, 0.2)]
            np.testing.assert_allclose(se3_log(se3_exp(xi)), xi, atol=2e-10, rtol=2e-10)

    def test_inverse(self):
        xi = np.array([0.1, -0.02, 0.3, 0.2, -0.1, 0.05])
        T = se3_exp(xi)
        np.testing.assert_allclose(T @ inv_transform(T), np.eye(4), atol=1e-12)

    def test_adjoint_identity(self):
        T = se3_exp(np.array([0.1, 0.2, -0.1, 0.2, 0.1, -0.2]))
        xi = np.array([0.01, -0.02, 0.03, 0.02, 0.01, -0.03])
        lhs = T @ se3_exp(xi) @ inv_transform(T)
        rhs = se3_exp(adjoint(T) @ xi)
        np.testing.assert_allclose(lhs, rhs, atol=2e-11)


if __name__ == "__main__":
    unittest.main()
