#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E2 — Dual-Camera Height × XY Grid Scan Collector
===================================================

Purpose
-------
Collect one reusable raw dataset for later comparison of:
- ihawk1 vs ihawk2
- Affine vs Homography vs PnP + camera extrinsic
- single-camera vs dual-camera fusion
- marker position within the A4 board
- board placement within the workspace
- error vs manually entered height

Physical board assumptions for this experiment
----------------------------------------------
- Board outer size: A4 = 210 x 297 mm
- 5 ArUco markers: four corners + center
- ArUco dictionary: DICT_4X4_50
- Marker black outer square: 50.0 mm
- Corner-marker outer edges are aligned to the A4 edges
- Center marker is centered on the A4 sheet
- Height is entered manually in millimetres for each height layer
- For every height layer, exactly 9 board-center XY placements are entered
- The A4 board is translated only; rotation is assumed to remain 0 deg
- The entered XY is the coordinate of the A4 CENTER / center marker

Important
---------
The manually entered height is ground truth for Z.
Camera measurements are observations/predictions, NOT ground truth.

The collector stores raw RGB frames, depth frames when available, camera
intrinsics, marker pixels, per-marker PnP pose, timestamps and detection
validity. This allows later offline re-processing without repeating the
physical experiment.

Typical pilot
-------------
python3 e2_dual_camera_xy_height_scan_v2.py --pilot --frames-per-placement 3

Typical formal run
------------------
python3 e2_dual_camera_xy_height_scan_v2.py --frames-per-placement 10
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


DEFAULT_ROOT = Path(
    "/mnt/c/Users/ASUS/Desktop/paper/E2/E2_dual_camera_height_scan"
)

CAMERAS = ("ihawk1", "ihawk2")
BOARD_WIDTH_MM = 210.0
BOARD_HEIGHT_MM = 297.0
MARKER_LENGTH_MM = 50.0

# Marker-center coordinates relative to the A4 CENTER.
#
# Experiment XY convention:
#   +X = right
#   +Y = up
# as viewed on the board in the initial ihawk1 discovery image.
#
# Assumption: corner-marker OUTER EDGES align with the A4 outer edges and
# the center marker is centered on the A4 sheet.
LOCAL_GT_BY_POSITION = {
    "TL": (-(BOARD_WIDTH_MM / 2.0 - MARKER_LENGTH_MM / 2.0),
            +(BOARD_HEIGHT_MM / 2.0 - MARKER_LENGTH_MM / 2.0)),
    "TR": (+(BOARD_WIDTH_MM / 2.0 - MARKER_LENGTH_MM / 2.0),
            +(BOARD_HEIGHT_MM / 2.0 - MARKER_LENGTH_MM / 2.0)),
    "C":  (0.0, 0.0),
    "BL": (-(BOARD_WIDTH_MM / 2.0 - MARKER_LENGTH_MM / 2.0),
            -(BOARD_HEIGHT_MM / 2.0 - MARKER_LENGTH_MM / 2.0)),
    "BR": (+(BOARD_WIDTH_MM / 2.0 - MARKER_LENGTH_MM / 2.0),
            -(BOARD_HEIGHT_MM / 2.0 - MARKER_LENGTH_MM / 2.0)),
}


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def now_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def iso_now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def msg_stamp_sec(msg) -> float:
    stamp = msg.header.stamp
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def safe_height_token(height_mm: float) -> str:
    # +001.250 -> p001p250, -000.500 -> m000p500
    sign = "p" if height_mm >= 0 else "m"
    x = abs(height_mm)
    whole = int(math.floor(x))
    frac = int(round((x - whole) * 1000.0))
    if frac == 1000:
        whole += 1
        frac = 0
    return f"{sign}{whole:03d}p{frac:03d}mm"


def nan() -> float:
    return float("nan")


def finite_or_nan(x) -> float:
    try:
        x = float(x)
        return x if math.isfinite(x) else nan()
    except Exception:
        return nan()


# ---------------------------------------------------------------------------
# OpenCV / ArUco compatibility
# ---------------------------------------------------------------------------

class ArucoDetectorCompat:
    def __init__(self):
        if not hasattr(cv2, "aruco"):
            raise RuntimeError(
                "cv2.aruco is unavailable. Install/use an OpenCV build with "
                "the aruco module."
            )

        aruco = cv2.aruco

        if hasattr(aruco, "getPredefinedDictionary"):
            self.dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
        else:
            self.dictionary = aruco.Dictionary_get(aruco.DICT_4X4_50)

        if hasattr(aruco, "DetectorParameters"):
            params = aruco.DetectorParameters()
        else:
            params = aruco.DetectorParameters_create()

        # Keep detector parameters near defaults for reproducibility.
        self.params = params

        if hasattr(aruco, "ArucoDetector"):
            self.detector = aruco.ArucoDetector(self.dictionary, self.params)
        else:
            self.detector = None

    def detect(self, bgr: np.ndarray):
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        if self.detector is not None:
            corners, ids, rejected = self.detector.detectMarkers(gray)
        else:
            corners, ids, rejected = cv2.aruco.detectMarkers(
                gray,
                self.dictionary,
                parameters=self.params,
            )

        if ids is None or len(ids) == 0:
            return {}

        # Optional sub-pixel refinement on all four corners.
        criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30,
            0.01,
        )

        found = {}
        for c, marker_id in zip(corners, ids.reshape(-1)):
            pts = np.asarray(c, dtype=np.float32).reshape(4, 2)
            try:
                refined = cv2.cornerSubPix(
                    gray,
                    pts.reshape(-1, 1, 2),
                    (3, 3),
                    (-1, -1),
                    criteria,
                )
                pts = refined.reshape(4, 2)
            except cv2.error:
                pass

            found[int(marker_id)] = pts.astype(np.float64)

        return found


def undistort_points_px(
    points_uv: np.ndarray,
    K: np.ndarray,
    D: np.ndarray,
) -> np.ndarray:
    pts = np.asarray(points_uv, dtype=np.float64).reshape(-1, 1, 2)
    und = cv2.undistortPoints(pts, K, D, P=K)
    return und.reshape(-1, 2)


