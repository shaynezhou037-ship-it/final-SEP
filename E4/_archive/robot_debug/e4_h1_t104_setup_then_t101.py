#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 H1: setup with T104, then diagnose T101 single-joint tracking.

Sequence:
  1) Read current T105 pose.
  2) Move to H1 HIGH with T104 (setup only).
  3) Record the settled T104 pose.
  4) Command BASE only to the IKFast target with T101.
  5) If BASE tracks, command SHOULDER only with T101.
  6) Report joint residuals and Cartesian residuals.

Safety:
  - H1 HIGH only; no descent to the table.
  - User confirmation before every motion.
  - After each motion, waits 3 s without T105 polling before measuring.
  - No automatic "stop" command is sent.
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
H1_TIT = 1.500000

IK_BASE = 0.5120438298092209
IK_SHOULDER = 0.2580689332852309

DEFAULT_T104_SPD = 0.05
DEFAULT_T101_SPD = 100
DEFAULT_ACC = 10

NO_POLL_WAIT_S = 3.0
JOINT_PASS_RAD = 0.0040       # about 0.23 deg
MAX_BASE_CORRECTION_RAD = 0.12
MAX_SHOULDER_CORRECTION_RAD = 0.12


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--t104-spd", type=float, default=DEFAULT_T104_SPD)
    p.add_argument("--t101-spd", type=int, default=DEFAULT_T101_SPD)
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
    return d if d.get("T") == 1051 else None


def valid_pose(p: Optional[Dict[str, Any]]) -> bool:
    if not p:
        return False
    return all(isinstance(p.get(k), (int, float))
               for k in ("x","y","z","b","s","e","t","r","g"))


def get_pose(ser: serial.Serial, timeout=35.0) -> Dict[str, Any]:
    end = time.time() + timeout
    next_req = 0.0
    last_msg = 0.0
    while time.time() < end:
        now = time.time()
        if now >= next_req:
            send(ser, {"T":105})
            next_req = now + 0.7

        raw = ser.readline()
        if raw:
            p = parse_t1051(raw.decode("utf-8", errors="replace"))
            if valid_pose(p):
                return p

        if now - last_msg >= 5.0:
            print(f"[WAIT] T105... {max(0.0, end-now):.0f}s remaining")
            last_msg = now

    raise RuntimeError("No valid T1051 received.")


def median_pose(ser: serial.Serial, n=7) -> Dict[str, Any]:
    samples: List[Dict[str, Any]] = []
    deadline = time.time() + 12.0

    while len(samples) < n and time.time() < deadline:
        send(ser, {"T":105})
        local_end = time.time() + 1.0
        while time.time() < local_end:
            raw = ser.readline()
            if not raw:
                continue
            p = parse_t1051(raw.decode("utf-8", errors="replace"))
            if valid_pose(p):
                samples.append(p)
                break
        time.sleep(0.15)

    if not samples:
        raise RuntimeError("No T105 samples collected.")

    keys = [
        "x","y","z","tit","b","s","e","t","r","g",
        "tB","tS","tE","tT","tR","tG",
        "torswitchB","torswitchS","torswitchE","torswitchT","torswitchR","torswitchG"
    ]
    out: Dict[str, Any] = {}
    for k in keys:
        vals = [float(p[k]) for p in samples if isinstance(p.get(k), (int, float))]
        if vals:
            out[k] = statistics.median(vals)
    return out


def h1_errors(p: Dict[str, Any]):
    dx = float(p["x"]) - H1_XYZ[0]
    dy = float(p["y"]) - H1_XYZ[1]
    dz = float(p["z"]) - H1_XYZ[2]
    xy = math.hypot(dx, dy)
    e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx, dy, dz, xy, e3


def print_pose(title: str, p: Dict[str, Any]):
    dx,dy,dz,xy,e3 = h1_errors(p)
    print("\n" + "="*78)
    print(title)
    print(
        f"XYZ=({p['x']:.3f},{p['y']:.3f},{p['z']:.3f}) mm | "
        f"H1 residual dX={dx:+.3f} dY={dy:+.3f} dZ={dz:+.3f} "
        f"XY={xy:.3f} 3D={e3:.3f} mm"
    )
    print(
        f"b={p['b']:.6f} s={p['s']:.6f} e={p['e']:.6f} "
        f"t={p['t']:.6f} r={p['r']:.6f} g={p['g']:.6f}"
    )
    extras = []
    for k in ("tB","tS","tE","tT","tR",
              "torswitchB","torswitchS","torswitchE","torswitchT","torswitchR"):
        if k in p:
            extras.append(f"{k}={p[k]:.0f}")
    if extras:
        print("feedback:", " ".join(extras))
    print("="*78)


def wait_after_motion_and_measure(ser: serial.Serial, label: str) -> Dict[str, Any]:
    print(f"[{label}] Waiting {NO_POLL_WAIT_S:.1f}s with NO T105 polling...")
    time.sleep(NO_POLL_WAIT_S)
    return median_pose(ser)


