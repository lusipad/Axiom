# Changelog

本文件记录 Axiom 的用户可见变化。版本遵循语义化版本。

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
