#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 H1 — OFFICIAL roarm_sdk single-joint test
=============================================

Goal:
Test the exact SDK path used by roarm_driver for a single base-joint command,
without hand/gripper ambiguity.

Flow:
1) Offline-print the exact JSON bytes the SDK generates for JOINT_RADIAN_CTRL.
2) Open ONE serial connection through official roarm_sdk.
3) Wait for controller reboot/startup.
4) Raw T104 -> known H1 HIGH setup (same serial connection).
5) Call official:
       arm.joint_radian_ctrl(joint=1, radian=IK_BASE, speed=1000, acc=50)
6) Read fresh T105 feedback and compare actual base vs IKFast target.
7) Only if BASE passes, optionally test shoulder using the same official SDK API.

Safety:
- H1 HIGH only; no table descent.
- Confirmation before every motion.
- No roarm_driver / other process may use /dev/ttyUSB0 simultaneously.
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
IK_SHOULDER = 0.2580689332852309

BOOT_WAIT_S = 22.0
T104_WAIT_S = 12.0
JOINT_WAIT_S = 4.0

SDK_SPEED = 1000
SDK_ACC = 50

JOINT_PASS_RAD = 0.0040
MAX_CORRECTION_RAD = 0.12


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

    base_cmd = cg._mesg(
        common.JsonCmd.JOINT_RADIAN_CTRL,
        1,
        IK_BASE,
        SDK_SPEED,
        SDK_ACC,
    )

    shoulder_cmd = cg._mesg(
        common.JsonCmd.JOINT_RADIAN_CTRL,
        2,
        IK_SHOULDER,
        SDK_SPEED,
        SDK_ACC,
    )

    print("=" * 80)
    print("[OFFLINE SDK SERIALIZATION — NO SERIAL OPEN YET]")
    print("BASE:")
    print(base_cmd.decode("utf-8").rstrip())
    print("SHOULDER:")
    print(shoulder_cmd.decode("utf-8").rstrip())
    print("=" * 80)


def send_raw(ser, obj: Dict[str, Any]):
    text = json.dumps(obj, separators=(",", ":"))
    print("[RAW SEND]", text)
    ser.reset_input_buffer()
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

    needed = ("x", "y", "z", "b", "s", "e", "t", "r", "g")
    if not all(isinstance(d.get(k), (int, float)) for k in needed):
        return None

    return d


def fresh_t105(ser, timeout_s=8.0) -> Dict[str, Any]:
    queued = ser.in_waiting
    ser.reset_input_buffer()
    print(f"[T105 PRE-FLUSH] flushed {queued} queued byte(s)")

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


def h1_errors(p: Dict[str, Any]):
    dx = float(p["x"]) - H1_XYZ[0]
    dy = float(p["y"]) - H1_XYZ[1]
    dz = float(p["z"]) - H1_XYZ[2]
    xy = math.hypot(dx, dy)
    e3 = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx, dy, dz, xy, e3


def print_pose(title: str, p: Dict[str, Any]):
    dx, dy, dz, xy, e3 = h1_errors(p)
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
    print("=" * 80)


