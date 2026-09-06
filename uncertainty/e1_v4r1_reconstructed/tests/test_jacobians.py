import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evidence_zG import geometry_evidence, geometry_residual
from evidence_zV import marker_grid, pose_absorption_map
from reconstruct_e1_v4r1 import build_nominal, load_config
from se3_utils import inv_transform
from ur5_model import body_jacobian, fk


class TestEvidenceJacobians(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config(ROOT / "e1_v4r1_config.yaml")
        cls.nom = build_nominal(cls.cfg)

    def test_body_jacobian_step_convergence(self):
        q = self.nom["q_list"][0]
        np.testing.assert_allclose(body_jacobian(q, 1e-6), body_jacobian(q, 2e-7), atol=2e-7, rtol=2e-6)

    def test_zV_absorption_normal_equations(self):
        q = self.nom["q_list"][0]
        T_CM = inv_transform(self.nom["T_BC"]) @ fk(q) @ self.nom["T_FM"]
        B, diag = pose_absorption_map(
            T_CM,
            marker_grid(tuple(self.cfg["marker"]["grid_shape"]), self.cfg["marker"]["spacing_m"]),
            self.nom["intrinsics"],
            self.cfg["marker"]["training_indices"],
        )
        residual = diag["J_xi_training"] @ B + diag["J_P_training"]
        normal = diag["J_xi_training"].T @ residual
        np.testing.assert_allclose(normal, 0.0, atol=2e-5)

    def test_zG_finite_difference_is_stable(self):
        q = self.nom["q_list"][0]
        T_CM = inv_transform(self.nom["T_BC"]) @ fk(q) @ self.nom["T_FM"]
        B, _ = pose_absorption_map(
            T_CM,
            self.nom["points"],
            self.nom["intrinsics"],
            self.cfg["marker"]["training_indices"],
        )
        J = geometry_evidence(q, self.nom["T_BC"], self.nom["T_FM"], B)["J_fault"]
        # Independent one-sided check at a small, finite perturbation.
        h = 2e-7
        for k in [5, 10, 11, 16, 17, 22]:
            th = np.zeros(23)
            th[k] = h
            fd = geometry_residual(th, np.zeros(12), q, self.nom["T_BC"], self.nom["T_FM"], B) / h
            np.testing.assert_allclose(fd, J[:, k], atol=3e-5, rtol=3e-5)


if __name__ == "__main__":
    unittest.main()
