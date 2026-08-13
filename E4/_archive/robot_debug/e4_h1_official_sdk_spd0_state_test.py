#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 H1 — official SDK T101 with spd=0 + full controller-state capture

Purpose:
- Test the exact T101-style parameters shown in Waveshare's control example:
  spd=0, acc=10.
- Capture full T1051 state before and after, including torque switches, loads,
  and supply voltage.
- Change only one control variable from the previous official-SDK test:
  joint command speed/acceleration.

Safety:
- H1 HIGH only; no table descent.
- Confirmation before every motion.
- No roarm_driver / MoveIt / other serial user may own /dev/ttyUSB0.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import time
from typing import Any, Dict, Optional

from roarm_sdk.roarm import roarm

H1_XYZ = (134.247166, 74.501560, -79.402225)
H1_TIT = 1.500000

IK_BASE = 0.5120438298092209

BOOT_WAIT_S = 22.0
T104_WAIT_S = 12.0
JOINT_WAIT_S = 4.0

SDK_SPEED = 0
SDK_ACC = 10

MAX_BASE_CORRECTION_RAD = 0.12
PASS_RAD = 0.0040


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--t104-spd", type=float, default=0.05)
    return p.parse_args()


def offline_sdk_bytes():
    gen = importlib.import_module("roarm_sdk.generate")
    common = importlib.import_module("roarm_sdk.common")
    cg = gen.CommandGenerator(roarm_type="roarm_m3", debug=False)

    cmd = cg._mesg(
        common.JsonCmd.JOINT_RADIAN_CTRL,
        1,
        IK_BASE,
        SDK_SPEED,
        SDK_ACC,
    )
    print("=" * 80)
    print("[OFFLINE SDK SERIALIZATION]")
    print(cmd.decode("utf-8").rstrip())
    print("=" * 80)


def send_raw(ser, obj: Dict[str, Any]):
    text = json.dumps(obj, separators=(",", ":"))
    ser.reset_input_buffer()
    print("[RAW SEND]", text)
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
    if not all(isinstance(d.get(k), (int, float)) for k in ("x","y","z","b","s","e","t","r","g")):
        return None
    return d


def fresh_t105(ser, timeout_s=8.0) -> Dict[str, Any]:
    n = ser.in_waiting
    ser.reset_input_buffer()
    print(f"[T105 PRE-FLUSH] flushed {n} queued byte(s)")
    ser.write(b'{"T":105}\n')
    ser.flush()
    print('[RAW SEND] {"T":105}')

    end = time.time() + timeout_s
    while time.time() < end:
        raw = ser.readline()
        if not raw:
            continue
        p = parse_t1051(raw.decode("utf-8", errors="replace"))
        if p is not None:
            return p
    raise RuntimeError("No valid fresh T1051 received.")


def h1_err(p):
    dx = p["x"] - H1_XYZ[0]
    dy = p["y"] - H1_XYZ[1]
    dz = p["z"] - H1_XYZ[2]
    xy = math.hypot(dx, dy)
    e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx,dy,dz,xy,e3


def print_full_state(title: str, p: Dict[str, Any]):
    dx,dy,dz,xy,e3 = h1_err(p)
    print("\n" + "=" * 80)
    print(title)
    print(
        f"XYZ=({p['x']:.3f},{p['y']:.3f},{p['z']:.3f}) mm | "
        f"H1 dX={dx:+.3f} dY={dy:+.3f} dZ={dz:+.3f} "
        f"XY={xy:.3f} 3D={e3:.3f} mm"
    )
    print(
        f"b={p['b']:.6f} s={p['s']:.6f} e={p['e']:.6f} "
        f"t={p['t']:.6f} r={p['r']:.6f} g={p['g']:.6f}"
    )

    torque_keys = ("torswitchB","torswitchS","torswitchE","torswitchT","torswitchR","torswitchG")
    load_keys = ("tB","tS","tE","tT","tR","tG")

    torque_text = " ".join(f"{k}={p.get(k, 'NA')}" for k in torque_keys)
    load_text = " ".join(f"{k}={p.get(k, 'NA')}" for k in load_keys)

    print("TORQUE:", torque_text)
    print("LOADS: ", load_text)

    v = p.get("v", None)
    if isinstance(v, (int, float)):
        print(f"VOLTAGE raw={v} -> {v * 0.01:.2f} V")
    else:
        print("VOLTAGE: NA")

    print("=" * 80)


