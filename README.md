# Axiom 文档入口

> 状态：v0.7 可发布；R0/R1 契约闭合，R2 Math F3 时间与离散参考栈已接入
> 当前里程碑：通用框架 `R0` + 有序离散点 `R1` + Five-Axis Math `F3`
> 更新日期：2026-08-11

Axiom 的目标不是做一个只理解 CNC 术语的“语义化评分器”，而是建立一套可逐级定义、可扩展到真实设备、可沉淀训练数据，并最终支持受约束参数优化的工业评估、实验与证据框架。

首个切入点是**有序离散点序列**。五轴轨迹是建立在通用框架上的第一个高价值数学领域包，而不是平台内核本身。

```mermaid
flowchart LR
    R0["R0 通用评估框架"] --> R1["R1 有序离散点"]
    R1 --> R2["R2 五轴数学领域包"]
    R2 --> R3["R3 设备只读接入"]
    R3 --> R4["R4 物理模型与对齐"]
    R4 --> R5["R5 数据集与学习模型"]
    R5 --> R6["R6 受约束参数推荐"]
    R6 --> R7["R7 受控闭环"]
    R7 -. "观测结果回流" .-> R4
```

## 规范主体与决策记录

| 文档 | 唯一职责 | 当前状态 |
|---|---|---|
| [项目规划蓝图](CNC%20算法效果评估与智能优化平台——项目规划蓝图.md) | 产品边界、总体架构、Roadmap、阶段门与非目标 | Draft |
| [通用评估框架规范](Axiom%20通用评估框架规范.md) | 跨领域核心对象、角色、能力协商、三状态轴、证据与执行语义 | Draft v0.5 |
| [有序离散点领域包规范](有序离散点领域包规范.md) | 第一个最小领域包及其输入、指标和验收闭环 | Draft v0.4 |
| [FiveAxisTrajectoryPack — CNC 五轴数学参考系统全景规范](CNC%20数学参考系统全景规范.md) | M0–M5 数学模型、进度/对应/重建契约、模型碰撞边界、证明义务和测试族 | Draft v0.7 / F3 implemented |
| [ADR 索引](架构决策记录/README.md) | 长期架构决策、替代方案与后果的审计历史 | Active |
| 本文档 | 总入口、阅读路径与文档治理 | Active |

除 ADR 行外的五项（含本文档）构成规范性主体；ADR 是决策记录，不复制规范正文。[implementation-notes](implementation-notes.md) 是任务过程记录，不属于正式规范，也不能作为实现依据。

## 推荐阅读路径

- 讨论产品方向：本文档 → 项目规划蓝图。
- 设计平台内核：本文档 → 通用评估框架规范 → 有序离散点领域包规范。
- 研究五轴数学：通用评估框架规范 → FiveAxisTrajectoryPack 全景规范。
- 规划设备、机器学习或优化：项目规划蓝图中的对应阶段 → 通用评估框架规范的角色与安全边界。
- 了解为何选择当前契约：对应规范 → ADR 索引 → 具体 ADR。
- 查看版本变化与升级边界：[CHANGELOG](CHANGELOG.md)。

## 文档所有权规则

1. 一个概念只能有一个规范来源；其他文档只摘要并链接。
2. 蓝图回答“为什么、先后顺序和阶段门”，不重复领域公式。
3. 通用规范只定义跨领域不变量，不吸收五轴、设备或模型训练细节。
4. 领域包定义自己的数据语义、验证器、指标和证据生产方式，但不得改写通用核心。
5. 实现细节只有在接口被实际采用后才进入规范；设想保留在 Roadmap，不提前写成伪稳定接口。
6. 每个重要结论必须区分：输入事实、计算结果、声明、证据和最终决策。
7. ADR 解释“为什么这样决定”；当前规范定义“实现必须遵守什么”。两者不一致时必须先修正文档，不能由实现自行选择。

## 后续文档的创建触发条件

以下文档现在**不创建空壳**，达到触发条件时再从蓝图中拆出：

| 未来文档 | 创建触发条件 |
|---|---|
| `设备接入与物理闭环规范.md` | 选定首个驱动器、控制器或仿真设备，开始定义只读遥测接口 |
| `数据集与学习模型规范.md` | `Run / Observation / Evidence` 模式稳定，并开始积累可训练的成对样本 |
| `受约束优化与安全闭环规范.md` | 参数推荐进入工程验证，需要定义搜索域、硬约束、shadow 与人工批准协议 |
| `架构决策记录/ADR-*` | 每次新增会长期约束实现、且存在实质替代方案的技术决策 |

