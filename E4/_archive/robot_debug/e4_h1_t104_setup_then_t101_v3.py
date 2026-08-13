#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 H1 — T104 setup + T101 single-joint tracking V3

Fix over V2:
- No unbounded "drain until quiet" loop.
- Uses serial.reset_input_buffer() to clear stale host RX immediately.
- Sends exactly one T105 request at a time.
- No motion command is sent before user confirmation.

Sequence:
1) Open serial, wait for controller reboot/startup.
2) Flush stale RX, request one fresh T105.
3) User confirms H1 -> send T104 to H1 HIGH.
4) Get fresh T105 after T104.
5) User confirms BASE -> send T101 base target.
6) If base tracks, user confirms SHOULDER -> send T101 shoulder target.
"""

from __future__ import annotations
import argparse, json, math, time
from typing import Any, Dict, Optional
import serial

H1_XYZ = (134.247166, 74.501560, -79.402225)
H1_TIT = 1.500000

IK_BASE = 0.5120438298092209
IK_SHOULDER = 0.2580689332852309

BOOT_WAIT_S = 22.0
DEFAULT_T104_SPD = 0.05
DEFAULT_T101_SPD = 100
DEFAULT_ACC = 10

MAX_BASE_CORRECTION_RAD = 0.12
MAX_SHOULDER_CORRECTION_RAD = 0.12
JOINT_PASS_RAD = 0.0040

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--boot-wait", type=float, default=BOOT_WAIT_S)
    p.add_argument("--t104-spd", type=float, default=DEFAULT_T104_SPD)
    p.add_argument("--t101-spd", type=int, default=DEFAULT_T101_SPD)
    p.add_argument("--acc", type=int, default=DEFAULT_ACC)
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

def send(ser, obj: Dict[str, Any]):
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

def valid_pose(p):
    return p is not None and all(
        isinstance(p.get(k), (int, float))
        for k in ("x","y","z","b","s","e","t","r","g")
    )

def flush_rx(ser, label="RX"):
    # Immediate host-side buffer clear: cannot hang.
    waiting = ser.in_waiting
    ser.reset_input_buffer()
    print(f"[{label}] flushed {waiting} queued byte(s)")

def one_fresh_t105(ser, timeout_s=6.0):
    flush_rx(ser, "T105 PRE-FLUSH")
    send(ser, {"T":105})
    end = time.time() + timeout_s
    while time.time() < end:
        raw = ser.readline()
        if not raw:
            continue
        p = parse_t1051(raw.decode("utf-8", errors="replace"))
        if valid_pose(p):
            return p
    raise RuntimeError(f"No valid fresh T1051 within {timeout_s:.1f}s.")

def h1_errors(p):
    dx = float(p["x"]) - H1_XYZ[0]
    dy = float(p["y"]) - H1_XYZ[1]
    dz = float(p["z"]) - H1_XYZ[2]
    xy = math.hypot(dx, dy)
    e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx,dy,dz,xy,e3

def print_pose(title, p):
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
    print("="*78)

def main():
    a = parse_args()
    print("="*78)
    print("E4 H1 — T104 SETUP + T101 TRACKING V3")
    print("="*78)
    print("V3 fix: bounded startup handling; no 'drain until quiet' loop.")
    print(f"H1 HIGH = {H1_XYZ} mm, tit={H1_TIT:.6f}")
    print(f"IKFast base={IK_BASE:.9f}, shoulder={IK_SHOULDER:.9f}")
    print("\n[SAFETY]")
    print("- H1 HIGH only; no table descent.")
    print("- No roarm_driver or other program may use /dev/ttyUSB0 simultaneously.")
    print("- Keep one hand near the power switch.")
    input("\nPress Enter to open serial...")

    ser = open_serial(a.port, a.baud)
    try:
        print(f"[BOOT] Waiting {a.boot_wait:.0f}s with NO commands...")
        t0 = time.time()
        while time.time() - t0 < a.boot_wait:
            remain = int(math.ceil(a.boot_wait - (time.time()-t0)))
            if remain in (20,15,10,5,3,2,1):
                print(f"[BOOT] {remain}s")
            time.sleep(0.25)

        # Immediate buffer reset; this is the core V3 fix.
        flush_rx(ser, "BOOT FLUSH")
        time.sleep(0.5)

        p0 = one_fresh_t105(ser, timeout_s=8.0)
        print_pose("[FRESH START POSE]", p0)

        if input("\nType H1 to send T104 to H1 HIGH: ").strip().upper() != "H1":
            print("Cancelled.")
            return

        flush_rx(ser, "PRE-T104 FLUSH")
        send(ser, {
            "T":104,
            "x":H1_XYZ[0], "y":H1_XYZ[1], "z":H1_XYZ[2],
            "t":H1_TIT, "spd":a.t104_spd
        })

        # T104 is expected to be blocking in firmware. Do not spam T105.
        print("[T104] Waiting 12s with NO polling...")
        time.sleep(12.0)

        p104 = one_fresh_t105(ser, timeout_s=8.0)
        print_pose("[AFTER T104 — FRESH FEEDBACK]", p104)

        _,_,_,_,e104 = h1_errors(p104)
        if e104 > 40.0:
            print("\n[STOP] T104 did not reach the H1 neighborhood (>40 mm 3D error).")
            print("Do not continue to T101.")
            return

        db = IK_BASE - float(p104["b"])
        ds = IK_SHOULDER - float(p104["s"])
        print(
            f"\nNeeded BASE correction: {db:+.6f} rad "
            f"({math.degrees(db):+.3f} deg)"
        )
        print(
            f"Needed SHOULDER correction: {ds:+.6f} rad "
            f"({math.degrees(ds):+.3f} deg)"
        )

        if abs(db) > MAX_BASE_CORRECTION_RAD or abs(ds) > MAX_SHOULDER_CORRECTION_RAD:
            print("[STOP] Required correction is unexpectedly large; refusing T101.")
            return

        if input("\nType BASE to test direct T101 base tracking: ").strip().upper() != "BASE":
            print("Stopped after T104.")
            return

        flush_rx(ser, "PRE-BASE FLUSH")
        send(ser, {
            "T":101, "joint":1, "rad":round(IK_BASE, 9),
            "spd":a.t101_spd, "acc":a.acc
        })
        print("[BASE] Waiting 4s with NO polling...")
        time.sleep(4.0)

        pb = one_fresh_t105(ser, timeout_s=8.0)
        print_pose("[AFTER T101 BASE — FRESH FEEDBACK]", pb)

        b_res = float(pb["b"]) - IK_BASE
        print(
            f"BASE residual actual-target = {b_res:+.6f} rad "
            f"({math.degrees(b_res):+.3f} deg)"
        )

        if abs(b_res) > JOINT_PASS_RAD:
            print("\n[DIAGNOSIS]")
            print("BASE did NOT reach the T101 target.")
            print("This implicates joint-command / servo execution rather than IKFast.")
            return

        print("[PASS] BASE tracked T101.")

        if input("\nType SHOULDER to test direct T101 shoulder tracking: ").strip().upper() != "SHOULDER":
            print("Stopped after BASE.")
            return

        flush_rx(ser, "PRE-SHOULDER FLUSH")
        send(ser, {
            "T":101, "joint":2, "rad":round(IK_SHOULDER, 9),
            "spd":a.t101_spd, "acc":a.acc
        })
        print("[SHOULDER] Waiting 4s with NO polling...")
        time.sleep(4.0)

        ps = one_fresh_t105(ser, timeout_s=8.0)
        print_pose("[AFTER T101 SHOULDER — FRESH FEEDBACK]", ps)

        s_res = float(ps["s"]) - IK_SHOULDER
        print(
            f"SHOULDER residual actual-target = {s_res:+.6f} rad "
            f"({math.degrees(s_res):+.3f} deg)"
        )

        dx,dy,dz,xy,e3 = h1_errors(ps)
        print("\n" + "="*78)
        print("[SUMMARY]")
        print(
            f"BASE target={IK_BASE:.6f}, actual={ps['b']:.6f}, "
            f"residual={ps['b']-IK_BASE:+.6f} rad"
        )
        print(
            f"SHOULDER target={IK_SHOULDER:.6f}, actual={ps['s']:.6f}, "
            f"residual={ps['s']-IK_SHOULDER:+.6f} rad"
        )
        print(f"H1 Cartesian after both: XY={xy:.3f} mm, 3D={e3:.3f} mm")
        print("="*78)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Closing serial. No automatic motion command sent.")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] serial closed.")

if __name__ == "__main__":
    main()
