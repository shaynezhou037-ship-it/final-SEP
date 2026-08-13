#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E4 ChArUco orientation preflight
================================

Purpose:
- DO NOT collect/freeze calibration data yet.
- Grab one good color frame from ihawk1 and ihawk2.
- Detect the 9x7 ChArUco board.
- Use the detected ChArUco corners to estimate the board->image homography.
- Project and label the FOUR OUTER BOARD CORNERS using intrinsic board labels:

    B00 = board coordinate (0,   0)     : print-design origin
    BX  = board coordinate (225, 0)     : +board X
    BXY = board coordinate (225, 175)
    BY  = board coordinate (0,   175)   : +board Y

IMPORTANT:
These labels belong to the printed board itself.
They are NOT "camera image top-left / top-right".

If the camera is rotated, B00 may appear at image bottom-right, etc.
That is completely fine.

Run this first, inspect the two annotated PNG files, then map
B00/BX/BXY/BY to the already-existing paper_frame coordinates.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


SQUARES_X = 9
SQUARES_Y = 7
SQUARE_LENGTH_MM = 25.0
MARKER_LENGTH_MM = 18.0
BOARD_W_MM = 225.0
BOARD_H_MM = 175.0


def get_dictionary():
    if hasattr(cv2.aruco, "Dictionary_get"):
        return cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def make_board(dictionary):
    if hasattr(cv2.aruco, "CharucoBoard_create"):
        return cv2.aruco.CharucoBoard_create(
            SQUARES_X,
            SQUARES_Y,
            SQUARE_LENGTH_MM,
            MARKER_LENGTH_MM,
            dictionary,
        )
    return cv2.aruco.CharucoBoard(
        (SQUARES_X, SQUARES_Y),
        SQUARE_LENGTH_MM,
        MARKER_LENGTH_MM,
        dictionary,
    )


def make_params():
    if hasattr(cv2.aruco, "DetectorParameters_create"):
        p = cv2.aruco.DetectorParameters_create()
    else:
        p = cv2.aruco.DetectorParameters()

    if hasattr(cv2.aruco, "CORNER_REFINE_SUBPIX"):
        p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    if hasattr(p, "cornerRefinementWinSize"):
        p.cornerRefinementWinSize = 5
    if hasattr(p, "cornerRefinementMaxIterations"):
        p.cornerRefinementMaxIterations = 50
    if hasattr(p, "cornerRefinementMinAccuracy"):
        p.cornerRefinementMinAccuracy = 0.01
    return p


def board_chessboard_corners(board):
    if hasattr(board, "chessboardCorners"):
        pts = np.asarray(board.chessboardCorners, dtype=np.float64)
    elif hasattr(board, "getChessboardCorners"):
        pts = np.asarray(board.getChessboardCorners(), dtype=np.float64)
    else:
        raise RuntimeError("Cannot read ChArUco chessboard corners.")
    return pts.reshape(-1, 3)


def detect(gray, board, dictionary, params):
    marker_corners, marker_ids, rejected = cv2.aruco.detectMarkers(
        gray, dictionary, parameters=params
    )
    if marker_ids is None or len(marker_ids) < 4:
        return None

    retval, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
        marker_corners,
        marker_ids,
        gray,
        board,
    )

    if charuco_ids is None or charuco_corners is None or int(retval) < 8:
        return None

    cc = charuco_corners.reshape(-1, 2).astype(np.float32)

    # Explicit sub-pixel refinement.
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        50,
        0.001,
    )
    h, w = gray.shape[:2]
    if np.all(
        (cc[:, 0] >= 6)
        & (cc[:, 0] < w - 6)
        & (cc[:, 1] >= 6)
        & (cc[:, 1] < h - 6)
    ):
        tmp = cc.reshape(-1, 1, 2)
        cv2.cornerSubPix(gray, tmp, (5, 5), (-1, -1), criteria)
        cc = tmp.reshape(-1, 2)

    return {
        "marker_corners": marker_corners,
        "marker_ids": marker_ids,
        "charuco_corners": cc,
        "charuco_ids": charuco_ids.reshape(-1).astype(int),
    }


def estimate_board_to_image_h(det, board):
    obj_all = board_chessboard_corners(board)

    board_xy = []
    image_uv = []

    for uv, cid in zip(det["charuco_corners"], det["charuco_ids"]):
        xyz = obj_all[int(cid)]
        board_xy.append([float(xyz[0]), float(xyz[1])])
        image_uv.append([float(uv[0]), float(uv[1])])

    board_xy = np.asarray(board_xy, dtype=np.float64)
    image_uv = np.asarray(image_uv, dtype=np.float64)

    # Direct homography only. No RANSAC: this is just a visualization preflight.
    H, _ = cv2.findHomography(board_xy, image_uv, method=0)
    if H is None:
        raise RuntimeError("Could not estimate board->image homography.")

    return H


def project(H, xy):
    p = np.asarray([[xy]], dtype=np.float64)
    return cv2.perspectiveTransform(p, H).reshape(2)


