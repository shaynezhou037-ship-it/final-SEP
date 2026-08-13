#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# EXPERIMENT LABEL:
# E0-B2 Varied-start / configuration/path-dependence endpoint test
#
# IMPORTANT INTERPRETATION:
# Random high joint configurations are intentionally used before returning
# to the same frozen Cartesian target. Therefore this script does NOT isolate
# pure same-start robot repeatability.
#

"""
E0-B Robot Repeatability using Yunkai Zhou Task10 final pipeline.

Design frozen for this experiment
---------------------------------
1. Reuse Yunkai Zhou's current 3-D fused robot-corrected target:
      /fused_target_pose_robot_corrected
2. Scan the marker ONCE at the beginning using core.collect_target():
      10 accepted fused samples -> per-axis median.
3. Freeze the final target for the whole run:
      (tx, ty, tz + 10 mm)
4. Trial 1 is the physical baseline.
      Manual offset = (0, 0, 0) by definition.
5. Trials 2..N:
      move to a conservative random high joint-space pose,
      return through the SAME three Task10 Final Cartesian waypoints,
      manually enter dx dy dz relative to Trial 1.
6. Save every trial immediately to CSV.
7. Produce JSON summary at the end.

IMPORTANT
---------
- This script measures repeatability relative to Trial 1, NOT absolute accuracy.
- dx, dy, dz are signed offsets in RoArm base-frame directions.
- +Z is upward.
- The two cameras / Yunkai calibration geometry must remain unchanged.
- The Yunkai ROS pipeline must already be publishing:
      /fused_target_pose_robot_corrected
- This script imports:
      task10_guarded_approach.py
  from the Yunkai FURP repository and reuses its:
      collect_target(), send_json(), get_pose()

Safety changes vs the original 10 mm Final script
--------------------------------------------------
- Tracking error above --max-tracking-error-mm causes a hard trial abort.
- If actual Z enters tz + 5 mm or lower, the run aborts.
- Before every random pose, the arm retracts through the SAME Task10 Final
  path to the high waypoint; it never jumps directly from the low endpoint.
- Random poses are then limited to a small conservative neighborhood around
  the official Task10 home pose and must report Z >= --min-random-z-mm.
- The marker target is scanned only once and then frozen.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import math
import os
import random
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


DEFAULT_CORE_DIR = (
    "/mnt/c/Users/ASUS/Desktop/"
    "FURP-2026-YUNKAI-CHOU-Mobile_Manipulator/"
    "tools/dual_berxel_roarm"
)

DEFAULT_OUTPUT_ROOT = (
    "/mnt/c/Users/ASUS/Desktop/paper/"
    "E0/E0_B_robot_repeatability"
)


CSV_FIELDS = [
    "run_id",
    "trial_index",
    "is_baseline",
    "timestamp",

    "scan_tx_mm",
    "scan_ty_mm",
    "scan_tz_mm",
    "fixed_target_x_mm",
    "fixed_target_y_mm",
    "fixed_target_z_mm",
    "clearance_mm",

    "random_seed",
    "random_base_rad",
    "random_shoulder_rad",
    "random_elbow_rad",
    "random_wrist_rad",
    "random_roll_rad",
    "random_hand_rad",

    "random_feedback_x_mm",
    "random_feedback_y_mm",
    "random_feedback_z_mm",

    "final_feedback_x_mm",
    "final_feedback_y_mm",
    "final_feedback_z_mm",
    "final_tracking_error_mm",

    "measurement_class",
    "measurement_resolution_mm",
    "exceeds_resolution",

    "manual_dx_mm",
    "manual_dy_mm",
    "manual_dz_mm",
    "manual_xy_offset_mm",
    "manual_3d_offset_mm",

    "success",
    "failure_type",
    "notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "E0-B robot repeatability using Yunkai Task10 final "
            "3-D fused target and manual XYZ offsets."
        )
    )

    parser.add_argument(
        "--trials",
        type=int,
        default=20,
        help=(
            "Total arrivals including Trial 1 baseline. Default: 20. "
            "Thus --trials 20 gives 19 comparison arrivals."
        ),
    )
    parser.add_argument(
        "--serial-port",
        default="/dev/ttyUSB0",
        help="RoArm serial device inside WSL. Default: /dev/ttyUSB0",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
    )
    parser.add_argument(
        "--core-dir",
        default=DEFAULT_CORE_DIR,
        help="Directory containing task10_guarded_approach.py",
    )
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260807,
        help="Random seed so the random-pose sequence is reproducible.",
    )
    parser.add_argument(
        "--clearance-mm",
        type=float,
        default=10.0,
        help="Final hover above scanned marker Z. Keep 10 mm for Yunkai Final.",
    )
    parser.add_argument(
        "--max-tracking-error-mm",
        type=float,
        default=45.0,
        help=(
            "Hard abort if Cartesian feedback differs from a waypoint "
            "by more than this amount. Default matches guarded Task10: 45 mm."
        ),
    )
    parser.add_argument(
        "--min-random-z-mm",
        type=float,
        default=150.0,
        help="Random high pose must report at least this Z.",
    )
    parser.add_argument(
        "--settle-timeout-s",
        type=float,
        default=15.0,
    )
    parser.add_argument(
        "--require-confirm-each-random",
        action="store_true",
        help="Ask for ENTER before every random high-pose move.",
    )
    parser.add_argument(
        "--measurement-resolution-mm",
        type=float,
        default=1.0,
        help=(
            "Practical manual needle-paper measurement resolution. "
            "Default: 1.0 mm."
        ),
    )

    return parser.parse_args()


def load_yunkai_core(core_dir: str, serial_port: str, baud: int):
    core_path = Path(core_dir)
    core_file = core_path / "task10_guarded_approach.py"

    if not core_file.exists():
        raise FileNotFoundError(
            "Yunkai core file not found:\n"
            f"  {core_file}\n"
            "Check --core-dir and make sure the FURP repository is present."
        )

    if str(core_path) not in sys.path:
        sys.path.insert(0, str(core_path))

    core = importlib.import_module("task10_guarded_approach")

    # Override the defaults from Yunkai's source so the experiment can
    # explicitly choose the WSL serial device.
    core.SERIAL_PORT = serial_port
    core.BAUD_RATE = baud

    return core, core_file


def append_csv(path: Path, row: Dict):
    exists = path.exists()

    with path.open(
        "a",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=CSV_FIELDS,
        )

        if not exists:
            writer.writeheader()

        writer.writerow(row)


def blank_random_fields() -> Dict:
    return {
        "random_base_rad": "",
        "random_shoulder_rad": "",
        "random_elbow_rad": "",
        "random_wrist_rad": "",
        "random_roll_rad": "",
        "random_hand_rad": "",
        "random_feedback_x_mm": "",
        "random_feedback_y_mm": "",
        "random_feedback_z_mm": "",
    }


def random_high_pose(rng: random.Random) -> Dict:
    """
    Conservative random joint pose near Yunkai Task10 official home:
      base=0
      shoulder=0
      elbow=1.57
      wrist=0
      roll=0
      hand=3.14

    The ranges are intentionally small for E0-B. The goal is to leave the
    target and return from a different configuration, not to explore the
    full joint workspace.
    """
    return {
        "T": 102,
        "base": round(rng.uniform(-0.22, 0.22), 5),
        "shoulder": round(rng.uniform(-0.10, 0.10), 5),
        "elbow": round(rng.uniform(1.44, 1.70), 5),
        "wrist": round(rng.uniform(-0.12, 0.12), 5),
        "roll": round(rng.uniform(-0.18, 0.18), 5),
        "hand": 3.14,
        "spd": 220,
        "acc": 10,
    }


def pose_xyz(pose: Dict) -> Tuple[float, float, float]:
    return (
        float(pose["x"]),
        float(pose["y"]),
        float(pose["z"]),
    )


def wait_cartesian_settle(
    core,
    timeout_s: float,
    movement_threshold_mm: float = 1.0,
    stable_required: int = 3,
) -> Dict:
    deadline = time.time() + timeout_s
    previous: Optional[Tuple[float, float, float]] = None
    stable_count = 0
    latest_pose: Optional[Dict] = None

    while time.time() < deadline:
        try:
            latest_pose = core.get_pose()
            xyz = pose_xyz(latest_pose)
        except Exception:
            time.sleep(0.10)
            continue

        if previous is not None:
            movement = math.dist(xyz, previous)

            if movement < movement_threshold_mm:
                stable_count += 1
            else:
                stable_count = 0

        previous = xyz

        print(
            f"\rFeedback XYZ mm: "
            f"{xyz[0]:.1f}, {xyz[1]:.1f}, {xyz[2]:.1f}",
            end="",
            flush=True,
        )

        if stable_count >= stable_required:
            print()
            return latest_pose

        time.sleep(0.10)

    print()

    if latest_pose is None:
        raise RuntimeError("No usable robot feedback during settling.")

    raise RuntimeError(
        f"Robot did not settle within {timeout_s:.1f} s."
    )


def move_joint_random_and_verify(
    core,
    command: Dict,
    args: argparse.Namespace,
) -> Dict:
    print("\n===== RANDOM HIGH POSE =====")
    print(json.dumps(command, indent=2))

    response = core.send_json(
        command,
        0.3,
    )

    if response.strip():
        print("Response:", response.strip())

    pose = wait_cartesian_settle(
        core,
        timeout_s=args.settle_timeout_s,
    )

    x, y, z = pose_xyz(pose)

    print(
        "Random-pose settled XYZ mm:",
        f"({x:.2f}, {y:.2f}, {z:.2f})",
    )

    if z < args.min_random_z_mm:
        raise RuntimeError(
            f"Random pose Z={z:.2f} mm is below "
            f"minimum {args.min_random_z_mm:.2f} mm."
        )

    # Broad sanity bounds, not an accuracy criterion.
    if not (
        -50.0 <= x <= 450.0
        and -350.0 <= y <= 350.0
        and z <= 400.0
    ):
        raise RuntimeError(
            "Random pose feedback is outside conservative sanity bounds: "
            f"({x:.2f}, {y:.2f}, {z:.2f})"
        )

    return pose


def move_cartesian_hard_abort(
    core,
    label: str,
    command: Dict,
    args: argparse.Namespace,
    surface_z_mm: float,
) -> Tuple[Dict, float]:
    """
    Based on Yunkai Final's move_without_error_abort(), but changed so a
    large tracking difference HARD-ABORTS the current run.
    """
    print(f"\n===== {label} =====")
    print("Command:", command)

    response = core.send_json(
        command,
        0.3,
    )

    if response.strip():
        print("Response:", response.strip())

    pose = wait_cartesian_settle(
        core,
        timeout_s=args.settle_timeout_s,
    )

    actual = pose_xyz(pose)
    expected = (
        float(command["x"]),
        float(command["y"]),
        float(command["z"]),
    )

    tracking_error = math.dist(
        actual,
        expected,
    )

    print(
        "Actual XYZ mm:",
        f"({actual[0]:.2f}, {actual[1]:.2f}, {actual[2]:.2f})",
    )
    print(
        "Tracking difference mm:",
        f"{tracking_error:.3f}",
    )

    # Preserve Yunkai Final's last-zone physical protection.
    if actual[2] < surface_z_mm + 5.0:
        raise RuntimeError(
            "Actual Z entered the final 5 mm "
            "surface-protection zone."
        )

    # Change from Final: do NOT only print a warning.
    if tracking_error > args.max_tracking_error_mm:
        raise RuntimeError(
            f"{label} tracking error {tracking_error:.2f} mm exceeds "
            f"hard limit {args.max_tracking_error_mm:.2f} mm."
        )

    return pose, tracking_error


def yunkai_final_waypoints(
    tx: float,
    ty: float,
    tz: float,
    clearance_mm: float,
) -> List[Dict]:
    """
    Same three waypoint geometry as
    task10_marker_approach_10mm( Final ).py
    """
    approach_z = tz + clearance_mm

    return [
        {
            "T": 104,
            "x": tx,
            "y": ty,
            "z": 170.0,
            "t": 0.75,
            "r": 0.0,
            "g": 1.57,
            "spd": 0.12,
        },
        {
            "T": 104,
            "x": tx - 10.0,
            "y": ty,
            "z": 50.0,
            "t": 1.42,
            "r": 0.0,
            "g": 1.57,
            "spd": 0.08,
        },
        {
            "T": 104,
            "x": tx,
            "y": ty,
            "z": approach_z,
            "t": 1.52,
            "r": 0.0,
            "g": 1.57,
            "spd": 0.05,
        },
    ]


def run_fixed_target_approach(
    core,
    tx: float,
    ty: float,
    tz: float,
    args: argparse.Namespace,
) -> Tuple[Dict, float]:
    open_gripper = {
        "T": 106,
        "cmd": 1.57,
        "spd": 300,
        "acc": 10,
    }

    print("\nOpening gripper...")
    response = core.send_json(
        open_gripper,
        1.0,
    )

    if response.strip():
        print(response.strip())

    waypoints = yunkai_final_waypoints(
        tx,
        ty,
        tz,
        args.clearance_mm,
    )

    final_pose = None
    final_error = float("nan")

    for index, waypoint in enumerate(
        waypoints,
        start=1,
    ):
        final_pose, final_error = move_cartesian_hard_abort(
            core=core,
            label=f"Approach {index}/{len(waypoints)}",
            command=waypoint,
            args=args,
            surface_z_mm=tz,
        )

    assert final_pose is not None

    return final_pose, final_error



def retract_from_fixed_target(
    core,
    tx: float,
    ty: float,
    tz: float,
    args: argparse.Namespace,
) -> None:
    """
    Retract from the fixed 10 mm approach point through the SAME Task10 Final
    path in reverse, stopping at the high waypoint before any random joint move.

    Final -> (tx-10, ty, 50) -> (tx, ty, 170)
    """
    waypoints = yunkai_final_waypoints(
        tx,
        ty,
        tz,
        args.clearance_mm,
    )

    # Exclude the final low waypoint; traverse the preceding waypoints in reverse.
    retract_waypoints = list(reversed(waypoints[:-1]))

    print("\n===== SAFE RETRACTION BEFORE RANDOM START =====")

    for index, waypoint in enumerate(retract_waypoints, start=1):
        move_cartesian_hard_abort(
            core=core,
            label=f"Retract {index}/{len(retract_waypoints)}",
            command=waypoint,
            args=args,
            surface_z_mm=tz,
        )


def parse_threshold_measurement(
    trial_index: int,
    resolution_mm: float,
) -> Dict:
    """
    Threshold/censored manual measurement for E0-B.

    The current needle-paper method cannot reliably resolve sub-resolution
    offsets. Therefore:
      b -> all XYZ offsets are below / not resolvable at the practical
           measurement resolution; numeric XYZ fields are intentionally blank.
      m -> at least one axis is clearly larger than the resolution; record
           signed numeric dx dy dz.
      q -> abort.

    This prevents "below 1 mm" observations from being silently converted into
    exact 0 mm values and then producing a misleading SD=0 result.
    """
    print()
    print("MANUAL PHYSICAL MEASUREMENT — THRESHOLD MODE")
    print("--------------------------------------------")
    print("Measure relative to Trial 1 baseline.")
    print(
        f"Practical needle-paper resolution: ~{resolution_mm:.2f} mm"
    )
    print()
    print("Choose:")
    print(
        "  b = no axis has a clearly resolvable displacement "
        f"> ~{resolution_mm:.2f} mm"
    )
    print(
        "      (store as BELOW RESOLUTION; numeric dx/dy/dz stay blank)"
    )
    print(
        "  m = at least one axis is clearly displaced "
        f"> ~{resolution_mm:.2f} mm"
    )
    print("      then enter signed dx dy dz in mm")
    print("  q = abort")
    print()
    print("Directions:")
    print("  +X = robot base +X")
    print("  +Y = robot base +Y")
    print("  +Z = upward")
    print(
        "Do NOT invent sub-mm decimals. Use m only for a clearly "
        "resolvable >threshold displacement."
    )

    while True:
        choice = input(
            f"Trial {trial_index} result [b/m/q] > "
        ).strip().lower()

        if choice == "q":
            raise KeyboardInterrupt

        if choice in ("b", "below", "<1", "below_resolution"):
            note = input(
                "Optional note (ENTER for none) > "
            ).strip()
            return {
                "measurement_class": "below_resolution",
                "exceeds_resolution": False,
                "manual_dx_mm": "",
                "manual_dy_mm": "",
                "manual_dz_mm": "",
                "manual_xy_offset_mm": "",
                "manual_3d_offset_mm": "",
                "notes": note or (
                    f"No visually resolvable axis displacement "
                    f"> ~{resolution_mm:.2f} mm"
                ),
            }

        if choice in ("m", "measurable", "measured"):
            print()
            print("Input signed dx dy dz in mm.")
            print("Example: 1.5 -2 0")
            print(
                "Use 0 only if that axis has no visibly resolvable displacement."
            )
            print("Optional note after the three values is allowed.")

            raw = input(
                f"Trial {trial_index} measurable dx dy dz > "
            ).strip()

            if raw.lower() == "q":
                raise KeyboardInterrupt

            parts = raw.replace(",", " ").split()
            if len(parts) < 3:
                print("[WARN] Need three numbers: dx dy dz")
                continue

            try:
                dx = float(parts[0])
                dy = float(parts[1])
                dz = float(parts[2])
            except ValueError:
                print("[WARN] dx/dy/dz must be numeric.")
                continue

            if max(abs(dx), abs(dy), abs(dz)) <= resolution_mm:
                print(
                    "[WARN] No entered axis exceeds the current "
                    f"~{resolution_mm:.2f} mm threshold."
                )
                print(
                    "Use 'b' if the displacement is not reliably resolvable."
                )
                continue

            xy = math.hypot(dx, dy)
            d3 = math.sqrt(dx * dx + dy * dy + dz * dz)
            note = " ".join(parts[3:])

            return {
                "measurement_class": "measurable_exceedance",
                "exceeds_resolution": True,
                "manual_dx_mm": dx,
                "manual_dy_mm": dy,
                "manual_dz_mm": dz,
                "manual_xy_offset_mm": xy,
                "manual_3d_offset_mm": d3,
                "notes": note or (
                    f"At least one axis clearly exceeded "
                    f"~{resolution_mm:.2f} mm"
                ),
            }

        print("[WARN] Enter b, m, or q.")


def summary_stats(values: List[float]) -> Dict:
    if not values:
        return {}

    result = {
        "n": len(values),
        "mean": float(statistics.mean(values)),
        "min": float(min(values)),
        "max": float(max(values)),
    }

    if len(values) >= 2:
        result["sd"] = float(
            statistics.stdev(values)
        )
    else:
        result["sd"] = 0.0

    ordered = sorted(values)

    # Linear percentile, adequate for the small E0-B descriptive sample.
    def percentile(p: float) -> float:
        if len(ordered) == 1:
            return ordered[0]

        rank = (len(ordered) - 1) * p
        lo = int(math.floor(rank))
        hi = int(math.ceil(rank))

        if lo == hi:
            return ordered[lo]

        frac = rank - lo
        return (
            ordered[lo] * (1.0 - frac)
            + ordered[hi] * frac
        )

    result["p50"] = float(percentile(0.50))
    result["p95"] = float(percentile(0.95))

    return result


def write_summary(
    path: Path,
    rows: List[Dict],
    run_meta: Dict,
):
    successful_motion = [
        row for row in rows
        if str(row.get("success")).lower() == "true"
    ]

    comparisons = [
        row for row in successful_motion
        if not bool(row.get("is_baseline"))
    ]

    below = [
        row for row in comparisons
        if row.get("measurement_class") == "below_resolution"
    ]

    measurable = [
        row for row in comparisons
        if row.get("measurement_class") == "measurable_exceedance"
    ]

    unclassified = [
        row for row in comparisons
        if row.get("measurement_class")
        not in ("below_resolution", "measurable_exceedance")
    ]

    resolution_mm = float(
        run_meta.get("measurement_resolution_mm", 1.0)
    )

    measurable_events = []
    for row in measurable:
        measurable_events.append({
            "trial_index": row.get("trial_index"),
            "dx_mm": row.get("manual_dx_mm"),
            "dy_mm": row.get("manual_dy_mm"),
            "dz_mm": row.get("manual_dz_mm"),
            "xy_offset_mm": row.get("manual_xy_offset_mm"),
            "3d_offset_mm": row.get("manual_3d_offset_mm"),
            "notes": row.get("notes", ""),
        })

    comparison_n = len(comparisons)
    exceed_n = len(measurable)

    data = {
        **run_meta,
        "successful_motion_arrivals": len(successful_motion),
        "comparison_trials_excluding_baseline": comparison_n,
        "threshold_result": {
            "measurement_resolution_mm_approx": resolution_mm,
            "below_resolution_count": len(below),
            "measurable_exceedance_count": exceed_n,
            "unclassified_count": len(unclassified),
            "exceedance_rate": (
                exceed_n / comparison_n
                if comparison_n > 0
                else None
            ),
            "measurable_exceedance_events": measurable_events,
        },
        "statistics_note": (
            "Sub-resolution observations are censored and are NOT converted "
            "to exact zeros. Therefore no continuous repeatability SD is "
            "reported from the manual needle-paper measurements. The primary "
            "result is the count/rate of arrivals with a clearly resolvable "
            "displacement above the practical measurement threshold."
        ),
    }

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def main():
    args = parse_args()

    if args.trials < 2:
        raise SystemExit(
            "--trials must be at least 2."
        )

    if args.measurement_resolution_mm <= 0:
        raise SystemExit(
            "[PREFLIGHT FAILED] --measurement-resolution-mm must be > 0."
        )

    if args.clearance_mm < 10.0:
        raise SystemExit(
            "Refusing clearance below 10 mm for this E0-B script."
        )

    core, core_file = load_yunkai_core(
        core_dir=args.core_dir,
        serial_port=args.serial_port,
        baud=args.baud,
    )

    output_root = Path(args.output_root)
    raw_dir = output_root / "raw"
    results_dir = output_root / "results"

    raw_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    results_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_id = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    csv_path = (
        raw_dir
        / f"E0B_robot_repeatability_{args.trials}trials_{run_id}.csv"
    )

    summary_path = (
        results_dir
        / f"E0B_robot_repeatability_{args.trials}trials_{run_id}_summary.json"
    )

    rng = random.Random(args.seed)

    print()
    print("=" * 72)
    print("E0-B2 VARIED-START / PATH-DEPENDENCE — YUNKAI FINAL PIPELINE")
    print("=" * 72)
    print("Yunkai core :", core_file)
    print("Serial      :", args.serial_port)
    print("Baud        :", args.baud)
    print("Trials      :", args.trials)
    print("Random seed :", args.seed)
    print("Clearance   :", f"{args.clearance_mm:.1f} mm")
    print("Output CSV  :", csv_path)
    print("=" * 72)
    print()
    print("Definition:")
    print("  Trial 1 physical endpoint = baseline (0,0,0).")
    print("  Trials 2..N are measured relative to Trial 1.")
    print("  This tests varied-start/path dependence, not pure same-start repeatability.")
    print()

    # Basic dependency / device preflight.
    if not Path(args.serial_port).exists():
        raise SystemExit(
            f"[PREFLIGHT FAILED] Serial device does not exist: "
            f"{args.serial_port}\n"
            "Attach the RoArm USB device into WSL first."
        )

    try:
        import serial  # noqa: F401
    except Exception as exc:
        raise SystemExit(
            "[PREFLIGHT FAILED] Python pyserial is missing.\n"
            "Install with: sudo apt install python3-serial\n"
            f"Original error: {exc}"
        )

    print("[PREFLIGHT] Yunkai core import: OK")
    print("[PREFLIGHT] Serial device exists: OK")
    print("[PREFLIGHT] pyserial import: OK")

    # Official Yunkai Task10 home.
    home = {
        "T": 102,
        "base": 0.0,
        "shoulder": 0.0,
        "elbow": 1.57,
        "wrist": 0.0,
        "roll": 0.0,
        "hand": 3.14,
        "spd": 300,
        "acc": 10,
    }

    input(
        "\nClear the full robot workspace. "
        "Press ENTER to move to Yunkai Task10 HOME..."
    )

    print("\nReturning to official Task10 home...")
    response = core.send_json(
        home,
        0.3,
    )

    if response.strip():
        print(response.strip())

    home_pose = wait_cartesian_settle(
        core,
        timeout_s=args.settle_timeout_s,
    )

    home_xyz = pose_xyz(home_pose)

    print(
        "Home XYZ mm:",
        f"({home_xyz[0]:.2f}, {home_xyz[1]:.2f}, {home_xyz[2]:.2f})",
    )

    if home_xyz[2] < 150.0:
        raise RuntimeError(
            "Official home was not reached safely: "
            f"Z={home_xyz[2]:.2f} mm < 150 mm."
        )

    input(
        "\nMake sure BOTH Yunkai cameras can see Marker 4 and the "
        "original Yunkai fusion/correction nodes are running. "
        "Press ENTER to scan the target ONCE..."
    )

    print("\nCollecting 10 accepted fused robot-corrected samples...")
    tx, ty, tz = core.collect_target()

    approach_z = tz + args.clearance_mm

    print()
    print("===== FROZEN SCANNED TARGET =====")
    print(f"Marker X        : {tx:.3f} mm")
    print(f"Marker Y        : {ty:.3f} mm")
    print(f"Marker Z        : {tz:.3f} mm")
    print(f"Fixed final X   : {tx:.3f} mm")
    print(f"Fixed final Y   : {ty:.3f} mm")
    print(f"Fixed final Z   : {approach_z:.3f} mm")
    print("Target will NOT be rescanned during the repeatability run.")
    print()

    if not (
        80.0 <= tx <= 350.0
        and -300.0 <= ty <= 300.0
        and -150.0 <= tz <= 50.0
    ):
        raise RuntimeError(
            "Scanned marker is outside Yunkai Final configured workspace."
        )

    confirmation = input(
        "Check the frozen target. Type E0B to start: "
    ).strip()

    if confirmation != "E0B":
        print("Cancelled.")
        return

    rows: List[Dict] = []

    run_meta = {
        "experiment": "E0-B Robot Repeatability",
        "method": (
            "Yunkai Task10 Final target scan once; fixed target; "
            "manual signed XYZ offsets relative to Trial 1"
        ),
        "run_id": run_id,
        "trials_requested": args.trials,
        "random_seed": args.seed,
        "serial_port": args.serial_port,
        "baud": args.baud,
        "yunkai_core_file": str(core_file),
        "scan_target_mm": {
            "x": tx,
            "y": ty,
            "z": tz,
        },
        "fixed_final_target_mm": {
            "x": tx,
            "y": ty,
            "z": approach_z,
        },
        "clearance_mm": args.clearance_mm,
        "max_tracking_error_mm": args.max_tracking_error_mm,
        "measurement_resolution_mm": args.measurement_resolution_mm,
        "measurement_protocol": (
            "Threshold/censored manual needle-paper measurement: "
            "below-resolution observations are stored without numeric XYZ."
        ),
        "baseline_definition": (
            "Trial 1 physical endpoint; baseline only. "
            "Comparison statistics exclude Trial 1."
        ),
    }

    try:
        for trial_index in range(
            1,
            args.trials + 1,
        ):
            print()
            print("=" * 72)
            print(
                f"TRIAL {trial_index}/{args.trials}"
            )
            print("=" * 72)

            random_command = None
            random_pose = None

            if trial_index > 1:
                # Safety-critical: never jump directly from the low final
                # approach point into a random joint pose. First retract
                # through the Task10 Final path to the high waypoint.
                retract_from_fixed_target(
                    core=core,
                    tx=tx,
                    ty=ty,
                    tz=tz,
                    args=args,
                )

                random_command = random_high_pose(
                    rng
                )

                if args.require_confirm_each_random:
                    print()
                    print("===== RANDOM HIGH POSE PREVIEW =====")
                    print(json.dumps(random_command, indent=2))
                    input(
                        "Check the random pose above. "
                        "Press ENTER to execute..."
                    )

                random_pose = move_joint_random_and_verify(
                    core=core,
                    command=random_command,
                    args=args,
                )

            try:
                final_pose, final_tracking_error = (
                    run_fixed_target_approach(
                        core=core,
                        tx=tx,
                        ty=ty,
                        tz=tz,
                        args=args,
                    )
                )
            except Exception as exc:
                row = {
                    "run_id": run_id,
                    "trial_index": trial_index,
                    "is_baseline": trial_index == 1,
                    "timestamp": datetime.now().isoformat(
                        timespec="seconds"
                    ),
                    "scan_tx_mm": tx,
                    "scan_ty_mm": ty,
                    "scan_tz_mm": tz,
                    "fixed_target_x_mm": tx,
                    "fixed_target_y_mm": ty,
                    "fixed_target_z_mm": approach_z,
                    "clearance_mm": args.clearance_mm,
                    "random_seed": args.seed,
                    **blank_random_fields(),
                    "final_feedback_x_mm": "",
                    "final_feedback_y_mm": "",
                    "final_feedback_z_mm": "",
                    "final_tracking_error_mm": "",
                    "measurement_class": "motion_failure",
                    "measurement_resolution_mm": args.measurement_resolution_mm,
                    "exceeds_resolution": "",
                    "manual_dx_mm": "",
                    "manual_dy_mm": "",
                    "manual_dz_mm": "",
                    "manual_xy_offset_mm": "",
                    "manual_3d_offset_mm": "",
                    "success": False,
                    "failure_type": type(exc).__name__,
                    "notes": str(exc),
                }

                if random_command is not None:
                    row.update({
                        "random_base_rad": random_command["base"],
                        "random_shoulder_rad": random_command["shoulder"],
                        "random_elbow_rad": random_command["elbow"],
                        "random_wrist_rad": random_command["wrist"],
                        "random_roll_rad": random_command["roll"],
                        "random_hand_rad": random_command["hand"],
                    })

                if random_pose is not None:
                    rx, ry, rz = pose_xyz(random_pose)
                    row.update({
                        "random_feedback_x_mm": rx,
                        "random_feedback_y_mm": ry,
                        "random_feedback_z_mm": rz,
                    })

                append_csv(
                    csv_path,
                    row,
                )
                rows.append(row)

                print(
                    "\n[HARD ABORT] Trial failed:",
                    exc,
                )
                raise

            final_x, final_y, final_z = pose_xyz(
                final_pose
            )

            if trial_index == 1:
                print()
                print("===== BASELINE =====")
                print(
                    "This physical endpoint is Trial 1 baseline."
                )
                print(
                    "Use your pen/ruler to establish the XYZ reference now."
                )
                input(
                    "When the baseline marks/reference are fixed, "
                    "press ENTER..."
                )

                measurement = {
                    "measurement_class": "baseline",
                    "exceeds_resolution": False,
                    "manual_dx_mm": 0.0,
                    "manual_dy_mm": 0.0,
                    "manual_dz_mm": 0.0,
                    "manual_xy_offset_mm": 0.0,
                    "manual_3d_offset_mm": 0.0,
                    "notes": "Trial 1 physical baseline",
                }
            else:
                measurement = parse_threshold_measurement(
                    trial_index=trial_index,
                    resolution_mm=args.measurement_resolution_mm,
                )

            row = {
                "run_id": run_id,
                "trial_index": trial_index,
                "is_baseline": trial_index == 1,
                "timestamp": datetime.now().isoformat(
                    timespec="seconds"
                ),

                "scan_tx_mm": tx,
                "scan_ty_mm": ty,
                "scan_tz_mm": tz,
                "fixed_target_x_mm": tx,
                "fixed_target_y_mm": ty,
                "fixed_target_z_mm": approach_z,
                "clearance_mm": args.clearance_mm,

                "random_seed": args.seed,
                **blank_random_fields(),

                "final_feedback_x_mm": final_x,
                "final_feedback_y_mm": final_y,
                "final_feedback_z_mm": final_z,
                "final_tracking_error_mm": final_tracking_error,

                "measurement_class": measurement["measurement_class"],
                "measurement_resolution_mm": args.measurement_resolution_mm,
                "exceeds_resolution": measurement["exceeds_resolution"],
                "manual_dx_mm": measurement["manual_dx_mm"],
                "manual_dy_mm": measurement["manual_dy_mm"],
                "manual_dz_mm": measurement["manual_dz_mm"],
                "manual_xy_offset_mm": measurement["manual_xy_offset_mm"],
                "manual_3d_offset_mm": measurement["manual_3d_offset_mm"],

                "success": True,
                "failure_type": "none",
                "notes": measurement["notes"],
            }

            if random_command is not None:
                row.update({
                    "random_base_rad": random_command["base"],
                    "random_shoulder_rad": random_command["shoulder"],
                    "random_elbow_rad": random_command["elbow"],
                    "random_wrist_rad": random_command["wrist"],
                    "random_roll_rad": random_command["roll"],
                    "random_hand_rad": random_command["hand"],
                })

            if random_pose is not None:
                rx, ry, rz = pose_xyz(
                    random_pose
                )
                row.update({
                    "random_feedback_x_mm": rx,
                    "random_feedback_y_mm": ry,
                    "random_feedback_z_mm": rz,
                })

            append_csv(
                csv_path,
                row,
            )
            rows.append(row)

            print()
            if measurement["measurement_class"] == "baseline":
                print(
                    f"[TRIAL {trial_index} SAVED] BASELINE"
                )
            elif measurement["measurement_class"] == "below_resolution":
                print(
                    f"[TRIAL {trial_index} SAVED] "
                    f"BELOW RESOLUTION (~{args.measurement_resolution_mm:.2f} mm); "
                    "numeric XYZ intentionally left blank"
                )
            else:
                print(
                    f"[TRIAL {trial_index} SAVED] MEASURABLE EXCEEDANCE "
                    f"dx={measurement['manual_dx_mm']:+.2f} mm, "
                    f"dy={measurement['manual_dy_mm']:+.2f} mm, "
                    f"dz={measurement['manual_dz_mm']:+.2f} mm, "
                    f"XY={measurement['manual_xy_offset_mm']:.2f} mm, "
                    f"3D={measurement['manual_3d_offset_mm']:.2f} mm"
                )

        print()
        print("=" * 72)
        print("ALL REQUESTED TRIALS COMPLETE")
        print("=" * 72)

    except KeyboardInterrupt:
        print(
            "\n[INTERRUPTED] Existing CSV rows are preserved."
        )

    except Exception as exc:
        print()
        print(
            "[RUN STOPPED FOR SAFETY]",
            f"{type(exc).__name__}: {exc}",
        )
        print(
            "Existing CSV rows are preserved. "
            "Do not continue automatic motion until the cause is checked."
        )

    finally:
        if rows:
            write_summary(
                summary_path,
                rows,
                run_meta,
            )

            successful_motion = [
                r for r in rows
                if r.get("success") is True
            ]

            comparisons = [
                r for r in successful_motion
                if not bool(r.get("is_baseline"))
            ]

            below = [
                r for r in comparisons
                if r.get("measurement_class") == "below_resolution"
            ]

            measurable = [
                r for r in comparisons
                if r.get("measurement_class") == "measurable_exceedance"
            ]

            print()
            print("===== QUICK SUMMARY =====")
            print(
                f"successful motion arrivals: "
                f"{len(successful_motion)}/{args.trials}"
            )
            print(
                f"comparison trials (excluding baseline): "
                f"{len(comparisons)}"
            )
            print(
                f"below ~{args.measurement_resolution_mm:.2f} mm resolution: "
                f"{len(below)}/{len(comparisons)}"
                if comparisons
                else "below-resolution comparisons: n/a"
            )
            print(
                f"measurable >~{args.measurement_resolution_mm:.2f} mm: "
                f"{len(measurable)}/{len(comparisons)}"
                if comparisons
                else "measurable exceedances: n/a"
            )

            if comparisons:
                rate = 100.0 * len(measurable) / len(comparisons)
                print(
                    f"exceedance rate: {rate:.1f}%"
                )

            if measurable:
                print("measurable events:")
                for r in measurable:
                    print(
                        f"  trial {r['trial_index']}: "
                        f"dx={float(r['manual_dx_mm']):+.2f}, "
                        f"dy={float(r['manual_dy_mm']):+.2f}, "
                        f"dz={float(r['manual_dz_mm']):+.2f} mm"
                    )

            print(
                "continuous manual XYZ SD: NOT REPORTED "
                "(sub-resolution observations are censored)"
            )

            print()
            print("Saved CSV:")
            print(" ", csv_path)
            print("Saved summary:")
            print(" ", summary_path)


if __name__ == "__main__":
    main()
