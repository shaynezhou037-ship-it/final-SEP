#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 Contact / Marking Pilot V1
=============================

Purpose
-------
Establish a SAFE, FIXED vertical contact protocol before the formal
Oracle / Affine / Homography / PnP robot trials.

THIS IS NOT A FORMAL E4 RESULT.
This script uses the development point paper O=(0,0), so none of the
9 formal held-out targets are consumed for tuning.

Frozen downstream configuration
-------------------------------
paper -> robot registration:
  robot_x = -0.074105303*paper_x + 0.992259200*paper_y + 187.854293495
  robot_y = -0.986716324*paper_x - 0.006933251*paper_y -   4.851741339
  robot_z =  0.001405397*paper_x + 0.006345201*paper_y - 118.909081155

Robot execution:
  base PID P16/I8
  T104 Cartesian only
  NO T101 correction
  target tit = 1.5 rad

Pilot point:
  paper O = (0,0) mm
  predicted robot surface =
    (187.854293495, -4.851741339, -118.909081155) mm

Workflow
--------
1) Open serial once (controller may reset); wait 22 s.
2) Capture startup pose as fixed start.
3) Apply base PID P16/I8.
4) Move fixed start -> O high (+40 mm).
5) Move vertically to O pre-contact (+12 mm).
6) User manually steps downward:
       2  = down 2.0 mm
       1  = down 1.0 mm
       0.5 = down 0.5 mm
       0.2 = down 0.2 mm
       u1 = up 1.0 mm
       u2 = up 2.0 mm
       c  = CONTACT CONFIRMED (record)
       q  = abort
7) Hard software guard: no command below predicted surface - 4 mm.
8) After contact confirmation, rise vertically +15 mm, then return to start.

Output
------
E4_contact_pilot/<runid>/contact_pilot.json

Important
---------
- T105 is internal firmware feedback, NOT independent physical GT.
- Contact must be visually/physically confirmed by the user.
- Use the SAME final marking medium / pointer setup you intend to use later,
  if possible.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import serial


# ---------------------------------------------------------------------------
# Frozen paper -> robot registration
# ---------------------------------------------------------------------------

MODEL = {
    "robot_x": (-0.074105303, +0.992259200, +187.854293495),
    "robot_y": (-0.986716324, -0.006933251,   -4.851741339),
    "robot_z": (+0.001405397, +0.006345201, -118.909081155),
}

PILOT_PAPER_X_MM = 0.0
PILOT_PAPER_Y_MM = 0.0

BASE_PID_P = 16
BASE_PID_I = 8

TARGET_TIT_RAD = 1.5

SAFE_HIGH_MM = 40.0
PRECONTACT_MM = 12.0
POST_CONTACT_RISE_MM = 15.0

T104_TRAVEL_SPD = 0.05
T104_DESCENT_SPD = 0.02

BOOT_WAIT_S = 22.0
TRAVEL_WAIT_S = 12.0
SMALL_STEP_WAIT_S = 3.0

# Never command more than 4 mm below the registration-predicted surface.
LOWER_GUARD_MM = -4.0


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument(
        "--out-root",
        default="/mnt/c/Users/ASUS/Desktop/paper/E4/E4_contact_pilot",
    )
    return p.parse_args()


def paper_to_robot(px: float, py: float):
    def f(c):
        return c[0] * px + c[1] * py + c[2]

    return (
        f(MODEL["robot_x"]),
        f(MODEL["robot_y"]),
        f(MODEL["robot_z"]),
    )


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


def move_t104(ser: serial.Serial, x, y, z, tit, spd):
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


def print_pose(label, state, target_xyz=None):
    print("\n" + "=" * 80)
    print(label)
    print(
        f"XYZ=({state['x']:.3f}, {state['y']:.3f}, {state['z']:.3f}) mm | "
        f"b={state['b']:.6f} s={state['s']:.6f} e={state['e']:.6f} "
        f"t={state['t']:.6f} r={state['r']:.6f}"
    )

    if target_xyz is not None:
        tx, ty, tz = target_xyz
        dx = float(state["x"]) - tx
        dy = float(state["y"]) - ty
        dz = float(state["z"]) - tz
        xy = math.hypot(dx, dy)
        e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
        print(
            f"T105 residual to commanded pose: "
            f"dX={dx:+.3f} dY={dy:+.3f} dZ={dz:+.3f} mm | "
            f"XY={xy:.3f} | 3D={e3:.3f}"
        )
    print("=" * 80)


