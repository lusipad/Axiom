# Changelog

本文件记录 Axiom 的用户可见变化。版本遵循语义化版本。

## Unreleased

## 0.23.0 - 2026-08-14

### Added

- 新增 `RealHoldoutCampaignManifest` / `RealHoldoutCampaignRegistration` 与 `axiom real-holdout-campaign`，使外部数据/试验责任方能在现场采集前封存 R5-B 基线、计划 Case、设备/工况、双运行身份和 command 内容身份。
- 新增 `axiom.intelligence.preregistered-real-holdout-intake-request@1` / `report@1`、`POST /api/v1/intelligence/r5b/campaigns/register` 和 `POST /api/v1/intelligence/r5b/intake/assess-preregistered`；严格 intake 会检查登记早于每次 capture 打开时间，并逐项核对实际 Case 与预登记 slot。
- R5-B 工作台新增 Campaign request/report 导入、严格 intake、Manifest/Registration 下载和 `PreRegistered` selection 状态展示；新增 ADR-0027 与 Windows 现场流程说明。
- 新增 Windows-only `intelligence.domain-pack@3`：25 点 R4 synthetic SIL 参数研究、15/5/5 空间 holdout、周期 `s` 与线性误差 `mm` 双输出 ridge 模型、split-conformal 区间、OOD 弃权和独立纯 Python parity。
- 新增 R5-C typed manifest/scenario/example/predict API、公共 Run 重放、Intelligence R5-C 网页工作台、开发/发布双档数值环境金值与 ADR-0028。
- 新增 Windows-only `optimization.domain-pack@2`、目标驱动 `optimization.search-request@2` 和 `RecommendationSet@2`：在 15×9 共 135 点网格上使用 R5-C 代理筛选，并把精确 F3/F4/R4 回放限制在最多 27 点。
- 新增速度、质量和紧凑指令三个 R6 v2 场景、typed manifest/example/search API、开发/发布双档数值环境金值、默认 v2 Optimization Lab 与 ADR-0029；网页保留 v1 切换入口。
- 新增 `axiom.control.recommendation-evidence-projection@1` 与 `axiom.adapter.r6v2-to-r7a-shadow@1`，把 R6 v2 Recommendation、screening、exact candidate 和预算内最优性身份显式接入既有 R7-A synthetic Shadow。
- 新增六个 R7-A v2 handoff 场景、typed manifest/example/replay API、环境绑定 Projection/Audit 金值与 ADR-0030；Controlled Runtime 默认展示 v2，并保留 v1 切换。
- 新增 `GoalToShadowRequest` / `GoalToShadowReport`、`axiom.control.physical-shadow-projection@1` 与 `POST /api/v1/control/goal-to-shadow/rehearse`；选中的 R6 v2 exact candidate 会按冻结协议重新执行 F3/F4/R4，并以实际 `PhysicalResponseTrace` 驱动既有 R7-A 状态机。
- Optimization Lab 新增候选级“进入 Synthetic Shadow”动作和内联结果卡，展示 exact sample 数、X/Y/Z 最大线性误差、OOD、Admission、Stop/Rollback 与永久零写入边界；新增 ADR-0031。
- 新增 R5-D `SimulationExperimentPlan` 与纯 Python 顺序 G-optimal planner：只用 R5-C 的 15 个 train 点构造信息矩阵，从 R6 v2 网格的 110 个未观测点中规划默认五点，并冻结开发/发布双数值环境身份。
- 新增 R5-D typed manifest/example/plan API、Intelligence Lab“规划下一批仿真”面板与 ADR-0032；界面展示选择前后最大 leverage、独立 `s`/`mm` 预测和预计命令样本数。
- 新增 R5-E 离线合成实验反馈闭环：完整五点 R5-D 计划在责任方显式 synthetic-only 批准后重放 exact F3/F4/R4，封存不可变 AcquisitionReceipt，生成 30 点 Dataset@2、20/5/5 Split@2、ModelBundle@2 候选与下一份未执行计划。
- 新增 R5-E typed manifest/example/approve/execute API、Intelligence Lab 批准与执行面板、双数值环境 fixture 和 ADR-0033；界面展示五点物理结果、数据/split 扩展、原 holdout 指标差值、候选门与下一计划。
- 新增 R5-F 候选模型下游影响评估：在同一三个 R6 v2 意图、135 点网格和 27 次精确预算下并排运行 R5-C v1 基线与 R5-E v2 候选，封存筛选差异、精确集合、预算内最佳目标和共享精确点预测误差差值。
- 新增 `optimization.search-request@3`、`axiom.optimization.recommendation-set@3`、R5-F typed manifest/impact API、Intelligence Lab 影响面板、双数值环境 fixture 和 ADR-0034；旧 `@2` 合同与金值保持不变。
- 新增 R5-G `ModelPromotionReadinessDossier`：确定性重放 R5-E/R5-F，冻结唯一基线、候选、candidate context 与 rollback baseline 身份，并把五项 readiness checks 和六项 remaining gates 封装为内容寻址审查包。
- 新增 R5-G typed manifest/readiness API、Intelligence Lab 只读审查面板、开发/发布双数值环境 fixture 和 ADR-0035；界面只生成审查包，不提供采用、注册、激活、默认切换或部署动作。
- 新增 R5-H 候选专属真实 holdout：采集前冻结 R5-G baseline/candidate、至少三个 Case、严格阈值、精确 M4/M5 与数值环境；评估只接受完整 R7-E/R4.1 报告，并由服务端重算周期与 X/Y/Z 线性误差标签。
- 新增 R5-H typed manifest/register/assess API、Intelligence Lab 预注册/下载/多报告导入/只读结果面板和 ADR-0036；状态明确区分 `Open`、`Blocked`、`Refuted` 与 `CaseScopedPassed`，不提供模型采用或设备动作。
- 新增 R5-I `PromotionDecision`、晋升预检、ActivationReceipt、MonitoringWindow 与 RollbackReceipt 合同；本机 SQLite Registry 以单事务完成候选注册、generation 增长、默认指针切换与提交后读回，并持久化分目标监控及显式回滚证据。
- 新增 Windows `axiom model-lifecycle status|predict|preflight|promote|monitor|rollback`、R5-I 只读 typed HTTP API、Intelligence Lab 生命周期面板和 ADR-0037；HTTP/网页不暴露晋升、激活或回滚写操作。

