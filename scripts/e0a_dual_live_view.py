#!/usr/bin/env python3
"""
Dual iHawk live ArUco viewer for E0-A placement checks.

Shows ihawk1 and ihawk2 RGB streams side-by-side and overlays:
- image center crosshair
- ArUco ID 4 outline
- subpixel marker center (u, v)
- visibility status

Keys:
  q / ESC : quit
  s       : save current combined screenshot
"""

import os
from datetime import datetime

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


TOPICS = {
    "ihawk1": "/ihawk1/color/color_raw",
    "ihawk2": "/ihawk2/color/color_raw",
}


class DualViewer(Node):
    def __init__(self):
        super().__init__("e0a_dual_live_view")
        self.bridge = CvBridge()
        self.frames = {}
        self.marker_id = 4

        self.dictionary = cv2.aruco.getPredefinedDictionary(
            cv2.aruco.DICT_4X4_50
        )
        self.params = cv2.aruco.DetectorParameters_create()
        self.params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.params.cornerRefinementWinSize = 5
        self.params.cornerRefinementMaxIterations = 50
        self.params.cornerRefinementMinAccuracy = 0.01

        self.subs = []
        for name, topic in TOPICS.items():
            self.subs.append(
                self.create_subscription(
                    Image,
                    topic,
                    lambda msg, n=name: self.callback(n, msg),
                    qos_profile_sensor_data,
                )
            )

    def callback(self, name, msg):
        try:
            rgb = self.bridge.imgmsg_to_cv2(msg, desired_encoding="rgb8")
            self.frames[name] = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception as exc:
            self.get_logger().warning(f"{name}: {exc}")

    def annotate(self, name, frame):
        out = frame.copy()
        h, w = out.shape[:2]

        # Image-center crosshair
        cx_img, cy_img = w // 2, h // 2
        cv2.drawMarker(
            out,
            (cx_img, cy_img),
            (255, 255, 0),
            markerType=cv2.MARKER_CROSS,
            markerSize=24,
            thickness=1,
        )

        gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(
            gray,
            self.dictionary,
            parameters=self.params,
        )

        found = False
        u = v = None

        if ids is not None:
            for i, mid in enumerate(ids.flatten().astype(int)):
                if mid != self.marker_id:
                    continue

                pts = corners[i].reshape(4, 2)
                center = pts.mean(axis=0)
                u, v = float(center[0]), float(center[1])

                cv2.aruco.drawDetectedMarkers(
                    out,
                    [corners[i]],
                    np.array([[mid]], dtype=np.int32),
                )

                cv2.circle(
                    out,
                    (int(round(u)), int(round(v))),
                    6,
                    (0, 0, 255),
                    -1,
                )

                found = True
                break

        title = f"{name} | ArUco ID {self.marker_id}"

        if found:
            status = f"VISIBLE  u={u:.1f}  v={v:.1f}"
            status_color = (0, 255, 0)
        else:
            status = "NOT DETECTED"
            status_color = (0, 0, 255)

        cv2.rectangle(out, (0, 0), (w, 58), (0, 0, 0), -1)
        cv2.putText(
            out,
            title,
            (10, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            out,
            status,
            (10, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            status_color,
            2,
            cv2.LINE_AA,
        )

        # Margin guide: avoid placing marker too close to image boundary
        margin = 25
        cv2.rectangle(
            out,
            (margin, margin + 40),
            (w - margin, h - margin),
            (180, 180, 180),
            1,
        )

        return out

    def combined_frame(self):
        if "ihawk1" not in self.frames or "ihawk2" not in self.frames:
            return None

        a = self.annotate("ihawk1", self.frames["ihawk1"])
        b = self.annotate("ihawk2", self.frames["ihawk2"])

        if a.shape[0] != b.shape[0]:
            target_h = min(a.shape[0], b.shape[0])
            a = cv2.resize(a, (int(a.shape[1] * target_h / a.shape[0]), target_h))
            b = cv2.resize(b, (int(b.shape[1] * target_h / b.shape[0]), target_h))

        return np.hstack([a, b])


def main():
    rclpy.init()
    node = DualViewer()

    save_dir = "/mnt/c/Users/ASUS/Desktop/paper/E0/E0_A_camera_static/raw"
    os.makedirs(save_dir, exist_ok=True)

    window = "E0-A Placement Check | ihawk1 + ihawk2"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1280, 500)

    print("Live viewer started.")
    print("Move the marker by hand and watch BOTH views.")
    print("q / ESC = quit, s = save screenshot")

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.01)

            combined = node.combined_frame()
            if combined is None:
                continue

            cv2.imshow(window, combined)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), 27):
                break

            if key == ord("s"):
                path = os.path.join(
                    save_dir,
                    "placement_check_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".png",
                )
                cv2.imwrite(path, combined)
                print("Saved:", path)

    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
