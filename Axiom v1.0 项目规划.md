# Axiom v1.0 项目规划

> 文档类型：产品章程、研究计划与交付 Roadmap  
> 状态：Draft / Proposed  
> 上位理论：[Axiom 数学基础 v1.0](Axiom%20数学基础%20v1.0.md)  
> 配套架构：[Axiom v1.0 高层架构设计](Axiom%20v1.0%20高层架构设计.md)  
> 更新日期：2026-08-19

## 1. 项目重新定义

### 1.1 一句话定义

> **Axiom 是面向 CNC 控制软件的算法验证、模型可信度评估与证据化发布决策平台。**

它将同一实验协议运行于数学 Reference、算法 SUT、Orion 和真实 CNC，保留多源 Trace、测量不确定度、适用域和推理链，并回答：

> 某个 CNC 算法或软件版本，在明确的机床、控制器、轨迹族和工况范围内，是否在不违反硬约束的前提下产生了具有实际意义、能够迁移到真实设备的改善？

### 1.2 北极星问题

Axiom v1 只围绕一个核心问题建设：

\[
\operatorname{sign}(\Delta_{offline})
\stackrel{?}{=}
\operatorname{sign}(\Delta_{real})
\]

更严格地，Axiom 要建立：

\[
\widehat\Delta+B_{transfer}< -\delta_{min}
\Longrightarrow
\Delta<-\delta_{min}
\]

也就是：离线或 Orion 中观察到的算法优势，在加入全部迁移误差后，是否仍足以支持真实设备上的有限范围结论。

### 1.3 Axiom 1.0 的产品承诺

Axiom 1.0 发布时，用户应能够：

1. 定义一个可复现的 CNC 算法 A/B Study；
2. 在相同路径、参数、机器 Profile 和环境下运行两个算法；
3. 获取数学 Reference、SUT、Orion 和真实设备的多通道 Trace；
4. 对时间、坐标、单位和采集质量进行显式验证；
5. 检查连续时间硬约束和离散重建误差；
6. 对模型与实机进行 calibration/validation 隔离的可信度评价；
7. 生成包含 Claim、Argument、Evidence、Defeater 和不确定度的 Decision Pack；
8. 对结论给出 `Promote`、`Reject` 或 `MoreEvidenceRequired`，但不直接写设备。

## 2. 用户与待完成工作

### 2.1 主要用户

| 用户 | 需要完成的工作 |
|---|---|
| 插补/速度规划工程师 | 判断新算法是否在硬约束内减少周期时间或轮廓误差 |
| CNC Runtime 工程师 | 判断软件变更是否造成轨迹、状态或时序回归 |
| PLC/CNC 联调工程师 | 验证控制权、停止、Reset、互锁和模式切换性质 |
| Orion 模型工程师 | 判断模型在什么应用域内足以预测真实响应 |
| 实验室工程师 | 以一致协议完成采集、计量和封存证据 |
| 发布评审者 | 看到一个可审计、可反驳、不过度外推的发布论证 |

### 2.2 用户不应该承担的工作

Axiom 1.0 不要求用户：

- 手工拼装 Calibration/Validation JSON；
- 在 Excel 中对齐控制器和主机时间；
- 自己编写哈希与 Provenance；
- 为每个算法重复实现指标；
- 从几十个阶段页面中人工推断最终结论；
- 因为系统给出一个总分而自行猜测安全边界。

## 3. 范围和非目标

### 3.1 Axiom v1 主范围

- CNC 算法 A/B 实验；
- 有类型的 Signal、Event、Mode、Trajectory、Measurement Trace；
- 数学 Reference 和独立 Verifier；
- 连续时间与固定周期重建证书；
- Orion Adapter；
- 一个真实 CNC Reference Cell 的只读采集；
- 系统辨识、模型偏差和测量不确定度；
- 算法排序迁移；
- Assurance Case 与发布证据包；
- CLI、Python API、HTTP API 和统一 Web Workspace。

### 3.2 明确非目标

Axiom 1.0 不做：

- 生产 CNC Runtime；
- 通用工业数字孪生平台；
- 自动 PLC 工程部署；
- Safety PLC 或紧停回路；
- 自动设备参数写入；
- 在线自学习；
- 闭环自主优化；
- 跨领域万能总分；
- 上传任意代码后无隔离执行；
- 把数学可行性称为 `DeviceSafe` 或 `ProcessSafe`。

