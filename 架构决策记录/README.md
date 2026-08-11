# Axiom 架构决策记录

> 状态：Active  
> 更新日期：2026-08-11
> 规范入口：[README](../README.md)

ADR 记录会长期约束多个文档或实现、且存在实质替代方案的决定。ADR 解释选择理由和后果；当前规范正文仍是实现契约的唯一来源。

## 已接受决策

| ADR | 决策 | 状态 |
|---|---|---|
| [ADR-0001](ADR-0001-拆分执行指标与Case状态.md) | 拆分执行、指标与 Case 三条公共状态轴 | Accepted |
| [ADR-0002](ADR-0002-离散点坐标单位与路径长度语义.md) | 无物理单位时使用 `coordinate-unit`，并冻结开放/闭合长度语义 | Accepted |
| [ADR-0003](ADR-0003-五轴路径进度对应与离散重建.md) | 统一 `PathProgress`、正则性、对应策略和离散重建契约 | Accepted |
| [ADR-0004](ADR-0004-五轴碰撞与安全声明边界.md) | 在 R2 纳入模型碰撞验证，并禁止把它升级为真实设备安全声明 | Accepted |
| [ADR-0005](ADR-0005-首版Run严格比较策略.md) | 首版只比较严格兼容 Run，不通过隐式转换制造排名 | Accepted |
| [ADR-0006](ADR-0006-首个可执行Experiment与本地Runner边界.md) | 首个可执行双臂 Experiment 使用静态本地 Runner 和严格参数契约 | Accepted |
| [ADR-0007](ADR-0007-领域包运行时绑定与显式Artifact-Adapter.md) | DomainPack 描述符与运行时绑定分离，跨领域转换必须使用显式 Artifact Adapter | Accepted |
| [ADR-0008](ADR-0008-领域包多Artifact声明与单主Artifact运行.md) | 同一 DomainPack 可声明多个有类型 Artifact，但一次 Run 保持单一主 Artifact | Accepted |
| [ADR-0009](ADR-0009-F1规范化前端与连续证据边界.md) | F1 采用严格 CL 子集、连续区间证据和分层碰撞能力边界 | Accepted |
| [ADR-0010](ADR-0010-F2参考机床与运动学证据边界.md) | F2 冻结三类参考机床、通用运动链、集合值 IK 与运动学证据边界 | Accepted |
| [ADR-0011](ADR-0011-F3时间参数化与区间重建证据边界.md) | F3 冻结二阶/Jerk 时间参数化子集、重建能力矩阵与区间证据边界 | Accepted |

## 生命周期规则

- `Proposed`：仍在讨论，不约束实现；
- `Accepted`：已同步进入当前规范，约束实现；
- `Superseded`：由新 ADR 替代，保留审计历史；
- `Deprecated`：决定不再适用，但没有直接替代项。

修改已接受决策时，不覆盖历史 ADR；新建 ADR 并用 `Supersedes` / `Superseded by` 互链，同时更新受影响规范。
