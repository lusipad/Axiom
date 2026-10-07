# Axiom 工业算法评估与智能优化平台——项目规划蓝图

> 文档类型：产品总纲与 Roadmap  
> 状态：Draft / 方向重整与契约闭合版 v0.23.0
> 当前阶段：R7-E / R4.1 Windows 双运行现场验收、Beckhoff 控制器侧只读见证、离线证据组装与 R5-B 真实 holdout intake 已实现；v0.23.0 新增采集前 Campaign 预注册、R5-C 条件效应代理模型、R5-D synthetic SIL 实验价值规划、R5-E 显式批准的离线合成实验反馈闭环、R5-F 候选模型下游影响评估、R5-G 模型晋升就绪审查包、R5-H 候选专属真实 holdout、R5-I 本机模型生命周期、R6 v2 目标驱动代理辅助搜索，以及 exact R4 response 驱动的 Goal-to-Shadow 应用闭环 / R5-I 已闭合签名决定预检、本机 SQLite 原子晋升、默认模型读回、运行监控与显式回滚合同；当前机器仍缺 TwinCAT、TF6100 与经授权的跨设备/工况 capture，因此 R5-H 和公开晋升路径默认 Open，受控试验、设备部署与设备写入 gate 保持 Open
> 更新日期：2026-08-14
> 文档入口：[README](README.md)  
> 核心规范：[Axiom 通用评估框架规范](Axiom%20通用评估框架规范.md)

> 文件名暂时沿用原 CNC 蓝图名称，以保留现有链接；Axiom 的产品边界已经扩展为通用工业评估、实验与证据平台，CNC 五轴是重点领域而不是内核边界。

## 1. 这次重整解决什么

旧蓝图把五轴数学参考系统、算法 Benchmark、设备接入、机器学习和参数优化放在同一条产品主链里。内容本身有价值，但容易形成两个误解：

1. Axiom 是一个理解 CNC 语义后给算法打分的专用评估器；
2. 必须先完成完整五轴 M0–M5，平台才有第一个可用闭环。

本蓝图明确改为：

> 先建立通用的评估、实验与证据框架；用有序离散点完成最小闭环；再接入五轴数学领域包；随后接入设备与物理模型；最后在可信数据和硬约束之上训练学习模型、提出参数建议，并逐步形成受控闭环。

五轴数学内容不删除，也不降级。它从“平台内核”调整为第一个高价值、完备建模的领域包。

## 2. 产品定义

### 2.1 一句话定义

Axiom 是一套可逐级增加语义和模型、统一记录运行与证据，并连接算法、数学模型、仿真、设备、学习模型和受约束决策的工业实验平台。

### 2.2 Axiom 不只是 Evaluator

Evaluator 只是平台中的一个角色。完整平台至少包含：

- Artifact 与领域语义；
- 可复现的 EvaluationCase，以及按需使用的 Experiment；
- 算法、模型和设备 Runner；
- 原始 Observation；
- 独立 Evaluator；
- Claim、Evidence 和 Provenance；
- 数据集快照与学习模型；
- Optimizer 产生的候选 Recommendation；
- 独立的安全 gate 与 AcceptanceRecord。

因此产品能力不是“输入数据 → 一个分数”，而是：

```text
定义试验 → 执行/导入结果 → 记录观测 → 独立评价
        → 形成声明与证据 → 比较/诊断 → 推荐下一次试验
```

### 2.3 核心价值

- **可从少量信息开始**：只有离散点，也能做结构和内在几何评价。
- **可逐级增强**：加入单位、参考、时间、机器和测量后，开放更多评价能力。
- **数学与物理分开**：数学合法不等于设备效果好；物理观测不能反过来改写数学真值。
- **结果可追溯**：每个结论都能回到输入、参数、版本、环境和证据。
- **为学习准备，而非先上学习**：先稳定对象、指标和数据谱系，再训练残差或代理模型。
- **建议与执行分开**：模型和优化器提出候选，独立 gate 决定是否进入仿真、shadow 或设备。

## 3. 锁定的架构决策

### 3.1 框架通用，领域能力插件化

平台核心只定义跨领域对象、角色、执行语义和证据规则。离散点、五轴轨迹、设备、测量或其他未来领域通过 DomainPack 接入。

领域包可以定义：

- Artifact 和 Profile；
- 结构/语义验证规则；
- MetricDefinition 和 Evaluator；
- ReferenceModel、PhysicalModel 或 Adapter；
- 领域失败码、证据生产方式和测试族。

领域包不能改变核心对象含义，也不能把自己的术语变成所有领域的强制字段。

### 3.2 外部是渐进层级，内部是组合图

用户看到的是从原始数据到语义、参考、执行、物理和学习的逐级能力；平台内部则用有类型关系组合对象，而不是把一切塞进一条继承链。

这允许：

- 只评价一组离散点；
- 同一结果同时被多个 Evaluator 消费；
- 同一 Case 分别运行数学模型、算法、仿真和设备；
- 一个物理观测关联多个数学基线或模型版本；
- 一个 Claim 由多条 Evidence 支持或反驳。

### 3.3 对每个领域，先数学模型，再物理模型

“先数学、后物理”仍是硬原则，但作用域改为**每个领域包内部**，而不是要求整个平台首先完成所有 CNC 数学。

以五轴为例：

```text
M0–M5 数学语义与离散命令
        ↓ 通过领域 gate
P1–P5 命令、驱动、机构、过程、测量
```

M0–M5 的规范来源只有 [FiveAxisTrajectoryPack — CNC 五轴数学参考系统全景规范](CNC%20数学参考系统全景规范.md)。

### 3.4 硬约束先于质量排序

所有领域遵循：

1. 输入与执行有效性；
2. 安全、数学和物理硬门槛；
3. 合法候选间的质量、代价和鲁棒性比较；
4. 特定业务下的决策策略。

默认不提供跨领域“万能总分”，也不允许高性能或低误差抵消硬约束失败。

### 3.5 学习模型不是真值来源

机器学习优先用于：

- 预测数学模型到实机结果之间的残差；
- 预测给定参数下的条件效果和风险；
- 识别异常、漂移和适用域；
- 缩小昂贵仿真或设备试验的搜索空间。

学习模型必须报告版本、训练域、数据谱系、验证结果和不确定性。它不替代 ReferenceModel、硬约束验证器或最终批准。

### 3.6 数学可行不等于设备安全

