#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 H2 — MoveIt /compute_ik diagnostic (NO robot motion)

Purpose
-------
Compute an IKFast joint solution for the H2 HIGH Cartesian target so that the
solution can be compared against the real T105 joint feedback from the H2
repeatability run.

This node does NOT open /dev/ttyUSB0 and does NOT command the robot.

Requirements
------------
- ROS 2 Humble sourced
- ~/roarm_ws/install/setup.bash sourced
- move_group already running with the same RoArm-M3 MoveIt configuration used
  for the earlier H1 /compute_ik test
- roarm_driver should remain OFF for this diagnostic

Frame conversion used (from prior 20-pose T105-vs-URDF comparison):
    MoveIt_X = T105_X - 1.609 mm
    MoveIt_Y = T105_Y + 0.047 mm
    MoveIt_Z = T105_Z + 54.227 mm

Orientation:
    roll  = 0
    pitch = 1.5 rad
    yaw   = atan2(T105_Y, T105_X)
"""

import math
import sys

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import PoseStamped
from moveit_msgs.srv import GetPositionIK


# H2 HIGH in firmware/T105 Cartesian coordinates [mm]
T105_X_MM = 241.913571675
T105_Y_MM = 54.004575551
T105_Z_MM = -78.676144925

ROLL = 0.0
PITCH = 1.5
YAW = math.atan2(T105_Y_MM, T105_X_MM)

# Local T105 -> MoveIt hand_tcp translation found previously [mm]
DX_MM = -1.609
DY_MM = +0.047
DZ_MM = +54.227

MOVEIT_X_M = (T105_X_MM + DX_MM) / 1000.0
MOVEIT_Y_M = (T105_Y_MM + DY_MM) / 1000.0
MOVEIT_Z_M = (T105_Z_MM + DZ_MM) / 1000.0


def rpy_to_quaternion(roll, pitch, yaw):
    cr = math.cos(roll / 2.0)
    sr = math.sin(roll / 2.0)
    cp = math.cos(pitch / 2.0)
    sp = math.sin(pitch / 2.0)
    cy = math.cos(yaw / 2.0)
    sy = math.sin(yaw / 2.0)

    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    qw = cr * cp * cy + sr * sp * sy
    return qx, qy, qz, qw


class H2IKClient(Node):
    def __init__(self):
        super().__init__("e4_h2_compute_ik")
        self.cli = self.create_client(GetPositionIK, "/compute_ik")

    def run(self):
        print("=" * 80)
        print("E4 H2 — IKFAST /compute_ik DIAGNOSTIC")
        print("=" * 80)
        print("NO ROBOT MOTION")
        print()
        print(
            f"H2 HIGH T105 target [mm] = "
            f"({T105_X_MM:.6f}, {T105_Y_MM:.6f}, {T105_Z_MM:.6f})"
        )
        print(
            f"MoveIt target [m] = "
            f"({MOVEIT_X_M:.9f}, {MOVEIT_Y_M:.9f}, {MOVEIT_Z_M:.9f})"
        )
        print(
            f"RPY [rad] = "
            f"({ROLL:.9f}, {PITCH:.9f}, {YAW:.9f})"
        )

        qx, qy, qz, qw = rpy_to_quaternion(ROLL, PITCH, YAW)
        print(
            f"Quaternion xyzw = "
            f"({qx:.12f}, {qy:.12f}, {qz:.12f}, {qw:.12f})"
        )

        print("\nWaiting for /compute_ik ...")
        if not self.cli.wait_for_service(timeout_sec=10.0):
            print(
                "ERROR: /compute_ik is not available.\n"
                "Start the same MoveIt move_group configuration used for the H1 "
                "IKFast test, with roarm_driver OFF, then run this script again."
            )
            return 2

        req = GetPositionIK.Request()
        req.ik_request.group_name = "hand"
        req.ik_request.ik_link_name = "hand_tcp"
        req.ik_request.avoid_collisions = False
        req.ik_request.timeout.sec = 2
        req.ik_request.timeout.nanosec = 0

        pose = PoseStamped()
        pose.header.frame_id = "base_link"
        pose.header.stamp = self.get_clock().now().to_msg()

        pose.pose.position.x = MOVEIT_X_M
        pose.pose.position.y = MOVEIT_Y_M
        pose.pose.position.z = MOVEIT_Z_M

        pose.pose.orientation.x = qx
        pose.pose.orientation.y = qy
        pose.pose.orientation.z = qz
        pose.pose.orientation.w = qw

        req.ik_request.pose_stamped = pose

        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)

        if not future.done():
            print("ERROR: /compute_ik call timed out.")
            return 3

        res = future.result()
        if res is None:
            print("ERROR: /compute_ik returned no response.")
            return 4

        print("\n" + "=" * 80)
        print("IK RESULT")
        print("=" * 80)
        print(f"error_code.val = {res.error_code.val}")

        names = list(res.solution.joint_state.name)
        pos = list(res.solution.joint_state.position)

        if res.error_code.val != 1:
            print("IK FAILED.")
            return 5

        wanted = [
            "base_link_to_link1",
            "link1_to_link2",
            "link2_to_link3",
            "link3_to_link4",
            "link4_to_link5",
            "link5_to_gripper_link",
        ]

        mapping = dict(zip(names, pos))

        for n in wanted:
            if n in mapping:
                print(f"{n:28s} = {mapping[n]: .12f}")
            else:
                print(f"{n:28s} = MISSING")

        print("\nCompact:")
        print(
            "base={:.12f} shoulder={:.12f} elbow={:.12f} "
            "wrist={:.12f} roll={:.12f} gripper={:.12f}".format(
                mapping.get("base_link_to_link1", float("nan")),
                mapping.get("link1_to_link2", float("nan")),
                mapping.get("link2_to_link3", float("nan")),
                mapping.get("link3_to_link4", float("nan")),
                mapping.get("link4_to_link5", float("nan")),
                mapping.get("link5_to_gripper_link", float("nan")),
            )
        )
        print("=" * 80)
        return 0


def main():
    rclpy.init()
    node = H2IKClient()
    try:
        code = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    sys.exit(code)


if __name__ == "__main__":
    main()
