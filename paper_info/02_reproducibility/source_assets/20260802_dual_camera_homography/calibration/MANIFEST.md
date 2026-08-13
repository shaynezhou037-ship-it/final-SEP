# MANIFEST - camera_board_calibration

## 状态

- status: active
- topic: camera_board_calibration
- role: 当前相机棋盘标定 / 双相机 homography 默认数据

## 主要文件

- `overhead_B242_intrinsics_640x400_final.json`
- `side_B479_intrinsics_640x400_final.json`
- `overhead_B242_final_homography_25mm.json`
- `side_B479_final_homography_25mm.json`
- `dual_final_homography_summary.json`
- `dual_aruco_one_point_validation_175_25.json`

## 推荐验证脚本

- `scripts/camera_board_calibration/validate_dual_aruco_one_point_175_25.py`
- `scripts/camera_board_calibration/compute_dual_final_homography_undistorted_0802.py`

## 当前结论

- 见根目录 `CURRENT_STATE.md`。