R2 可以声明 `GeometryValid`、`ModelCollisionFree`、`KinematicallyFeasible`、`ContinuouslyFeasible` 和 `IntervalCertified`，但这些结论都限定在冻结的数学模型、几何、接触策略、机器配置和重建策略内。

R2 不得输出 `DeviceSafe`、`ProcessSafe` 或不加限定的“可执行”。真实装配误差、控制器行为、伺服跟随、热/摩擦/柔性、刀具磨损、切削过程和在线停止能力分别由 R3/R4/R7 的设备、物理和安全 gate 处理。该边界的正式决策见 [ADR-0004](架构决策记录/ADR-0004-五轴碰撞与安全声明边界.md)。

## 4. 总体架构

```mermaid
flowchart TB
    subgraph Definition["定义层"]
        Artifact
        Profile
        Case["EvaluationCase"]
        Params["ParameterSet"]
        Experiment["Experiment (optional)"]
    end

    subgraph Execution["执行层"]
        Ref["Reference / Math Model"]
        SUT["Algorithm / System Under Test"]
        Sim["Physical Model / Simulator"]
        Device["Driver / Real Device"]
    end

    subgraph EvidenceLayer["观测与证据层"]
        Run
        Obs["Observation"]
        Eval["Independent Evaluator"]
        Claim
        Evidence
    end

    subgraph Intelligence["数据与决策层"]
        Dataset["Versioned Dataset"]
        Learner["Residual / Surrogate Model"]
        Optimizer
        Rec["Recommendation"]
        Gate["Safety & Acceptance Gates"]
    end

    Definition --> Execution
    Execution --> Run --> Obs --> Eval
    Eval --> Claim
    Eval --> Evidence
    Run --> Dataset
    Obs --> Dataset
    Evidence --> Dataset
    Dataset --> Learner --> Optimizer --> Rec --> Gate
    Gate -. "approved experiment" .-> Experiment
    Gate -. "controlled execution, R7 only" .-> Device
```

### 4.1 五个平面

| 平面 | 稳定职责 | 典型扩展 |
|---|---|---|
| Core Plane | Case、Experiment、Run、Observation、Claim、Evidence、Provenance | 存储、查询、比较、重放 |
| Domain Plane | Artifact、Profile、Evaluator、领域契约 | 离散点、五轴轨迹、测量、设备 |
| Execution Plane | Runner 与环境隔离 | 本地算法、容器、仿真器、控制器、驱动器 |
| Evidence Plane | 指标、证书、对齐、失败与决策材料 | 数学证明、交叉验证、实测、回归 |
| Intelligence Plane | Dataset、Surrogate、Optimizer、Recommendation | 诊断、预测、主动试验、受约束优化 |

这五个平面是责任边界，不要求首版实现成五个服务。

## 5. 最小闭环：有序离散点

### 5.1 为什么它是正确切入点

如果通用框架必须等到五轴、设备或场景模型完备后才能运行，它就不是通用框架。离散点切片可以最早暴露以下架构问题：

- 输入类型和语义是否可分离；
- 缺少上下文时是否能诚实降级；
- 指标能否声明前置能力；
- 结果、声明和证据是否分开；
- A/B 比较是否真的可复现；
- 新领域能否在不修改核心的情况下接入。

### 5.2 首个用户闭环

```mermaid
flowchart LR
    Input["有序点 + 可选上下文"] --> Experiment["双臂 Experiment<br/>共同参数"]
    Experiment --> Validate["执行 + 契约与结构检查"]
    Validate --> Metrics["可用指标"]
    Validate --> Missing["不可计算项及原因"]
    Metrics --> Result["Run + Claim + Evidence"]
    Missing --> Result
    Result --> Compare["重放 / A-B / 回归"]
```

最低可用体验：

1. 用户提交一组二维或三维有序点；
2. 系统保留原始输入并检查结构；
3. 即使没有物理单位，也在 `coordinate-unit` 下计算点数、范围、相邻重复、`path.length.open`、步长和适用的转角等；
4. 若提供参考和对应策略，则计算明确命名的误差或距离；
5. 若提供时间，则计算声明方法下的运动学离散指标；
6. 对不能计算的指标说明缺失能力，而不是猜测；
7. 选择两个静态注册的 Subject，在共同输入与参数下实际执行；
8. 保存可重放结果与严格比较，并从网页下载 Claim、Evidence 和 Provenance 证据包。

详细定义见 [有序离散点领域包规范](有序离散点领域包规范.md)。

## 6. 五轴数学领域包

FiveAxisTrajectoryPack 是通用框架的第一个复杂领域验证。它承担：

- M0 语义真值；
- M1 原始数学路径、`PathProgress` 与正则性；
- M2 容差内几何路径、名义扫掠体与过切/干涉；
- M3 机器运动学路径、分支、奇异性与配置空间碰撞；
- M4 连续时间参数化；
- M5 固定周期采样、离散命令重建与区间证书；
- 层间不变量、证明义务、证据等级和测试族。

它不承担：

- Axiom Core 的公共对象定义；
- 通用 Experiment/Run 生命周期；
- 设备协议；
- 学习模型训练；
- 参数写入策略。

### 6.1 接入方式

五轴领域包通过显式契约映射到 Core：

| Core 概念 | 五轴领域实例 |
|---|---|
| Artifact | M0–M5 各层规范对象 |
| Profile | 几何、碰撞上下文、运动学、约束、采样和机床配置 |
| EvaluationCase | 解析案例、一般数值案例、退化或失败案例 |
| ReferenceModel | 高精度或带证书的 M0–M5 参考求解器 |
| Subject | 被测几何、IK、时间参数化或插补算法 |
| Evaluator | 层内合法性、对应/重建策略、碰撞、跨层不变量、误差与运行代价 |
| Evidence | Exact / Certified / Validated / Observed |

领域内部阶段门仍由数学规范定义；本蓝图只决定它在平台 Roadmap 中何时进入。

实现上，DomainPack 的可哈希描述符与进程内运行绑定分离；Core 只按 `domainPackId` 解析绑定并保存领域中立 Artifact envelope。任何五轴采样视图与有序点之间的转换都必须经过版本化 Artifact Adapter，产生新的内容标识并记录保留/丢弃语义。FiveAxis F0 以“契约与能力面板”进入网页；F1 则可以呈现已经实际求值的 M0–M2 几何、连续误差、标准对应和任务几何碰撞声明。Math F4 已完成后，界面仍必须标出当前数学阶段和标准 Claim 范围，不能把 F1 的任务几何证据呈现为运动学、整机碰撞或设备可执行性结论。

