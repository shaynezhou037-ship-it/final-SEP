# 低成本视觉引导机器人精度分配研究：阶段性总结与冻结框架

## 摘要

本阶段将研究方向从“Affine / Homography / PnP / Stereo 的算法比较”重新收敛为：**在给定任务精度与工作条件下，分析视觉、标定、几何模型、计算与机器人执行误差如何传播至最终末端，并识别当前精度瓶颈、minimum-sufficient capability 及瓶颈切换边界。** 现有 E0–E6 不再被视为彼此独立的 benchmark，而作为真实低成本系统上的模型识别与验证数据。核心待完成工作不是继续扩充硬件或实验数量，而是建立统一的 hybrid error model、precision leverage / bottleneck switching 判据，以及可进行非循环验证的 Precision Regime Map。

---

# 1. 当前研究定位

## 1.1 已放弃的主叙事

不再以以下问题作为论文核心：

> Which localization algorithm is better: Affine, Homography, PnP, or Stereo?

原因：

* 基础算法本身已有成熟理论，单纯比较缺乏足够研究价值；
* 不同方法使用的信息并不等价，简单排名容易失去科学解释；
* E1–E6 已表现出明显的 condition-dependent behavior，说明问题本质不是“谁普遍最好”。

**状态：已确认共识。**

**反思：** 如果论文最终仍主要呈现算法 RMSE 排名，而无法预测“何时需要升级”，则应视为重新退化成 benchmark。

---

## 1.2 当前冻结的核心研究问题

研究不再问：

> 如何让系统尽可能准确？

而是问：

> **对于给定任务，到底需要多少精度？当前哪个环节限制最终末端精度？继续改善某个模块什么时候仍然有意义，什么时候已经进入边际收益递减？**

更正式地：

[
\text{Task Condition}
+
\text{Required Endpoint Precision}
+
\text{Existing System Capability}
]

[
\rightarrow
\text{Endpoint Error Prediction}
]

[
\rightarrow
\text{Dominant Precision Bottleneck}
]

[
\rightarrow
\text{Minimum Sufficient Capability / Upgrade Priority}
]

研究重点是：

### Task-conditioned precision bottleneck switching

即：

> **任务与环境发生变化时，主导末端误差的 subsystem 会发生切换。**

**状态：当前最核心、已冻结方向。**

**反思：** 这一研究价值依赖于“瓶颈切换”可以被模型预测并被真实数据验证；如果最后只能找出当前最大的误差项，则研究价值不足。

---

# 2. 研究中隐含的三个核心维度

目前所有讨论实际上围绕三个维度展开。

## 2.1 精度定义：What precision is actually required?

不是追求每个模块最高精度，而是从最终任务要求反推 minimum sufficient capability。

例如：

* endpoint P95 ≤ 5 mm；
* static target；
* Z = 0–30 mm；
* ≥30 Hz。

然后判断：

* 是否需要 PnP；
* 是否需要第二视图；
* 当前 resolution 是否已经足够；
* robot repeatability 是否成为瓶颈。

---

## 2.2 瓶颈识别：What limits endpoint performance now?

关注：

[
E_{endpoint}
]

而不是单独最小化：

[
E_{vision}
]

系统可能出现：

* model mismatch dominated；
* calibration dominated；
* sensing dominated；
* robot dominated；
* compute dominated；
* multi-view geometry dominated。

---

## 2.3 条件变化：When does the bottleneck switch?

重点不是静态 error budget，而是研究：

[
Task\ Condition
\rightarrow
Dominant\ Error\ Source
]

例如：

* planar → Homography 已足够；
* off-plane → planar model mismatch 成为主导；
* 换 PnP 后 → robot execution 可能重新成为主导；
* robot 进一步改善 → sensing / stereo geometry 可能成为下一瓶颈。

这构成预期的 **Precision Regime Map**。

---

# 3. 当前拟研究的系统框架

## 3.1 用户输入

框架原则上不依赖具体品牌或型号，而接收 capability-level parameters。

### Task

[
T=
{
E_{req},
confidence,
workspace,
Z\ range,
static/dynamic,
FPS,
target\ geometry
}
]

第一版限定：

