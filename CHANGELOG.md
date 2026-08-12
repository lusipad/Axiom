# Changelog

本文件记录 Axiom 的用户可见变化。版本遵循语义化版本。

## 0.14.0 - 2026-08-12

### Added

- 增加 Windows-only R7-A Synthetic Shadow Contract：`control.domain-pack@1`、独立 `AcceptanceRecord`、控制包线、fail-closed admission、状态迁移、停止 receipt、基线保留 receipt 与公共 Run 重放验收。
- 增加 nominal、包线越界、缺 deployment evidence、Controlled Trial 越权和设备写请求五个确定性场景；全部场景均保持 `deviceWriteAllowed=false` 和 `deviceWritePerformed=false`。
- 增加 Controlled Runtime R7-A 网页工作台、manifest/scenario/example/replay API，以及 ADR-0019。

### Changed

- R6 Recommendation 继续保持 Offline 且不可变；R7-A 用独立处置记录绑定候选、证据快照、责任主体和 Shadow 权限，不把推荐本身改写成执行许可。
- 阶段状态拆为 `syntheticShadowContractStatus=Passed` 与 `deploymentShadowStatus=Open`，标准符合性保持 `NotAssessed`。

### Verification

- Windows AMD64 / CPython 3.12.10 全量验证通过：Python `644 passed`，网页 `32 passed`，TypeScript 检查与生产构建通过。
- 干净构建并安装的 `0.14.0` wheel 只包含当前一对 JS/CSS 与完整 `axiom/control`；R7-A RunBundle 完整性、内容身份篡改、非 Windows 结构化 Unsupported、越界停止路径、基线保留和 OpenAPI 响应契约均已验证。

### Boundary

- R7-A 只重放 synthetic shadow，不连接设备、不发出 stop/write 命令，也不验证设备 acknowledgment/readback；其 rollback 只证明离线基线未被修改。
- 真实 deployment Shadow、Controlled Trial、Closed Loop、厂商协议、功能安全评估与标准符合性仍未实现；本版本不形成设备安全或工艺安全声明。

## 0.13.0 - 2026-08-12

### Added

- 增加 Windows-only R6 Offline Recommendation：`optimization.domain-pack@1`、两参数六点确定性搜索、三目标无权重 Pareto、RecommendationSet 内容身份和公共 Run 重放验收。
- 增加 R4 多采样率适用性证据，用结构不同的双滞后 oracle 独立覆盖 `0.04s` / `0.08s`；物理仿真现在拒绝超出模型声明适用范围的采样周期。
- 增加 Optimization R6 Lab、manifest/scenario/example/search API、目标上限输入、候选矩阵、七数学硬门、OOD 注记和验证/回滚计划。
- 增加[受约束优化与安全闭环规范](受约束优化与安全闭环规范.md)与 ADR-0018。

### Changed

- `feedOverride` 通过按 `f/f²/f³` 降额运动约束后重新规划 M4，不再通过缩放旧时间戳伪造新证书。
- R5 模型只承担 OOD 注记与晋级阻断；首版物理目标来自 R4 模型响应，秒、毫米和样本数不相加。

### Verification

- Windows AMD64 / CPython 3.12.10 发布环境全量验证通过：Python `625 passed`，网页 `29 passed`，TypeScript 检查与生产构建通过。
- 安装后的 `0.13.0` wheel 在固定数值环境中重放 6 个候选与 6 个 Pareto 候选，R6 内容身份和公共 Run 完整性 smoke 通过。

### Boundary

- 所有 Recommendation 固定为 `Offline`，`deviceWriteAllowed=false`、`automaticAcceptanceAllowed=false`、`promotionEligible=false`。
- `realityValidationStatus` 与 `realWorldGeneralizationStatus` 继续保持 Open；本版本不实现 Ubuntu/Linux/WSL、Shadow、Controlled Trial、Closed Loop、DeviceSafe 或 ProcessSafe。

## 0.12.0 - 2026-08-12

### Added

