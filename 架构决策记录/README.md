# Axiom 架构决策记录

> 状态：Active  
> 更新日期：2026-08-13
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
| [ADR-0012](ADR-0012-v0.7-Windows确定性发布基线.md) | v0.7 以 Windows 3.12.10 与固定 BLAS 策略作为唯一发布阻断基线 | Accepted |
| [ADR-0013](ADR-0013-F4进程内验收与完整数学门禁.md) | F4 使用进程内双实现、M5 时间区间碰撞和完整 7 Claim 数学门禁 | Accepted |
| [ADR-0014](ADR-0014-R3-Windows只读设备观测与谱系边界.md) | R3 使用 Windows 文件回放冻结只读设备观测、谱系与零写入边界 | Accepted |
| [ADR-0015](ADR-0015-R4轴空间物理模型与SIL可信度边界.md) | R4 使用轴空间物理响应 Artifact，并把 synthetic SIL 与真实设备可信度严格分开 | Accepted |
| [ADR-0016](ADR-0016-R5可审计数据集与端侧模型边界.md) | R5 使用可审计数据集快照、split/governance/lineage 和 Windows-only 端侧模型边界 | Accepted |
| [ADR-0017](ADR-0017-R5B-Windows真实holdout就绪门边界.md) | R5-B 使用 Windows 真实 holdout 就绪门、case-scoped reality exit 和外部真实 capture 边界 | Accepted |
| [ADR-0018](ADR-0018-R6多目标离线推荐与权限边界.md) | R6 使用无权重多目标 Offline Recommendation，并保持零设备写入与零自动接受 | Accepted |
| [ADR-0019](ADR-0019-R7A-Shadow受控运行与设备安全边界.md) | R7-A 先闭合 Windows Synthetic Shadow 合同，并保持真实设备写入、受控试验和安全声明为 Open | Accepted |
| [ADR-0020](ADR-0020-R7B-部署影子就绪性与厂商边界.md) | R7-B 先冻结厂商无关的只读部署证据门，不在目标控制器未选时伪造厂商 Adapter | Accepted |
| [ADR-0021](ADR-0021-R7C-Windows虚拟OPC-UA传输验收边界.md) | R7-C 使用隔离的官方 .NET 栈闭合 Windows 虚拟 OPC UA 只读传输合同，厂商与现实门保持 Open | Accepted |
| [ADR-0022](ADR-0022-R7D-Beckhoff-TwinCAT厂商验收边界.md) | R7-D 锁定 Beckhoff TwinCAT 3 / TF6100 厂商验收链，并把 Profile、运行时、现实与安全 gate 分开 | Accepted |
| [ADR-0023](ADR-0023-R7E样本索引采集与R41双运行现实门.md) | R7-E 用样本索引触发七节点只读采集，R4.1 用独立 calibration/holdout 双运行关闭 case-scoped 现实门 | Accepted |
| [ADR-0024](ADR-0024-现场证据采用应用层双运行编排.md) | 现场验收在应用层编排两个 R7-E 与既有 R4.1，不新增重复的 R7-F DomainPack 或安全 Claim | Accepted |

## 生命周期规则

- `Proposed`：仍在讨论，不约束实现；
- `Accepted`：已同步进入当前规范，约束实现；
- `Superseded`：由新 ADR 替代，保留审计历史；
- `Deprecated`：决定不再适用，但没有直接替代项。

修改已接受决策时，不覆盖历史 ADR；新建 ADR 并用 `Supersedes` / `Superseded by` 互链，同时更新受影响规范。
