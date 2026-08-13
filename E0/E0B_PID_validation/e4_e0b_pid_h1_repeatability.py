#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 / E0-B — H1 HIGH repeatability validation
RoArm-M3-S base PID = P16 / I8

Flow per trial:
captured fixed start
-> T104 H1 HIGH
-> official SDK T101 base correction to IKFast base target
-> fresh T105
-> 3 s creep check
-> return to fixed start

No table descent.
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

from roarm_sdk.roarm import roarm

H1_X = 134.247166
H1_Y = 74.501560
H1_Z = -79.402225
H1_TIT = 1.500000
IK_BASE = 0.5120438298092209

BASE_PID_P = 16
BASE_PID_I = 8

T104_SPD = 0.05
T101_SPEED = 0
T101_ACC = 10

BOOT_WAIT_S = 22.0
START_WAIT_S = 10.0
H1_WAIT_S = 12.0
BASE_WAIT_S = 4.0
CREEP_WAIT_S = 3.0

MAX_BASE_CORRECTION_RAD = math.radians(8.0)

BASE_GOOD_DEG = 1.0
BASE_MAX_DEG = 1.5
XY_MEAN_MAX_MM = 3.0
XY_MAX_MM = 5.0
CREEP_MAX_DEG = 0.30


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--trials", type=int, default=10)
    p.add_argument(
        "--out-root",
        default="/mnt/c/Users/ASUS/Desktop/paper/E4/E0B_PID_validation",
    )
    return p.parse_args()


def raw_send(ser, obj: Dict[str, Any], label="RAW SEND"):
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


def fresh_t105(ser, timeout_s=8.0) -> Dict[str, Any]:
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
        state = parse_t1051(raw.decode("utf-8", errors="replace"))
        if state is not None:
            return state
    raise RuntimeError("No valid fresh T1051 received.")


def h1_error(state):
    dx = float(state["x"]) - H1_X
    dy = float(state["y"]) - H1_Y
    dz = float(state["z"]) - H1_Z
    xy = math.hypot(dx, dy)
    e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx, dy, dz, xy, e3


def print_pose(title, state):
    dx, dy, dz, xy, e3 = h1_error(state)
    b_res_deg = math.degrees(float(state["b"]) - IK_BASE)

    print("\n" + "=" * 80)
    print(title)
    print(f"XYZ=({state['x']:.3f}, {state['y']:.3f}, {state['z']:.3f}) mm")
    print(
        f"H1 error: dX={dx:+.3f} dY={dy:+.3f} dZ={dz:+.3f} mm | "
        f"XY={xy:.3f} mm | 3D={e3:.3f} mm"
    )
    print(
        f"b={state['b']:.6f} s={state['s']:.6f} e={state['e']:.6f} "
        f"t={state['t']:.6f} r={state['r']:.6f} g={state['g']:.6f}"
    )
    print(f"base target={IK_BASE:.9f} rad | residual={b_res_deg:+.3f} deg")
    print("=" * 80)


def move_t104(ser, x, y, z, tit):
    raw_send(
        ser,
        {"T":104, "x":float(x), "y":float(y), "z":float(z),
         "t":float(tit), "spd":T104_SPD},
        "T104",
    )


def set_base_pid(ser):
    raw_send(
        ser,
        {"T":108, "joint":1, "p":BASE_PID_P, "i":BASE_PID_I},
        "T108 BASE PID",
    )
    time.sleep(1.0)


