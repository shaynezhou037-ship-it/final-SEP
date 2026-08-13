#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 H1: T104 vs IKFast-joint/T102 diagnostic
===========================================

This program compares two ways of reaching the SAME H1 high target:

A) Firmware Cartesian command T104
B) IKFast joint solution sent directly with official T102 joint-radian command

The serial port is opened only once.

Safety:
- H1 HIGH only: no descent to the table.
- The program pauses for confirmation before BOTH motion commands.
- It does not use T106 as a stop command (T106 is an EOAT/gripper command).
- Ctrl+C only closes serial; use the robot power switch if emergency stopping is needed.

Interpretation:
- T105 Cartesian error after T104: firmware Cartesian execution result.
- T105 Cartesian error after T102: result after bypassing T104 Cartesian IK/trajectory.
- Joint residual after T102: whether servos actually reached the IKFast joint target.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from typing import Any, Dict, Optional, Tuple

import serial


# ---------------------------------------------------------------------
# SAME H1 HIGH TARGET used in the previous held-out test, T105/firmware frame
# ---------------------------------------------------------------------
TARGET_XYZ_MM = (134.247166, 74.501560, -79.402225)
TARGET_TIT_RAD = 1.500000

# Exact /compute_ik solution returned by MoveIt + IKFast for the converted H1 pose
IKFAST_JOINTS = {
    "base":     0.5120438298092209,
    "shoulder": 0.2580689332852309,
    "elbow":    2.4105797921381840,
    "wrist":    0.4021476011149847,
    "roll":    -0.0000000007641365,
}

DEFAULT_T104_SPEED = 0.05
DEFAULT_T102_SPEED = 150       # steps/s; conservative
DEFAULT_ACC = 10

# Stable-pose detection
POSE_STABLE_XYZ_MM = 0.40
POSE_STABLE_JOINT_RAD = 0.0020
STABLE_REQUIRED_S = 2.0
MOTION_TIMEOUT_S = 30.0


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--t104-spd", type=float, default=DEFAULT_T104_SPEED)
    p.add_argument("--t102-spd", type=int, default=DEFAULT_T102_SPEED)
    p.add_argument("--acc", type=int, default=DEFAULT_ACC)
    return p.parse_args()


def open_serial(port: str, baud: int) -> serial.Serial:
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = 0.15
    ser.write_timeout = 0.5
    ser.rtscts = False
    ser.dsrdtr = False

    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass

    ser.open()

    try:
        ser.setDTR(False)
        ser.setRTS(False)
    except Exception:
        pass

    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser


def send_json(ser: serial.Serial, obj: Dict[str, Any]) -> None:
    s = json.dumps(obj, separators=(",", ":"))
    print(f"[SEND] {s}")
    ser.write((s + "\n").encode("utf-8"))
    ser.flush()


def parse_t1051(line: str) -> Optional[Dict[str, Any]]:
    i = line.find("{")
    j = line.rfind("}")
    if i < 0 or j <= i:
        return None

    try:
        obj = json.loads(line[i:j+1])
    except json.JSONDecodeError:
        return None

    return obj if obj.get("T") == 1051 else None


def pose_xyz(p: Dict[str, Any]) -> Tuple[float, float, float]:
    return float(p["x"]), float(p["y"]), float(p["z"])