### Changed

- 只有同时绑定 Campaign Manifest/Registration 的 `selectionEvidenceStatus=PreRegistered` 才能关闭 R5-B holdout isolation 门。旧 `selectedBeforeEvaluation=true`、v1 intake schema 和历史 selection 内容身份保持兼容读取，但 runtime 会以 `RealHoldoutSelectionNotPreRegistered` 保持现实泛化 Claim 为 `Inconclusive`。
- 严格 intake 继续复用 v0.22.0 的 R7-E/R4.1 投影、治理、谱系、单位和隔离检查；本次没有新增 DomainPack 或修改 Core。
- R5-C 保持两个目标和单位独立，不生成综合评分；R6 v1 继续逐候选重放 F3/F4/R4 六点完全枚举，不静默改用代理模型。
- R6 v2 用一个主目标和两个显式同量纲约束代替权重总分。代理只产生候选和筛选回执；最终 Recommendation 只来自预算内精确回放，且只声明 `best observed`，不声明全局最优。
- `control.domain-pack@1` 的 Recommendation context 现在显式接受 schema version 1/2；主 RuntimeAudit、Evaluator、Runner 和六项 Claim 不变，R7-A v1 计算语义不变，其 Recommendation/Audit 身份按冻结数值环境分别保持不变。
- R7-A v2 只允许 exact-eligible 候选进入 synthetic Shadow；缺 Projection、跨候选重绑、精确约束失败和设备写请求均 fail closed。Projection 不是 AcceptanceRecord，非 best 的 exact-eligible 候选仍需独立处置。
- Goal-to-Shadow 不再把 R7-A 固定四点合同夹具解释为当前候选响应。服务端重验候选 M4/M5/R4 identity，并要求 M5 与 response 的 sample index、time 和五轴 command 逐项一致；Shadow 误差仅使用 X/Y/Z mm，B/C rad 明确排除，禁止插值或补点。
- R5-C、R5-D、R6 v2、R7-A 与 Goal-to-Shadow 中包含数值求解谱系的身份不再宣称跨环境 portable；fixture 显式区分 CPython 3.14 开发档案与 CPython 3.12.10 + Haswell/单线程 OpenBLAS 发布档案。
- R5-D 明确区分 split-conformal 区间与 design leverage：前者继续表达 validation 边界内的经验覆盖，后者只作为线性设计的 epistemic proxy；预测值不参与首版信息价值排序。
- R5-D 每轮选点后更新信息矩阵，validation/test 永不进入设计矩阵，全部已观测点都从候选池排除；获得新标签后必须生成新的 DatasetSnapshot 与 ModelBundle 才能再次规划。
- R5-E 保持全部 R5-C v1 序列化与内容金值不变；v2 只按 proposal 顺序向 train 追加五点，原 validation/test 成员与顺序冻结，候选仍在原 holdout 上与基线比较。
- R5-E 把 Campaign 成功、candidate gate 与 model promotion 分成三个独立状态。冻结 fixture 上的 RMSE 改善只记录为观测，`generalImprovementGuarantee=NotClaimed`，`modelPromotionStatus=NotPerformed`。
- R5-F 在影响评估前重放 R5-E Campaign 并重验 candidate bundle、training、parity、dataset、split 与 assessment 谱系；客户端不能提交自报的 RecommendationSet。
- 候选 surrogate 仍只改变有限预算内的筛选顺序，最终结果继续由 exact F3/F4/R4 和七个数学/碰撞门裁决；影响门不改变 R6 v2 默认模型。
- R5-G 的 `ReadyForIndependentReview` 只由证据完整性派生。准备者三项确认不是 PromotionDecision；报告固定等待独立人工决定，并保持 registry/default/activation 状态不变。
- R5-G HTTP intake 会按冻结 R6 v2 参数 schema 恢复 JavaScript JSON 往返中从 `1.0` 退化为 `1` 的坐标类型，再执行原内容哈希校验；全局哈希算法和既有 R5/R6 金值不变。
- R5-H 不复用 R5-B 对 R5-A 残差模型的结论。周期头固定为不计入 reality 的 `exact-planner` 证据；线性误差头才从 controller-live-read 的 X/Y/Z `mm` 序列派生，两个目标保持独立 RMSE、coverage、单位和门禁。
- R5-H 网页的登记、评估和 JSON 下载改用保留 IEEE-754 `-0` 的序列化器，M5 关节坐标会写成 `-0.0`；sealed dossier、Registration report 与现场报告在 OpenAPI 输入侧作为 canonical JSON artifact 提交，服务端仍恢复完整类型并重验嵌套哈希，同时保持既有 R7-E OpenAPI 组件名不变。
- R5-I 在任何状态写入前权威重放 R5-G/R5-H，并要求独立决定人与 R5-G 准备者分离、决定签名绑定 dossier、assessment、候选及冻结回滚基线；相同决定可幂等读回，不同内容复用 ID 或 generation 冲突均 fail closed。
- R5-I 默认模型只供显式配置该 Registry 的当前模型推理使用。既有 R6/R7 请求、历史结果和内容身份不会静默查询或跟随 Registry，避免本机激活改变已封存计算语义。

