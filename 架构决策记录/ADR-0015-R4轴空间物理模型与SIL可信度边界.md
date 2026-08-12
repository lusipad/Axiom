# ADR-0015：R4 使用轴空间物理响应 Artifact 并冻结 synthetic SIL 可信度边界

- 状态：Accepted
- 日期：2026-08-12
- 决策范围：R4 主 Artifact、首个物理模型、校准/验证隔离、证据与安全边界

## 背景

R2 已发布 M0–M5 数学参考链，R3 已发布 Windows 文件只读观测合同。R4 需要把数学指令、模型响应和设备格式观测放到同一 Case 中比较，但当前仓库没有真实控制器的独立 paired telemetry，也没有外部计量证据。

Core 一次 Run 保持一个主 Artifact，并把非导入 Runner 的主 Artifact 记录为 `ExecutedSubject` Observation。Domain runtime 只返回 EvaluationReport，不能在执行完成后替换另一个主 Artifact。R3 的时钟/坐标 Claim 只验证上下文身份，不代表已经完成 M5 到 raw frame 的逐样点数值对齐。

如果把 PhysicalModel 本身设为主 Artifact，Observation 会错误表示成“执行后观测到的模型定义”；如果把 R3 trace 设为主 Artifact并使用 simulation Runner，又会把 raw 设备观测错标成模型执行产物。把 command、model、simulation 和 device 塞入 mega-artifact 也会破坏单主 Artifact 与 raw 不可变边界。

## 决策

1. R4 使用 `five-axis.domain-pack@6`；一次 Run 的主 Artifact 是版本化 `five-axis.physical-response-trace`，表示 PhysicalModel 对 validation M5 command 的仿真响应。
2. `PhysicalModelDefinition`、calibration/validation M5 command、R3 MachineObservationRequest、calibration snapshot 和 `PhysicalRunAlignment` 是有类型支持对象，其身份分别进入 provenance；不扩展 Core 公共对象语义。
3. 首个候选模型是逐轴一阶滞后加静态偏置，采样区间采用 exact-ZOH；线性轴和旋转轴按 `mm` 与 `rad` 分开评估。
4. 校准使用冻结 tau 网格搜索、解析 bias 和固定 tie-break。calibration 与 validation 的 pair、command 和 raw trace identities 必须全部不同；泄漏属于结构化失败。
5. synthetic reference observation 由结构不同的两级滞后 oracle、偏置和确定性扰动生成。禁止候选模型自生成观测后自证。
6. 当前 F4 fixture 未激励旋转轴；未充分激励轴必须显式不可辨识，不输出猜测参数或伪 0 总分。
7. R4 Evaluator 独立重放主 response、逐样点对齐并重算三段残差与 closure，不信任 Artifact 或 fixture 的自报结论。
8. synthetic SIL 最多支持模型合同、校准、对齐、残差分解和 holdout fit 等限定 Claim；`physical-model-reality-validated` 必须保持 `Inconclusive`。
9. R4 即使有真实低残差，也不直接发布 `DeviceSafe`、`ProcessSafe`、`safe-to-run` 或设备写入许可；这些至少还需要 R7 的权限、在线停止和责任边界。
10. 当前实现、CI、fixture golden 与发布只支持 Windows AMD64 + CPython 3.12.10；不从 Windows 结果外推 Ubuntu/Linux。

## 后果

- 同一 Case 能在不改 Core 的前提下保存模型执行 Observation，并引用不可变的数学与设备格式证据。
- 模型参数、仿真响应、原始观测和派生残差保持不同内容身份，适合后续 R5 训练数据谱系。
- 首版可以证明框架能防止自验证、泄漏、错位、单位混合与超适用域声明，但不能证明真实设备可信度。
- 加入真实设备时复用 Artifact 和 evaluator 合同；新增 Case 必须冻结控制器、固件、时钟、坐标、工况、校准和 holdout，而不是改写 synthetic fixture 的证据等级。
- 若将来需要把多个派生响应作为独立可寻址对象，应新增明确的派生 Artifact Run/存储能力，不在 Core Observation 中隐式塞入多个主对象。

## 被拒方案

- **PhysicalModel 作为主 Artifact**：它是被执行 Subject/Profile，不是执行后 Observation。
- **R3 MachineTelemetryTrace 作为 simulation Run 主 Artifact**：会把不可变 raw 设备观测错误标记为模型执行产物。
- **math + model + sim + device mega-artifact**：破坏有类型关系、单主 Artifact、独立内容身份和 raw 不可变边界。
- **用候选一阶模型生成 synthetic observation**：形成结构性自验证，无法证明 verifier 能发现模型 mismatch。
- **校准集兼作验证集**：数据泄漏，不能支持 holdout Claim。
- **先上神经网络或通用数字孪生平台**：当前对象、真实数据和可信度门尚未闭合，复杂度不能增加证据强度。
- **合并 `mm` 与 `rad` 为一个默认总分**：量纲不兼容，会制造不可解释排序。
- **首版同时支持 Windows 与 Ubuntu**：扩大验证矩阵但不增加 R4 物理证据，且违反当前发布边界。