## 7. 设备与物理世界

设备接入不是“再加一个数据源”，而是引入新的时间、同步、标定、安全和权限边界。

### 7.1 顺序

```text
已通过数学 gate 的输出
  → 设备/仿真适配
  → 命令或只读输入
  → 遥测与测量
  → 时间/坐标对齐
  → 物理指标与残差
  → 新 Evidence
```

### 7.2 首先只读

R3 首个设备能力只允许：

- 读取配置和版本；
- 采集遥测、报警和运行状态；
- 导入已执行结果；
- 记录设备时钟和主机时钟的映射；
- 将 MachineRun 追溯到对应 Benchmark/Reference Run。

不允许：

- 自动写入参数；
- 自动启动加工；
- 绕过设备自身联锁；
- 用平台推断值覆盖原始遥测；
- 在未标定时把控制器坐标直接当作测量真值。

### 7.3 物理模型的职责

PhysicalModel 可以覆盖驱动、伺服、机构、切削或过程、传感与测量中的一个或多个层次。模型必须声明：

- 状态、输入和输出；
- 时间尺度与积分或采样方法；
- 参数来源和标定版本；
- 适用设备、工况和边界；
- 未建模因素；
- 与真实 Observation 的对齐策略。

数学结果、仿真结果和实机结果是不同证据来源，必须并存而不能相互覆盖。

## 8. 数据与学习模型

### 8.1 数据前提

只有以下对象稳定后，数据才适合训练：

- Artifact、Profile、ParameterSet 的版本语义；
- ReferenceRun、BenchmarkRun、SimulationRun、MachineRun 的关联；
- 原始 Observation 和派生指标的分离；
- Case、MetricDefinition、Evidence 和失败分类；
- 时间、坐标和设备标定的对齐记录；
- 数据授权、脱敏、保留和删除策略。

没有这些条件，大量日志只是不可比的数据堆积。

### 8.2 首选学习任务

按优先级：

1. **异常与域外检测**：判断当前样本是否偏离已知运行域；
2. **残差预测**：学习确定性数学或物理基线未解释的部分；
3. **条件效果预测**：输入工况与参数，预测多项结果及不确定性；
4. **试验价值估计**：选择最能减少不确定性的下一批仿真或设备试验；
5. **代理模型**：近似昂贵仿真或设备响应，为约束搜索提供候选。

不优先训练“万能评分模型”，因为它会隐藏问题来源、约束冲突和数据偏移。

### 8.3 数据集是版本化产品

R5-A 当前工作面先闭合逐样本残差合同片；R5-B 把真实 holdout 的就绪门独立出来，默认示例只提供 Open readiness 场景，不内置真实正例；R5-C 则把冻结的 R4 参数研究变成有独立空间 holdout 的条件效应代理模型；R5-D 在同一冻结设计空间里规划最能补足线性认知空洞的下一批 synthetic SIL 点；R5-E 再在显式批准后执行该批次、封存标签、生成新候选并重规划；R5-F 在不晋升的前提下检验候选对冻结 R6 v2 下游决策的影响；R5-G 把可重放证据封装为等待独立人工决定的审查包；R5-H 再为 dossier 中的唯一候选冻结专属操作点并用 R7-E/R4.1 现场证据进行 case-scoped 证伪；R5-I 只在这些真实门和独立签名决定均已闭合时，执行本机 Registry 的原子默认切换、读回、监控与显式回滚。仓库没有内置真实正例，因此默认公开路径仍停在 R5-H `Open`；R5-I 的成功路径只由测试构造验证，不能当作已取得真实晋升证据。权威规范见[数据集与学习模型规范](数据集与学习模型规范.md)、[ADR-0016](架构决策记录/ADR-0016-R5可审计数据集与端侧模型边界.md)、[ADR-0028](架构决策记录/ADR-0028-R5C条件效应代理模型与空间Holdout边界.md)、[ADR-0032](架构决策记录/ADR-0032-R5D仿真实验价值采用顺序G最优设计.md)、[ADR-0033](架构决策记录/ADR-0033-R5E离线合成实验反馈闭环与候选晋升边界.md)、[ADR-0034](架构决策记录/ADR-0034-R5F候选模型下游影响评估与晋升隔离.md)、[ADR-0035](架构决策记录/ADR-0035-R5G晋升就绪审查包与模型激活隔离.md)、[ADR-0036](架构决策记录/ADR-0036-R5H候选真实Holdout与模型晋升隔离.md)与[ADR-0037](架构决策记录/ADR-0037-R5I本机模型生命周期与设备部署隔离.md)。

R5-B 不把“可以评估真实 holdout”误写成“真实泛化已经通过”。它把外部 controller-export / device-read、owner attestation、评估许可、R3 paired lineage、时钟 / 坐标对齐、`PhysicalResponseTrace`、至少 2 个 in-domain case 跨 2 台 device 和 2 个 condition、再加 1 个 OOD probe，明确拆成可上传、可验证、可拒绝的就绪门。v0.22.0 的 `axiom.adapter.r7e-to-r5b-holdout@1` 已能把多个独立 R7-E/R4.1 现场 dossier 投影为该合同；v0.23.0 进一步要求外部责任方在采集前封存 Campaign Manifest/Registration，并由严格 intake 逐项核对计划 slot 与实际 Case 后才生成 `PreRegistered` selection。CLI、HTTP 与 R5-B UI 使用同一合同；仓库仍不冻结或内置真实正例数据。

R5-C 首片不直接优化参数，而是先证明“参数条件变化到多项物理结果”的模型面可审计、可证伪。它固定 `feedOverride × samplePeriod` 的 25 点 R4 synthetic SIL 网格，以 15/5/5 空间切分隔离 train、validation 与 test，并分别预测带单位的周期 `s` 和线性跟随误差 `mm`。两个目标不合成总分，域外输入必须弃权；`syntheticConditionalEffectContractStatus=Passed` 不改变 `realWorldGeneralizationStatus=Open`，也不让 R6 v1 自动消费代理结果。

