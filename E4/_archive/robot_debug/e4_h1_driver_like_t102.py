#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 H1 — test the SAME joint-control pattern used by the official ROS driver.

Stages
------
1) T104 -> known H1 HIGH setup pose.
2) T102 ONE-SHOT using the official driver's parameters: spd=1000, acc=50.
3) If needed, T102 STREAM: resend the same joint target at 10 Hz for 3 s,
   approximating the repeated /joint_states -> roarm_driver behavior.
4) Fresh T105 after each stage; compare joint and Cartesian residuals.

Safety
------
- H1 HIGH only; no table descent.
- User confirmation before every motion stage.
- Refuses if the required IKFast joint correction is unexpectedly large.
- No T105 polling during T102 motion/stream.
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

IK = {
    "base": 0.5120438298092209,
    "shoulder": 0.2580689332852309,
    "elbow": 2.4105797921381840,
    "wrist": 0.4021476011149847,
    "roll": -0.0000000007641365,
}

BOOT_WAIT_S = 22.0
T104_WAIT_S = 12.0

OFFICIAL_DRIVER_SPD = 1000
OFFICIAL_DRIVER_ACC = 50

STREAM_HZ = 10.0
STREAM_DURATION_S = 3.0

MAX_CORRECTION_RAD = 0.12
JOINT_PASS_RAD = 0.0040


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--t104-spd", type=float, default=0.05)
    return p.parse_args()


def open_serial(port: str, baud: int) -> serial.Serial:
    s = serial.Serial(
        port=port,
        baudrate=baud,
        timeout=0.20,
        write_timeout=0.5,
        rtscts=False,
        dsrdtr=False,
    )
    try:
        s.setDTR(False)
        s.setRTS(False)
    except Exception:
        pass
    return s


def send(ser: serial.Serial, obj: Dict[str, Any], verbose=True):
    text = json.dumps(obj, separators=(",", ":"))
    if verbose:
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
    if d.get("T") != 1051:
        return None
    needed = ("x","y","z","b","s","e","t","r","g")
    if not all(isinstance(d.get(k), (int, float)) for k in needed):
        return None
    return d


def flush_rx(ser: serial.Serial, label: str):
    n = ser.in_waiting
    ser.reset_input_buffer()
    print(f"[{label}] flushed {n} queued byte(s)")


def fresh_t105(ser: serial.Serial, timeout=8.0) -> Dict[str, Any]:
    flush_rx(ser, "T105 PRE-FLUSH")
    send(ser, {"T":105})
    end = time.time() + timeout
    while time.time() < end:
        raw = ser.readline()
        if not raw:
            continue
        p = parse_t1051(raw.decode("utf-8", errors="replace"))
        if p is not None:
            return p
    raise RuntimeError("No fresh T1051 received.")


def h1_error(p: Dict[str, Any]):
    dx = p["x"] - H1_XYZ[0]
    dy = p["y"] - H1_XYZ[1]
    dz = p["z"] - H1_XYZ[2]
    xy = math.hypot(dx, dy)
    e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx, dy, dz, xy, e3


def joint_residuals(p: Dict[str, Any]):
    return {
        "base": p["b"] - IK["base"],
        "shoulder": p["s"] - IK["shoulder"],
        "elbow": p["e"] - IK["elbow"],
        "wrist": p["t"] - IK["wrist"],
        "roll": p["r"] - IK["roll"],
    }


def print_pose(title: str, p: Dict[str, Any]):
    dx,dy,dz,xy,e3 = h1_error(p)
    jr = joint_residuals(p)
    print("\n" + "="*80)
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
    print(
        "joint residual actual-IK: "
        f"db={jr['base']:+.6f} ds={jr['shoulder']:+.6f} "
        f"de={jr['elbow']:+.6f} dt={jr['wrist']:+.6f} "
        f"dr={jr['roll']:+.6f} rad"
    )
    print("="*80)


def build_t102(preserve_g: float):
    return {
        "T":102,
        "base":IK["base"],
        "shoulder":IK["shoulder"],
        "elbow":IK["elbow"],
        "wrist":IK["wrist"],
        "roll":IK["roll"],
        "hand":preserve_g,
        "spd":OFFICIAL_DRIVER_SPD,
        "acc":OFFICIAL_DRIVER_ACC,
    }


def max_required_delta(p: Dict[str, Any]) -> float:
    vals = [
        abs(IK["base"] - p["b"]),
        abs(IK["shoulder"] - p["s"]),
        abs(IK["elbow"] - p["e"]),
        abs(IK["wrist"] - p["t"]),
        abs(IK["roll"] - p["r"]),
    ]
    return max(vals)


def base_residual(p):
    return p["b"] - IK["base"]


