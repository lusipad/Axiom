# ADR-0017：R5-B 采用 Windows 真实 holdout 就绪门与 case-scoped reality exit 边界

- 状态：Accepted
- 日期：2026-08-12
- 决策范围：R5-B 真实 holdout readiness、Windows-only 平台边界、证据层级、阈值冻结、case-scoped 现实退出门

## 背景

R5-A 已经把 synthetic learning contract 闭合到一个可审计的 Windows slice，但这并不等于真实世界泛化已经闭合。真实 holdout 的问题与 synthetic 合同片不同：它要求外部采集证据、冻结的治理与许可、时间与坐标上下文、跨设备与跨工况隔离，以及只针对单个 case 的 reality exit。

如果把这一步继续包装成“更通用的语义评估器”，就会把真实 holdout、模型评分和设备安全混在一起，导致两类误读：

1. 任何可解析的输入都可能被误报为现实闭合；
2. 任何训练/回放结果都可能被误当作真实 Windows capture。

R5-B 只负责把真实 holdout 的就绪门钉死，不在仓库内伪造真实正例。

## 决策

1. R5-B 的发布与阻断验收基线是 Windows AMD64 + CPython 3.12.10；runtime 平台门只接受 Windows。非 Windows 环境必须返回结构化 `Unsupported`，不得产生正向现实闭合声明；Ubuntu、Linux、WSL 不在本 slice 的支持范围内。其他 Windows 运行环境不属于冻结验收矩阵，不能据此声明可复现发布身份。
2. `ModelBundle@1` 继续作为主 Artifact。真实 holdout 是独立上下文，不替代主 Artifact，也不把 source evidence 塞回 bundle 本体。
3. 真实 holdout 必须包含 R3 controller-export / device-read paired observation、PhysicalResponseTrace、治理与许可、选择收据、时钟上下文、坐标上下文、跨设备与跨工况标记，以及 OOD 样本。内容哈希只证明完整性，不证明物理真实性；数据所有者自证属于信任边界。
4. R5-B 使用两条不能混用的状态轴：
   - `contractReadinessStatus=Passed`：表示 Windows 输入合同、验证器和上传路径已经实现，不表示真实证据已到位；
   - `realWorldGeneralizationStatus=Open`：仓库默认态，表示没有足够的真实 holdout 证据，或提交的证据未通过 case-scoped 门；
   - `CaseScopedPassed`：只允许外部真实 holdout 通过全部门槛后产生，且范围仅限本次提交的 case 集合，不得外推为全局泛化。
5. R5-B 的阈值冻结为：
   - in-domain improvement `>= 0.20`；
   - conformal coverage `>= 0.80`；
   - OOD abstention `= 1`；
   - target parity `<= 1e-12`；
   - alignment coverage `= 1`；
   - 至少 2 组 in-domain 真实样本，覆盖 2 个 device 与 2 个 condition，并额外包含 1 组 OOD 真实样本；
   - device、condition、task、batch、time 必须冻结隔离，不能跨 split 复用连通身份组件。
6. 证据等级上限保持 `Observed`。R5-B 不得升级出 `DeviceSafe`、`ProcessSafe`、`safe-to-run`、`writeback`、`online learning` 或 `auto deployment`。

## 后果

- 仓库可以明确区分“就绪门已完成”和“现实退出门已关闭”。
- 外部真实 Windows capture 有明确的接入契约，不会被 synthetic fixture 误导。
- 文档、API 和 UI 可以只展示 readiness / Open，不会把 case-scoped 现实闭合伪装成通用结论。
- 后续如果要真正进入现实闭合，只需要补真实 capture，而不是重写 R5 的主结构。

## 被拒方案

- **把 R5-B 写成通用语义评估器**：会模糊真实 holdout 与 synthetic 合同片的边界，拒绝。
- **允许仓库内置 fixture 生成 CaseScopedPassed**：这会伪造现实闭合，拒绝。
- **把 Windows 真实 capture 解释成可跨平台通用能力**：这会越过当前阻断基线，拒绝。

## 备注

R5-B 的存在不改变 R5-A 现状：R5-A 仍然是 synthetic learning contract slice，realWorldGeneralizationStatus 仍保持 `Open`，直到外部真实 Windows holdout 真正进入 case-scoped 退出门。