R5-D 首片把 §8.2 的“试验价值估计”落为应用层 `SimulationExperimentPlan`：只用 15 个 train 点构造六维信息矩阵，排除全部 25 个已观测点，再从 R6 v2 的 135 点网格余下 110 点中按顺序 greedy G-optimal leverage 规划默认 5 点。它只生成计划，不执行仿真、不更新模型、不自动接受或写设备；design leverage 是线性 epistemic proxy，不是预测误差概率、现实收益或安全证据。

R5-E 首片只闭合一次有限、可审计的 synthetic 反馈循环。责任方必须批准完整五点计划；每点通过 exact F3/F4/R4 硬门后封存 M4/M5/物理响应和标签身份。R5-C v1 身份保持不变，新 v2 数据为 30 点、split 为 20/5/5，validation/test 不变。候选重训后在原 holdout 上记录指标差值，然后从 105 个剩余点中生成下一计划；它不递归执行、不自动晋升，也不把 fixture 改善外推为一般收益。

R5-F 首片回答“候选用于下游筛选时会不会损害精确决策”，而不是“是否立即采用候选”。它用同一 135 点网格、同一三个意图和同一 27 次 exact 预算并排运行基线/候选；筛选顺序可以变化，精确硬门不能变化。只有候选不丢失基线预算内最佳精确目标时影响门才通过；结果仍为 `EvaluatedOnly` / `NotPerformed`，不关闭 reality 或模型晋升门。

R5-G 首片回答“这些候选证据是否完整到可以提交独立审查”，而不是“是否已经批准晋升”。它确定性重放 R5-E/R5-F、冻结旧基线回滚身份并列出六个仍未关闭的门；`ReadyForIndependentReview` 不改变 default、registry、activation、deployment 或 device 状态。

R5-H 首片回答“这个具体候选在预登记的真实 Case 上是否仍满足目标定义”，而不是“R5-B 的另一模型是否通过”或“是否自动采用候选”。它冻结至少两个跨设备/工况的 in-domain Case、一个 contextual OOD probe、精确 M4/M5 和阈值，只接受完整 R7-E/R4.1 报告；周期头保持 exact-planner，线性误差头才由 X/Y/Z controller-live-read 派生并计入 reality。通过也只产生 `CaseScopedPassed`，不自行产生独立决定或修改默认模型。

R5-I 首片回答“在真实证据和独立决定都成立后，如何让本机默认模型以可恢复、可审计的方式改变”。它权威重放 R5-G/R5-H、验证内容绑定的 HMAC-SHA256 `PromotionDecision`，再用单个 SQLite 事务完成候选注册、generation 增长、默认指针切换与 ActivationReceipt，并在提交后重新读回。运行监控分别检查 bundle、推理、OOD、双目标 RMSE 与覆盖率；只有持久化的 `RollbackRequired` 报告和另一份显式签名决定才能回到冻结基线。所有写操作只存在于 Windows 本机 CLI，HTTP/网页只读；该层不连接控制器，也不授予设备部署或写入权限。

每个 DatasetSnapshot 至少绑定：

- 查询和筛选规则；
- 所含 Run 和 Artifact 的不可变引用；
- 标签和派生过程；
- 训练、验证、测试的分组策略；
- 设备、工件、算法版本和时间分布；
- 已知偏差与覆盖空洞；
- 许可和敏感性。

训练和测试不得因同一轨迹、同一设备批次或同一加工任务的派生样本而发生泄漏。

### 8.4 为端侧小模型预留正确接口

端侧模型不是把训练代码直接搬到设备。R5-A 应把训练与部署拆开：

- 训练端消费版本化 DatasetSnapshot，保留完整特征和标签谱系；
- 导出端生成固定输入契约、预处理、模型权重、适用域和资源预算组成的 ModelBundle；
- 端侧只执行受控推理，输出预测、不确定性和域外标记；
- 端侧原始观测继续回传为新的 Observation，不在首版进行无审计在线学习；
- 量化、剪枝或蒸馏后的模型必须与原模型在独立测试集和目标设备上重新验证；
- 模型升级、回退和设备兼容性必须版本化。

这样，当前设计既不提前选择具体端侧框架，也不会等到 R5-A 才发现训练特征无法在目标端稳定复现。

## 9. 受约束参数优化

### 9.1 正确的闭环

```mermaid
flowchart LR
    Goal["用户目标 + 硬约束"] --> Search["Optimizer 搜索安全域"]
    Model["Reference / Physical / Surrogate"] --> Search
    Search --> Candidate["Recommendation"]
    Candidate --> MathGate["数学 gate"]
    MathGate --> BenchGate["Benchmark gate"]
    BenchGate --> Shadow["仿真 / shadow"]
    Shadow --> Trial["受控设备试验"]
    Trial --> Accept["人工/策略批准"]
    Accept --> Data["结果回流"]
    Data --> Model
```

Optimizer 的目标不是“找到一个分数最高的参数”，而是在声明的安全域内寻找满足硬约束的 Pareto 候选，并说明：

- 预计改善哪些指标；
- 可能牺牲哪些指标；
- 预测不确定性；
- 与训练或验证域的距离；
- 还需要通过哪些 gate；
- 推荐的试验范围、停止条件和回退值。

### 9.2 权限逐级提升

| 级别 | 平台权限 | 允许时机 |
|---|---|---|
| Offline | 离线计算候选 | R6 初期 |
| Advisory | 向用户展示建议 | 通过离线 gate 后 |
| Shadow | 跟随真实运行但不控制 | 仿真与历史回放稳定后 |
| Controlled Trial | 在限定工况、限幅和人工批准下试验 | 设备安全协议完成后 |
| Closed Loop | 在明确控制包线内自动调整 | R7 且具备监控、回滚、审计和法规条件 |

从 Offline 到 Closed Loop 不是界面开关，而是证据和责任边界的升级。

## 10. Roadmap

Roadmap 使用 R0–R7，避免与五轴领域内部的 M0–M5 混淆。阶段按依赖关系推进，不承诺固定日历时间。