def main():
    a = parse_args()

    offline_sdk_bytes()

    print("\n[SAFETY]")
    print("- This test uses the official roarm_sdk for the joint command.")
    print("- H1 HIGH only; no table descent.")
    print("- BASE moves only about 3 degrees from the expected H1 setup pose.")
    print("- No roarm_driver / MoveIt / other program may own /dev/ttyUSB0.")
    input("\nPress Enter to open the official SDK serial connection...")

    # IMPORTANT: one and only one serial connection for the whole run.
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
        queued = ser.in_waiting
        ser.reset_input_buffer()
        print(f"[BOOT FLUSH] flushed {queued} queued byte(s)")

        p0 = fresh_t105(ser)
        print_pose("[FRESH START]", p0)

        # ------------------------------------------------------------------
        # H1 setup via known T104 command on the SAME SDK-owned serial port.
        # ------------------------------------------------------------------
        if input("\nType H1 to move to the known H1 HIGH target: ").strip().upper() != "H1":
            print("Cancelled.")
            return

        send_raw(
            ser,
            {
                "T": 104,
                "x": H1_XYZ[0],
                "y": H1_XYZ[1],
                "z": H1_XYZ[2],
                "t": H1_TIT,
                "spd": a.t104_spd,
            },
        )

        print(f"[T104] Waiting {T104_WAIT_S:.0f}s with NO polling...")
        time.sleep(T104_WAIT_S)

        p104 = fresh_t105(ser)
        print_pose("[AFTER T104]", p104)

        _, _, _, _, e104 = h1_errors(p104)
        if e104 > 40.0:
            print("[STOP] T104 did not reach the H1 neighborhood.")
            return

        base_delta = IK_BASE - float(p104["b"])
        shoulder_delta = IK_SHOULDER - float(p104["s"])

        print(
            f"\nBASE correction required = {base_delta:+.6f} rad "
            f"({math.degrees(base_delta):+.3f} deg)"
        )
        print(
            f"SHOULDER correction required = {shoulder_delta:+.6f} rad "
            f"({math.degrees(shoulder_delta):+.3f} deg)"
        )

        if abs(base_delta) > MAX_CORRECTION_RAD:
            print("[STOP] BASE correction unexpectedly large.")
            return

        # ------------------------------------------------------------------
        # Official SDK BASE test.
        # ------------------------------------------------------------------
        if input(
            "\nType SDKBASE to call arm.joint_radian_ctrl(joint=1,...): "
        ).strip().upper() != "SDKBASE":
            print("Stopped after T104.")
            return

        print(
            f"[SDK CALL] joint_radian_ctrl("
            f"joint=1, radian={IK_BASE:.9f}, speed={SDK_SPEED}, acc={SDK_ACC})"
        )

        result = arm.joint_radian_ctrl(
            joint=1,
            radian=IK_BASE,
            speed=SDK_SPEED,
            acc=SDK_ACC,
        )
        print("[SDK RETURN]", result)

        print(f"[SDK BASE] Waiting {JOINT_WAIT_S:.0f}s with NO polling...")
        time.sleep(JOINT_WAIT_S)

        pb = fresh_t105(ser)
        print_pose("[AFTER OFFICIAL SDK BASE]", pb)

        base_residual = float(pb["b"]) - IK_BASE
        print(
            f"BASE residual actual-target = {base_residual:+.6f} rad "
            f"({math.degrees(base_residual):+.3f} deg)"
        )

        if abs(base_residual) > JOINT_PASS_RAD:
            print("\n" + "=" * 80)
            print("[RESULT]")
            print("Official roarm_sdk BASE command did NOT reach the requested target.")
            print("This is now evidence against blaming our hand-written JSON formatting.")
            print("Next layer: firmware / command-state / servo execution.")
            print("=" * 80)
            return

        print("\n[PASS] Official SDK BASE reached the IKFast base target.")

        # ------------------------------------------------------------------
        # Optional shoulder test, only after BASE passes.
        # ------------------------------------------------------------------
        if abs(shoulder_delta) > MAX_CORRECTION_RAD:
            print("[STOP] Shoulder correction unexpectedly large.")
            return

        if input(
            "\nType SDKSHOULDER to test joint=2, or Enter to stop: "
        ).strip().upper() != "SDKSHOULDER":
            print("Stopped after successful BASE test.")
            return

        print(
            f"[SDK CALL] joint_radian_ctrl("
            f"joint=2, radian={IK_SHOULDER:.9f}, speed={SDK_SPEED}, acc={SDK_ACC})"
        )
        result = arm.joint_radian_ctrl(
            joint=2,
            radian=IK_SHOULDER,
            speed=SDK_SPEED,
            acc=SDK_ACC,
        )
        print("[SDK RETURN]", result)

        print(f"[SDK SHOULDER] Waiting {JOINT_WAIT_S:.0f}s with NO polling...")
        time.sleep(JOINT_WAIT_S)

        ps = fresh_t105(ser)
        print_pose("[AFTER OFFICIAL SDK SHOULDER]", ps)

        shoulder_residual = float(ps["s"]) - IK_SHOULDER
        print(
            f"SHOULDER residual actual-target = {shoulder_residual:+.6f} rad "
            f"({math.degrees(shoulder_residual):+.3f} deg)"
        )

        _, _, _, xy, e3 = h1_errors(ps)
        print("\n" + "=" * 80)
        print("[SUMMARY]")
        print(
            f"BASE residual     = {float(ps['b']) - IK_BASE:+.6f} rad"
        )
        print(
            f"SHOULDER residual = {float(ps['s']) - IK_SHOULDER:+.6f} rad"
        )
        print(f"H1 Cartesian      = XY={xy:.3f} mm | 3D={e3:.3f} mm")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Closing SDK serial connection.")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        print("[CLOSED] serial closed.")


if __name__ == "__main__":
    main()
