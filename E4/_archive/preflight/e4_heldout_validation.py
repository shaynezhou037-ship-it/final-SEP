#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 held-out validation for the current board -> robot planar affine model.

Purpose:
- Use 3 board points NOT used in calibration.
- Move to a safe hover first, then to a low XY-check height.
- User measures the actual pointer-tip board X/Y and enters them.
- Compute independent end-to-end XY validation error.

Important:
- This validates the full downstream registration/execution chain, not only affine fit.
- Serial is opened only once to avoid repeated controller reboots.
- No point is commanded at the fitted surface itself; LOW_CLEARANCE_MM defaults to +5 mm.
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
from typing import Any, Dict, Optional, Tuple, List

import serial


DEFAULT_MODEL = Path(
    "/mnt/c/Users/ASUS/Desktop/paper/E4/"
    "E4_board_to_robot_registration/20260810_144418/"
    "board_to_robot_planar_affine_model_REBUILT.json"
)

# Held-out points: all are inside the calibration convex hull and were not in the 20-point fit.
TEST_POINTS = [
    ("H1", -80.0, -60.0),
    ("H2", -60.0,  50.0),
    ("H3",  40.0, -20.0),
]

HIGH_CLEARANCE_MM = 40.0
LOW_CLEARANCE_MM = 5.0
TILT_RAD = 1.50
MOVE_SPEED = 0.05
ARRIVE_TOL_MM = 15.0
MOTION_TIMEOUT_S = 45.0


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    p.add_argument("--high", type=float, default=HIGH_CLEARANCE_MM)
    p.add_argument("--low", type=float, default=LOW_CLEARANCE_MM)
    p.add_argument("--tilt", type=float, default=TILT_RAD)
    p.add_argument("--spd", type=float, default=MOVE_SPEED)
    return p.parse_args()


def send_json(ser: serial.Serial, obj: Dict[str, Any]) -> None:
    text = json.dumps(obj, separators=(",", ":"))
    print(f"[SEND] {text}")
    ser.write((text + "\n").encode("utf-8"))
    ser.flush()


def parse_t1051(text: str) -> Optional[Dict[str, Any]]:
    i = text.find("{")
    j = text.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        obj = json.loads(text[i:j+1])
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


def pose_text(pose: Optional[Dict[str, Any]]) -> str:
    if not pose:
        return "<no pose>"
    parts = []
    for k in ("x", "y", "z", "tit", "b", "s", "e", "t", "r", "g"):
        v = pose.get(k)
        if isinstance(v, (int, float)):
            parts.append(f"{k}={float(v):.3f}")
    return " ".join(parts)


def wait_for_pose(ser: serial.Serial, timeout_s: float = 35.0) -> Dict[str, Any]:
    print("[INITIALIZING] Waiting for valid T1051; controller may reboot when serial opens.")
    end = time.time() + timeout_s
    next_req = 0.0
    last_status = 0.0
    while time.time() < end:
        now = time.time()
        if now >= next_req:
            send_json(ser, {"T": 105})
            next_req = now + 0.7

        raw = ser.readline()
        if raw:
            pose = parse_t1051(raw.decode("utf-8", errors="replace").strip())
            if pose is not None:
                print("[READY POSE]", pose_text(pose))
                return pose

        if now - last_status >= 5.0:
            print(f"[WAITING] {max(0, end-now):.0f} s remaining...")
            last_status = now

    raise SystemExit("[ERROR] No valid T1051 within 35 s.")


def fresh_pose(ser: serial.Serial, timeout_s: float = 3.0) -> Optional[Dict[str, Any]]:
    end = time.time() + timeout_s
    next_req = 0.0
    latest = None
    while time.time() < end:
        now = time.time()
        if now >= next_req:
            send_json(ser, {"T": 105})
            next_req = now + 0.5
        raw = ser.readline()
        if not raw:
            continue
        pose = parse_t1051(raw.decode("utf-8", errors="replace").strip())
        if pose is not None:
            latest = pose
    return latest