## 当前最近目标

R1 的离散点最小闭环已经成立。v0.7 在不向 Core 写入五轴分支、也不改写 F2 Artifact 的前提下，把第二个领域包推进到可执行的 F3 时间与离散参考栈：

> F1 的 M0→M2 几何证据链和 F2 的 M3 运动学/`Q_free` 证据继续保留；F3 新增独立 `MotionConstraintProfile`、M4 连续时间律、逐轴 V/A/J 重验、结点停启与 dwell、M5 固定周期采样，以及绑定重建策略的区间证书和分量化误差账本。

F3 可独立发布 `ContinuouslyFeasible` 与 `IntervalCertified`。解析二阶 `ProvenOptimal` 只覆盖冻结的线性 stop-to-stop 子集；七次 smoothstep 只声明 Jerk 可行。F1/F2/F3 的 Claim 不能互相替代，F3 也不生成 `ModelCollisionFree`、`DeviceSafe` 或 `ProcessSafe`。下一个数学阶段是 F4 Reference Solver/SUT 集成与完整验收。

## v0.7 快速开始

v0.7 保留 Point Lab、F1 Geometry Reference Workbench 与 F2 Kinematics Reference Workbench，并新增 F3 Time & Sampling Lab。七个 F3 场景覆盖三类 canonical 五轴拓扑、二阶已证最优、dwell/mandatory-stop、移动 ZOH 不支持，以及“采样端点速度为零、区间内部仍超限”的多项式反例；页面展示 σ(t)、逐轴 V/A/J、结点时间线、固定周期样本、重建策略、误差账本、标准 Claim 和 sealed M4/M5 身份，并永久标注 `MATH ONLY / NOT DEVICE SAFE`。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m axiom evaluate examples\basic-evaluation.json
# 准备符合 run-spec@1 的 JSON 后：
.\.venv\Scripts\python.exe -m axiom run .\path\to\run-spec.json
.\.venv\Scripts\python.exe -m axiom compare fixtures\cnc_scenarios\comparisons\cnc-contour-ab-pass-vs-fail.json
.\.venv\Scripts\python.exe -m axiom experiment fixtures\cnc_scenarios\experiments\cnc-contour-true-ab.json
.\.venv\Scripts\python.exe -m axiom serve --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m pytest
```

启动后访问 `http://127.0.0.1:8000`，可在 Point Lab、Five-Axis F1、F2 与 F3 间切换。发布包已经内置网页资源；从源码修改 UI 时，先在 `web` 目录执行 `pnpm install` 和 `pnpm build`。单次输入契约见 [`examples/basic-evaluation.json`](examples/basic-evaluation.json)，真实双臂实验见 [`cnc-contour-true-ab.json`](fixtures/cnc_scenarios/experiments/cnc-contour-true-ab.json)。仓库验收使用的 Five-Axis F2 机床/碰撞参考见 [`fixtures/five_axis_f2`](fixtures/five_axis_f2)，F3 CL 输入、M3/M4/M5 内容身份和 Claim 金值见 [`fixtures/five_axis_f3`](fixtures/five_axis_f3)；这些文件是源码仓库的冻结验收资料，不承诺为 wheel 内部文件路径。安装发布包后，可由 F1/F2/F3 示例 API 获取包含 `manifest / scenario / source / artifacts / runSpec` 的完整 envelope，再交给公共 `POST /api/v1/runs/evaluate` 执行。

Python 中可直接执行内建 F0 示例：

```python
from axiom import evaluate_run, f0_example_run_spec

bundle = evaluate_run(f0_example_run_spec())
assert bundle.report.case_outcome.value == "Passed"
```

也可以执行三个 F1 场景，并直接读取标准声明而不是把 Core 的运行完成状态误当成几何结论：

```python
from axiom import evaluate_run, f1_example_run_spec

bundle = evaluate_run(f1_example_run_spec("fixture-collision"))
claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}
assert claims["five-axis.geometry-valid-claim@1"] == "Supported"
assert claims["five-axis.task-geometry-collision-free-claim@1"] == "Refuted"
```

