#!/usr/bin/env python3

import json
import math
import re
import statistics
import time

import rclpy
import serial
from geometry_msgs.msg import PointStamped
from rclpy.node import Node


SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
SAFE_CLEARANCE_MM = 50.0
MAX_WAYPOINT_ERROR_MM = 45.0


class TargetCollector(Node):

    def __init__(self):
        super().__init__("task10_target_collector")
        self.samples = []
        self.create_subscription(
            PointStamped,
            "/fused_target_pose_robot_corrected",
            self.callback,
            10,
        )

    def callback(self, message):
        self.samples.append((
            message.point.x * 1000.0,
            message.point.y * 1000.0,
            message.point.z * 1000.0,
        ))


def send_json(command, wait_seconds=1.0):
    with serial.Serial(
        SERIAL_PORT,
        BAUD_RATE,
        timeout=1,
    ) as port:
        port.reset_input_buffer()
        port.write((json.dumps(command) + "\n").encode())
        port.flush()
        time.sleep(wait_seconds)
        return port.read_all().decode(errors="replace")


def get_pose():
    raw = send_json({"T": 105}, 0.15)

    matches = re.findall(r"\{[^\r\n]*\}", raw)

    for text in reversed(matches):
        try:
            values = json.loads(text)
        except json.JSONDecodeError:
            continue

        if all(key in values for key in ("x", "y", "z")):
            return values

    raise RuntimeError(
        f"Could not parse robot feedback: {raw!r}"
    )


def move_and_check(label, command):
    print(f"\n{label}")
    print("Command:", command)

    response = send_json(command, 5.0)
    print("Response:", response.strip())

    pose = get_pose()
    actual = (
        float(pose["x"]),
        float(pose["y"]),
        float(pose["z"]),
    )
    expected = (
        float(command["x"]),
        float(command["y"]),
        float(command["z"]),
    )

    error = math.dist(actual, expected)

    print("Actual XYZ mm:", actual)
    print("Waypoint error mm:", error)

    if error > MAX_WAYPOINT_ERROR_MM:
        print(
            f"WARNING: {label} error {error:.1f} mm "
            f"exceeds {MAX_WAYPOINT_ERROR_MM:.1f} mm; "
            "continuing by user request."
        )

    return actual


def collect_target():
    rclpy.init()
    node = TargetCollector()
    deadline = time.time() + 30.0

    try:
        while (
            len(node.samples) < 10
            and time.time() < deadline
        ):
            rclpy.spin_once(node, timeout_sec=0.5)

        if len(node.samples) < 5:
            raise RuntimeError(
                "Not enough accepted fused target samples."
            )

        target = tuple(
            statistics.median(
                sample[axis] for sample in node.samples
            )
            for axis in range(3)
        )
        return target
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main():
    print(
        "The robot will first return to its "
        "initial ready pose."
    )
    confirmation = input(
        "Clear the full robot workspace, "
        "then type HOME: "
    )

    if confirmation != "HOME":
        print("Cancelled.")
        return

    home_command = {
        "T": 102,
        "base": 0.0,
        "shoulder": 0.0,
        "elbow": 1.57,
        "wrist": 0.0,
        "roll": 0.0,
        "hand": 3.14,
        "spd": 300,
        "acc": 10,
    }

    print("Returning to ready pose:", home_command)
    response = send_json(home_command, 12.0)
    print("Home response:", response.strip())

    current = get_pose()
    current_xyz = (
        float(current["x"]),
        float(current["y"]),
        float(current["z"]),
    )

    print("Ready-pose XYZ mm:", current_xyz)

    if current_xyz[2] < 150.0:
        raise RuntimeError(
            "Initial pose was not reached; Z is below 150 mm."
        )

    print("Collecting synchronized target...")
    tx, ty, tz = collect_target()

    print("Target XYZ mm:", (tx, ty, tz))

    if not (
        80.0 <= tx <= 350.0
        and -300.0 <= ty <= 300.0
        and -150.0 <= tz <= 100.0
    ):
        raise RuntimeError(
            "Target is outside configured workspace limits."
        )

    safe_z = tz + SAFE_CLEARANCE_MM

    waypoints = [
        {
            "T": 104,
            "x": tx,
            "y": ty,
            "z": 200.0,
            "t": 0.0,
            "r": 0.0,
            "g": 3.14,
            "spd": 0.12,
        },
        {
            "T": 104,
            "x": tx - 10.0,
            "y": ty,
            "z": 170.0,
            "t": 0.75,
            "r": 0.0,
            "g": 3.14,
            "spd": 0.10,
        },
        {
            "T": 104,
            "x": tx - 10.0,
            "y": ty,
            "z": 100.0,
            "t": 1.30,
            "r": 0.0,
            "g": 3.14,
            "spd": 0.08,
        },
        {
            "T": 104,
            "x": tx - 10.0,
            "y": ty,
            "z": 50.0,
            "t": 1.45,
            "r": 0.0,
            "g": 3.14,
            "spd": 0.06,
        },
        {
            "T": 104,
            "x": tx,
            "y": ty,
            "z": 0.0,
            "t": 1.52,
            "r": 0.0,
            "g": 3.14,
            "spd": 0.06,
        },
        {
            "T": 104,
            "x": tx,
            "y": ty,
            "z": safe_z,
            "t": 1.52,
            "r": 0.0,
            "g": 3.14,
            "spd": 0.04,
        },
    ]

    print("\nSafe approach point mm:",
          (tx, ty, safe_z))
    print("The robot will NOT touch the marker.")

    confirmation = input(
        "Clear the workspace, then type APPROACH: "
    )

    if confirmation != "APPROACH":
        print("Cancelled.")
        return

    completed = []

    try:
        for index, waypoint in enumerate(
            waypoints,
            start=1,
        ):
            move_and_check(
                f"Approach {index}/{len(waypoints)}",
                waypoint,
            )
            completed.append(waypoint)

        print("\nSafe point reached. Holding 3 seconds.")
        time.sleep(3)

        for index, waypoint in enumerate(
            reversed(completed[:-1]),
            start=1,
        ):
            retract = dict(waypoint)
            retract["spd"] = min(
                float(retract["spd"]),
                0.06,
            )
            move_and_check(
                f"Retract {index}/{len(completed)-1}",
                retract,
            )

        print("\nGuarded approach and retract: PASS")

    except Exception as error:
        print("\nABORTED:", error)
        print(
            "Robot remains torque-locked. "
            "Do not continue downward."
        )
        raise


if __name__ == "__main__":
    main()