| 阶段 | 目标 | 核心交付 | 退出阶段门 |
|---|---|---|---|
| **R0 通用框架宪法** | 锁定跨领域核心 | Core 对象、角色、DomainPack、三状态轴、证据与失败语义 | 离散点和五轴均可映射；相同输入/能力/策略得到相同公共状态；领域概念未泄漏进 Core |
| **R1 有序离散点 MVP** | 完成第一个可运行评估闭环 | 输入、校验、指标、参考比较、带时间 Case、可执行双臂 Experiment、重放、网页报告 | 通过领域包规范 §11 的全部条件及 §10.4 一致性样例；Case D 冻结共同输入与参数 |
| **R2 五轴数学领域包** | 接入完备数学模型 | M0–M5、PathProgress、对应/重建策略、模型碰撞验证、参考求解器、证书和测试族 | 通过数学规范 Math F0–F4；R2 已闭合，面向下游的候选具备完整标准 Claim 且无 `CollisionUnchecked`；无需改写 Core |
| **R3 设备只读接入** | 建立可信数据采集链 | Device/Profile、遥测、时钟或坐标对齐、MachineRun lineage | 数学、算法和设备 Run 可追溯；零自动写入 |
| **R4 物理模型与现实对齐** | 解释模型—设备差异 | PhysicalModel、标定、仿真、残差分解、SIL/HIL 或等价验证 | 同一 Case 可比较数学、仿真和设备证据 |
| **R5 数据集与学习模型** | 形成可信预测、实验规划与本机模型生命周期能力 | DatasetSnapshot、异常检测、残差或条件效果模型、不确定性、端侧 ModelBundle 候选、R5-B real holdout readiness、R5-D SimulationExperimentPlan、R5-E approved synthetic AcquisitionReceipt/retrain/replan、R5-F candidate downstream impact report、R5-G promotion readiness dossier、R5-H candidate holdout study/assessment、R5-I PromotionDecision/local registry/activation/monitoring/rollback receipts | R5-A 闭合 syntheticLearningContractStatus；R5-C 闭合声明域内 syntheticConditionalEffectContractStatus；R5-D 在冻结未观测池生成可复算 Planned/Blocked 结果；R5-E 在显式批准后闭合单批 synthetic plan→train→replan；R5-F 在同网格/预算/精确门下比较候选影响；R5-G 只把完整证据标为 ReadyForIndependentReview；R5-H 必须预登记指定候选和 exact command，只有完整 R4.1 证据、双头非劣与 coverage 门全过才可形成 CaseScopedPassed；R5-I 只在 R5-G/R5-H 与独立签名决定均闭合后，原子写入本机 SQLite、读回 generation、监控并接受显式回滚；仓库没有真实正例，默认 realWorldGeneralizationStatus 与公开模型晋升路径仍为 Open；集中式 Registry、设备部署、受控试验和设备写入保持 Open |
| **R6 受约束参数推荐** | 反向寻找候选参数 | 目标或约束、代理辅助搜索、精确重放、Recommendation、离线与 shadow gate | 候选不违反硬约束，建议可解释、可复验、不可自动写入 |
| **R7 受控闭环** | 在控制包线内自动调整 | 权限、限幅、停止、回滚、审计、在线监控 | 安全论证、责任边界和运行证据满足具体部署要求 |

### 10.1 当前工作面

当前只推进：

- R0：稳定文档边界和核心契约；
- R1：有序离散点最小闭环，以及本地 Point Lab 工作台；
- R2：已完成 Math F0–F4 的五轴数学领域包闭环，Reference Solver / SUT 验收现在是已关闭的数学门禁，不再新增驱动器写入或控制器上机许可；
- R3：已完成 Windows JSON capture 的只读参考链，冻结 Device/Profile、raw telemetry、时钟/坐标上下文、paired/unpaired MachineRun lineage、五类 `Observed` 数据 Claim 和 Machine Lab；它不代表真实控制器协议或写能力已经实现；
- R4：首片冻结 Windows 轴空间一阶响应模型、独立 synthetic SIL oracle、校准/holdout 隔离、显式时间/通道对齐和单位分组残差；这只闭合合同片，不能把真实设备 reality gate 标为完成；
- R5：R5-A Windows synthetic learning 合同片已实现，已冻结 DatasetSnapshot、split/lineage/governance、X-only 残差、split conformal 不确定性、JSON ModelBundle、typed API/UI 和禁语边界；R5-B Windows real holdout readiness 与现场 intake 已实现，并在 v0.23.0 新增采集前 Campaign Manifest/Registration、严格 slot/时序核验和 `PreRegistered` selection；R5-C 新增 25 点 R4 SIL 参数研究、15/5/5 空间 holdout、周期与线性误差双输出代理模型、conformal/OOD/parity 门和网页工作台；R5-D 复用 R5-C 训练设计与 R6 v2 网格，以顺序 G-optimal leverage 规划默认 5 个未观测 SIL 点；R5-E 要求责任方批准完整五点批次，重放 exact F3/F4/R4，封存 acquisition receipt，以 30 点/20-5-5 split 重训 v2 候选，并在 105 个剩余点中生成下一计划；R5-F 再用同一三个 R6 v2 意图、135 点网格和 27 次精确预算并排评估 v1 基线与 v2 候选，只在预算内最佳精确结果无退化时通过影响门；R5-G 对该证据链做确定性重放，冻结 rollback baseline 并生成只读审查包；R5-H 对 dossier 唯一候选执行预登记的 Case-scoped 真实 holdout。旧自报 `selectedBeforeEvaluation` 只保留兼容重放，不能关闭现实门；R5-C/R5-D/R5-E/R5-F/R5-G 不能替代真实 holdout，R5-H 也不会自动晋升；
- R5-I：新增内容绑定的晋升/回滚决定、本机 SQLite Registry、原子 generation/default 切换、提交后读回、当前默认模型推理、分目标运行监控与显式回滚。写权限仅在 Windows 本机 `model-lifecycle` CLI，HTTP/网页保持只读；仓库无真实 R5-H 正例，所以产品默认不产生已晋升模型，测试构造成功路径不属于发布证据；
- R6：Windows Offline Recommendation v1 保持六点完全枚举和三目标无权重 Pareto；v2 新增 15×9 共 135 点的目标驱动代理筛选，以一个主目标和两个显式约束替代权重总分，最多选择 27 点精确重放 F3/F4/R4，最终 Recommendation 只来自精确可行候选。两版都保持零写入、零自动接受、reality Open；v2 只声明预算内 best observed，不声明全局最优；
- R7：R7-A Windows Synthetic Shadow 合同片冻结 AcceptanceRecord、Shadow 包线与 fail-closed 状态机；新增 v2 显式接力，把 R6 v2 Recommendation、screening 与 exact candidate 身份投影为独立证据快照，再进入同一状态机，既不降级成 v1，也不自动接受。Goal-to-Shadow 应用路径进一步从 Optimization Lab 的用户选择出发，按冻结协议重新执行同一候选的 F3/F4/R4，只有 M4/M5/PhysicalResponseTrace identity 与逐样本时间、command 完全一致时，才把 X/Y/Z mm 误差无插值投影为 R7-A trace；固定合同夹具不会冒充候选响应。R7-B 用 `control.domain-pack@2` 冻结厂商无关 Deployment Shadow Readiness；R7-C 用隔离 `.NET 8` 官方 OPC UA 栈和 `control.domain-pack@3` 闭合 Windows localhost 的证书固定、加密五轴订阅、通知完整性和零写合同；R7-D 选择 Beckhoff TwinCAT 3 Build 4026+ / TF6100，以 `control.domain-pack@4` 冻结 Vendor Profile、`tcpkg`/二进制预检、许可证、BuildInfo、五轴访问级别与独立非执行 canary 拒写收据；R7-E 再用 `control.domain-pack@5` 把 command hash、sample index 与 X/Y/Z/B/C 七节点 batch Read 冻结为 exact-index Shadow Witness。Windows 现场验收包现可保留外部 `caseId`、依次重验两个 R7-E 输入并生成内容寻址的 R4.1 报告；控制器侧部署工具包进一步提供只读 `.TcPOU`、窗口 sentinel/索引最后发布协议、七节点只读属性检查和显式 namespace/NodeId 离线绑定评估；离线 `beckhoff-shadow-assessment` 与双文件 `field-evidence` 入口把采集结果确定性接入同一应用层编排器，R5-B intake 再把多个封存报告投影到跨设备/工况 holdout。整条链仍不创建安全 Claim、任意进程执行或自动 PLC 部署路径。当前开发机没有 TwinCAT/TF6100 和经授权的跨设备/工况 capture，TwinCAT compile、厂商运行时、deployment shadow、reality validation、Controlled Trial、Closed Loop 与标准符合性继续保持 Open。