F2 场景通过同一 Core 运行路径执行；配置空间反例会保留成功的运动学 Claim，同时用区间内部见证反驳碰撞自由 Claim：

```python
from axiom import evaluate_run
from axiom.five_axis.f2_scenarios import validate_f2_example_run_spec

bundle = evaluate_run(validate_f2_example_run_spec("configuration-interior-collision"))
claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}
assert claims["five-axis.kinematically-feasible-claim@1"] == "Supported"
assert claims["five-axis.configuration-collision-free-claim@1"] == "Refuted"
```

F3 也沿用同一 Core 路径。下面的多项式反例在采样端点看不到违规，但区间重建会反驳 `IntervalCertified`：

```python
from axiom import evaluate_run, validate_f3_example_run_spec

bundle = evaluate_run(validate_f3_example_run_spec("polynomial-interior-violation"))
claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}
assert claims["five-axis.continuously-feasible-claim@1"] == "Supported"
assert claims["five-axis.interval-certified-claim@1"] == "Refuted"
```

CLI 退出码：`evaluate` 与 `run` 的 `0` 表示 `Passed`，`1` 表示 `Failed / Inconclusive / Unsupported`，`2` 表示读取失败或 `Invalid`；`compare` 的 `0` 表示两个导入式 Run 兼容且比较成功，`1` 表示语义不兼容，`2` 表示请求无效；`experiment` 只有在两个 Arm 执行、严格比较和实验硬门槛都通过时返回 `0`，结构化业务失败返回 `1`，请求无效返回 `2`。

`ComparisonSpec` 把两个 Subject 与各自的完整 `EvaluationRequest` 冻结在同一文件中：

```json
{
  "policyId": "ordered-point.run-comparison.strict@1",
  "left": {
    "subjectId": "algorithm-a",
    "request": {
      "artifact": {
        "artifactType": "ordered-point-sequence",
        "schemaVersion": 1,
        "points": [[0, 0], [3, 4]],
        "semantics": {"unit": "mm", "coordinateFrame": "G54-workpiece"}
      },
      "case": {"caseId": "path-ab@1", "requiredMetrics": ["path.length.open"]}
    }
  },
  "right": {
    "subjectId": "algorithm-b",
    "request": {
      "artifact": {
        "artifactType": "ordered-point-sequence",
        "schemaVersion": 1,
        "points": [[0, 0], [0, 6]],
        "semantics": {"unit": "mm", "coordinateFrame": "G54-workpiece"}
      },
      "case": {"caseId": "path-ab@1", "requiredMetrics": ["path.length.open"]}
    }
  }
}
```

首版严格策略要求双方使用相同的领域包、Artifact 类型和 schema、Case、Profile、ReferenceBinding、执行结果策略、MetricDefinition、结果单位与坐标系。`evaluatorVersion` 和数值环境差异会记录为 finding，但不会自动禁止比较。不兼容时不会生成指标差值、综合分数差值或优胜方。

v0.7 沿用单个评估或 Run 请求最多 8 MiB、单个比较或实验文件最多 16 MiB、单个序列最多 100,000 点、非逐点参考比较最多 5,000,000 个距离单元的预算；当前 Fréchet 实现另有更严格的路径存储预算。F1 名义扫掠差集、F2 连续配置碰撞细分和 F3 区间重建都有确定性证明边界；超过可证明范围会返回结构化 `Unsupported*` / `Inconclusive`，不会用有限采样伪造正向证书。

按 G1、G2/G3、闭合轮廓、螺旋下刀、采样时间戳和名义—观测偏差构造的 CNC 工程合成数据，见 [`fixtures/cnc_scenarios`](fixtures/cnc_scenarios)。目录内的 `manifest.json` 给出了每个请求的预期状态、指标与 CLI 退出码，可直接批量验收。

v0.7 的执行边界仍是本地、确定性、静态注册。它不会执行任意命令或 Python 模块，也不启动厂商算法、容器或设备。Point Lab 对三维及更高维数据只显示明确标注的 XY 投影，数值评估仍消费全部坐标；Five-Axis F1 覆盖任务几何，F2 覆盖冻结 M3 数学机床及显式 `Q_free` 碰撞模型，F3 覆盖 M4/M5 数学时间与重建语义。数据库、认证、远程队列、动态 Solver/SUT Adapter、持久化历史、设备接入、机器学习训练和参数回写仍属于后续阶段。
