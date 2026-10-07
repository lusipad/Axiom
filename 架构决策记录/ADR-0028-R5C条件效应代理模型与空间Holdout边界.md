# ADR-0028：R5-C 使用条件效应双输出代理模型，不把预测升级为优化或现实结论

- 状态：Accepted
- 日期：2026-08-13
- 决策范围：R4 参数研究、R5-C 数据与空间切分、双输出代理模型、域外弃权、R6 关系和权限边界

## 背景

R5-A 已证明可审计数据、残差学习和端侧解释器合同可以闭合，R5-B 已把真实跨设备、跨工况 holdout 独立成现实门；R6 v1 则只在六个固定参数点上完全枚举。下一步需要回答的是“输入参数变化时，周期和物理响应怎样变化”，而不是再造一个语义评分器，也不是立刻让模型替代数学或物理求解器。

如果直接把周期、误差和样本数合成单分，量纲和取舍会被隐藏；如果直接用全部 25 个参数点训练并报告拟合误差，无法证明未见参数点上的插值能力；如果把 synthetic SIL 的高精度解释成真实机床泛化，则会越过 R5-B 的现实证据门。

## 决策

1. R5-C 使用独立 `intelligence.domain-pack@3`，主 Artifact 的 `artifactType` 为 `axiom.intelligence.conditional-effect-model-bundle`，`schemaId` 为 `axiom.intelligence.conditional-effect-model-bundle@1`。它不修改 Core，也不改写 R5-A、R5-B 或 R6 的既有对象和内容身份。
2. 首版参数域固定为 `feedOverride ∈ [0.65, 1.00]`、`samplePeriod ∈ [0.04, 0.08] s`，训练数据来自同一 canonical head-table 路径和同一 R4 synthetic SIL 物理模型的 5×5 完全参数研究。
3. `ConditionalEffectDataset` 是 R5 `DatasetSnapshot` 原则的领域特化：必须冻结治理、选择策略、逐样本 M4/M5/PhysicalResponse 内容身份、已知偏差和覆盖空洞。它不能被称为真实设备数据。
4. 25 个参数点按固定空间策略分成 15 train、5 validation、5 test；同一点只能出现一次。validation 只标定 split-conformal 半径，test 不参与拟合或区间标定。该空间 holdout 只验证声明参数域内、同一路径同一物理模型下的插值，不证明跨拓扑、跨任务、跨设备或跨工况泛化。
5. 模型保留两个独立输出头：`cycleTimeSeconds` 的单位是 `s`，`linearFollowingErrorMaxMm` 的单位是 `mm`。不得相加、加权或改写为万能总分；`commandSampleCount` 保留为确定性来源结果，不在首版回归。
6. 训练侧使用冻结的六项物理启发特征与 ridge `λ=1e-6`。目标运行面继续使用独立纯 Python 解释器；NumPy 与目标解释器的最大绝对差必须不高于 `1e-12`。
7. 独立测试门冻结为：周期 NRMSE `<=0.02`、线性误差 NRMSE `<=0.05`、每个输出 conformal coverage `>=0.80`、域外弃权率 `=1`。域外请求只返回 `Abstained + OutsideDeclaredDomain`，不得外推数值。
8. `syntheticConditionalEffectContractStatus` 与 `realWorldGeneralizationStatus` 必须并存。前者可以由内建 SIL 场景闭合，后者保持 `Open`，只能由 R5-B 的独立真实 holdout 证据推进。
9. R5-C 只提供 Offline、只读预测；`deviceWriteAllowed=false`。它不产生 Recommendation、AcceptanceRecord、DeviceSafe、ProcessSafe、上机许可、在线学习或自动部署能力。
10. R6 v1 仍以 R4 重放结果做六点完全枚举，不静默改成代理搜索。未来扩大参数域时可以显式消费经过独立验收的 R5-C bundle，但每个候选仍须重过数学、物理、现实和权限门，且 Recommendation 内容身份必须版本化更新。

## 后果

- 平台从“逐样本残差学习”扩展到“参数条件对多物理量结果的可审计预测”，仍保持多层评估器而非语义总分器。
- 25 次 R4 参数研究只在场景构建时执行，随后可由内容寻址的数据、训练回执、模型和 parity 回执确定性重放。
- 秒与毫米的含义、阈值和不确定性保持独立，R6 后续可以使用代理模型加速搜索而不隐藏目标权衡。
- synthetic 合同通过不会关闭真实机床泛化门，也不会扩大设备权限。

## 被拒方案

- **周期、误差和样本数加权成单分**：隐藏量纲和用户偏好，也偏离多层通用评估器设计。
- **在完整 25 点上训练并用训练误差验收**：没有独立插值证据，容易把记忆写成预测能力。
- **直接用通用黑盒 AutoML 或神经网络**：首版样本少、合同面窄，增加依赖和解释成本却没有证据收益。
- **首版导出 ONNX**：纯 Python 解释器已经满足 Windows 目标端与 parity 门，格式扩展应由真实部署需求触发。
- **让 R6 自动改用 surrogate 或直接写设备**：会改变既有 Recommendation 语义并越过 R7 权限门。
- **把 synthetic SIL 精度称为真实泛化**：缺少独立设备与工况 holdout，必须保持 Open。