def calc_stats(values):
    return {
        "mean": statistics.mean(values),
        "sd": statistics.stdev(values) if len(values) >= 2 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def main():
    a = parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(a.out_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "h1_pid16_i8_repeatability.csv"
    summary_path = out_dir / "summary.json"

    print("=" * 80)
    print("E4 / E0-B — H1 HIGH REPEATABILITY")
    print("=" * 80)
    print(f"Trials: {a.trials}")
    print(f"Base PID: P={BASE_PID_P}, I={BASE_PID_I}")
    print(f"H1 = ({H1_X:.6f}, {H1_Y:.6f}, {H1_Z:.6f}) mm")
    print(f"IKFast base target = {IK_BASE:.9f} rad")
    print(f"Output: {out_dir}")

    print("\n[SAFETY]")
    print("- H1 HIGH only; no table descent.")
    print("- Keep one hand near the power switch.")
    print("- No roarm_driver / MoveIt / other process may use /dev/ttyUSB0.")
    print("- One serial connection remains open for all trials.")

    input("\nPress Enter to open serial...")

    arm = roarm(
        roarm_type="roarm_m3",
        port=a.port,
        baudrate=a.baud,
        timeout=0.1,
        debug=False,
        thread_lock=True,
    )
    ser = arm._serial_port
    rows = []

    try:
        print(f"[BOOT] Waiting {BOOT_WAIT_S:.0f}s with NO commands...")
        time.sleep(BOOT_WAIT_S)
        queued = ser.in_waiting
        ser.reset_input_buffer()
        print(f"[BOOT FLUSH] {queued} byte(s)")

        start_state = fresh_t105(ser)

        print("\n[FIXED START CAPTURED]")
        print(
            f"x={start_state['x']:.3f} y={start_state['y']:.3f} "
            f"z={start_state['z']:.3f} t={start_state['t']:.6f}"
        )

        set_base_pid(ser)

        if input(
            f"\nType RUN to begin {a.trials} automatic H1 HIGH trials: "
        ).strip().upper() != "RUN":
            print("Cancelled.")
            return

        for trial in range(1, a.trials + 1):
            print("\n" + "#" * 80)
            print(f"TRIAL {trial}/{a.trials}")
            print("#" * 80)

            set_base_pid(ser)

            print("[1] Return to fixed start")
            move_t104(
                ser,
                start_state["x"], start_state["y"],
                start_state["z"], start_state["t"]
            )
            time.sleep(START_WAIT_S)
            start_actual = fresh_t105(ser)

            print("[2] T104 -> H1 HIGH")
            move_t104(ser, H1_X, H1_Y, H1_Z, H1_TIT)
            time.sleep(H1_WAIT_S)
            before = fresh_t105(ser)
            print_pose("[BEFORE BASE CORRECTION]", before)

            correction = IK_BASE - float(before["b"])
            correction_deg = math.degrees(correction)
            print(
                f"Required base correction: {correction:+.6f} rad "
                f"({correction_deg:+.3f} deg)"
            )

            if abs(correction) > MAX_BASE_CORRECTION_RAD:
                raise RuntimeError(
                    f"Safety stop: base correction {correction_deg:+.3f} deg "
                    f"exceeds {math.degrees(MAX_BASE_CORRECTION_RAD):.1f} deg."
                )

            print("[3] Official SDK T101 -> IKFast base target")
            sdk_ret = arm.joint_radian_ctrl(
                joint=1,
                radian=IK_BASE,
                speed=T101_SPEED,
                acc=T101_ACC,
            )
            print("[SDK RETURN]", sdk_ret)

            time.sleep(BASE_WAIT_S)
            after = fresh_t105(ser)
            print_pose("[AFTER BASE CORRECTION]", after)

            print(f"[4] Creep check: wait {CREEP_WAIT_S:.0f}s")
            time.sleep(CREEP_WAIT_S)
            creep = fresh_t105(ser)

            dx, dy, dz, xy, e3 = h1_error(after)
            base_res_rad = float(after["b"]) - IK_BASE
            base_res_deg = math.degrees(base_res_rad)
            creep_base_rad = float(creep["b"]) - float(after["b"])
            creep_base_deg = math.degrees(creep_base_rad)
            creep_xyz_mm = math.sqrt(
                (float(creep["x"]) - float(after["x"]))**2 +
                (float(creep["y"]) - float(after["y"]))**2 +
                (float(creep["z"]) - float(after["z"]))**2
            )

            row = {
                "trial": trial,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "pid_p": BASE_PID_P,
                "pid_i": BASE_PID_I,
                "target_x_mm": H1_X,
                "target_y_mm": H1_Y,
                "target_z_mm": H1_Z,
                "ik_base_target_rad": IK_BASE,
                "start_x_mm": start_actual["x"],
                "start_y_mm": start_actual["y"],
                "start_z_mm": start_actual["z"],
                "start_base_rad": start_actual["b"],
                "pre_base_x_mm": before["x"],
                "pre_base_y_mm": before["y"],
                "pre_base_z_mm": before["z"],
                "pre_base_rad": before["b"],
                "requested_base_correction_rad": correction,
                "requested_base_correction_deg": correction_deg,
                "actual_x_mm": after["x"],
                "actual_y_mm": after["y"],
                "actual_z_mm": after["z"],
                "actual_base_rad": after["b"],
                "actual_shoulder_rad": after["s"],
                "actual_elbow_rad": after["e"],
                "actual_wrist_rad": after["t"],
                "actual_roll_rad": after["r"],
                "base_residual_rad": base_res_rad,
                "base_residual_deg": base_res_deg,
                "abs_base_residual_deg": abs(base_res_deg),
                "dx_mm": dx,
                "dy_mm": dy,
                "dz_mm": dz,
                "xy_error_mm": xy,
                "error_3d_mm": e3,
                "creep_base_rad": creep_base_rad,
                "creep_base_deg": creep_base_deg,
                "abs_creep_base_deg": abs(creep_base_deg),
                "creep_xyz_mm": creep_xyz_mm,
            }
            rows.append(row)

            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

            print(
                f"[TRIAL {trial}] "
                f"|base residual|={abs(base_res_deg):.3f} deg | "
                f"XY={xy:.3f} mm | 3D={e3:.3f} mm | "
                f"3s base creep={creep_base_deg:+.3f} deg"
            )

        abs_base = [r["abs_base_residual_deg"] for r in rows]
        signed_base = [r["base_residual_deg"] for r in rows]
        xy_values = [r["xy_error_mm"] for r in rows]
        e3_values = [r["error_3d_mm"] for r in rows]
        dz_values = [r["dz_mm"] for r in rows]
        creep_values = [r["abs_creep_base_deg"] for r in rows]

        good_base_count = sum(v < BASE_GOOD_DEG for v in abs_base)
        required_good = math.ceil(0.8 * a.trials)

        gates = {
            "base_good_count": {
                "value": good_base_count,
                "required_at_least": required_good,
                "pass": good_base_count >= required_good,
            },
            "base_max_deg": {
                "value": max(abs_base),
                "required_less_than": BASE_MAX_DEG,
                "pass": max(abs_base) < BASE_MAX_DEG,
            },
            "xy_mean_mm": {
                "value": statistics.mean(xy_values),
                "required_less_than": XY_MEAN_MAX_MM,
                "pass": statistics.mean(xy_values) < XY_MEAN_MAX_MM,
            },
            "xy_max_mm": {
                "value": max(xy_values),
                "required_less_than": XY_MAX_MM,
                "pass": max(xy_values) < XY_MAX_MM,
            },
            "creep_max_deg": {
                "value": max(creep_values),
                "required_less_than": CREEP_MAX_DEG,
                "pass": max(creep_values) < CREEP_MAX_DEG,
            },
        }

        overall_pass = all(v["pass"] for v in gates.values())

        summary = {
            "run_id": run_id,
            "trials": len(rows),
            "configuration": {
                "base_pid_p": BASE_PID_P,
                "base_pid_i": BASE_PID_I,
                "t104_spd": T104_SPD,
                "t101_speed": T101_SPEED,
                "t101_acc": T101_ACC,
                "ik_base_target_rad": IK_BASE,
                "h1_target_mm": [H1_X, H1_Y, H1_Z],
                "h1_tit_rad": H1_TIT,
            },
            "base_residual_deg_signed": calc_stats(signed_base),
            "base_residual_deg_absolute": calc_stats(abs_base),
            "xy_error_mm": calc_stats(xy_values),
            "error_3d_mm": calc_stats(e3_values),
            "z_error_mm": calc_stats(dz_values),
            "base_creep_abs_deg_3s": calc_stats(creep_values),
            "base_trials_under_1deg": good_base_count,
            "acceptance_gates": gates,
            "overall_pass": overall_pass,
            "csv": str(csv_path),
        }

        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        print("\n" + "=" * 80)
        print("FINAL SUMMARY")
        print("=" * 80)
        print(
            f"Base residual signed: mean={statistics.mean(signed_base):+.3f} deg, "
            f"SD={statistics.stdev(signed_base) if len(signed_base) > 1 else 0:.3f} deg"
        )
        print(
            f"|Base residual|: mean={statistics.mean(abs_base):.3f} deg, "
            f"max={max(abs_base):.3f} deg"
        )
        print(f"Base trials <1.0 deg: {good_base_count}/{a.trials}")
        print(
            f"XY error: mean={statistics.mean(xy_values):.3f} mm, "
            f"SD={statistics.stdev(xy_values) if len(xy_values) > 1 else 0:.3f} mm, "
            f"max={max(xy_values):.3f} mm"
        )
        print(
            f"3D error: mean={statistics.mean(e3_values):.3f} mm, "
            f"max={max(e3_values):.3f} mm"
        )
        print(
            f"3 s base creep: mean={statistics.mean(creep_values):.3f} deg, "
            f"max={max(creep_values):.3f} deg"
        )

        print("\nAcceptance gates:")
        for name, result in gates.items():
            print(f"  {'PASS' if result['pass'] else 'FAIL'}  {name}: {result}")

        if overall_pass:
            print("\nPASS — candidate configuration can be frozen for E4.")
        else:
            print("\nNOT YET FROZEN — inspect failed gate(s) before formal E4.")

        print(f"\nCSV:     {csv_path}")
        print(f"Summary: {summary_path}")
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