def solve_marker_pose_mm(
    corners_uv: np.ndarray,
    K: np.ndarray,
    D: np.ndarray,
    marker_length_mm: float = MARKER_LENGTH_MM,
):
    """
    Solve marker pose in CAMERA coordinates from its known 50 mm square.

    ArUco corner order is:
        top-left, top-right, bottom-right, bottom-left

    Object coordinate convention used here:
        marker center = origin
        +X right
        +Y up
        Z = 0 on marker plane

    Translation tvec is therefore the marker-center position in camera frame,
    in millimetres.
    """
    h = marker_length_mm / 2.0
    obj = np.array(
        [
            [-h, +h, 0.0],
            [+h, +h, 0.0],
            [+h, -h, 0.0],
            [-h, -h, 0.0],
        ],
        dtype=np.float64,
    )

    img = np.asarray(corners_uv, dtype=np.float64).reshape(4, 2)

    methods = []
    if hasattr(cv2, "SOLVEPNP_IPPE_SQUARE"):
        methods.append(("IPPE_SQUARE", cv2.SOLVEPNP_IPPE_SQUARE))
    methods.append(("ITERATIVE", cv2.SOLVEPNP_ITERATIVE))

    last_exc = None
    for name, flag in methods:
        try:
            ok, rvec, tvec = cv2.solvePnP(
                obj,
                img,
                K,
                D,
                flags=flag,
            )
            if not ok:
                continue

            projected, _ = cv2.projectPoints(obj, rvec, tvec, K, D)
            projected = projected.reshape(4, 2)
            reproj = float(
                np.sqrt(np.mean(np.sum((projected - img) ** 2, axis=1)))
            )

            return {
                "valid": True,
                "method": name,
                "rvec": rvec.reshape(3),
                "tvec_mm": tvec.reshape(3),
                "reprojection_rmse_px": reproj,
            }
        except cv2.error as exc:
            last_exc = exc

    return {
        "valid": False,
        "method": "",
        "rvec": np.array([nan(), nan(), nan()]),
        "tvec_mm": np.array([nan(), nan(), nan()]),
        "reprojection_rmse_px": nan(),
        "error": str(last_exc) if last_exc else "solvePnP failed",
    }


# ---------------------------------------------------------------------------
# ROS image conversion
# ---------------------------------------------------------------------------

def color_msg_to_bgr(msg) -> np.ndarray:
    h = int(msg.height)
    w = int(msg.width)
    enc = str(msg.encoding).lower()
    raw = np.frombuffer(msg.data, dtype=np.uint8)

    if enc in ("bgr8", "rgb8"):
        arr = raw.reshape(h, int(msg.step))[:, : w * 3].reshape(h, w, 3)
        if enc == "rgb8":
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return arr.copy()

    if enc in ("bgra8", "rgba8"):
        arr = raw.reshape(h, int(msg.step))[:, : w * 4].reshape(h, w, 4)
        if enc == "rgba8":
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)

    if enc in ("mono8", "8uc1"):
        arr = raw.reshape(h, int(msg.step))[:, :w]
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)

    raise RuntimeError(f"Unsupported color image encoding: {msg.encoding}")


def depth_msg_to_array(msg) -> Tuple[np.ndarray, str]:
    h = int(msg.height)
    w = int(msg.width)
    enc = str(msg.encoding).lower()

    if enc in ("16uc1", "mono16", "16sc1"):
        dtype = np.dtype(">u2" if msg.is_bigendian else "<u2")
        raw = np.frombuffer(msg.data, dtype=dtype)
        px_per_row = int(msg.step) // 2
        arr = raw.reshape(h, px_per_row)[:, :w].copy()
        return arr.astype(np.uint16, copy=False), "uint16"

    if enc in ("32fc1",):
        dtype = np.dtype(">f4" if msg.is_bigendian else "<f4")
        raw = np.frombuffer(msg.data, dtype=dtype)
        px_per_row = int(msg.step) // 4
        arr = raw.reshape(h, px_per_row)[:, :w].copy()
        return arr.astype(np.float32, copy=False), "float32"

    raise RuntimeError(f"Unsupported depth image encoding: {msg.encoding}")


# ---------------------------------------------------------------------------
# ROS capture state
# ---------------------------------------------------------------------------

@dataclass
class CameraState:
    camera_id: str
    color_topic: str
    info_topic: str
    depth_topic: Optional[str] = None

    color_seq: int = 0
    latest_color: Optional[np.ndarray] = None
    latest_color_stamp: Optional[float] = None
    latest_color_encoding: str = ""

    K: Optional[np.ndarray] = None
    D: Optional[np.ndarray] = None
    camera_info_received: bool = False
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    distortion_model: str = ""

    depth_buffer: deque = field(default_factory=lambda: deque(maxlen=30))
    depth_encoding: str = ""


@dataclass
class FrameSnapshot:
    camera_id: str
    color: np.ndarray
    color_stamp: float
    color_seq: int
    K: np.ndarray
    D: np.ndarray
    depth: Optional[np.ndarray]
    depth_stamp: Optional[float]
    depth_storage_type: str


# ---------------------------------------------------------------------------
# Marker geometry / board mapping
# ---------------------------------------------------------------------------

def marker_centers(detected: Dict[int, np.ndarray]) -> Dict[int, Tuple[float, float]]:
    result = {}
    for marker_id, corners in detected.items():
        c = np.mean(corners, axis=0)
        result[int(marker_id)] = (float(c[0]), float(c[1]))
    return result


def infer_five_position_mapping(
    selected_ids: List[int],
    centers: Dict[int, Tuple[float, float]],
) -> Dict[int, str]:
    """
    Infer C + four image quadrants from ihawk1.

    This establishes ONE run-level board orientation.
    It is saved in metadata and reused for ihawk2, so cross-camera matching
    uses marker IDs rather than each camera's own image quadrants.
    """
    pts = np.array([centers[i] for i in selected_ids], dtype=np.float64)
    centroid = np.mean(pts, axis=0)

    d = np.linalg.norm(pts - centroid, axis=1)
    center_idx = int(np.argmin(d))
    center_id = selected_ids[center_idx]

    corners = [i for i in selected_ids if i != center_id]
    corner_pts = [(i, centers[i][0], centers[i][1]) for i in corners]

    # Split top and bottom by image v, then left/right by u.
    corner_pts.sort(key=lambda x: x[2])
    top = sorted(corner_pts[:2], key=lambda x: x[1])
    bottom = sorted(corner_pts[2:], key=lambda x: x[1])

    mapping = {
        center_id: "C",
        top[0][0]: "TL",
        top[1][0]: "TR",
        bottom[0][0]: "BL",
        bottom[1][0]: "BR",
    }
    return mapping


