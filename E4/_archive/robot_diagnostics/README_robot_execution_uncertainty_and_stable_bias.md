# Robot Execution Uncertainty and Stable Cartesian Bias

## 1. 这个文件记录什么

本文件记录 RoArm-M3-S 在 E4 前置诊断中发现的一个重要现象：

> IK 求解成功，并不等于真实机械臂末端一定准确到达目标 Cartesian pose。

在此前 H1 测试中：

- MoveIt + IKFast 能够为目标位姿计算出合法 joint solution；
- T104 能够驱动机械臂运动；
- 但机械臂稳定后仍存在明显 Cartesian residual；
- 当时观察到的 T104 Cartesian bias 大约为 7–8 mm；
- 因此问题不能简单归因于“IK 算不出来”。

为了进一步区分原因，之后进行了：

1. T104 firmware Cartesian control
2. IKFast 求出 joint solution
3. 使用 T102 直接发送 IKFast joint target
4. 比较最终 Cartesian residual 与 joint residual

目的就是区分：

- IK / Cartesian controller 问题
- joint tracking 问题
- robot geometry/model mismatch
- frame / TCP mismatch
- mechanical systematic bias


---

# 2. 最重要的概念：Accuracy 和 Repeatability 不一样

机械臂可能出现：

    每次都到错的位置，
    但每次错得几乎一样。

例如：

    Commanded target:
        X = 200 mm
        Y = 50 mm

    Actual endpoint:
        Trial 1 = (207.2, 49.4)
        Trial 2 = (207.5, 49.2)
        Trial 3 = (207.3, 49.5)

这种情况：

    Repeatability = 很好
    Absolute accuracy = 不好

也就是说：

    小随机波动
    +
    大稳定偏差

并不矛盾。

这种稳定偏差可称为：

    systematic Cartesian bias
    pose-dependent systematic bias
    execution bias

它和随机 uncertainty 必须分开分析。


---

# 3. IKFast 在这里到底解决了什么

IKFast解决的是：

    Desired Cartesian pose
             ↓
    mathematical robot model
             ↓
    joint angles q1...qn

即：

    x_target
        ↓ IK
    q_target

它回答的是：

> “按照这个机器人模型，哪些关节角应该产生这个末端位姿？”

但是实际系统还有下一半：

    q_target
        ↓
    controller
        ↓
    motor / servo
        ↓
    gearbox / linkage
        ↓
    physical robot
        ↓
    actual endpoint

因此：

    IK 正确

只能说明：

    数学求解层没有明显失败

不能证明：

    actual endpoint = target endpoint


---

# 4. 为什么 IK 正确后仍然可能存在稳定误差

完整链路可以写成：

    Target Cartesian Pose
              ↓
             IK
              ↓
       Target Joint Angles
              ↓
      Firmware / Controller
              ↓
        Servo Tracking
              ↓
      Mechanical Structure
              ↓
        Actual Joint Pose
              ↓
     Real Robot Geometry
              ↓
       Actual TCP Position

任何一层都可能引入误差。


---

# 5. Robot uncertainty / error source 分类

## A. Kinematic model uncertainty

### A1. Link length mismatch

URDF / IK 模型中的 link length 与真实机械臂不完全相同。

例如模型认为：

    L2 = 120.0 mm

真实机械臂可能是：

    L2 = 119.x mm 或 120.x mm

单个 link 的小偏差会通过 forward kinematics 传播到 TCP。


### A2. Joint zero-offset

数学模型中的：

    joint = 0 rad

未必等于真实机械臂的物理零点。

因此即使：

    commanded q = IK q

真实 joint angle 仍可能整体偏移。


### A3. Axis alignment / assembly tolerance

真实关节轴：

- 不一定完全平行
- 不一定完全垂直
- 装配位置可能存在小偏差

这些误差不会出现在理想 URDF 中。


### A4. TCP / pointer geometry