R4 的首个具体合同见[物理模型与现实对齐规范](物理模型与现实对齐规范.md)：`PhysicalResponseTrace` 是模型执行主 Artifact，数学命令、物理模型、标定、R3 raw observation 与对齐记录保持独立内容身份。首个参考数据来自结构不同于候选模型的 synthetic SIL oracle；阶段报告必须把 `syntheticContractStatus` 与 `realityValidationStatus` 分开。新增真实设备 source 时仍须独立冻结厂商协议、许可、最小权限和环境验收，不从文件回放结果外推。

R5-A 当前实现只闭合逐样本 synthetic learning 合同；R5-C 只闭合冻结 R4 模型与声明参数域内的 synthetic 条件效应合同；R5-D 只闭合下一批 synthetic SIL 计划；R5-E 只在显式批准下闭合一批 synthetic 标签获取、候选重训和重规划；R5-F 只闭合候选在冻结下游搜索中的影响评估；R5-G 只闭合晋升审查包的证据完整性；R5-H 只闭合候选专属 Case 的真实证伪；R5-I 才在外部证据与独立决定齐备后修改本机默认模型，但仍不执行设备部署。R6 v1 仍只把 R5-A 用作 OOD 注记和晋级阻断，不消费 R5-C；R6 v2 使用新的版本化合同显式消费 R5-C 基线，R5-F 则用独立候选版本进行同条件比较；代理都只筛选 135 点参数网格，最多 27 个候选仍逐一重放 R4 与全部数学硬门。R5-C 预测、R5-D design leverage、R5-E synthetic candidate gate、R5-F impact gate、R5-G review readiness、R5-H Case-scoped assessment 和 R5-I 本机 activation 都不升级为物理目标、跨域真实泛化、设备权限或闭环控制证据。R6/R7 权威合同见[受约束优化与安全闭环规范](受约束优化与安全闭环规范.md)、[ADR-0018](架构决策记录/ADR-0018-R6多目标离线推荐与权限边界.md)、[ADR-0019](架构决策记录/ADR-0019-R7A-Shadow受控运行与设备安全边界.md)、[ADR-0020](架构决策记录/ADR-0020-R7B-部署影子就绪性与厂商边界.md)、[ADR-0021](架构决策记录/ADR-0021-R7C-Windows虚拟OPC-UA传输验收边界.md)、[ADR-0022](架构决策记录/ADR-0022-R7D-Beckhoff-TwinCAT厂商验收边界.md)、[ADR-0023](架构决策记录/ADR-0023-R7E样本索引采集与R41双运行现实门.md)、[ADR-0024](架构决策记录/ADR-0024-现场证据采用应用层双运行编排.md)、[ADR-0025](架构决策记录/ADR-0025-Beckhoff见证采用控制器锁存与离线部署预检.md)、[ADR-0026](架构决策记录/ADR-0026-R7E现场证据到R5B真实holdout投影.md)、[ADR-0027](架构决策记录/ADR-0027-R5B现场Campaign预注册与选择证据边界.md)、[ADR-0028](架构决策记录/ADR-0028-R5C条件效应代理模型与空间Holdout边界.md)、[ADR-0029](架构决策记录/ADR-0029-R6V2目标驱动代理筛选与精确回放边界.md)、[ADR-0030](架构决策记录/ADR-0030-R6V2到R7A显式证据投影与兼容边界.md)、[ADR-0032](架构决策记录/ADR-0032-R5D仿真实验价值采用顺序G最优设计.md)、[ADR-0033](架构决策记录/ADR-0033-R5E离线合成实验反馈闭环与候选晋升边界.md)、[ADR-0034](架构决策记录/ADR-0034-R5F候选模型下游影响评估与晋升隔离.md)、[ADR-0035](架构决策记录/ADR-0035-R5G晋升就绪审查包与模型激活隔离.md)、[ADR-0036](架构决策记录/ADR-0036-R5H候选真实Holdout与模型晋升隔离.md)与[ADR-0037](架构决策记录/ADR-0037-R5I本机模型生命周期与设备部署隔离.md)。

### 10.2 依赖原则

- R1 可以在 R2 之前独立完成；
- R2 不能依赖 R3；
- R3 仅把已通过领域 gate、绑定重建策略和完整数学 Claim 的命令作为只读对齐基线；它也可只读导入既有运行，但不向设备发送控制写入；
- R5 依赖稳定的 R3/R4 数据语义，而不是依赖数据量这个单一数字；
- R6 依赖可独立验证的模型和约束；
- R7 不因 R6 的离线效果好而自动开启。