def print_mapping(mapping: Dict[int, str], centers: Dict[int, Tuple[float, float]]) -> None:
    inv = {label: mid for mid, label in mapping.items()}
    print()
    print("Run-level marker mapping inferred from ihawk1 image:")
    for label in ("TL", "TR", "C", "BL", "BR"):
        mid = inv[label]
        u, v = centers[mid]
        local_gt = LOCAL_GT_BY_POSITION[label]
        print(
            f"  {label:2s} -> marker ID {mid:3d} | "
            f"pixel≈({u:.1f},{v:.1f}) | "
            f"local XY from board center≈"
            f"({local_gt[0]:+.1f},{local_gt[1]:+.1f}) mm"
        )


# ---------------------------------------------------------------------------
# Main ROS node
# ---------------------------------------------------------------------------

def run_collector(args) -> None:
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
        from sensor_msgs.msg import Image, CameraInfo
    except Exception as exc:
        raise RuntimeError(
            "ROS2 Python packages are unavailable. Run this script in a shell "
            "where /opt/ros/humble and ~/berxel_ros2_ws are sourced."
        ) from exc

    detector = ArucoDetectorCompat()

    run_id = now_run_id()
    run_root = Path(args.output_root) / f"run_{run_id}"
    raw_dir = run_root / "raw"
    frame_root = raw_dir / "frames"
    metadata_dir = run_root / "metadata"
    results_dir = run_root / "results"
    script_dir = run_root / "scripts"

    for p in (raw_dir, frame_root, metadata_dir, results_dir, script_dir):
        ensure_dir(p)
    for camera in CAMERAS:
        ensure_dir(frame_root / camera)

    # Snapshot the exact script used.
    try:
        shutil.copy2(Path(__file__), script_dir / Path(__file__).name)
    except Exception:
        pass

    csv_path = raw_dir / f"E2_dual_height_raw_{run_id}.csv"
    metadata_path = metadata_dir / f"E2_run_metadata_{run_id}.json"
    summary_path = results_dir / f"E2_capture_summary_{run_id}.json"
    session_log_path = run_root / f"E2_session_{run_id}.log"

    def log(text: str = ""):
        print(text, flush=True)
        with session_log_path.open("a", encoding="utf-8") as lf:
            lf.write(text + "\n")

    qos = QoSProfile(
        reliability=ReliabilityPolicy.BEST_EFFORT,
        history=HistoryPolicy.KEEP_LAST,
        depth=10,
    )

    class CollectorNode(Node):
        def __init__(self):
            super().__init__("e2_dual_camera_xy_height_scan_collector")
            self.states: Dict[str, CameraState] = {}

            for cam in CAMERAS:
                color_topic = f"/{cam}/color/color_raw"
                info_topic = f"/{cam}/color/camera_info"

                st = CameraState(
                    camera_id=cam,
                    color_topic=color_topic,
                    info_topic=info_topic,
                )
                self.states[cam] = st

                self.create_subscription(
                    Image,
                    color_topic,
                    lambda msg, c=cam: self.color_cb(c, msg),
                    qos,
                )
                self.create_subscription(
                    CameraInfo,
                    info_topic,
                    lambda msg, c=cam: self.info_cb(c, msg),
                    qos,
                )

            self.depth_subscriptions_created = False

        def color_cb(self, cam: str, msg):
            st = self.states[cam]
            try:
                st.latest_color = color_msg_to_bgr(msg)
                st.latest_color_stamp = msg_stamp_sec(msg)
                st.latest_color_encoding = str(msg.encoding)
                st.color_seq += 1
            except Exception as exc:
                self.get_logger().warning(f"{cam} color conversion failed: {exc}")

        def info_cb(self, cam: str, msg):
            st = self.states[cam]
            st.K = np.asarray(msg.k, dtype=np.float64).reshape(3, 3)
            st.D = np.asarray(msg.d, dtype=np.float64).reshape(-1, 1)
            st.camera_info_received = True
            st.image_width = int(msg.width)
            st.image_height = int(msg.height)
            st.distortion_model = str(msg.distortion_model)

        def depth_cb(self, cam: str, msg):
            st = self.states[cam]
            try:
                arr, storage_type = depth_msg_to_array(msg)
                st.depth_buffer.append(
                    (msg_stamp_sec(msg), arr, storage_type, str(msg.encoding))
                )
                st.depth_encoding = str(msg.encoding)
            except Exception as exc:
                self.get_logger().warning(f"{cam} depth conversion failed: {exc}")

        def discover_and_subscribe_depth(self):
            if self.depth_subscriptions_created:
                return

            topic_map = dict(self.get_topic_names_and_types())

            candidate_suffixes = [
                "depth/depth_raw",
                "depth/image_raw",
                "depth/depth_registered",
                "depth_registered/image_raw",
                "aligned_depth_to_color/image_raw",
            ]

            for cam in CAMERAS:
                st = self.states[cam]
                found = None

                if getattr(args, f"{cam}_depth_topic"):
                    found = getattr(args, f"{cam}_depth_topic")
                else:
                    for suffix in candidate_suffixes:
                        candidate = f"/{cam}/{suffix}"
                        if candidate in topic_map:
                            found = candidate
                            break

                if found:
                    st.depth_topic = found
                    self.create_subscription(
                        Image,
                        found,
                        lambda msg, c=cam: self.depth_cb(c, msg),
                        qos,
                    )

            self.depth_subscriptions_created = True

    def closest_depth(
        st: CameraState,
        color_stamp: float,
    ) -> Tuple[Optional[np.ndarray], Optional[float], str]:
        if not st.depth_buffer:
            return None, None, ""
        best = min(st.depth_buffer, key=lambda x: abs(x[0] - color_stamp))
        return best[1], best[0], best[2]

    def snapshot_from_state(st: CameraState) -> FrameSnapshot:
        depth, depth_stamp, depth_storage_type = closest_depth(
            st, st.latest_color_stamp
        )
        return FrameSnapshot(
            camera_id=st.camera_id,
            color=st.latest_color.copy(),
            color_stamp=float(st.latest_color_stamp),
            color_seq=int(st.color_seq),
            K=st.K.copy(),
            D=st.D.copy(),
            depth=None if depth is None else depth.copy(),
            depth_stamp=None if depth_stamp is None else float(depth_stamp),
            depth_storage_type=depth_storage_type,
        )

    def wait_initial_ready(node: CollectorNode, timeout_s: float = 20.0):
        log("Waiting for both color streams + CameraInfo ...")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            node.discover_and_subscribe_depth()
            ready = all(
                st.latest_color is not None
                and st.latest_color_stamp is not None
                and st.camera_info_received
                for st in node.states.values()
            )
            if ready:
                return
        details = {
            cam: {
                "color": node.states[cam].latest_color is not None,
                "camera_info": node.states[cam].camera_info_received,
                "depth_topic": node.states[cam].depth_topic,
            }
            for cam in CAMERAS
        }
        raise RuntimeError(f"Camera startup timeout: {details}")

    def wait_fresh_pair(
        node: CollectorNode,
        last_seq: Dict[str, int],
        timeout_s: float,
    ) -> Tuple[Dict[str, FrameSnapshot], float]:
        deadline = time.time() + timeout_s
        best_delta_ms = float("inf")

        while time.time() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)

            s1 = node.states["ihawk1"]
            s2 = node.states["ihawk2"]

            if (
                s1.color_seq <= last_seq["ihawk1"]
                or s2.color_seq <= last_seq["ihawk2"]
                or s1.latest_color is None
                or s2.latest_color is None
            ):
                continue

            delta_ms = abs(s1.latest_color_stamp - s2.latest_color_stamp) * 1000.0
            best_delta_ms = min(best_delta_ms, delta_ms)

            if delta_ms <= args.max_pair_delta_ms:
                snaps = {
                    "ihawk1": snapshot_from_state(s1),
                    "ihawk2": snapshot_from_state(s2),
                }
                return snaps, delta_ms

        raise RuntimeError(
            f"Could not obtain a fresh ihawk1/ihawk2 color pair within "
            f"{args.max_pair_delta_ms:.1f} ms. "
            f"Best observed delta≈{best_delta_ms:.1f} ms."
        )

    def detect_pair(snaps: Dict[str, FrameSnapshot]):
        return {
            cam: detector.detect(snaps[cam].color)
            for cam in CAMERAS
        }

    def discover_expected_markers(
        node: CollectorNode,
    ) -> Tuple[List[int], Dict[int, str], Dict[int, Tuple[float, float]]]:
        log()
        log("Discovering the five common board markers ...")

        last_seq = {"ihawk1": -1, "ihawk2": -1}
        deadline = time.time() + args.marker_discovery_timeout_s
        latest_report = None

        while time.time() < deadline:
            try:
                snaps, delta_ms = wait_fresh_pair(
                    node,
                    last_seq,
                    timeout_s=min(5.0, args.marker_discovery_timeout_s),
                )
            except RuntimeError:
                continue

            for cam in CAMERAS:
                last_seq[cam] = snaps[cam].color_seq

            found = detect_pair(snaps)
            ids1 = sorted(found["ihawk1"].keys())
            ids2 = sorted(found["ihawk2"].keys())
            common = sorted(set(ids1) & set(ids2))
            latest_report = (ids1, ids2, common, delta_ms)

            # Ideal case: exactly the same five common markers.
            if len(common) == 5:
                centers = marker_centers(found["ihawk1"])
                mapping = infer_five_position_mapping(common, centers)

                log(f"ihawk1 IDs: {ids1}")
                log(f"ihawk2 IDs: {ids2}")
                log(f"Common board IDs selected automatically: {common}")
                print_mapping(mapping, centers)
                log()
                log(
                    "NOTE: TL/TR/BL/BR are established from ihawk1 image "
                    "geometry for this run and then tied permanently to marker IDs."
                )
                return common, mapping, centers

            # If extra ArUco markers are visible, ask user to choose five.
            if len(common) > 5:
                log(f"ihawk1 IDs: {ids1}")
                log(f"ihawk2 IDs: {ids2}")
                log(f"Common IDs: {common}")
                log(
                    "More than five common markers are visible. "
                    "Enter the five IDs belonging to the A4 test board."
                )
                while True:
                    text = input("Five board marker IDs, comma-separated: ").strip()
                    try:
                        selected = [int(x.strip()) for x in text.split(",")]
                        if len(selected) != 5 or len(set(selected)) != 5:
                            raise ValueError
                        if not set(selected).issubset(set(common)):
                            raise ValueError
                        break
                    except ValueError:
                        print("Please enter exactly five distinct IDs shown above.")

                centers = marker_centers(found["ihawk1"])
                mapping = infer_five_position_mapping(selected, centers)
                print_mapping(mapping, centers)
                return selected, mapping, centers

        raise RuntimeError(
            "Could not see five common test-board markers on both cameras "
            f"within {args.marker_discovery_timeout_s:.0f}s. "
            f"Last observation: {latest_report}"
        )

    def save_depth_image(
        arr: np.ndarray,
        path_base: Path,
    ) -> Optional[str]:
        if arr is None:
            return None

        if arr.dtype == np.uint16:
            path = path_base.with_suffix(".png")
            ok = cv2.imwrite(str(path), arr)
            if not ok:
                raise RuntimeError(f"Failed to write depth PNG: {path}")
            return str(path.relative_to(run_root))

        path = path_base.with_suffix(".npz")
        np.savez_compressed(path, depth=arr)
        return str(path.relative_to(run_root))

    def depth_roi_value(
        depth: Optional[np.ndarray],
        color_shape: Tuple[int, int, int],
        center_u: float,
        center_v: float,
    ):
        """
        Conservative policy:
        - only sample depth if --depth-aligned-to-color is explicitly enabled
        - and the depth image resolution matches the color image resolution.
        """
        if depth is None:
            return nan(), 0, "no_depth"

        if not args.depth_aligned_to_color:
            return nan(), 0, "alignment_not_asserted"

        h, w = color_shape[:2]
        if depth.shape[0] != h or depth.shape[1] != w:
            return nan(), 0, "resolution_mismatch"

        u = int(round(center_u))
        v = int(round(center_v))
        r = int(args.depth_roi_radius_px)

        x0, x1 = max(0, u - r), min(w, u + r + 1)
        y0, y1 = max(0, v - r), min(h, v + r + 1)

        roi = depth[y0:y1, x0:x1].astype(np.float64)
        valid = roi[np.isfinite(roi) & (roi > 0)]
        if len(valid) == 0:
            return nan(), 0, "no_valid_pixels"

        val = float(np.median(valid))

        # Berxel 16-bit depth is normally in sensor depth units, commonly mm.
        # We record the raw numeric median and the encoding rather than silently
        # asserting a physical unit when not independently verified.
        return val, int(len(valid)), "ok"

    csv_fields = [
        "run_id",
        "capture_time_host",
        "height_step_index",
        "height_gt_mm",
        "placement_index",
        "board_center_gt_x_mm",
        "board_center_gt_y_mm",
        "board_rotation_gt_deg",
        "marker_local_x_mm",
        "marker_local_y_mm",
        "marker_gt_x_mm",
        "marker_gt_y_mm",
        "frame_index",
        "camera_id",
        "camera_role",
        "color_stamp_sec",
        "other_camera_color_stamp_sec",
        "pair_delta_ms",
        "pair_sync_valid",
        "marker_id",
        "board_position",
        "board_gt_z_mm",
        "detection_valid",
        "center_u_raw_px",
        "center_v_raw_px",
        "center_u_undist_px",
        "center_v_undist_px",
        "corner0_u_raw_px",
        "corner0_v_raw_px",
        "corner1_u_raw_px",
        "corner1_v_raw_px",
        "corner2_u_raw_px",
        "corner2_v_raw_px",
        "corner3_u_raw_px",
        "corner3_v_raw_px",
        "corner0_u_undist_px",
        "corner0_v_undist_px",
        "corner1_u_undist_px",
        "corner1_v_undist_px",
        "corner2_u_undist_px",
        "corner2_v_undist_px",
        "corner3_u_undist_px",
        "corner3_v_undist_px",
        "pnp_valid",
        "pnp_method",
        "pnp_tx_camera_mm",
        "pnp_ty_camera_mm",
        "pnp_tz_camera_mm",
        "pnp_rvec_x",
        "pnp_rvec_y",
        "pnp_rvec_z",
        "pnp_reprojection_rmse_px",
        "depth_available",
        "depth_stamp_sec",
        "color_depth_delta_ms",
        "depth_encoding",
        "depth_center_roi_raw_median",
        "depth_center_roi_valid_pixels",
        "depth_center_roi_status",
        "color_image_relpath",
        "depth_image_relpath",
    ]

    rclpy.init()
    node = CollectorNode()

    summary = {
        "run_id": run_id,
        "started_at": iso_now(),
        "experiment": "E2 dual-camera height x XY-grid scan",
        "status": "running",
        "height_steps": [],
    }

    try:
        log("================================================================")
        log("E2 — DUAL-CAMERA INTERACTIVE HEIGHT SCAN")
        log("================================================================")
        log(f"run_id             : {run_id}")
        log(f"output             : {run_root}")
        log("dictionary         : DICT_4X4_50")
        log(f"marker outer size  : {MARKER_LENGTH_MM:.1f} mm")
        log(
            f"A4 board geometry  : {BOARD_WIDTH_MM:.1f} x "
            f"{BOARD_HEIGHT_MM:.1f} mm"
        )
        log(f"placements / height: {args.placements_per_height}")
        log(f"frames / placement : {args.frames_per_placement}")
        log(f"pair sync gate     : <= {args.max_pair_delta_ms:.1f} ms")
        log("height unit        : mm")
        log()

        wait_initial_ready(node)

        for cam in CAMERAS:
            st = node.states[cam]
            log(
                f"{cam}: color={st.color_topic} | "
                f"camera_info={st.info_topic} | "
                f"depth={st.depth_topic or 'NOT FOUND / OPTIONAL'}"
            )

        selected_ids, position_map, first_centers = discover_expected_markers(node)

        # Camera metadata snapshot.
        camera_meta = {}
        for cam in CAMERAS:
            st = node.states[cam]
            camera_meta[cam] = {
                "role": args.ihawk1_role if cam == "ihawk1" else args.ihawk2_role,
                "color_topic": st.color_topic,
                "camera_info_topic": st.info_topic,
                "depth_topic": st.depth_topic,
                "K": st.K.tolist(),
                "D": st.D.reshape(-1).tolist(),
                "distortion_model": st.distortion_model,
                "camera_info_width": st.image_width,
                "camera_info_height": st.image_height,
                "color_encoding": st.latest_color_encoding,
                "depth_encoding": st.depth_encoding,
            }

        metadata = {
            "run_id": run_id,
            "experiment": "E2 dual-camera height x XY-grid scan",
            "created_at": iso_now(),
            "ground_truth": {
                "height": (
                    "Manual user-entered height in millimetres relative to the "
                    "chosen experiment reference plane."
                ),
                "board_outer_size_mm": [BOARD_WIDTH_MM, BOARD_HEIGHT_MM],
                "marker_outer_size_mm": MARKER_LENGTH_MM,
                "xy_reference": (
                    "At every placement the user enters the A4 CENTER XY "
                    "coordinate in millimetres. The center marker is assumed "
                    "to coincide with the A4 center."
                ),
                "xy_axis_convention": {
                    "+X": "right on the board",
                    "+Y": "up on the board",
                },
                "rotation_assumption_deg": 0.0,
                "xy_assumption": (
                    "The A4 board is translated only, without rotation. "
                    "Four corner-marker OUTER EDGES align with the A4 edges; "
                    "the center marker is centered."
                ),
                "marker_local_xy_from_board_center_mm": {
                    k: [float(v[0]), float(v[1])]
                    for k, v in LOCAL_GT_BY_POSITION.items()
                },
            },
            "aruco": {
                "dictionary": "DICT_4X4_50",
                "selected_marker_ids": selected_ids,
                "marker_id_to_position": {
                    str(k): v for k, v in position_map.items()
                },
                "position_mapping_basis": (
                    "First valid ihawk1 frame. Center = marker nearest the "
                    "five-marker image centroid; remaining four labelled by "
                    "image top/bottom and left/right. Mapping is then frozen "
                    "by marker ID for both cameras."
                ),
            },
            "cameras": camera_meta,
            "collection": {
                "placements_per_height": args.placements_per_height,
                "frames_per_placement": args.frames_per_placement,
                "max_pair_delta_ms": args.max_pair_delta_ms,
                "depth_aligned_to_color_asserted": bool(
                    args.depth_aligned_to_color
                ),
                "depth_roi_radius_px": args.depth_roi_radius_px,
                "raw_color_saved_losslessly": True,
                "raw_depth_saved_when_available": True,
                "one_row_per_expected_marker_per_camera_per_frame": True,
                "missing_marker_rows_are_retained": True,
            },
            "important_interpretation": [
                "Manual height is ground truth for Z.",
                "Camera/PnP/depth values are observations, not ground truth.",
                "The raw dataset is intended for later offline model comparison.",
                "PnP in this collector is a diagnostic per-marker camera-frame pose.",
            ],
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        log()
        log("Ready.")
        log(
            "For each Z layer: enter the measured height in mm, then complete "
            f"exactly {args.placements_per_height} board-center XY placements."
        )
        log(
            "XY input is the A4 CENTER / center-marker coordinate in mm. "
            "Convention: +X right, +Y up. Translate only; do NOT rotate."
        )
        log("Type q only at the Height prompt to finish the run.")
        log()

        def parse_xy_input(text: str):
            clean = text.strip()
            # Accept: "5 0", "5,0", "x=5 y=0", "x=5,y=0"
            clean = clean.replace(",", " ")
            clean = re.sub(r"[xX]\s*=", "", clean)
            clean = re.sub(r"[yY]\s*=", "", clean)
            parts = clean.split()
            if len(parts) != 2:
                raise ValueError
            x, y = float(parts[0]), float(parts[1])
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError
            return x, y

        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=csv_fields)
            writer.writeheader()
            f.flush()

            height_step_index = 0
            last_seq = {
                cam: node.states[cam].color_seq
                for cam in CAMERAS
            }

            while True:
                text = input("Height Z [mm] (or q to finish): ").strip()

                if text.lower() in ("q", "quit"):
                    log("User requested end of run.")
                    break

                try:
                    height_mm = float(text)
                    if not math.isfinite(height_mm):
                        raise ValueError
                except ValueError:
                    log("Invalid height. Enter a number in mm, or q.")
                    continue

                height_step_index += 1
                height_token = safe_height_token(height_mm)

                log()
                log("================================================================")
                log(
                    f"[HEIGHT {height_step_index:03d}] "
                    f"Z = {height_mm:.3f} mm"
                )
                log(
                    f"This Z layer requires exactly "
                    f"{args.placements_per_height} XY placements."
                )
                log(
                    "For each placement enter the A4 CENTER coordinate as "
                    "\"X Y\" in mm. Example: 5 0"
                )
                log("Board rotation must remain 0 deg.")
                log("================================================================")

                used_xy = set()
                height_record = {
                    "height_step_index": height_step_index,
                    "height_gt_mm": height_mm,
                    "placements": [],
                    "started_at": iso_now(),
                }

                for placement_index in range(1, args.placements_per_height + 1):
                    while True:
                        xy_text = input(
                            f"Placement {placement_index}/"
                            f"{args.placements_per_height} — "
                            "board CENTER X Y [mm]: "
                        ).strip()

                        try:
                            board_x_mm, board_y_mm = parse_xy_input(xy_text)
                        except ValueError:
                            log(
                                "Invalid XY. Enter two numbers, e.g. "
                                "\"5 0\", \"5,0\", or \"x=5 y=0\"."
                            )
                            continue

                        xy_key = (
                            round(board_x_mm, 9),
                            round(board_y_mm, 9),
                        )
                        if xy_key in used_xy:
                            log(
                                "That XY has already been recorded at this Z. "
                                "Enter a different placement."
                            )
                            continue
                        used_xy.add(xy_key)
                        break

                    xy_token = (
                        f"x_{safe_height_token(board_x_mm).replace('mm','')}_"
                        f"y_{safe_height_token(board_y_mm).replace('mm','')}"
                    )
                    if args.placements_per_height == 1:
                        placement_name = f"h_{height_token}"
                    else:
                        placement_name = (
                            f"h_{height_token}/"
                            f"placement_{placement_index:02d}_{xy_token}"
                        )

                    for cam in CAMERAS:
                        ensure_dir(frame_root / cam / placement_name)

                    log()
                    log(
                        f"[PLACEMENT {placement_index}/"
                        f"{args.placements_per_height}] "
                        f"Z={height_mm:.3f} mm | "
                        f"board center XY=({board_x_mm:.3f}, "
                        f"{board_y_mm:.3f}) mm"
                    )

                    if args.settle_seconds > 0:
                        log(
                            f"Waiting {args.settle_seconds:.1f}s "
                            "for board settling ..."
                        )
                        settle_end = time.time() + args.settle_seconds
                        while time.time() < settle_end:
                            rclpy.spin_once(node, timeout_sec=0.05)

                    placement_counts = {
                        cam: {
                            "expected_marker_observations": (
                                args.frames_per_placement * len(selected_ids)
                            ),
                            "detected_marker_observations": 0,
                            "pnp_valid": 0,
                        }
                        for cam in CAMERAS
                    }
                    pair_deltas = []

                    for frame_idx in range(
                        1, args.frames_per_placement + 1
                    ):
                        snaps, pair_delta_ms = wait_fresh_pair(
                            node,
                            last_seq,
                            timeout_s=args.frame_timeout_s,
                        )
                        pair_deltas.append(pair_delta_ms)

                        for cam in CAMERAS:
                            last_seq[cam] = snaps[cam].color_seq

                        detections = detect_pair(snaps)
                        host_time = iso_now()

                        rel_color_paths = {}
                        rel_depth_paths = {}

                        for cam in CAMERAS:
                            snap = snaps[cam]
                            cam_step_dir = frame_root / cam / placement_name

                            color_path = (
                                cam_step_dir
                                / f"frame_{frame_idx:04d}_color.png"
                            )
                            ok = cv2.imwrite(str(color_path), snap.color)
                            if not ok:
                                raise RuntimeError(
                                    f"Failed to save color image: {color_path}"
                                )
                            rel_color_paths[cam] = str(
                                color_path.relative_to(run_root)
                            )

                            if snap.depth is not None:
                                depth_base = (
                                    cam_step_dir
                                    / f"frame_{frame_idx:04d}_depth"
                                )
                                rel_depth_paths[cam] = save_depth_image(
                                    snap.depth,
                                    depth_base,
                                )
                            else:
                                rel_depth_paths[cam] = ""

                        # One row per expected marker per camera per frame.
                        for cam in CAMERAS:
                            snap = snaps[cam]
                            other_cam = (
                                "ihawk2" if cam == "ihawk1" else "ihawk1"
                            )
                            other_stamp = snaps[other_cam].color_stamp
                            found = detections[cam]

                            for marker_id in selected_ids:
                                position = position_map[marker_id]
                                local_x, local_y = (
                                    LOCAL_GT_BY_POSITION[position]
                                )
                                marker_gt_x = board_x_mm + local_x
                                marker_gt_y = board_y_mm + local_y

                                base = {key: "" for key in csv_fields}

                                base.update({
                                    "run_id": run_id,
                                    "capture_time_host": host_time,
                                    "height_step_index": height_step_index,
                                    "height_gt_mm": f"{height_mm:.6f}",
                                    "placement_index": placement_index,
                                    "board_center_gt_x_mm": (
                                        f"{board_x_mm:.6f}"
                                    ),
                                    "board_center_gt_y_mm": (
                                        f"{board_y_mm:.6f}"
                                    ),
                                    "board_rotation_gt_deg": "0.000000",
                                    "marker_local_x_mm": (
                                        f"{local_x:.6f}"
                                    ),
                                    "marker_local_y_mm": (
                                        f"{local_y:.6f}"
                                    ),
                                    "marker_gt_x_mm": (
                                        f"{marker_gt_x:.6f}"
                                    ),
                                    "marker_gt_y_mm": (
                                        f"{marker_gt_y:.6f}"
                                    ),
                                    "frame_index": frame_idx,
                                    "camera_id": cam,
                                    "camera_role": (
                                        args.ihawk1_role
                                        if cam == "ihawk1"
                                        else args.ihawk2_role
                                    ),
                                    "color_stamp_sec": (
                                        f"{snap.color_stamp:.9f}"
                                    ),
                                    "other_camera_color_stamp_sec": (
                                        f"{other_stamp:.9f}"
                                    ),
                                    "pair_delta_ms": (
                                        f"{pair_delta_ms:.6f}"
                                    ),
                                    "pair_sync_valid": int(
                                        pair_delta_ms
                                        <= args.max_pair_delta_ms
                                    ),
                                    "marker_id": marker_id,
                                    "board_position": position,
                                    "board_gt_z_mm": (
                                        f"{height_mm:.6f}"
                                    ),
                                    "color_image_relpath": (
                                        rel_color_paths[cam]
                                    ),
                                    "depth_image_relpath": (
                                        rel_depth_paths[cam]
                                    ),
                                })

                                if snap.depth_stamp is not None:
                                    base["depth_available"] = 1
                                    base["depth_stamp_sec"] = (
                                        f"{snap.depth_stamp:.9f}"
                                    )
                                    base["color_depth_delta_ms"] = (
                                        f"{abs(snap.depth_stamp - snap.color_stamp) * 1000.0:.6f}"
                                    )
                                    base["depth_encoding"] = (
                                        node.states[cam].depth_encoding
                                    )
                                else:
                                    base["depth_available"] = 0

                                if marker_id not in found:
                                    base["detection_valid"] = 0
                                    base["pnp_valid"] = 0
                                    base["depth_center_roi_status"] = (
                                        "marker_missing"
                                    )
                                    writer.writerow(base)
                                    continue

                                placement_counts[cam][
                                    "detected_marker_observations"
                                ] += 1

                                corners = found[marker_id]
                                center = np.mean(corners, axis=0)
                                und_corners = undistort_points_px(
                                    corners,
                                    snap.K,
                                    snap.D,
                                )
                                und_center = np.mean(
                                    und_corners,
                                    axis=0,
                                )

                                base["detection_valid"] = 1
                                base["center_u_raw_px"] = (
                                    f"{center[0]:.6f}"
                                )
                                base["center_v_raw_px"] = (
                                    f"{center[1]:.6f}"
                                )
                                base["center_u_undist_px"] = (
                                    f"{und_center[0]:.6f}"
                                )
                                base["center_v_undist_px"] = (
                                    f"{und_center[1]:.6f}"
                                )

                                for k in range(4):
                                    base[
                                        f"corner{k}_u_raw_px"
                                    ] = f"{corners[k, 0]:.6f}"
                                    base[
                                        f"corner{k}_v_raw_px"
                                    ] = f"{corners[k, 1]:.6f}"
                                    base[
                                        f"corner{k}_u_undist_px"
                                    ] = f"{und_corners[k, 0]:.6f}"
                                    base[
                                        f"corner{k}_v_undist_px"
                                    ] = f"{und_corners[k, 1]:.6f}"

                                pose = solve_marker_pose_mm(
                                    corners,
                                    snap.K,
                                    snap.D,
                                )
                                base["pnp_valid"] = int(
                                    pose["valid"]
                                )
                                base["pnp_method"] = pose["method"]

                                if pose["valid"]:
                                    placement_counts[cam][
                                        "pnp_valid"
                                    ] += 1
                                    t = pose["tvec_mm"]
                                    r = pose["rvec"]
                                    base["pnp_tx_camera_mm"] = (
                                        f"{t[0]:.6f}"
                                    )
                                    base["pnp_ty_camera_mm"] = (
                                        f"{t[1]:.6f}"
                                    )
                                    base["pnp_tz_camera_mm"] = (
                                        f"{t[2]:.6f}"
                                    )
                                    base["pnp_rvec_x"] = (
                                        f"{r[0]:.9f}"
                                    )
                                    base["pnp_rvec_y"] = (
                                        f"{r[1]:.9f}"
                                    )
                                    base["pnp_rvec_z"] = (
                                        f"{r[2]:.9f}"
                                    )
                                    base[
                                        "pnp_reprojection_rmse_px"
                                    ] = (
                                        f"{pose['reprojection_rmse_px']:.6f}"
                                    )

                                depth_val, depth_n, depth_status = (
                                    depth_roi_value(
                                        snap.depth,
                                        snap.color.shape,
                                        center[0],
                                        center[1],
                                    )
                                )
                                base[
                                    "depth_center_roi_raw_median"
                                ] = (
                                    ""
                                    if not math.isfinite(depth_val)
                                    else f"{depth_val:.6f}"
                                )
                                base[
                                    "depth_center_roi_valid_pixels"
                                ] = depth_n
                                base[
                                    "depth_center_roi_status"
                                ] = depth_status

                                writer.writerow(base)

                        f.flush()

                        d1 = len(detections["ihawk1"])
                        d2 = len(detections["ihawk2"])
                        log(
                            f"  [CAPTURE {frame_idx:02d}/"
                            f"{args.frames_per_placement}] "
                            f"pair Δt={pair_delta_ms:.1f} ms | "
                            f"markers ihawk1={d1}, ihawk2={d2}"
                        )

                    placement_record = {
                        "placement_index": placement_index,
                        "board_center_gt_x_mm": board_x_mm,
                        "board_center_gt_y_mm": board_y_mm,
                        "board_rotation_gt_deg": 0.0,
                        "frames": args.frames_per_placement,
                        "pair_delta_ms": {
                            "mean": float(np.mean(pair_deltas)),
                            "median": float(np.median(pair_deltas)),
                            "max": float(np.max(pair_deltas)),
                        },
                        "cameras": placement_counts,
                        "completed_at": iso_now(),
                    }
                    height_record["placements"].append(
                        placement_record
                    )

                    log(
                        f"[PLACEMENT PASS] {placement_index}/"
                        f"{args.placements_per_height} | "
                        f"XY=({board_x_mm:.3f}, {board_y_mm:.3f}) mm | "
                        f"ihawk1 "
                        f"{placement_counts['ihawk1']['detected_marker_observations']}/"
                        f"{placement_counts['ihawk1']['expected_marker_observations']} | "
                        f"ihawk2 "
                        f"{placement_counts['ihawk2']['detected_marker_observations']}/"
                        f"{placement_counts['ihawk2']['expected_marker_observations']}"
                    )
                    log()

                # Only after all nine placements is this Z considered complete.
                height_record["completed_at"] = iso_now()
                height_record["n_placements"] = len(
                    height_record["placements"]
                )
                summary["height_steps"].append(height_record)
                summary_path.write_text(
                    json.dumps(summary, indent=2),
                    encoding="utf-8",
                )

                log("------------------------------------------------------------")
                log(
                    f"[HEIGHT PASS] Z={height_mm:.3f} mm | "
                    f"{len(height_record['placements'])}/"
                    f"{args.placements_per_height} placements complete"
                )
                log("Recorded board-center XY values:")
                for rec in height_record["placements"]:
                    log(
                        f"  P{rec['placement_index']:02d}: "
                        f"({rec['board_center_gt_x_mm']:.3f}, "
                        f"{rec['board_center_gt_y_mm']:.3f}) mm"
                    )
                log("Now set the next physical Z and enter the next height.")
                log("------------------------------------------------------------")
                log()

        summary["status"] = "completed"
        summary["finished_at"] = iso_now()
        summary["n_height_steps"] = len(summary["height_steps"])
        summary["placements_per_height_required"] = args.placements_per_height
        summary["frames_per_placement"] = args.frames_per_placement
        summary["height_values_mm"] = [
            x["height_gt_mm"]
            for x in summary["height_steps"]
        ]
        summary_path.write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

        log("================================================================")
        log("[PASS] E2 HEIGHT SCAN RUN COMPLETE")
        log("================================================================")
        log(f"Raw CSV : {csv_path}")
        log(f"Metadata: {metadata_path}")
        log(f"Summary : {summary_path}")
        log(f"Frames  : {frame_root}")
        log()
        log(
            f"Recorded {len(summary['height_steps'])} height step(s): "
            f"{summary['height_values_mm']}"
        )

    except KeyboardInterrupt:
        summary["status"] = "interrupted"
        summary["finished_at"] = iso_now()
        summary["n_height_steps"] = len(summary["height_steps"])
        summary_path.write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        log()
        log("[INTERRUPTED] Existing data were kept and flushed to disk.")
        log(f"Partial run: {run_root}")

    finally:
        node.destroy_node()
        rclpy.shutdown()