### 3.3 现有 R5–R7 的处置

当前 Intelligence、Optimization 和 Controlled Runtime 代码不删除，但在 v1 主路线中标记为 `Experimental`：

- 不再增加新的学习模型；
- 不扩大优化参数域；
- 不增加设备写入能力；
- 不把 synthetic contract completion 计作产品成熟度；
- 只有 Reality Transfer Gate 通过后，才讨论恢复主线。

## 4. 第一条产品纵切

### 4.1 为什么先选择进给规划/插补 A/B

Axiom v1 的第一条纵切选择：

> **同一条 CNC 路径、同一机器约束和同一固定周期下，比较两个 Jerk 受限进给规划或插补算法版本。**

它同时具备：

- 明确数学参考；
- 可定义连续时间硬约束；
- 可在 Orion 和真机上执行；
- 可测量周期时间、跟随误差和轮廓误差；
- 与现有 FiveAxis F1–F4 资产兼容；
- 能直接回答算法工程师的发布问题。

### 4.2 首版范围

首版先使用 3 线性轴 Reference Cell 闭合现实验证，避免同时引入五轴运动学、旋转计量和复杂碰撞造成不可辨识的失败来源。

现有 FiveAxisTrajectoryPack 作为 Advanced Domain Pack 保留，并在 Evidence Kernel v2 稳定后迁移。Axiom 1.0 不以“完成全部五轴实机证明”为发布前提。

### 4.3 Benchmark 场景族

至少包括：

1. 单轴直线启停；
2. 双轴圆轨迹；
3. 短线段连续拐角；
4. 小半径圆弧；
5. 曲率突变路径；
6. 曲率连续样条；
7. 单轴速度成为瓶颈；
8. 单轴加速度成为瓶颈；
9. 单轴 Jerk 成为瓶颈；
10. 固定周期重建边界；
11. 指令饱和；
12. 采集丢样和时间错位反例；
13. FiveAxis 扩展：旋转轴限速和 IK 分支边界；
14. FiveAxis 扩展：奇异邻域和区间碰撞。

## 5. 研究问题和预注册假设

### RQ-1 数学正确性

两个算法是否满足相同的几何、连续时间运动学和固定周期重建约束？

### RQ-2 数值可信度

SUT 与独立 Reference/Verifier 的差异是否处于声明的数值误差界内？

### RQ-3 Orion 可信度

Orion 在什么 Applicability Domain 内，能够以预声明的误差和覆盖率预测真实 Trace？

### RQ-4 排序迁移

离线和 Orion 对算法 A/B 的优劣排序，能否预测真实 Reference Cell 的排序？

### RQ-5 决策价值

Axiom 能否减少算法发布所需的人工作业，同时降低错误晋升率？

### 预注册原则

在读取 Validation 和真实 A/B 结果前，必须冻结：

- 主要指标；
- 最小实际改善 \(\delta_{min}\)；
- 适用域；
- 置信或覆盖水平；
- 模型选择规则；
- 异常和缺失处理规则；
- 排序迁移门；
- 停止条件。

## 6. 成功指标

### 6.1 科学与可信度指标

| 指标 | 定义目的 |
|---|---|
| ReproducibilityRate | 相同输入、版本和环境的结果是否可重放 |
| IndependentOracleAgreement | 关键数学结论是否经过独立实现复核 |
| PredictionIntervalCoverage | 模型区间是否达到预声明覆盖率 |
| RealityTransferRate | 离线/Orion 排序与实机排序一致比例 |
| FalsePromotionRate | 被 Axiom 晋升但实机无实际改善的比例 |
| ApplicabilityAbstentionAccuracy | 超出适用域时是否正确拒绝外推 |
| UnresolvedDefeaterRate | 发布决策中尚未关闭的 Defeater 比例 |

### 6.2 产品指标

| 指标 | Axiom 1.0 目标方向 |
|---|---|
| EvidenceCycleTime | 从算法提交到 Decision Pack 显著低于当前人工流程 |
| ManualAssemblySteps | 降至 0 个安全相关手工拼装步骤 |
| TraceLineageCompleteness | 100% 原始和派生 Trace 可追溯 |
| CalibrationValidationOverlap | 0 |
| DeviceWriteSurface | 0 |
| StudyReuseRate | 同一 Protocol 可复用到多个版本和运行环境 |

