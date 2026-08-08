# ADR-0001：拆分执行、指标与 Case 状态

> 状态：Accepted  
> 日期：2026-08-08  
> 影响：[通用评估框架规范](../Axiom%20通用评估框架规范.md)、[有序离散点领域包规范](../有序离散点领域包规范.md)

## 背景

原契约把 `UnsupportedCapability` 放在 Run 状态，却允许单项指标返回 `NotApplicable`，没有唯一说明“实现未支持”“输入上下文缺失”“数学上不适用”和“执行失败”的边界。两个实现可能对同一输入给出不同层级的状态。

## 决策

采用三条正交公共状态轴：

- `ExecutionStatus` 只描述 Runner/Subject 生命周期；
- `MetricStatus` 只描述单项指标是否得到可信结果及未得到的原因；
- `CaseOutcome` 只描述整个 EvaluationCase 的最终可判定结论。

每个 MetricDefinition 必须声明版本化能力依赖；Case 必须区分必选和可选指标。聚合优先级固定为：`Invalid`；否则已判定硬失败为 `Failed`；否则依次为 `Unsupported`、`Inconclusive`、`Passed`。可选指标不改变 CaseOutcome。

需要执行的 Case 还必须绑定版本化 `executionOutcomePolicy`。默认策略把 Subject/输出契约/Case 限额失败映射为 `Failed`，把 Runner/环境失败和用户取消映射为 `Inconclusive`；运行中状态不得提前写最终 CaseOutcome。

## 被拒绝的方案

- 单一 Run 状态枚举：无法同时表达“执行成功但某指标不支持”。
- 用 `NotApplicable` 覆盖所有无结果：混淆数学定义域、缺上下文和实现能力。
- 由每个领域自行定义聚合：跨领域比较和重放会失去确定性。

## 后果

- 数据模型会多两个显式状态字段，但每个字段的责任更窄；
- 旧的 `InvalidInput`、`UnsupportedCapability`、`EvaluationFailed` 不再作为 ExecutionStatus；
- 领域失败码仍保留，但必须映射到三条公共状态轴；
- 报告和测试必须分别断言三条状态，不能只断言“Run 成功/失败”。
- 执行失败、取消和跳过必须保存原因码，不能让实现自行决定 CaseOutcome。

## 一致性检查

同一 Artifact、Case、Profile、能力清单和策略版本交给两个符合规范的实现，三条状态轴必须一致。缺能力测试至少覆盖 `NotApplicable`、`InsufficientContext`、`UnsupportedCapability`、`InvalidObservation` 和 `NumericalFailure`。
