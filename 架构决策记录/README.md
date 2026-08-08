# Axiom 架构决策记录

> 状态：Active  
> 更新日期：2026-08-08  
> 规范入口：[README](../README.md)

ADR 记录会长期约束多个文档或实现、且存在实质替代方案的决定。ADR 解释选择理由和后果；当前规范正文仍是实现契约的唯一来源。

## 已接受决策

| ADR | 决策 | 状态 |
|---|---|---|
| [ADR-0001](ADR-0001-拆分执行指标与Case状态.md) | 拆分执行、指标与 Case 三条公共状态轴 | Accepted |
| [ADR-0002](ADR-0002-离散点坐标单位与路径长度语义.md) | 无物理单位时使用 `coordinate-unit`，并冻结开放/闭合长度语义 | Accepted |
| [ADR-0003](ADR-0003-五轴路径进度对应与离散重建.md) | 统一 `PathProgress`、正则性、对应策略和离散重建契约 | Accepted |
| [ADR-0004](ADR-0004-五轴碰撞与安全声明边界.md) | 在 R2 纳入模型碰撞验证，并禁止把它升级为真实设备安全声明 | Accepted |

## 生命周期规则

- `Proposed`：仍在讨论，不约束实现；
- `Accepted`：已同步进入当前规范，约束实现；
- `Superseded`：由新 ADR 替代，保留审计历史；
- `Deprecated`：决定不再适用，但没有直接替代项。

修改已接受决策时，不覆盖历史 ADR；新建 ADR 并用 `Supersedes` / `Superseded by` 互链，同时更新受影响规范。