### Boundary

- 首版 Registration 使用 `external-owner-attestation`。Axiom 验证内容身份与时间先后，但不提供可信时间戳、数字签名或物理真实性证明；Registration 本身固定 `countsTowardReality=false`。
- 仓库仍不包含真实 TwinCAT/TF6100 capture 或正向真实 holdout。Campaign/Intake 不连接或写入设备，不开放 Controlled Trial、Closed Loop、DeviceSafe 或 ProcessSafe。
- R5-C 数据全部来自同一冻结 R4 synthetic SIL 模型与 canonical head-table path；`syntheticConditionalEffectContractStatus=Passed` 不关闭 `realWorldGeneralizationStatus=Open`，域外预测只弃权，且不存在 Recommendation、设备写回或在线学习入口。
- R6 v2 的 `globalOptimalityStatus=NotClaimed`、`permissionLevel=Offline`、`deviceWriteAllowed=false`、`realityValidationStatus=Open`。它不产生 AcceptanceRecord、DeviceSafe、ProcessSafe、上机许可或任何设备写入路径。
- R7-A v2 仍是 Windows 进程内 synthetic Shadow：Stop 只抑制晋级，Rollback 只证明离线基线未改写。Deployment Shadow、Reality、Controlled Trial、Closed Loop 和标准符合性继续为 Open/NotAssessed。
- Goal-to-Shadow 是应用层 synthetic SIL 编排，不新增 DomainPack、Core Claim、缓存、历史持久化或设备连接。用户选择不是自动接受；报告固定 `deviceWriteAllowed=false`、Reality/Deployment Shadow/Controlled Trial/Closed Loop Open、Device/Process Safety NotAssessed。
- R5-D 只生成 synthetic SIL 计划，不执行 F3/F4/R4、不生成标签、不更新模型，也不声明全局最优或现实收益；固定 Offline、NotExecuted、NotPerformed、零自动执行、零设备写入和 reality Open。
- R5-E 只能在 Windows 本地执行一批冻结 synthetic SIL；不连接真实设备，不递归执行下一计划，不自动晋升、部署或回写模型。报告固定 `SYNTHETIC SIL / NOT REALITY VALIDATED / NOT DEVICE SAFE / PROMOTION NOT PERFORMED`。
- R5-F 的 `Passed` 只表示冻结 synthetic SIL 下游场景在同预算下无精确主目标退化；报告固定 `EvaluatedOnly`、`NotPerformed`、Offline、零设备写入和 reality Open，不表示模型晋升、一般收益、全局最优或设备安全。
- R5-G 本身不执行模型晋升；其审查包继续固定 Offline、reality Open、零部署和零设备写入。后续 R5-I 只能在真实 holdout 与独立签名决定齐备后关闭本机 registry/default/monitoring 合同，不能反向扩大 R5-G 结论。
- R5-H 仓库不包含真实现场正例；默认 assessment 因缺证据保持 Open。即使外部报告得到 `CaseScopedPassed`，结论也只限预登记 Case；它只可作为 R5-I 的必要输入，不能单独关闭模型采用、DeviceSafe 或 ProcessSafe。
- R5-I 首版授权证明为调用方注入的单机 HMAC-SHA256 内容绑定，不是企业 PKI、可信时间戳或不可否认性证明；密钥不进入请求、响应、SQLite、网页或日志。
- `modelPromotionStatus=Performed` 仅表示 Axiom 本机 Registry 已切换默认纯 Python 模型。集中式 Registry、远程多机分发、控制器部署、受控试验、自动回滚、DeviceSafe、ProcessSafe 和设备写入仍不在本阶段范围内。

### Verification

