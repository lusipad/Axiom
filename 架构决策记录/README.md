# Axiom 架构决策记录

> 状态：Active  
> 更新日期：2026-08-14
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
| [ADR-0025](ADR-0025-Beckhoff见证采用控制器锁存与离线部署预检.md) | Beckhoff 见证使用控制器锁存、索引最后发布和显式 NodeId 离线预检，不引入自动 PLC 部署 | Accepted |
| [ADR-0026](ADR-0026-R7E现场证据到R5B真实holdout投影.md) | R7-E / R4.1 现场证据经确定性应用层 Adapter 进入 R5-B，保留原始哈希与安全边界 | Accepted |
| [ADR-0027](ADR-0027-R5B现场Campaign预注册与选择证据边界.md) | R5-B 真实 holdout 以采集前 Campaign/Registration 形成显式选择证据，旧自报布尔值只保留兼容重放 | Accepted |
| [ADR-0028](ADR-0028-R5C条件效应代理模型与空间Holdout边界.md) | R5-C 使用双输出条件效应代理模型和空间 holdout，保持 synthetic、现实、优化与设备权限边界分离 | Accepted |
| [ADR-0029](ADR-0029-R6V2目标驱动代理筛选与精确回放边界.md) | R6 v2 用目标与两个显式约束驱动代理筛选，最终推荐只来自预算内精确回放 | Accepted |
| [ADR-0030](ADR-0030-R6V2到R7A显式证据投影与兼容边界.md) | R6 v2 通过显式证据投影进入既有 R7-A Shadow，保持 v1 身份与零设备权限边界 | Accepted |
| [ADR-0031](ADR-0031-目标搜索到物理响应Shadow采用应用层精确重放.md) | Goal-to-Shadow 在应用层重放 exact candidate 的真实 R4 响应，并以逐样本零插值投影进入既有 R7-A 状态机 | Accepted |
| [ADR-0032](ADR-0032-R5D仿真实验价值采用顺序G最优设计.md) | R5-D 以顺序 G-optimal 设计规划下一批未观测 synthetic SIL 实验，并保持规划、执行与设备权限分离 | Accepted |
| [ADR-0033](ADR-0033-R5E离线合成实验反馈闭环与候选晋升边界.md) | R5-E 以显式批准和不可变回执闭合 synthetic plan→train→replan，不自动执行后续批次或晋升模型 | Accepted |
| [ADR-0034](ADR-0034-R5F候选模型下游影响评估与晋升隔离.md) | R5-F 在固定 R6 v2 搜索合同下评估候选下游影响，并把评估通过与模型晋升永久分离 | Accepted |
| [ADR-0035](ADR-0035-R5G晋升就绪审查包与模型激活隔离.md) | R5-G 将可重放候选证据整理为独立审查包，并保持注册、激活、默认切换与现实门开放 | Accepted |
| [ADR-0036](ADR-0036-R5H候选真实Holdout与模型晋升隔离.md) | R5-H 用采集前冻结的操作点和 R7-E/R4.1 证据验证指定候选，并把 case-scoped 现实结论与模型晋升隔离 | Accepted |
| [ADR-0037](ADR-0037-R5I本机模型生命周期与设备部署隔离.md) | R5-I 用独立签名决定和本地 SQLite 原子切换默认模型，并把本机模型生命周期与设备部署永久隔离 | Accepted |

## 生命周期规则

- `Proposed`：仍在讨论，不约束实现；
- `Accepted`：已同步进入当前规范，约束实现；
- `Superseded`：由新 ADR 替代，保留审计历史；
- `Deprecated`：决定不再适用，但没有直接替代项。

修改已接受决策时，不覆盖历史 ADR；新建 ADR 并用 `Supersedes` / `Superseded by` 互链，同时更新受影响规范。
