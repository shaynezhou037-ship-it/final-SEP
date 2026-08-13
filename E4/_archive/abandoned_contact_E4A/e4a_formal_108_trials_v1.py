#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4-A FORMAL END-TO-END ROBOT EXPERIMENT — V1
=============================================

PRIMARY E4-A DESIGN
-------------------
9 formal planar held-out targets
x 4 methods:
    Oracle
    Affine
    Homography
    PnP_IPPE
x 3 robot repeats
= 108 physical endpoint trials

IMPORTANT METHODOLOGICAL CHOICE
-------------------------------
This script DOES NOT re-detect the ChArUco target during robot trials.

It reads the already-FROZEN 9-point held-out vision predictions produced by:
    E4_model_freeze_v1/<runid>/E4_heldout_model_results.csv

Therefore:
- Affine/Homography/PnP predictions are frozen BEFORE robot execution.
- All 3 robot repeats for a method/target use the same frozen visual estimate.
- The 3 repeats measure propagation through the downstream robot system,
  rather than re-sampling the vision detector.
- Oracle uses the known physical paper GT and bypasses vision.
- Camera images may be affected by later physical marks without changing E4-A.
- Camera/paper/robot base must nevertheless remain physically fixed.

FORMAL CAMERA
-------------
Default = ihawk1.
This gives exactly 108 E4-A moves.

ihawk2 can later be run as a separate optional/bonus E4-A replication:
    --camera ihawk2

FROZEN DOWNSTREAM CONFIGURATION
-------------------------------
paper -> robot registration:
  robot_x = -0.074105303*paper_x + 0.992259200*paper_y + 187.854293495
  robot_y = -0.986716324*paper_x - 0.006933251*paper_y -   4.851741339
  robot_z =  0.001405397*paper_x + 0.006345201*paper_y - 118.909081155

Robot:
  base PID = P16 / I8
  other joints = current/default
  controller = T104 Cartesian only
  NO extra T101 correction
  target tit = 1.5 rad

Contact:
  HIGH     = registration-predicted surface +40 mm
  CONTACT  = registration-predicted surface +10 mm
  same XY during vertical descent
  then vertical rise and fixed-start return

GROUND TRUTH / OUTCOMES
-----------------------
GT = known physical ChArUco corner coordinate in paper_frame.

For each trial, after the robot returns to fixed start, the user measures
the physical mark in paper_frame and enters:
    x,y
Example:
    -65.5,32.0

The script computes:
1) vision error:
      predicted paper XY - GT paper XY
2) T105 internal execution residual:
      firmware-reported robot pose - commanded robot pose
   (diagnostic only; NOT independent GT)
3) physical E2E error [PRIMARY]:
      physical mark XY - GT paper XY
4) physical downstream residual:
      physical mark XY - predicted paper XY
   (contains paper->robot registration + controller + mechanics + measurement)

ORDER CONTROL
-------------
- Target order is deterministically shuffled for each repeat using seed 20260811.
- Method order uses a rotating 4x4 Latin cycle:
    O A H P
    A H P O
    H P O A
    P O A H
- The full 108-trial plan is written BEFORE robot execution.
- The plan is never altered based on observed errors.

RESUME
------
The script saves after EVERY trial.

New run:
    python3 e4a_formal_108_trials_v1.py --port /dev/ttyUSB0

Resume an interrupted run:
    python3 e4a_formal_108_trials_v1.py \
      --port /dev/ttyUSB0 \
      --resume /mnt/c/.../E4A_formal_ihawk1/<runid>

On resume, the same frozen plan is reused and completed trial_uid values are
skipped. Each serial-open session is logged separately because opening the
controller may reset the robot.

SAFETY
------
- Keep one hand near robot power.
- Nothing else may use /dev/ttyUSB0.
- Every trial requires explicit GO before motion.
- Before CONTACT, the script checks the HIGH T105 pose.
- If HIGH T105 3D residual > 20 mm, the trial is blocked before descent.
- If paper/board/robot base moved, STOP; the frozen transforms are invalid.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import serial


# =============================================================================
# FROZEN E4 CONFIGURATION
# =============================================================================

PAPER_TO_ROBOT = {
    "robot_x": (-0.074105303, +0.992259200, +187.854293495),
    "robot_y": (-0.986716324, -0.006933251,   -4.851741339),
    "robot_z": (+0.001405397, +0.006345201, -118.909081155),
}

BASE_PID_P = 16
BASE_PID_I = 8

TARGET_TIT_RAD = 1.5
SAFE_HIGH_MM = 40.0
CONTACT_OFFSET_MM = 10.0

T104_TRAVEL_SPD = 0.05
T104_DESCENT_SPD = 0.02

BOOT_WAIT_S = 22.0
START_WAIT_S = 10.0
HIGH_WAIT_S = 12.0
CONTACT_WAIT_S = 8.0
RISE_WAIT_S = 8.0