def main():
    a = parse_args()
    offline_sdk_bytes()

    print("\n[SAFETY]")
    print("- H1 HIGH only.")
    print("- This test changes only T101 speed/acc to spd=0, acc=10.")
    print("- Full T1051 torque/load/voltage state is captured.")
    print("- No other process may use /dev/ttyUSB0.")
    input("\nPress Enter to open official SDK serial...")

    arm = roarm(
        roarm_type="roarm_m3",
        port=a.port,
        baudrate=a.baud,
        timeout=0.1,
        debug=False,
        thread_lock=True,
    )
    ser = arm._serial_port

    try:
        print(f"[BOOT] Waiting {BOOT_WAIT_S:.0f}s with NO commands...")
        time.sleep(BOOT_WAIT_S)
        n = ser.in_waiting
        ser.reset_input_buffer()
        print(f"[BOOT FLUSH] flushed {n} queued byte(s)")

        p0 = fresh_t105(ser)
        print_full_state("[FRESH START STATE]", p0)

        if input("\nType H1 to move to H1 HIGH: ").strip().upper() != "H1":
            print("Cancelled.")
            return

        send_raw(ser, {
            "T":104,
            "x":H1_XYZ[0],
            "y":H1_XYZ[1],
            "z":H1_XYZ[2],
            "t":H1_TIT,
            "spd":a.t104_spd,
        })
        print(f"[T104] Waiting {T104_WAIT_S:.0f}s with NO polling...")
        time.sleep(T104_WAIT_S)

        p104 = fresh_t105(ser)
        print_full_state("[AFTER T104 — FULL STATE]", p104)

        db = IK_BASE - p104["b"]
        print(
            f"\nBASE correction required = {db:+.6f} rad "
            f"({math.degrees(db):+.3f} deg)"
        )

        if abs(db) > MAX_BASE_CORRECTION_RAD:
            print("[STOP] BASE correction unexpectedly large.")
            return

        if input(
            "\nType SDKBASE0 to call official SDK T101 with spd=0, acc=10: "
        ).strip().upper() != "SDKBASE0":
            print("Stopped after T104.")
            return

        print(
            f"[SDK CALL] joint_radian_ctrl("
            f"joint=1, radian={IK_BASE:.9f}, speed={SDK_SPEED}, acc={SDK_ACC})"
        )
        ret = arm.joint_radian_ctrl(
            joint=1,
            radian=IK_BASE,
            speed=SDK_SPEED,
            acc=SDK_ACC,
        )
        print("[SDK RETURN]", ret)

        print(f"[T101 spd=0] Waiting {JOINT_WAIT_S:.0f}s with NO polling...")
        time.sleep(JOINT_WAIT_S)

        p1 = fresh_t105(ser)
        print_full_state("[AFTER OFFICIAL SDK T101 spd=0 — FULL STATE]", p1)

        res = p1["b"] - IK_BASE
        moved = p1["b"] - p104["b"]

        print("\n" + "=" * 80)
        print("[RESULT]")
        print(
            f"BASE before T101 = {p104['b']:.9f} rad\n"
            f"BASE after T101  = {p1['b']:.9f} rad\n"
            f"BASE movement    = {moved:+.9f} rad ({math.degrees(moved):+.4f} deg)\n"
            f"Target residual  = {res:+.9f} rad ({math.degrees(res):+.4f} deg)"
        )

        if abs(res) <= PASS_RAD:
            print("PASS: official SDK T101 with spd=0 reached the target.")
        else:
            print("FAIL: official SDK T101 with spd=0 still did not reach the target.")
            print("At this point the next diagnostic should move below the SDK layer.")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] serial closed.")


if __name__ == "__main__":
    main()