## 11. 阶段性产品形态

| 阶段 | 面向用户的形态 |
|---|---|
| R0–R1 | Point Lab Web Workbench：导入、编辑、执行、评价、比较和下载证据包 |
| R2 | Five-Axis Algorithm Lab：数学参考、算法适配、回归与诊断 |
| R3–R4 | Machine Lab：仿真或设备运行、遥测对齐和差异定位 |
| R5 | Intelligence Lab：数据集、漂移、残差、真实 holdout、效果预测、下一批实验规划，以及本机 Registry、默认模型、监控与显式回滚状态 |
| R6 | Optimization Lab：目标或约束定义、候选参数和验证计划 |
| R7 | Controlled Runtime：限定包线内的受控执行和监控 |

这些可以先是同一应用中的工作区，不预设微服务拆分。

## 12. Run 与数据谱系

从 R0 起，所有阶段共享同一条逻辑谱系。`Experiment` 是比较、重复或参数扫描的可选组织对象，不是每个 RunSpec 的必经父节点：

```mermaid
flowchart TB
    D["DomainPack / Artifact / Profile"] --> C["EvaluationCase + ParameterSet"]
    C --> RS["RunSpec"] --> R["Run"] --> O["Observation"]
    O --> MR["MetricResult"] --> CL["Claim ↔ Evidence"]
    CL --> CD["Comparison / Diagnosis / DatasetSnapshot"]
    CD --> REC["Recommendation"] --> AR["AcceptanceRecord"]
    E["Experiment (optional)"] -. "groups" .-> C
    E -. "schedules" .-> RS
    AR -. "next experiment" .-> E
```

领域可以增加：

- ReferenceRun；
- BenchmarkRun；
- SimulationRun；
- MachineRun；
- TrainingRun；
- OptimizationRun。

这些是 Run 的专业化视图或标签，不应形成互不兼容的数据孤岛。

每次运行至少可回溯：

- 输入内容及模式版本；
- 参数、约束、Profile 和 Case；
- 算法、模型、驱动和 Evaluator 版本；
- 环境、随机种子、数值精度和容差；
- 原始输出与原始遥测；
- 转换、对齐和派生指标；
- Claim、Evidence、决策与批准记录。
- 能力解析、`ExecutionStatus`、各项 `MetricStatus` 和 `CaseOutcome`。

## 13. 评估与报告原则

一份合格报告应分开显示：

1. **事实**：输入、版本、运行环境、原始观测；
2. **有效性**：哪些契约和硬约束通过或失败；
3. **状态**：执行、每项指标和整个 Case 分别为何成功、失败、无结论或不支持；
4. **指标**：独立数值、区间或分布；
5. **声明**：这些指标支持或反驳什么；
6. **证据**：Exact、Certified、Validated 或 Observed；
7. **比较**：与参考、基线或其他候选的差异；
8. **不确定性与适用域**；
9. **建议**：下一步验证或候选参数；
10. **决策**：由谁基于哪些证据接受或拒绝。

报告不应只剩：

- 一个总分；
- 一个“通过或失败”但没有原因；
- 无法定位版本的图；
- 把模型预测画成测量真值；
- 把缺失数据画成零。

## 14. 工业方法的借鉴边界

自动驾驶等行业已经验证了一组有用模式：场景化测试、SIL/HIL/VIL 分层验证、ODD/条件域、shadow 运行、持续回归和数据闭环。Axiom 借鉴的是这些**验证治理方法**，不是照搬自动驾驶的场景本体或仿真器。

在 Axiom 中的对应关系是：

| 工业验证模式 | Axiom 对应 |
|---|---|
| 场景或测试用例库 | EvaluationCase + 可选 ScenarioSpec |
| ODD 或运行条件域 | Profile + applicability/constraints |
| SIL/HIL/VIL | 不同 Runner、Run 类型和 Evidence |
| 安全 gate | Validity/Safety Claim + DecisionPolicy |
| Shadow mode | Recommendation 只观察、不控制 |
| 数据闭环 | Run/Observation/Evidence → Dataset → Model → 新 Experiment |

关键差别：离散点或单个算法评估不必被强行包装成复杂场景。ScenarioSpec 是可选组合工具，不是 Core 的唯一入口。

### 14.1 非规范性研究与标准入口

下列资料用于校准分层验证、条件域、交换格式和物理数字孪生的方向，不直接定义 Axiom 内部数据模型：