- 最终源码共收集 `931` 项：Windows CPython 3.14 开发档案全仓 `924 passed / 7 skipped`；冻结 CPython 3.12.10 + `AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS=1`、Haswell/单线程 OpenBLAS 发布档案全仓 `925 passed / 6 skipped`。R5-I/CLI/Web 定向终验另有 `44 passed`。
- 网页全量 `17 files / 59 tests`、TypeScript 和 Vite 生产构建通过；R5-H 真实浏览器流程继续保持 `Open`，R5-I 又完成未配置 Registry、只读预检/默认模型动作边界和桌面/375px 移动布局检查，控制台 `0 errors / 0 warnings`、生命周期写动作 `0`，视觉门 `94/100`。生产 JS 为 561.72 kB，仍有既有的 Vite 大 chunk 警告。
- R5-D Python/API 在开发与发布档案各 `12 passed`；独立 NumPy oracle 逐轮复算五个候选，双档 fixture 分别冻结 request/plan 身份，非 Windows 返回结构化 Blocked。
- R5-D 在 1440×900 与 375×812 实页复核中无横向溢出、页面错误、失败请求或设备动作；移动端候选完整卡片化，视觉门 `94/100`。浏览器仍会请求仓库既有的缺失 `/favicon.ico` 并记录单个 404，不影响应用请求。
- R5-E Python/API 在开发与发布档案各 `15 passed / 1 skipped`；覆盖明确批准、完整五点 exact 标签、25→30 数据、15→20 train、原 holdout 冻结、候选非回归、重规划、非 Windows 拒绝、内容篡改和跨对象 lineage 错配。
- R5-E 在 1440×900、768×1024 和 375×812 实页上完成 plan→责任方/勾选→approve→execute 流程，无控制台错误、失败请求或设备动作；移动表格卡片化后视觉门 `94/100`。
- R5-F Python/API 与既有 R6 v2/R5-E 联合测试在开发和发布档案均通过；覆盖三场景 135/27 等条件比较、旧 `@2` 金值不变、候选全谱系、派生状态篡改、非 Windows 拒绝和双环境内容身份。
- R5-F 在 1440×900 与 375×812 实页完成 R5-D→R5-E→R5-F 流程，0 个应用请求失败、0 横向溢出、无设备动作；独立青绿色影响卡与移动证据卡通过视觉门 `94/100`。浏览器仍可能请求仓库既有的缺失 `/favicon.ico`，不影响应用接口。
- R5-I 变更范围 Ruff、`git diff --check`、65 个 JSON 解析与 58 份 Markdown / 225 个本地链接检查通过（0 个缺失）。仓库级 Ruff 仍报告 6 个不属于本包的既存问题（5 个未使用导入、1 个旧 `__all__` 名称）。
- R5-F 阶段曾在 CPython 3.12.10 下完成源码→sdist→wheel、独立 target 安装与 Goal-to-Shadow/R5-D/R5-E/R5-F/OpenAPI smoke；该阶段 wheel SHA-256 为 `0513e4038f6926b7cce11eb41084fcb3aaa930e2627e91754058660df4d4ede9`。
- R5-H 最终 wheel 沿源码→sdist→洁净解包源码→wheel 路径构建并安装到全新 CPython 3.12.10 环境；安装后 manifest、三条 R5-H API、旧 R7-E OpenAPI `$ref` 和当前网页资产 smoke 通过。wheel 只包含 `index-CK7vlEZX.js` / `index-DmgFvKgD.css`，SHA-256 为 `45866717945a18959dfbd0798565c015d920a179fbc5cea47419eed6befce2f7`。
- v0.23.0 最终 wheel 沿源码→sdist→洁净解包源码→wheel 路径构建并安装到全新 CPython 3.12.10 环境；安装后版本、CLI、R5-I manifest、5 条只读/预检 OpenAPI 路由、零生命周期写路由和未初始化 Registry 零落盘 smoke 通过。wheel 只包含当前 `index-BnGCl8ia.css` / `index-DGm2MFL1.js` 两份网页资产，SHA-256 为 `45f10a7bd712d04912ffe45d1b78ab13721acfd1be8aaf1007dd7f558f9e2735`。
- 锁定 .NET SDK 8.0.424 完成 locked restore、Release build 与 Windows OPC UA conformance，`0 warnings / 0 errors`；适配器和见证写入计数均为 0，独立写入、未信任证书、过期授权、超时及多类身份错配均被拒绝。
- R7-A v1/v2 定向 Python/API `36 passed`；Controlled Runtime 组件与 App 联合 `15 passed`，默认 v2/v1 切换、六类 handoff 场景和无设备控制入口均有覆盖。
- R7-A v2 桌面、v1 参考与 375×812 移动端实页检查无横向溢出或控制台错误，视觉门 `94/100`；sdist→wheel、隔离安装、OpenAPI smoke 和两份当前网页资产检查通过。

## 0.22.0 - 2026-08-13

### Added

