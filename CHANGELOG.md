# Changelog

本文件记录 Axiom 的用户可见变化。版本遵循语义化版本。

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
