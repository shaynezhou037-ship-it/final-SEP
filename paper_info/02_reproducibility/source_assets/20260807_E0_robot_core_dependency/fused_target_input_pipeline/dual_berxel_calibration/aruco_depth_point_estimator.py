#!/usr/bin/env python3

import json
from collections import deque

import cv2
import numpy as np
import rclpy
from rclpy.executors import MultiThreadedExecutor
from geometry_msgs.msg import PointStamped
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import String
from tf2_geometry_msgs import do_transform_point
from tf2_ros import Buffer, TransformException, TransformListener


class ArucoDepthPointEstimator(Node):

    def __init__(self):
        super().__init__('aruco_depth_point_estimator')

        self.declare_parameter('target_marker_id', 4)
        self.declare_parameter('roi_radius', 4)
        self.declare_parameter('minimum_valid_pixels', 20)
        self.declare_parameter('maximum_skew_ms', 60.0)

        self.target_id = int(
            self.get_parameter('target_marker_id').value
        )
        self.roi_radius = int(
            self.get_parameter('roi_radius').value
        )
        self.minimum_valid_pixels = int(
            self.get_parameter('minimum_valid_pixels').value
        )
        self.maximum_skew_ms = float(
            self.get_parameter('maximum_skew_ms').value
        )

        qos = QoSProfile(depth=5)
        qos.reliability = ReliabilityPolicy.RELIABLE
        qos.durability = DurabilityPolicy.VOLATILE

        dictionary = cv2.aruco.getPredefinedDictionary(
            cv2.aruco.DICT_4X4_50
        )
        parameters = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(
            dictionary,
            parameters,
        )

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(
            self.tf_buffer,
            self,
        )

        self.state = {}
        self._subscriptions = []

        for camera in ('ihawk1', 'ihawk2'):
            self.state[camera] = {
                'depth_buffer': deque(maxlen=60),
                'depth_info': None,
            }

            self.state[camera]['camera_publisher'] = (
                self.create_publisher(
                    PointStamped,
                    f'/{camera}/target_point_camera',
                    10,
                )
            )
            self.state[camera]['base_publisher'] = (
                self.create_publisher(
                    PointStamped,
                    f'/{camera}/target_point_base',
                    10,
                )
            )
            self.state[camera]['quality_publisher'] = (
                self.create_publisher(
                    String,
                    f'/{camera}/target_quality',
                    10,
                )
            )

            self._subscriptions.append(
                self.create_subscription(
                    Image,
                    f'/{camera}/depth/depth_raw',
                    lambda msg, name=camera:
                    self.depth_callback(name, msg),
                    qos,
                )
            )
            self._subscriptions.append(
                self.create_subscription(
                    CameraInfo,
                    f'/{camera}/depth/camera_info',
                    lambda msg, name=camera:
                    self.info_callback(name, msg),
                    qos,
                )
            )
            self._subscriptions.append(
                self.create_subscription(
                    Image,
                    f'/{camera}/color/color_raw',
                    lambda msg, name=camera:
                    self.color_callback(name, msg),
                    qos,
                )
            )

        self.get_logger().info(
            f'Aruco depth estimator started. '
            f'Target ID={self.target_id}.'
        )

    @staticmethod
    def stamp_seconds(stamp):
        return stamp.sec + stamp.nanosec * 1.0e-9

    @staticmethod
    def color_to_bgr(msg):
        rows = np.frombuffer(
            msg.data,
            dtype=np.uint8,
        ).reshape(msg.height, msg.step)

        image = rows[:, :msg.width * 3].reshape(
            msg.height,
            msg.width,
            3,
        )

        if msg.encoding.lower() == 'rgb8':
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        return image.copy()

    @staticmethod
    def depth_to_array(msg):
        pixels_per_row = msg.step // 2
        rows = np.frombuffer(
            msg.data,
            dtype=np.uint16,
        ).reshape(msg.height, pixels_per_row)

        return rows[:, :msg.width].copy()

    def depth_callback(self, camera, msg):
        self.state[camera]['depth_buffer'].append(msg)

    def info_callback(self, camera, msg):
        self.state[camera]['depth_info'] = msg

    def publish_quality(self, camera, values):
        message = String()
        message.data = json.dumps(values)
        self.state[camera]['quality_publisher'].publish(message)

    def color_callback(self, camera, color_msg):
        depth_buffer = self.state[camera]['depth_buffer']
        camera_info = self.state[camera]['depth_info']

        if not depth_buffer or camera_info is None:
            return

        color_time_for_match = self.stamp_seconds(
            color_msg.header.stamp
        )
        depth_msg = min(
            depth_buffer,
            key=lambda message: abs(
                self.stamp_seconds(message.header.stamp)
                - color_time_for_match
            ),
        )

        try:
            color_image = self.color_to_bgr(color_msg)
            depth_image = self.depth_to_array(depth_msg)
        except (ValueError, TypeError) as error:
            self.get_logger().warning(
                f'{camera}: image conversion failed: {error}'
            )
            return

        if color_image.shape[:2] != depth_image.shape:
            self.publish_quality(camera, {
                'camera': camera,
                'marker_id': self.target_id,
                'accepted': False,
                'reason': 'color_depth_size_mismatch',
            })
            return

        corners, ids, _ = self.detector.detectMarkers(
            color_image
        )

        if ids is None:
            return

        ids_flat = ids.flatten().astype(int)
        matches = np.where(ids_flat == self.target_id)[0]

        if len(matches) == 0:
            return

        marker_corners = corners[int(matches[0])][0]
        center = np.mean(marker_corners, axis=0)

        u = int(round(float(center[0])))
        v = int(round(float(center[1])))

        height, width = depth_image.shape
        radius = self.roi_radius

        x0 = max(0, u - radius)
        x1 = min(width, u + radius + 1)
        y0 = max(0, v - radius)
        y1 = min(height, v + radius + 1)

        roi = depth_image[y0:y1, x0:x1]
        valid = roi[(roi > 0) & (roi < 10000)]

        color_time = self.stamp_seconds(
            color_msg.header.stamp
        )
        depth_time = self.stamp_seconds(
            depth_msg.header.stamp
        )
        skew_ms = abs(color_time - depth_time) * 1000.0

        if valid.size < self.minimum_valid_pixels:
            self.publish_quality(camera, {
                'camera': camera,
                'marker_id': self.target_id,
                'accepted': False,
                'reason': 'insufficient_depth_pixels',
                'valid_depth_pixels': int(valid.size),
                'timestamp_skew_ms': skew_ms,
            })
            return

        if skew_ms > self.maximum_skew_ms:
            self.publish_quality(camera, {
                'camera': camera,
                'marker_id': self.target_id,
                'accepted': False,
                'reason': 'timestamp_skew',
                'valid_depth_pixels': int(valid.size),
                'timestamp_skew_ms': skew_ms,
            })
            return

        median_mm = float(np.median(valid))
        std_mm = float(np.std(valid))
        mad_mm = float(
            np.median(np.abs(valid - median_mm))
        )

        z = median_mm / 1000.0

        fx = float(camera_info.k[0])
        fy = float(camera_info.k[4])
        cx = float(camera_info.k[2])
        cy = float(camera_info.k[5])

        x = (u - cx) * z / fx
        y = (v - cy) * z / fy

        point_camera = PointStamped()
        point_camera.header.stamp = depth_msg.header.stamp
        point_camera.header.frame_id = (
            camera_info.header.frame_id
        )
        point_camera.point.x = x
        point_camera.point.y = y
        point_camera.point.z = z

        self.state[camera][
            'camera_publisher'
        ].publish(point_camera)

        transformed = False
        transform_source = 'none'

        try:
            transform = self.tf_buffer.lookup_transform(
                'base_link',
                point_camera.header.frame_id,
                Time(),
            )
            point_base = do_transform_point(
                point_camera,
                transform,
            )
            transform_source = 'tf2'
            transformed = True

        except TransformException:
            fixed = {
                'ihawk1': {
                    't': [0.5504684463, 0.3366870988, 0.1909076807],
                    'q': [0.2835615600, 0.7827647848,
                          -0.5038852795, -0.2301559438],
                },
                'ihawk2': {
                    't': [0.6029966119, -0.0867445117, 0.1863700234],
                    'q': [0.6259837936, 0.5363969986,
                          -0.3801877032, -0.4193803291],
                },
            }[camera]

            qx, qy, qz, qw = fixed['q']
            rotation = np.array([
                [
                    1 - 2 * (qy*qy + qz*qz),
                    2 * (qx*qy - qz*qw),
                    2 * (qx*qz + qy*qw),
                ],
                [
                    2 * (qx*qy + qz*qw),
                    1 - 2 * (qx*qx + qz*qz),
                    2 * (qy*qz - qx*qw),
                ],
                [
                    2 * (qx*qz - qy*qw),
                    2 * (qy*qz + qx*qw),
                    1 - 2 * (qx*qx + qy*qy),
                ],
            ])

            camera_xyz = np.array([
                point_camera.point.x,
                point_camera.point.y,
                point_camera.point.z,
            ])
            base_xyz = (
                rotation @ camera_xyz
                + np.array(fixed['t'])
            )

            point_base = PointStamped()
            point_base.header.stamp = point_camera.header.stamp
            point_base.header.frame_id = 'base_link'
            point_base.point.x = float(base_xyz[0])
            point_base.point.y = float(base_xyz[1])
            point_base.point.z = float(base_xyz[2])

            transform_source = 'corrected_calibration_fallback'
            transformed = True

        self.state[camera][
            'base_publisher'
        ].publish(point_base)

        self.publish_quality(camera, {
            'camera': camera,
            'marker_id': self.target_id,
            'accepted': transformed,
            'center_u': u,
            'center_v': v,
            'valid_depth_pixels': int(valid.size),
            'depth_median_mm': median_mm,
            'depth_std_mm': std_mm,
            'depth_mad_mm': mad_mm,
            'timestamp_skew_ms': skew_ms,
            'camera_frame': point_camera.header.frame_id,
            'transformed_to_base': transformed,
            'transform_source': transform_source,
        })


def main(args=None):
    rclpy.init(args=args)
    node = ArucoDepthPointEstimator()

    try:
        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(node)
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
