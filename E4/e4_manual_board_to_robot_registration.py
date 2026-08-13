#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 manual board -> robot registration
Planar board: user manually aligns the pointer/TCP to a known board point,
then enters board X/Y in mm. Board Z is recorded as 0 by default.

No automatic robot motion is sent. Only:
  T210 cmd=0 : torque OFF
  T210 cmd=1 : torque ON
  T105       : read current pose

Recommended:
  9 well-spread calibration points, then 3 held-out validation points later.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import serial


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument(
        "--base-dir",
        type=Path,
        default=Path("/mnt/c/Users/ASUS/Desktop/paper/E4/E4_board_to_robot_registration"),
    )
    p.add_argument("--target-count", type=int, default=9)
    return p.parse_args()


def send_json(ser: serial.Serial, obj: Dict[str, Any]) -> None:
    text = json.dumps(obj, separators=(",", ":"))
    print(f"[SEND] {text}")
    ser.write((text + "\n").encode("utf-8"))
    ser.flush()


def parse_t1051(line: str) -> Optional[Dict[str, Any]]:
    s = line.strip()
    i = s.find("{")
    j = s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        obj = json.loads(s[i:j+1])
    except json.JSONDecodeError:
        return None
    return obj if obj.get("T") == 1051 else None


def open_serial(port: str, baud: int) -> serial.Serial:
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = 0.15
    ser.write_timeout = 0.5
    ser.rtscts = False
    ser.dsrdtr = False
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    ser.open()
    try:
        ser.setDTR(False)
        ser.setRTS(False)
    except Exception:
        pass
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser


def collect_pose_window(
    ser: serial.Serial,
    duration_s: float = 1.8,
    request_interval_s: float = 0.35,
) -> Tuple[Optional[Dict[str, float]], int]:
    poses: List[Dict[str, Any]] = []
    end = time.time() + duration_s
    next_req = 0.0

    while time.time() < end:
        now = time.time()
        if now >= next_req:
            send_json(ser, {"T": 105})
            next_req = now + request_interval_s

        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        obj = parse_t1051(line)
        if obj is not None:
            poses.append(obj)

    if not poses:
        return None, 0

    out: Dict[str, float] = {}
    for key in ("x", "y", "z", "tit", "b", "s", "e", "t", "r", "g"):
        vals = [
            float(p[key]) for p in poses
            if isinstance(p.get(key), (int, float))
            and math.isfinite(float(p[key]))
        ]
        if vals:
            out[key] = float(statistics.median(vals))

    return out, len(poses)


def wait_for_robot(ser: serial.Serial, timeout_s: float = 35.0) -> Dict[str, float]:
    print("[INITIALIZING] Waiting for a valid T1051 pose.")
    print("[NOTE] Opening this serial connection may reboot the controller; wait up to 35 s.")
    end = time.time() + timeout_s
    next_req = 0.0
    last_report = 0.0

    while time.time() < end:
        now = time.time()
        if now >= next_req:
            send_json(ser, {"T": 105})
            next_req = now + 0.7

        raw = ser.readline()
        if raw:
            obj = parse_t1051(raw.decode("utf-8", errors="replace"))
            if obj is not None:
                pose = {
                    k: float(obj[k]) for k in ("x", "y", "z", "tit", "b", "s", "e", "t", "r", "g")
                    if isinstance(obj.get(k), (int, float))
                }
                print_pose(pose, "[READY POSE]")
                return pose

        if now - last_report >= 5.0:
            remaining = max(0.0, end - now)
            print(f"[WAITING] {remaining:.0f} s remaining...")
            last_report = now

    raise SystemExit("[ERROR] No valid T1051 received within 35 s.")


def print_pose(pose: Optional[Dict[str, float]], prefix="[POSE]") -> None:
    if not pose:
        print(prefix, "<no pose>")
        return
    parts = []
    for k in ("x", "y", "z", "tit", "b", "s", "e", "t", "r", "g"):
        if k in pose:
            parts.append(f"{k}={pose[k]:.4f}")
    print(prefix, " ".join(parts))


RAW_FIELDS = [
    "timestamp", "sample_id",
    "board_x_mm", "board_y_mm", "board_z_mm",
    "robot_x_mm", "robot_y_mm", "robot_z_mm",
    "robot_tit", "robot_b", "robot_s", "robot_e", "robot_t", "robot_r", "robot_g",
    "pose_sample_count",
]


def save_raw_csv(path: Path, records: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=RAW_FIELDS)
        w.writeheader()
        for row in records:
            w.writerow({k: row.get(k, "") for k in RAW_FIELDS})


def stats(vals: np.ndarray) -> Dict[str, float]:
    return {
        "mean": float(np.mean(vals)),
        "rmse": float(np.sqrt(np.mean(vals ** 2))),
        "median": float(np.median(vals)),
        "max": float(np.max(vals)),
    }


