#!/usr/bin/env python3
"""
E0-A Camera Static Repeatability - v2

Purpose
-------
Measure short-term static localization repeatability for two Berxel iHawk100
cameras using a fixed ArUco marker.

Key v2 changes
--------------
1. Enables ArUco subpixel corner refinement.
2. Supports pilot/formal phases.
3. Supports position labels: center/left/right/near/far.
4. Uses explicit marker ID 4 by default.
5. Saves run-specific CSV, metadata JSON, summary JSON, and annotated images.
6. Keeps depth/XYZ in native mono16 units unless an explicit mm scale is given.
"""

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

VALID_POSITIONS = ["center", "left", "right", "near", "far"]
VALID_PHASES = ["pilot", "formal"]


def stamp_sec(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


class E0ACollector(Node):
    def __init__(self, args):
        super().__init__("e0a_camera_static_v2")

        self.args = args
        self.bridge = CvBridge()

        self.colors = {}
        self.depths = {}
        self.infos = {}

        self.rows = []
        self.counts = {name: 0 for name in CAMERAS}
        self.last_sample_wall = {name: 0.0 for name in CAMERAS}
        self.last_sample_stamp = {name: None for name in CAMERAS}

        if not hasattr(cv2, "aruco"):
            raise RuntimeError("cv2.aruco is unavailable")

        if not hasattr(cv2.aruco, args.dictionary):
            raise RuntimeError(f"Unknown ArUco dictionary: {args.dictionary}")

        dict_id = getattr(cv2.aruco, args.dictionary)
        self.dictionary = cv2.aruco.getPredefinedDictionary(dict_id)

        self.detector_params = cv2.aruco.DetectorParameters_create()

        # ---- v2: subpixel refinement ----
        self.detector_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector_params.cornerRefinementWinSize = args.subpix_win_size
        self.detector_params.cornerRefinementMaxIterations = args.subpix_max_iterations
        self.detector_params.cornerRefinementMinAccuracy = args.subpix_min_accuracy

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
        return all(
            self.counts[name] >= self.args.samples
            for name in CAMERAS
        )

    def try_sample_all(self, raw_dir, run_id):
        for name in CAMERAS:
            self.try_sample(name, raw_dir, run_id)

    def try_sample(self, name, raw_dir, run_id):
        if self.counts[name] >= self.args.samples:
            return

        if (
            name not in self.colors
            or name not in self.depths
            or name not in self.infos
        ):
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
            rgb = self.bridge.imgmsg_to_cv2(
                color_msg,
                desired_encoding="rgb8",
            )
            depth = self.bridge.imgmsg_to_cv2(
                depth_msg,
                desired_encoding="passthrough",
            )
        except Exception as exc:
            self.get_logger().warning(
                f"{name}: cv_bridge failed: {exc}"
            )
            return

        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

        corners, ids, _ = cv2.aruco.detectMarkers(
            gray,
            self.dictionary,
            parameters=self.detector_params,
        )

        if ids is None or len(ids) == 0:
            return

        ids_flat = ids.flatten().astype(int)

        matches = []

        for i, marker_id in enumerate(ids_flat):
            if int(marker_id) != self.args.marker_id:
                continue

            pts = corners[i].reshape(4, 2).astype(np.float32)
            area = abs(float(cv2.contourArea(pts)))

            matches.append(
                (int(marker_id), area, pts, i)
            )

        if not matches:
            return

        marker_id, area_px2, pts, marker_index = max(
            matches,
            key=lambda x: x[1]
        )

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

        if valid_count == 0:
            return

        if valid_ratio < self.args.min_valid_ratio:
            return

        depth_median_raw = float(np.median(valid))
        depth_mean_raw = float(np.mean(valid))
        depth_std_raw = (
            float(np.std(valid, ddof=1))
            if valid_count > 1
            else 0.0
        )

        K = np.array(
            info_msg.k,
            dtype=float,
        ).reshape(3, 3)

        fx = float(K[0, 0])
        fy = float(K[1, 1])
        cx = float(K[0, 2])
        cy = float(K[1, 2])

        z_raw = depth_median_raw
        x_raw = (u - cx) * z_raw / fx
        y_raw = (v - cy) * z_raw / fy

        row = {
            "experiment": "E0-A",
            "phase": self.args.phase,
            "position": self.args.position,
            "camera_id": name,
            "serial": CAMERAS[name]["serial"],
            "sample_index": self.counts[name] + 1,
            "wall_time_iso": datetime.now().isoformat(
                timespec="milliseconds"
            ),
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
            "depth_median_raw": depth_median_raw,
            "depth_mean_raw": depth_mean_raw,
            "depth_std_raw": depth_std_raw,
            "x_cam_raw": x_raw,
            "y_cam_raw": y_raw,
            "z_cam_raw": z_raw,
            "fx": fx,
            "fy": fy,
            "cx": cx,
            "cy": cy,
            "color_frame_id": color_msg.header.frame_id,
            "depth_frame_id": depth_msg.header.frame_id,
        }

        if self.args.depth_scale_mm is not None:
            scale = self.args.depth_scale_mm
            row["depth_median_mm"] = depth_median_raw * scale
            row["x_cam_mm"] = x_raw * scale
            row["y_cam_mm"] = y_raw * scale
            row["z_cam_mm"] = z_raw * scale

        self.rows.append(row)

        self.counts[name] += 1
        self.last_sample_wall[name] = now
        self.last_sample_stamp[name] = color_stamp

        extra = ""
        if self.args.depth_scale_mm is not None:
            extra = (
                f" Z_mm={row['z_cam_mm']:.2f}"
            )

        print(
            f"[{name}] "
            f"{self.counts[name]:02d}/{self.args.samples}  "
            f"id={marker_id}  "
            f"u={u:.3f} v={v:.3f}  "
            f"depth_raw={depth_median_raw:.1f}  "
            f"valid={valid_ratio:.2f}  "
            f"dt={dt_ms:.1f} ms  "
            f"XYZ_raw=({x_raw:.3f}, "
            f"{y_raw:.3f}, {z_raw:.3f})"
            f"{extra}"
        )

        if self.counts[name] == 1:
            annotated = cv2.cvtColor(
                rgb,
                cv2.COLOR_RGB2BGR,
            )

            cv2.aruco.drawDetectedMarkers(
                annotated,
                [corners[marker_index]],
                np.array(
                    [[marker_id]],
                    dtype=np.int32,
                ),
            )

            cv2.circle(
                annotated,
                (ui, vi),
                5,
                (0, 0, 255),
                -1,
            )

            cv2.putText(
                annotated,
                (
                    f"{self.args.position} {name} "
                    f"id={marker_id} "
                    f"u={u:.2f} v={v:.2f} "
                    f"depth={depth_median_raw:.1f}"
                ),
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

            image_path = os.path.join(
                raw_dir,
                (
                    f"E0A_{self.args.phase}_"
                    f"{self.args.position}_{name}_"
                    f"{run_id}_first_detection.png"
                ),
            )

            cv2.imwrite(
                image_path,
                annotated,
            )


def stats_block(values):
    x = np.array(
        values,
        dtype=float,
    )

    return {
        "mean": float(np.mean(x)),
        "sd": (
            float(np.std(x, ddof=1))
            if len(x) > 1
            else 0.0
        ),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
        "range": float(np.max(x) - np.min(x)),
        "p05": float(np.percentile(x, 5)),
        "p50": float(np.percentile(x, 50)),
        "p95": float(np.percentile(x, 95)),
    }


def summarize(rows, args):
    summary = {
        "experiment": "E0-A",
        "phase": args.phase,
        "position": args.position,
        "samples_requested_per_camera": args.samples,
        "subpixel_refinement": True,
        "cameras": {},
    }

    for camera in CAMERAS:
        sub = [
            r for r in rows
            if r["camera_id"] == camera
        ]

        if not sub:
            summary["cameras"][camera] = {
                "n": 0
            }
            continue

        result = {
            "n": len(sub),
            "serial": CAMERAS[camera]["serial"],
            "marker_ids": sorted(
                set(
                    int(r["marker_id"])
                    for r in sub
                )
            ),
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

        if args.depth_scale_mm is not None:
            fields.extend([
                "depth_median_mm",
                "x_cam_mm",
                "y_cam_mm",
                "z_cam_mm",
            ])

        for field in fields:
            result[field] = stats_block(
                [float(r[field]) for r in sub]
            )

        xs = np.array(
            [r["x_cam_raw"] for r in sub],
            dtype=float,
        )

        ys = np.array(
            [r["y_cam_raw"] for r in sub],
            dtype=float,
        )

        radial = np.sqrt(
            (xs - xs.mean()) ** 2
            + (ys - ys.mean()) ** 2
        )

        result["xy_radial_deviation_raw"] = stats_block(
            radial
        )

        if args.depth_scale_mm is not None:
            radial_mm = radial * args.depth_scale_mm
            result["xy_radial_deviation_mm"] = stats_block(
                radial_mm
            )

        summary["cameras"][camera] = result

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="E0-A Camera Static Repeatability v2"
    )

    parser.add_argument(
        "--phase",
        choices=VALID_PHASES,
        default="formal",
        help="pilot or formal",
    )

    parser.add_argument(
        "--position",
        choices=VALID_POSITIONS,
        required=True,
        help="workspace target position",
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=None,
        help=(
            "accepted samples per camera; "
            "default=10 for pilot, 50 for formal"
        ),
    )

    parser.add_argument(
        "--sample-interval",
        type=float,
        default=0.20,
    )

    parser.add_argument(
        "--dictionary",
        type=str,
        default="DICT_4X4_50",
    )

    parser.add_argument(
        "--marker-id",
        type=int,
        default=4,
    )

    parser.add_argument(
        "--patch-size",
        type=int,
        default=9,
    )

    parser.add_argument(
        "--min-valid-ratio",
        type=float,
        default=0.50,
    )

    parser.add_argument(
        "--max-rgb-depth-dt-ms",
        type=float,
        default=80.0,
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
    )

    parser.add_argument(
        "--subpix-win-size",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--subpix-max-iterations",
        type=int,
        default=50,
    )

    parser.add_argument(
        "--subpix-min-accuracy",
        type=float,
        default=0.01,
    )

    parser.add_argument(
        "--depth-scale-mm",
        type=float,
        default=None,
        help=(
            "optional conversion from native depth units to mm. "
            "Example: --depth-scale-mm 1.0 only after unit is confirmed."
        ),
    )

    parser.add_argument(
        "--output-root",
        type=str,
        default=(
            "/mnt/c/Users/ASUS/Desktop/paper/"
            "E0/E0_A_camera_static"
        ),
    )

    args = parser.parse_args()

    if args.samples is None:
        args.samples = (
            10 if args.phase == "pilot"
            else 50
        )

    if args.patch_size % 2 == 0:
        raise ValueError(
            "--patch-size must be odd"
        )

    raw_dir = os.path.join(
        args.output_root,
        "raw",
    )

    results_dir = os.path.join(
        args.output_root,
        "results",
    )

    os.makedirs(
        raw_dir,
        exist_ok=True,
    )

    os.makedirs(
        results_dir,
        exist_ok=True,
    )

    run_id = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    base_name = (
        f"E0A_{args.phase}_"
        f"{args.position}_{run_id}"
    )

    csv_path = os.path.join(
        raw_dir,
        f"{base_name}.csv",
    )

    metadata_path = os.path.join(
        raw_dir,
        f"{base_name}_metadata.json",
    )

    summary_path = os.path.join(
        results_dir,
        f"{base_name}_summary.json",
    )

    rclpy.init()
    node = E0ACollector(args)

    print()
    print("==========================================")
    print("E0-A Camera Static Repeatability v2")
    print("==========================================")
    print(f"Phase            : {args.phase}")
    print(f"Position         : {args.position}")
    print(f"Dictionary       : {args.dictionary}")
    print(f"Marker ID        : {args.marker_id}")
    print(f"Samples/camera   : {args.samples}")
    print(f"Sample interval  : {args.sample_interval} s")
    print(f"Depth patch      : {args.patch_size}x{args.patch_size}")
    print("Subpixel refine  : ON")
    print(
        "Depth unit       : "
        + (
            f"{args.depth_scale_mm} mm/native-unit"
            if args.depth_scale_mm is not None
            else "UNVERIFIED native mono16 units"
        )
    )
    print("==========================================")
    print()

    start = time.time()

    try:
        while (
            rclpy.ok()
            and not node.finished()
        ):
            rclpy.spin_once(
                node,
                timeout_sec=0.05,
            )

            node.try_sample_all(
                raw_dir,
                run_id,
            )

            if time.time() - start > args.timeout:
                print()
                print("TIMEOUT")
                break

    except KeyboardInterrupt:
        print()
        print("INTERRUPTED BY USER")

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
            "script_version": "v2_subpixel",
            "phase": args.phase,
            "position": args.position,
            "run_id": run_id,
            "dictionary": args.dictionary,
            "marker_id": args.marker_id,
            "samples_requested_per_camera": args.samples,
            "samples_collected": node.counts,
            "sample_interval_s": args.sample_interval,
            "depth_patch_size": args.patch_size,
            "min_valid_ratio": args.min_valid_ratio,
            "max_rgb_depth_dt_ms": args.max_rgb_depth_dt_ms,
            "subpixel_refinement": {
                "enabled": True,
                "method": "CORNER_REFINE_SUBPIX",
                "win_size": args.subpix_win_size,
                "max_iterations": args.subpix_max_iterations,
                "min_accuracy": args.subpix_min_accuracy,
            },
            "depth_encoding": "mono16",
            "depth_scale_mm": args.depth_scale_mm,
            "depth_unit_status": (
                "CONFIRMED_BY_USER_SCALE"
                if args.depth_scale_mm is not None
                else "UNVERIFIED_NATIVE_UNIT"
            ),
            "camera_info": camera_info_meta,
            "camera_mapping": CAMERAS,
        }

        if rows:
            fieldnames = list(
                rows[0].keys()
            )

            with open(
                csv_path,
                "w",
                newline="",
                encoding="utf-8",
            ) as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=fieldnames,
                )

                writer.writeheader()
                writer.writerows(rows)

        with open(
            metadata_path,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                metadata,
                f,
                indent=2,
            )

        summary = summarize(
            rows,
            args,
        )

        with open(
            summary_path,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                summary,
                f,
                indent=2,
            )

        node.destroy_node()
        rclpy.shutdown()

    print()
    print("==========================================")
    print("RUN COMPLETE")
    print("==========================================")
    print("counts   :", node.counts)
    print("CSV      :", csv_path)
    print("metadata :", metadata_path)
    print("summary  :", summary_path)

    print()
    print("--- QUICK SUMMARY ---")

    for camera, result in summary["cameras"].items():
        print()
        print(camera)

        if result.get("n", 0) == 0:
            print("  NO VALID SAMPLES")
            continue

        print("  n:", result["n"])
        print("  marker IDs:", result["marker_ids"])

        print(
            "  u SD:",
            f'{result["u_px"]["sd"]:.4f} px',
        )

        print(
            "  v SD:",
            f'{result["v_px"]["sd"]:.4f} px',
        )

        print(
            "  depth SD:",
            f'{result["depth_median_raw"]["sd"]:.4f} raw',
        )

        print(
            "  X SD:",
            f'{result["x_cam_raw"]["sd"]:.4f} raw',
        )

        print(
            "  Y SD:",
            f'{result["y_cam_raw"]["sd"]:.4f} raw',
        )

        print(
            "  XY radial P95:",
            f'{result["xy_radial_deviation_raw"]["p95"]:.4f} raw',
        )

        print(
            "  depth valid ratio mean:",
            f'{result["depth_valid_ratio"]["mean"]:.3f}',
        )

        print(
            "  RGB-depth dt mean:",
            f'{result["color_depth_dt_ms"]["mean"]:.2f} ms',
        )

        if args.depth_scale_mm is not None:
            print(
                "  XY radial P95:",
                f'{result["xy_radial_deviation_mm"]["p95"]:.4f} mm',
            )


if __name__ == "__main__":
    main()