机器人内部计算的位置通常对应某个理论末端 frame。

但是我们实际测的是：

    pointer tip

如果：

    tool0 / TCP / pointer tip

之间存在未建模 offset，那么会产生稳定 Cartesian bias。


---

# 6. Controller uncertainty

## B1. T104 Cartesian controller

T104并不是：

    输入 XYZ
    → 机械臂物理末端必然准确到 XYZ

内部仍包含：

    Cartesian target
        ↓
    firmware IK
        ↓
    trajectory generation
        ↓
    servo commands
        ↓
    termination condition

如果 controller 的停止条件允许一定误差：

    robot stable

并不等于：

    robot reached exact target


## B2. Joint tracking error

即使 IKFast 给出的 joint target 完全正确：

    q_target

servo 最后可能只到：

    q_actual = q_target + Δq

小的 Δq 经过 forward kinematics 后可能形成明显的 TCP ΔX/ΔY。


## B3. PID / control parameters

例如：

    P
    I
    speed
    acceleration

都会影响：

- steady-state error
- overshoot
- settling
- final pose
- repeatability

因此正式 E4 必须固定 controller configuration。


## B4. Firmware implementation

上位机发出的：

    T101
    T102
    T104

并不是同一条控制路径。

不同 command 可能经过不同：

- IK
- trajectory
- speed interpretation
- joint command logic
- termination logic

因此 command interface 本身也是 uncertainty source。


---

# 7. Mechanical uncertainty

## C1. Gear backlash

关节从：

    clockwise approach

和：

    counter-clockwise approach

到达同一个 nominal angle 时，真实位置可能不同。

因此 approach direction 必须固定。


## C2. Joint compliance

机械结构不是无限刚性的。

不同姿态下：

- gravity
- arm extension
- payload

会造成不同程度的结构变形。


## C3. Servo resolution / deadband

低成本 servo 存在：

- encoder resolution
- command quantisation
- dead zone
- holding error

因此很小的目标变化未必产生可观察的末端运动。


## C4. Friction

static friction / joint friction 会导致：

    controller command 已经很接近目标
    但不足以继续驱动关节

于是机械臂稳定停在一个有偏差的位置。


## C5. Pose-dependent error

机械臂误差通常不是整个 workspace 都一样。

例如：

    center = 3 mm
    left = 5 mm
    far reach = 8 mm

因此不能只用一个点描述整个机械臂 accuracy。


---

# 8. Experimental / measurement uncertainty

## D1. Paper → robot registration

即使机械臂完美执行：

    paper coordinate
        ↓ registration
    robot coordinate

本身也可能存在 registration error。

所以：

    endpoint error

不全部属于 controller。


## D2. Manual measurement

人工读取 pointer 的实际 XY 会产生：

- ruler/grid resolution
- parallax
- pointer width
- human judgement

这属于 ground-truth measurement uncertainty。


## D3. Robot internal feedback

T105/T1051 是：

    robot firmware 对自己状态的估计

它不是独立 physical ground truth。

因此：

    commanded XYZ
        vs
    T105 XYZ

只能用于 controller diagnostic。

正式 end-to-end accuracy 应使用外部物理 measurement。


---

# 9. Error 和 Uncertainty 要区分

严格来说：

## Systematic error / bias

例如：

    每次都向 +X 偏 7 mm

这是：

    systematic bias

如果原因和大小已经完全已知，可以进行 correction。


## Random uncertainty

例如：

    同一目标重复 20 次

结果在：

    ±2 mm

范围内波动。

这是：

    repeatability / random uncertainty。


所以系统可以写成：

    observed endpoint error
        =
    systematic bias
        +
    random variation
        +
    measurement uncertainty


更完整地：

    E_total
      ≈
    E_vision
      +
    E_registration
      +
    E_robot_systematic
      +
    E_robot_repeatability
      +
    E_measurement


注意：

这些项在严格统计上不一定可以简单线性相加；
这个公式主要用于理解 error propagation。