HIGH_3D_RESIDUAL_GATE_MM = 20.0

PLAN_SEED = 20260811

METHODS = ["Oracle", "Affine", "Homography", "PnP_IPPE"]

LATIN_METHOD_ORDERS = [
    ["Oracle", "Affine", "Homography", "PnP_IPPE"],
    ["Affine", "Homography", "PnP_IPPE", "Oracle"],
    ["Homography", "PnP_IPPE", "Oracle", "Affine"],
    ["PnP_IPPE", "Oracle", "Affine", "Homography"],
]


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)

    p.add_argument(
        "--camera",
        choices=["ihawk1", "ihawk2"],
        default="ihawk1",
        help="Formal vision source. Default ihawk1.",
    )

    p.add_argument(
        "--freeze-root",
        default="/mnt/c/Users/ASUS/Desktop/paper/E4/E4_model_freeze_v1",
        help="Root containing frozen E4_model_freeze_v1 run folders.",
    )

    p.add_argument(
        "--freeze-run",
        default=None,
        help=(
            "Optional exact frozen run directory. If omitted, auto-select the "
            "latest run containing E4_heldout_model_results.csv."
        ),
    )

    p.add_argument(
        "--out-root",
        default="/mnt/c/Users/ASUS/Desktop/paper/E4",
    )

    p.add_argument(
        "--resume",
        default=None,
        help="Existing E4-A run directory to resume.",
    )

    p.add_argument(
        "--max-trials",
        type=int,
        default=0,
        help=(
            "0 = all remaining trials. Nonzero = stop cleanly after this many "
            "trials in the current session. Useful for splitting 108 trials."
        ),
    )

    return p.parse_args()


# =============================================================================
# GENERIC HELPERS
# =============================================================================

def now_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def iso_now():
    return datetime.now().isoformat(timespec="seconds")


def read_csv(path: Path) -> List[dict]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[dict], fields: Optional[List[str]] = None):
    if fields is None:
        if not rows:
            return
        fields = list(rows[0].keys())

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def fnum(x):
    if x in ("", None):
        return None
    return float(x)


def metric_summary(vals):
    a = [float(x) for x in vals]
    if not a:
        return None

    return {
        "n": len(a),
        "mean_mm": statistics.mean(a),
        "rmse_mm": math.sqrt(sum(x*x for x in a) / len(a)),
        "median_mm": statistics.median(a),
        "sd_mm": statistics.stdev(a) if len(a) > 1 else 0.0,
        "max_mm": max(a),
    }


def paper_to_robot(px: float, py: float):
    def f(c):
        return c[0] * px + c[1] * py + c[2]

    return (
        f(PAPER_TO_ROBOT["robot_x"]),
        f(PAPER_TO_ROBOT["robot_y"]),
        f(PAPER_TO_ROBOT["robot_z"]),
    )


def pose_residual(state, target_xyz):
    tx, ty, tz = target_xyz
    dx = float(state["x"]) - tx
    dy = float(state["y"]) - ty
    dz = float(state["z"]) - tz
    xy = math.hypot(dx, dy)
    e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx, dy, dz, xy, e3


def print_pose(label, state, target=None):
    print("\n" + "=" * 82)
    print(label)
    print(
        f"XYZ=({state['x']:.3f}, {state['y']:.3f}, {state['z']:.3f}) mm | "
        f"b={state['b']:.6f} s={state['s']:.6f} "
        f"e={state['e']:.6f} t={state['t']:.6f} r={state['r']:.6f}"
    )

    if target is not None:
        dx,dy,dz,xy,e3 = pose_residual(state, target)
        print(
            f"T105 residual: dX={dx:+.3f} dY={dy:+.3f} dZ={dz:+.3f} mm | "
            f"XY={xy:.3f} | 3D={e3:.3f}"
        )
    print("=" * 82)


# =============================================================================
# SERIAL / ROBOT
# =============================================================================

def send_json(ser: serial.Serial, obj: Dict[str, Any], label="SEND"):
    text = json.dumps(obj, separators=(",", ":"))
    ser.reset_input_buffer()
    print(f"[{label}] {text}", flush=True)
    ser.write((text + "\n").encode("utf-8"))
    ser.flush()


def parse_t1051(line: str) -> Optional[Dict[str, Any]]:
    i, j = line.find("{"), line.rfind("}")
    if i < 0 or j <= i:
        return None

    try:
        d = json.loads(line[i:j+1])
    except Exception:
        return None

    if d.get("T") != 1051:
        return None

    required = ("x", "y", "z", "b", "s", "e", "t", "r", "g")
    if not all(isinstance(d.get(k), (int, float)) for k in required):
        return None

    return d


