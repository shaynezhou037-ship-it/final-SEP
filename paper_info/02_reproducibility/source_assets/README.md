# B2 论文有效复现资产索引

最后复核：2026-08-13

本目录只保存可直接支撑论文方法、参数、历史基线或正式实验依赖的外部仓库复制件。原仓库仍位于：

- `C:\Users\ASUS\Desktop\RoArm`
- `C:\Users\ASUS\Desktop\FURP-2026-YUNKAI-CHOU-Mobile_Manipulator`

这里是论文整理快照，不是开发仓库，也不应把不同日期的标定结果混成同一批实验。

## 批次与用途

### 20260801_historical_static_repeatability

保留文件：两台相机各 30 帧的静态逐帧结果，以及汇总表。

可用于：论文中的历史静态重复性基线、说明早期系统的像素/平面坐标和深度抖动。

不可用于：替代 2026-08-07 的正式 E0-A；也不可与后续相机布局、标定或 E4 数据合并统计。

### 20260802_dual_camera_homography

保留内容：

- 两台 iHawk 在 640×400 下的内参与畸变参数；
- 25 mm 棋盘格的 undistorted pixel → common-board homography；
- homography 计算、侧相机 180° common-board 对齐和单点 ArUco 核验脚本；
- 每台相机真正用于 homography 的 `Color_1.bmp`；
- 双相机汇总与单点核验结果。

几何参数：

- 棋盘格：9×7 个方格，8×6 个内角点，单格 25 mm；
- ArUco：`DICT_4X4_50`，E0/E2 使用的 marker 外边长为 50 mm；
- 相机：B479 = ihawk1，B242 = ihawk2。

可用于：复核 2026-08-02 homography 的算法、输入、坐标定义和数值结果；在相机、分辨率、焦距与安装状态未变化时，内参可作为条件性设备参数。

不可用于：作为当前 board-to-robot；也不可自动视为 2026-08-11 E4 的 frozen Homography。E4 使用后来单独采集并冻结的 ChArUco 模型。

### 20260807_E0_robot_core_dependency

保留 `task10_guarded_approach.py` 及其正式目标输入的最小生成链：

- `aruco_depth_point_estimator.py`：由两台相机的 RGB-D 与 ArUco 检测生成 camera/base 点和质量信息；
- `dual_point_fusion.py`：按深度标准差加权融合，并发布 `/fused_target_pose_robot_corrected`；
- `camera1_empirical_correction.yaml` 与 `fused_to_robot_correction.yaml`：上述融合节点运行时实际读取的修正参数；
- ROS 2 Python 包的最小入口文件；
- `task10_guarded_approach.py`：订阅该 topic，并提供 E0 正式脚本实际导入的 `collect_target()`、`send_json()` 和 `get_pose()`。

正式 E0 结果摘要记录了 `task10_guarded_approach.py` 的来源路径；源代码追踪确认其目标输入来自上述 fusion pipeline。

可用于：复现 E0 的 ArUco RGB-D 点估计、双相机加权融合、fused-to-robot 修正、目标扫描、机器人串口命令和反馈读取方法。

不可用于：代表 FURP task1–task10 的全部旧实验结果，也不可把旧 task9 融合精度当作本论文 E0 结果。

## 当前有效的后续 board-to-robot / E4 批次

2026-08-02 的旧 5-point 3-D affine 已从本目录移除。后续论文实验重新做了 board-to-robot：

- 采集批次：`E4/E4_board_to_robot_registration/20260810_144418/`
- 原始 20 点配对：`registration_raw.csv`
- 当前平面 affine：`board_to_robot_planar_affine_model_REBUILT.json`
- 独立检查：同目录两个 `heldout_validation_*` 批次
- 2026-08-11 视觉标定：`E4/E4_charuco_calibration_v4/20260811_191758/`
- 2026-08-11 frozen 模型：`E4/E4_model_freeze_v1/20260811_192958/`
- 正式 E4-A（当前进行中，元数据记录 44/108）：`E4/E4A_formal_hover_ihawk1/20260811_195548/`

E4 ChArUco 使用 18 mm marker，属于独立于 E0/E2 的后续标定板批次；不要与 50 mm ArUco 目标混写。

注意：8 月 10 日 registration 模型的训练 XY RMSE 为 3.327 mm；两个 held-out 批次只有 2 个点，误差分别为 5/14.142 mm 和 5/12.806 mm。它确实被后续 E4 采用，但论文中应如实区分训练拟合与独立检查，不能把训练残差表述为独立精度。

## 已排除的复制件

- 2026-08-01/02 的旧 board-to-robot 表、模型、脚本和原始串口日志：已被 2026-08-10 E4 注册替代；
- vertical height logs：只反映机器人竖直运动，与正式 E2 的视觉模型×高度数据重复且不能回答同一问题；
- FURP task1–task10 旧结果、task9 incomplete/excluded 数据、旧融合/外参/robot correction：没有进入后续正式 E0/E2/E4 证据链；
- FURP ROS 相机驱动完整源码、工程报告、多版本 approach 脚本和 `__pycache__`：不是论文结果或当前唯一方法依赖；E0 的最小点估计/融合/修正链已单独保留；
- homography 的 Depth/RAW/PLY 和重复 Color 图：当前 homography 计算只读取每台相机的 `Color_1.bmp`，其余副本不参与复核。

这些删除只发生在本论文整理目录；桌面原仓库未修改。
