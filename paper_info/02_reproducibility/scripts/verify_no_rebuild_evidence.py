#!/usr/bin/env python3
"""Verify and freeze the evidence added after the no-rebuild decision.

This script does not create new physical observations. It checks the existing
E5/E6/E7 derived outputs, enforces the paper-level evidence boundaries, and
writes a hash-backed JSON manifest for the audit trail. Verification preserves
repository integrity; it does not make every verified experiment eligible for
the current submission.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import json
import math
import subprocess
import sys


SCRIPT = Path(__file__).resolve()
REPO_ROOT = SCRIPT.parents[3]
OUTPUT = REPO_ROOT / "paper_info" / "02_reproducibility" / "no_rebuild_evidence_manifest.json"

E5_ROOT = REPO_ROOT / "E5" / "E5_resolution_operating_envelope"
E6_ROOT = REPO_ROOT / "E6" / "E6_dual_camera_information_and_view_geometry"
E7_ROOT = REPO_ROOT / "E7" / "E7_moving_camera_relocalization_simulation"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def close(actual: float, expected: float, tolerance: float = 1e-9) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=tolerance):
        raise RuntimeError(f"Expected {expected}, got {actual}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def run_component_verifiers() -> None:
    verifiers = (
        E5_ROOT / "scripts" / "verify_e5_outputs.py",
        E6_ROOT / "scripts" / "verify_e6_outputs.py",
        E7_ROOT / "scripts" / "verify_e7_outputs.py",
    )
    for verifier in verifiers:
        subprocess.run([sys.executable, str(verifier)], cwd=REPO_ROOT, check=True)


def main() -> None:
    run_component_verifiers()

    e5_summary_path = E5_ROOT / "results" / "E5_summary.json"
    e5_height_path = E5_ROOT / "results" / "E5_height_summary.csv"
    e6_summary_path = E6_ROOT / "results" / "E6_summary.json"
    e6_angle_path = E6_ROOT / "results" / "E6_angle_identifiability_audit.json"
    e7_summary_path = E7_ROOT / "results" / "E7_summary.json"

    e5 = load_json(e5_summary_path)
    e5_height = load_csv(e5_height_path)
    e6 = load_json(e6_summary_path)
    e6_angle = load_json(e6_angle_path)
    e7 = load_json(e7_summary_path)

    if e5["source_images"] != 330 or e5["qc_excluded_images"] != 6:
        raise RuntimeError("E5 source/QC cardinality changed")
    detection = {
        (row["camera_id"], int(row["width_px"])): float(row["complete_image_rate"])
        for row in e5["overall_detection"]
    }
    close(detection[("ihawk1", 640)], 1.0)
    close(detection[("ihawk2", 640)], 1.0)
    close(detection[("ihawk1", 480)], 0.7839506172839507)
    close(detection[("ihawk2", 480)], 0.9876543209876543)
    native_latency_p95 = max(
        float(row["pipeline_latency_p95_ms"])
        for row in e5["latency_summary"]
        if int(row["width_px"]) == 640
    )
    close(native_latency_p95, 8.1491561, tolerance=1e-6)

    def e5_xy(camera: str, width: int, height: float, model: str) -> float:
        row = next(
            row
            for row in e5_height
            if row["camera_id"] == camera
            and int(row["width_px"]) == width
            and float(row["height_gt_mm"]) == height
            and row["model"] == model
        )
        return float(row["xy_rmse_mean_mm"])

    close(e5_xy("ihawk2", 640, 25.0, "PnP"), 4.78591695481763)
    close(e5_xy("ihawk2", 480, 25.0, "PnP"), 12.807537471313072)
    close(e5_xy("ihawk2", 320, 25.0, "PnP"), 18.126269643343484)

    pnp25 = e6["fusion_key_heights"]["PnP"]["25"]
    if not (
        pnp25["ihawk2"]
        < pnp25["LOOWeightedFusion"]
        < pnp25["EqualFusion"]
        < pnp25["ihawk1"]
    ):
        raise RuntimeError("E6 PnP fusion ordering changed")
    close(e6["stereo_key_heights"]["25"]["xy_rmse_mean_mm"], 2.7521386895985205)
    close(e6["stereo_key_heights"]["25"]["z_rmse_mean_mm"], 1.7718476758354282)
    pnp3d25 = e6["pnp3d_key_heights"]["25"]
    close(pnp3d25["ihawk2"]["error3d_rmse_mean_mm"], 6.144212828130747)
    close(pnp3d25["EqualXYZ"]["error3d_rmse_mean_mm"], 7.431398224022177)
    close(pnp3d25["LOOWeightedXYZ"]["error3d_rmse_mean_mm"], 6.350689231127146)
    close(e6["stereo_key_heights"]["25"]["error3d_rmse_mean_mm"], 3.341760741375508)
    contrast25 = e6["pnp3d_stereo_contrasts_key_heights"]["25"]["ihawk2"]
    contrast50 = e6["pnp3d_stereo_contrasts_key_heights"]["50"]["ihawk2"]
    if int(contrast25["stereo_lower_3d_error_n"]) != 5:
        raise RuntimeError("E6 25-mm paired XYZ contrast changed")
    if int(contrast50["stereo_lower_3d_error_n"]) != 4:
        raise RuntimeError("E6 50-mm paired XYZ contrast changed")
    if e6_angle["verdict"] != "not_identifiable_from_current_E6":
        raise RuntimeError("E6 angle evidence boundary changed")
    if e6_angle["effective_fixed_camera_placements"] != 2:
        raise RuntimeError("E6 must retain two fixed placements")
    if not all(
        not row["camera_ranges_overlap"] for row in e6_angle["camera_identity_audit"]
    ):
        raise RuntimeError("E6 geometry ranges no longer match the confounding audit")

    if e7["evidence_class"] != "simulation_only":
        raise RuntimeError("E7 must remain simulation-only")
    e7_headline = e7["headline"]
    close(e7_headline["FrozenExtrinsicPnP"]["S3_large"]["xy_rmse_mm"], 40.611727350040965)
    relocalized = [
        float(row["xy_rmse_mm"])
        for row in e7_headline["RelocalizedPnP"].values()
    ]
    if min(relocalized) < 6.62 or max(relocalized) > 6.85:
        raise RuntimeError("E7 relocalized-PnP headline range changed")

    source_paths = (
        e5_summary_path,
        e5_height_path,
        E5_ROOT / "results" / "E5_manifest.json",
        e6_summary_path,
        E6_ROOT / "results" / "E6_stereo_height_summary.csv",
        E6_ROOT / "results" / "E6_pnp3d_height_summary.csv",
        E6_ROOT / "results" / "E6_pnp3d_contrast_summary.csv",
        e6_angle_path,
        E6_ROOT / "results" / "E6_manifest.json",
        e7_summary_path,
        E7_ROOT / "results" / "E7_manifest.json",
    )
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": "no_physical_rebuild",
        "scope": "offline reuse and simulation only; no new physical observations",
        "component_verifiers": "PASS",
        "paper_role": {
            "E5": "supporting validity check for resolution/reliability/latency constraints",
            "E6": "core evidence for single-view, estimate-fusion, and stereo information flows",
            "E6_angle": "supplementary descriptive confounding/identifiability audit only",
            "E7": "repository-only future-work simulation; excluded from manuscript, Appendix, and Supplement",
        },
        "pending_claim_map_rows": [
            {
                "claim_id": "C19",
                "claim": "Processing the saved 640x400 baseline images already met the predefined 30 Hz latency gate, while offline downsampling to 480x300 reduced complete-frame detection reliability, especially for ihawk1.",
                "evidence": relative(e5_summary_path),
                "key_result": "native complete detection 100% for both cameras; native worst pipeline P95 8.149 ms; 480x300 complete frames 78.4%/98.8%",
                "strength": "direct within offline downsampling protocol",
                "caveat": "not a native sensor-mode experiment; timing is computer-specific",
                "submission_role": "supporting",
            },
            {
                "claim_id": "C20",
                "claim": "Downsampling imposed a camera- and method-dependent accuracy cost and did not reveal a universal height-amplification law.",
                "evidence": relative(e5_height_path),
                "key_result": "ihawk2 PnP at 25 mm: 4.786/12.808/18.126 mm at 640/480/320 widths",
                "strength": "conditional paired transformation evidence",
                "caveat": "survivorship after detection failure; same physical images reused",
                "submission_role": "supporting",
            },
            {
                "claim_id": "C21",
                "claim": "Averaging two camera-specific estimates and using calibrated stereo parallax are distinct information flows; the latter added depth information in E6.",
                "evidence": relative(e6_summary_path),
                "key_result": "strict XYZ ablation at 25 mm: ihawk1/ihawk2/equal/LOO/stereo 3-D RMSE = 10.348/6.144/7.431/6.351/3.342 mm; stereo lower than ihawk2 in 5/5 rebuilds (4/5 at 50 mm)",
                "strength": "direct within five paired physical rebuilds",
                "caveat": "static target; Z=0-derived stereo geometry; no E4 endpoint propagation",
                "submission_role": "core",
            },
            {
                "claim_id": "C22",
                "claim": "The existing data do not identify a causal camera-angle effect.",
                "evidence": relative(e6_angle_path),
                "key_result": "10 run-camera rows but only 2 fixed placements; all audited geometry ranges are separated by camera identity",
                "strength": "direct design/identifiability limitation",
                "caveat": "pooled correlations are descriptive and confounded",
                "submission_role": "supporting limitation",
            },
            {
                "claim_id": "C23",
                "claim": "In simulation, per-frame relocalization prevented camera motion from making the nominal extrinsic stale.",
                "evidence": relative(e7_summary_path),
                "key_result": "at 25 mm and 0.5 px noise, frozen-extrinsic PnP reached 40.612 mm under large motion; relocalized PnP stayed 6.623-6.846 mm",
                "strength": "simulation-only mechanism evidence",
                "caveat": "no physical motion, detector failure, blur, vibration, rolling shutter, or endpoint validation",
                "submission_role": "excluded future work",
            },
        ],
        "source_hashes_sha256": {relative(path): sha256(path) for path in source_paths},
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"No-rebuild evidence verification PASS: {relative(OUTPUT)}")


if __name__ == "__main__":
    main()
