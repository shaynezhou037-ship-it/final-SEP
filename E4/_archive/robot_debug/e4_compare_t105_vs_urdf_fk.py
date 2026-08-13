#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import serial

DEFAULT_XACRO = Path(
    "/home/shayne/roarm_ws/src/roarm_main/"
    "roarm_description/urdf/roarm_m3/roarm_m3.xacro"
)

JOINT_VALUE_MAP = {
    "base_link_to_link1": "b",
    "link1_to_link2": "s",
    "link2_to_link3": "e",
    "link3_to_link4": "t",
    "link4_to_link5": "r",
}

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--xacro", type=Path, default=DEFAULT_XACRO)
    p.add_argument("--timeout", type=float, default=35.0)
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

def send_t105(ser: serial.Serial):
    ser.write(b'{"T":105}\n')
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

def read_firmware_pose(ser: serial.Serial, timeout_s: float) -> Dict[str, Any]:
    print("[SERIAL] Waiting for T1051. Opening serial may reboot the controller.")
    end = time.time() + timeout_s
    next_req = 0.0
    last_status = 0.0
    while time.time() < end:
        now = time.time()
        if now >= next_req:
            send_t105(ser)
            next_req = now + 0.7
        raw = ser.readline()
        if raw:
            obj = parse_t1051(raw.decode("utf-8", errors="replace").strip())
            if obj is not None:
                need = ("x", "y", "z", "b", "s", "e", "t", "r")
                missing = [k for k in need if not isinstance(obj.get(k), (int, float))]
                if missing:
                    raise SystemExit(f"[ERROR] T1051 missing numeric fields: {missing}")
                return obj
        if now - last_status >= 5.0:
            print(f"[SERIAL] waiting... {max(0.0, end-now):.0f} s remaining")
            last_status = now
    raise SystemExit("[ERROR] No valid T1051 within timeout.")

def parse_vec(text: Optional[str], default: Tuple[float, float, float]) -> np.ndarray:
    if not text:
        return np.array(default, dtype=float)
    vals = [float(v) for v in text.split()]
    if len(vals) != 3:
        raise ValueError(f"Expected 3 values, got: {text}")
    return np.array(vals, dtype=float)

def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1,0,0],[0,c,-s],[0,s,c]], dtype=float)

def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c,0,s],[0,1,0],[-s,0,c]], dtype=float)

def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c,-s,0],[s,c,0],[0,0,1]], dtype=float)

def rpy_matrix(rpy: np.ndarray) -> np.ndarray:
    r, p, y = rpy
    return rot_z(y) @ rot_y(p) @ rot_x(r)

def axis_angle_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
    n = float(np.linalg.norm(axis))
    if n == 0:
        return np.eye(3)
    x, y, z = axis / n
    c = math.cos(angle)
    s = math.sin(angle)
    C = 1.0 - c
    return np.array([
        [x*x*C + c,     x*y*C - z*s, x*z*C + y*s],
        [y*x*C + z*s,   y*y*C + c,   y*z*C - x*s],
        [z*x*C - y*s,   z*y*C + x*s, z*z*C + c],
    ], dtype=float)