def pose_joints(p: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
    return (
        float(p["b"]),
        float(p["s"]),
        float(p["e"]),
        float(p["t"]),
        float(p["r"]),
    )


def xyz_error_mm(p: Dict[str, Any]) -> Tuple[float, float, float, float]:
    x, y, z = pose_xyz(p)
    tx, ty, tz = TARGET_XYZ_MM
    dx = x - tx
    dy = y - ty
    dz = z - tz
    dxy = math.hypot(dx, dy)
    d3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx, dy, dz, d3


def joint_error_rad(p: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
    actual = pose_joints(p)
    target = (
        IKFAST_JOINTS["base"],
        IKFAST_JOINTS["shoulder"],
        IKFAST_JOINTS["elbow"],
        IKFAST_JOINTS["wrist"],
        IKFAST_JOINTS["roll"],
    )
    return tuple(a - t for a, t in zip(actual, target))


def pose_text(p: Dict[str, Any]) -> str:
    return (
        f"x={float(p['x']):.3f} y={float(p['y']):.3f} z={float(p['z']):.3f} "
        f"tit={float(p.get('tit', float('nan'))):.6f} | "
        f"b={float(p['b']):.6f} s={float(p['s']):.6f} "
        f"e={float(p['e']):.6f} t={float(p['t']):.6f} "
        f"r={float(p['r']):.6f} g={float(p.get('g', float('nan'))):.6f}"
    )


def wait_initial_pose(ser: serial.Serial, timeout_s: float = 35.0) -> Dict[str, Any]:
    print("[INIT] Waiting for valid T1051; opening serial can reboot the controller.")
    end = time.time() + timeout_s
    next_req = 0.0
    last_status = 0.0

    while time.time() < end:
        now = time.time()

        if now >= next_req:
            send_json(ser, {"T": 105})
            next_req = now + 0.7

        raw = ser.readline()
        if raw:
            p = parse_t1051(raw.decode("utf-8", errors="replace").strip())
            if p is not None:
                needed = ("x", "y", "z", "b", "s", "e", "t", "r", "g")
                if all(isinstance(p.get(k), (int, float)) for k in needed):
                    print("[READY]", pose_text(p))
                    return p

        if now - last_status >= 5.0:
            print(f"[INIT] waiting... {max(0.0, end-now):.0f}s")
            last_status = now

    raise SystemExit("[ERROR] No valid T1051 within 35 s.")


def max_joint_delta(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ja = pose_joints(a)
    jb = pose_joints(b)
    return max(abs(x-y) for x, y in zip(ja, jb))


def xyz_delta(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    return math.dist(pose_xyz(a), pose_xyz(b))


def wait_until_stable(
    ser: serial.Serial,
    label: str,
    timeout_s: float = MOTION_TIMEOUT_S,
) -> Dict[str, Any]:
    """
    Wait until consecutive fresh T105 samples are stable for ~2 s.
    This deliberately does NOT require reaching the commanded Cartesian target,
    because the old T104 behavior can stop with a systematic residual.
    """
    print(f"[{label}] Waiting for motion to settle...")
    start = time.time()
    end = start + timeout_s
    next_req = start + 0.5
    last_print = 0.0
    prev: Optional[Dict[str, Any]] = None
    latest: Optional[Dict[str, Any]] = None
    stable_since: Optional[float] = None

    while time.time() < end:
        now = time.time()

        if now >= next_req:
            send_json(ser, {"T": 105})
            next_req = now + 0.7

        raw = ser.readline()
        if not raw:
            continue

        p = parse_t1051(raw.decode("utf-8", errors="replace").strip())
        if p is None:
            continue

        needed = ("x", "y", "z", "b", "s", "e", "t", "r", "g")
        if not all(isinstance(p.get(k), (int, float)) for k in needed):
            continue

        latest = p

        if now - last_print >= 1.0:
            _, _, _, e3 = xyz_error_mm(p)
            print(f"[{label}] {pose_text(p)} | target 3D error={e3:.2f} mm")
            last_print = now

        if prev is not None:
            dx = xyz_delta(p, prev)
            dj = max_joint_delta(p, prev)

            if dx <= POSE_STABLE_XYZ_MM and dj <= POSE_STABLE_JOINT_RAD:
                if stable_since is None:
                    stable_since = now
                elif now - stable_since >= STABLE_REQUIRED_S:
                    print(
                        f"[{label}] STABLE for {STABLE_REQUIRED_S:.1f}s "
                        f"(last Δxyz={dx:.3f} mm, Δjoint_max={dj:.6f} rad)"
                    )
                    return p
            else:
                stable_since = None

        prev = p

    if latest is None:
        raise SystemExit(f"[ERROR] {label}: no valid pose feedback.")

    print(f"[{label}] TIMEOUT; using latest pose.")
    return latest


def print_result(label: str, p: Dict[str, Any], include_joint_target: bool) -> None:
    dx, dy, dz, d3 = xyz_error_mm(p)
    dxy = math.hypot(dx, dy)

    print("\n" + "=" * 78)
    print(f"[{label} RESULT]")
    print(pose_text(p))
    print(
        f"Cartesian residual vs H1 target: "
        f"dX={dx:+.3f} mm dY={dy:+.3f} mm dZ={dz:+.3f} mm "
        f"XY={dxy:.3f} mm 3D={d3:.3f} mm"
    )

    if include_joint_target:
        db, ds, de, dt, dr = joint_error_rad(p)
        max_abs = max(abs(v) for v in (db, ds, de, dt, dr))
        print(
            "Joint residual actual-target: "
            f"db={db:+.6f} ds={ds:+.6f} de={de:+.6f} "
            f"dt={dt:+.6f} dr={dr:+.6f} rad "
            f"(max={max_abs:.6f} rad = {math.degrees(max_abs):.3f} deg)"
        )
    print("=" * 78)


def main():
    args = parse_args()

    print("=" * 78)
    print("E4 H1 — T104 vs IKFast joints via official T102")
    print("=" * 78)
    print(
        f"H1 T105-frame target XYZ = "
        f"({TARGET_XYZ_MM[0]:.3f}, {TARGET_XYZ_MM[1]:.3f}, "
        f"{TARGET_XYZ_MM[2]:.3f}) mm"
    )
    print(f"H1 target pitch/tit = {TARGET_TIT_RAD:.6f} rad")
    print("\nIKFast joint target:")
    for k, v in IKFAST_JOINTS.items():
        print(f"  {k:8s} = {v:.9f} rad")

    print("\n[SAFETY]")
    print("- H1 HIGH only; no table descent.")
    print("- Keep the path clear and keep one hand near the robot power switch.")
    print("- Program pauses before each motion.")
    print("- Ctrl+C closes serial; it does NOT send T106 (T106 is gripper control).")

    input("\nPress Enter when the robot is in a raised/open safe pose...")

    ser = open_serial(args.port, args.baud)

    try:
        initial = wait_initial_pose(ser)

        print("\n[INITIAL POSE]")
        print(pose_text(initial))

        # --------------------------------------------------------------
        # A) T104
        # --------------------------------------------------------------
        ans = input(
            "\nType T104 to move to H1 HIGH using firmware Cartesian control: "
        ).strip().upper()
        if ans != "T104":
            print("[CANCELLED before T104]")
            return

        send_json(
            ser,
            {
                "T": 104,
                "x": TARGET_XYZ_MM[0],
                "y": TARGET_XYZ_MM[1],
                "z": TARGET_XYZ_MM[2],
                "t": TARGET_TIT_RAD,
                "spd": args.t104_spd,
            },
        )

        t104_pose = wait_until_stable(ser, "T104")
        print_result("T104", t104_pose, include_joint_target=False)

        # Preserve actual current gripper command/position
        hand = float(t104_pose["g"])

        print("\n[T102 PREVIEW]")
        t102_cmd = {
            "T": 102,
            "base": IKFAST_JOINTS["base"],
            "shoulder": IKFAST_JOINTS["shoulder"],
            "elbow": IKFAST_JOINTS["elbow"],
            "wrist": IKFAST_JOINTS["wrist"],
            "roll": IKFAST_JOINTS["roll"],
            "hand": hand,
            "spd": args.t102_spd,
            "acc": args.acc,
        }
        print(json.dumps(t102_cmd, indent=2))

        print(
            "\nThis bypasses T104 Cartesian IK and commands the IKFast joint "
            "solution directly using official T102."
        )
        ans = input("Type IK to apply this small joint correction: ").strip().upper()
        if ans != "IK":
            print("[CANCELLED before T102]")
            return

        # --------------------------------------------------------------
        # B) T102 with IKFast joints
        # --------------------------------------------------------------
        send_json(ser, t102_cmd)

        t102_pose = wait_until_stable(ser, "T102-IKFAST")
        print_result("T102-IKFAST", t102_pose, include_joint_target=True)

        # --------------------------------------------------------------
        # Comparison
        # --------------------------------------------------------------
        _, _, _, e104_3d = xyz_error_mm(t104_pose)
        dx104, dy104, _, _ = xyz_error_mm(t104_pose)
        e104_xy = math.hypot(dx104, dy104)

        _, _, _, e102_3d = xyz_error_mm(t102_pose)
        dx102, dy102, _, _ = xyz_error_mm(t102_pose)
        e102_xy = math.hypot(dx102, dy102)

        print("\n" + "=" * 78)
        print("[A/B COMPARISON]")
        print(f"T104      XY error = {e104_xy:.3f} mm | 3D error = {e104_3d:.3f} mm")
        print(f"T102+IK   XY error = {e102_xy:.3f} mm | 3D error = {e102_3d:.3f} mm")

        if e102_xy + 1.0 < e104_xy:
            print(
                "Interpretation: direct IKFast joint control materially improved XY. "
                "T104 Cartesian execution/termination is strongly implicated."
            )
        elif abs(e102_xy - e104_xy) <= 1.0:
            print(
                "Interpretation: little XY improvement. The dominant error is likely "
                "outside T104 alone (joint tracking / geometry / frame/TCP)."
            )
        else:
            print(
                "Interpretation: IKFast joint command made XY worse. Inspect joint "
                "residual and URDF-vs-firmware geometry before using it for E4."
            )

        print("=" * 78)
        print("\nPlease copy the [T104 RESULT], [T102-IKFAST RESULT], and [A/B COMPARISON].")

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Serial will be closed. No automatic motion command sent.")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] Serial port closed.")


if __name__ == "__main__":
    main()
