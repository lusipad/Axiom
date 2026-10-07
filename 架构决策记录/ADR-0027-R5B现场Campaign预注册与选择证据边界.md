# ADR-0027：R5-B 现场 Campaign 采用外部责任方预注册与显式选择证据

- 状态：Accepted
- 日期：2026-08-13
- 决策范围：R5-B 真实 holdout 选择时序、Campaign 身份、兼容入口与信任边界
- 细化：[ADR-0017](ADR-0017-R5B-Windows真实holdout就绪门边界.md)、[ADR-0026](ADR-0026-R7E现场证据到R5B真实holdout投影.md)

## 背景

R5-B 原有 `RealHoldoutSelectionReceipt.selectedBeforeEvaluation=true` 由 intake 调用方直接提交，且旧 intake 在已经看到现场 dossier 后才生成选择收据。该字段可以表达调用方意图，却不能证明设备、工况、任务、批次和命令身份在采集前已经冻结。若继续让它关闭 holdout 隔离门，事后挑选表现较好的 Case 也可能被包装成“独立真实 holdout”。

现场证据投影、R5-B 指标和 Core 运行语义已经存在。缺口是应用层的试验预登记与选择证据，不是新的领域对象、设备能力或安全 Claim。

## 决策

1. 在真实采集前由外部数据/试验责任方提交 `axiom.intelligence.real-holdout-campaign-registration-request@1`。注册结果分为不可变 `RealHoldoutCampaignManifest` 与独立 `RealHoldoutCampaignRegistration`，二者分别计算内容哈希。
2. Campaign Manifest 必须绑定 R5-B 基线中的 `ModelBundle`、训练数据集、holdout/selection identity、固定选择策略、`device/condition/task/batch/time` 五类隔离维度，以及每个计划 Case 的角色、拓扑、轨迹族、任务、工况、批次、设备、双运行 pair identity、calibration/validation command identity 和时间误差上限。
3. Campaign 在注册时就必须覆盖至少两个跨设备、跨工况的 in-domain slot 和至少一个 OOD probe；Case、assessment、pair、task 与 batch 等身份必须满足冻结的唯一性规则。
4. Registration 记录 `registeredAt`、外部责任方/登记机构标识、外部记录标识和版本化登记方法。首版方法固定为 `external-owner-attestation`：Axiom 验证字段完整性、内容身份和时间先后，但不把普通时间戳或内容哈希描述为可信时间戳、数字签名或物理真实性证明。
5. `axiom.intelligence.preregistered-real-holdout-intake-request@1` 必须同时携带 Manifest、Registration、治理记录、基线 RunSpec 和现场 Case。严格 intake 要求登记时间早于每个 Case 的 calibration 与 validation capture `openedAt`，并逐字段验证实际现场身份与预登记 slot 完全一致；不得事后替换设备、命令、任务、工况或角色。
6. 严格 intake 复用 `axiom.adapter.r7e-to-r5b-holdout@1` 的既有投影和治理检查，不复制 R3/R4.1/R5-B 真值。全部门通过后，生成的 `RealHoldoutSelectionReceipt` 必须标记 `selectionEvidenceStatus=PreRegistered`，并绑定 Manifest 与 Registration 两个内容身份。
7. 旧 `axiom.intelligence.real-holdout-intake-request@1`、既有模型字段和旧 selection 内容哈希保持可解析、可重放。它仍可用于投影诊断，但仅有 `selectedBeforeEvaluation=true` 不能再关闭 R5-B holdout isolation 或 real-world generalization 门；runtime 必须返回 `InsufficientContext / RealHoldoutSelectionNotPreRegistered`。
8. Campaign 注册与严格 intake 都属于应用层合同，不新增 DomainPack、不修改 Core，也不把多个主 Artifact 压成 mega-artifact。CLI、HTTP 与 R5-B 网页必须调用同一注册/验收函数并产生相同 portable 输出。
9. Registration 本身固定 `countsTowardReality=false`。只有严格 intake 通过并随后执行生成的 R5-B RunSpec，才可能在所提交 Case 范围内形成 `Observed` 级结论；所有路径继续保持 Controlled Trial、Closed Loop 为 `Open`，DeviceSafe、ProcessSafe 为 `NotAssessed`。

## 后果

- 真实 holdout 的“选择发生在评估前”由可复验 Campaign 身份和现场采集时序支撑，不再依赖一个自报布尔值。
- 现场团队必须在采集前知道计划设备、工况、任务、双运行身份和命令内容；改变计划需要新的 Campaign/Registration，而不是修改旧记录。
- 已发布的 v1 intake 与历史 selection 仍可重放，但不会被升级为新的现实正向证据。
- 如果未来需要更强的时间与责任证明，应新增签名、可信时间服务或外部注册表验证方法；不得静默改变 `external-owner-attestation` 的含义。

## 被拒绝的方案

- **继续信任 `selectedBeforeEvaluation=true`**：该值可在看到结果后填写，不能证明预先选择，拒绝。
- **从已提交 dossier 反推并封存 Campaign**：这仍是事后选择，无法关闭泄漏门，拒绝。
- **为 Campaign 新增 DomainPack 或修改 Core**：缺口属于既有现场证据与 R5-B 之间的应用层治理，不需要扩大公共语义，拒绝。
- **首版宣称密码学可信时间**：当前没有 TSA、签名密钥治理或外部注册表验证器；伪造该保证比明确的责任方信任边界更危险，拒绝。
