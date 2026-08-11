# ADR-0008：领域包多 Artifact 声明与单主 Artifact 运行

> 状态：Accepted
> 日期：2026-08-11
> 影响范围：Axiom Core、DomainPack、Run、FiveAxisTrajectoryPack

## 背景

ADR-0007 已把可序列化 DomainPack 描述符与运行时绑定分开，但当前描述符仍只有一个 `artifactType`。这足以承载有序离散点和 FiveAxis F0 的单一派生视图，却不能表达同一 FiveAxisTrajectoryPack 内有明确类型边界的 M0 规范化程序、M1 参考任务路径和 M2 候选任务几何。

如果把每一层注册成独立 DomainPack，领域身份和能力目录会被人为拆散；如果把所有层塞入一个无类型 payload，Core preflight、schema 版本和证书依赖将无法得到唯一结果。另一方面，让一次 Run 同时携带任意数量的主 Artifact 会扩大比较、身份和失败聚合语义，而 F1 并不需要这种复杂度。

## 决策

1. `DomainPack` 可以声明一个有序的 `ArtifactTypeDescriptor` 集合。每个描述符至少冻结 `artifactType`、允许的 `schemaVersion` 集合和领域内角色。
2. 现有 `artifactType` / `artifactSchemaVersions` 继续表示 primary descriptor，并保持既有构造与 JSON 兼容；新增集合只扩充同一包接受的有类型 Artifact。
3. 一次 `RunSpec` 和 `Observation` 仍只有一个主 Artifact。Core 只验证请求中的 `(artifactType, schemaVersion)` 是否属于已注册描述符，不理解 M0、M1、M2 或其他领域角色。
4. 层间派生由独立、不可变 Run、内容标识和 `derivedFrom` provenance 串联。参考对象、策略和上下文可以作为领域请求的有类型支持对象存在，但不能冒充第二个主 Observation。
5. DomainPack 的 metric-to-Claim 投影必须是机器可读的通用声明；Core 不按五轴 metric ID 写分支。未计算的指标只能形成 `Inconclusive` 领域 Claim，不能因声明存在而产生正向结论。
6. Artifact 类型已知但 schema 版本不支持，与 Artifact 类型本身未知是两个独立、确定的 preflight 失败。

## 被否决方案

- **每个 M 层一个 DomainPack**：无需扩展描述符，但破坏同一领域包的能力、策略和 Claim 边界。
- **一个包含 M0～M2 的无类型 mega Artifact**：代码量较少，却把类型依赖推迟到 evaluator 内部，两个实现可能得到不同 preflight 结果。
- **一次 Run 接受多个任意主 Artifact**：对 F1 非必要，并会立即扩大比较兼容性、Observation 身份和失败聚合协议。
- **在 Core 中识别 FiveAxis stage**：直接违反领域中立边界。

## 后果

- FiveAxisTrajectoryPack 可以用一个版本化描述符公开 M0、M1、M2，同时每次运行仍有清晰的单一被评对象。
- 现有 ordered-point 与 FiveAxis F0 请求继续使用 legacy primary 字段，不需要迁移。
- 新领域接入同样可以声明多个 Artifact 类型，而无需修改 Core 调度代码。
- 跨层完整性需要由 provenance 和内容身份验证；Core 不替领域推导层间等价性。