def main():
    a = parse_args()

    print("="*78)
    print("E4 H1 — T104 SETUP + T101 SINGLE-JOINT TRACKING")
    print("="*78)
    print(f"H1 high target XYZ = {H1_XYZ} mm, tit={H1_TIT:.6f} rad")
    print(f"IKFast BASE target     = {IK_BASE:.9f} rad")
    print(f"IKFast SHOULDER target = {IK_SHOULDER:.9f} rad")
    print(f"T104 spd={a.t104_spd}; T101 spd={a.t101_spd} steps/s; acc={a.acc}")
    print("\n[SAFETY]")
    print("- This script stays at H1 HIGH; it never descends to the table.")
    print("- Keep the full path clear and one hand near the robot power switch.")
    print("- No roarm_driver / other program may use /dev/ttyUSB0 simultaneously.")
    input("\nPress Enter when ready to open serial...")

    ser = open_serial(a.port, a.baud)

    try:
        print("[INIT] Waiting for current T105 pose...")
        p0 = get_pose(ser)
        print_pose("[CURRENT POSE]", p0)

        # ------------------------------------------------------------
        # SETUP: use T104 to reach the known safe H1 HIGH neighborhood
        # ------------------------------------------------------------
        print("\n[SETUP]")
        print("The arm is not assumed to already be near H1.")
        print("Next command will move to the known H1 HIGH target only.")
        if input("Type H1 to move to H1 HIGH with T104: ").strip().upper() != "H1":
            print("Cancelled.")
            return

        send(ser, {
            "T":104,
            "x":H1_XYZ[0],
            "y":H1_XYZ[1],
            "z":H1_XYZ[2],
            "t":H1_TIT,
            "spd":a.t104_spd,
        })

        p104 = wait_after_motion_and_measure(ser, "T104 SETUP")
        print_pose("[AFTER T104 SETUP]", p104)

        # Only allow small single-joint corrections from here.
        db = IK_BASE - float(p104["b"])
        ds = IK_SHOULDER - float(p104["s"])

        print(
            f"\nRequired BASE correction: {db:+.6f} rad "
            f"({math.degrees(db):+.3f} deg)"
        )
        print(
            f"Required SHOULDER correction: {ds:+.6f} rad "
            f"({math.degrees(ds):+.3f} deg)"
        )

        if abs(db) > MAX_BASE_CORRECTION_RAD:
            raise RuntimeError(
                f"BASE correction {db:+.4f} rad exceeds safety limit "
                f"{MAX_BASE_CORRECTION_RAD:.4f}."
            )
        if abs(ds) > MAX_SHOULDER_CORRECTION_RAD:
            raise RuntimeError(
                f"SHOULDER correction {ds:+.4f} rad exceeds safety limit "
                f"{MAX_SHOULDER_CORRECTION_RAD:.4f}."
            )

        # ------------------------------------------------------------
        # BASE T101
        # ------------------------------------------------------------
        if input("\nType BASE to command BASE only with T101: ").strip().upper() != "BASE":
            print("Stopped after T104 setup.")
            return

        send(ser, {
            "T":101,
            "joint":1,
            "rad":round(IK_BASE, 9),
            "spd":a.t101_spd,
            "acc":a.acc,
        })

        pb = wait_after_motion_and_measure(ser, "T101 BASE")
        print_pose("[AFTER T101 BASE]", pb)

        b_res = float(pb["b"]) - IK_BASE
        print(
            f"BASE residual actual-target = {b_res:+.6f} rad "
            f"({math.degrees(b_res):+.3f} deg)"
        )

        if abs(b_res) > JOINT_PASS_RAD:
            print("\n" + "="*78)
            print("[DIAGNOSIS]")
            print("BASE did NOT reach the requested T101 target.")
            print("Stop here. This is already enough to implicate joint-command/servo execution.")
            print("Do not test SHOULDER yet.")
            print("="*78)
            return

        print("[PASS] BASE reached the requested T101 target.")

        # ------------------------------------------------------------
        # SHOULDER T101
        # ------------------------------------------------------------
        if input("\nType SHOULDER to command SHOULDER only with T101: ").strip().upper() != "SHOULDER":
            print("Stopped after BASE test.")
            return

        send(ser, {
            "T":101,
            "joint":2,
            "rad":round(IK_SHOULDER, 9),
            "spd":a.t101_spd,
            "acc":a.acc,
        })

        ps = wait_after_motion_and_measure(ser, "T101 SHOULDER")
        print_pose("[AFTER T101 SHOULDER]", ps)

        s_res = float(ps["s"]) - IK_SHOULDER
        print(
            f"SHOULDER residual actual-target = {s_res:+.6f} rad "
            f"({math.degrees(s_res):+.3f} deg)"
        )

        print("\n" + "="*78)
        print("[SUMMARY]")
        print(
            f"BASE: target={IK_BASE:.6f}, actual={ps['b']:.6f}, "
            f"residual={ps['b']-IK_BASE:+.6f} rad"
        )
        print(
            f"SHOULDER: target={IK_SHOULDER:.6f}, actual={ps['s']:.6f}, "
            f"residual={ps['s']-IK_SHOULDER:+.6f} rad"
        )
        dx,dy,dz,xy,e3 = h1_errors(ps)
        print(f"H1 Cartesian: XY={xy:.3f} mm | 3D={e3:.3f} mm")
        print("="*78)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Closing serial; no automatic motion command sent.")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] serial closed.")


if __name__ == "__main__":
    main()
