#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 H1 T104 setup -> T101 joint tracking, V2
Fixes stale T105 feedback caused by spamming T105 during controller reboot.

Key changes:
- After opening serial, wait 22 s WITHOUT sending commands.
- Drain RX buffer after boot.
- Use ONE T105 request at a time.
- Drain RX before every motion.
- After T104, queue only ONE T105 request and wait for its reply.
- T101 tests wait 3 s with no polling, then read a fresh single T105.

No table descent: H1 HIGH only.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from typing import Any, Dict, Optional

import serial

H1_XYZ = (134.247166, 74.501560, -79.402225)
H1_TIT = 1.500000

IK_BASE = 0.5120438298092209
IK_SHOULDER = 0.2580689332852309

BOOT_WAIT_S = 22.0
T104_REPLY_TIMEOUT_S = 45.0
T101_WAIT_S = 3.0

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
    p.add_argument("--t104-spd", type=float, default=DEFAULT_T104_SPD)
    p.add_argument("--t101-spd", type=int, default=DEFAULT_T101_SPD)
    p.add_argument("--acc", type=int, default=DEFAULT_ACC)
    p.add_argument("--boot-wait", type=float, default=BOOT_WAIT_S)
    return p.parse_args()


def open_serial(port, baud):
    s = serial.Serial()
    s.port = port
    s.baudrate = baud
    s.timeout = 0.2
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
    return s


def send(ser, obj):
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
        for k in ("x", "y", "z", "b", "s", "e", "t", "r", "g")
    )


def drain_rx(ser, quiet_s=0.5):
    """Drain host RX until no bytes arrive for quiet_s."""
    end_quiet = time.time() + quiet_s
    count = 0
    while time.time() < end_quiet:
        raw = ser.readline()
        if raw:
            count += 1
            end_quiet = time.time() + quiet_s
    if count:
        print(f"[DRAIN] discarded {count} old serial line(s)")


def one_fresh_t105(ser, timeout_s=5.0):
    """
    Clear host-side stale RX, send exactly ONE T105, then wait for ONE T1051.
    Never floods the controller with queued T105 requests.
    """
    drain_rx(ser, 0.3)
    send(ser, {"T": 105})

    end = time.time() + timeout_s
    while time.time() < end:
        raw = ser.readline()
        if not raw:
            continue
        p = parse_t1051(raw.decode("utf-8", errors="replace"))
        if valid_pose(p):
            return p
    raise RuntimeError(f"No fresh T1051 within {timeout_s:.1f}s.")


def wait_boot_then_pose(ser, wait_s):
    print(
        f"[BOOT] Serial open may reset the controller. "
        f"Waiting {wait_s:.0f}s with NO commands..."
    )
    for remaining in range(int(wait_s), 0, -1):
        if remaining % 5 == 0 or remaining <= 3:
            print(f"[BOOT] {remaining}s")
        time.sleep(1.0)

    print("[BOOT] draining any startup output...")
    drain_rx(ser, 1.0)

    # One request at a time. If the controller is still not ready, wait and retry,
    # but never stack many requests.
    for attempt in range(1, 5):
        try:
            p = one_fresh_t105(ser, timeout_s=4.0)
            print(f"[BOOT] fresh T105 received on attempt {attempt}")
            return p
        except RuntimeError:
            if attempt == 4:
                raise
            print("[BOOT] controller not ready; waiting 3s before one retry...")
            time.sleep(3.0)


def h1_errors(p):
    dx = float(p["x"]) - H1_XYZ[0]
    dy = float(p["y"]) - H1_XYZ[1]
    dz = float(p["z"]) - H1_XYZ[2]
    xy = math.hypot(dx, dy)
    e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx, dy, dz, xy, e3


def print_pose(title, p):
    dx, dy, dz, xy, e3 = h1_errors(p)
    print("\n" + "=" * 78)
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
    if all(k in p for k in ("tB", "tS", "tE", "tT", "tR")):
        print(
            "joint load: "
            f"tB={p['tB']} tS={p['tS']} tE={p['tE']} "
            f"tT={p['tT']} tR={p['tR']}"
        )
    if all(k in p for k in ("torswitchB", "torswitchS", "torswitchE", "torswitchT", "torswitchR")):
        print(
            "torque lock: "
            f"B={p['torswitchB']} S={p['torswitchS']} E={p['torswitchE']} "
            f"T={p['torswitchT']} R={p['torswitchR']}"
        )
    print("=" * 78)