def fresh_t105(ser: serial.Serial, timeout_s=8.0):
    queued = ser.in_waiting
    ser.reset_input_buffer()
    print(f"[T105 PRE-FLUSH] {queued} byte(s)", flush=True)

    ser.write(b'{"T":105}\n')
    ser.flush()

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        raw = ser.readline()
        if not raw:
            continue

        d = parse_t1051(raw.decode("utf-8", errors="replace"))
        if d is not None:
            return d

    raise RuntimeError("No fresh T1051 received.")


def set_base_pid(ser: serial.Serial):
    send_json(
        ser,
        {"T":108, "joint":1, "p":BASE_PID_P, "i":BASE_PID_I},
        "T108 BASE PID",
    )
    time.sleep(1.0)


def move_t104(ser, x, y, z, tit, spd):
    send_json(
        ser,
        {
            "T":104,
            "x":float(x),
            "y":float(y),
            "z":float(z),
            "t":float(tit),
            "spd":float(spd),
        },
        "T104",
    )


# =============================================================================
# FROZEN VISION INPUT
# =============================================================================

def resolve_freeze_run(args) -> Path:
    if args.freeze_run:
        p = Path(args.freeze_run)
        if not p.exists():
            raise FileNotFoundError(p)
        return p

    root = Path(args.freeze_root)
    if not root.exists():
        raise FileNotFoundError(root)

    candidates = []
    for d in root.iterdir():
        if not d.is_dir():
            continue

        if (
            (d / "E4_heldout_model_results.csv").exists()
            and (d / "E4_formal_9targets.csv").exists()
        ):
            candidates.append(d)

    if not candidates:
        raise RuntimeError(
            f"No completed frozen E4 model run found under {root}."
        )

    candidates.sort(key=lambda p: p.name)
    return candidates[-1]


def load_frozen_predictions(freeze_run: Path, camera: str):
    results_path = freeze_run / "E4_heldout_model_results.csv"
    target_path = freeze_run / "E4_formal_9targets.csv"

    result_rows = read_csv(results_path)
    target_rows = read_csv(target_path)

    targets = {}
    for r in target_rows:
        tid = r["target_id"]
        targets[tid] = {
            "target_id": tid,
            "charuco_id": int(r["charuco_id"]),
            "gt_x": float(r["paper_x_mm"]),
            "gt_y": float(r["paper_y_mm"]),
        }

    if sorted(targets) != [f"T{i:02d}" for i in range(1,10)]:
        raise RuntimeError(
            f"Expected T01..T09 in {target_path}; found {sorted(targets)}"
        )

    predictions = {
        tid: {
            "Oracle": (t["gt_x"], t["gt_y"])
        }
        for tid, t in targets.items()
    }

    method_map = {
        "Affine": "Affine",
        "Homography": "Homography",
        "PnP_IPPE": "PnP_IPPE",
    }

    selected = [r for r in result_rows if r["camera"] == camera]

    for r in selected:
        tid = r["target_id"]
        method = r["method"]

        if method not in method_map:
            continue

        if tid not in targets:
            raise RuntimeError(f"Unexpected target {tid} in results.")

        # Cross-check GT is unchanged.
        gx = float(r["paper_x_gt_mm"])
        gy = float(r["paper_y_gt_mm"])
        if (
            abs(gx - targets[tid]["gt_x"]) > 1e-9
            or abs(gy - targets[tid]["gt_y"]) > 1e-9
        ):
            raise RuntimeError(
                f"{tid}: GT mismatch between targets/results."
            )

        predictions[tid][method] = (
            float(r["paper_x_pred_mm"]),
            float(r["paper_y_pred_mm"]),
        )

    for tid in sorted(targets):
        missing = set(METHODS) - set(predictions[tid])
        if missing:
            raise RuntimeError(
                f"{camera} {tid}: missing frozen predictions {sorted(missing)}."
            )

    return targets, predictions, results_path, target_path


# =============================================================================
# PLAN
# =============================================================================

PLAN_FIELDS = [
    "plan_index",
    "trial_uid",
    "repeat_id",
    "target_order_in_repeat",
    "target_id",
    "charuco_id",
    "method_order_in_block",
    "method",
    "camera",

    "paper_gt_x_mm",
    "paper_gt_y_mm",
    "paper_pred_x_mm",
    "paper_pred_y_mm",

    "vision_dx_mm",
    "vision_dy_mm",
    "vision_xy_error_mm",

    "robot_surface_x_mm",
    "robot_surface_y_mm",
    "robot_surface_z_mm",
    "robot_high_z_mm",
    "robot_contact_z_mm",
]