数值阈值由 P0 的预注册会议冻结，不在本 Draft 中凭空制定。

## 7. 阶段门

| Gate | 名称 | 证明内容 |
|---|---|---|
| G0 | Reproducible | 相同输入和环境可重放，身份公式稳定 |
| G1 | Independently Verified | 关键数学结论由独立 Oracle/Verifier 复核 |
| G2 | Trace Trustworthy | 时钟、坐标、单位、采集完整性和测量模型闭合 |
| G3 | Model Validated | 独立真实 holdout 满足预声明误差和覆盖门 |
| G4 | Ranking Transfer | 离线/Orion 排序满足数学基础 T4 的迁移条件 |
| G5 | Cross-Condition | 在第二工况族上重新验证或正确弃权 |
| G6 | Decision Support | 证据足以支持人工 Promote/Reject/MoreEvidence |
| G7 | Controlled Trial | 由独立权限和安全系统批准；不属于 Axiom 1.0 |

代码完成、API 存在和 fixture Passed 不能代替 Gate 关闭。

## 8. 总体交付计划

### 8.1 资源假设

计划按 5–7 人核心团队估算：

- 1 名技术负责人/系统架构师；
- 1–2 名数学与运动规划工程师；
- 1 名系统辨识/统计工程师；
- 1 名平台后端工程师；
- 1 名 Windows/设备接入工程师；
- 0.5–1 名 Web/产品工程师；
- 共享实验室与 CNC 工艺支持。

团队更小时可以延长周期，但不能跳过阶段门。

### 8.2 周期总览

| 阶段 | 建议周期 | 主要结果 |
|---|---:|---|
| P0 重新立项与预注册 | 2–3 周 | 统一目标、Reference Cell、Claim Catalog |
| P1 Evidence Kernel v2 | 6–8 周 | 多 Trace、证书、Argument、显式组合根 |
| P2 CNC Offline Benchmark | 8–10 周 | A/B 数学闭环和独立验证 |
| P3 Orion Credibility Lab | 8–10 周 | 模型适配、失配注入、辨识基线 |
| P4 Reference Cell | 10–12 周 | 真实只读采集和测量不确定度 |
| P5 Reality/Ranking Transfer | 8–10 周 | 模型验证和算法排序迁移 |
| P6 产品化与试点 | 8–10 周 | 统一 Workspace、Decision Pack、3 个试点 |

顺序执行约 52–63 周；设备准备和平台工作可以有限并行。

## 9. P0：重新立项与预注册

### 目标

将当前“覆盖更多阶段”的推进方式切换为“关闭一个真实可证伪问题”。

### 任务

- 建立 `v0.22-research-snapshot` 标签；
- 接受或修订本数学基础、项目规划和架构；
- 确定第一台 Reference Cell；
- 确定算法 A 和 B；
- 冻结首版 MachineProfile；
- 定义 10 个以内顶级 Claim；
- 定义主要指标和 \(\delta_{min}\)；
- 定义 Validation 数据封存规则；
- 创建 ADR-0027；
- 建立 P0 风险登记表。

### 交付物

```text
Axiom 数学基础 v1.0.md
Axiom v1.0 项目规划.md
Axiom v1.0 高层架构设计.md
Claim Catalog v1
Reference Cell Profile v1
Statistical Analysis Plan v1
Validation Data Governance v1
```

### 退出条件

- 团队能够用同一句话描述 Axiom 1.0；
- 第一条纵切、机床和算法版本均已确定；
- Validation 数据在分析前可被独立封存；
- R5–R7 主线扩张停止。

## 10. P1：Evidence Kernel v2

### 目标

构建真正领域中立、支持多 Trace、误差证书和 Assurance Case 的核心。

### 新核心对象

```text
Study
ResearchQuestion
IntendedUse
ApplicabilityDomain
ExperimentProtocol
RunPlan
Run
RawTraceSet
DerivedTraceSet
AnalysisPlan
AnalysisRun
CredibilityCertificate
Claim
Argument
Assumption
Evidence
Defeater
DecisionRecord
```

### 任务

