# Axiom v1 重新立项入口

> 状态：Review / Proposed  
> 分支：`codex/axiom-math-foundation-v1`  
> 目的：在修改现有实现前，先冻结数学根基、产品目标、阶段门和高层架构。

## 核心判断

Axiom 当前最重要的任务，不是继续从 R5 扩展到更多学习、优化和控制能力，而是证明：

> Axiom 在数学或 Orion 中判断更好的 CNC 算法，能否在声明的真实机床和工况范围内仍然更好？

Axiom v1 因此采用“**有界声明迁移**”作为主线：

```text
理想数学
→ 数值求解
→ 固定周期命令
→ Orion / 物理模型
→ 真实 CNC
→ 测量
→ Claim–Argument–Evidence
→ 人工发布决策
```

正向结论必须满足：

\[
\text{结论裕量} > \text{组合迁移误差和风险}
\]

否则输出 `Inconclusive` 或 `MoreEvidenceRequired`。

## 阅读顺序

1. [Axiom 数学基础 v1.0](Axiom%20数学基础%20v1.0.md)  
   定义混合系统、Trace 空间、可信度证书、11 个定理/命题、32 项 Proof Obligations 和反例库。
2. [Axiom v1.0 项目规划](Axiom%20v1.0%20项目规划.md)  
   定义唯一产品纵切、G0–G7 阶段门、52–63 周路线、Reference Cell、风险与停止规则。
3. [Axiom v1.0 高层架构设计](Axiom%20v1.0%20高层架构设计.md)  
   定义多 Trace Evidence Kernel、九个 Bounded Context、运行时部署、插件边界和 v0.22 迁移策略。
4. [ADR-0027：Axiom v1 以有界声明迁移重新立项](架构决策记录/ADR-0027-Axiom-v1以有界声明迁移重新立项.md)  
   记录为何调整路线、保留什么、冻结什么，以及接受该决定所需的条件。

## Axiom 1.0 唯一纵切

首个正式产品闭环是：

> 在相同路径、机器约束和固定周期下，比较两个 Jerk 受限进给规划或插补算法版本，并连接 Independent Reference、SUT、Orion 和真实 Reference Cell 的证据。

首个现实闭环优先使用三线性轴机床，已有 FiveAxis F1–F4 作为高级领域包保留和迁移。

## 需要项目 Owner 决定的五件事

1. 是否接受 Axiom v1 的收缩产品定义；
2. 第一组算法 A/B 是什么；
3. 第一台 Reference Cell 是什么；
4. 是否将当前 R5–R7 主线冻结为 Experimental；
5. P0 阶段可投入的人员、设备和计量资源。

在这五项决定之前，本分支只建立理论和规划，不修改现有运行代码，不把 ADR-0027 标记为 Accepted。
