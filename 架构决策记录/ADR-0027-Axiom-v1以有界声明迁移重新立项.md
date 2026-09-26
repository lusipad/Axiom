# ADR-0027：Axiom v1 以有界声明迁移重新立项

> 状态：Proposed  
> 日期：2026-08-19  
> 决策范围：产品定义、理论根基、Roadmap、Core v2、R5–R7 主线地位  
> 上位理论：[Axiom 数学基础 v1.0](../Axiom%20数学基础%20v1.0.md)  
> 项目规划：[Axiom v1.0 项目规划](../Axiom%20v1.0%20项目规划.md)  
> 架构设计：[Axiom v1.0 高层架构设计](../Axiom%20v1.0%20高层架构设计.md)

## 背景

Axiom v0.22 已积累大量有价值的工程资产：

- DomainPack、Run、Claim、Evidence 与 Provenance；
- ordered-point 最小闭环；
- FiveAxis F1–F4 数学链；
- R3 只读设备观测；
- R4 synthetic SIL 和现实对齐合同；
- R5 数据、学习和真实 holdout intake；
- R6 Offline Recommendation；
- R7 Shadow、OPC UA、Beckhoff 和现场证据编排。

这些资产的局部边界通常是谨慎的，仓库也明确没有把 synthetic、readiness 或 imported evidence 误称为 DeviceSafe 或 ProcessSafe。

但当前 Roadmap 仍存在结构性问题：

1. 产品范围同时覆盖通用实验平台、五轴数学、数字孪生、机器学习、优化和受控运行；
2. 上游真实可信度门仍 Open，工程资源却持续向依赖该门的 R5–R7 横向扩张；
3. Core 文档宣称领域中立，但公共 Experiment 和部分对象仍由 ordered-point 首个用例塑形；
4. Claim 与 Evidence 之间缺少显式 Argument、Assumption、Defeater 和误差迁移规则；
5. 当前最薄弱的模型—现实预测能力、测量不确定度和参数可辨识性，没有成为唯一优先级；
6. 阶段完成主要由合同、fixture、API 和 UI 闭合表达，不能直接回答“离线判断能否预测真实 CNC”。

若继续沿当前顺序推进，项目会拥有越来越完整的合同体系，却仍无法证明其核心产品价值。

## 决策

### 1. 重新锁定产品定义

Axiom v1 定义为：

> 面向 CNC 控制软件的算法验证、模型可信度评估与证据化发布决策平台。

它不以成为通用工业数字孪生、生产 CNC、设备控制器或自动闭环优化平台为 v1 目标。

### 2. 采用“有界声明迁移”作为数学根基

Axiom v1 的理论中心从：

```text
Artifact → Metric → Claim
```

调整为：

```text
表示层之间的误差/风险证书
→ 证书组合
→ 鲁棒性质迁移
→ 算法排序迁移
→ 限定适用域 Claim
```

正向 Claim 必须满足 Margin Principle：

\[
\text{claim margin} > \text{combined transfer bound}
\]

否则状态必须为 `Inconclusive` 或 `MoreEvidenceRequired`。

### 3. 以一条真实纵切作为 Axiom 1.0

第一条主纵切为：

> 在相同 CNC 路径、机器约束和固定周期下，比较两个 Jerk 受限进给规划或插补算法，并将 Reference、SUT、Orion 和真实 Reference Cell 的结果连接成一个 Assurance Case。

首个现实闭环优先使用三线性轴 Reference Cell；现有五轴资产作为高级领域包保留和迁移，不作为第一台真实设备门的复杂度前提。

### 4. 冻结 R5–R7 的主线扩张

现有 R5、R6 和 R7 代码与历史证据保留，但重新分类为 `Experimental`：

- 不删除历史实现；
- 不改写原始 Claim 和 Open 状态；
- 不继续增加新的学习、优化或设备控制表面；
- 在 Reality/Ranking Transfer Gate 通过前，不把这些阶段作为产品主线成熟度。

本 ADR 不否定 ADR-0016 至 ADR-0026 的局部合同和安全边界；它改变的是这些能力在产品 Roadmap 中的优先级和进入条件。

### 5. 建立 Evidence Kernel v2

Core v2 引入：

```text
Study
ExperimentProtocol
RunPlan
RawTraceSet
DerivedTraceSet
ClockGraph
FrameGraph
AnalysisPlan
CredibilityCertificate
Argument
Assumption
Defeater
DecisionRecord
```

同时：

- ordered-point 移出 Core；
- 一个 Run 可以产生多个 Trace；
- Raw Trace 永不可变；
- 顶层导入不再通过副作用注册所有领域；
- 插件通过显式 CompositionRoot 和 Manifest 组合；
- v0.22 通过只读 Import Adapter 保留。

### 6. 成熟度由现实 Gate 表达

v1 使用以下 Gate：

```text
G0 Reproducible
G1 Independently Verified
G2 Trace Trustworthy
G3 Model Validated
G4 Ranking Transfer
G5 Cross-Condition
G6 Decision Support
G7 Controlled Trial
```