- [PEGASUS Method](https://www.pegasusprojekt.de/en/pegasus-method)：场景分层、测试空间和安全论证方法；
- [ASAM OpenSCENARIO DSL](https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/latest/index.html)：功能、逻辑、具体场景及可复用场景描述；
- [ASAM OpenODD](https://publications.pages.asam.net/standards/ASAM_OpenODD/ASAM_OpenODD/latest/specification/index.html)：运行条件域的模块化表达；
- [ISO 34502](https://www.iso.org/standard/78951.html)：基于场景的自动驾驶安全评价框架；
- [Assume-guarantee testing](https://doi.org/10.1145/1118537.1123060)：局部契约与组合验证；
- [NIST — Building a digital twin for a CNC machine tool](https://www.nist.gov/publications/building-digital-twin-cnc-machine-tool)：CNC 物理数字孪生实践。

Axiom 借鉴其“分层、契约、逐级证据和受控升级”，但内部 Core 保持领域中立，外部标准通过 Adapter 连接。

## 15. 明确不做

### 当前不做

- 完整厂商五轴生产算法或控制器仿制；
- 设备写参数或启动运行；
- 通用场景 DSL；
- 通用知识图谱或本体平台；
- 自动训练和自动部署模型；
- 无约束黑盒调参；
- 跨领域统一总分；
- 为未来可能性预建微服务。

### 长期也不应做

- 用单一模型替代数学证据和设备观测；
- 在数据不兼容时给出伪精确比较；
- 把“系统运行成功”误认为“结果正确”；
- 把“历史上没出问题”误认为安全证明；
- 在没有明确授权、限幅和回滚时自动控制设备；
- 让领域包绕过 Core 的 Provenance 与 Evidence 规则。

## 16. 成功标准

### 16.1 架构成功

- 新领域通过 DomainPack 接入，而非修改核心语义；
- Artifact 在上下文增加后逐级获得能力；
- 数学模型、算法、物理模型、设备和学习模型角色清楚；
- Case、Run、Observation、Claim、Evidence 和 Decision 可完整追溯；
- 内部可以组合为图，外部仍有清楚的阅读和操作层次。

### 16.2 R1 产品成功

- 用户输入有序离散点即可得到有意义且不过度声明的结果；
- 可添加参考、时间或 Profile 获得更高层评价；
- 可重放、A/B、回归并解释差异；
- 可在共同输入和 `ParameterSet` 下实际执行两个 Subject，而不是把两个既有输出冒充实验；
- 失败能定位到输入、执行、评价或上下文不足；
- Case A/B/C/D 和离散点规范的一致性样例在两个实现中产生相同公共状态与约定数值；
- 结果可以自然成为五轴领域包和后续数据链的基础。

### 16.3 长期闭环成功

用户最终可以：

1. 输入目标、工况和允许参数域；
2. 运行数学模型、算法、仿真或设备；
3. 采集对齐后的结果；
4. 获得多维评价、证据和问题定位；
5. 用版本化数据训练残差或代理模型；
6. 得到受约束、带不确定性和验证计划的候选参数；
7. 在仿真、shadow 和受控试验中验证；
8. 由人或明确策略批准；
9. 把结果回流为下一轮更好的模型和决策。

这条链路才是 Axiom 的最终方向。评估器是起点，不是终点。

## 17. 主要风险与控制

| 风险 | 早期信号 | 控制方式 |
|---|---|---|
| 通用内核过度抽象 | R1 需要大量空字段或复杂配置 | 以离散点用例反推最小 Core，删除未使用抽象 |
| 五轴概念泄漏到 Core | 核心对象出现刀具、轴或机床强制字段 | 移回 FiveAxisTrajectoryPack，通过 Adapter 连接 |
| 指标堆积但不能决策 | 页面有大量数字却无 Claim 或 gate | 指标必须绑定用途、前置能力和声明 |
| 数据很多但不可训练 | 版本、坐标、参数或标签无法对齐 | 从 R0 强制 Provenance，R5 前做 Dataset 审计 |
| 学习模型掩盖物理问题 | 预测准但无法解释漂移 | 优先残差或条件模型，保留确定性基线和域外检测 |
| 优化器越权 | 建议直接写入设备 | Recommendation 与 AcceptanceRecord 分离，权限分级 |
| 文档再次重复 | 同一术语在多处被重新定义 | 遵循 README 的唯一所有权和链接规则 |

## 18. 文档演进

当前规范性主体保持为九份，长期架构决策另以 ADR 记录：

1. [文档入口](README.md)；
2. 本项目规划蓝图；
3. [Axiom 通用评估框架规范](Axiom%20通用评估框架规范.md)；
4. [有序离散点领域包规范](有序离散点领域包规范.md)；
5. [FiveAxisTrajectoryPack — CNC 五轴数学参考系统全景规范](CNC%20数学参考系统全景规范.md)；
6. [设备接入与物理闭环规范](设备接入与物理闭环规范.md)；
7. [物理模型与现实对齐规范](物理模型与现实对齐规范.md)；
8. [数据集与学习模型规范](数据集与学习模型规范.md)；
9. [受约束优化与安全闭环规范](受约束优化与安全闭环规范.md)。

已生效的架构决策见 [ADR 索引](架构决策记录/README.md)。ADR 只记录跨文档、长期约束实现且存在实质替代方案的决定，不复制规范正文。

后续新增长期且存在替代方案的技术决策时，新增或替代 ADR。

R3–R7 的设备、物理、学习、受约束推荐与受控运行规范已经创建。R7-E 已在 Beckhoff TwinCAT 3 / TF6100 路线上闭合 exact sample-index Shadow Witness、只读 `.NET` Adapter、DomainPack/API/UI 与 contract conformance；R4.1 已闭合双运行 calibration/holdout reality evaluator；Windows 现场验收包进一步闭合显式 Case、双 R7-E 重放、pair 构造、最终状态与报告哈希；v0.20.0 又冻结可导入的控制器锁存模板、七只读 OPC UA 符号和离线部署绑定报告；v0.21.0 把原始采集支持文件组装为两份可独立重验的 R7-E 请求；v0.22.0 则把多个 dossier 的 validation 结果、R3 上下文与外部治理确定性投影为 R5-B holdout，并提供 Python、CLI、HTTP 与网页入口。v0.23.0 又把预先选择从调用方布尔值提升为采集前 Campaign/Registration 与严格 slot 核验，用 R5-C 闭合 R4 SIL 参数研究到双输出条件效应代理模型的独立合同，用 R5-D 把顺序 G-optimal 设计接成默认五点的下一批 synthetic SIL 计划，并由 R6 v2 在显式目标/约束下把代理筛选接回精确 F3/F4/R4 回放；Goal-to-Shadow 再把用户选择的 exact candidate 以同协议重算并接入既有 R7-A 状态机，使“数据—模型—实验计划—目标—建议—候选物理响应—Shadow 结论”成为一条可操作的应用链。这些合同都不改变现实门。Campaign 登记仍是外部责任方信任边界，不是密码学可信时间证明；R5-C、R5-D、R6 v2 与 Goal-to-Shadow 结果仍只限 synthetic SIL 和 Offline/Shadow 软件合同。由于尚无经授权的真实 TwinCAT 环境和跨设备/工况 capture，TwinCAT compile、`vendorRuntimeStatus`、跨设备/跨工况 `realWorldGeneralizationStatus`、case-scoped reality validation、deployment Shadow、Controlled Trial 与自动闭环仍保持 Open。

R5-H 在 v0.23.0 只闭合“候选专属研究可预登记、现场报告可导入、标签与门禁可重放”的实现合同。由于仓库没有经授权的真实报告，默认 assessment 必须保持 `Open`；测试构造数据不得进入产品 fixture 或发布证据。

R5-I 在 v0.23.0 已闭合“满足证据条件后如何安全改变本机默认模型”的实现合同：独立签名决定、SQLite 原子事务、generation/readback、运行监控和显式回滚均可重放。它没有改变上述现实缺口；没有真实 `CaseScopedPassed` 就不会在产品默认路径产生晋升，且本机模型激活不等于控制器部署、受控试验或设备写入。

详细触发条件见 [README](README.md)。这保证现在有清晰边界，又不把尚未验证的想法伪装成稳定规范。

---

下一篇：[Axiom 通用评估框架规范](Axiom%20通用评估框架规范.md)  
返回：[文档入口](README.md)