def load_model(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "board_to_robot_planar_affine":
        raise SystemExit(f"[ERROR] Unexpected model schema: {data.get('schema')}")
    return data


def affine(coeff, x, y):
    return float(coeff[0])*x + float(coeff[1])*y + float(coeff[2])


def predict(model, bx, by):
    rx = affine(model["robot_x_coefficients"], bx, by)
    ry = affine(model["robot_y_coefficients"], bx, by)
    rz = affine(model["robot_z_coefficients"], bx, by)
    return rx, ry, rz


def command_pose(ser, x, y, z, tilt, spd):
    cmd = {
        "T": 104,
        "x": round(x, 6),
        "y": round(y, 6),
        "z": round(z, 6),
        "t": round(tilt, 6),
        "spd": round(spd, 6),
    }
    send_json(ser, cmd)


def monitor_motion(
    ser: serial.Serial,
    target: Tuple[float, float, float],
    timeout_s: float = MOTION_TIMEOUT_S,
) -> Optional[Dict[str, Any]]:
    tx, ty, tz = target
    end = time.time() + timeout_s
    next_req = time.time() + 1.0
    latest = None
    stable = 0

    while time.time() < end:
        now = time.time()
        if now >= next_req:
            send_json(ser, {"T": 105})
            next_req = now + 1.0

        raw = ser.readline()
        if not raw:
            continue
        pose = parse_t1051(raw.decode("utf-8", errors="replace").strip())
        if pose is None:
            continue
        latest = pose

        if all(isinstance(pose.get(k), (int, float)) for k in ("x", "y", "z")):
            err = math.sqrt(
                (float(pose["x"])-tx)**2
                + (float(pose["y"])-ty)**2
                + (float(pose["z"])-tz)**2
            )
            print(f"[FEEDBACK] {pose_text(pose)} | firmware target error={err:.2f} mm")
            if err <= ARRIVE_TOL_MM:
                stable += 1
            else:
                stable = 0
            if stable >= 3:
                return latest

    print("[WARNING] Arrival not confirmed inside tolerance before timeout.")
    return latest


def main():
    args = parse_args()
    model = load_model(args.model)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.model.parent / f"heldout_validation_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "heldout_validation.csv"

    print("=" * 82)
    print("E4 HELD-OUT BOARD -> ROBOT VALIDATION")
    print("=" * 82)
    print(f"Model: {args.model}")
    print(f"High clearance: +{args.high:.1f} mm")
    print(f"Low clearance:  +{args.low:.1f} mm")
    print(f"Tilt: {args.tilt:.3f} rad")
    print(f"Speed: {args.spd:.3f}")
    print()
    for pid, bx, by in TEST_POINTS:
        rx, ry, rz = predict(model, bx, by)
        print(
            f"{pid}: board=({bx:.1f},{by:.1f}) -> "
            f"robot surface=({rx:.2f},{ry:.2f},{rz:.2f})"
        )
    print("=" * 82)

    print("\n[PHYSICAL SAFETY]")
    print("- Start with the arm raised/open and the path clear.")
    print("- Keep one hand ready at the power switch.")
    print("- The program first moves to +high clearance, then only after confirmation to +low clearance.")
    print("- It never commands fitted surface Z=0 directly.")
    input("Press Enter when ready to open serial...")

    ser = open_serial(args.port, args.baud)
    results: List[Dict[str, Any]] = []

    try:
        start_pose = wait_for_pose(ser)
        current_z = start_pose.get("z")
        if not isinstance(current_z, (int, float)) or float(current_z) < 20.0:
            raise SystemExit(
                f"[REFUSED] Start z={current_z}. Manually return to a raised/open pose first."
            )

        for idx, (pid, bx, by) in enumerate(TEST_POINTS, start=1):
            rx, ry, surface_z = predict(model, bx, by)
            high_z = surface_z + args.high
            low_z = surface_z + args.low

            print("\n" + "=" * 82)
            print(f"[{pid}] Held-out point {idx}/{len(TEST_POINTS)}")
            print(f"Nominal board XY = ({bx:.1f}, {by:.1f}) mm")
            print(f"Pred robot surface XYZ = ({rx:.3f}, {ry:.3f}, {surface_z:.3f}) mm")
            print(f"High target Z = {high_z:.3f} mm")
            print(f"Low target Z  = {low_z:.3f} mm")
            print("=" * 82)

            confirm = input(f"Type {pid} to move to HIGH position: ").strip().upper()
            if confirm != pid:
                print("[CANCELLED]")
                break

            command_pose(ser, rx, ry, high_z, args.tilt, args.spd)
            high_pose = monitor_motion(ser, (rx, ry, high_z))
            print("[HIGH FINAL]", pose_text(high_pose))

            confirm = input(
                f"Visually check path/board. Type LOW to descend to +{args.low:.1f} mm: "
            ).strip().upper()
            if confirm != "LOW":
                print("[SKIPPED LOW] Retaining high position.")
                break

            command_pose(ser, rx, ry, low_z, args.tilt, args.spd)
            low_pose = monitor_motion(ser, (rx, ry, low_z))
            print("[LOW FINAL]", pose_text(low_pose))

            print("\n[MEASURE]")
            print(
                "Read the actual pointer-tip position in BOARD coordinates. "
                "Do not use robot feedback as ground truth."
            )
            try:
                ax = float(input("Actual board X [mm]: ").strip())
                ay = float(input("Actual board Y [mm]: ").strip())
            except ValueError:
                print("[ERROR] Invalid measurement; stopping before next point.")
                break

            ex = ax - bx
            ey = ay - by
            e_xy = math.hypot(ex, ey)

            row = {
                "point_id": pid,
                "nominal_board_x_mm": bx,
                "nominal_board_y_mm": by,
                "actual_board_x_mm": ax,
                "actual_board_y_mm": ay,
                "error_x_mm": ex,
                "error_y_mm": ey,
                "error_xy_mm": e_xy,
                "pred_robot_x_mm": rx,
                "pred_robot_y_mm": ry,
                "pred_surface_z_mm": surface_z,
                "command_low_z_mm": low_z,
                "feedback_x_mm": low_pose.get("x") if low_pose else "",
                "feedback_y_mm": low_pose.get("y") if low_pose else "",
                "feedback_z_mm": low_pose.get("z") if low_pose else "",
            }
            results.append(row)

            with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
                fields = list(row.keys())
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(results)

            print(
                f"[VALIDATION ERROR] dx={ex:+.2f} mm, dy={ey:+.2f} mm, "
                f"XY={e_xy:.2f} mm"
            )

            print("[RETREAT] Returning vertically to high clearance.")
            command_pose(ser, rx, ry, high_z, args.tilt, args.spd)
            monitor_motion(ser, (rx, ry, high_z))

        if results:
            errors = [float(r["error_xy_mm"]) for r in results]
            mean = statistics.mean(errors)
            rmse = math.sqrt(sum(e*e for e in errors) / len(errors))
            med = statistics.median(errors)
            mx = max(errors)

            print("\n" + "=" * 82)
            print("[HELD-OUT SUMMARY]")
            for r in results:
                print(
                    f"{r['point_id']}: "
                    f"nominal=({r['nominal_board_x_mm']:.1f},{r['nominal_board_y_mm']:.1f}) "
                    f"actual=({r['actual_board_x_mm']:.1f},{r['actual_board_y_mm']:.1f}) "
                    f"XY error={r['error_xy_mm']:.2f} mm"
                )
            print(f"Mean   = {mean:.3f} mm")
            print(f"RMSE   = {rmse:.3f} mm")
            print(f"Median = {med:.3f} mm")
            print(f"Max    = {mx:.3f} mm")
            print(f"CSV    = {out_csv}")
            print("=" * 82)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        try:
            send_json(ser, {"T": 106, "spd": 0})
        except Exception:
            pass
    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] Serial port closed.")


if __name__ == "__main__":
    main()