- 新增 `axiom.adapter.r7e-to-r5b-holdout@1` 与 `axiom.intelligence.real-holdout-intake-request@1` / `report@1`，把多个已通过的 R7-E / R4.1 现场 dossier 确定性投影为现有 `RealPairedHoldoutSet` 和可执行 R5-B RunSpec。
- 新增 `axiom real-holdout-intake`。既可读取完整请求文件，也可用 `--base-run-spec`、`--governance` 与可重复的 `--case` 直接组装多文件输入；退出码固定为 `0=可进入 R5-B`、`1=Open/Blocked`、`2=Malformed`。
- 新增 `POST /api/v1/intelligence/r5b/intake/assess` 与 R5-B 网页多文件 intake 面板；网页可展示逐 Case 投影收据、八项门禁、原始/派生内容身份和永久安全边界，下载投影后的 `RealPairedHoldoutSet` / R5-B RunSpec，并执行生成的 RunSpec。
- 新增 ADR-0026，并扩展 Windows 现场证据指南、R3/R4/R5 规范与 Roadmap 的跨阶段合同。

### Changed

- 每个现场 dossier 只允许贡献 validation 运行；calibration 仍只用于 R4.1 模型识别。Intake 要求至少两个 in-domain Case 跨两个设备与两个 condition，再加一个 OOD probe，并拒绝报告/Shadow 证据复用、capture 窗口重叠、治理时序错误和谱系/设备/单位冲突。
- R3 投影保持 `sourceKind=device-read` 与 `operation=file-import` 两条事实，并以 `axiom.r7e.x-source-timestamp@1` 显式映射单一设备时间；五轴原始 source/server/host timestamp、sample-index 证据和原始 Shadow/R4.1 哈希完整保留，不插值、不平均、不静默修复。
- 投影后的 R3 `MachineTelemetryTrace` 使用其规范化内容重新计算 `traceContentHash`；上游 Shadow 证据哈希仍作为独立来源身份保留，避免把来源身份误当成派生 Artifact 身份。
- `countsTowardReality=true` 现在明确只表示 intake 有资格进入 R5-B evaluator。真实泛化是否得到支持仍由随后执行的 R5-B RunSpec 决定，范围只限提交的 Case。
- 版本提升至 `0.22.0`，发布 wheel 同步包含更新后的 R5-B 工作台和 typed OpenAPI 契约。

### Verification

- Python 本机完整非环境绑定套件 `786 passed / 1 skipped`；定向 intake 套件覆盖 Passed/Open/Blocked、跨设备/工况/OOD 覆盖、复用/谱系/治理/时间窗反例、原始值与哈希保留、多文件 CLI、HTTP 和公共 R5-B Run。
- 网页 `14 files / 49 tests`、TypeScript 与 Vite 生产构建通过；R5-B 组件覆盖多文件导入、投影报告和生成 RunSpec 的公共执行链。
- `.NET SDK 8.0.424` locked restore 与 Release solution build 通过，`0 warnings / 0 errors`。本机 CPython 是 3.14.3，无法重放只绑定 CPython 3.12.10 的 F2/F3 bundle 金值；现有 Windows CI 继续使用精确 3.12.10 阻断该门。

### Boundary

- 仓库仍不包含真实 TwinCAT/TF6100 capture 或正向真实 holdout。Intake 只投影外部封存证据，不连接 PLC、不写设备、不重新训练、不自动部署或接受参数。
- `Controlled Trial`、`Closed Loop` 保持 `Open`；`DeviceSafe`、`ProcessSafe` 保持 `NotAssessed`。即使 R5-B 对提交 Case 给出 Supported，也不能外推到未提交设备、工况或安全许可。

## 0.21.0 - 2026-08-13

### Added

- Windows `.NET` Adapter 新增离线 `beckhoff-shadow-assessment`：从 Bound Vendor/Witness Profile、runtime、controller、只读 authority、capture authorization、M5 command 和原始 Shadow evidence 生成一份 Python 可直接验证的 R7-E assessment 文件。
- `axiom field-evidence` 新增双文件入口，可直接传入 calibration/validation 两份 R7-E assessment 与三个显式 pair identity；原有完整请求文件入口保持兼容。

### Changed

- 离线组装器重算 portable 内容身份并逐项核对 runtime/Profile、authority/controller、authorization/command 和 Shadow evidence 的绑定，同时要求 `controller-live-read + declaredReal`、有效授权时间窗、成功采集与零 Write/Call；失败和已存在输出都不会被覆盖。
- controller 与 authority 会按 Python 侧完整强类型合同验收；M5 canonical hash 按 schema 区分整数与浮点字段，因此合法序列化器写出的 `0` 与模型中的 `0.0` 不再产生伪身份冲突。
- C# portable JSON 哈希使用与 Python `ensure_ascii=false` 一致的字符编码，并按 Five-Axis M5 合同执行 8 位有效数字规范化，避免 UTC offset 和浮点表示造成跨语言身份漂移。
- 现场推荐流程变为“不可变原始采集 → 离线 R7-E 组装 → 两文件双运行验收”；没有新增 DomainPack、第二套网页工作台或任意外部进程执行入口。

### Verification