def homogeneous(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    T = np.eye(4)
    T[:3,:3] = R
    T[:3,3] = t
    return T

def matrix_to_rpy(R: np.ndarray) -> Tuple[float, float, float]:
    sy = math.sqrt(R[0,0]**2 + R[1,0]**2)
    singular = sy < 1e-9
    if not singular:
        roll = math.atan2(R[2,1], R[2,2])
        pitch = math.atan2(-R[2,0], sy)
        yaw = math.atan2(R[1,0], R[0,0])
    else:
        roll = math.atan2(-R[1,2], R[1,1])
        pitch = math.atan2(-R[2,0], sy)
        yaw = 0.0
    return roll, pitch, yaw

def load_urdf_from_xacro(xacro_path: Path) -> ET.Element:
    if not xacro_path.exists():
        raise SystemExit(f"[ERROR] Xacro not found: {xacro_path}")
    try:
        xml = subprocess.check_output(
            ["xacro", str(xacro_path)],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError:
        raise SystemExit("[ERROR] 'xacro' command not found.")
    except subprocess.CalledProcessError as e:
        raise SystemExit("[ERROR] xacro failed:\n" + e.output)
    return ET.fromstring(xml)

def build_joint_table(root: ET.Element):
    by_child = {}
    for j in root.findall("joint"):
        parent_el = j.find("parent")
        child_el = j.find("child")
        if parent_el is None or child_el is None:
            continue
        origin = j.find("origin")
        xyz = parse_vec(origin.attrib.get("xyz") if origin is not None else None, (0,0,0))
        rpy = parse_vec(origin.attrib.get("rpy") if origin is not None else None, (0,0,0))
        axis_el = j.find("axis")
        axis = parse_vec(axis_el.attrib.get("xyz") if axis_el is not None else None, (1,0,0))
        item = {
            "name": j.attrib["name"],
            "type": j.attrib.get("type", "fixed"),
            "parent": parent_el.attrib["link"],
            "child": child_el.attrib["link"],
            "xyz": xyz,
            "rpy": rpy,
            "axis": axis,
        }
        by_child[item["child"]] = item
    return by_child

def get_chain(by_child, base: str, tip: str) -> List[Dict[str, Any]]:
    chain = []
    current = tip
    seen = set()
    while current != base:
        if current in seen:
            raise RuntimeError("Cycle in URDF chain.")
        seen.add(current)
        if current not in by_child:
            raise RuntimeError(f"No joint found with child link '{current}'")
        j = by_child[current]
        chain.append(j)
        current = j["parent"]
    chain.reverse()
    return chain

def compute_fk(chain, pose: Dict[str, Any]) -> np.ndarray:
    T = np.eye(4)
    for j in chain:
        T = T @ homogeneous(rpy_matrix(j["rpy"]), j["xyz"])
        if j["type"] in ("revolute", "continuous"):
            field = JOINT_VALUE_MAP.get(j["name"])
            if field is None:
                raise RuntimeError(f"No T105 joint mapping for movable joint: {j['name']}")
            q = float(pose[field])
            T = T @ homogeneous(axis_angle_matrix(j["axis"], q), np.zeros(3))
        elif j["type"] == "fixed":
            pass
        elif j["type"] == "prismatic":
            raise RuntimeError("Prismatic joint not expected.")
        else:
            raise RuntimeError(f"Unsupported joint type: {j['type']}")
    return T

def main():
    args = parse_args()

    print("=" * 78)
    print("RoArm T105 XYZ  vs  URDF FK(base_link -> hand_tcp)")
    print("=" * 78)
    print("[SAFETY] T105 only. NO motion command is sent.")
    print(f"Xacro: {args.xacro}")
    print(f"Serial: {args.port} @ {args.baud}")

    root = load_urdf_from_xacro(args.xacro)
    chain = get_chain(build_joint_table(root), "base_link", "hand_tcp")

    print("\n[URDF CHAIN]")
    for j in chain:
        print(
            f"{j['name']}: {j['parent']} -> {j['child']} "
            f"type={j['type']} origin_xyz={j['xyz'].tolist()} "
            f"origin_rpy={j['rpy'].tolist()} axis={j['axis'].tolist()}"
        )

    ser = open_serial(args.port, args.baud)
    try:
        pose = read_firmware_pose(ser, args.timeout)
    finally:
        ser.close()

    print("\n[FIRMWARE T1051]")
    print(
        f"XYZ = ({float(pose['x']):.3f}, {float(pose['y']):.3f}, "
        f"{float(pose['z']):.3f}) mm"
    )
    print(
        f"joints b/s/e/t/r = "
        f"({float(pose['b']):.6f}, {float(pose['s']):.6f}, "
        f"{float(pose['e']):.6f}, {float(pose['t']):.6f}, "
        f"{float(pose['r']):.6f}) rad"
    )
    if isinstance(pose.get("tit"), (int, float)):
        print(f"firmware tit = {float(pose['tit']):.6f} rad")

    T = compute_fk(chain, pose)
    fk_mm = T[:3,3] * 1000.0
    rr, pp, yy = matrix_to_rpy(T[:3,:3])

    fw = np.array([float(pose["x"]), float(pose["y"]), float(pose["z"])])
    diff = fk_mm - fw
    diff_norm = float(np.linalg.norm(diff))

    print("\n[URDF FK]")
    print(
        f"base_link -> hand_tcp XYZ = "
        f"({fk_mm[0]:.3f}, {fk_mm[1]:.3f}, {fk_mm[2]:.3f}) mm"
    )
    print(f"RPY = ({rr:.6f}, {pp:.6f}, {yy:.6f}) rad")

    print("\n[DIFFERENCE: URDF_FK - T105]")
    print(
        f"dX={diff[0]:+.3f} mm, dY={diff[1]:+.3f} mm, "
        f"dZ={diff[2]:+.3f} mm, 3D={diff_norm:.3f} mm"
    )

    print("\n[INTERPRETATION]")
    if diff_norm <= 3.0:
        print(
            "PASS-LIKE: T105 XYZ and MoveIt hand_tcp are very close. "
            "The board->robot XYZ can likely be reused for the IKFast test."
        )
    elif diff_norm <= 10.0:
        print(
            "BORDERLINE: broadly similar, but there is a nontrivial frame/TCP offset."
        )
    else:
        print(
            "MISMATCH: T105 XYZ and MoveIt hand_tcp are not the same Cartesian quantity. "
            "A frame/TCP conversion is required before IKFast testing."
        )
    print("=" * 78)

if __name__ == "__main__":
    main()
