# ADR-0036：R5-H 候选真实 Holdout 与模型晋升隔离

- 状态：Accepted
- 日期：2026-08-14
- 决策范围：R5-G 候选现实证伪、采集前操作点登记、R7-E/R4.1 标签派生、模型晋升边界

## 背景

R5-G 已把 R5-E/R5-F 候选证据整理为可提交独立审查的 dossier，但其真实 holdout gate 仍为 Open。既有 R5-B 评估的是 R5-A 的逐样本残差 `ModelBundle`；待审查候选则是 R5-C/R5-E 的双输出 `ConditionalEffectModelBundle`。两者的模型族、特征、目标和谱系不同，因此 R5-B 的结论不能证明 R5-G 候选在真实现场仍成立。

与此同时，R5-C 的两个训练目标并不具备相同现实含义。`cycleTimeSeconds` 来自 M4 计划时长，而 `linearFollowingErrorMaxMm` 可以从 R7-E/R4.1 validation 的 X/Y/Z command-observation 序列按同定义重算。若把两者都称作真实标签，或让客户端提交裸评分值，会扩大证据含义并失去可重放性。

## 决策

1. 新增 Windows-only R5-H 应用层合同，专门验证 R5-G dossier 中唯一的 baseline/candidate 条件效应模型；不修改或复用 R5-B 的模型结论，不新增 DomainPack 或 Core 状态。
2. 研究必须在任何 validation capture 前预登记至少三个 Case：两个 `in-domain` Case 跨两个设备和两个工况，另含一个 `ood-probe`。登记冻结操作点、角色、设备/工况、严格零退化与 100% interval coverage 阈值以及候选/基线身份。
3. 服务端按冻结 R4 协议重算每个操作点，并把完整 M5、M4/M5 内容身份、精确时长、样本数和数值环境封入 Manifest。客户端不得提交自报的命令身份或预测结果。
4. 评估只接受完整 `FieldEvidenceAssessmentReport`。HTTP 输入把 dossier、Registration report 与现场报告视为 canonical JSON artifact，服务端恢复完整类型并重验全部嵌套哈希；M5 中的 IEEE-754 `-0` 必须以 `-0.0` 保留。服务端重放 R5-G、R4 和 R7-E/R4.1，要求报告按 Manifest 顺序排列，并逐项绑定 Case、assessment、设备、采样周期和 validation M5；Registration 必须严格早于 capture。
5. 周期头使用 exact M4 计划时长，标记 `exact-planner` 且不计入现实证据。线性误差头从 X/Y/Z 计算 `max(abs(command-observation))`，标记 `controller-live-read` 并计入 case-scoped reality；B/C 旋转轴不得混入毫米标签。
6. 只用 `in-domain` Case 汇总 baseline/candidate RMSE 与 candidate interval coverage。预登记的 `ood-probe` 只承担设备/工况语境边界诊断，不声称 R5-C 能检测其未建模的设备域外特征。
7. 缺证据为 `Open`，谱系、顺序、时序、命令或 R4.1 reality 不一致为 `Blocked`，任一目标不满足预登记非劣性/coverage 为 `Refuted`，全部通过才产生 `CaseScopedPassed`。
8. `CaseScopedPassed` 仅限提交 Case，仍固定等待独立人工决定，且不执行模型注册、晋升、激活、默认切换、部署或设备写入。仓库不得打包真实正例；测试构造的现场报告不能作为发布证据。

## 后果

- R5-G 候选第一次拥有与自身模型族和目标定义一致、可重放、可证伪的真实 holdout 路径。
- 周期的精确软件证据与线性误差的真实现场证据不会被合成一个含义不明的现实总分。
- 外部责任方仍负责登记时间、设备工况语义和物理真实性；`external-owner-attestation` 不是可信时间戳或数字签名。
- 真正晋升仍需后续独立实现 PromotionDecision、授权主体、持久化 registry、激活读回、可执行回滚和运行监控。

## 被拒方案

- **直接用 R5-B 结果关闭 R5-G 真实门**：R5-B 评估的是不同模型族和目标，无法绑定待晋升候选。
- **让现场人员上传 actual/RMSE/Passed 数值**：无法重放标签定义，也无法阻止结果后选择和状态伪造。
- **把 M4 计划周期称为真实设备完成周期**：当前证据没有加工完成事件或独立周期测量。
- **把周期与线性误差合成一个加权总分**：会混合单位、证据等级和失败原因。
- **R5-H 通过后自动注册或激活模型**：当前没有授权、持久化、读回、回滚和监控合同。