def build_plan(targets, predictions, camera):
    rng = random.Random(PLAN_SEED)
    target_ids = sorted(targets)

    rows = []
    plan_index = 0
    block_index = 0

    for repeat_id in range(1, 4):
        order = list(target_ids)
        rng.shuffle(order)

        for target_order_index, tid in enumerate(order, start=1):
            block_method_order = LATIN_METHOD_ORDERS[
                block_index % len(LATIN_METHOD_ORDERS)
            ]

            gt_x = targets[tid]["gt_x"]
            gt_y = targets[tid]["gt_y"]
            charuco_id = targets[tid]["charuco_id"]

            for method_order_index, method in enumerate(
                block_method_order,
                start=1,
            ):
                plan_index += 1

                pred_x, pred_y = predictions[tid][method]
                vdx = pred_x - gt_x
                vdy = pred_y - gt_y
                verr = math.hypot(vdx, vdy)

                rx, ry, rz = paper_to_robot(pred_x, pred_y)

                rows.append({
                    "plan_index": plan_index,
                    "trial_uid": (
                        f"R{repeat_id}-{tid}-{method}"
                    ),
                    "repeat_id": repeat_id,
                    "target_order_in_repeat": target_order_index,
                    "target_id": tid,
                    "charuco_id": charuco_id,
                    "method_order_in_block": method_order_index,
                    "method": method,
                    "camera": camera,

                    "paper_gt_x_mm": gt_x,
                    "paper_gt_y_mm": gt_y,
                    "paper_pred_x_mm": pred_x,
                    "paper_pred_y_mm": pred_y,

                    "vision_dx_mm": vdx,
                    "vision_dy_mm": vdy,
                    "vision_xy_error_mm": verr,

                    "robot_surface_x_mm": rx,
                    "robot_surface_y_mm": ry,
                    "robot_surface_z_mm": rz,
                    "robot_high_z_mm": rz + SAFE_HIGH_MM,
                    "robot_contact_z_mm": rz + CONTACT_OFFSET_MM,
                })

            block_index += 1

    if len(rows) != 108:
        raise RuntimeError(f"Internal plan error: expected 108, got {len(rows)}.")

    # Strong design checks.
    counts = {m: 0 for m in METHODS}
    for r in rows:
        counts[r["method"]] += 1

    if any(v != 27 for v in counts.values()):
        raise RuntimeError(f"Method counts not balanced: {counts}")

    return rows


# =============================================================================
# RUN FILES / RESUME
# =============================================================================

RESULT_FIELDS = PLAN_FIELDS + [
    "session_id",
    "executed_at",

    "high_t105_x_mm",
    "high_t105_y_mm",
    "high_t105_z_mm",
    "high_t105_dx_mm",
    "high_t105_dy_mm",
    "high_t105_dz_mm",
    "high_t105_xy_residual_mm",
    "high_t105_3d_residual_mm",

    "contact_t105_x_mm",
    "contact_t105_y_mm",
    "contact_t105_z_mm",
    "contact_t105_dx_mm",
    "contact_t105_dy_mm",
    "contact_t105_dz_mm",
    "contact_t105_xy_residual_mm",
    "contact_t105_3d_residual_mm",

    "physical_mark_x_mm",
    "physical_mark_y_mm",

    "e2e_dx_mm",
    "e2e_dy_mm",
    "e2e_xy_error_mm",

    "downstream_dx_mm",
    "downstream_dy_mm",
    "downstream_xy_error_mm",

    "measurement_status",
    "notes",
]


