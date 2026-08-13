#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 diagnostic — H2 HIGH repeatability only

Goal:
Determine whether the large H2 error seen in held-out V3 is:
  (A) repeatable / pose-specific controller bias, or
  (B) an occasional execution outlier.

Frozen conditions:
- Base PID P16 / I8
- T104 Cartesian only
- NO T101 correction
- H2 HIGH only, no descent
- Same captured start pose before every trial

H2 HIGH target:
  (241.913571675, 54.004575551, -78.676144925) mm
  tit = 1.5 rad
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
from typing import Any, Dict, Optional

import serial

H2_X = 241.913571675
H2_Y = 54.004575551
H2_Z = -78.676144925
H2_TIT = 1.5

BASE_PID_P = 16
BASE_PID_I = 8
T104_SPD = 0.05

BOOT_WAIT_S = 22.0
RETURN_WAIT_S = 10.0
MOVE_WAIT_S = 12.0
SETTLE_EXTRA_S = 3.0


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--trials", type=int, default=5)
    p.add_argument(
        "--out-root",
        default="/mnt/c/Users/ASUS/Desktop/paper/E4/E4_H2_repeatability",
    )
    return p.parse_args()


def send_json(ser, obj: Dict[str, Any], label="SEND"):
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
        d = json.loads(line[i:j+1])
    except Exception:
        return None
    if d.get("T") != 1051:
        return None
    req = ("x","y","z","b","s","e","t","r","g")
    if not all(isinstance(d.get(k), (int,float)) for k in req):
        return None
    return d


def fresh_t105(ser, timeout_s=8.0):
    n = ser.in_waiting
    ser.reset_input_buffer()
    print(f"[T105 PRE-FLUSH] {n} byte(s)")
    ser.write(b'{"T":105}\n')
    ser.flush()

    end = time.time() + timeout_s
    while time.time() < end:
        raw = ser.readline()
        if not raw:
            continue
        d = parse_t1051(raw.decode("utf-8", errors="replace"))
        if d is not None:
            return d
    raise RuntimeError("No fresh T1051 received.")


def set_base_pid(ser):
    send_json(
        ser,
        {"T":108, "joint":1, "p":BASE_PID_P, "i":BASE_PID_I},
        "T108 BASE PID",
    )
    time.sleep(1.0)


def move_t104(ser, x, y, z, tit):
    send_json(
        ser,
        {"T":104, "x":float(x), "y":float(y), "z":float(z),
         "t":float(tit), "spd":T104_SPD},
        "T104",
    )


def err(state):
    dx = float(state["x"]) - H2_X
    dy = float(state["y"]) - H2_Y
    dz = float(state["z"]) - H2_Z
    xy = math.hypot(dx, dy)
    e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx,dy,dz,xy,e3