* static / quasi-static positioning；
* eye-to-hand；
* marker-based localization；
* 不扩展至完整动态抓取。

### Camera capability

可能包括：

* resolution；
* FOV；
* projected target size；
* pixel-localization noise；
* depth accuracy / depth uncertainty；
* FPS；
* latency。

### Robot capability

可能包括：

* endpoint repeatability；
* empirical execution error；
* tracking variability；
* workspace / configuration dependence。

不要求输入具体机器人型号。

### Calibration capability

可能包括：

* point count；
* spatial coverage；
* conditioning；
* extrinsic uncertainty / stability。

### Geometry / algorithm

包括：

* Homography；
* PnP；
* one view；
* two-estimate fusion；
* calibrated stereo；
* baseline / parallax 等。

### Compute

第一版优先采用：

* measured processing latency；
* throughput；
* normalized compute budget。

而不是建立 CPU/GPU 型号数据库。

---

# 4. 核心误差模型思想

## 4.1 不能把全部误差统一称为 uncertainty

现有实验至少包含两种性质不同的误差。

### Random variability

例如：

* camera static jitter；
* corner localization variability；
* robot repeatability；
* manual reading variability。

可表示：

[
\epsilon_i
]

或 covariance：

[
\Sigma_i
]

### Systematic bias / model mismatch

例如：

Homography 在 Z=0 时误差很低，但离开标定平面后误差快速增长。

应表示为：

[
b_H(Z)
]

而不是简单称作：

[
\sigma_H
]

因此预期采用：

[
e_i(x)=b_i(x)+\epsilon_i
]

最终：

[
e_{endpoint}
============

F(
b_{model},
b_{cal},
\epsilon_{camera},
\epsilon_{cal},
\epsilon_{robot},
\epsilon_{measurement},
...
)
]

**状态：已确认共识。**

**反思：** 如果强行使用简单 RSS 或 Gaussian variance budget，会错误处理 E2 等明显的 model mismatch。

---

## 4.2 传播方法

优先考虑：

### Hybrid empirical + analytical model

各子模型可来自：

* Own Experiment；
* Physics；
* Literature；
* Datasheet；
* Simulation。

然后通过 Monte Carlo 或适当解析模型传播：

[
x_i^{(k)}\sim p_i(x)
]

[
E_{endpoint}^{(k)}
==================

F(x_1^{(k)},x_2^{(k)},...)
]

最终输出：

* median；
* RMSE；
* P95；
* probability of satisfying task requirement。

例如：

[
P(E_{endpoint}\leq E_{req})
]

---

# 5. Precision Leverage 与 Bottleneck Switching

单纯比较“哪一项误差最大”不足以成为研究贡献。

需要研究：

> **改善哪一个 subsystem 会给最终 endpoint 带来最大的实际收益？**

对当前 configuration (\Theta)：

[
E_{current}=Q_{95}(E_{endpoint}|\Theta)
]

假设只改善 subsystem (i)：

[
\Theta\rightarrow\Theta_i'
]

定义：