def main():
    a = parse_args()

    print("="*80)
    print("E4 H1 — OFFICIAL-DRIVER-LIKE T102 TEST")
    print("="*80)
    print(f"T102 parameters: spd={OFFICIAL_DRIVER_SPD}, acc={OFFICIAL_DRIVER_ACC}")
    print(f"Optional stream: {STREAM_HZ:.1f} Hz for {STREAM_DURATION_S:.1f} s")
    print("\n[SAFETY]")
    print("- H1 HIGH only; no table descent.")
    print("- No roarm_driver / MoveIt / other program may use /dev/ttyUSB0.")
    print("- Confirmation required before T104, T102 one-shot, and T102 stream.")
    input("\nPress Enter to open serial...")

    ser = open_serial(a.port, a.baud)
    try:
        print(f"[BOOT] Waiting {BOOT_WAIT_S:.0f}s with NO commands...")
        time.sleep(BOOT_WAIT_S)
        flush_rx(ser, "BOOT FLUSH")
        p0 = fresh_t105(ser)
        print_pose("[FRESH START]", p0)

        if input("\nType H1 to move to H1 HIGH using T104: ").strip().upper() != "H1":
            print("Cancelled.")
            return

        flush_rx(ser, "PRE-T104 FLUSH")
        send(ser, {
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
        print_pose("[AFTER T104]", p104)

        _,_,_,_,e104 = h1_error(p104)
        if e104 > 40.0:
            print("[STOP] T104 did not reach H1 neighborhood.")
            return

        max_delta = max_required_delta(p104)
        print(
            f"\nLargest requested joint correction = {max_delta:.6f} rad "
            f"({math.degrees(max_delta):.3f} deg)"
        )
        if max_delta > MAX_CORRECTION_RAD:
            print("[STOP] Correction unexpectedly large; refusing joint test.")
            return

        t102 = build_t102(float(p104["g"]))

        # ------------------------------------------------------------
        # Stage 1: ONE-SHOT exact official driver speed/acc
        # ------------------------------------------------------------
        print("\n[T102 ONE-SHOT PREVIEW]")
        print(json.dumps(t102, indent=2))
        if input("Type ONE to send one T102 command: ").strip().upper() != "ONE":
            print("Stopped after T104.")
            return

        flush_rx(ser, "PRE-ONE FLUSH")
        send(ser, t102)
        print("[ONE] Waiting 3s with NO polling...")
        time.sleep(3.0)
        pone = fresh_t105(ser)
        print_pose("[AFTER T102 ONE-SHOT]", pone)

        br_one = abs(base_residual(pone))
        if br_one <= JOINT_PASS_RAD:
            print("\n[PASS] One-shot T102 reached the IKFast base target.")
            print("No streaming test is necessary.")
            return

        # ------------------------------------------------------------
        # Stage 2: repeated T102 like /joint_states -> roarm_driver
        # ------------------------------------------------------------
        print(
            "\nOne-shot did not reach the target. "
            "Next stage repeats the SAME small target, like the ROS driver receives "
            "repeated joint_states callbacks."
        )
        if input("Type STREAM to run the repeated T102 test: ").strip().upper() != "STREAM":
            print("Stopped after one-shot.")
            return

        # Preserve current gripper.
        t102["hand"] = float(pone["g"])
        flush_rx(ser, "PRE-STREAM FLUSH")

        period = 1.0 / STREAM_HZ
        count = int(round(STREAM_HZ * STREAM_DURATION_S))
        print(f"[STREAM] Sending {count} identical T102 commands...")
        start = time.perf_counter()
        for i in range(count):
            target_time = start + i * period
            now = time.perf_counter()
            if target_time > now:
                time.sleep(target_time - now)
            send(ser, t102, verbose=(i == 0 or i == count-1))

        print("[STREAM] Finished. Waiting 1s with NO polling...")
        time.sleep(1.0)
        pstream = fresh_t105(ser)
        print_pose("[AFTER T102 STREAM]", pstream)

        _,_,_,xy104,e3104 = h1_error(p104)
        _,_,_,xyone,e3one = h1_error(pone)
        _,_,_,xystream,e3stream = h1_error(pstream)

        print("\n" + "="*80)
        print("[COMPARISON]")
        print(
            f"T104:        base residual={base_residual(p104):+.6f} rad | "
            f"XY={xy104:.3f} mm | 3D={e3104:.3f} mm"
        )
        print(
            f"T102 one:    base residual={base_residual(pone):+.6f} rad | "
            f"XY={xyone:.3f} mm | 3D={e3one:.3f} mm"
        )
        print(
            f"T102 stream: base residual={base_residual(pstream):+.6f} rad | "
            f"XY={xystream:.3f} mm | 3D={e3stream:.3f} mm"
        )

        if abs(base_residual(pstream)) <= JOINT_PASS_RAD:
            print(
                "RESULT: repeated driver-like T102 reaches the IK target. "
                "Use the official ROS driver / repeated joint-state path for E4."
            )
        elif abs(base_residual(pone)) + 0.005 < abs(base_residual(p104)):
            print(
                "RESULT: high-speed one-shot helped, but did not fully converge. "
                "Command execution behavior still needs characterization."
            )
        else:
            print(
                "RESULT: even driver-like repeated T102 did not reach the target. "
                "Next inspect/use the official roarm_sdk function directly rather "
                "than continuing to vary raw JSON commands."
            )
        print("="*80)

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