def fit_model(records: List[Dict[str, Any]], run_dir: Path, latest_path: Path) -> None:
    if len(records) < 6:
        print("[REFUSED] Need at least 6 points. 9 spread points are recommended.")
        return

    bx = np.array([r["board_x_mm"] for r in records], dtype=float)
    by = np.array([r["board_y_mm"] for r in records], dtype=float)
    rx = np.array([r["robot_x_mm"] for r in records], dtype=float)
    ry = np.array([r["robot_y_mm"] for r in records], dtype=float)
    rz = np.array([r["robot_z_mm"] for r in records], dtype=float)

    A = np.column_stack([bx, by, np.ones_like(bx)])
    rank = int(np.linalg.matrix_rank(A))
    cond = float(np.linalg.cond(A))

    if rank < 3:
        print("[REFUSED] Point geometry is rank-deficient. Spread points over 2D area.")
        return

    cx, *_ = np.linalg.lstsq(A, rx, rcond=None)
    cy, *_ = np.linalg.lstsq(A, ry, rcond=None)
    cz, *_ = np.linalg.lstsq(A, rz, rcond=None)

    px = A @ cx
    py = A @ cy
    pz = A @ cz

    ex = rx - px
    ey = ry - py
    ez = rz - pz
    e_xy = np.sqrt(ex**2 + ey**2)
    e_3d = np.sqrt(ex**2 + ey**2 + ez**2)

    model = {
        "schema": "board_to_robot_planar_affine",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sample_count": len(records),
        "board_z_assumption_mm": 0.0,
        "input": ["board_x_mm", "board_y_mm", "1"],
        "output": ["robot_x_mm", "robot_y_mm", "robot_z_mm"],
        "robot_x_coefficients": cx.tolist(),
        "robot_y_coefficients": cy.tolist(),
        "robot_z_coefficients": cz.tolist(),
        "equations": {
            "robot_x": f"{cx[0]:.9f}*board_x + {cx[1]:.9f}*board_y + {cx[2]:.9f}",
            "robot_y": f"{cy[0]:.9f}*board_x + {cy[1]:.9f}*board_y + {cy[2]:.9f}",
            "robot_z": f"{cz[0]:.9f}*board_x + {cz[1]:.9f}*board_y + {cz[2]:.9f}",
        },
        "geometry": {
            "board_x_min_mm": float(bx.min()),
            "board_x_max_mm": float(bx.max()),
            "board_y_min_mm": float(by.min()),
            "board_y_max_mm": float(by.max()),
            "design_rank": rank,
            "design_condition_number": cond,
        },
        "training_fit_only_not_independent_accuracy": {
            "xy_residual_mm": stats(e_xy),
            "three_dimensional_residual_mm": stats(e_3d),
        },
        "points": records,
        "warning": "Training residual is not independent endpoint accuracy. Validate on >=3 held-out board points before E4 use.",
    }

    model_path = run_dir / "board_to_robot_planar_affine_model.json"
    residual_path = run_dir / "fit_residuals.csv"

    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")

    with residual_path.open("w", newline="", encoding="utf-8-sig") as f:
        fields = [
            "sample_id", "board_x_mm", "board_y_mm",
            "measured_robot_x", "measured_robot_y", "measured_robot_z",
            "pred_robot_x", "pred_robot_y", "pred_robot_z",
            "xy_residual_mm", "residual_3d_mm",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, r in enumerate(records):
            w.writerow({
                "sample_id": r["sample_id"],
                "board_x_mm": r["board_x_mm"],
                "board_y_mm": r["board_y_mm"],
                "measured_robot_x": rx[i],
                "measured_robot_y": ry[i],
                "measured_robot_z": rz[i],
                "pred_robot_x": px[i],
                "pred_robot_y": py[i],
                "pred_robot_z": pz[i],
                "xy_residual_mm": e_xy[i],
                "residual_3d_mm": e_3d[i],
            })

    print("\n" + "=" * 78)
    print("[FIT COMPLETE]")
    print(model["equations"]["robot_x"])
    print(model["equations"]["robot_y"])
    print(model["equations"]["robot_z"])
    print(f"XY training RMSE = {model['training_fit_only_not_independent_accuracy']['xy_residual_mm']['rmse']:.3f} mm")
    print(f"XY training MAX  = {model['training_fit_only_not_independent_accuracy']['xy_residual_mm']['max']:.3f} mm")
    print(f"3D training RMSE = {model['training_fit_only_not_independent_accuracy']['three_dimensional_residual_mm']['rmse']:.3f} mm")
    print(f"X range = {bx.min():.1f} .. {bx.max():.1f} mm")
    print(f"Y range = {by.min():.1f} .. {by.max():.1f} mm")
    print(f"Design rank = {rank}, condition number = {cond:.2f}")
    print(f"Model: {model_path}")
    print(f"Latest: {latest_path}")
    print("[IMPORTANT] These are training residuals, not independent accuracy.")
    print("Validate >=3 held-out points before freezing this transform for E4.")
    print("=" * 78)


def main():
    args = parse_args()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_csv = run_dir / "registration_raw.csv"
    latest_model = args.base_dir / "board_to_robot_planar_affine_latest.json"

    records: List[Dict[str, Any]] = []
    torque_locked = False

    print("=" * 78)
    print("E4 MANUAL BOARD -> ROBOT REGISTRATION")
    print("=" * 78)
    print(f"Run: {run_id}")
    print(f"Port: {args.port} @ {args.baud}")
    print(f"Recommended calibration count: {args.target_count}")
    print("Board coordinates: enter physical X/Y in mm; board Z defaults to 0.")
    print("This program NEVER sends T104/T123 automatic movement commands.")
    print()
    print("Commands:")
    print("  o : torque OFF; support arm, then manually move pointer")
    print("  i : torque ON; wait for settle")
    print("  p : print fresh robot pose")
    print("  r : record one calibration point; enter board X/Y/Z")
    print("  u : undo last recorded point")
    print("  l : list recorded points")
    print("  f : fit/save affine model")
    print("  q : quit")
    print("=" * 78)

    ser = open_serial(args.port, args.baud)

    try:
        wait_for_robot(ser, 35.0)

        while True:
            cmd = input("\nCommand [o/i/p/r/u/l/f/q]: ").strip().lower()[:1]

            if cmd == "o":
                print("[TORQUE OFF] Support the arm before release.")
                confirm = input("Type O to confirm torque OFF: ").strip().lower()
                if confirm != "o":
                    print("[CANCELLED]")
                    continue
                send_json(ser, {"T": 210, "cmd": 0})
                torque_locked = False
                time.sleep(0.5)
                print("[UNLOCKED] Move the pointer manually to the desired board point.")
                continue

            if cmd == "i":
                send_json(ser, {"T": 210, "cmd": 1})
                torque_locked = True
                print("[LOCKED] Waiting 1.5 s for settling...")
                time.sleep(1.5)
                pose, n = collect_pose_window(ser, 1.5)
                print_pose(pose, f"[LOCKED POSE, n={n}]")
                continue

            if cmd == "p":
                pose, n = collect_pose_window(ser, 1.5)
                print_pose(pose, f"[FRESH POSE, n={n}]")
                continue

            if cmd == "r":
                if not torque_locked:
                    print("[REFUSED] Press i to lock/settle the arm before recording.")
                    continue

                try:
                    bx = float(input("Board X [mm]: ").strip())
                    by = float(input("Board Y [mm]: ").strip())
                    ztext = input("Board Z [mm, Enter=0]: ").strip()
                    bz = 0.0 if ztext == "" else float(ztext)
                except ValueError:
                    print("[CANCELLED] Invalid number.")
                    continue

                pose, n = collect_pose_window(ser, 1.8)
                if not pose or not all(k in pose for k in ("x", "y", "z")):
                    print("[REFUSED] No valid fresh robot XYZ.")
                    continue

                sample_id = len(records) + 1
                print(f"[PROPOSED] P{sample_id}: board=({bx:.1f},{by:.1f},{bz:.1f}) mm")
                print_pose(pose, "[ROBOT]")
                ok = input("Press Enter to SAVE, or type x to cancel: ").strip().lower()
                if ok == "x":
                    print("[CANCELLED]")
                    continue

                row = {
                    "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                    "sample_id": sample_id,
                    "board_x_mm": bx,
                    "board_y_mm": by,
                    "board_z_mm": bz,
                    "robot_x_mm": pose["x"],
                    "robot_y_mm": pose["y"],
                    "robot_z_mm": pose["z"],
                    "robot_tit": pose.get("tit", ""),
                    "robot_b": pose.get("b", ""),
                    "robot_s": pose.get("s", ""),
                    "robot_e": pose.get("e", ""),
                    "robot_t": pose.get("t", ""),
                    "robot_r": pose.get("r", ""),
                    "robot_g": pose.get("g", ""),
                    "pose_sample_count": n,
                }
                records.append(row)
                save_raw_csv(raw_csv, records)
                print(f"[SAVED] {len(records)} point(s). Raw CSV: {raw_csv}")
                if len(records) >= args.target_count:
                    print("[READY TO FIT] Recommended point count reached. You may press f.")
                continue

            if cmd == "u":
                if records:
                    removed = records.pop()
                    save_raw_csv(raw_csv, records)
                    print(f"[UNDO] Removed P{removed['sample_id']} board=({removed['board_x_mm']},{removed['board_y_mm']})")
                else:
                    print("[UNDO] No records.")
                continue

            if cmd == "l":
                if not records:
                    print("[LIST] No points recorded.")
                else:
                    for r in records:
                        print(
                            f"P{r['sample_id']:02d} board=({r['board_x_mm']:.1f},{r['board_y_mm']:.1f},0) "
                            f"-> robot=({r['robot_x_mm']:.2f},{r['robot_y_mm']:.2f},{r['robot_z_mm']:.2f})"
                        )
                continue

            if cmd == "f":
                fit_model(records, run_dir, latest_model)
                continue

            if cmd == "q":
                if not torque_locked:
                    print("[REFUSED] Torque is OFF. Support arm and press i before quitting.")
                    continue
                print("[QUIT]")
                break

            print("[INVALID] Use o/i/p/r/u/l/f/q.")

    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        if not torque_locked:
            print("[SAFETY] Torque appears OFF. Keep supporting the arm; lock it before letting go.")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        print(f"[CLOSED] Serial closed. Run folder: {run_dir}")


if __name__ == "__main__":
    main()
