#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 H1 single-joint tracking diagnostic (T101)
---------------------------------------------
Purpose:
  Diagnose why T102 did not reach the IKFast joint target.

Sequence:
  1) Read current T105 pose.
  2) Test BASE only using official T101.
  3) If BASE reaches target, optionally test SHOULDER only using T101.
  4) Report joint residuals and Cartesian H1-high residual.

Safety:
  - Intended ONLY when the robot is already near the H1 HIGH pose.
  - Refuses to move if current Cartesian pose is too far from H1 high.
  - Small corrections only (~3 deg base, ~1 deg shoulder in the current case).
  - No T105 polling is sent for 3 s after each move, to avoid any possibility
    of feedback traffic interfering with motion.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from typing import Any, Dict, List, Optional

import serial


H1_XYZ = (134.247166, 74.501560, -79.402225)

IK_BASE = 0.5120438298092209
IK_SHOULDER = 0.2580689332852309

SAFE_START_MAX_3D_MM = 25.0
JOINT_PASS_RAD = 0.0040       # ~0.23 deg
DEFAULT_SPD = 100             # official T101 unit: steps/s
DEFAULT_ACC = 10
NO_POLL_WAIT_S = 3.0
SAMPLE_COUNT = 7


def args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--spd", type=int, default=DEFAULT_SPD)
    p.add_argument("--acc", type=int, default=DEFAULT_ACC)
    return p.parse_args()


def open_serial(port: str, baud: int) -> serial.Serial:
    s = serial.Serial()
    s.port = port
    s.baudrate = baud
    s.timeout = 0.15
    s.write_timeout = 0.5
    s.rtscts = False
    s.dsrdtr = False
    try:
        s.dtr = False
        s.rts = False
    except Exception:
        pass
    s.open()
    try:
        s.setDTR(False)
        s.setRTS(False)
    except Exception:
        pass
    s.reset_input_buffer()
    s.reset_output_buffer()
    return s


def send(ser: serial.Serial, obj: Dict[str, Any]) -> None:
    text = json.dumps(obj, separators=(",", ":"))
    print("[SEND]", text)
    ser.write((text + "\n").encode())
    ser.flush()


def parse_t1051(line: str) -> Optional[Dict[str, Any]]:
    i, j = line.find("{"), line.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(line[i:j+1])
    except Exception:
        return None
    return d if d.get("T") == 1051 else None


def get_pose(ser: serial.Serial, timeout=35.0) -> Dict[str, Any]:
    end = time.time() + timeout
    next_req = 0.0
    while time.time() < end:
        now = time.time()
        if now >= next_req:
            send(ser, {"T": 105})
            next_req = now + 0.7
        raw = ser.readline()
        if raw:
            p = parse_t1051(raw.decode(errors="replace"))
            if p and all(isinstance(p.get(k), (int, float))
                         for k in ("x","y","z","b","s","e","t","r","g")):
                return p
    raise RuntimeError("No valid T1051 received.")


def median_pose(ser: serial.Serial, n=SAMPLE_COUNT) -> Dict[str, Any]:
    samples: List[Dict[str, Any]] = []
    deadline = time.time() + 12.0
    while len(samples) < n and time.time() < deadline:
        send(ser, {"T": 105})
        local_end = time.time() + 1.0
        while time.time() < local_end:
            raw = ser.readline()
            if not raw:
                continue
            p = parse_t1051(raw.decode(errors="replace"))
            if p and all(isinstance(p.get(k), (int, float))
                         for k in ("x","y","z","b","s","e","t","r","g")):
                samples.append(p)
                break
        time.sleep(0.15)

    if not samples:
        raise RuntimeError("No T105 samples collected.")

    keys = ["x","y","z","tit","b","s","e","t","r","g",
            "tB","tS","tE","tT","tR","tG",
            "torswitchB","torswitchS","torswitchE","torswitchT","torswitchR","torswitchG"]
    out = {}
    for k in keys:
        vals = [float(p[k]) for p in samples if isinstance(p.get(k), (int, float))]
        if vals:
            out[k] = statistics.median(vals)
    return out


def err3(p: Dict[str, Any]) -> float:
    return math.dist((p["x"],p["y"],p["z"]), H1_XYZ)


def print_pose(title: str, p: Dict[str, Any]) -> None:
    dx = p["x"] - H1_XYZ[0]
    dy = p["y"] - H1_XYZ[1]
    dz = p["z"] - H1_XYZ[2]
    print("\n" + "="*76)
    print(title)
    print(
        f"XYZ=({p['x']:.3f},{p['y']:.3f},{p['z']:.3f}) mm | "
        f"H1 residual dX={dx:+.3f} dY={dy:+.3f} dZ={dz:+.3f} "
        f"XY={math.hypot(dx,dy):.3f} 3D={math.sqrt(dx*dx+dy*dy+dz*dz):.3f} mm"
    )
    print(
        f"b={p['b']:.6f} s={p['s']:.6f} e={p['e']:.6f} "
        f"t={p['t']:.6f} r={p['r']:.6f} g={p['g']:.6f}"
    )
    extras = []
    for k in ("tB","tS","tE","tT","tR","torswitchB","torswitchS","torswitchE","torswitchT","torswitchR"):
        if k in p:
            extras.append(f"{k}={p[k]:.0f}")
    if extras:
        print("feedback:", " ".join(extras))
    print("="*76)