- 将 ordered-point 类型移出 Core；
- 支持一个 Run 输出多个 Trace；
- 实现 Raw/Derived 不可变身份规则；
- 实现 ClockGraph 和 FrameGraph；
- 实现证书链组合和风险预算；
- 实现 Claim → Argument → Evidence 约束；
- 取消顶层 `__init__` 导入副作用注册；
- 建立显式 CompositionRoot；
- 提供 v0.22 RunBundle 导入 Adapter；
- 建立 Proof Obligation 状态模型。

### 退出条件

- Core 不导入具体 CNC、FiveAxis、Physical、Intelligence 或 Control 模块；
- 任一派生 Trace 都引用源 Trace 和变换证书；
- 缺少 Argument 时无法发布 Supported Claim；
- T2 证书组合有性质测试和反例测试；
- v0.22 证据可以只读迁移，不破坏历史身份。

## 11. P2：CNC Offline Benchmark

### 目标

建立第一个不依赖实机、但具有独立数学证据的算法 A/B 闭环。

### 三个隔离角色

```text
Subject / SUT
Reference Solver
Independent Verifier
```

关键算法不得共享同一核心实现后互相自证。

### 指标和硬门

- 路径端点、拓扑和 Frame 正确；
- 几何误差；
- 速度、加速度和 Jerk 连续区间约束；
- 固定周期重建误差；
- 轴限位；
- Cycle time；
- 约束利用率；
- 数值稳定性；
- 算法执行时间；
- FiveAxis 扩展的 IK、奇异和碰撞。

### 退出条件

- 至少 20 个来源明确的 Benchmark Case；
- 每个硬门有独立 Verifier；
- 关键数值结论有误差界或明确降级；
- 失败可定位到时间区间、轴、性质和 Proof Obligation；
- 没有万能总分；
- G0、G1 通过。

## 12. P3：Orion Credibility Lab

### 目标

让同一 ExperimentProtocol 可以运行于算法、Reference 和 Orion，并能故意构造可检测的模型失配。

### 模型梯度

```text
M0 identity / zero-delay baseline
M1 independent first-order null model
M2 FOPDT
M3 ARX
M4 low-order state space
M5 structured discrepancy model
```

### 必须注入的失配

- 时间常数错误；
- 静态偏置；
- 摩擦和死区；
- 回差；
- 限速与饱和；
- 轴间耦合；
- 时间戳偏移与抖动；
- 丢样与撕裂；
- 坐标变换错误；
- 测量噪声变化。

### 任务

- 建立 Orion Adapter；
- 定义命令、Signal/Event/Mode Trace 合同；
- 建立模型版本和参数身份；
- 实现 excitation 和 identifiability 诊断；
- 实现 residual diagnostics；
- 建立 calibration/validation 数据隔离；
- 实现模型比较而不是只拟合一个模型；
- 设计未来 FMI Adapter，但不强制重写 Orion。

### 退出条件

Axiom 能够区分并结构化报告：

```text
implementation error
parameter error
model-form discrepancy
clock error
frame error
measurement error
insufficient excitation
```

## 13. P4：Reference Cell

### 目标

建立第一条从冻结命令到真实设备、外部测量和不可变证据的完整链。

### Reference Cell 必须冻结

- Machine ID；
- Controller/PLC/CNC 版本；
- 驱动和固件；
- 轴和编码器配置；
- 插补与 PLC 周期；
- Machine/Workpiece/Tool Frame；
- 时间源和同步方式；
- 采集程序版本；
- 温度、暖机和负载条件；
- 操作者和评估授权。

### 最低采集通道

```text
commanded position
actual position
actual velocity
following error
torque/current
feed override
CNC mode
PLC mode
alarm and event
controller timestamp
device timestamp
sample sequence
```

### 测量计划

- 编码器/控制器反馈作为内部测量；
- 圆轨迹使用 ISO 230-4 派生测试；
- 必要时加入球杆仪、激光干涉仪或其他外部计量；
- 每个 Measurand 有不确定度预算；
- 内部反馈与外部计量不能混称为同一种现实真值。

### 数据治理

\[
D_{cal}\cap D_{val}=\varnothing
\]

隔离不仅要求文件不同，还要求 Case、命令、时间窗、运行和内容身份无重叠。

### 退出条件

