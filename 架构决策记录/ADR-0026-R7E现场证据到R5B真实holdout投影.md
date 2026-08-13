# ADR-0026：R7-E 现场证据通过应用层 Adapter 投影为 R5-B 真实 holdout

- 状态：Accepted
- 日期：2026-08-13
- 决策范围：R7-E / R4.1 现场证据进入 R5-B 真实 holdout

## 背景

R7-E 与 R4.1 已能对一个现场 dossier 的 calibration/validation 双运行形成可审计报告，R5-B 也已经冻结 `RealPairedHoldoutSet`。两者之间仍缺少确定性的机器合同：现场报告中的 Shadow 轴样本、R4.1 仿真序列、设备上下文和 F4 谱系不能靠人工复制进 R5-B，否则会丢失原始时间戳、内容身份或数据隔离边界。

这个缺口属于既有领域对象之间的组合，不是新的算法层或运行时领域。为它新增 DomainPack、扩展 Core，或把多个运行压成一个 mega-artifact，都会重复 R3、R4.1 和 R5-B 已冻结的职责。

## 决策

1. 使用版本化应用层 Adapter `axiom.adapter.r7e-to-r5b-holdout@1`。输入是一个或多个不可变 `FieldEvidenceAssessmentReport` 加显式的 `DeviceProfile`、`ClockMapping`、`CoordinateAlignment`、`MachineRunLineage`、轴通道绑定、Case 元数据和外部治理记录；输出是现有 `RealPairedHoldoutSet` 及嵌入它的 R5-B `RunSpec`。不新增 DomainPack，不修改 Core。
2. 每个现场 dossier 只投影 validation 运行。calibration 运行继续作为上游 R4.1 模型识别证据，不得再次作为 holdout Case 使用。只有现场报告、其 validation Reality 分析和 validation Shadow evidence 都通过原门禁时，才可投影该 Case。
3. Shadow 的 X/Y/Z/B/C 数值、单位、quality 与顺序原样进入 R3 `MachineTelemetryTrace`。R3 单一 `deviceTimestamp` 使用冻结策略 `axiom.r7e.x-source-timestamp@1`：取同帧 X 轴 `sourceTimestamp`；五轴各自的 source/server timestamp、协议序号、通知索引、读回索引和 host timestamp 全部保存在 `vendorMetadata.sourceFrameBindings`，不得静默平均、插值或丢弃。
4. 导入后的 `captureReceipt.operation` 保持 `file-import`，因为 Axiom 消费的是已封存 dossier 文件；`sourceKind` 保持 `device-read`，表示数据的原始事实来源。`traceContentHash` 按 R3 规则对新生成的完整 `MachineTelemetryTrace`（排除自引用字段）重新计算；原始 validation Shadow evidence 的内容哈希作为独立来源身份保存在 vendor metadata 和 `RealHoldoutProjectionReceipt` 中。新生成的 Observation、PhysicalResponseTrace 和 CaseEvidence 分别生成自己的内容哈希，收据同时记录源与目标身份。
5. R4.1 validation 分析中的五轴 command/simulation 公共时间网格投影为现有 `PhysicalResponseTrace`。任何轴顺序、单位、时间网格、长度、设备身份、controller family 或 command lineage 不一致都使投影 `Blocked`，不做猜测或隐式转换。
6. 一个可输出的 intake 至少包含三个相互独立 Case：两个 in-domain Case 必须跨至少两个设备和两个 condition，另有至少一个 OOD probe；报告哈希和 validation Shadow evidence 哈希不得复用，capture 窗口不得重叠，且 selection 必须在 evaluation 前冻结。覆盖不足为 `Open`，身份、投影、治理或隔离违反为 `Blocked`。
7. `intakeStatus=Passed` 与 `countsTowardReality=true` 只表示该证据集有资格进入 R5-B 真实 holdout 评估，不表示 R5-B 指标已经通过，更不表示真实世界泛化 Claim 已得到支持。真正的 case-scoped 结论只能由生成的 R5-B RunSpec 经公共运行接口评估后给出。
8. intake 报告永久保持 `controlledTrialStatus=Open`、`closedLoopStatus=Open`、`deviceSafetyStatus=NotAssessed` 和 `processSafetyStatus=NotAssessed`。Adapter 不连接设备、不写设备、不部署模型、不自动接受参数，也不发布 DeviceSafe、ProcessSafe 或 safe-to-run。
9. 仓库不内置伪造的正向真实 capture。Python、CLI、HTTP 和网页只处理用户在 Windows 环境提交的外部封存文件，并对同一输入产生相同报告哈希。

## 后果

- R7-E/R4.1 到 R5-B 的证据链可以自动重放，并保留原始现场哈希、时间戳和谱系。
- R5-B 继续只负责 holdout 指标和 case-scoped Claim；上游现场门、设备上下文和治理失败不会被下游覆盖。
- 现场操作者仍需提供设备 profile、时钟/坐标标定、F4 数学谱系和数据所有者治理记录；Adapter 不推断这些事实。
- 单一 R3 时间戳字段的投影策略已经显式版本化。未来若采用控制器公共锁存时间或更强的时钟模型，应新增 Adapter/策略版本，不得改写既有报告含义。

## 被拒绝的方案

- 新增 R7-F DomainPack：这只是应用层组合，新增领域会复制 R3、R4.1 与 R5-B 的真值。
- 修改 Core 以运行并保存多个主 Artifact：现有 typed support 与应用层报告足以闭合，不需要扩大公共语义。
- 直接把 `FieldEvidenceAssessmentReport` 当作 R5-B Case：它不满足 R5-B 已冻结的 Observation、PhysicalResponseTrace、治理与隔离合同。
- 用 host timestamp 或五轴时间戳平均值填充 R3 `deviceTimestamp`：会引入未声明的时间变换，且无法逐值追溯。
- 将 intake `Passed` 解释为真实世界泛化或设备安全通过：绕过了 R5-B 指标、受控试验和执行安全链。
