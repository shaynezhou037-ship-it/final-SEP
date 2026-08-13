#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 H1 — T104 setup + T121 angle-control diagnostic

Why this version:
- T104 clearly moves the real arm.
- T101/T102 radian-direct commands did not reach their requested joint targets.
- This tests the alternative official single-joint ANGLE path (T121).

Sequence:
1) Boot-safe serial open and one fresh T105.
2) T104 -> H1 HIGH.
3) T121 BASE -> IKFast base angle (degrees).
4) If BASE tracks, T121 SHOULDER -> IKFast shoulder angle.
5) Read fresh T105 after each motion and report residuals.

H1 HIGH only; no table descent.
"""

import argparse
import json
import math
import time
import serial

H1_XYZ = (134.247166, 74.501560, -79.402225)
H1_TIT = 1.500000

IK_BASE_RAD = 0.5120438298092209
IK_SHOULDER_RAD = 0.2580689332852309
IK_BASE_DEG = math.degrees(IK_BASE_RAD)
IK_SHOULDER_DEG = math.degrees(IK_SHOULDER_RAD)

BOOT_WAIT_S = 22.0
JOINT_PASS_RAD = 0.0040

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--t104-spd", type=float, default=0.05)
    p.add_argument("--t121-spd", type=float, default=30.0)  # deg/s
    p.add_argument("--acc", type=float, default=10.0)
    return p.parse_args()

def open_serial(port, baud):
    s = serial.Serial(
        port=port, baudrate=baud, timeout=0.20, write_timeout=0.5,
        rtscts=False, dsrdtr=False
    )
    try:
        s.setDTR(False)
        s.setRTS(False)
    except Exception:
        pass
    return s

def send(ser, obj):
    text = json.dumps(obj, separators=(",", ":"))
    print("[SEND]", text)
    ser.write((text + "\n").encode("utf-8"))
    ser.flush()

def parse_t1051(line):
    i, j = line.find("{"), line.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(line[i:j+1])
    except Exception:
        return None
    if d.get("T") != 1051:
        return None
    needed = ("x","y","z","b","s","e","t","r","g")
    if not all(isinstance(d.get(k), (int,float)) for k in needed):
        return None
    return d

def flush_rx(ser, label):
    n = ser.in_waiting
    ser.reset_input_buffer()
    print(f"[{label}] flushed {n} queued byte(s)")

def one_fresh_t105(ser, timeout=8.0):
    flush_rx(ser, "T105 PRE-FLUSH")
    send(ser, {"T":105})
    end = time.time() + timeout
    while time.time() < end:
        raw = ser.readline()
        if not raw:
            continue
        p = parse_t1051(raw.decode("utf-8", errors="replace"))
        if p:
            return p
    raise RuntimeError("No fresh T1051 received.")

def h1_err(p):
    dx = p["x"] - H1_XYZ[0]
    dy = p["y"] - H1_XYZ[1]
    dz = p["z"] - H1_XYZ[2]
    return dx, dy, dz, math.hypot(dx,dy), math.sqrt(dx*dx+dy*dy+dz*dz)

def print_pose(title, p):
    dx,dy,dz,xy,e3 = h1_err(p)
    print("\n" + "="*78)
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
    print("="*78)

def main():
    a = parse_args()
    print("="*78)
    print("E4 H1 — T104 SETUP + T121 ANGLE CONTROL")
    print("="*78)
    print(f"IKFast BASE:     {IK_BASE_RAD:.9f} rad = {IK_BASE_DEG:.4f} deg")
    print(f"IKFast SHOULDER: {IK_SHOULDER_RAD:.9f} rad = {IK_SHOULDER_DEG:.4f} deg")
    print("\n[SAFETY]")
    print("- H1 HIGH only; no table descent.")
    print("- No roarm_driver / other program may use /dev/ttyUSB0.")
    print("- User confirmation before each motion.")
    input("\nPress Enter to open serial...")

    ser = open_serial(a.port, a.baud)
    try:
        print(f"[BOOT] Waiting {BOOT_WAIT_S:.0f}s with NO commands...")
        time.sleep(BOOT_WAIT_S)
        flush_rx(ser, "BOOT FLUSH")
        p0 = one_fresh_t105(ser)
        print_pose("[FRESH START]", p0)

        if input("\nType H1 to move to H1 HIGH using T104: ").strip().upper() != "H1":
            return
        flush_rx(ser, "PRE-T104 FLUSH")
        send(ser, {
            "T":104,
            "x":H1_XYZ[0], "y":H1_XYZ[1], "z":H1_XYZ[2],
            "t":H1_TIT, "spd":a.t104_spd
        })
        print("[T104] Waiting 12s with no polling...")
        time.sleep(12.0)
        p104 = one_fresh_t105(ser)
        print_pose("[AFTER T104]", p104)

        _,_,_,_,e104 = h1_err(p104)
        if e104 > 40.0:
            print("[STOP] T104 did not reach H1 neighborhood.")
            return

        db = IK_BASE_RAD - p104["b"]
        ds = IK_SHOULDER_RAD - p104["s"]
        print(f"\nBASE correction needed: {db:+.6f} rad = {math.degrees(db):+.3f} deg")
        print(f"SHOULDER correction needed: {ds:+.6f} rad = {math.degrees(ds):+.3f} deg")

        if abs(db) > 0.12 or abs(ds) > 0.12:
            print("[STOP] correction unexpectedly large.")
            return

        if input("\nType BASE to send T121 base angle: ").strip().upper() != "BASE":
            return
        flush_rx(ser, "PRE-BASE FLUSH")
        send(ser, {
            "T":121,
            "joint":1,
            "angle":round(IK_BASE_DEG, 6),
            "spd":a.t121_spd,
            "acc":a.acc
        })
        print("[BASE] Waiting 4s with no polling...")
        time.sleep(4.0)
        pb = one_fresh_t105(ser)
        print_pose("[AFTER T121 BASE]", pb)
        br = pb["b"] - IK_BASE_RAD
        print(f"BASE residual = {br:+.6f} rad = {math.degrees(br):+.3f} deg")

        if abs(br) > JOINT_PASS_RAD:
            print("\n[RESULT] T121 BASE also failed to reach target.")
            print("Then the issue is below the T101/T102 command family; inspect servo/torque/control state.")
            return

        print("[PASS] T121 BASE reached the IKFast target.")

        if input("\nType SHOULDER to send T121 shoulder angle: ").strip().upper() != "SHOULDER":
            return
        flush_rx(ser, "PRE-SHOULDER FLUSH")
        send(ser, {
            "T":121,
            "joint":2,
            "angle":round(IK_SHOULDER_DEG, 6),
            "spd":a.t121_spd,
            "acc":a.acc
        })
        print("[SHOULDER] Waiting 4s with no polling...")
        time.sleep(4.0)
        ps = one_fresh_t105(ser)
        print_pose("[AFTER T121 SHOULDER]", ps)
        sr = ps["s"] - IK_SHOULDER_RAD
        print(f"SHOULDER residual = {sr:+.6f} rad = {math.degrees(sr):+.3f} deg")

        dx,dy,dz,xy,e3 = h1_err(ps)
        print("\n" + "="*78)
        print("[SUMMARY]")
        print(f"BASE residual     = {ps['b']-IK_BASE_RAD:+.6f} rad")
        print(f"SHOULDER residual = {ps['s']-IK_SHOULDER_RAD:+.6f} rad")
        print(f"H1 Cartesian      = XY {xy:.3f} mm | 3D {e3:.3f} mm")
        print("="*78)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Closing serial.")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] serial closed.")

if __name__ == "__main__":
    main()