[
G_i
===

## E_{current}

E(\Theta_i')
]

其中 (G_i) 表示：

> **该 subsystem 当前可提供的 endpoint precision gain / precision leverage。**

若提供成本：

[
G_i^{cost}
==========

\frac{G_i}{\Delta C_i}
]

但成本不是当前论文必须条件。

---

## 5.1 Bottleneck switching

不断对 subsystem 做 counterfactual improvement 后重新计算 (G_i)。

可能出现：

```text
Initial:
Model mismatch > Robot > Camera

Homography → PnP:
Robot > Calibration > Camera

Robot improved:
Stereo / sensing > Robot
```

因此：

> **最优升级方向不是固定的，而是随任务和当前系统状态改变。**

**状态：核心待验证假设。**

**反思：** 必须证明这种 switching 不只是人为解释已有结果，而能够对 held-out condition 做预测。

---

# 6. Precision Regime Map

最终希望得到的不是算法排名，而是任务空间中的区域划分。

概念形式：

```text
Required endpoint precision
↑
│                    Stereo / better geometry
│
│           PnP                Robot precision
│
│
│ Homography
└────────────────────────────────────→ Off-plane distance / task difficulty
```

不同区域回答：

* Homography 什么时候已经 sufficient？
* PnP 什么时候变成必要条件？
* 第二个 view 什么时候值得加入？
* robot performance 什么时候成为真正瓶颈？
* resolution / compute 什么时候已经过度优化？

这张图暂称：

## Precision Regime Map

**状态：研究目标，尚未数学化。**

**反思：** 如果无法建立明确的 regime boundary，论文容易重新变成定性工程经验总结。

---

# 7. E0–E7 在新框架中的角色

现有实验不再按照“实验数量”解释，而作为 system error model 的 empirical anchors。

| Experiment | 新框架中的角色                                    | 提供的信息                                                                         |
| ---------- | ------------------------------------------ | ----------------------------------------------------------------------------- |
| E0-A       | Camera baseline variability                | camera short-term random localization variation                               |
| E0-B       | Robot/control + physical endpoint baseline | 当前 PI tuning 下的执行与物理反馈经验误差                                                    |
| E1         | Planar sufficiency / control condition     | planar model capability                                                       |
| E2         | Model-mismatch curve                       | algorithm × off-plane height → bias/error                                     |
| E3         | Calibration conditioning                   | spatial coverage / point count → calibration performance                      |
| E4         | Downstream propagation validation          | visual target → command → robot execution → physical endpoint → human reading |
| E5         | Effective resolution / compute trade-off   | resolution → detection / localization / latency                               |
| E6         | Additional information / view geometry     | single estimate vs estimate fusion vs stereo                                  |
| E7         | Calibration validity under motion          | stale calibration / relocalization；simulation only                            |

---

# 8. 各实验当前可支持的核心结论

## E0-A：Camera baseline variability

主要结果：

* XY radial P95 median：0.389 mm；
* worst P95：1.023 mm。

可支持：

> 当前相机短期随机定位波动处于毫米以下至约 1 mm 量级，不足以单独解释 E2 中数十毫米级离面误差。

**状态：已确认。**

**反思：** 仅代表短期静态 repeatability，不代表不同距离、光照、sensor 或长期 drift。

---

## E0-B：Robot / endpoint baseline

20 次到达同一目标，并与内部反馈进行交叉检查。

结果：

* Pearson (r=0.964)；
* RMSE = 1.325 mm。

新解释：

> 当前数据可以作为调好 PI 后，这套 RoArm + controller + 当前操作条件下的 robot/control empirical error anchor。

不能解释为：

> RoArm 普遍具有固定 X mm uncertainty。

**状态：已确认。**

**反思：** robot error 可能依赖姿态、payload、方向和 controller，因此 framework 应允许用户输入自己的 empirical capability。

---

## E1：Planar sufficiency

Z=0：

* Affine：4.854 mm；
* Homography：0.660 mm；
* PnP：0.661 mm。

核心意义：

> 当任务严格处于 planar regime 时，Homography 已经提供与 PnP 描述性相近的定位能力，额外 3-D representation 未产生明显收益。

同时作为 E2 的 control：

> Homography 并非从一开始就是一个“坏 estimator”。

**状态：已确认。**

**反思：** 该结论仅适用于当前 planar setup，不能推断所有平面任务都无需 PnP。

---

## E2：Off-plane model mismatch

Z=50 mm：

ihawk1：

* Affine 69.63 mm；
* Homography 81.97 mm；
* PnP 10.63 mm。

ihawk2 PnP：

* 4.54 mm。

核心意义：

[
Z
\rightarrow
b_{algorithm}(Z)
]

说明：

> planar mapping 在离开 calibration manifold 后出现显著 systematic model mismatch，而 PnP 提供所需 metric 3-D geometry。

同时拥有：

* 5 次 physical rebuild；
* 11 个 height levels；
* 双相机。

**状态：当前最重要 empirical model 之一。**

**反思：** 现有 0–50 mm 范围与两个固定 camera geometry 不构成普适 deployment envelope。

---

## E3：Calibration conditioning

结果示例：

4 spread points：

* Homography median ≈ 0.955 mm；
* PnP ≈ 0.731 mm。

4 clustered：

* Homography median ≈ 243.696 mm。

核心意义：

> **Calibration quantity ≠ useful calibration information.**

真正重要的是：

* spatial coverage；
* conditioning；
* geometry。

它可提供：

[
E_{cal}
=======

f(N,coverage,conditioning)
]

**状态：已确认 empirical evidence。**

**反思：** E3 是同一观测集上的 offline resampling，不等于 100 次独立 physical calibration。

---

## E4：Endpoint propagation

链：

[
Vision\ Target
\rightarrow
Robot\ Command
\rightarrow
Execution
\rightarrow
Physical\ Endpoint
\rightarrow
Human\ Measurement
]

结果：

* Oracle RMSE：1.581 mm；
* Affine：3.306 mm；
* Homography：2.236 mm；
* PnP：2.065 mm。

当前冻结解释：

> E4 已经能够支撑当前系统的 downstream error propagation，并表明 perception improvement 不会一比一传递成 endpoint improvement。

Oracle 仍约 1.58 mm：

> 表明即使 perception 被理想化，下游 robot/control + measurement chain 仍存在有限误差 floor。

E4 不是单纯“一个 completed block / 九个 targets”的弱 application experiment，而是：

> 当前低成本系统的 physical endpoint validation anchor。

**状态：已确认重新定位。**

**反思：** E4 识别的是当前 PI tuning、当前 robot condition 和人工读数链的经验表现，不可直接泛化为其他机器人。

---

## E5：Effective resolution / resource sensitivity

native 640×400：

* worst pipeline P95 = 8.149 ms；
* 满足 30 Hz 时间预算。

480×300 完整 5-marker frame：

* ihawk1：78.4%；
* ihawk2：98.8%。

核心意义：

> 当前系统中 compute 并不是 native-resolution bottleneck；继续降 effective resolution 会损害 detection completeness，因此 reduction 不一定产生有价值的系统收益。

它可建模：

[
resolution
\rightarrow
{
accuracy,
detection,
latency
}
]

**状态：已确认 supporting evidence。**

**反思：** 这是 offline downsampling，不等同于真实低分辨率 sensor hardware。

---

## E6：Second estimate vs second view

25 mm 3-D RMSE：

* ihawk1：10.348 mm；
* ihawk2：6.144 mm；
* EqualXYZ：7.431 mm；
* LOOWeightedXYZ：6.351 mm；
* Stereo：3.342 mm。

核心结论：

> **Adding another estimate is not equivalent to adding another geometric view.**

Equal / LOO fusion：

> 重组已有带偏 estimate。

Stereo：

> 利用 calibrated parallax 提供新的 cross-view geometric constraint。

因此：

> sensor count 本身没有价值；真正重要的是新增 observation 是否解除当前 geometry bottleneck。

**状态：已确认核心 conceptual result。**

**反思：** 当前仅有一个固定双相机 geometry，因此不能从本实验推断 causal “最佳角度”或“最佳 baseline”。

---

## E7：Calibration validity

纯 simulation。

核心意义：

> 正确但过期的 extrinsic information 不再是有效 information。

例如：

FrozenExtrinsicPnP 随 motion 明显退化，而 relocalized PnP 保持稳定。

当前仍：

> repository-only / future work。

**状态：明确排除本次 physical validation 主线。**

**反思：** simulation 只能支持机制探索，不能与 E1–E6 的真实证据层级混用。

---

# 9. 现有实验背后的统一模式

讨论中形成了一个重要的跨实验模式：

> **More is not necessarily more useful.**

具体体现：

* E1：更多 3-D machinery ≠ planar task 更高精度；
* E3：更多 calibration points ≠ 更多有效 geometric information；
* E4：更低 upstream vision error ≠ 同比例更低 endpoint error；
* E5：减少像素 / computation ≠ 解决真正 bottleneck；
* E6：更多 estimates ≠ 更多 geometric constraints；
* E7：更多已有信息，如果已经 stale，也 ≠ useful information。

进一步抽象：

> **真正值得增加的是当前任务所缺失的约束，而不是单纯增加数据量、模型复杂度、像素、sensor 数量或计算量。**

**状态：重要 conceptual insight，但暂不作为普适理论定律。**

**反思：** 当前实验证据仅来自有限的低成本 eye-to-hand setup，不能推广成通用机器人理论。

---

# 10. 与相关研究的关系

## 10.1 Attention Is All You Need

讨论中主要作为科研结构参照，而不是技术相关工作。

启示：

* 价值不一定来自单一组件首次出现；
* 更重要的是提出一个明确的问题；
* 删除/增加某种信息后，系统是否仍然成立；
* 性能、效率和消融共同服务于一个统一命题。

对本研究的启发：

> 不应该堆 E1–E7，而应围绕“什么时候什么精度/信息才真正必要”设计统一解释与预测。

---

## 10.2 Robot Co-design

讨论涉及的工作：

> Carlone & Pinciroli：robot co-design / automatic selection of sensing, actuation and computing modules under task specifications。

贡献：

> 从任务要求出发选择系统模块组合。

与本研究区别：

Robot co-design 更接近：

[
Task
\rightarrow
System\ Design
]

当前研究更关注：

[
Existing/System\ Capability
+
Task\ Condition
\rightarrow
Precision\ Bottleneck
\rightarrow
Minimum\ Necessary\ Improvement
]

但“已有系统”本身不足以形成 novelty，因此真正区别必须落到：

* precision allocation；
* hybrid error propagation；
* bottleneck switching；
* diminishing-return boundary。

---

## 10.3 TaCOS

Task-Specific Camera Optimization。

核心思想：

> 不把 camera 单独追求更高规格，而根据 downstream task 优化 camera design / parameters。

与本研究关系：

* 强烈支持“task-specific capability，而不是性能越高越好”；
* 说明 simulation + physical validation 的设计空间扩展方法具有合理性。

区别：

> TaCOS 主要优化 camera；本研究希望研究 precision 如何在 perception、calibration、geometry、compute 和 robot execution 之间重新分配。

---

## 10.4 Task-space Error Budget / Learning From a Steady Hand

核心思想：

> 建立 observation / calibration 等误差，并传播到最终 task-space performance，再通过真实系统验证 error budget。

与本研究关系：

它回答：

> “这套系统最终误差是多少、从哪里来？”

当前研究希望进一步回答：

> “当任务或能力变化时，哪一环最值得继续改善；什么时候瓶颈会发生切换？”

因此：

* error budget 是底层工具；
* bottleneck switching / precision allocation 才可能成为上层贡献。

---

## 10.5 Barfoot & Furgale

讨论中作为：

> 3-D pose uncertainty representation and propagation 的成熟理论基础。

作用：

> 不需要从零发明 SE(3) pose uncertainty mathematics。

---

## 10.6 Nguyen & Pham：Covariance of X in AX = XB

与 hand-eye / robot-sensor calibration covariance propagation 直接相关。

作用：

> 支撑 Camera → Extrinsic → Robot frame 链中的 calibration uncertainty propagation。

---

## 10.7 GUM / JCGM

作用：

* Type A：来自重复统计观测；
* Type B：来自分辨率、datasheet、已有知识、校准证据等；
* Monte Carlo：适用于非线性、复杂 probability propagation。

对本研究尤其重要：

> 用户不一定需要完整计量设备；datasheet / bounded error / empirical samples 都可以成为不同 evidence level 的输入，但不能假装具有同等可信度。

---

## 10.8 Adámek 等：Planar Fiducial Pose Variance

讨论中作为：

> planar fiducial pose error 随距离、相对观察几何变化的 analytical / empirical model。

意义：

> angle / distance 等并非全部需要自己逐点实验，可以使用理论或文献模型进入 framework。

限制：

> 不应该跨系统直接复用“某角度误差 = X mm”的具体经验数值。

---

## 10.9 Calibration conditioning / Next-Best-View

相关工作支持：

> calibration quality 更依赖 control-point configuration / information gain，而非单纯样本数量。

用于解释 E3：

> spread calibration points 显著优于 clustered layout 有明确 geometric conditioning 基础。

---

## 10.10 Stereo geometry / baseline

成熟关系：

[
Z=\frac{fB}{d}
]

近似：

[
\sigma_Z
\propto
\frac{Z^2}{fB}\sigma_d
]

因此：

* baseline；
* focal length；
* disparity precision；
* target distance

已有明确理论关系。

当前结论：

> 不需要为了论文完整性再做大规模 physical baseline sweep。

E6 负责验证：

> 在当前实际双相机 geometry 中，真实第二视图确实能带来 measurable improvement。

---

## 10.11 ISO 9283

作用：

> robot performance 可用 pose accuracy、repeatability 等 capability-level indicators 表述。

因此：

> framework 不需要绑定 robot model，也不需要做 cross-hardware robot benchmark。

---

# 11. 数据来源与证据层级

未来 framework 中所有模型建议标注来源。

| Code | Source                    | 例子                                  |
| ---- | ------------------------- | ----------------------------------- |
| E    | Own Empirical             | E0–E6                               |
| P    | Physics / analytical      | stereo triangulation                |
| L    | Literature                | viewpoint / fiducial variance model |
| D    | Datasheet / specification | camera depth accuracy               |
| S    | Simulation                | E7 / compute-budget simulation      |

必要时再加入：

* confidence；
* applicability domain；
* uncertainty of the model itself。

**状态：已确认建议。**

**反思：** 混合 evidence source 后，如果不给 provenance / confidence，framework 很容易输出虚假的高精度数字。

---

# 12. 当前不再认为必须补的数据

经过讨论，以下内容不再作为论文的硬性 physical data requirement：

* 多个不同 camera 型号真实测试；
* 多个不同 robot 型号真实测试；
* 多个 compute hardware 平台；
* 大规模 camera-angle sweep；
* 大规模 stereo-baseline sweep；
* 产品价格数据库。

原因：

> 研究目标是 capability-driven，而不是 product benchmark。

这些变量原则上可以通过：

* physics；
* literature；
* datasheet；
* user measurement；
* normalized simulation

进入模型。

---

# 13. 当前仍然真正缺失的核心内容

## 13.1 Unified System Error Model

尚未正式建立：

[
E_{endpoint}
============

F(
Camera,
Calibration,
Model,
Geometry,
Compute,
Robot,
Measurement,
Task
)
]

这是当前最大的数学缺口。

**状态：开放问题 / 必须解决。**

---

## 13.2 Bias + random uncertainty 的统一表达

需要把：

[
b_i(x)
]

和：

[
\epsilon_i
]

放在同一传播框架中。

特别是：

* E2 model mismatch；
* E0 random variability；
* E4 downstream execution；
* literature / datasheet prior。

**状态：开放问题。**

---

## 13.3 Precision leverage 的正式定义

当前候选：

[
G_i
===

## Q_{95}(E_{current})

Q_{95}(E_{after\ improving\ i})
]

但仍需定义：

* “improved”改善到什么 reference capability；
* 连续变量如何处理；
* algorithm / camera count 等离散变量如何比较。

**状态：待设计。**

---

## 13.4 Diminishing-return boundary

目前仍是概念。

可能方法：

* marginal derivative；
* counterfactual gain threshold；
* Pareto knee；
* task-satisfaction plateau。

**状态：开放问题。**

---

## 13.5 Precision Regime Map

需要真正从数学模型得到：

[
(Task,\ Required\ Precision)
\rightarrow
Dominant\ Subsystem
]

并形成可以预测 transition boundary 的 map。

**状态：最重要待实现输出之一。**

---

## 13.6 Non-circular validation

不能：

> 用 E2 拟合 E2，再用同一数据证明 E2 模型正确。

优先方案：

### Leave-one-physical-rebuild-out

例如：

* rebuild 1–4 建模；
* rebuild 5 预测；
* 循环进行。

此外可考虑：

* held-out height；
* held-out resolution；
* held-out calibration configuration；
* E4 作为 downstream endpoint validation。

**状态：已确认必须执行。**

---

# 14. E4 的最终冻结定位

E4 当前不再被降级为单纯 exploratory application experiment。

它已经包含：

[
Predicted\ Target
\rightarrow
Command
\rightarrow
Robot
\rightarrow
Physical\ Endpoint
\rightarrow
Human\ Reading
]

因此：

> **E4 可以作为当前系统中 error propagation 到真实 endpoint 的核心实证锚点。**

但它识别的是：

[
p(e_R|PI^*,workspace,current\ conditions)
]

不是普适 robot uncertainty。

人工约 1 mm 读数分辨率可作为 measurement component；如果无法独立分离 observer repeatability，可先将其作为 combined downstream measurement term。

**状态：已确认共识。**

---

# 15. Compute 的处理原则

当前不打算建立：

> Raspberry Pi / Jetson / RTX / CPU 型号 → latency

数据库。

更合理：

## Capability mode

用户测：

[
T_{PnP},T_{Stereo},T_{Detection}
]

直接输入。

## Research simulation mode

可以通过：

* CPU core limitation；
* CPU quota；
* thread count；
* resolution；
* workload；

建立 normalized compute tiers：

[
C={0.25,0.5,1.0}
]

研究：

[
Latency=f(C,resolution,algorithm)
]

必须称：

> compute-budget emulation

不能冒充：

> 某具体真实 hardware benchmark。

**状态：方法共识。**

---

# 16. Camera 与 Robot 的 hardware-agnostic 原则

## Camera

不以：

> 640×400

单一分辨率代表 camera precision。

至少应考虑：

* projected target size；
* pixel-localization quality；
* FOV；
* depth accuracy；
* FPS / latency。

Datasheet 可作为 Type-B / prior input，但 manufacturer bound 不应直接等价为 Gaussian standard deviation。

---

## Robot

不绑定型号。

使用：

* repeatability；
* empirical execution error；
* tracking variability。

当前 RoArm 数据只是：

> 一轮低成本 system validation case。

---

# 17. 暂时明确排除的研究范围

为了避免 scope 爆炸，当前不纳入核心算法：

* PID / PI 自动调参；
* controller synthesis；
* dynamic target；
* moving-camera physical validation；
* full grasp mechanics；
* grasp success rate；
* object slipping / force control；
* payload optimization；
* universal camera-placement optimization；
* camera / robot product recommendation；
* monetary cost database。

特别是：

> framework 可以判断 robot/control 已成为 bottleneck，但不负责告诉用户具体 Kp、Ki 设多少。

---

# 18. 当前论文最可能的两个 Research Questions

## RQ1

> **How do task conditions change the dominant contributors to endpoint positioning error in a low-cost vision-guided robotic system?**

中文：

> 任务条件变化时，哪些 subsystem 主导最终末端定位误差？

---

## RQ2

> **Can a hybrid error-propagation model predict minimum sufficient subsystem capabilities and transitions in optimization priority required to satisfy a target endpoint precision?**

中文：

> 能否利用 hybrid error-propagation model，预测满足目标末端精度所需的最低 subsystem capability，以及优化优先级发生切换的条件？

---

# 19. 当前最可能的 Contribution

## C1 — Hybrid Error-Propagation Model

统一表示：

* systematic model bias；
* stochastic variability；
* calibration / geometry；
* robot execution；
* measurement。

并传播至 endpoint distribution。

---

## C2 — Precision Leverage / Bottleneck Switching

不是只找最大 error source，而是通过 counterfactual intervention 判断：

> 改善哪个 subsystem 对最终 endpoint 的边际收益最大，以及什么时候该 subsystem 已经进入 diminishing-return regime。

---

## C3 — Physical Validation Using Existing E0–E6

利用真实低成本 eye-to-hand system 验证多个 regime / bottleneck transition：

* planar → Homography sufficient；
* off-plane → geometric model mismatch dominates；
* PnP 后 → downstream error floor 显现；
* calibration coverage → information quality matters；
* effective resolution → compute / detection trade-off；
* second estimate → 不等价于 second geometric view。

---

# 20. 当前 novelty 边界

不能宣称：

* 首个 robot co-design；
* 首个 task-specific precision framework；
* 首个 task-space error budget；
* 首个 uncertainty propagation；
* 首个 stereo / PnP comparison。

可能的特殊性交集在于：

[
\boxed{
Task-conditioned\ precision\ requirement
+
Hybrid\ error\ propagation
+
Bottleneck\ switching
+
Counterfactual\ upgrade\ gain
}
]

更直观：

> **不是告诉系统“怎样做到更准”，而是判断“什么时候继续变准才有用，以及下一单位精度资源应该投入在哪里”。**

**状态：待正式 novelty search 验证。**

**反思：** “已有系统升级”本身不是 novelty；必须依靠可预测的 precision regime / bottleneck transition 与正式方法区分已有 co-design 和 error-budget 工作。

---

# 21. 当前主要风险

## Risk 1：最后退化成 Error-Budget Dashboard

如果方法只是：

> 把各误差列出来 → 最大那个就是瓶颈，

研究价值不足。

必须体现：

* propagation；
* counterfactual gain；
* transition；
* minimum sufficiency；
* held-out prediction。

---

## Risk 2：Precision Regime Map 推不出来

如果无法建立：

[
Task
\rightarrow
Bottleneck\ Transition
]

论文会失去最明确的 scientific mechanism。

---

## Risk 3：文学模型跨域滥用

其他论文可以补：

* physical relationship；
* model form；
* qualitative dependency。

但不能无条件搬：

* camera-specific coefficient；
* 某固定最佳角度；
* 某系统具体 mm error。

---

## Risk 4：过度声称 uncertainty

需要持续区分：

* error；
* variability；
* bias；
* uncertainty；
* model mismatch。

不写：

> complete uncertainty budget

除非满足严格 measurement requirements。

---

## Risk 5：自我拟合、自我验证

必须用：

* leave-one-rebuild-out；
* held-out condition；
* downstream E4；

避免循环验证。

---

# 22. 当前判断：是否值得继续

## 不值得继续的版本

如果最终研究问题只是：

> 现有系统达不到要求，找出哪个误差最大并建议升级哪个模块。

则：

> **不建议投入大量精力。**

原因：

* 工程诊断性质过强；
* 方法难度不足；
* 与 error budget / co-design 研究区分有限。

---

## 值得继续的版本

如果能够实现：

[
Task
\rightarrow
Hybrid\ Error\ Model
\rightarrow
Endpoint\ Distribution
\rightarrow
Precision\ Leverage
\rightarrow
Bottleneck\ Switching
\rightarrow
Precision\ Regime\ Map
]

并通过 held-out E0–E6 数据验证 transition prediction，则：

> **值得继续。**

当前真正研究的问题可以压缩成一句：

> **When is more precision actually useful, and where should it come from?**

中文：

> **什么时候更高精度真正有价值，这部分精度应该来自系统的哪一环？**

---

# 23. 下一阶段优先级

当前不优先继续增加物理实验。

优先顺序：

1. **定义统一 error-chain variables。**
2. **明确每个变量的来源：E / P / L / D / S。**
3. **建立 (e=b(x)+\epsilon) 的 hybrid model。**
4. **确定 endpoint propagation 方法。**
5. **正式定义 Precision Leverage (G_i)。**
6. **定义 diminishing-return / minimum-sufficient boundary。**
7. **构建第一版 Precision Regime Map。**
8. **使用 leave-one-rebuild-out / held-out condition 测试预测能力。**
9. **用 E4 验证最终 endpoint distribution。**
10. 只有在上述模型暴露明确缺口后，再决定是否补新的 physical experiment。

---

# 24. 当前冻结原则

1. **E1–E6 是真实系统 validation evidence，不再把“实验数量”本身当贡献。**
2. **E7 保持 simulation / future-work 证据层级，不与 physical experiments 混用。**
3. **不绑定特定 camera / robot 型号；框架面向 capability parameters。**
4. **不以 resolution 单独代表 camera quality。**
5. **不以一个固定 mm 数值代表所有 robot uncertainty。**
6. **不把 systematic bias 与 random uncertainty 混为一谈。**
7. **文献和 physics 用于补理论关系，不用于伪造当前平台的 empirical coefficient。**
8. **当前论文不扩展到 PID tuning、dynamic grasp、产品价格数据库。**
9. **如果无法预测 bottleneck transition，则应重新评估该研究方向。**
10. **研究价值来自“minimum sufficient precision + bottleneck switching”，不是“把系统做到最精确”。**

---

# 文档状态

* **版本：** v1.0 冻结版
* **日期：** 2026-08-17
* **用途：** 长期研究参考 + 后续 AI 上下文同步 + 阶段性研究方向冻结
* **当前阶段：** 已完成研究问题重构与现有证据重新定位；下一阶段进入统一误差模型、Precision Leverage 与 Precision Regime Map 的形式化设计