def main():
    args = parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "contact_pilot.json"

    sx, sy, sz = paper_to_robot(PILOT_PAPER_X_MM, PILOT_PAPER_Y_MM)

    high_z = sz + SAFE_HIGH_MM
    precontact_z = sz + PRECONTACT_MM
    guard_z = sz + LOWER_GUARD_MM

    print("=" * 80)
    print("E4 CONTACT / MARKING PILOT V1")
    print("=" * 80)
    print("DEVELOPMENT POINT ONLY — NOT A FORMAL E4 TARGET")
    print(f"paper O = ({PILOT_PAPER_X_MM:.1f},{PILOT_PAPER_Y_MM:.1f}) mm")
    print(
        f"predicted robot surface = ({sx:.3f},{sy:.3f},{sz:.3f}) mm"
    )
    print(f"safe HIGH Z       = {high_z:.3f} mm  (surface +{SAFE_HIGH_MM:.0f})")
    print(f"pre-contact Z     = {precontact_z:.3f} mm  (surface +{PRECONTACT_MM:.0f})")
    print(f"HARD lower guard  = {guard_z:.3f} mm  (surface {LOWER_GUARD_MM:+.0f})")
    print()
    print("Frozen execution: base P16/I8, T104 only, tit=1.5 rad")
    print()
    print("SAFETY:")
    print("- Keep one hand near power.")
    print("- Nothing else may use /dev/ttyUSB0.")
    print("- The script will NOT descend automatically from pre-contact.")
    print("- You must visually confirm each further step.")
    print("=" * 80)

    input("\nPress Enter to open serial...")

    ser = serial.Serial(
        port=args.port,
        baudrate=args.baud,
        timeout=0.20,
        write_timeout=0.5,
        rtscts=False,
        dsrdtr=False,
    )

    record = {
        "run_id": run_id,
        "formal_result": False,
        "purpose": "contact/marking protocol pilot",
        "pilot_paper_xy_mm": [PILOT_PAPER_X_MM, PILOT_PAPER_Y_MM],
        "predicted_robot_surface_xyz_mm": [sx, sy, sz],
        "execution": {
            "base_pid_p": BASE_PID_P,
            "base_pid_i": BASE_PID_I,
            "controller": "T104 only",
            "target_tit_rad": TARGET_TIT_RAD,
            "travel_spd": T104_TRAVEL_SPD,
            "descent_spd": T104_DESCENT_SPD,
            "safe_high_mm": SAFE_HIGH_MM,
            "precontact_mm": PRECONTACT_MM,
            "lower_guard_relative_to_pred_surface_mm": LOWER_GUARD_MM,
        },
        "contact_confirmed": False,
        "command_history": [],
    }

    try:
        try:
            ser.setDTR(False)
            ser.setRTS(False)
        except Exception:
            pass

        print(f"[BOOT] Waiting {BOOT_WAIT_S:.0f}s with NO commands...")
        time.sleep(BOOT_WAIT_S)
        ser.reset_input_buffer()

        start = fresh_t105(ser)
        record["fixed_start_t105"] = start

        print_pose("[FIXED START]", start)

        set_base_pid(ser)

        confirm = input(
            "\nType RUN only if the pilot area is clear and the tip is safe: "
        ).strip().upper()

        if confirm != "RUN":
            print("Cancelled.")
            return

        # 1) High
        print("\n[1] Move to O HIGH")
        move_t104(
            ser, sx, sy, high_z,
            TARGET_TIT_RAD, T104_TRAVEL_SPD
        )
        record["command_history"].append({
            "stage": "high",
            "x": sx, "y": sy, "z": high_z,
        })
        time.sleep(TRAVEL_WAIT_S)
        high_state = fresh_t105(ser)
        record["high_t105"] = high_state
        print_pose("[O HIGH]", high_state, (sx, sy, high_z))

        input(
            "\nVisually confirm the pointer is safely above the intended O area. "
            "Press Enter to continue to pre-contact (+12 mm), or Ctrl+C to abort..."
        )

        # 2) Precontact
        print("\n[2] Vertical move to PRE-CONTACT")
        move_t104(
            ser, sx, sy, precontact_z,
            TARGET_TIT_RAD, T104_DESCENT_SPD
        )
        record["command_history"].append({
            "stage": "precontact",
            "x": sx, "y": sy, "z": precontact_z,
        })
        time.sleep(TRAVEL_WAIT_S)
        pre_state = fresh_t105(ser)
        record["precontact_t105"] = pre_state
        print_pose(
            "[PRE-CONTACT]",
            pre_state,
            (sx, sy, precontact_z),
        )

        current_z = precontact_z

        print("\nManual descent controls:")
        print("  2    -> down 2.0 mm")
        print("  1    -> down 1.0 mm")
        print("  0.5  -> down 0.5 mm")
        print("  0.2  -> down 0.2 mm")
        print("  u1   -> up 1.0 mm")
        print("  u2   -> up 2.0 mm")
        print("  p    -> fresh T105 only")
        print("  c    -> CONTACT CONFIRMED, record and rise")
        print("  q    -> abort and rise")
        print()
        print(
            f"Current command Z={current_z:.3f}; "
            f"predicted surface Z={sz:.3f}; "
            f"guard Z={guard_z:.3f}"
        )

        contact_state = None
        contact_command_z = None

        while True:
            cmd = input("\ncontact> ").strip().lower()

            if cmd == "p":
                st = fresh_t105(ser)
                print_pose("[FRESH T105]", st, (sx, sy, current_z))
                continue

            if cmd == "c":
                contact_command_z = current_z
                contact_state = fresh_t105(ser)
                record["contact_confirmed"] = True
                record["contact_command_z_mm"] = current_z
                record["contact_offset_from_pred_surface_mm"] = current_z - sz
                record["contact_t105"] = contact_state

                print_pose(
                    "[CONTACT CONFIRMED]",
                    contact_state,
                    (sx, sy, current_z),
                )
                print(
                    f"\nRecorded contact command offset = "
                    f"{current_z - sz:+.3f} mm relative to predicted surface."
                )
                break

            if cmd == "q":
                print("Abort requested; rising.")
                break

            steps = {
                "2": -2.0,
                "1": -1.0,
                "0.5": -0.5,
                ".5": -0.5,
                "0.2": -0.2,
                ".2": -0.2,
                "u1": +1.0,
                "u2": +2.0,
            }

            if cmd not in steps:
                print("Unknown command.")
                continue

            next_z = current_z + steps[cmd]

            if next_z < guard_z - 1e-9:
                print(
                    f"[BLOCKED] requested Z={next_z:.3f} is below hard guard "
                    f"{guard_z:.3f}. Do not force deeper; inspect setup."
                )
                continue

            print(
                f"[STEP] Z {current_z:.3f} -> {next_z:.3f} "
                f"(surface offset {next_z - sz:+.3f} mm)"
            )

            move_t104(
                ser, sx, sy, next_z,
                TARGET_TIT_RAD, T104_DESCENT_SPD
            )
            record["command_history"].append({
                "stage": "manual_step",
                "input": cmd,
                "x": sx, "y": sy, "z": next_z,
                "surface_offset_mm": next_z - sz,
            })

            current_z = next_z
            time.sleep(SMALL_STEP_WAIT_S)

            st = fresh_t105(ser)
            print_pose("[AFTER STEP]", st, (sx, sy, current_z))

        # 3) Vertical rise, regardless of contact/abort.
        rise_z = max(current_z + POST_CONTACT_RISE_MM, sz + SAFE_HIGH_MM)

        print(f"\n[3] Vertical rise to Z={rise_z:.3f}")
        move_t104(
            ser, sx, sy, rise_z,
            TARGET_TIT_RAD, T104_DESCENT_SPD
        )
        time.sleep(TRAVEL_WAIT_S)

        rise_state = fresh_t105(ser)
        record["rise_t105"] = rise_state
        print_pose("[AFTER RISE]", rise_state, (sx, sy, rise_z))

        print("\n[4] Return to fixed start")
        set_base_pid(ser)
        move_t104(
            ser,
            start["x"], start["y"], start["z"], start["t"],
            T104_TRAVEL_SPD,
        )
        time.sleep(TRAVEL_WAIT_S)

        final_state = fresh_t105(ser)
        record["final_start_return_t105"] = final_state
        print_pose("[RETURNED START]", final_state)

        json_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\n" + "=" * 80)
        print("CONTACT PILOT COMPLETE")
        print("=" * 80)

        if record["contact_confirmed"]:
            print(
                f"Contact command Z = {record['contact_command_z_mm']:.3f} mm"
            )
            print(
                f"Contact offset from predicted surface = "
                f"{record['contact_offset_from_pred_surface_mm']:+.3f} mm"
            )
            print(
                "This is ONE pilot measurement only; do not yet freeze a "
                "formal contact offset."
            )
        else:
            print("No contact was confirmed.")

        print(f"Saved: {json_path}")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        try:
            # Best-effort immediate upward move at current paper O.
            safe_z = sz + SAFE_HIGH_MM
            move_t104(
                ser, sx, sy, safe_z,
                TARGET_TIT_RAD, T104_DESCENT_SPD
            )
            print(f"[BEST-EFFORT SAFETY RISE] commanded Z={safe_z:.3f}")
        except Exception:
            pass

    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] serial closed.")


if __name__ == "__main__":
    main()