def load_or_create_run(args, freeze_run, targets, predictions):
    if args.resume:
        run_dir = Path(args.resume)
        if not run_dir.exists():
            raise FileNotFoundError(run_dir)

        plan_path = run_dir / "E4A_plan_108.csv"
        if not plan_path.exists():
            raise RuntimeError(f"Resume directory missing {plan_path.name}")

        plan = read_csv(plan_path)

        # Convert only values needed later; preserve row strings otherwise.
        if len(plan) != 108:
            raise RuntimeError(
                f"Resume plan should have 108 rows, got {len(plan)}."
            )

        metadata_path = run_dir / "E4A_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        if metadata["camera"] != args.camera:
            raise RuntimeError(
                f"Resume camera={metadata['camera']} but CLI camera={args.camera}"
            )

        return run_dir, plan, metadata

    run_id = now_id()
    run_dir = Path(args.out_root) / f"E4A_formal_{args.camera}" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    plan = build_plan(targets, predictions, args.camera)
    plan_path = run_dir / "E4A_plan_108.csv"
    write_csv(plan_path, plan, PLAN_FIELDS)

    metadata = {
        "run_id": run_id,
        "created_at": iso_now(),
        "status": "PLANNED_NOT_COMPLETE",

        "formal_experiment": "E4-A",
        "camera": args.camera,
        "n_targets": 9,
        "methods": METHODS,
        "robot_repeats": 3,
        "planned_physical_trials": 108,

        "freeze_run": str(freeze_run),
        "frozen_vision_results": str(
            freeze_run / "E4_heldout_model_results.csv"
        ),
        "frozen_targets": str(
            freeze_run / "E4_formal_9targets.csv"
        ),

        "design": {
            "target_order_seed": PLAN_SEED,
            "method_order": "rotating 4x4 Latin cycle",
            "fresh_vision_during_robot_trial": False,
            "reason": (
                "Use pre-frozen 9-point vision predictions. "
                "Three repeats therefore measure downstream robot propagation."
            ),
        },

        "paper_to_robot": {
            k: list(v) for k,v in PAPER_TO_ROBOT.items()
        },

        "robot_execution": {
            "base_pid_p": BASE_PID_P,
            "base_pid_i": BASE_PID_I,
            "controller": "T104 only",
            "extra_t101_correction": False,
            "target_tit_rad": TARGET_TIT_RAD,
            "travel_spd": T104_TRAVEL_SPD,
            "descent_spd": T104_DESCENT_SPD,
        },

        "contact_protocol": {
            "high_relative_to_pred_surface_mm": SAFE_HIGH_MM,
            "contact_relative_to_pred_surface_mm": CONTACT_OFFSET_MM,
        },

        "primary_outcome": (
            "physical paper endpoint XY error relative to known paper GT"
        ),
        "t105_role": "internal execution diagnostic only; not independent GT",

        "sessions": [],
    }

    (run_dir / "E4A_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return run_dir, plan, metadata


def existing_results(run_dir):
    p = run_dir / "E4A_results.csv"
    if not p.exists():
        return []
    return read_csv(p)


def save_results(run_dir, rows):
    write_csv(
        run_dir / "E4A_results.csv",
        rows,
        RESULT_FIELDS,
    )


def save_metadata(run_dir, metadata):
    (run_dir / "E4A_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# =============================================================================
# PHYSICAL MEASUREMENT INPUT
# =============================================================================

def get_mark_measurement(gt_x, gt_y, pred_x, pred_y):
    while True:
        print(
            "\nMeasure the physical endpoint mark in the SAME paper_frame:"
        )
        print(f"  GT       = ({gt_x:+.2f}, {gt_y:+.2f}) mm")
        print(f"  predicted= ({pred_x:+.2f}, {pred_y:+.2f}) mm")
        print("Enter actual mark as x,y  (example: -65.5,32.0)")
        print("Or type SKIP to flag this trial incomplete; Q to stop session.")

        s = input("mark> ").strip()

        if s.upper() == "Q":
            return {"action": "STOP"}

        if s.upper() == "SKIP":
            note = input("Reason for SKIP: ").strip()
            return {
                "action": "SAVE_SKIP",
                "measurement_status": "SKIPPED_INCOMPLETE",
                "notes": note,
            }

        try:
            parts = [x.strip() for x in s.split(",")]
            if len(parts) != 2:
                raise ValueError
            mx = float(parts[0])
            my = float(parts[1])
        except Exception:
            print("Invalid format. Use x,y, SKIP, or Q.")
            continue

        e2e_dx = mx - gt_x
        e2e_dy = my - gt_y
        e2e = math.hypot(e2e_dx, e2e_dy)

        down_dx = mx - pred_x
        down_dy = my - pred_y
        down = math.hypot(down_dx, down_dy)

        print(
            f"Physical E2E error = {e2e:.3f} mm "
            f"(dX={e2e_dx:+.3f}, dY={e2e_dy:+.3f})"
        )
        print(
            f"Downstream residual = {down:.3f} mm "
            f"(mark - model prediction)"
        )

        confirm = input("Type Y to save this measurement: ").strip().upper()
        if confirm != "Y":
            print("Not saved; re-enter measurement.")
            continue

        note = input("Optional note (Enter for none): ").strip()

        return {
            "action": "SAVE",
            "measurement_status": "MEASURED",
            "notes": note,

            "physical_mark_x_mm": mx,
            "physical_mark_y_mm": my,

            "e2e_dx_mm": e2e_dx,
            "e2e_dy_mm": e2e_dy,
            "e2e_xy_error_mm": e2e,

            "downstream_dx_mm": down_dx,
            "downstream_dy_mm": down_dy,
            "downstream_xy_error_mm": down,
        }


# =============================================================================
# SUMMARY
# =============================================================================

def update_summary(run_dir, plan, results, metadata):
    measured = [
        r for r in results
        if r.get("measurement_status") == "MEASURED"
    ]

    completed_uids = {r["trial_uid"] for r in results}
    measured_uids = {r["trial_uid"] for r in measured}

    summary = {
        "planned_trials": 108,
        "executed_rows_saved": len(results),
        "measured_trials": len(measured),
        "remaining_unexecuted": 108 - len(completed_uids),
        "remaining_without_physical_measurement":
            108 - len(measured_uids),
        "complete": len(measured_uids) == 108,
        "by_method": {},
    }

    for method in METHODS:
        rr = [r for r in measured if r["method"] == method]
        errs = [
            float(r["e2e_xy_error_mm"])
            for r in rr
            if r.get("e2e_xy_error_mm") not in ("", None)
        ]

        summary["by_method"][method] = (
            metric_summary(errs)
            if errs else {"n": 0}
        )

    (run_dir / "E4A_live_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    metadata["status"] = (
        "COMPLETE_108_MEASURED"
        if summary["complete"]
        else "IN_PROGRESS"
    )
    metadata["last_updated"] = iso_now()
    metadata["live_summary"] = summary
    save_metadata(run_dir, metadata)

    return summary


# =============================================================================
# EXECUTION
# =============================================================================

def normalize_plan_row(r):
    out = dict(r)

    int_fields = [
        "plan_index", "repeat_id", "target_order_in_repeat",
        "charuco_id", "method_order_in_block",
    ]
    float_fields = [
        "paper_gt_x_mm", "paper_gt_y_mm",
        "paper_pred_x_mm", "paper_pred_y_mm",
        "vision_dx_mm", "vision_dy_mm", "vision_xy_error_mm",
        "robot_surface_x_mm", "robot_surface_y_mm", "robot_surface_z_mm",
        "robot_high_z_mm", "robot_contact_z_mm",
    ]

    for k in int_fields:
        out[k] = int(out[k])

    for k in float_fields:
        out[k] = float(out[k])

    return out


def main():
    args = parse_args()

    freeze_run = resolve_freeze_run(args)
    targets, predictions, results_path, targets_path = load_frozen_predictions(
        freeze_run,
        args.camera,
    )

    run_dir, raw_plan, metadata = load_or_create_run(
        args,
        freeze_run,
        targets,
        predictions,
    )

    plan = [normalize_plan_row(r) for r in raw_plan]

    results = existing_results(run_dir)
    completed_uids = {r["trial_uid"] for r in results}

    remaining = [r for r in plan if r["trial_uid"] not in completed_uids]

    print("=" * 94)
    print("E4-A FORMAL END-TO-END ROBOT EXPERIMENT V1")
    print("=" * 94)
    print(f"Formal camera:    {args.camera}")
    print(f"Frozen vision:    {results_path}")
    print(f"Frozen targets:   {targets_path}")
    print(f"E4-A run dir:     {run_dir}")
    print()
    print("DESIGN:")
    print("  9 targets × 4 methods × 3 robot repeats = 108")
    print("  Vision predictions are PRE-FROZEN; no camera re-fit/re-detection here.")
    print("  Oracle bypasses vision.")
    print("  Base PID P16/I8; T104 only; no T101 correction.")
    print("  HIGH=surface+40 mm; CONTACT=surface+10 mm.")
    print()
    print(f"Already saved:    {len(completed_uids)}/108")
    print(f"Remaining:        {len(remaining)}/108")
    print("=" * 94)

    if not remaining:
        summary = update_summary(run_dir, plan, results, metadata)
        print("No unexecuted trials remain.")
        print(json.dumps(summary, indent=2))
        return

    # User-level integrity confirmation before opening serial.
    print("\nFORMAL INTEGRITY CHECK:")
    print("- ChArUco/paper has NOT physically moved.")
    print("- robot base has NOT moved.")
    print("- paper origin / axes are unchanged.")
    print("- pointer/marking setup is unchanged.")
    print("- /dev/ttyUSB0 is not used by another process.")
    confirm = input("\nType E4A to open serial and continue formal trials: ").strip()
    if confirm != "E4A":
        print("Cancelled before robot motion.")
        return

    ser = serial.Serial(
        port=args.port,
        baudrate=args.baud,
        timeout=0.20,
        write_timeout=0.5,
        rtscts=False,
        dsrdtr=False,
    )

    session_id = now_id()
    session_record = {
        "session_id": session_id,
        "started_at": iso_now(),
        "serial_port": args.port,
        "status": "RUNNING",
        "completed_trial_uids": [],
    }

    metadata.setdefault("sessions", []).append(session_record)
    save_metadata(run_dir, metadata)

    executed_this_session = 0
    stop_requested = False

    try:
        try:
            ser.setDTR(False)
            ser.setRTS(False)
        except Exception:
            pass

        print(f"\n[BOOT] Waiting {BOOT_WAIT_S:.0f}s with NO commands...")
        time.sleep(BOOT_WAIT_S)
        ser.reset_input_buffer()

        start = fresh_t105(ser)
        session_record["fixed_start_t105"] = start

        print_pose("[SESSION FIXED START]", start)

        set_base_pid(ser)

        for p in remaining:
            if args.max_trials > 0 and executed_this_session >= args.max_trials:
                print(
                    f"\n[MAX-TRIALS] Reached {args.max_trials} in this session."
                )
                break

            plan_idx = p["plan_index"]
            tid = p["target_id"]
            method = p["method"]
            repeat_id = p["repeat_id"]
            uid = p["trial_uid"]

            gt_x = p["paper_gt_x_mm"]
            gt_y = p["paper_gt_y_mm"]

            pred_x = p["paper_pred_x_mm"]
            pred_y = p["paper_pred_y_mm"]

            rx = p["robot_surface_x_mm"]
            ry = p["robot_surface_y_mm"]
            rz = p["robot_surface_z_mm"]

            high_z = p["robot_high_z_mm"]
            contact_z = p["robot_contact_z_mm"]

            print("\n" + "#" * 94)
            print(
                f"FORMAL TRIAL {plan_idx:03d}/108 | {uid}"
            )
            print("#" * 94)
            print(
                f"Repeat={repeat_id} | target={tid} "
                f"(ChArUco id={p['charuco_id']}) | method={method}"
            )
            print(
                f"GT paper       = ({gt_x:+.3f}, {gt_y:+.3f}) mm"
            )
            print(
                f"Predicted paper= ({pred_x:+.3f}, {pred_y:+.3f}) mm"
            )
            print(
                f"Frozen vision error = {p['vision_xy_error_mm']:.3f} mm"
            )
            print(
                f"Robot surface command = ({rx:.3f},{ry:.3f},{rz:.3f}) mm"
            )
            print(
                f"HIGH Z={high_z:.3f} | CONTACT Z={contact_z:.3f}"
            )
            print()
            print(
                "After contact the robot will rise and return to fixed start, "
                "then you will measure the physical mark."
            )

            go = input(
                "Type GO to execute this formal trial, "
                "Q to stop session: "
            ).strip().upper()

            if go == "Q":
                stop_requested = True
                break

            if go != "GO":
                print("Confirmation mismatch; stopping session.")
                stop_requested = True
                break

            # Reapply base PID each trial to keep condition explicit/frozen.
            set_base_pid(ser)

            # --------------------------------------------------------------
            # A. Fixed start
            # --------------------------------------------------------------
            print("[1] Return to fixed start")
            move_t104(
                ser,
                start["x"], start["y"], start["z"], start["t"],
                T104_TRAVEL_SPD,
            )
            time.sleep(START_WAIT_S)
            start_state = fresh_t105(ser)

            # --------------------------------------------------------------
            # B. HIGH
            # --------------------------------------------------------------
            print("[2] Move to HIGH")
            move_t104(
                ser,
                rx, ry, high_z,
                TARGET_TIT_RAD,
                T104_TRAVEL_SPD,
            )
            time.sleep(HIGH_WAIT_S)

            high_state = fresh_t105(ser)
            hdx,hdy,hdz,hxy,h3 = pose_residual(
                high_state,
                (rx, ry, high_z),
            )

            print_pose(
                "[HIGH]",
                high_state,
                (rx, ry, high_z),
            )

            if h3 > HIGH_3D_RESIDUAL_GATE_MM:
                print(
                    f"\n[SAFETY BLOCK] HIGH T105 3D residual={h3:.3f} mm "
                    f"> {HIGH_3D_RESIDUAL_GATE_MM:.1f} mm."
                )
                print("CONTACT WILL NOT BE COMMANDED.")

                # Rise/return best-effort using the same high and start.
                try:
                    move_t104(
                        ser,
                        start["x"], start["y"], start["z"], start["t"],
                        T104_TRAVEL_SPD,
                    )
                    time.sleep(START_WAIT_S)
                except Exception:
                    pass

                stop_requested = True
                break

            # --------------------------------------------------------------
            # C. CONTACT — vertical only
            # --------------------------------------------------------------
            print("[3] Vertical descent to frozen CONTACT offset")
            move_t104(
                ser,
                rx, ry, contact_z,
                TARGET_TIT_RAD,
                T104_DESCENT_SPD,
            )
            time.sleep(CONTACT_WAIT_S)

            contact_state = fresh_t105(ser)
            cdx,cdy,cdz,cxy,c3 = pose_residual(
                contact_state,
                (rx, ry, contact_z),
            )

            print_pose(
                "[CONTACT]",
                contact_state,
                (rx, ry, contact_z),
            )

            # --------------------------------------------------------------
            # D. Rise
            # --------------------------------------------------------------
            print("[4] Vertical rise to HIGH")
            move_t104(
                ser,
                rx, ry, high_z,
                TARGET_TIT_RAD,
                T104_DESCENT_SPD,
            )
            time.sleep(RISE_WAIT_S)
            rise_state = fresh_t105(ser)

            # --------------------------------------------------------------
            # E. Return start so mark is accessible
            # --------------------------------------------------------------
            print("[5] Return to fixed start")
            set_base_pid(ser)
            move_t104(
                ser,
                start["x"], start["y"], start["z"], start["t"],
                T104_TRAVEL_SPD,
            )
            time.sleep(START_WAIT_S)
            final_start_state = fresh_t105(ser)

            # --------------------------------------------------------------
            # F. Physical independent endpoint measurement
            # --------------------------------------------------------------
            measurement = get_mark_measurement(
                gt_x, gt_y, pred_x, pred_y
            )

            if measurement["action"] == "STOP":
                print(
                    "Trial was physically executed but no measurement was saved. "
                    "This trial UID remains uncompleted and MUST be handled "
                    "carefully before rerunning because an old mark now exists."
                )
                stop_requested = True
                break

            result = dict(p)
            result.update({
                "session_id": session_id,
                "executed_at": iso_now(),

                "high_t105_x_mm": high_state["x"],
                "high_t105_y_mm": high_state["y"],
                "high_t105_z_mm": high_state["z"],
                "high_t105_dx_mm": hdx,
                "high_t105_dy_mm": hdy,
                "high_t105_dz_mm": hdz,
                "high_t105_xy_residual_mm": hxy,
                "high_t105_3d_residual_mm": h3,

                "contact_t105_x_mm": contact_state["x"],
                "contact_t105_y_mm": contact_state["y"],
                "contact_t105_z_mm": contact_state["z"],
                "contact_t105_dx_mm": cdx,
                "contact_t105_dy_mm": cdy,
                "contact_t105_dz_mm": cdz,
                "contact_t105_xy_residual_mm": cxy,
                "contact_t105_3d_residual_mm": c3,

                "measurement_status":
                    measurement.get("measurement_status", ""),
                "notes": measurement.get("notes", ""),
            })

            for k in [
                "physical_mark_x_mm",
                "physical_mark_y_mm",
                "e2e_dx_mm",
                "e2e_dy_mm",
                "e2e_xy_error_mm",
                "downstream_dx_mm",
                "downstream_dy_mm",
                "downstream_xy_error_mm",
            ]:
                result[k] = measurement.get(k, "")

            results.append(result)
            completed_uids.add(uid)
            save_results(run_dir, results)

            session_record["completed_trial_uids"].append(uid)
            executed_this_session += 1

            summary = update_summary(
                run_dir, plan, results, metadata
            )

            print(
                f"\n[SAVED] {uid} | "
                f"{len(completed_uids)}/108 executed rows saved | "
                f"{summary['measured_trials']}/108 physical measurements"
            )

            if measurement["action"] == "SAVE_SKIP":
                print(
                    "[WARNING] This formal trial is incomplete because the "
                    "physical endpoint measurement was skipped."
                )

        # End for

        # Best-effort final return.
        try:
            print("\n[SESSION END] Return to fixed start")
            set_base_pid(ser)
            move_t104(
                ser,
                start["x"], start["y"], start["z"], start["t"],
                T104_TRAVEL_SPD,
            )
            time.sleep(START_WAIT_S)
            end_state = fresh_t105(ser)
            session_record["final_start_t105"] = end_state
        except Exception as e:
            session_record["final_return_error"] = str(e)

        session_record["ended_at"] = iso_now()
        session_record["status"] = (
            "STOPPED_BY_USER"
            if stop_requested
            else "SESSION_COMPLETE"
        )

        summary = update_summary(
            run_dir, plan, results, metadata
        )

        print("\n" + "=" * 94)
        print("E4-A SESSION SUMMARY")
        print("=" * 94)
        print(
            f"Saved rows: {summary['executed_rows_saved']}/108 | "
            f"Measured: {summary['measured_trials']}/108"
        )

        if summary["by_method"]:
            print("\nCurrent physical E2E summary (do NOT interpret final until complete):")
            for method in METHODS:
                s = summary["by_method"][method]
                if s.get("n", 0) > 0:
                    print(
                        f"  {method:<11} "
                        f"n={s['n']:2d} "
                        f"mean={s['mean_mm']:.3f} mm | "
                        f"RMSE={s['rmse_mm']:.3f} | "
                        f"max={s['max_mm']:.3f}"
                    )
                else:
                    print(f"  {method:<11} n=0")

        print(f"\nRun dir: {run_dir}")
        print(f"Plan:    {run_dir / 'E4A_plan_108.csv'}")
        print(f"Results: {run_dir / 'E4A_results.csv'}")
        print(f"Summary: {run_dir / 'E4A_live_summary.json'}")

        if summary["complete"]:
            print("\nFORMAL E4-A COMPLETE: 108/108 measured.")
        else:
            print(
                "\nE4-A remains IN PROGRESS. Resume with:\n"
                f"python3 {Path(__file__).resolve()} "
                f"--port {args.port} --camera {args.camera} "
                f"--resume '{run_dir}'"
            )
        print("=" * 94)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        session_record["ended_at"] = iso_now()
        session_record["status"] = "KEYBOARD_INTERRUPT"
        update_summary(run_dir, plan, results, metadata)

    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] serial closed.")


if __name__ == "__main__":
    main()