- 至少 2 个 calibration Case；
- 至少 2 个独立 in-domain validation Case；
- 至少 1 个 OOD Case；
- G2 通过；
- 所有数据由工具链封存，无安全相关手工拼装；
- 设备生产路径中不存在 Write/Call。

## 14. P5：Reality 与 Ranking Transfer

### 目标

用独立真实 holdout 检验模型是否足以支持“离线算法排序”这一预期用途。

### 分析流程

```text
冻结 Validation Set
→ 重放数学硬门
→ 模型预测
→ 实机运行
→ 测量与对齐
→ 预测区间覆盖
→ 残差诊断
→ A/B 配对差异
→ 迁移界组合
→ Ranking Transfer Decision
```

### 主要输出

- ModelApplicabilityReport；
- PredictionCoverageReport；
- ResidualDiagnosticReport；
- RealityTransferReport；
- FalsePromotionAssessment；
- Claim–Argument–Evidence Case；
- 未关闭 Defeater。

### 退出条件

- G3 通过；
- G4 通过，或明确判定当前模型不足；
- 模型不足时不以学习模型自动补洞；
- 所有正向排序 Claim 满足数学基础 T4；
- 超出适用域时系统正确弃权。

若 G4 未通过，Axiom 仍可作为高质量离线 Benchmark 与回归平台发布，但不得宣传为“智能优化平台”。

## 15. P6：产品化与试点

### 目标

把当前多个阶段 Workbench 合并为一个围绕 Study、Trace、Claim 和 Decision 的统一用户流程。

### 用户主流程

```text
创建 Study
→ 选择/创建 Protocol
→ 绑定算法 A/B
→ 选择 Reference、Orion、Reference Cell
→ 预检适用域和权限
→ 执行/导入 Run
→ 检查 Trace、Clock、Frame 和质量
→ 执行 Analysis Plan
→ 检查 Proof Obligations
→ 查看 Assurance Case
→ 生成 Decision Pack
```

### 发布物

- Python SDK；
- CLI；
- HTTP API；
- Unified Experiment Workspace；
- Windows Read-only Edge Agent；
- Orion Adapter；
- CNC Trajectory Benchmark Pack；
- HTML/PDF Decision Pack；
- v0.22 兼容导入器；
- 3 个真实团队试点。

### 退出条件

- 非核心开发者无需修改 Python 源码即可运行主流程；
- 三个试点均形成可审计 Decision Pack；
- 关键流程在失败后不会保留陈旧 Supported 状态；
- G6 通过；
- Axiom 1.0 仍无设备写入表面。

## 16. 后续 P7：条件性智能化

P7 不属于 Axiom 1.0，只有 G4 通过后才能启动。

允许：

- 预测数学/Orion 到实机的残差；
- 主动选择最有信息量的下一次实验；
- 缩小昂贵仿真和实机实验的搜索空间；
- 离线候选推荐；
- 不确定度驱动的 `MoreEvidenceRequired` 建议。

仍禁止：

- 自动设备写入；
- 自动批准候选；
- 在线无监督学习；
- 用学习结果覆盖硬约束；
- OOD 强制外推。

## 17. 团队和责任

| 角色 | 主要责任 | 不得承担 |
|---|---|---|
| Product/Research Owner | Intended Use、优先级和停止条件 | 单方面改统计门 |
| Math/Verification Lead | 定义、定理、Proof Obligations、Oracle | 自己批准设备试验 |
| Identification/UQ Lead | 试验设计、辨识、偏差、测量和统计 | 看到 validation 后改规则 |
| Platform Lead | Core、存储、Provenance、API | 把领域语义塞回 Core |
| Edge/Device Lead | 只读采集、Clock、Frame、权限证明 | 增加隐式写路径 |
| Lab Owner | Reference Cell、操作和安全许可 | 修改证据或结论 |
| Decision Authority | Promote/Reject/MoreEvidence | 生成或选择性删除证据 |

## 18. 决策治理

### 必须使用 ADR 的决定

- 修改核心数学语义；
- 改变 Claim/Evidence/Certificate 定义；
- 增加新的设备权限；
- 修改 Calibration/Validation 隔离；
- 修改统计分析计划；
- 扩大 Applicability Domain；
- 重新启用 R5–R7 主线；
- 引入动态代码加载或远程执行。