- 增加 Windows-only R5-B real holdout readiness 合同：`intelligence.domain-pack@2`、`RealPairedHoldoutSet`、`RealHoldoutGovernance`、`RealHoldoutSelectionReceipt`、case-scoped `RealHoldoutCaseEvidence`，以及外部真实 holdout 的治理、选择和证据输入边界。
- 增加 R5-B manifest / scenarios / example API 与网页工作台入口；默认示例只提供 `real-holdout-readiness-open` 就绪场景，不内置 bundled real capture，也不伪造真实正例。
- 增加 R5-B 的程序化就绪门：Windows 上对缺失 real holdout 返回 `Succeeded + Inconclusive + RealPairedHoldoutMissing`，非 Windows 继续返回 `Skipped + UnsupportedRuntimePlatform`。

### Changed

- R5 从单一 synthetic learning 合同扩展为 `R5-A` / `R5-B` 两层：`R5-A` 继续冻结合成学习合同，`realWorldGeneralizationStatus` 仍保持 Open；`R5-B` 只负责把真实 holdout 的就绪门拆开，不把“可以接外部真实数据”误写成“真实泛化已经通过”。
- 文档入口、蓝图与快速开始都改为公开 R5-B 就绪门、上传入口和 Windows-only 支持边界；网页实验室列表现在包含 Intelligence R5-B。

### Verification

- 本次发布笔记已同步 README、蓝图和 Changelog 的版本标识、R5-B 路径与支持边界。
- R5-B 的接口和默认示例与现有 Windows 测试预期保持一致：`/api/v1/intelligence/r5b/manifest`、`/api/v1/intelligence/r5b/scenarios`、`/api/v1/examples/intelligence-r5b`、`POST /api/v1/runs/evaluate`。

### Boundary

- 仓库不内置真实 holdout 正例；R5-B 只提供就绪门、验证器和上传入口，不能把 `realWorldGeneralizationStatus=Open` 解释成已经完成现实泛化。
- 仍不支持 Ubuntu/Linux/WSL；R5-Runtime 在非 Windows 上继续返回结构化 Unsupported。

## 0.11.0 - 2026-08-12

### Added

- 增加 Windows-only R5-A synthetic learning 合同：不可变 `DatasetSnapshot`、按 trajectory/task/device-batch/pair/time 隔离的 split manifest、数据许可/保留治理和逐样本上游内容身份。
- 增加 X-only ridge residual head、训练域 envelope OOD 弃权、split conformal 区间，以及 15 位权重导出的 JSON `ModelBundle` 与独立纯 Python 目标解释器。
- 增加 `intelligence.domain-pack@1`、有类型 manifest/scenario/example API、Intelligence R5-A 工作台，以及 group leak、时间逆序、bundle 篡改和 parity 篡改四类反例。
- 增加[数据集与学习模型规范](数据集与学习模型规范.md)与 ADR-0016，冻结 R5-A 的数据、学习、目标端和安全声明边界。

### Changed

- 发布矩阵继续只包含 Windows AMD64 + CPython 3.12.10；R5 runtime 在非 Windows 环境返回 `Skipped + UnsupportedRuntimePlatform`。
- R5 阶段拆为 `syntheticLearningContractStatus=Passed` 与 `realWorldGeneralizationStatus=Open`，合成学习合同不再被包装成真实跨设备泛化。
- 反例页面只展示预期 `Skipped / Invalid` 与零正向 Claim，不再继承基准场景的通过分数和 Evidence。

### Verification

- 本地 Windows 全量验证：Python `592 passed / 1 skipped`，网页 `22 passed`，TypeScript 检查、生产构建和本次差异内 Python 静态检查通过。
- R5-A 定向 Python/API 验收 `23 passed`；固定结果为 X 轴 RMSE 改善 `50.43%`、OOD 检出率 `100%`、conformal coverage `83.33%`、目标解释器最大差 `1.39e-17`。
- 三档响应式网页实测通过，结构化视觉终审 `95/100`，无控制台错误、无设备写入或在线学习控件。
- 发布工作流会在冻结的 Windows 3.12.10 环境中重跑全量测试，并对安装后的 wheel 执行 CLI/API/UI 与 R5-A 内容身份 smoke。

