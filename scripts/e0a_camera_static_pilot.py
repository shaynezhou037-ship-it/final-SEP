#!/usr/bin/env python3

import argparse
import csv
import json
import os
import time
from datetime import datetime

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image


CAMERAS = {
    "ihawk1": {
        "serial": "HK100QB6513M2B479",
        "color_topic": "/ihawk1/color/color_raw",
        "depth_topic": "/ihawk1/depth/depth_raw",
        "info_topic": "/ihawk1/depth/camera_info",
    },
    "ihawk2": {
        "serial": "HK100QB5311M2B242",
        "color_topic": "/ihawk2/color/color_raw",
        "depth_topic": "/ihawk2/depth/depth_raw",
        "info_topic": "/ihawk2/depth/camera_info",
    },
}


def stamp_sec(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


class E0APilot(Node):
    def __init__(self, args):
        super().__init__("e0a_camera_static_pilot")
        self.args = args
        self.bridge = CvBridge()

        self.colors = {}
        self.depths = {}
        self.infos = {}

        self.rows = []
        self.counts = {name: 0 for name in CAMERAS}
        self.last_sample_wall = {name: 0.0 for name in CAMERAS}
        self.last_sample_stamp = {name: None for name in CAMERAS}
        self.locked_marker = {name: None for name in CAMERAS}

        if not hasattr(cv2, "aruco"):
            raise RuntimeError("cv2.aruco is unavailable")

        if not hasattr(cv2.aruco, args.dictionary):
            raise RuntimeError(f"Unknown ArUco dictionary: {args.dictionary}")

        dict_id = getattr(cv2.aruco, args.dictionary)
        self.dictionary = cv2.aruco.getPredefinedDictionary(dict_id)
        self.detector_params = cv2.aruco.DetectorParameters_create()

        for name, cfg in CAMERAS.items():
            self.create_subscription(
                Image,
                cfg["color_topic"],
                lambda msg, n=name: self._color_cb(n, msg),
                qos_profile_sensor_data,
            )
            self.create_subscription(
                Image,
                cfg["depth_topic"],
                lambda msg, n=name: self._depth_cb(n, msg),
                qos_profile_sensor_data,
            )
            self.create_subscription(
                CameraInfo,
                cfg["info_topic"],
                lambda msg, n=name: self._info_cb(n, msg),
                qos_profile_sensor_data,
            )

    def _color_cb(self, name, msg):
        self.colors[name] = msg

    def _depth_cb(self, name, msg):
        self.depths[name] = msg

    def _info_cb(self, name, msg):
        self.infos[name] = msg

    def finished(self):
        return all(self.counts[name] >= self.args.samples for name in CAMERAS)

    def try_sample_all(self, raw_dir):
        for name in CAMERAS:
            self.try_sample(name, raw_dir)

    def try_sample(self, name, raw_dir):
        if self.counts[name] >= self.args.samples:
            return
        if name not in self.colors or name not in self.depths or name not in self.infos:
            return

        now = time.time()
        if now - self.last_sample_wall[name] < self.args.sample_interval:
            return

        color_msg = self.colors[name]
        depth_msg = self.depths[name]
        info_msg = self.infos[name]

        color_stamp = stamp_sec(color_msg)
        depth_stamp = stamp_sec(depth_msg)

        if self.last_sample_stamp[name] == color_stamp:
            return

        dt_ms = abs(color_stamp - depth_stamp) * 1000.0
        if dt_ms > self.args.max_rgb_depth_dt_ms:
            return

        try:
            rgb = self.bridge.imgmsg_to_cv2(color_msg, desired_encoding="rgb8")
            depth = self.bridge.imgmsg_to_cv2(depth_msg, desired_encoding="passthrough")
        except Exception as exc:
            self.get_logger().warning(f"{name}: cv_bridge failed: {exc}")
            return

        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(
            gray, self.dictionary, parameters=self.detector_params
        )

        if ids is None or len(ids) == 0:
            return

        candidates = []
        for i, marker_id in enumerate(ids.flatten().astype(int)):
            pts = corners[i].reshape(4, 2).astype(np.float32)
            area = abs(float(cv2.contourArea(pts)))
            candidates.append((int(marker_id), area, pts, i))

        target_id = self.args.marker_id

        if target_id < 0:
            if self.locked_marker[name] is None:
                chosen = max(candidates, key=lambda x: x[1])
                self.locked_marker[name] = chosen[0]
                self.get_logger().info(
                    f"{name}: auto-locked marker ID {self.locked_marker[name]}"
                )
            target_id = self.locked_marker[name]

        matches = [c for c in candidates if c[0] == target_id]
        if not matches:
            return

        marker_id, area_px2, pts, marker_index = max(matches, key=lambda x: x[1])

        center = pts.mean(axis=0)
        u = float(center[0])
        v = float(center[1])
        ui = int(round(u))
        vi = int(round(v))

        h, w = depth.shape[:2]
        half = self.args.patch_size // 2
        x0 = max(0, ui - half)
        x1 = min(w, ui + half + 1)
        y0 = max(0, vi - half)
        y1 = min(h, vi + half + 1)

        patch = depth[y0:y1, x0:x1]
        if patch.size == 0:
            return

        valid_mask = (patch > 0) & (patch < 65535)
        valid = patch[valid_mask]

        valid_count = int(valid.size)
        valid_ratio = float(valid_count / patch.size)

        if valid_count == 0 or valid_ratio < self.args.min_valid_ratio:
            return

        depth_median = float(np.median(valid))
        depth_mean = float(np.mean(valid))
        depth_std = float(np.std(valid, ddof=1)) if valid_count > 1 else 0.0

        K = np.array(info_msg.k, dtype=float).reshape(3, 3)
        fx, fy = K[0, 0], K[1, 1]
        cx, cy = K[0, 2], K[1, 2]

        # XYZ use the same native unit as the mono16 depth image.
        z_native = depth_median
        x_native = (u - cx) * z_native / fx
        y_native = (v - cy) * z_native / fy

        row = {
            "camera_id": name,
            "serial": CAMERAS[name]["serial"],
            "sample_index": self.counts[name] + 1,
            "wall_time_iso": datetime.now().isoformat(timespec="milliseconds"),
            "color_stamp_s": color_stamp,
            "depth_stamp_s": depth_stamp,
            "color_depth_dt_ms": dt_ms,
            "marker_id": marker_id,
            "u_px": u,
            "v_px": v,
            "marker_area_px2": area_px2,
            "depth_patch_size": self.args.patch_size,
            "depth_valid_count": valid_count,
            "depth_valid_ratio": valid_ratio,
            "depth_median_raw": depth_median,
            "depth_mean_raw": depth_mean,
            "depth_std_raw": depth_std,
            "x_cam_raw": x_native,
            "y_cam_raw": y_native,
            "z_cam_raw": z_native,
            "fx": fx,
            "fy": fy,
            "cx": cx,
            "cy": cy,
            "color_frame_id": color_msg.header.frame_id,
            "depth_frame_id": depth_msg.header.frame_id,
        }

        self.rows.append(row)
        self.counts[name] += 1
        self.last_sample_wall[name] = now
        self.last_sample_stamp[name] = color_stamp

        print(
            f"[{name}] {self.counts[name]:02d}/{self.args.samples} "
            f"id={marker_id} "
            f"u={u:.2f} v={v:.2f} "
            f"depth_raw={depth_median:.1f} "
            f"valid={valid_ratio:.2f} "
            f"dt={dt_ms:.1f} ms "
            f"XYZ_raw=({x_native:.2f}, {y_native:.2f}, {z_native:.2f})"
        )

        if self.counts[name] == 1:
            annotated = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            cv2.aruco.drawDetectedMarkers(
                annotated,
                [corners[marker_index]],
                np.array([[marker_id]], dtype=np.int32),
            )
            cv2.circle(annotated, (ui, vi), 5, (0, 0, 255), -1)
            cv2.putText(
                annotated,
                f"{name} id={marker_id} u={u:.1f} v={v:.1f} depth={depth_median:.1f}",
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )
            cv2.imwrite(
                os.path.join(raw_dir, f"{name}_first_detection.png"),
                annotated,
            )


def summarize(rows):
    summary = {}

    for camera in CAMERAS:
        sub = [r for r in rows if r["camera_id"] == camera]

        if not sub:
            summary[camera] = {"n": 0}
            continue

        result = {
            "n": len(sub),
            "serial": CAMERAS[camera]["serial"],
            "marker_ids": sorted(set(int(r["marker_id"]) for r in sub)),
        }

        fields = [
            "u_px",
            "v_px",
            "depth_median_raw",
            "x_cam_raw",
            "y_cam_raw",
            "z_cam_raw",
            "color_depth_dt_ms",
            "depth_valid_ratio",
            "marker_area_px2",
        ]

        for field in fields:
            x = np.array([float(r[field]) for r in sub], dtype=float)
            result[field] = {
                "mean": float(np.mean(x)),
                "sd": float(np.std(x, ddof=1)) if len(x) > 1 else 0.0,
                "min": float(np.min(x)),
                "max": float(np.max(x)),
                "range": float(np.max(x) - np.min(x)),
                "p05": float(np.percentile(x, 5)),
                "p95": float(np.percentile(x, 95)),
            }

        xs = np.array([r["x_cam_raw"] for r in sub], dtype=float)
        ys = np.array([r["y_cam_raw"] for r in sub], dtype=float)

        radial = np.sqrt((xs - xs.mean()) ** 2 + (ys - ys.mean()) ** 2)

        result["xy_radial_deviation_raw"] = {
            "mean": float(radial.mean()),
            "sd": float(np.std(radial, ddof=1)) if len(radial) > 1 else 0.0,
            "max": float(radial.max()),
            "p95": float(np.percentile(radial, 95)),
        }

        summary[camera] = result

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--sample-interval", type=float, default=0.20)
    parser.add_argument("--dictionary", type=str, default="DICT_4X4_50")
    parser.add_argument("--marker-id", type=int, default=-1)
    parser.add_argument("--patch-size", type=int, default=9)
    parser.add_argument("--min-valid-ratio", type=float, default=0.50)
    parser.add_argument("--max-rgb-depth-dt-ms", type=float, default=80.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--output-root",
        type=str,
        default="/mnt/c/Users/ASUS/Desktop/paper/E0/E0_A_camera_static",
    )
    args = parser.parse_args()

    if args.patch_size % 2 == 0:
        raise ValueError("--patch-size must be odd")

    raw_dir = os.path.join(args.output_root, "raw")
    results_dir = os.path.join(args.output_root, "results")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(raw_dir, f"E0A_center_pilot_{run_id}.csv")
    summary_path = os.path.join(
        results_dir, f"E0A_center_pilot_summary_{run_id}.json"
    )
    metadata_path = os.path.join(
        raw_dir, f"E0A_center_pilot_metadata_{run_id}.json"
    )

    rclpy.init()
    node = E0APilot(args)

    print("\n==========================================")
    print("E0-A Camera Static Repeatability PILOT")
    print("==========================================")
    print(f"Dictionary       : {args.dictionary}")
    print(f"Marker ID        : {args.marker_id} (-1 = auto)")
    print(f"Samples/camera   : {args.samples}")
    print(f"Sample interval  : {args.sample_interval} s")
    print(f"Depth patch      : {args.patch_size}x{args.patch_size}")
    print("Depth unit       : UNVERIFIED mono16 native units")
    print("Position         : center")
    print("==========================================\n")

    start = time.time()

    try:
        while rclpy.ok() and not node.finished():
            rclpy.spin_once(node, timeout_sec=0.05)
            node.try_sample_all(raw_dir)

            if time.time() - start > args.timeout:
                print("\nTIMEOUT")
                break
    finally:
        rows = list(node.rows)

        camera_info_meta = {}
        for camera, msg in node.infos.items():
            camera_info_meta[camera] = {
                "serial": CAMERAS[camera]["serial"],
                "frame_id": msg.header.frame_id,
                "width": int(msg.width),
                "height": int(msg.height),
                "distortion_model": msg.distortion_model,
                "D": list(msg.d),
                "K": list(msg.k),
                "P": list(msg.p),
            }

        metadata = {
            "experiment": "E0-A Camera Static Repeatability",
            "phase": "center_pilot",
            "run_id": run_id,
            "dictionary": args.dictionary,
            "requested_marker_id": args.marker_id,
            "locked_marker_ids": node.locked_marker,
            "samples_requested_per_camera": args.samples,
            "sample_interval_s": args.sample_interval,
            "depth_patch_size": args.patch_size,
            "min_valid_ratio": args.min_valid_ratio,
            "max_rgb_depth_dt_ms": args.max_rgb_depth_dt_ms,
            "depth_encoding": "mono16",
            "depth_unit_status": "UNVERIFIED_NATIVE_UNIT",
            "camera_info": camera_info_meta,
            "camera_mapping": CAMERAS,
        }

        if rows:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        summary = summarize(rows)

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        node.destroy_node()
        rclpy.shutdown()

    print("\n==========================================")
    print("PILOT COMPLETE")
    print("==========================================")
    print("counts:", node.counts)
    print("CSV     :", csv_path)
    print("metadata:", metadata_path)
    print("summary :", summary_path)

    print("\n--- QUICK SUMMARY ---")
    for camera, result in summary.items():
        print(f"\n{camera}")

        if result.get("n", 0) == 0:
            print("  NO VALID SAMPLES")
            continue

        print("  n:", result["n"])
        print("  marker IDs:", result["marker_ids"])
        print(f'  u SD: {result["u_px"]["sd"]:.4f} px')
        print(f'  v SD: {result["v_px"]["sd"]:.4f} px')
        print(f'  depth SD: {result["depth_median_raw"]["sd"]:.4f} raw')
        print(f'  X SD: {result["x_cam_raw"]["sd"]:.4f} raw')
        print(f'  Y SD: {result["y_cam_raw"]["sd"]:.4f} raw')
        print(
            f'  XY radial P95: '
            f'{result["xy_radial_deviation_raw"]["p95"]:.4f} raw'
        )
        print(
            f'  depth valid ratio mean: '
            f'{result["depth_valid_ratio"]["mean"]:.3f}'
        )
        print(
            f'  RGB-depth dt mean: '
            f'{result["color_depth_dt_ms"]["mean"]:.2f} ms'
        )


if __name__ == "__main__":
    main()
