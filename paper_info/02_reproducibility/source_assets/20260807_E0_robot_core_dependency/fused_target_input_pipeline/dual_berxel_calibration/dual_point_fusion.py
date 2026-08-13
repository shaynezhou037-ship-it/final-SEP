#!/usr/bin/env python3

import json
from collections import deque
from pathlib import Path

import numpy as np
import rclpy
import yaml
from geometry_msgs.msg import PointStamped
from rclpy.node import Node
from std_msgs.msg import Float64, String


class DualPointFusion(Node):

    def __init__(self):
        super().__init__('dual_point_fusion')

        self.declare_parameter('max_time_skew_ms', 50.0)
        self.declare_parameter('max_point_distance_mm', 15.0)
        self.declare_parameter('minimum_sigma_mm', 1.0)

        self.max_skew_ms = float(
            self.get_parameter('max_time_skew_ms').value
        )
        self.max_distance_mm = float(
            self.get_parameter('max_point_distance_mm').value
        )
        self.minimum_sigma_mm = float(
            self.get_parameter('minimum_sigma_mm').value
        )

        config_path = (
            Path.home()
            / 'berxel_ros2_ws/src/dual_berxel_calibration/config'
            / 'camera1_empirical_correction.yaml'
        )

        with config_path.open('r', encoding='utf-8') as file:
            config = yaml.safe_load(file)

        self.rotation = np.asarray(
            config['rotation'],
            dtype=float,
        )

        translation = config['translation_m']
        self.translation = np.array([
            translation['x'],
            translation['y'],
            translation['z'],
        ], dtype=float)

        robot_config_path = (
            Path.home()
            / 'berxel_ros2_ws/src/dual_berxel_calibration/config'
            / 'fused_to_robot_correction.yaml'
        )

        with robot_config_path.open(
            'r',
            encoding='utf-8',
        ) as file:
            robot_config = yaml.safe_load(file)

        self.robot_rotation = np.asarray(
            robot_config['rotation'],
            dtype=float,
        )

        robot_translation = robot_config['translation_mm']
        self.robot_translation = np.array([
            robot_translation['x'],
            robot_translation['y'],
            robot_translation['z'],
        ], dtype=float) / 1000.0

        self.points = {
            'ihawk1': deque(maxlen=60),
            'ihawk2': deque(maxlen=60),
        }

        self.quality = {
            'ihawk1': None,
            'ihawk2': None,
        }

        self.last_pair = None
        self._subscriptions = []

        for camera in ('ihawk1', 'ihawk2'):
            self._subscriptions.append(
                self.create_subscription(
                    PointStamped,
                    f'/{camera}/target_point_base',
                    lambda msg, name=camera:
                    self.point_callback(name, msg),
                    10,
                )
            )

            self._subscriptions.append(
                self.create_subscription(
                    String,
                    f'/{camera}/target_quality',
                    lambda msg, name=camera:
                    self.quality_callback(name, msg),
                    10,
                )
            )

        self.corrected_publisher = self.create_publisher(
            PointStamped,
            '/ihawk1/target_point_base_corrected',
            10,
        )

        self.fused_publisher = self.create_publisher(
            PointStamped,
            '/fused_target_pose',
            10,
        )

        self.robot_corrected_publisher = (
            self.create_publisher(
                PointStamped,
                '/fused_target_pose_robot_corrected',
                10,
            )
        )

        self.difference_publisher = self.create_publisher(
            Float64,
            '/dual_camera/point_difference',
            10,
        )

        self.status_publisher = self.create_publisher(
            String,
            '/dual_camera/fusion_status',
            10,
        )

        self.timer = self.create_timer(
            0.02,
            self.process,
        )

        self.get_logger().info(
            'Dual point fusion started. '
            f'Max skew={self.max_skew_ms:.1f} ms, '
            f'max distance={self.max_distance_mm:.1f} mm.'
        )

    @staticmethod
    def stamp_seconds(stamp):
        return stamp.sec + stamp.nanosec * 1.0e-9

    def point_callback(self, camera, message):
        self.points[camera].append(message)

    def quality_callback(self, camera, message):
        try:
            self.quality[camera] = json.loads(message.data)
        except json.JSONDecodeError:
            self.quality[camera] = None

    def publish_status(self, values):
        message = String()
        message.data = json.dumps(values)
        self.status_publisher.publish(message)

    def process(self):
        buffer1 = self.points['ihawk1']
        buffer2 = self.points['ihawk2']
        quality1 = self.quality['ihawk1']
        quality2 = self.quality['ihawk2']

        if (
            not buffer1
            or not buffer2
            or quality1 is None
            or quality2 is None
        ):
            return

        point1 = buffer1[-1]
        time1 = self.stamp_seconds(point1.header.stamp)

        point2 = min(
            buffer2,
            key=lambda message: abs(
                self.stamp_seconds(message.header.stamp)
                - time1
            ),
        )

        pair = (
            point1.header.stamp.sec,
            point1.header.stamp.nanosec,
            point2.header.stamp.sec,
            point2.header.stamp.nanosec,
        )

        if pair == self.last_pair:
            return

        self.last_pair = pair

        if not quality1.get('accepted', False):
            self.publish_status({
                'accepted': False,
                'reason': 'ihawk1_invalid',
            })
            return

        if not quality2.get('accepted', False):
            self.publish_status({
                'accepted': False,
                'reason': 'ihawk2_invalid',
            })
            return

        time1 = self.stamp_seconds(point1.header.stamp)
        time2 = self.stamp_seconds(point2.header.stamp)
        skew_ms = abs(time1 - time2) * 1000.0

        if skew_ms > self.max_skew_ms:
            self.publish_status({
                'accepted': False,
                'reason': 'timestamp_skew',
                'timestamp_skew_ms': skew_ms,
            })
            return

        raw1 = np.array([
            point1.point.x,
            point1.point.y,
            point1.point.z,
        ])

        corrected1 = (
            self.rotation @ raw1
            + self.translation
        )

        value2 = np.array([
            point2.point.x,
            point2.point.y,
            point2.point.z,
        ])

        corrected_message = PointStamped()
        corrected_message.header = point1.header
        corrected_message.header.frame_id = 'base_link'
        corrected_message.point.x = float(corrected1[0])
        corrected_message.point.y = float(corrected1[1])
        corrected_message.point.z = float(corrected1[2])
        self.corrected_publisher.publish(corrected_message)

        difference_mm = float(
            np.linalg.norm(corrected1 - value2) * 1000.0
        )

        difference_message = Float64()
        difference_message.data = difference_mm
        self.difference_publisher.publish(difference_message)

        if difference_mm > self.max_distance_mm:
            self.publish_status({
                'accepted': False,
                'reason': 'point_difference',
                'point_difference_mm': difference_mm,
                'timestamp_skew_ms': skew_ms,
            })
            return

        sigma1 = max(
            float(quality1.get(
                'depth_std_mm',
                10.0,
            )),
            self.minimum_sigma_mm,
        )

        sigma2 = max(
            float(quality2.get(
                'depth_std_mm',
                10.0,
            )),
            self.minimum_sigma_mm,
        )

        weight1 = 1.0 / (sigma1 ** 2)
        weight2 = 1.0 / (sigma2 ** 2)

        fused = (
            weight1 * corrected1
            + weight2 * value2
        ) / (weight1 + weight2)

        fused_message = PointStamped()
        fused_message.header = point1.header
        fused_message.header.frame_id = 'base_link'
        fused_message.point.x = float(fused[0])
        fused_message.point.y = float(fused[1])
        fused_message.point.z = float(fused[2])
        self.fused_publisher.publish(fused_message)

        robot_corrected = (
            self.robot_rotation @ fused
            + self.robot_translation
        )

        robot_message = PointStamped()
        robot_message.header = fused_message.header
        robot_message.header.frame_id = 'base_link'
        robot_message.point.x = float(robot_corrected[0])
        robot_message.point.y = float(robot_corrected[1])
        robot_message.point.z = float(robot_corrected[2])

        self.robot_corrected_publisher.publish(
            robot_message
        )

        self.publish_status({
            'accepted': True,
            'reason': 'weighted_fusion',
            'point_difference_mm': difference_mm,
            'timestamp_skew_ms': skew_ms,
            'ihawk1_depth_std_mm': sigma1,
            'ihawk2_depth_std_mm': sigma2,
            'ihawk1_weight': weight1 / (weight1 + weight2),
            'ihawk2_weight': weight2 / (weight1 + weight2),
            'ihawk1_corrected_base_m': corrected1.tolist(),
            'ihawk2_base_m': value2.tolist(),
            'fused_base_m': fused.tolist(),
            'robot_corrected_base_m': robot_corrected.tolist(),
        })


def main(args=None):
    rclpy.init(args=args)
    node = DualPointFusion()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