def main():
    a = parse_args()

    print("=" * 78)
    print("E4 H1 — T104 SETUP + T101 TRACKING V2")
    print("=" * 78)
    print("Fix: no T105 flooding during reboot; only fresh one-request/one-reply feedback.")
    print(f"H1 HIGH = {H1_XYZ} mm, tit={H1_TIT:.6f}")
    print(f"IKFast base={IK_BASE:.9f}, shoulder={IK_SHOULDER:.9f}")
    print("\n[SAFETY]")
    print("- H1 HIGH only; no table descent.")
    print("- No roarm_driver or other process may use /dev/ttyUSB0.")
    print("- Keep one hand near the power switch.")
    input("\nPress Enter to open serial...")

    ser = open_serial(a.port, a.baud)

    try:
        p0 = wait_boot_then_pose(ser, a.boot_wait)
        print_pose("[FRESH START POSE]", p0)

        print("\n[SETUP]")
        if input("Type H1 to send the known H1 HIGH T104 command: ").strip().upper() != "H1":
            print("Cancelled.")
            return

        # Ensure no stale feedback exists before motion.
        drain_rx(ser, 0.5)

        send(ser, {
            "T": 104,
            "x": H1_XYZ[0],
            "y": H1_XYZ[1],
            "z": H1_XYZ[2],
            "t": H1_TIT,
            "spd": a.t104_spd,
        })

        print(
            "[T104] Sent. Waiting 1s, then sending exactly ONE T105 request. "
            "Because T104 is blocking in firmware, its reply may not arrive until "
            "the move finishes."
        )
        time.sleep(1.0)

        # Do NOT drain here: there should be no pre-motion requests left.
        send(ser, {"T": 105})
        end = time.time() + T104_REPLY_TIMEOUT_S
        p104 = None
        while time.time() < end:
            raw = ser.readline()
            if not raw:
                continue
            p = parse_t1051(raw.decode("utf-8", errors="replace"))
            if valid_pose(p):
                p104 = p
                break

        if p104 is None:
            raise RuntimeError("No T1051 after T104 within 45 s.")

        # Give mechanics a moment, then get one additional fresh confirmation.
        time.sleep(1.0)
        p104 = one_fresh_t105(ser, timeout_s=5.0)
        print_pose("[AFTER T104 — FRESH FEEDBACK]", p104)

        _, _, _, _, e104 = h1_errors(p104)
        if e104 > 40.0:
            print(
                "\n[T104 DID NOT REACH H1 NEIGHBORHOOD]"
                "\nDo NOT continue to T101."
                "\nThis would be a real T104/setup failure, not stale feedback."
            )
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
            print("[REFUSE] Joint correction unexpectedly large; stop.")
            return

        # ------------------------------------------------------------
        # T101 BASE
        # ------------------------------------------------------------
        if input("\nType BASE to test T101 base tracking: ").strip().upper() != "BASE":
            print("Stopped after T104.")
            return

        drain_rx(ser, 0.3)
        send(ser, {
            "T": 101,
            "joint": 1,
            "rad": round(IK_BASE, 9),
            "spd": a.t101_spd,
            "acc": a.acc,
        })
        print(f"[BASE] waiting {T101_WAIT_S:.1f}s with NO polling...")
        time.sleep(T101_WAIT_S)

        pb = one_fresh_t105(ser, timeout_s=5.0)
        print_pose("[AFTER T101 BASE — FRESH FEEDBACK]", pb)

        b_res = float(pb["b"]) - IK_BASE
        print(
            f"BASE residual actual-target = {b_res:+.6f} rad "
            f"({math.degrees(b_res):+.3f} deg)"
        )

        if abs(b_res) > JOINT_PASS_RAD:
            print("\n[DIAGNOSIS]")
            print("BASE failed to reach the direct T101 target.")
            print("This points to joint-command / servo execution rather than IKFast.")
            return

        print("[PASS] BASE tracked T101.")

        # ------------------------------------------------------------
        # T101 SHOULDER
        # ------------------------------------------------------------
        if input("\nType SHOULDER to test T101 shoulder tracking: ").strip().upper() != "SHOULDER":
            print("Stopped after BASE.")
            return

        drain_rx(ser, 0.3)
        send(ser, {
            "T": 101,
            "joint": 2,
            "rad": round(IK_SHOULDER, 9),
            "spd": a.t101_spd,
            "acc": a.acc,
        })
        print(f"[SHOULDER] waiting {T101_WAIT_S:.1f}s with NO polling...")
        time.sleep(T101_WAIT_S)

        ps = one_fresh_t105(ser, timeout_s=5.0)
        print_pose("[AFTER T101 SHOULDER — FRESH FEEDBACK]", ps)

        s_res = float(ps["s"]) - IK_SHOULDER
        print(
            f"SHOULDER residual actual-target = {s_res:+.6f} rad "
            f"({math.degrees(s_res):+.3f} deg)"
        )

        print("\n" + "=" * 78)
        print("[SUMMARY]")
        print(
            f"BASE target={IK_BASE:.6f}, actual={ps['b']:.6f}, "
            f"residual={ps['b']-IK_BASE:+.6f} rad"
        )
        print(
            f"SHOULDER target={IK_SHOULDER:.6f}, actual={ps['s']:.6f}, "
            f"residual={ps['s']-IK_SHOULDER:+.6f} rad"
        )
        dx, dy, dz, xy, e3 = h1_errors(ps)
        print(f"H1 Cartesian after both: XY={xy:.3f} mm, 3D={e3:.3f} mm")
        print("=" * 78)

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