### Boundary

- R5-A 的全部训练/验证/测试数据仍来自 synthetic SIL；没有真实 paired controller/device holdout，因此不能声明现实验证、跨设备/工况泛化或控制器兼容。
- Y/Z 轴保持 `NoValidatedImprovement`，B/C 轴保持 `InsufficientExcitation`；不把不同轴或 `mm/rad` 混成统一总分。
- 本版本不实现 Ubuntu/Linux/WSL、设备写回、在线学习、自动部署、`DeviceSafe`、`ProcessSafe`、`safe-to-run` 或上机许可。

## 0.10.1 - 2026-08-12

### Fixed

- R4 场景、sealed runtime 与网页示例现在由同一个 `PhysicalValidationAnalysis` 事实源生成；`analysisContentHash` 不再引用场景侧的第二套预计算结果。
- R4 manifest、场景目录和示例接口现在使用有类型的 FastAPI response model，并在 OpenAPI 中发布稳定响应契约。
- R4 runtime 现在执行 Windows-only 平台门禁；非 Windows 环境返回 `Skipped + Unsupported` 和 `UnsupportedRuntimePlatform`，不再形成误导性的 `Passed`。

### Verification

- [Windows 发布工作流](https://github.com/lusipad/Axiom/actions/runs/31562511858)在 `windows-latest + CPython 3.12.10` 上通过：Python `570 passed`、网页 `20 passed`、构建、wheel 安装后 CLI/API/UI smoke 与 GitHub Release 均成功。
- `v0.10.1` 已发布到 [GitHub Releases](https://github.com/lusipad/Axiom/releases/tag/v0.10.1)。

### Boundary

- 本补丁不增加 Ubuntu/Linux/WSL 支持；R4 reality validation 仍为 `Open`，并继续禁止 `DeviceSafe`、`ProcessSafe`、`safe-to-run` 和上机许可。

## 0.10.0 - 2026-08-12

### Added

- 增加 R4.0 Windows synthetic SIL 物理模型验证链：`five-axis.domain-pack@6`、轴空间一阶 lag + bias、exact-ZOH 仿真响应、确定性校准、独立 holdout 和残差分解。
- 增加与候选模型结构不同的两级滞后 synthetic oracle，以及模型 mismatch、时间错位、校准/验证泄漏、轴激励不足和缺坐标上下文等可证伪场景。
- 增加 `PhysicalResponseTrace`、有类型的模型/标定/对齐支持对象、R4 manifest/scenario/example API 和 Physical R4 网页工作台。
- 增加[物理模型与现实对齐规范](物理模型与现实对齐规范.md)与 ADR-0015，冻结主 Artifact、单位隔离、校准/验证隔离和可信度边界。

### Changed

- 同一 R4 Case 现在可同时追溯 F4 数学指令、模型仿真响应和 R3-compatible raw observation；三类对象保留独立内容身份，R3 raw frame 不被派生值覆盖。
- Windows 发布包纳入 R4 package fixtures 与网页资源，并在安装后重放正向 SIL Case 和反例。
- Roadmap 明确区分 `syntheticContractStatus` 与 `realityValidationStatus`；R4.0 合同片通过不等于真实设备 reality gate 关闭。

### Verification

- 本地 Windows 候选验证为 Python 全量 `567 passed / 1 skipped`，R4 定向测试 `36 passed`，网页 `20 passed`，TypeScript 检查与生产构建通过。
- `python -m build` 产出的 wheel 已包含 R4 package fixtures 与 Physical R4 workbench 静态资源；安装后 smoke 覆盖 F4、R3 与 R4 回放，结果通过。
- Physical R4 workbench 视觉终审 `92/100`，桌面与窄屏视口均无横向溢出，且页面不暴露设备写控件。
- 本地安装后 smoke 运行于 Windows + Python 3.14；阻断验收与 GitHub Release 仍以 `windows-latest + CPython 3.12.10` 工作流为准。

### Boundary

- 本版本只支持 Windows AMD64 + CPython 3.12.10 的阻断验收，不实现或验证 Ubuntu/Linux/WSL。
- 所有内置 R4 telemetry 均为 `synthetic-replay`。它们能证明 SIL 合同、确定性和可证伪性，不能证明真实控制器兼容、真实设备效果或加工安全。
- R4.0 不写设备、不应用参数、不启动加工，也不产生 `DeviceSafe`、`ProcessSafe`、`safe-to-run` 或上机许可。

## 0.9.0 - 2026-08-12

### Added

- 增加 R3 Windows 只读设备观测参考链：`machine-observation.domain-pack@1`、`machine.telemetry-trace`、`machine-trace-import@1` 和 `axiom.windows-file-telemetry-source@1`。
- 增加有类型的 `DeviceProfile`、`ClockMapping`、`CoordinateAlignment` 与 paired/unpaired `MachineRunLineage`；Profile 冻结设备/导出身份和只读 operation，对齐对象冻结方法、来源、适用时间和标定上下文。
- 增加五类最高为 `Observed` 的数据可信性 Claim，以及配对通过、未配对通过、缺时钟、序列 gap 和禁止写操作五个确定性场景。
- 增加 R3 manifest/scenario/example API、统一 CLI 回放和 Machine Read-only Lab；页面分开展示 raw trace、派生对齐、谱系、Metric、Claim 与 Evidence。

### Changed

- `DomainPack` 新增通用 `importRunnerIds`，让非内建导入 Runner 也能把 Observation 来源稳定记录为 `ImportedArtifact`，同时保留 `artifact-import@1` 的既有兼容语义。
- `Provenance` 新增可选 `contextHashes`，用于独立冻结不属于主 Artifact 的 Profile、对齐和谱系对象；未使用该能力的旧领域内容身份不变。
- Roadmap 的 R3 v1 参考门切换为已闭合，下一工作面为 R4 物理模型与现实对齐。

### Verification

- R3 Python、CLI、HTTP 与网页端消费同一 RunSpec 和场景数据；重复回放会重验 trace、支持对象与 RunBundle 内容身份。
- Windows 发布构建包含 R3 package fixtures 和 Machine Lab 静态资源，并在安装后重跑 paired 与禁止写操作 smoke。
- 本地 Windows 候选验证为 Python 全量 `531 passed / 1 environment-bound skip`、网页 `16 passed`、TypeScript 与生产构建通过；安装后 wheel smoke 通过，视觉终审 `93/100`，依赖审计未发现已知漏洞。

### Boundary

- 本版本只支持 Windows 已落盘 JSON capture，不连接真实控制器、不轮询设备、不调用厂商 SDK，也不支持 Ubuntu/Linux。
- R3 不提供设备写入、程序传输、cycle start 或联锁操作，不产生 `DeviceSafe`、`ProcessSafe`、`safe-to-run` 或上机许可。

## 0.8.0 - 2026-08-12

### Added

- 增加 Five-Axis Math F4 参考求解器 / SUT 验收闭环：`five-axis.domain-pack@5`、静态 `five-axis.solver-adapter@1`、reference / SUT in-process adapters、三类 canonical solver 拓扑、`adapter-input-hash-mismatch` 与 `interval-interior-collision` 反例，以及冻结的 M0–M5 manifest 与 example payload。
- 增加 F4 的七个数学 gate claims，分别覆盖 `GeometryValid`、`TaskGeometryCollisionFree`、`KinematicallyFeasible`、`ConfigurationCollisionFree`、`ContinuouslyFeasible`、`IntervalCertified` 与 `ModelCollisionFree`。
- 增加 F4 公开 API 查询面：`/api/v1/five-axis/f4/manifest`、`/api/v1/five-axis/f4/scenarios` 与 `/api/v1/examples/five-axis-f4`。
- 增加 F4 Gate Acceptance Lab 网页工作台，展示三拓扑覆盖、Adapter receipts、Reference/SUT gap、M5 区间碰撞见证和七个数学 claims；反例禁止执行并明确不计入闭环。

### Changed

- R2 数学领域 gate 现在以 Math F4 为完成门，Roadmap 下一阶段切到 R3 设备只读接入。
- 文档与示例都把 F4 的数学边界固定为 Windows AMD64 + CPython 3.12.10 + Haswell / 单线程 baseline，不把 Ubuntu 或设备写入声明当成本阶段支持范围。
- Windows 验收约束固定 `pip==26.1.2`，源码安装与 wheel 烟测都会先按 `constraints/acceptance.txt` 升级安装器，避免发布环境落入已知漏洞版本。
- F4 只通过 reference / SUT cross-validation 与 M5 重建碰撞证据发布数学 claims，不引入 `DeviceSafe`、`ProcessSafe` 或上机许可。

### Verification

- F4 的 example payload 可经 `POST /api/v1/runs/evaluate` 回放为 `Passed`，并保留七个数学 gate claims。
- API 层已暴露 F4 manifest / scenarios / example payload 端点，供网页工作台消费同一份数据契约。
- Windows AMD64 + CPython 3.12.10 精确环境下，Python 全量 503 项、前端 14 项、TypeScript 检查、生产构建、wheel 安装后 CLI/API/网页烟测均通过；依赖审计未发现已知漏洞。
- 当前文档同步保留了 0.7.0 的旧条目，不回写历史版本内容。

### Boundary

- 本次 F4 完成门不包含真实控制器、驱动器写入、设备启动、过程安全批准或学习模型闭环。
- `DeviceSafe`、`ProcessSafe` 和任何上机许可在 F4 仍然禁止发布。

## 0.7.0 - 2026-08-12

### 新增

- 增加 Five-Axis Math F3 时间与离散参考栈：独立 `MotionConstraintProfile`、M4 连续时间轨迹、M5 采样轨迹/离散命令，以及内容身份和 provenance 绑定。
- 增加线性固定路径、零边界状态下的解析二阶三角/梯形时间律；只有该闭合子集标记为 `ProvenOptimal`。
- 增加七次停到停 smoothstep Jerk 可行时间律、逐轴 V/A/J 约束重放和向外舍入的保守界；最优性保持 `FeasibleOnly`。
- 增加结点停启与 dwell 语义、固定周期与 remainder/终点/final-hold 契约，以及 `reference-m4`、多项式、FOH、ZOH 四种版本化重建策略。
- 增加覆盖三类 canonical 五轴拓扑、二阶最优、dwell/mandatory-stop、移动 ZOH 不支持和多项式区间内部违反的确定性 F3 场景与 fixture。
- 将 `five-axis.domain-pack@4` 接入公共 `RunSpec → RunBundle` 路径，只发布 `ContinuouslyFeasible` 与 `IntervalCertified` 两项标准 Claim，并提供 manifest、场景目录和示例 envelope API。
- 增加 Five-Axis F3 Time & Sampling Lab，展示 σ(t)、逐轴 V/A/J、结点时间线、固定周期样本、重建策略、分量化误差账本、Claim 与 sealed M4/M5 身份。

### 契约变化

- v0.7 将发布与阻断验收基线收敛为 Windows AMD64 + CPython 3.12.10，并固定 Haswell OpenBLAS core、OpenBLAS/OMP 单线程和 acceptance 依赖；其他平台暂不纳入本阶段支持矩阵。
- F2/F3 数值环境新增 Pint、OpenBLAS core 与线程策略字段；发布 fixture 必须唯一匹配环境记录并覆盖全部场景，缺失金值不再静默退化为仅做同进程重放。
- F3 runtime 在发布正向 Claim 前重算 M3/Profile 内容身份、时间律、边界状态、逐轴连续极值、结点契约、采样计划和重建能力，不信任 Artifact 内嵌证书的自报结论。
- M5 明确区分对 M4 的 `SampledTrajectory` 与具有保持语义的 `DiscreteCommand`；所有区间按 `[t_k,t_{k+1})` 解释，终点之后是否保持由 `finalHold` 单独声明。
- FOH/ZOH 不继承完整高阶连续证书；移动 ZOH 和未闭合高阶导数的 FOH 返回结构化 `Unsupported`，不会制造 `IntervalCertified` 正向 Claim。
- 误差账本按 quantity/unit/source/bound/method 分项记录，位置、姿态、时间与浮点误差不再合并为无量纲依据的单一总误差。

### 修复

- 统一 M5 内容身份中的 signed zero，使示例 RunSpec 经浏览器 `JSON.stringify` 往返后仍能通过冻结哈希校验。
- 统一网页运行态 Claim 与 API 的 `claimDefinitionId` 字段，确保 Supported、Inconclusive 与 Refuted 结论按真实证据展示。
- 将区间验证的 `Unsupported` 明确投影为标准 `IntervalCertified = Inconclusive`，并让场景摘要、MathStageManifest、RunBundle 与 fixture 使用同一状态和证据语义。
- 二阶解析 `ProvenOptimal` 严格拒绝内部连续通过的移动结点，保持在 ADR 冻结的线性 stop-to-stop 闭包内。
- 规范化 SVD 派生的奇异性证据并把具体运行时版本移到 Manifest/Run 层，使 M3/M4/M5 内容身份在 Python 3.12/3.14 与 NumPy 2.4/2.5 验收环境间一致。
- 将 portable 五轴 Artifact 哈希的浮点表示固定为 8 位有效数字并统一 signed zero；SVD 证据保留 12 位，raw gate 之后的小于 `1e-14` 的 IK 残差证据提升为保守上界，所有门槛判定仍使用原始 binary64 值；`RunBundle` 金值额外绑定操作系统与机器架构。
- 固定 Windows 前端源码与内置构建产物的 LF 换行契约，避免 Vite 构建仅因 checkout 换行策略产生伪差异。
- 单次 F3 评估只重放一次连续轨迹与区间重建 verifier，避免指标数量放大相同证明成本。

### 当前边界

- F3 的二阶 `ProvenOptimal` 仅适用于冻结的线性 stop-to-stop 子集；Jerk 路径只证明可行，不宣称一般三阶固定路径全局最优。
- F3 不生成 `ModelCollisionFree`、`DeviceSafe`、`ProcessSafe` 或控制器兼容声明；网页永久显示 `MATH ONLY / NOT DEVICE SAFE`。
- R2 仍需 Math F4 的 Reference Solver/SUT Adapter、独立集成验收和完整 Claim gate；设备、学习与参数闭环属于后续 R3–R7。

## 0.6.0 - 2026-08-11

### 新增

- 增加 Five-Axis Math F2 运动学参考栈：版本化 `MachineProfile`、通用运动链、双转台 AC / 摆头转台 BC / 双摆头 CB 三类闭式 IK，以及固定搜索策略的一般数值 IK。
- 增加 M2→M3 连续提升、分支图、wrap、结点事件、局部幂基轴段、归一化轴限位裕量、奇异性下界和 FK 回放证书。
- 增加显式 `Q_free` 配置空间碰撞模型、机床自身/环境碰撞对、连续区间聚合证明和内部碰撞反例见证。
- 将 `five-axis.domain-pack@3` 接入公共 `RunSpec → RunBundle` 路径，发布 `KinematicallyFeasible` 与 `ConfigurationCollisionFree` 标准 Claim，并提供 manifest、场景目录和示例 envelope API。
- 增加四个确定性工程参考场景和 `fixtures/five_axis_f2`：三类 canonical 拓扑的安全连续提升，以及端点安全但 \(\sigma=0.5\) 内部碰撞的反例。
- 增加独立的 Five-Axis F2 Kinematics Reference Workbench，展示连续五轴坐标、分支/wrap、`Q_free` 证书、区间碰撞见证、内容身份和 sealed M3 输出。

### 契约变化

- F2 runtime 在发布正向 Claim 前重算 M2/M3/MachineProfile 内容身份、冻结方法与策略、FK 回放、节点连续、整段限位、奇异性和碰撞覆盖，不信任 Artifact 内嵌证书的自报结论。
- `five-axis.axis-limit-margin.min@1` 使用逐轴行程归一化后的无量纲最小裕量，禁止把毫米和弧度直接聚合。
- 配置碰撞正向 Claim 必须来自完整 path 查询和 `Certified` 区间覆盖；单点查询、端点采样、F1 任务几何碰撞或 partial coverage 都不能替代。
- 网页把 Core 的执行/Case 状态与 F2 标准 Claim 分开显示；碰撞反例可得到 `caseOutcome=Passed`，同时保持 `ConfigurationCollisionFree=Refuted`。

### 当前边界

- F2 连续正向闭包首版只覆盖 canonical Profile 下的直线位置、常量刀轴和固定解析分支/wrap；一般数值 IK 最高为 `Validated`，超出可证明子集时返回 `Unsupported` / `Inconclusive`。
- F2 尚不包含 M4 时间参数化、M5 控制周期采样/重建、厂商 Solver/SUT Adapter、控制器、驱动器或真实设备观测。
- F2 的数学 Claim 不构成 `DeviceSafe`、`ProcessSafe` 或上机许可；R2 仍需完成 Math F3/F4 才能通过整体阶段门。

## 0.5.0 - 2026-08-11

### 新增

- 增加 Five-Axis Math F1 几何参考栈：严格 CL 子集规范化为 M0，生成带来源、无隙 `PathProgress` 和正则性证书的 M1，并以 M2 绑定候选连续几何、参考内容身份、坐标上下文、容差和标准对应证书。
- 增加连续位置/姿态误差证书、`GeometryValid` 标准声明，以及明确区分严格连续界、解析恒等和采样观察的证据等级。
- 增加任务几何碰撞与名义过切验证：显式刀具组件、工件/夹具 AABB、接触策略、允许去除区、过程状态时间线、库存快照内容哈希和确定性差集复杂度上限。
- 增加三个可重复的工程化 F1 参考场景：名义通过、几何容差违反和夹具碰撞；场景都可通过公共 `RunSpec → RunBundle` 路径产生标准 Claim/Evidence。
- 增加 F1 manifest、场景目录和完整示例 envelope API，并将 `five-axis.domain-pack@2` 注册为可执行领域包。
- 将 Five-Axis 网页升级为 Geometry Reference Workbench，展示 CL 输入、M0/M1/M2 谱系、几何投影、对应证书、碰撞/过程状态、指标证据、标准声明和冻结身份；支持桌面与移动端。

### 契约变化

- Domain runtime 可声明领域自己的输入/请求 Artifact 描述符和 Metric 到标准 Claim 的投影；Core 继续只处理领域中立对象，不包含 Five-Axis ID 分支。
- `M2CandidateTaskGeometry` 现在必须显式携带 `coordinateContext`，禁止通过场景全局值或隐式属性补齐单位与坐标系。
- F1 示例接口返回 `manifest / scenario / source / artifacts / runSpec` envelope；调用通用执行接口时提交其中的 `runSpec`。
- 网页将 Core 的 `executionStatus/caseOutcome` 与领域标准 Claim verdict 分开显示；指标成功计算不能被误读为碰撞声明成立。
- 允许去除区内的正常切削接触只保留为 trace finding，不会把已经连续证明的无禁止碰撞结论从 `Certified` 降级；编程型异常也不会再伪装成能力不支持。

### 当前边界

- F1 只发布 `GeometryValid` 与 `TaskGeometryCollisionFree`；任务几何碰撞不包含 IK、分支、轴限位、奇异性、配置空间、机床部件、控制器或真实设备安全。
- F1 内建场景用于确定性参考和回归，不是厂商控制器、材料去除或整机数字孪生。
- 下一数学阶段是 F2 运动学参考栈；动态 Solver/SUT Adapter、设备接入、学习模型和参数闭环仍属于后续阶段。

## 0.4.0 - 2026-08-11

### 新增

- 增加领域中立 `ArtifactEnvelope` 与静态 `DomainRuntimeBinding`；有序离散点和 Five-Axis F0 通过同一 Core 路径执行，不在 `run.py` 增加领域分支。
- 增加版本化 `ArtifactAdapter` 及 Five-Axis Cartesian 采样位置视图到有序点的显式转换，记录源/结果内容身份与保留、丢弃语义。
- 增加 Five-Axis Math F0 机器契约、M0–M5 envelope、真实可复算内容 ID、package fixtures 和 F0 契约执行入口。
- 增加 `speed.point.mean` 与 `acceleration.point.max`，冻结前向相邻差分、区间端点和数值容差合同。
- 增加 Five-Axis Lab 网页契约面板；与 Point Lab 并列展示领域包、阶段 envelope、Adapter、finding 和证据边界。
- 为 CNC Case D 增加 Python 3.12.13 acceptance 环境的双方 RunBundle 与 comparison 金值，并在其他环境执行完整性重验与同环境重放。

### 契约变化

- `MetricDefinition` 公开 `differencePolicy`、`endpointPolicy` 与 `numericTolerance`；DomainPack 公开机器可读失败映射。
- `RunSpec.request` 使用领域中立请求 envelope，领域绑定负责恢复严格类型；原有 `EvaluationRequest` 与 bare ordered-point 输入保持兼容。
- 未绑定 Evaluator、请求解析失败和 Evaluator 执行异常都返回结构化状态，不再由 Core 借用其他领域实现或泄漏内部异常。
- `axiom run` 与 `POST /api/v1/runs/evaluate` 可执行任意已静态绑定的 DomainPack RunSpec。
- `EvaluationReport.contentHash` 统一为排除自引用字段后的报告内容身份；`Provenance.requestHash` 单独标识请求，Run 与 Claim 必须引用同一报告哈希。
- 旧调用方若曾把 `EvaluationReport.contentHash` 当作请求哈希，应改读 `Provenance.requestHash`；补齐运行 provenance 后报告哈希会按同一公式重新计算。
- Five-Axis F0 只有在 fixture、M0–M5 envelope、能力依赖与显式 Adapter 路由全部闭合后才返回 `Computed`，错配输入不会产生 `Passed`。

### 当前边界

- Five-Axis F0 只证明 manifest、schema、能力依赖、失败映射与 Adapter 边界可执行；M1–M5 数值求解、连续碰撞验证和七类数学正向 Claim 尚未实现。
- Five-Axis Lab 不是轨迹仿真器，不显示伪造的运动学、碰撞或设备可执行结果。
- 动态插件、厂商 Solver/SUT 进程或 RPC Adapter、设备接入、模型训练和参数闭环仍属于后续阶段。

## 0.3.0 - 2026-08-11

### 新增

- 增加可执行的双臂 `Experiment`：在共同输入、共同参数和版本化 Subject 下运行基线与候选算法。
- 增加静态 `python-call@1` Runner 和两个内建有序离散点 Subject；不允许任意命令或模块执行。
- 增加本地 FastAPI 服务和 React Point Lab，可编辑输入、重跑实验、查看轨迹、指标、Claim、Evidence 与 Provenance，并下载证据包。
- 增加真实 CNC 轮廓合成实验 fixture，冻结跨 Python、CLI 和 HTTP 入口的一致结果。
- 增加 CI、可复现前端构建检查和带内置网页资源的 GitHub Release 工作流。

### 契约变化

- `ParameterSet` 必须声明 `parameterSchemaId`，并与 Subject 所声明的参数模式完全匹配。
- 严格实验比较接收完整 `ExperimentSpec`，同时校验 Subject ID/版本、Runner、输入、参数、Experiment 内容标识以及 RunBundle 完整性。
- Subject 执行或输出契约失败时不生成伪造的 Observation/RunBundle。
- `axiom experiment` 仅在执行、比较和实验硬门槛全部通过时返回退出码 `0`。

### 当前边界

- 本版本只提供确定性的本地静态 Subject，不含厂商算法进程、容器编排、数据库、认证、设备驱动或机器学习训练。
- 网页中的三维及更高维轨迹明确显示为 XY 投影；数值评估仍使用全部坐标。