---

# 10. 为什么这个问题对 B2 非常重要

论文真正比较的是：

    Affine
    Homography
    PnP

假设视觉误差为：

    Affine       4.0 mm
    Homography   2.5 mm
    PnP          2.0 mm

但机械臂 downstream uncertainty / bias 已经是：

    5–8 mm

那么到了真实 endpoint：

视觉模型之间 1–2 mm 的改善可能被机械臂执行层掩盖。


因此：

    better vision accuracy

不一定意味着：

    equally large improvement in physical endpoint accuracy


这不是实验失败。

这本身就是一个重要研究结果：

> 视觉定位精度只有在 downstream robot uncertainty 足够低时，
> 才能完整转化为真实机械臂末端定位精度。


---

# 11. 为什么 E4-A 要加入 Oracle

Oracle 的意义是绕过视觉。

Oracle 输入：

    known physical paper GT
        ↓
    paper→robot
        ↓
    robot execution
        ↓
    measured endpoint

因此 Oracle 测量的是近似：

    registration
    +
    controller
    +
    mechanics
    +
    measurement

形成的 downstream error floor。


而：

    Affine / Homography / PnP

则额外加入：

    vision model error


因此：

    Oracle
       ↓
    downstream floor

    Affine/H/PnP - Oracle
       ↓
    vision error transferred through robot system


这是解释 E4 结果最重要的 baseline。


---

# 12. 当前实验中必须固定的 robot factors

正式 E4-A 应固定：

- robot base physical position
- paper physical position
- paper frame
- pointer / TCP setup
- starting pose
- controller type
- T104 execution path
- base PID
- speed
- descent speed
- target tilt
- approach direction
- payload
- measurement procedure

否则：

    method difference

可能实际上来自：

    robot condition difference


---

# 13. 当前正式 E4 的处理原则

目前正式 E4-A 使用：

    Base PID = P16 / I8
    Controller = T104 Cartesian only
    Extra T101 correction = OFF
    Fixed target tilt
    Fixed start
    Same vertical approach

重点不是把 RoArm 调成“绝对完美”。

重点是：

> 为所有视觉模型提供完全相同、稳定、可复现的 downstream robot system。

因此即使机械臂存在稳定 bias：

只要：

    Oracle
    Affine
    Homography
    PnP

全部经过相同 downstream chain，

模型之间的比较仍然可以保持公平。


---

# 14. 对此前 IK 诊断的最终解释

此前观察到：

    IKFast solved successfully
             ↓
    joint target available
             ↓
    robot can move
             ↓
    stable Cartesian error remains

这说明：

不能简单写：

    "IK was inaccurate"

更准确的描述是：

> A stable pose-dependent Cartesian execution bias remained despite successful
> inverse-kinematics solution, indicating that the dominant downstream error
> could arise from controller execution, joint tracking, robot/model mismatch,
> TCP definition, mechanical effects, or a combination of these factors.

因此这个问题应该归类为：

    ROBOT EXECUTION UNCERTAINTY / SYSTEMATIC BIAS

而不是：

    VISION ERROR

也不能单纯归类为：

    IK FAILURE


---

# 15. 对论文结果的影响

最终分析至少分成三层：

## Layer 1 — Vision

    camera
      ↓
    Affine / Homography / PnP
      ↓
    predicted paper XY


## Layer 2 — Registration

    predicted paper XY
      ↓
    paper→robot transform
      ↓
    commanded robot XYZ


## Layer 3 — Robot execution

    commanded XYZ
      ↓
    controller
      ↓
    mechanics
      ↓
    measured physical endpoint


最终：

    Vision error
         ↓
    Registration error
         ↓
    Robot execution uncertainty
         ↓
    Physical end-to-end error


E4-A 的作用就是观察：

> 前面不同视觉模型的精度差异，在经过真实低成本机械臂的
> downstream uncertainty 后，还能保留多少。