def main():
    a = args()

    print("="*76)
    print("E4 H1 T101 SINGLE-JOINT TRACKING TEST")
    print("="*76)
    print(f"H1 high XYZ target: {H1_XYZ} mm")
    print(f"IKFast base target:     {IK_BASE:.9f} rad")
    print(f"IKFast shoulder target: {IK_SHOULDER:.9f} rad")
    print(f"T101 speed={a.spd} steps/s, acc={a.acc}")
    print("\nNo MoveIt/ROS driver should be using /dev/ttyUSB0 at the same time.")
    input("Press Enter when the arm is still near H1 HIGH and the path is clear...")

    ser = open_serial(a.port, a.baud)
    try:
        print("[INIT] Waiting for T105...")
        p0 = get_pose(ser)
        print_pose("[START]", p0)

        if err3(p0) > SAFE_START_MAX_3D_MM:
            raise RuntimeError(
                f"Start pose is {err3(p0):.1f} mm from H1 high; "
                f"refusing motion (limit {SAFE_START_MAX_3D_MM:.1f} mm)."
            )

        # -------- BASE only --------
        base_delta = IK_BASE - p0["b"]
        print(
            f"\nBASE correction requested: {base_delta:+.6f} rad "
            f"({math.degrees(base_delta):+.3f} deg)"
        )
        if abs(base_delta) > 0.12:
            raise RuntimeError("Base correction > 0.12 rad; refusing.")

        if input("Type BASE to send T101 base target: ").strip().upper() != "BASE":
            print("Cancelled.")
            return

        send(ser, {
            "T": 101,
            "joint": 1,
            "rad": round(IK_BASE, 9),
            "spd": a.spd,
            "acc": a.acc,
        })
        print(f"[WAIT] {NO_POLL_WAIT_S:.1f}s with NO T105 polling...")
        time.sleep(NO_POLL_WAIT_S)

        pb = median_pose(ser)
        print_pose("[AFTER T101 BASE]", pb)
        b_res = pb["b"] - IK_BASE
        print(
            f"BASE residual actual-target = {b_res:+.6f} rad "
            f"({math.degrees(b_res):+.3f} deg)"
        )

        if abs(b_res) > JOINT_PASS_RAD:
            print(
                "\n[DIAGNOSIS] BASE did NOT reach its T101 target. "
                "Stop here: this points to joint-command/servo execution, not IKFast."
            )
            return

        print("\n[PASS] BASE reached the requested T101 target.")

        # -------- SHOULDER only --------
        shoulder_delta = IK_SHOULDER - pb["s"]
        print(
            f"\nSHOULDER correction requested: {shoulder_delta:+.6f} rad "
            f"({math.degrees(shoulder_delta):+.3f} deg)"
        )
        if abs(shoulder_delta) > 0.12:
            raise RuntimeError("Shoulder correction > 0.12 rad; refusing.")

        if input("Type SHOULDER to send T101 shoulder target: ").strip().upper() != "SHOULDER":
            print("Stopped after BASE test.")
            return

        send(ser, {
            "T": 101,
            "joint": 2,
            "rad": round(IK_SHOULDER, 9),
            "spd": a.spd,
            "acc": a.acc,
        })
        print(f"[WAIT] {NO_POLL_WAIT_S:.1f}s with NO T105 polling...")
        time.sleep(NO_POLL_WAIT_S)

        ps = median_pose(ser)
        print_pose("[AFTER T101 SHOULDER]", ps)
        s_res = ps["s"] - IK_SHOULDER
        print(
            f"SHOULDER residual actual-target = {s_res:+.6f} rad "
            f"({math.degrees(s_res):+.3f} deg)"
        )

        print("\n" + "="*76)
        print("[SUMMARY]")
        print(
            f"BASE:     target={IK_BASE:.6f}, actual={ps['b']:.6f}, "
            f"residual={ps['b']-IK_BASE:+.6f} rad"
        )
        print(
            f"SHOULDER: target={IK_SHOULDER:.6f}, actual={ps['s']:.6f}, "
            f"residual={ps['s']-IK_SHOULDER:+.6f} rad"
        )
        dx = ps["x"] - H1_XYZ[0]
        dy = ps["y"] - H1_XYZ[1]
        dz = ps["z"] - H1_XYZ[2]
        print(
            f"H1 Cartesian: XY={math.hypot(dx,dy):.3f} mm, "
            f"3D={math.sqrt(dx*dx+dy*dy+dz*dz):.3f} mm"
        )

        if abs(ps["b"]-IK_BASE) <= JOINT_PASS_RAD and abs(ps["s"]-IK_SHOULDER) <= JOINT_PASS_RAD:
            print(
                "Both single-joint commands tracked correctly. "
                "This strongly implicates the T102 all-joint path (or its interaction), "
                "not the individual servos."
            )
        else:
            print(
                "At least one individual joint did not track its target. "
                "Investigate joint execution/servo load/torque before blaming IK."
            )
        print("="*76)

    except KeyboardInterrupt:
        print("\nInterrupted; closing serial.")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] serial closed.")


if __name__ == "__main__":
    main()
