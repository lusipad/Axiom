# ADR-0031：目标搜索到 Synthetic Shadow 采用应用层精确物理重放

- 状态：Accepted
- 日期：2026-08-13
- 决策范围：R6 v2 用户目标、exact candidate、R4 PhysicalResponseTrace 与 R7-A synthetic Shadow 的可操作垂直接力

## 背景

ADR-0030 已解决 `RecommendationSet@2` 如何携带完整筛选与精确证据进入既有 R7-A 状态机，但内建 R7-A v2 场景仍使用独立的固定四点 `ShadowTrace`。R6 exact candidate 只保存 M4、M5 与 R4 response 内容身份，并不保存可从哈希反推出的数据。因而“候选可以入场”与“用户正在预演这个候选的实际 SIL 响应”仍是两件不同的事；若网页直接把候选 ID 与固定轨迹并列展示，会形成错误的数据谱系。

## 决策

1. 新增应用层 `GoalToShadowRequest` / `GoalToShadowReport` 与 `POST /api/v1/control/goal-to-shadow/rehearse`，不新增 DomainPack、Core 对象、指标或 Claim。
2. 请求携带完整 R6 v2 `SearchRequest` 和可选 exact candidate ID。服务端重新执行搜索；未指定候选时选择 `bestObservedCandidateIds[0]`，显式指定时只接受 exact-eligible 候选。用户选择不构成自动接受或设备授权。
3. 候选必须用 R6 v2 冻结的命名与参数协议重新执行 F3/F4/R4。重放得到的候选 M4 hash、M5 content ID 和 `PhysicalResponseTrace.contentHash` 必须逐项等于 Recommendation 中的冻结值；任一差异均 fail closed。
4. `axiom.control.physical-shadow-projection@1` 同时保存 M5、R4 response 与派生 `ShadowTrace`。M5 和 response 必须按 sample index、time 与五轴 command 完全一致；禁止插值、重排、补点或按哈希猜数据。
5. R7-A 的 `linearFollowingErrorMm` 只取每个样本 X/Y/Z 三个线性轴最大绝对跟随误差，单位固定为 mm；B/C rad 明确排除。候选级 `oodFraction` 按 `candidate-constant-per-sample` 策略投影到各样本。
6. 物理投影通过后，继续复用 ADR-0030 的 Recommendation Projection、`ControlEnvelope` 和同一个 Admission/Monitor/Stop/Rollback 状态机。Optimizer 工作台提供候选级“进入 Synthetic Shadow”动作，并以内联报告展示响应、采样、越界与永久边界。
7. 报告固定为 Windows-only、synthetic SIL。Deployment Shadow、Reality、Controlled Trial、Closed Loop 保持 Open，Device/Process Safety 保持 NotAssessed；设备写入与自动接受永久为 false。

## 后果

- 用户从目标与约束出发，可以在一个工作流里看到代理筛选、精确候选、同一候选的实际 R4 响应投影和 R7-A 运行结论。
- R6、R4、R7 的权威对象与内容身份保持独立；应用报告只是重验并编排，避免把跨阶段流程塞进 Core 或复制 DomainPack。
- 固定四点 R7-A v2 场景继续用于独立合同与反例测试，但不再被 Optimizer 的候选级入口解释为该候选的物理响应。
- 每次预演会重新计算目标搜索和选中候选的物理响应；首片不增加缓存、后台任务、历史持久化或设备连接。

## 被拒方案

- **按 `physicalResponseContentHash` 构造轨迹**：哈希是身份，不是可逆数据，会伪造来源。
- **继续复用固定四点场景作为候选轨迹**：只能验证状态机，不能证明与当前候选的 R4 response 一致。
- **把完整 PhysicalResponseTrace 塞回 RecommendationSet@2**：扩大离线推荐合同并复制精确执行数据；确定性重放和独立投影已足以闭合接力。
- **新增 Goal-to-Shadow DomainPack**：主 Artifact、指标和 Claim 没有新语义，应用编排层更符合现有 ADR-0024/0026 模式。
- **把 B/C 旋转误差合入 mm 总分**：量纲不兼容，会产生无物理意义的包线指标。
- **直接进入 Deployment Shadow 或设备**：缺少真实控制器 Observation、权限、停止/回退、安全论证和责任方授权。
