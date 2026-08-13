#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 Held-out Validation V3
-------------------------
Purpose:
  Sanity-check the frozen paper->robot registration at three held-out paper points
  H1/H2/H3 using the corrected execution configuration:

      base PID = P16 / I8
      T104 Cartesian execution only
      NO extra T101 base correction

This is a SAFE HIGH-HOVER validation only:
  surface Z + 40 mm
No table descent and no touching.

Held-out paper points:
  H1 = (-80, -60) mm
  H2 = (-60, +50) mm
  H3 = (+40, -20) mm

Frozen 20-point paper->robot planar affine model:
  robot_x = -0.074105303*paper_x + 0.992259200*paper_y + 187.854293495
  robot_y = -0.986716324*paper_x - 0.006933251*paper_y -   4.851741339
  robot_z =  0.001405397*paper_x + 0.006345201*paper_y - 118.909081155

Important:
- T105 feedback is NOT independent physical ground truth.
- The optional manual hover observation is diagnostic only.
- Formal E4 endpoint GT will still come from the physical paper mark.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import serial


# ---------------------------------------------------------------------------
# Frozen registration
# ---------------------------------------------------------------------------

MODEL = {
    "robot_x": (-0.074105303,  0.992259200, 187.854293495),
    "robot_y": (-0.986716324, -0.006933251,  -4.851741339),
    "robot_z": ( 0.001405397,  0.006345201, -118.909081155),
}

HELDOUT = {
    "H1": (-80.0, -60.0),
    "H2": (-60.0,  50.0),
    "H3": ( 40.0, -20.0),
}

SAFE_HOVER_MM = 40.0
TARGET_TIT_RAD = 1.5

BASE_PID_P = 16
BASE_PID_I = 8

T104_SPD = 0.05

BOOT_WAIT_S = 22.0
RETURN_WAIT_S = 10.0
MOVE_WAIT_S = 12.0

# Internal firmware-feedback safety gate only.
MAX_INTERNAL_3D_ERROR_MM = 20.0


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument(
        "--out-root",
        default="/mnt/c/Users/ASUS/Desktop/paper/E4/E4_heldout_validation_v3",
    )
    return p.parse_args()


def paper_to_robot(px: float, py: float):
    def f(c):
        a, b, d = c
        return a * px + b * py + d

    return (
        f(MODEL["robot_x"]),
        f(MODEL["robot_y"]),
        f(MODEL["robot_z"]),
    )


def send_json(ser: serial.Serial, obj: Dict[str, Any], label="SEND"):
    text = json.dumps(obj, separators=(",", ":"))
    ser.reset_input_buffer()
    print(f"[{label}] {text}")
    ser.write((text + "\n").encode("utf-8"))
    ser.flush()


def parse_t1051(line: str) -> Optional[Dict[str, Any]]:
    i, j = line.find("{"), line.rfind("}")
    if i < 0 or j <= i:
        return None

    try:
        d = json.loads(line[i:j + 1])
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
    print(f"[T105 PRE-FLUSH] {queued} byte(s)")

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
        {
            "T": 108,
            "joint": 1,
            "p": BASE_PID_P,
            "i": BASE_PID_I,
        },
        "T108 BASE PID",
    )
    time.sleep(1.0)


def move_t104(ser, x, y, z, tit):
    send_json(
        ser,
        {
            "T": 104,
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "t": float(tit),
            "spd": T104_SPD,
        },
        "T104",
    )


def pose_error(state, target):
    tx, ty, tz = target
    dx = float(state["x"]) - tx
    dy = float(state["y"]) - ty
    dz = float(state["z"]) - tz
    xy = math.hypot(dx, dy)
    e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx, dy, dz, xy, e3


def print_state(target_id, paper_xy, target_xyz, state):
    dx, dy, dz, xy, e3 = pose_error(state, target_xyz)

    print("\n" + "=" * 80)
    print(f"[{target_id} HIGH — FRESH FEEDBACK]")
    print(f"Paper target = ({paper_xy[0]:+.1f}, {paper_xy[1]:+.1f}) mm")
    print(
        f"Robot HIGH target = "
        f"({target_xyz[0]:.3f}, {target_xyz[1]:.3f}, {target_xyz[2]:.3f}) mm"
    )
    print(
        f"T105 actual = "
        f"({state['x']:.3f}, {state['y']:.3f}, {state['z']:.3f}) mm"
    )
    print(
        f"Firmware target residual: "
        f"dX={dx:+.3f} dY={dy:+.3f} dZ={dz:+.3f} mm | "
        f"XY={xy:.3f} mm | 3D={e3:.3f} mm"
    )
    print(
        f"joints: b={state['b']:.6f} s={state['s']:.6f} "
        f"e={state['e']:.6f} t={state['t']:.6f} "
        f"r={state['r']:.6f} g={state['g']:.6f}"
    )
    print("=" * 80)


