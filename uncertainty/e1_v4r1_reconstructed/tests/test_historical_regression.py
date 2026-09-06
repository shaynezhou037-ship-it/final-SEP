import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestHistoricalRegressionGate(unittest.TestCase):
    def test_gate_is_fail_closed(self):
        report = json.loads((ROOT / "results" / "restoration_regression.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "results" / "reconstruction_manifest.json").read_text(encoding="utf-8"))
        checks = report["restoration"]["checks"]
        expected = "PASS" if all(x["pass"] for x in checks.values()) else "FAIL"
        self.assertEqual(report["restoration"]["status"], expected)
        if expected == "FAIL":
            self.assertFalse(manifest["phase_map_authorized"])
            self.assertFalse(manifest["perfect_zG_replay_authorized"])
            self.assertFalse(manifest["formal_e2_input_authorized"])

    def test_required_historical_checks_exist(self):
        report = json.loads((ROOT / "results" / "restoration_regression.json").read_text(encoding="utf-8"))
        names = report["restoration"]["checks"]
        for pair in ["P-C", "P-T", "P-R", "C-R", "T-R"]:
            self.assertIn(f"principal_angle_{pair}", names)
        self.assertIn("relative_noise_monotonic", names)
        self.assertIn("camera_noise_monotonic", names)
        self.assertIn("indexing_near_invariant", names)


if __name__ == "__main__":
    unittest.main()