### 发布评审输入

每次发布评审必须同时查看：

```text
Scope
Open Defeaters
Proof Obligation Status
Evidence Independence
Uncertainty Budget
Applicability Domain
Known Counterexamples
Decision Authority
```

## 19. 风险登记

| 风险 | 后果 | 早期信号 | 缓解 |
|---|---|---|---|
| 继续扩张功能 | 核心科学问题未关闭 | 新页面多于新实机证据 | 冻结 R5–R7 |
| Reference 与 SUT 共享实现 | 自验证 | 结果永远完全一致 | 独立实现和变异测试 |
| 真机数据不足 | 无法验证现实迁移 | 只有 synthetic Passed | P0 锁定 Reference Cell |
| 采集时间不可比 | 错误残差和排序 | 对齐依赖人工平移 | ClockGraph 和误差界 |
| 模型不可辨识 | 参数无物理意义 | FIM 秩亏、参数漂移 | 试验设计和集合值估计 |
| 外部计量缺失 | 反馈信号被误称真值 | 只看控制器内部值 | 测量计划和不确定度 |
| UI 掩盖不确定性 | 错误 Promote | 单一绿色状态 | 展示 Margin/Defeater |
| 统计规则后验修改 | 过拟合结论 | 看结果后改阈值 | 预注册和封存 |
| 安全边界漂移 | Axiom 变成控制产品 | 新增 Write/Call | 架构和 CI 零写门 |
| Core 再次领域化 | 扩展需要改 Core | import 依赖增长 | CompositionRoot 契约测试 |

## 20. 停止与转向规则

以下规则高于功能 Roadmap：

1. 没有真实 Reference Cell，P5 不启动；
2. 没有测量不确定度，不发布现实优劣 Claim；
3. 没有独立 holdout，不发布 Model Validated Claim；
4. G4 未通过，不恢复“智能优化平台”主叙事；
5. 新领域接入需要修改 Core 调度逻辑，视为 P1 失败；
6. 新功能无法映射到 Research Question、Claim 或用户决策，不进入主线；
7. 发现 Calibration/Validation 泄漏，相关全部 Claim 作废；
8. 发现设备写入表面，Axiom 1.0 发布阻断；
9. 结论裕量小于总迁移界，必须输出 `MoreEvidenceRequired`；
10. 现实证据反驳模型时，优先修正或限制模型，不通过学习器掩盖。

## 21. Axiom 1.0 Definition of Done

Axiom 1.0 只有同时满足以下条件才完成：

- 一个算法 A/B Study 可端到端运行；
- 同一 Protocol 覆盖 Reference、SUT、Orion 和真实 Reference Cell；
- 至少一个现实 Model Validation Case 完成；
- 至少一个排序迁移 Claim 被 Supported 或明确 Refuted；
- 全部结论带 Applicability Domain 和不确定度；
- Evidence、Argument 和 Defeater 可审计；
- Raw/Derived Trace 身份和变换链完整；
- 用户能从统一 Workspace 生成 Decision Pack；
- 旧 v0.22 结果可导入查看；
- 无设备写入、自动批准或在线学习能力；
- 数学基础中的相关 Proof Obligations 已关闭。

## 22. 首个 90 天执行清单

### 第 1–2 周

- 评审 ADR-0027；
- 确定算法 A/B；
- 确定 Reference Cell；
- 冻结 Claim Catalog；
- 冻结主要指标和 \(\delta_{min}\)。

### 第 3–6 周

- 建立 `core_v2`；
- 实现 Study、Protocol、Run、TraceSet；
- 实现内容身份和 Raw/Derived 规则；
- 建立 v0.22 Import Adapter。

### 第 7–10 周

- 实现 Certificate、Argument、Defeater；
- 实现 T2/T3/T4 的计算对象；
- 建立 ClockGraph、FrameGraph；
- 建立 Proof Obligation 状态机。

### 第 11–13 周

- 接入第一个进给规划 SUT；
- 接入独立 Reference；
- 完成首批 8–10 个 Benchmark Case；
- 产出第一份完全离线的 A/B Decision Pack。

90 天结束时，目标不是恢复 R5–R7，而是证明新的数学对象和用户闭环能够替代当前以阶段页面为中心的推进方式。