- Python 全量 `771 passed / 1 skipped`；定向测试覆盖双文件配对、缺失/混用/不可读/Malformed R7-E 输入、旧入口兼容与退出码，Windows `.NET` 跨语言测试覆盖完整对象一致性、强类型 support 反例、M5 整数词法兼容和 command 身份错配时不落文件。网页 `48 passed`，TypeScript 与生产构建通过。
- `.NET` 解决方案使用精确 SDK 8.0.424 完成无警告构建和四项跨语言/localhost 验收，secure read/subscription conformance 保持零生产 Write/Call；剩余一项 skip 是本地 CPython 3.14 不满足冻结的 CPython 3.12.10 数值环境金值，由 Windows CI 与发布工作流再次阻断验收。

### Boundary

- 开发机仍没有 TwinCAT/TF6100 与经授权双运行 capture；本版本消除的是现场文件拼装缺口，不会伪造 deployment Shadow、case-scoped reality、Controlled Trial 或 Closed Loop 通过结论。
- `beckhoff-shadow-assessment` 永不联网；生产采集仍只允许 read/subscribe。DeviceSafe/ProcessSafe 继续为 `NotAssessed`。

## 0.20.1 - 2026-08-13

### Fixed

- Release wheel 冒烟测试现在从发布标签推导安装版本，并按实际路由引用核验 R7-E 的 split input schema 与 typed response，不再把 `v0.20.1` 或 FastAPI 生成的 `R7EAssessmentRequest-Input` 误判为缺失契约。

### Boundary

- 本补丁不改变 R7-E API、采集协议或安全语义；真实 TwinCAT/TF6100 证据、Deployment Shadow 与 Reality 仍保持 `Open`，DeviceSafe/ProcessSafe 仍为 `NotAssessed`。

## 0.20.0 - 2026-08-13

### Added

- 增加可导入的 TwinCAT `FB_AxiomShadowWitness.TcPOU`：关闭窗口或窗口内命令身份异常切换时保持 sentinel；每个新快照先以 sentinel 使旧快照失效，再锁存 command hash 和 X/Y/Z/B/C，最后发布 sample index；七个输出均使用 TF6100 只读 OPC UA pragma。
- 增加 `axiom.control.beckhoff-shadow-witness-deployment-request@1` / `report@1`、`axiom beckhoff-witness-deployment`、typed HTTP API 与 Field Evidence 网页部署预检。
- 增加 [Beckhoff 只读见证部署指南](BECKHOFF-WITNESS-DEPLOYMENT-WINDOWS.md)、Open 请求骨架与 ADR-0025；Windows Adapter ZIP 同时携带模板、指南和请求示例。

### Changed

- R7-E 不再只描述“控制器应提供 sample index”；现在冻结控制器锁存协议、七信号顺序、显式 namespace/identifier、同一 runtime 的 BrowseName/DataType/只读访问证据和可复算的 Bound Witness Profile 生成规则。
- 节点检查器会把 config 与实际连接的 endpoint、证书和 Application URI 同 R7-D runtime 逐项核对；生产 `beckhoff-shadow-capture` 强制重验原始节点证据，不能以旧 Profile 绕过。
- 生产采集在自己的 OPC UA session 中、订阅前再次读取 BrowseName/DataType/访问级别；检查后发生的 PLC 符号映射变化会 fail closed。
- 每个有效 sample-index 通知都执行索引前读、七节点 batch Read、索引后读；sentinel 或任一版本不一致都会阻断撕裂快照。
- 网页可下载模板、导入部署请求并分别显示 Profile、vendor runtime、preparation、TwinCAT compile、Shadow 与 Reality 状态；仍没有 PLC 连接、写入、下发或控制入口。

### Verification

- 自动验证 `.TcPOU` XML、七组 `OPC.UA.DA`/只读 Access pragma、索引最后赋值、零运动控制调用、绑定顺序、内容哈希、CLI/HTTP 同义和 wheel/ZIP 包含关系。
- TwinCAT 导入、编译、激活、TF6100 ACL 与真实 capture 仍需在部署方 Windows 环境执行并留证；开发机没有伪造这些结果。

### Boundary

- `capturePreparationStatus=Passed` 只表示模板、runtime、command、NodeId 声明及七节点运行时属性证据闭合；capture authorization、Deployment Shadow、Reality、Controlled Trial 与 Closed Loop 仍为 `Open`，DeviceSafe/ProcessSafe 仍为 `NotAssessed`。

## 0.19.0 - 2026-08-13

### Added

- 增加 `axiom.field-evidence-assessment-request@1` / `report@1`，把两次 R7-E assessment、pair 构造、R4.1 holdout 验证、最终状态与内容哈希收敛为一个确定性 Windows 现场验收流程。
- 增加 `axiom field-evidence REQUEST.json` 和 `POST /api/v1/field-evidence/assess`；退出码固定为 `0=Passed`、`1=Open/Blocked/Refuted`、`2=Malformed`。
- Field Evidence 网页工作台现在分别导入 calibration 与 validation 两份 R7-E payload，并通过统一服务端编排器执行验收；新增 [Windows 现场证据验收指南](FIELD-EVIDENCE-WINDOWS.md)和可执行 Open 请求骨架。

