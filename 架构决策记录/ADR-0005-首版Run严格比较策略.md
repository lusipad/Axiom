# ADR-0005：首版 Run 严格比较策略

> 状态：Accepted
> 日期：2026-08-08
> 影响：[Axiom 通用评估框架规范](../Axiom%20通用评估框架规范.md)、[有序离散点领域包规范](../有序离散点领域包规范.md)

## 背景

R0 要求两个兼容 Run 可比较，但“兼容”若只检查指标名称，会把不同 Case、单位、坐标系、参考绑定或指标版本的结果放进同一排名。另一种极端是要求执行器版本和机器环境逐字相同，这又会阻断有审计信息的回归比较。

## 决策

首个有序离散点比较策略使用版本化 ID `ordered-point.run-comparison.strict@1`。比较分两步：先验证 DomainPack、Runner、Artifact 语义、Case/Profile/ReferenceBinding、执行策略、指标定义和结果单位；只有没有兼容性 `error` 时，才生成逐指标或综合分数差值。

Evaluator 版本、数值类型和数值环境差异作为 `finding` 保存，不自动禁止比较。不兼容报告必须指出字段和值，不得输出差值、优胜 Subject 或强制排序。原始 Run 和 Observation 保持不可变，比较结果是独立派生物。

内容身份继续区分输入中的“未提供”和“明确未知”。比较身份只规范化规范已声明为等价的 Case/Profile 默认项，不能借规范化抹去 Artifact 输入事实。

## 被拒绝的方案

- 只按 Metric ID 对齐后直接相减：会把不同定义、单位或参考上下文伪装成可比结果。
- 首版自动做单位、坐标系或 schema 转换：Adapter 的适用条件和证据尚未冻结，隐式转换不可审计。
- 版本或数值环境不同就一律拒绝：无法支持跨环境回归；保存 finding 后可由上层策略决定是否升级门槛。
- 不保存原始 Run，只输出一张差值表：破坏追溯，无法复核兼容性判定。

## 后果

- 首版能力较保守，但不会为产生排名而猜测语义；
- 后续若支持单位或坐标系等价转换，必须新增带版本的比较策略和显式 Adapter；
- `compatible = true` 只表示上下文可直接比较，不表示任一 Case 通过；
- 比较器必须保持确定性，并把策略 ID、双方 Run 内容标识、冲突和 finding 纳入报告内容身份。

## 一致性检查

同一 Case 下的 CNC 名义轮廓 A/B 样本应输出逐指标 `left/right/delta/direction`；改变 Case hash、Profile、ReferenceBinding、schema、单位、坐标系或 MetricDefinition 后，报告必须为不兼容且不含差值。仅改变记录的 evaluator 版本或数值环境时，报告仍可兼容，但必须出现 finding。