def build_parser():
    p = argparse.ArgumentParser(
        description=(
            "Interactive E2 dual-camera height-scan collector "
            "(DICT_4X4_50, 50 mm markers, A4 board)"
        )
    )

    p.add_argument(
        "--frames-per-placement",
        type=int,
        default=10,
        help=(
            "Fresh synchronized dual-camera frame pairs collected at each "
            "board-center XY placement."
        ),
    )
    p.add_argument(
        "--placements-per-height",
        type=int,
        default=9,
        help=(
            "Number of XY board-center placements required before the next "
            "height can be entered. Formal E2 uses 9."
        ),
    )
    p.add_argument(
        "--pilot",
        action="store_true",
        help=(
            "Pilot mode: force one XY placement per height. Pilot runs are "
            "not formal E2 datasets."
        ),
    )
    p.add_argument(
        "--output-root",
        default=str(DEFAULT_ROOT),
    )
    p.add_argument(
        "--max-pair-delta-ms",
        type=float,
        default=50.0,
        help="Maximum ihawk1/ihawk2 RGB timestamp difference.",
    )
    p.add_argument(
        "--frame-timeout-s",
        type=float,
        default=10.0,
    )
    p.add_argument(
        "--marker-discovery-timeout-s",
        type=float,
        default=30.0,
    )
    p.add_argument(
        "--settle-seconds",
        type=float,
        default=1.0,
        help="Wait after height input before collecting.",
    )

    p.add_argument(
        "--ihawk1-role",
        default="primary",
        help="Human-readable role label stored in the dataset.",
    )
    p.add_argument(
        "--ihawk2-role",
        default="secondary",
        help="Human-readable role label stored in the dataset.",
    )

    p.add_argument(
        "--ihawk1-depth-topic",
        default="",
        help="Optional explicit ihawk1 depth Image topic.",
    )
    p.add_argument(
        "--ihawk2-depth-topic",
        default="",
        help="Optional explicit ihawk2 depth Image topic.",
    )

    p.add_argument(
        "--depth-aligned-to-color",
        action="store_true",
        help=(
            "Explicitly assert that depth pixels are registered/aligned to "
            "the RGB pixels. Without this flag, raw depth images are still "
            "saved but RGB-center depth sampling is NOT performed."
        ),
    )
    p.add_argument(
        "--depth-roi-radius-px",
        type=int,
        default=2,
        help="Radius for center depth median if aligned depth is asserted.",
    )

    return p


def main():
    args = build_parser().parse_args()

    if args.frames_per_placement <= 0:
        raise SystemExit("--frames-per-placement must be > 0")
    if args.pilot:
        args.placements_per_height = 1
    if args.placements_per_height <= 0:
        raise SystemExit("--placements-per-height must be > 0")
    if args.max_pair_delta_ms <= 0:
        raise SystemExit("--max-pair-delta-ms must be > 0")
    if args.depth_roi_radius_px < 0:
        raise SystemExit("--depth-roi-radius-px must be >= 0")

    run_collector(args)


if __name__ == "__main__":
    main()
