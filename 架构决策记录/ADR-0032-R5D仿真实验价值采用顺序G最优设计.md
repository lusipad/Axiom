# ADR-0032：R5-D 仿真实验价值采用顺序 G-optimal 设计

- 状态：Accepted
- 日期：2026-08-13
- 决策范围：R5-C 条件效应代理模型、R6 v2 冻结候选网格与下一批 synthetic SIL 实验规划

## 背景

蓝图要求 R5 能估计“下一批仿真或设备试验”的价值。R5-C 已提供六维线性特征、两个单位独立的输出头和 15/5/5 空间切分，R6 v2 又冻结了 15×9 共 135 个参数点，但现有流程仍由固定网格或用户目标决定评估点，不能回答“在不执行试验的前提下，哪些未观测点最能补足当前线性设计的认知空洞”。

R5-C 的 split-conformal 半径对同一输出头是常数，适合表达声明边界内的经验覆盖，不适合作为候选间的认知不确定性排序。直接按预测误差、周期或用户目标排序也会把性能偏好误写成信息价值。

## 决策

1. R5-D 是应用层的离线实验规划器，不新增 DomainPack、Core 对象、训练算法、Recommendation、AcceptanceRecord 或设备权限。
2. 输入必须同时携带已通过的 R5-C `ConditionalEffectModelBundle`、原始 `ConditionalEffectDataset` 和 `ConditionalEffectSplitManifest`，并逐项重验三者内容身份与 split 声明。
3. 设计矩阵只使用 15 个 train 样本。validation 和 test 不进入信息矩阵；全部 25 个已观测点都从 135 点的 R6 v2 冻结网格中排除，因此默认候选池为 110 个未观测点。
4. 首版使用与 R5-C 相同的六维归一化特征和 `λ=1e-6` 岭正则信息矩阵 `A = X_train^T X_train + λI`。候选值定义为设计 leverage `x^T A^-1 x`，它只表示线性模型的 epistemic proxy，不是校准后的误差概率、现实收益或安全置信度。
5. 批次按顺序 greedy G-optimal 规则产生：每轮选择当前 leverage 最大的候选，把 `xx^T` 加入信息矩阵后再选择下一点。分数按 15 位有效数字冻结；并列时按 `feedOverride`、`samplePeriod` 升序确定，保证纯 Python 与独立数值 oracle 可复现。
6. 默认批次为 5，允许 1–10。每个 proposal 保留 R5-C 的周期 `s` 与线性跟随误差 `mm` 预测、预计命令样本数、计划 runner 和独立内容身份，但这些预测不参与首版候选排序。
7. 计划固定 `experimentExecutionStatus=NotExecuted`、`modelUpdateStatus=NotPerformed`、`globalOptimalityStatus=NotClaimed`、`permissionLevel=Offline`、`automaticExecutionAllowed=false`、`deviceWriteAllowed=false` 和 `realWorldGeneralizationStatus=Open`。生成新标签后必须创建新的 DatasetSnapshot 与 ModelBundle，才能再次规划。
8. Windows 是唯一验收平台。非 Windows 调用返回结构化 `Blocked + UnsupportedRuntimePlatform`，不得产生 proposal 或正向通过结论。

## 后果

- Intelligence Lab 可以把“当前模型能预测什么”与“下一批最值得补哪些 synthetic SIL 点”连接起来，同时保持规划、执行、数据封存和模型更新为四个不同动作。
- 默认五点批次把冻结候选池的最大设计 leverage 从 `2.51493750502277` 降到 `0.427556838778371`，相对下降约 `82.9993%`；该数值只属于冻结 R5-C/R6 v2 线性设计和数值环境。
- validation/test 继续只承担既有校准与验收职责，不因主动选点回流到训练设计。
- 首版把所有 synthetic SIL 候选视为等采集成本；加入运行时成本、异方差、现实设备风险或多保真信息时必须另行版本化协议。

## 被拒方案

- **按 split-conformal 区间宽度排序**：同一输出头的冻结半径对所有域内候选相同，不能区分候选的信息价值，也不代表 epistemic uncertainty。
- **按预测误差、周期或 R6 用户目标排序**：这是性能偏好或优化问题，不是减少线性设计最坏认知空洞的问题。
- **直接引入贝叶斯优化、强化学习或深度集成**：当前只有 15 个训练点和冻结线性特征；新增先验、噪声模型与依赖会超过首片所需，并降低独立重放能力。
- **规划后自动执行 F3/F4/R4 并重新训练**：会把 plan、execution、label acquisition 和 model update 混成一个不可审计动作，也扩大了当前授权范围。
- **把真实设备试验纳入同一候选池**：仓库没有经授权的真实 capture、成本、安全包线与责任方许可，不能由 synthetic planner 外推。

## 研究依据

- [Hard-Margin Active Linear Regression](https://proceedings.mlr.press/v32/hazan14.pdf) 讨论 G-optimality 与主动线性回归的设计关系。
- [Online A-Optimal Design and Active Linear Regression](https://proceedings.mlr.press/v139/fontaine21a.html) 展示序贯实验设计与主动线性回归的现代研究脉络；Axiom 首版不声称实现其在线算法。
- [Minimax Experimental Design: Bridging the Gap Between Statistical and Worst-Case Approaches to Least Squares Regression](https://proceedings.mlr.press/v99/derezinski19b.html) 说明最坏情形实验设计与最小二乘估计之间的联系；Axiom 只采用有限候选集上的确定性 greedy 近似。
