# ADR-0007：领域包运行时绑定与显式 Artifact Adapter

> 状态：Accepted
> 日期：2026-08-11
> 影响范围：Axiom Core、DomainPack、Run、FiveAxisTrajectoryPack、Web Catalog

## 背景

R1 首版为了尽快证明离散点评估闭环，把 `OrderedPointSequence` 的请求和执行函数直接接入了 Core 的 `RunSpec` 路径。DomainPack 因而只能注册描述符，真正执行时仍由 Core 判断是否为有序点领域。继续沿用这一结构接入五轴，会迫使 Core 增加五轴类型和条件分支，违背“领域概念不泄漏进 Core”以及“无需改写 Core 即可接入第二个领域包”的阶段门。

五轴和有序离散点之间也不是天然等价。五轴关节向量、连续路径、采样位置视图和普通欧氏点列具有不同的单位、坐标、进度与区间语义；若靠字段形状隐式转换，会产生无法审计的能力和安全声明。

## 决策

1. DomainPack 的可序列化描述符与进程内运行时绑定分离。描述符声明 Artifact、schema、能力、指标、Claim、失败映射和策略；运行时绑定负责把领域中立请求解析为领域请求并调用 Evaluator。
2. Core 的运行路径只按 `domainPackId` 解析已注册绑定，不按有序点或五轴类型写条件分支。只有描述符而没有运行时绑定时，必须返回 `DomainPackEvaluatorUnavailable`，不能借用其他领域的 Evaluator。
3. Core 使用只要求 `artifactType` 与 `schemaVersion` 的领域中立 Artifact envelope 保存未知领域载荷；严格领域校验仍由对应运行时绑定完成。现有有序离散点请求继续作为强类型公共接口，并通过其绑定接入相同运行路径。
4. 跨领域转换必须经过版本化、静态注册的 `ArtifactAdapter`。Adapter 必须声明源/目标 Artifact 类型，保存源与结果内容标识、转换 provenance，以及明确的保留和丢弃语义。
5. 首个 FiveAxis→OrderedPoint Adapter 只接受显式标注坐标系与长度单位的 Cartesian XYZ 采样位置视图。它不得把关节向量或线性/旋转混合向量解释成欧氏点；`PathProgress` 等不能由目标类型表达的语义必须记入丢弃清单。
6. 本阶段只实现进程内静态注册，不实现动态模块发现、任意代码加载，也不提前决定 Reference Solver/SUT 的文件、子进程或 RPC 传输。后者按五轴 F4 的决策截止点处理。
7. FiveAxis F0 运行时只能验证机器契约并报告上下文/能力状态，不产生 `GeometryValid`、`ModelCollisionFree`、`KinematicallyFeasible`、`ContinuouslyFeasible`、`IntervalCertified` 等正向数学 Claim，也不产生设备安全声明。

## 被否决方案

- **在 `run.py` 中继续增加领域 ID 分支**：第二个领域能短期运行，但每个新领域都要改 Core，领域边界名存实亡。
- **把 `EvaluationRequest.artifact` 改成无约束字典**：丢失最小 Artifact 身份约束，也使内容标识和错误路径难以稳定。
- **按数组维度自动把五轴数据当点列**：五维关节坐标不等于五维欧氏位置，会把单位、坐标和区间语义错误混合。
- **现在建设动态插件或 RPC 框架**：F0 只需证明领域可外挂；传输和隔离需求尚未由实际 Solver/SUT 验证。

## 后果

- 有序离散点成为第一个使用通用绑定执行的领域包；第二个领域包可在不修改 Core 调度逻辑的情况下注册和运行。
- Core 可以保存领域 Artifact 的完整 JSON，同时保持 `artifactType/schemaVersion`、内容标识和谱系稳定；领域错误仍由各包严格解释。
- Adapter 产生新的 Artifact 和内容标识，不能冒充无损别名；比较策略只有在显式接受该 Adapter 的等价性契约时才能跨领域比较。
- 五轴 F0 可以先交付可审计的机器入口，后续 M0～M5 数值实现沿相同边界增量接入，而不会把“schema 已存在”误写为“数学结论已证明”。