def annotate(bgr, det, H, camera):
    out = bgr.copy()

    cv2.aruco.drawDetectedMarkers(
        out,
        det["marker_corners"],
        det["marker_ids"],
    )

    try:
        cv2.aruco.drawDetectedCornersCharuco(
            out,
            det["charuco_corners"].reshape(-1, 1, 2),
            det["charuco_ids"].reshape(-1, 1),
        )
    except Exception:
        pass

    anchors = {
        "B00 (0,0)": np.array([0.0, 0.0]),
        "BX (+X)": np.array([BOARD_W_MM, 0.0]),
        "BXY": np.array([BOARD_W_MM, BOARD_H_MM]),
        "BY (+Y)": np.array([0.0, BOARD_H_MM]),
        "CENTER": np.array([BOARD_W_MM / 2.0, BOARD_H_MM / 2.0]),
    }

    pix = {name: project(H, xy) for name, xy in anchors.items()}

    # Outer boundary
    poly = np.array([
        pix["B00 (0,0)"],
        pix["BX (+X)"],
        pix["BXY"],
        pix["BY (+Y)"],
    ], dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(out, [poly], True, (255, 255, 255), 2, cv2.LINE_AA)

    def ipt(v):
        return (int(round(float(v[0]))), int(round(float(v[1]))))

    # Board axes: +X and +Y start at intrinsic board origin B00.
    p0 = ipt(pix["B00 (0,0)"])
    px = ipt(pix["BX (+X)"])
    py = ipt(pix["BY (+Y)"])

    cv2.arrowedLine(out, p0, px, (0, 0, 255), 3, cv2.LINE_AA, tipLength=0.08)
    cv2.arrowedLine(out, p0, py, (0, 255, 0), 3, cv2.LINE_AA, tipLength=0.08)

    labels = [
        ("B00 (0,0)", "B00", (255, 0, 255)),
        ("BX (+X)", "BX", (0, 0, 255)),
        ("BXY", "BXY", (255, 255, 0)),
        ("BY (+Y)", "BY", (0, 255, 0)),
        ("CENTER", "CENTER", (255, 255, 255)),
    ]

    for key, text, color in labels:
        p = ipt(pix[key])
        cv2.circle(out, p, 8, color, -1)
        cv2.putText(
            out, text, (p[0] + 8, p[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA
        )

    cv2.putText(
        out,
        f"{camera}: RED=board +X, GREEN=board +Y",
        (12, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    return out, pix


class OrientationCheck(Node):
    def __init__(self, args):
        super().__init__("e4_charuco_orientation_check")
        self.args = args
        self.bridge = CvBridge()
        self.dictionary = get_dictionary()
        self.board = make_board(self.dictionary)
        self.params = make_params()

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out_dir = Path(args.out_root) / run_id
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.done = {"ihawk1": False, "ihawk2": False}
        self.results = {}

        print("=" * 88, flush=True)
        print("E4 CHARUCO ORIENTATION PREFLIGHT — NO CALIBRATION FREEZE", flush=True)
        print("=" * 88, flush=True)
        print("Intrinsic board labels:", flush=True)
        print("  B00 = (0,0) mm       : board print-design origin", flush=True)
        print("  BX  = (225,0) mm     : board +X", flush=True)
        print("  BXY = (225,175) mm", flush=True)
        print("  BY  = (0,175) mm     : board +Y", flush=True)
        print("", flush=True)
        print("These are NOT camera-image TL/TR/BR/BL.", flush=True)
        print(f"Output: {self.out_dir}", flush=True)
        print("=" * 88, flush=True)

        self.sub1 = self.create_subscription(
            Image, args.topic1,
            lambda msg: self.on_image("ihawk1", msg),
            10,
        )
        self.sub2 = self.create_subscription(
            Image, args.topic2,
            lambda msg: self.on_image("ihawk2", msg),
            10,
        )

    def on_image(self, camera, msg):
        if self.done[camera]:
            return

        try:
            bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as e:
            self.get_logger().error(f"{camera}: cv_bridge failed: {e}")
            return

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        det = detect(gray, self.board, self.dictionary, self.params)
        if det is None:
            return

        H = estimate_board_to_image_h(det, self.board)
        ann, pix = annotate(bgr, det, H, camera)

        raw_path = self.out_dir / f"{camera}_raw.png"
        ann_path = self.out_dir / f"{camera}_orientation_annotated.png"

        cv2.imwrite(str(raw_path), bgr)
        cv2.imwrite(str(ann_path), ann)

        self.results[camera] = {
            "detected_aruco_markers": int(len(det["marker_ids"])),
            "detected_charuco_corners": int(len(det["charuco_ids"])),
            "projected_outer_board_pixels": {
                k: [float(v[0]), float(v[1])]
                for k, v in pix.items()
            },
            "raw_image": str(raw_path),
            "annotated_image": str(ann_path),
        }
        self.done[camera] = True

        print(f"\n[{camera}] GOOD FRAME", flush=True)
        print(
            f"  markers={len(det['marker_ids'])}, "
            f"charuco={len(det['charuco_ids'])}",
            flush=True
        )
        for k, v in pix.items():
            print(f"  {k:12s} -> image (u,v)=({v[0]:.2f},{v[1]:.2f})", flush=True)
        print(f"  annotated: {ann_path}", flush=True)

        if all(self.done.values()):
            summary = self.out_dir / "orientation_summary.json"
            summary.write_text(
                json.dumps(self.results, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print("\n" + "=" * 88, flush=True)
            print("ORIENTATION PREFLIGHT COMPLETE", flush=True)
            print(f"Summary: {summary}", flush=True)
            print("Inspect BOTH annotated PNGs.", flush=True)
            print(
                "Then assign paper_frame coordinates to B00/BX/BXY/BY "
                "(not to camera-image corners).",
                flush=True
            )
            print("=" * 88, flush=True)
            rclpy.shutdown()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--topic1", default="/ihawk1/color/color_raw")
    p.add_argument("--topic2", default="/ihawk2/color/color_raw")
    p.add_argument(
        "--out-root",
        default="/mnt/c/Users/ASUS/Desktop/paper/E4/E4_charuco_orientation_check",
    )
    return p.parse_args()


def main():
    args = parse_args()
    rclpy.init()
    node = OrientationCheck(args)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]", flush=True)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
