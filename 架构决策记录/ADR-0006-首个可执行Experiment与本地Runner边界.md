# ADR-0006：首个可执行 Experiment 与本地 Runner 边界

> 状态：Accepted
> 日期：2026-08-11
> 影响范围：通用框架、有序离散点领域包、CLI、Web API、Point Lab

## 背景

v0.2 的 A/B 能力比较两个已经导入的输出，无法证明两个算法使用了相同输入和参数。要迈向“输入参数、采出结果、评价并反向优化”的长期闭环，首个实现必须真正执行两个 Subject，同时又不能过早引入任意代码执行、通用工作流、设备控制或分布式调度。

## 决策

1. v0.3 的 `ExperimentSpec` 固定为恰好两个不同的 Arm，共享一个输入 Artifact 和一个 `ParameterSet`。
2. `ParameterSet` 必须携带 `parameterSchemaId`；Runner 必须验证它与 Subject 声明的模式一致。
3. 首个 Runner 为 `python-call@1`，仅能解析代码中静态注册的、带版本的 Subject；不接受任意命令、模块名或用户代码。
4. 每个 Arm 独立执行并生成自己的 Observation、Run 和 RunBundle；执行异常或输出类型不符合契约时记录版本化失败原因，不生成伪造的成功谱系。
5. `ordered-point.experiment-comparison.strict@1` 必须接收完整冻结的 `ExperimentSpec`，并重新核对左右 Arm 的 Subject ID/版本、Runner、输入、参数、Experiment 内容标识和 RunBundle 完整性。
6. CLI 和 HTTP 区分“请求无法解析”与“实验得出失败结论”：HTTP 对可解析的业务失败返回结构化报告；CLI 仅在执行、比较和硬门槛全部通过时返回 `0`。
7. Point Lab 是本地 API 的可视化客户端。高于二维的轨迹只能声明为 XY 投影，不能把投影冒充完整几何。

## 被否决方案

- **继续停留在导入式 A/B**：不能冻结共同输入和参数，无法形成真实实验闭环。
- **允许任意命令或 Python 模块**：扩大远程代码执行面，也无法在当前阶段给出环境、资源和隔离契约。
- **立即建设通用 DAG/队列/数据库**：首个双臂确定性实验不需要这些设施，会遮蔽核心契约是否闭合。
- **执行失败时补造空 Observation**：会把“没有观测”错误表达为“观测为空”，破坏谱系和机器判定。

## 后果

- Axiom 第一次能够证明两个内建 Subject 在同一输入和参数下被实际执行并严格比较。
- 新增 Subject 必须显式注册版本、Runner、输入/输出 Artifact 类型和参数模式，不能依赖字符串反射。
- 将来接入厂商进程、容器、设备或远程执行时，必须新增 Runner ID 和相应隔离、资源、环境与安全契约，不能扩大 `python-call@1` 的含义。
- 当前两臂限制是有序离散点首个实现的产品边界，不是通用框架对未来参数扫描或多臂 Experiment 的永久限制。