### Changed

- 外部 R7-E assessment 在包含 M5 command 或 Shadow evidence 时必须显式携带 `caseId`；生成的 RunSpec 原样保留该身份，避免不同现场输入被共享默认 Case 错误归并。
- 现场报告仅在两个 R7-E deployment Shadow gate 都为 `Passed` 时创建有类型 calibration/validation pair；证据复用、跨 Case、门未闭合和 holdout 失配分别保持 `Blocked`、拒绝、`Open` 或 `Refuted`。
- 发布目标继续只包含 Windows；现场编排器只读取导入 JSON，不添加 PLC 网络、Write、Method Call 或设备控制路径。

### Fixed

- 新的现场导入或双运行验收失败时立即清除旧 Reality 结果，避免错误提示旁继续显示上一次的 `Passed` 状态。

### Verification

- Python 定向覆盖 Open、Passed、Blocked、Refuted、跨 Case 拒绝、内容篡改、CLI 和 HTTP 确定性；网页组件测试、TypeScript 和 Vite 生产构建通过。
- Field Evidence 双运行页面在 1440×1000 实页复核中无横向溢出，主动作层级视觉门为 `94/100`。

### Boundary

- Passed 测试数据只存在于单元测试，未进入公共示例；仓库仍没有可计入现实证据的 TwinCAT/TF6100 双运行 capture。
- 即使 case-scoped reality 通过，Controlled Trial、Closed Loop、DeviceSafe、ProcessSafe 和跨设备/工况泛化仍保持 Open/NotAssessed。

## 0.18.0 - 2026-08-13

### Added

- 增加 Windows-only R7-E Beckhoff Shadow Witness：`control.domain-pack@5`、sample-index-triggered 七节点 batch Read、带 UTC 有效时间窗的 typed 数据所有者采集授权、完整 M5 索引覆盖与零 Write/Call 收据。
- `.NET` Adapter 新增 `beckhoff-shadow-capture`；localhost conformance 会生成 5 帧 contract-only witness 证据，并由 Python 重验 schema 与内容哈希。
- 增加 R4.1 双运行现实验证器：`five-axis.domain-pack@7`、独立 calibration/validation pair、`five-axis.physical-model-definition@2`、exact-index 对齐、线性/旋转分组 improvement 和残差分解门。
- 网页新增 Field Evidence R7-E/R4.1 工作台，把 Shadow receipt、校准运行、独立 holdout、reality gate 与永久安全边界放在一条证据链中。

### Changed

- 真实轴采集不再由 OPC UA publishing interval 推断 M5 覆盖；每个 controller sample index 必须触发一次 command hash、index、X/Y/Z/B/C batch Read，缺索引不插值。
- 现实模型验证从 R4.0 synthetic SIL 的开放 Claim 扩展为可运行的双运行合同；同一 capture、同一授权、contract fixture、不同设备或不同采样周期都会 fail closed。
- 发布目标继续只包含 Windows；Ubuntu/Linux/WSL 不进入本阶段支持矩阵。

### Verification

- `.NET 8.0.424` 解决方案无警告构建和 localhost conformance 通过；生产 Shadow Witness 5 个索引对应 5 次 batch Read，Write/Call 为 0。
- Windows CPython 3.12.10 环境绑定套件 `732 passed`；网页 `45 passed`，TypeScript 与 Vite 生产构建通过，覆盖 R7-E/R4.1 的 Open、Unsupported、泄漏阻断、contract fixture 阻断和独立 holdout 数学路径。
- Field Evidence 页面在 1280、768、375 像素宽度通过 `94/100` 视觉门，根页面无横向溢出或失败请求。

### Boundary

- 仓库没有真实 TwinCAT/TF6100 运行时或现场 capture；conformance 永久是 `contract-fixture`，不能关闭 deployment Shadow 或 reality gate。
- 即使未来单设备单 Case 的 R4.1 reality Claim 通过，Controlled Trial、Closed Loop、DeviceSafe、ProcessSafe 和跨设备/工况泛化仍保持 Open/NotAssessed。

## 0.17.0 - 2026-08-13

### Added

- 你现在可以在 Windows 上用版本化 Vendor Profile 和九项审计检查验收 Beckhoff TwinCAT 3 Build 4026+ / TF6100；结果通过 `control.domain-pack@4`、typed API 和公共 Run 语义留证。
- 可先运行 `.NET` `beckhoff-preflight` / `beckhoff-inspect`，只读核验 `tcpkg`、XAR 软件包、Build、服务端二进制、标准 BuildInfo、TF6100 许可证结果与 X/Y/Z/B/C 节点访问级别。
- 需要验证权限边界时，可使用隔离的 Beckhoff 权限 verifier；它只接受部署责任人确认的非执行 canary，并以恰好一次同值 Write 冻结拒写收据。
- 网页新增 Beckhoff R7-D 工作台和默认开放 Profile；`win-x64` 发布包同时包含只读生产 Adapter 与独立权限 verifier，ADR-0022 记录了两者的责任边界。

### Changed