G7 由独立设备权限和安全系统负责，不属于 Axiom 1.0。

### 7. 保持零设备写入

Axiom 1.0 的生产 Adapter 只允许：

- Read；
- Subscribe；
- Import；
- Seal evidence。

不允许 Write、Method Call、PLC 部署、参数激活、自动 Stop 或自动 Acceptance。

## 影响的现有决策

### 保留且继续有效

- ADR-0001 至 ADR-0015 的大部分状态、数学边界、显式 Adapter、连续区间证据、只读观测和 synthetic/reality 隔离原则；
- ADR-0016 至 ADR-0026 已实现对象的历史身份、零写边界和 Open 状态；
- Calibration/Validation 隔离；
- 不允许数学 Claim 越权为设备安全 Claim。

### 需要后续迁移或补充

- ADR-0006 的双臂 ordered-point Experiment 变为一个领域实现，不再代表 Core 的通用 Experiment 上限；
- ADR-0008 的“单主 Artifact Run”在 Core v2 中由多 Trace Run 替代，但历史 v0.22 语义保留；
- ADR-0016 至 ADR-0026 的能力移入 Experimental 路线；
- 新增 Argument、Defeater、Applicability Domain、Uncertainty 和 Certificate 语义；
- DomainPack 拆分为 DomainPackage 与执行/采集/模型 Adapter 合同。

在本 ADR 被接受前，不直接把既有 ADR 标记为 Superseded；接受后应分别创建迁移 ADR 或更新互链，避免用一个总 ADR 模糊覆盖局部技术决定。

## 正面后果

- 项目首次拥有一个可证伪、可测量的核心科学问题；
- 数学、仿真、真实设备和工程决策通过误差界而非文档层级连接；
- 真机和测量证据成为主路线，不再被更多 synthetic 合同替代；
- 现有五轴、内容寻址、只读采集和负例资产得到保留；
- Core 的通用性由多个 Trace 和显式扩展合同验证，而不是由文档宣称；
- 学习和优化只有在基础可信度成立后恢复，减少错误外推风险；
- 产品可以先以高质量 Benchmark/Regression 平台交付，即使 G4 最终未通过。

## 负面后果

- 短期内需要停止一些功能开发并重构核心对象；
- 旧 Web Workbench 不再继续作为主产品形态；
- 需要真实 Reference Cell、计量资源和跨专业团队；
- 一些当前称为“已完成”的阶段会改为“合同已实现，但产品 Gate 未关闭”；
- 多 Trace、UQ、Assurance 和迁移兼容会增加 v1 Core 工作量；
- 项目可能通过真实证据发现 Orion 或当前物理模型不足，导致结论收缩。

这些成本被视为必要，因为不能用更多接口完整性替代现实预测能力。

## 被否决方案

### 继续按 R0–R7 顺序扩张

局部实现可以继续增长，但上游 Reality Gate 没有增加足够现实信息，无法解决当前瓶颈。

### 只补充更多论文和文档，不改变 Roadmap

理论不会自动约束实现；如果没有新的阶段门、Core 对象和停止规则，文档仍会被现有实现反向塑形。

### 直接使用神经网络弥补物理模型

在模型结构、测量、可辨识和真实 holdout 尚未闭合时，学习器可能降低训练误差，却不能证明可迁移性。

### 直接把 Orion 作为世界模型底座

Orion 可以成为重要 PlantModel/Simulator，但其可信度必须相对于 Intended Use、Applicability Domain 和真实 holdout 评价，不能因功能丰富而自动成为现实真值。

### 彻底删除 v0.22 并重写

会破坏已建立的 Provenance、数学和设备边界，也无法从历史实现中学习。选择 Strangler 迁移和只读兼容。

### 立即拆分微服务

当前瓶颈是理论和产品闭环，不是服务伸缩。模块化单体加隔离 Worker 能更低成本地保持边界。

## 实施步骤

1. 评审并接受/修订三份 v1 主体文档；
2. 建立 `v0.22-research-snapshot`；
3. 冻结首个 Reference Cell、算法 A/B 和 Claim Catalog；
4. 建立 `core_v2` 与 v0.22 Import Adapter；
5. 交付第一个纯离线 A/B Decision Pack；
6. 接入 Orion 并建立模型失配实验室；
7. 完成真实只读采集、计量和 holdout；
8. 评价 Model Validation 和 Ranking Transfer；
9. 只有 G4 通过后，提交是否恢复智能化路线的新 ADR。

## 接受条件

本 ADR 应在以下事项明确后由项目 Owner 接受：

- 第一条算法纵切；
- 第一台 Reference Cell；
- 现实数据授权和实验责任；
- P0 的主要 Claim 和指标；
- R5–R7 冻结范围；
- Core v2 兼容策略；
- 项目人力和设备资源。

若这些条件无法满足，本 ADR 可继续保持 Proposed，但主线不应继续以“真实优化与闭环即将完成”的方式扩张。