def parse_manual_observation(text, target_xy):
    """
    Accepted:
      OK
      SKIP
      x,y

    x,y is a manually observed paper-frame location and is diagnostic only.
    """
    s = text.strip()

    if not s:
        return "SKIP", None, None, None

    if s.upper() in ("OK", "PASS"):
        return "OK", None, None, None

    if s.upper() in ("SKIP", "S"):
        return "SKIP", None, None, None

    try:
        parts = [v.strip() for v in s.split(",")]
        if len(parts) != 2:
            raise ValueError

        ox, oy = float(parts[0]), float(parts[1])
        tx, ty = target_xy

        dx = ox - tx
        dy = oy - ty
        err = math.hypot(dx, dy)

        return "MEASURED", ox, oy, err

    except Exception:
        return "INVALID", None, None, None


def main():
    a = parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(a.out_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "heldout_high_hover.csv"
    meta_path = out_dir / "metadata.json"

    print("=" * 80)
    print("E4 HELD-OUT VALIDATION V3")
    print("=" * 80)
    print("Execution configuration:")
    print(f"  Base PID = P{BASE_PID_P} / I{BASE_PID_I}")
    print("  T104 Cartesian only")
    print("  NO T101 base correction")
    print(f"  Safe hover = surface Z + {SAFE_HOVER_MM:.0f} mm")
    print()
    print("Held-out targets:")

    target_cache = {}

    for target_id, (px, py) in HELDOUT.items():
        sx, sy, sz = paper_to_robot(px, py)
        high = (sx, sy, sz + SAFE_HOVER_MM)
        target_cache[target_id] = {
            "paper": (px, py),
            "surface": (sx, sy, sz),
            "high": high,
        }

        print(
            f"  {target_id}: paper=({px:+.0f},{py:+.0f}) "
            f"surface=({sx:.3f},{sy:.3f},{sz:.3f}) "
            f"HIGH=({high[0]:.3f},{high[1]:.3f},{high[2]:.3f})"
        )

    print("\n[SAFETY]")
    print("- HIGH HOVER ONLY. This script never descends to the paper.")
    print("- No roarm_driver / MoveIt / other process may use /dev/ttyUSB0.")
    print("- Keep one hand near the power switch.")
    print("- Each target requires explicit confirmation.")

    input("\nPress Enter to open serial...")

    ser = serial.Serial(
        port=a.port,
        baudrate=a.baud,
        timeout=0.20,
        write_timeout=0.5,
        rtscts=False,
        dsrdtr=False,
    )

    rows = []

    try:
        try:
            ser.setDTR(False)
            ser.setRTS(False)
        except Exception:
            pass

        print(f"[BOOT] Waiting {BOOT_WAIT_S:.0f}s with NO commands...")
        time.sleep(BOOT_WAIT_S)

        queued = ser.in_waiting
        ser.reset_input_buffer()
        print(f"[BOOT FLUSH] {queued} byte(s)")

        start = fresh_t105(ser)

        print("\n[FIXED START CAPTURED]")
        print(
            f"XYZ=({start['x']:.3f}, {start['y']:.3f}, {start['z']:.3f}) mm "
            f"t={start['t']:.6f}"
        )

        set_base_pid(ser)
        print(f"[PID] Base P={BASE_PID_P}, I={BASE_PID_I} applied after boot.")

        for target_id in ("H1", "H2", "H3"):
            data = target_cache[target_id]
            paper_xy = data["paper"]
            surface_xyz = data["surface"]
            high_xyz = data["high"]

            print("\n" + "#" * 80)
            print(f"NEXT TARGET: {target_id}")
            print("#" * 80)
            print(
                f"Paper target: ({paper_xy[0]:+.1f}, {paper_xy[1]:+.1f}) mm"
            )
            print(
                f"Predicted robot surface: "
                f"({surface_xyz[0]:.3f}, {surface_xyz[1]:.3f}, "
                f"{surface_xyz[2]:.3f}) mm"
            )
            print(
                f"Safe HIGH target: "
                f"({high_xyz[0]:.3f}, {high_xyz[1]:.3f}, "
                f"{high_xyz[2]:.3f}) mm"
            )

            confirm = input(
                f"\nType {target_id} to execute this HIGH-HOVER target, "
                f"or Q to stop: "
            ).strip().upper()

            if confirm == "Q":
                print("Stopped by user.")
                break

            if confirm != target_id:
                print("Confirmation mismatch; stopping.")
                break

            # Reapply PID in case some controller action restored defaults.
            set_base_pid(ser)

            print("[1] Return to fixed start")
            move_t104(
                ser,
                start["x"],
                start["y"],
                start["z"],
                start["t"],
            )
            time.sleep(RETURN_WAIT_S)
            start_actual = fresh_t105(ser)

            print(f"[2] Move to {target_id} HIGH")
            move_t104(
                ser,
                high_xyz[0],
                high_xyz[1],
                high_xyz[2],
                TARGET_TIT_RAD,
            )
            time.sleep(MOVE_WAIT_S)

            actual = fresh_t105(ser)
            print_state(target_id, paper_xy, high_xyz, actual)

            dx, dy, dz, xy, e3 = pose_error(actual, high_xyz)

            if e3 > MAX_INTERNAL_3D_ERROR_MM:
                print(
                    f"\n[SAFETY STOP] T105 3D residual {e3:.3f} mm exceeds "
                    f"{MAX_INTERNAL_3D_ERROR_MM:.1f} mm."
                )
                print("Do not continue to the next target.")
                break

            print(
                "\nManual high-hover observation (diagnostic only):\n"
                "  OK       = pointer visually appears over the intended paper point\n"
                "  SKIP     = do not record a physical judgment\n"
                "  x,y      = manually observed paper-frame XY, e.g. -78,-61\n"
            )

            while True:
                obs_text = input("Observation: ")
                obs_status, obs_x, obs_y, obs_err = parse_manual_observation(
                    obs_text, paper_xy
                )

                if obs_status != "INVALID":
                    break

                print("Invalid entry. Use OK, SKIP, or x,y.")

            if obs_status == "MEASURED":
                print(
                    f"[MANUAL] observed=({obs_x:+.2f},{obs_y:+.2f}) mm | "
                    f"physical hover XY error={obs_err:.3f} mm"
                )

            row = {
                "target_id": target_id,
                "timestamp": datetime.now().isoformat(timespec="seconds"),

                "paper_target_x_mm": paper_xy[0],
                "paper_target_y_mm": paper_xy[1],

                "robot_surface_x_mm": surface_xyz[0],
                "robot_surface_y_mm": surface_xyz[1],
                "robot_surface_z_mm": surface_xyz[2],

                "robot_high_target_x_mm": high_xyz[0],
                "robot_high_target_y_mm": high_xyz[1],
                "robot_high_target_z_mm": high_xyz[2],

                "actual_x_mm": actual["x"],
                "actual_y_mm": actual["y"],
                "actual_z_mm": actual["z"],

                "firmware_dx_mm": dx,
                "firmware_dy_mm": dy,
                "firmware_dz_mm": dz,
                "firmware_xy_error_mm": xy,
                "firmware_3d_error_mm": e3,

                "actual_base_rad": actual["b"],
                "actual_shoulder_rad": actual["s"],
                "actual_elbow_rad": actual["e"],
                "actual_wrist_rad": actual["t"],
                "actual_roll_rad": actual["r"],
                "actual_gripper_rad": actual["g"],

                "manual_observation_status": obs_status,
                "manual_observed_paper_x_mm": obs_x,
                "manual_observed_paper_y_mm": obs_y,
                "manual_hover_xy_error_mm": obs_err,

                "base_pid_p": BASE_PID_P,
                "base_pid_i": BASE_PID_I,
                "t104_spd": T104_SPD,
                "safe_hover_mm": SAFE_HOVER_MM,

                "start_actual_x_mm": start_actual["x"],
                "start_actual_y_mm": start_actual["y"],
                "start_actual_z_mm": start_actual["z"],
            }

            rows.append(row)

            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

            print(f"[SAVED] {target_id}")

        meta = {
            "run_id": run_id,
            "purpose": "E4 held-out high-hover sanity validation",
            "formal_endpoint_ground_truth": False,
            "execution": {
                "base_pid_p": BASE_PID_P,
                "base_pid_i": BASE_PID_I,
                "controller": "T104 Cartesian only",
                "extra_t101_base_correction": False,
                "safe_hover_mm": SAFE_HOVER_MM,
                "target_tit_rad": TARGET_TIT_RAD,
                "t104_spd": T104_SPD,
            },
            "registration": {
                "type": "20-point planar affine",
                "robot_x": MODEL["robot_x"],
                "robot_y": MODEL["robot_y"],
                "robot_z": MODEL["robot_z"],
            },
            "heldout_points": HELDOUT,
            "csv": str(csv_path),
            "completed_targets": [r["target_id"] for r in rows],
        }

        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        print("\n" + "=" * 80)
        print("HELD-OUT V3 COMPLETE")
        print("=" * 80)

        if rows:
            for r in rows:
                extra = ""
                if r["manual_hover_xy_error_mm"] is not None:
                    extra = (
                        f" | manual hover XY="
                        f"{r['manual_hover_xy_error_mm']:.3f} mm"
                    )

                print(
                    f"{r['target_id']}: "
                    f"T105 XY={r['firmware_xy_error_mm']:.3f} mm | "
                    f"3D={r['firmware_3d_error_mm']:.3f} mm | "
                    f"manual={r['manual_observation_status']}"
                    f"{extra}"
                )

        print(f"\nCSV:  {csv_path}")
        print(f"Meta: {meta_path}")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        if rows:
            print(f"Partial CSV retained: {csv_path}")

    finally:
        try:
            ser.close()
        except Exception:
            pass

        print("[CLOSED] serial closed.")


if __name__ == "__main__":
    main()