- R7 现在从厂商无关虚拟 OPC UA 合同推进到首个具体厂商 Profile；Profile、厂商运行时、真实 deployment Shadow 与 reality validation 分别判定，不再互相替代。
- 发布与 CI 会同时构建生产零写 Adapter 和独立权限 verifier；静态检查锁定前者没有 OPC UA session Write/Call，后者恰好只有一次 Write。

### Verification

- Windows `.NET 8.0.424` locked restore 和解决方案无警告构建通过；默认 Profile 的 `.NET → Python` 预检证据完成跨语言哈希重验。
- Windows CPython 3.12.10 环境绑定套件 `696/696` 通过；前端 `43/43`、TypeScript 与 Vite 生产构建通过。实页视觉门 `95/100`，桌面与 390px 窄屏控制台均为 0 错误。

### Boundary

- 当前开发机没有 TwinCAT/TF6100，预检如实返回 `TwinCatPackageManagerMissing` / `vendorRuntimeStatus=Open`；没有生成厂商运行时正例。
- 独立权限 verifier 未在真实设备运行；`deploymentShadowStatus`、`realityValidationStatus`、Controlled Trial 与 Closed Loop 保持 Open，DeviceSafe/ProcessSafe 保持 NotAssessed。

## 0.16.0 - 2026-08-13

### Added

- 增加 Windows-only R7-C OPC UA Shadow Transport：隔离的 `.NET 8` 只读 Adapter、`control.domain-pack@3`、五轴传输证据、七项机器可判定检查和跨语言内容哈希。
- 增加独立 localhost OPC UA Server conformance：固定 `SignAndEncrypt`、应用证书互信、非匿名 username、X/Y/Z/B/C 订阅、通知序号/时间/丢包，以及未知客户端证书和写请求拒绝验证。
- 增加 OPC UA R7-C 网页工作台、manifest/scenario/example/assess API、Windows 配置模板、locked NuGet 依赖和 `win-x64` 发布包。

### Changed

- R7 从厂商无关 JSON 就绪门推进到可执行网络传输合同；生产 Adapter 源码不包含 OPC UA Write 或 Method Call 路径，密码只从命名的 Windows 进程环境变量读取。
- CI 与发布工作流新增由 `global.json` 冻结的 .NET SDK 8.0.424、locked restore、无警告构建、网络 conformance 和 `.NET → Python` 证据重验。

### Verification

- Windows 本地 `.NET 8` 构建与网络 conformance 通过；五轴 25 个样本被采集，Adapter 写计数为 0，独立写请求和未知客户端证书均被拒绝。
- Python 全量测试 `677 passed, 1 skipped`；前端全量测试 `39 passed`，TypeScript 与 Vite 生产构建通过；干净 Python 3.12 wheel、Windows Adapter ZIP 与实页视觉门（`92/100`、控制台 0 错误、无设备控制按钮）均通过。

### Boundary

- `virtualTransportStatus=Passed` 不等于厂商兼容或真实设备验证；所有 R7-C 证据均 `declaredReal=false`、`countsTowardReality=false`。
- `vendorAdapterStatus`、`realityValidationStatus`、真实 deployment Shadow、Controlled Trial 与 Closed Loop 继续保持 Open；DeviceSafe、ProcessSafe 和标准符合性未评估。

## 0.15.0 - 2026-08-12

### Added

- 增加 Windows-only R7-B Deployment Shadow Readiness：`control.domain-pack@2`、控制器 Profile、控制器端只读权限证据、raw capture、Adapter Receipt、时钟/信号映射、外部 provenance 和七项机器可判定检查。
- 增加无证据 `Open` 与合同夹具 `Blocked` 两个确定性场景；合同夹具永久 `declaredReal=false`、`countsTowardReality=false`，不能升级为真实部署证据。
- 增加 Deployment R7-B 网页工作台、manifest/scenario/example/assess API、外部证据 JSON 导入，以及 ADR-0020。

### Changed

- R7 从 R7-A synthetic software contract 扩展到 R7-B vendor-neutral readiness gate；用户尚未选择目标控制器时，不预先伪造 Siemens、FANUC、HEIDENHAIN 或其他厂商 Adapter。
- 真实接入条件现在显式拆为目标控制器、厂商 Adapter、控制器端 authority verifier、capture integrity、clock/signal coverage 与 case-scoped reality gate。

### Verification

- Windows AMD64 / CPython 3.12.10 冻结接受环境全量验证通过：Python `661 passed`，网页 `36 passed`，TypeScript 检查与生产构建通过。
- R7-B 覆盖公共 Run 的 `Inconclusive` 语义、内容身份篡改、非 Windows 结构化 Unsupported、OpenAPI 响应、JSON 证据导入和禁设备控制 UI。

### Boundary

- 本版本不连接控制器，不包含厂商 SDK，不执行 read/subscribe，更不执行设备写入；上传的 JSON 不能自行关闭现实门。
- 厂商 Adapter、真实 deployment Shadow、Controlled Trial、Closed Loop、DeviceSafe、ProcessSafe 和标准符合性仍未实现；下一步需要部署方选定目标控制器并提供只读凭据与可验收环境。

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