def main():
    a = parse_args()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(a.out_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "h2_high_repeatability.csv"

    print("="*80)
    print("E4 DIAGNOSTIC — H2 HIGH REPEATABILITY")
    print("="*80)
    print(f"Trials: {a.trials}")
    print(f"Base PID: P{BASE_PID_P}/I{BASE_PID_I}")
    print(f"H2 HIGH = ({H2_X:.3f}, {H2_Y:.3f}, {H2_Z:.3f}) mm")
    print("T104 only; NO T101 correction; NO descent.")
    print(f"Output: {out_dir}")

    input("\nPress Enter to open serial...")

    ser = serial.Serial(
        a.port, a.baud,
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
        ser.reset_input_buffer()

        start = fresh_t105(ser)
        print(
            f"[START] XYZ=({start['x']:.3f},{start['y']:.3f},{start['z']:.3f}) "
            f"t={start['t']:.6f}"
        )

        set_base_pid(ser)

        if input(f"\nType RUN to start {a.trials} H2 trials: ").strip().upper() != "RUN":
            print("Cancelled.")
            return

        for i in range(1, a.trials + 1):
            print("\n" + "#"*80)
            print(f"TRIAL {i}/{a.trials}")
            print("#"*80)

            set_base_pid(ser)

            print("[1] Return to fixed start")
            move_t104(ser, start["x"], start["y"], start["z"], start["t"])
            time.sleep(RETURN_WAIT_S)
            start_actual = fresh_t105(ser)

            print("[2] Move to H2 HIGH")
            move_t104(ser, H2_X, H2_Y, H2_Z, H2_TIT)
            time.sleep(MOVE_WAIT_S)
            s1 = fresh_t105(ser)

            dx,dy,dz,xy,e3 = err(s1)

            print(
                f"[FIRST] XYZ=({s1['x']:.3f},{s1['y']:.3f},{s1['z']:.3f}) | "
                f"dX={dx:+.3f} dY={dy:+.3f} dZ={dz:+.3f} | "
                f"XY={xy:.3f} 3D={e3:.3f} mm"
            )

            print(f"[3] Wait extra {SETTLE_EXTRA_S:.0f}s, no commands")
            time.sleep(SETTLE_EXTRA_S)
            s2 = fresh_t105(ser)

            dx2,dy2,dz2,xy2,e32 = err(s2)

            settle_dx = float(s2["x"]) - float(s1["x"])
            settle_dy = float(s2["y"]) - float(s1["y"])
            settle_dz = float(s2["z"]) - float(s1["z"])
            settle_xyz = math.sqrt(settle_dx**2 + settle_dy**2 + settle_dz**2)

            print(
                f"[+3s]  XYZ=({s2['x']:.3f},{s2['y']:.3f},{s2['z']:.3f}) | "
                f"dX={dx2:+.3f} dY={dy2:+.3f} dZ={dz2:+.3f} | "
                f"XY={xy2:.3f} 3D={e32:.3f} mm | "
                f"settle drift={settle_xyz:.3f} mm"
            )

            row = {
                "trial": i,
                "timestamp": datetime.now().isoformat(timespec="seconds"),

                "target_x_mm": H2_X,
                "target_y_mm": H2_Y,
                "target_z_mm": H2_Z,

                "start_x_mm": start_actual["x"],
                "start_y_mm": start_actual["y"],
                "start_z_mm": start_actual["z"],

                "first_x_mm": s1["x"],
                "first_y_mm": s1["y"],
                "first_z_mm": s1["z"],
                "first_dx_mm": dx,
                "first_dy_mm": dy,
                "first_dz_mm": dz,
                "first_xy_error_mm": xy,
                "first_3d_error_mm": e3,

                "settled_x_mm": s2["x"],
                "settled_y_mm": s2["y"],
                "settled_z_mm": s2["z"],
                "settled_dx_mm": dx2,
                "settled_dy_mm": dy2,
                "settled_dz_mm": dz2,
                "settled_xy_error_mm": xy2,
                "settled_3d_error_mm": e32,
                "settle_drift_3d_mm": settle_xyz,

                "base_rad": s2["b"],
                "shoulder_rad": s2["s"],
                "elbow_rad": s2["e"],
                "wrist_rad": s2["t"],
                "roll_rad": s2["r"],

                "base_pid_p": BASE_PID_P,
                "base_pid_i": BASE_PID_I,
                "t104_spd": T104_SPD,
            }
            rows.append(row)

            with csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

        xy = [r["settled_xy_error_mm"] for r in rows]
        e3 = [r["settled_3d_error_mm"] for r in rows]
        dx = [r["settled_dx_mm"] for r in rows]
        dy = [r["settled_dy_mm"] for r in rows]
        dz = [r["settled_dz_mm"] for r in rows]
        drift = [r["settle_drift_3d_mm"] for r in rows]

        print("\n" + "="*80)
        print("H2 REPEATABILITY SUMMARY")
        print("="*80)
        print(
            f"dX mean={statistics.mean(dx):+.3f} mm | "
            f"SD={statistics.stdev(dx) if len(dx)>1 else 0:.3f}"
        )
        print(
            f"dY mean={statistics.mean(dy):+.3f} mm | "
            f"SD={statistics.stdev(dy) if len(dy)>1 else 0:.3f}"
        )
        print(
            f"dZ mean={statistics.mean(dz):+.3f} mm | "
            f"SD={statistics.stdev(dz) if len(dz)>1 else 0:.3f}"
        )
        print(
            f"XY mean={statistics.mean(xy):.3f} mm | "
            f"SD={statistics.stdev(xy) if len(xy)>1 else 0:.3f} | "
            f"min={min(xy):.3f} | max={max(xy):.3f}"
        )
        print(
            f"3D mean={statistics.mean(e3):.3f} mm | "
            f"max={max(e3):.3f}"
        )
        print(
            f"Extra 3s settle drift: mean={statistics.mean(drift):.3f} mm | "
            f"max={max(drift):.3f}"
        )

        if statistics.mean(xy) > 7.0 and (
            statistics.stdev(xy) if len(xy)>1 else 0
        ) < 3.0:
            print(
                "\nINTERPRETATION: H2 error is repeatable and pose-specific/systematic."
            )
        elif max(xy) - min(xy) > 5.0:
            print(
                "\nINTERPRETATION: H2 shows large run-to-run variability/outliers."
            )
        else:
            print(
                "\nINTERPRETATION: mixed; inspect per-axis residuals and joints."
            )

        print(f"\nCSV: {csv_path}")
        print("="*80)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        if rows:
            print(f"Partial CSV: {csv_path}")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] serial closed.")


if __name__ == "__main__":
    main()
