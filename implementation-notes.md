# Implementation notes — Axiom 文档演进

本文件按工作包保留过程记录；后续工作包的裁定会取代较早工作包中已经过时的结论。本文件不是规范来源。

## 工作包 1：数学全景规范与蓝图重构

Plan: 当前任务计划（建立全景规范、重构蓝图、交叉验证）

Summary: 已新增数学全景规范，并将原蓝图重构为 Math Foundation → Algorithm Lab → Physical/Real Machine → Intelligence。两轮独立复审发现的问题均已修正；最终未发现仍会误导实现者的高、中严重度冲突。文档尚未进入代码实现阶段。

### Decisions

- 新增独立的数学全景规范，原蓝图继续承担产品定位和阶段路线职责。
- 数学链使用 M0–M5；物理链从经过验证的 M5 离散命令开始。
- 采用“规范闭合、成熟领域完整参考实现、开放问题报告边界”的口径。
- 物理链统一为 P1 命令链、P2 伺服驱动、P3 机械响应、P4 切削过程、P5 测量反馈。
- 三类拓扑与一般配置数值 IK 的首版范围较大，但这是用户明确锁定的范围；通过分阶段门控制风险，不缩减为占位接口。
- 增加 `Validated` 证据等级；高精度交叉一致不再混入需要严格包含证明的 `Certified`。同时把 `Bounded` 从证据等级拆为独立的最优性状态。
- 测试语料不按 `exact/certified/bounded` 建目录；每个 case 通过 manifest 分别声明证据等级和最优性状态。

### Deviations

### Surprises

- 原蓝图将局部最近点作为轮廓误差核心定义；连续五轴还需要单调进度、源段和位置—姿态同步约束。
- 原 P0–P4 同时混合数学变换和物理反馈，无法表达 IK 路径提升和连续时间参数化，已拆为 M0–M5 与 P1–P5。

### Questions for review

---

## 工作包 2：Axiom 文档体系与 Roadmap 重整

Plan: 审计职责 → 建立文档入口与 Core 规范 → 增加离散点领域包 → 将五轴规范调整为领域包 → 交叉验证。

Summary: 已把产品路线重整为 R0 通用框架 → R1 有序离散点 → R2 五轴数学领域包 → R3 设备只读接入 → R4 物理模型与对齐 → R5 数据集/学习模型 → R6 受约束参数推荐 → R7 受控闭环。正式文档保持为五份；设备、学习、优化的详细规范只在对应阶段启动时创建。

### Decisions

- Axiom Core 是通用评估、实验与证据框架，不是 CNC 语义评分器。
- 外部能力逐级定义，内部对象使用有类型关系组合，不强制所有评估使用 Scenario。
- 有序离散点作为首个可运行领域包；无参考、单位或时间时，只做信息充分的最低层评估。
- M0–M5 全部保留，并调整为 `FiveAxisTrajectoryPack` 的内部数学链；不再作为 Axiom R0/R1 的前置条件。
- 通用证据等级与最优性状态由 Core 规范唯一拥有，五轴规范只说明领域应用。
- 对每个领域仍坚持先数学模型、后物理模型。
- 设备接入先只读，Recommendation 与 AcceptanceRecord 分离；R6 之前禁止自动写入。
- 学习优先面向残差、条件效果、异常和域外检测；为端侧 ModelBundle 预留可复现接口，不提前锁定框架。
- 当前正式文档不拆入 `docs/`，保留两个既有文件名以避免链接迁移；待文档数量或实现资料增加后再评估目录迁移。

### Deviations

- 独立审阅建议立即拆出设备、学习和优化规范；本次选择在 README 登记创建触发条件，避免尚未进入阶段的空壳规范。
- 独立审阅建议进一步把五轴规范拆成三个数学子文档；当前保留单一文件，先解决平台 Core 与领域包的权威边界。

### Verification

- 五份正式文档的本地 Markdown 链接均可解析。
- 每份正式文档只有一个 H1，代码/图表围栏成对闭合。
- 旧的“物理层唯一入口”和“Math F4 后平台才开始”口径已收窄到 FiveAxisTrajectoryPack。
- 独立只读终审未发现会误导后续实现的高、中严重度问题；仅保留旧文件名这一低风险命名历史包袱。
- 尚未进行 Markdown 渲染器级视觉检查，也未进入代码实现。

---

## 工作包 3：实现基线契约闭合

Plan: 修复 P1 契约歧义 → 同步 P2/P3 文档治理问题 → 建立 ADR → 跨文档验证。

Summary: 根据实现基线审计，已把能力状态、无单位离散点、PathProgress、对应策略、离散重建、碰撞/过切和阶段门改成机器可判定契约；此前“没有高、中严重度问题”的历史结论由本工作包取代。

### Decisions

- Core 拆分 `ExecutionStatus`、`MetricStatus`、`CaseOutcome`，并冻结必选指标聚合顺序。
- 无物理单位的有序点使用 `coordinate-unit` 计算内在坐标几何；冻结开放长度、闭合间隙和闭合长度三种指标。
- 五轴 M1–M5 使用统一 `PathProgress`，并引入 `RegularityCertificate`、`NodeEvent`、版本化 `CorrespondencePolicy` 与 `ReconstructionPolicy`。
- M2 检查任务几何扫掠体/名义过切，M3 检查 `Q_free`，M5 按重建策略复核区间；R2 不产生真实设备安全声明。
- 建立四份 Accepted ADR，记录上述长期决策与被拒方案。

### Verification

- 检查 11 份 Markdown：每份恰好一个 H1，代码/图表围栏和展示数学块均成对闭合。
- 扫描 87 个 Markdown 链接，本地目标 0 个断链；未执行外部站点全量可达性和 Mermaid/MathJax 渲染器级视觉检查。
- 旧 Bobrow/Shin–McKay DOI 已替换为与标题匹配的 1985 年论文标识。
- 三路独立只读复核覆盖整体状态契约、碰撞/安全边界及 PathProgress/对应/重建；复核发现的 NodeEvent 碰撞事件、stock 状态转移和 R2 措辞歧义均已修正。
- 仓库仍无实现代码，尚不能运行公式数值回归或两个独立实现的一致性测试；规范已给出后续 fixture 与 StageManifest 的验收要求。

---

## 工作包 4：有序离散指令序列评估器 v0.1

Plan: 冻结最小产品契约 → 以 OPS-C01～C06 和边界条件建立失败测试 → 实现确定性指标、能力状态、参考比较和显式评分 → 增加 CLI 示例 → 独立复核。

Summary: 已完成可运行原型。该版本把产品入口命名为 `DiscreteMotionCommandSequence`，但数据契约仍复用 `ordered-point-sequence@1`；它是有序离散点领域包的首个可运行实现，不引入控制器、G-code 或连续轨迹语义。

### Decisions

- 首版接受二维或三维有序欧氏点，可选单位、坐标系、闭合声明、时间参数和显式参考绑定。
- 无 `ScoreProfile` 时只返回指标、状态、证据和门槛结果，不产生默认总分。
- `ScoreProfile` 必须带版本标识、适用场景、指标方向、归一化端点和权重；评分不能覆盖硬门槛或改变 `CaseOutcome`。
- 第三方库只承担数据校验、单位换算和数值核；Axiom 自己冻结能力语义、状态聚合、确定性 tie-break 和证据结构。
- 采样点之间不声明连续轨迹行为；五轴、设备、机器学习、数据库、插件系统和 Web UI 均延后。

### Deviations

- 本工作包没有宣称完成整个 R0/R1 阶段门；DomainPack 注册、Run/Observation/Claim 生命周期、A/B 编排和持久化仍属于后续平台工作。
- 因用户明确需要“评分”，原型实现了可选 `ScoreProfile`；它不是平台默认总分，也不能改变硬门槛结论。

### Surprises

- `parameter.interval.*` 只依赖合法参数值；缺少物理时间单位时仍可按 `parameter-unit` 报告，不能把它误归入需要 `parameter.time` 的速度/加速度指标。
- 完整 ReferenceBinding 不只是参考对象和对应策略，还必须显式冻结对齐、距离、容差与边界策略；内置策略必须使用规范的完整版本化 ID。
- `InvalidObservation` 和 `NumericalFailure` 可能发生在 Artifact 已成功导入之后，因此不能把这类指标失败一律回写为 `ExecutionStatus = Skipped`。
- 物理单位参考比较在 identity 对齐下还需要双方声明相同坐标系；单侧 frame 缺失只能得到 `InsufficientContext`。

### Questions for review

- 下一工作包优先补通用 `RunSpec / Observation / Claim / DomainPack` 注册面，还是先扩充转角、离散曲率和更高阶时间指标？

### Verification

- 先观察到 7 个测试模块因公共 API 不存在而收集失败，再实现到全部通过，保留了 TDD 红—绿证据。
- `.venv` 下运行 `pytest`：58 项通过；覆盖 OPS-C01～C06、输入失败、状态聚合、单位、参考 tie-break、时间间隔、显式评分、CLI 与确定性重放。
- `compileall`、`pip check` 和已安装的 `axiom evaluate examples/basic-evaluation.json` 均通过。
- 三路独立只读复核最终均确认当前“有序离散点评估器 v0.1 可运行原型”范围内没有剩余 P0/P1；完整 R0/R1 平台对象仍明确列为后续，不混入本次交付声明。

---

## 工作包 5：v0.1 测试加固

Plan: 审计既有测试 → 补状态/单位/确定性/评分/CLI 高价值回归 → 以失败测试暴露分类缺陷 → 最小修复 → 全量验证。

Summary: 已把测试从 58 项扩充到 92 项，并新增阈值单位换算、参考策略契约、距离变形性质、评分双向归一化、CLI 退出码等回归证据；补测暴露的两类单位状态错误已做最小修复。

### Decisions

- 不新增覆盖率或 mutation testing 依赖；优先测试规范状态、数学性质和用户可见 CLI 行为，而不是追求行覆盖率数字。
- 把 `coordinate-unit` 与 `parameter-unit` 统一视为“可计算但物理尺度未知”的结果标记。
- 物理单位施加到真正无量纲的指标时是契约不适用；施加到上述未定尺度结果时是上下文不足。

### Deviations

- 原任务只要求“补测试”，但失败测试证明 `point.count <= 1 mm` 被误分类为 `Inconclusive`；最小修复为 `NotApplicable → Invalid`。
- 失败测试还证明 `parameter-unit` 遇到物理阈值/评分被误分类为单位不兼容；最小修复为 `InsufficientContext`，不猜测秒。

### Surprises

- 阈值和评分原先对 `None`、`coordinate-unit`、`parameter-unit` 三类单位状态没有采用同一判定表，导致相邻路径出现不同语义。

### Questions for review

### Verification

- 全量 `pytest`：92 项通过。
- 新增测试覆盖阈值四种运算符与单位换算、未知指标与可选指标中立性、ReferenceBinding 版本/容差错误、有向最近距离和 Hausdorff 性质、刚体旋转/尺度/反转变形关系、评分夹断与单位换算，以及 CLI 的 0/1/2 退出码。

---

## 工作包 6：CNC 工程合成场景与工具验收

Plan: 冻结 CNC 运动语义与合成边界 → 生成可执行请求及预期清单 → 增加契约、独立数学复算和 CLI 测试 → 全量验证。

Summary: 已建立 8 个确定性 CNC 工程合成场景，覆盖 G1 直线、G2 四分之一圆弧、G3 闭合圆、G3 螺旋下刀、带时间抖动的拐角采样、缺失时间戳的数据质量边界，以及名义轮廓对比的通过/失败样本。每个 JSON 都是完整的 `axiom evaluate` 请求，`manifest.json` 冻结预期状态、指标、精确能力集合、溯源字段和退出码。

### Decisions

- 数据语义依据 LinuxCNC 官方 G-code 与轨迹规划文档，但坐标和时间值由工程规则确定性构造，不冒充厂商控制器或真实机床日志。
- 圆弧、圆和螺旋仍按离散折线评估；测试明确检查折线长度小于对应解析曲线长度，避免把采样近似写成连续几何真值。
- 轮廓观测使用 identity 对齐和 index-paired 对应；通过样本最大偏差为 0.025 mm，失败样本含 0.08 mm 局部偏差，硬门槛固定为 0.03 mm。
- 失败样本是验收套件的预期成功：评估执行成功、Case 失败、CLI 返回 1，证明总分不能抵消硬门槛。
- 缺少时间戳的样本固定为 `Skipped + Inconclusive + exit 1`，把“数据不足”和“实际超差”区分开。
- 不为场景引入 G-code 解析器或设备模型；当前输入仍是有序采样点、可选时间和显式参考绑定。

### Deviations

- “真实 CNC 场景”解释为遵循真实运动语义的工程合成数据，而不是未经提供的数据源生成“实测数据”。

### Surprises

- 首轮独立复算测试错误地对相邻序列使用等长 `zip(strict=True)`，在 22 项契约与 CLI 检查已通过时暴露 5 个测试自身错误；修正为合法的 `n-1` 相邻对后，场景测试全部通过。

### Questions for review

- 下一批数据应优先来自可审计的控制器/测量日志，还是继续补刀补、进退刀、重复点和不合法时间参数等合成边界场景？

### Verification

- `tests/test_cnc_scenario_files.py` 对清单完整性、逐场景验收契约、两次确定性重放和 CLI 退出协议执行参数化检查。
- 使用 Python 标准库独立复算折线长度、圆半径/方向、闭合段、螺旋 Z 单调性、时间间隔和逐点轮廓偏差，避免只用被测实现证明自身。
- 场景专项测试 32 项通过；安装后的 `axiom.exe` 逐文件运行 8 个请求，6 个通过、1 个按预期超差失败、1 个按预期因缺少时间戳得出不确定结论。
- 提交前安全审查为 CLI 冻结 8 MiB 文件上限，为序列冻结 100,000 点上限，并在距离矩阵和当前 Fréchet 路径实现分配前执行复杂度预算；超限明确返回 `UnsupportedCapability / ComplexityBudgetExceeded`。
- 提交前数值复核修正了有限输入运算溢出被误报为 `Computed` 的问题；几何、时间、参考距离和评分端点溢出现在返回 `NumericalFailure / NonFiniteComputation`。
- 参考能力支持性检查先于上下文检查，不支持的策略不会被误报为上下文不足；业务容差不再参与数学最优解的并列判定。
- 全量 `pytest`：137 项通过；`compileall`、`pip check` 与 `git diff --check` 通过。
- 两路独立只读终审未发现 P0；对能力集合断言过弱、按清单索引取场景、参考策略绑定固定指标以及 G94/G64 措辞过强的问题均已修正。

---

## 工作包 7：R1 v0.2 导入式 A/B 比较闭环

Plan: 保留现有 `evaluate` 数值内核与 JSON 契约 → 增加静态 DomainPack 与最小 Run 谱系 → 实现严格兼容的 Run A/B 比较 → 接入 CLI、CNC Case D fixture 与使用文档 → 全量验证和独立复核。

Summary: 已完成 R1 v0.2 的导入式 A/B 比较闭环：内建有序离散点 DomainPack、确定性 Run/Observation/Claim 谱系、严格兼容性报告、逐指标与分数比较、CLI、CNC A/B 导入数据及正式契约均已落地。

### Decisions

- 首版 A/B 比较只导入两个 Subject 已产生的有序离散点结果，不负责启动厂商算法、控制器或设备。
- 比较采用版本化严格策略：Case、Artifact schema、执行结果策略和 MetricDefinition 必须一致；缺少 Adapter 时不猜测语义等价性。
- `evaluatorVersion` 和数值环境差异必须记录，但不自动禁止回归或跨实现比较。
- `RunSpec`、Observation、RunBundle 和 Comparison 使用独立的确定性内容哈希；墙钟时间和随机 UUID 不进入内容身份。
- 现有 `ExecutionStatus`、`MetricStatus`、`CaseOutcome` 聚合语义以及 `axiom evaluate` 对外行为保持不变。

### Deviations

- 本工作包实现的是“导入两个 Subject 输出并比较”，不是启动算法的 Experiment Runner；ParameterSet 调度、持久化和厂商执行适配仍延后。
- 静态 DomainPack 注册面已经公开，但 v0.2 只有内建 `ordered-point.domain-pack@1` 绑定 evaluator；其他描述明确返回 `DomainPackEvaluatorUnavailable`，避免伪造谱系。
- 首版只支持精确兼容，不提供单位、坐标系或 schema Adapter；这一保守边界已写入 ADR-0005。

### Surprises

- 既有 CNC `observation-pass` 与 `observation-fail` 请求的指标、门槛和 Profile 相同，但 `caseId` 不同，因此不能直接充当严格 Case D 比较输入；需要单独冻结共享 Case 的 A/B fixture。
- 内容身份不能被统一“规范化”：Artifact 中未提供语义与明确 `null` 是不同输入事实；只有 Case/Profile 已定义为等价的默认项可用于兼容身份归一化。全局折叠曾触发既有可复现性测试失败，最终拆分为输入身份和比较身份两条哈希路径。

### Questions for review

### Verification

- 全量 `pytest`：161 项通过；新增覆盖 DomainPack 注册边界、Run 谱系与 Claim、默认值身份、兼容矩阵、逐指标方向/差值、CLI 文件预算和 0/1/2 退出码。
- `compileall src tests`、`pip check`、`git diff --check` 通过；安装后的 `axiom evaluate` 与 `axiom compare` 完成端到端验证。
- CNC A/B 通过/超差样本得到兼容报告及两项参考误差差值；Case 不兼容变体不输出差值并返回 1；格式错误返回 `MalformedComparisonSpec` 和退出码 2。
- 代码终审在修复默认值哈希和未绑定 DomainPack 借用 evaluator 两项高风险问题后给出 Approve；独立验证复跑 161 项并给出 Pass。
- 正式规范增加 ComparisonSpec/ComparisonReport、strict@1 兼容矩阵和 ADR-0005；5 份变更文档的 H1、围栏和本地链接检查通过。

---

## 工作包 9：R0/R1 边界硬化与 R2 Math F0 入口

Plan: 冻结可移植 fixture 身份 → 把 DomainPack 描述符补成可执行运行时绑定 → 建立显式 Artifact Adapter → 交付 FiveAxis F0 机器契约 → 全量回归、网页验收与发布。

Summary: 已完成并发布为 v0.4.0。本工作包交付 R2 的 F0 契约入口，没有实现 M1～M5 数值求解器，也没有宣称五轴几何、运动学、连续时间、区间碰撞或设备安全已经通过。

### Assumptions

- 现有 Point Lab 与有序离散点 JSON 是稳定的第一领域接口，必须向后兼容。
- Core 只承载领域中立的 Artifact envelope、运行谱系、状态和证据；五轴字段只能存在于领域包。
- DomainPack 描述符与进程内 callable binding 分离；本阶段不实现动态插件加载或 Solver/SUT 的文件、进程、RPC 传输。
- 五轴采样位置视图只能通过显式 Adapter 降维成有序欧氏点；混合关节向量不得被当作 Cartesian 点。
- Case D 的完整 RunBundle 身份包含数值环境，因此跨环境冻结可移植输入/报告身份，完整 bundle 身份用于同环境完整性重验。

### Success criteria

- 第二个领域包无需修改 Core 调度分支即可注册并执行，描述符但无 binding 的领域包仍明确失败。
- FiveAxis F0 manifest 冻结能力、fixture、策略、数值环境、期望状态/Claim 与容差，并拒绝隐式单位、坐标和非法版本。
- F0 执行不产生任何 R2 正向数学 Claim，缺碰撞或重建上下文时只能给出不确定/不支持结论。
- R1 Case A/C/D fixture 与机器可读策略、容差和身份契约闭合；Python、CLI、HTTP 结果继续一致。
- 全量测试、构建、安装检查、网页交互验收与内容哈希重验通过后才进入发布。

### Decisions

### Deviations

### Surprises

### Verification

- `five-axis.domain-pack@1` 与有序离散点通过同一 Core 运行路径执行；未绑定领域包、解析失败和 Evaluator 异常都有结构化状态。
- F0 manifest、package fixture、显式 Cartesian sampled-view Adapter、Case D 可移植身份和网页边界通过自动化验收。
- v0.4.0 的 wheel/sdist、内置网页资源和 GitHub Release 已由发布工作流生成。

---

## 工作包 10：R2 Math F1 连续几何参考栈与网页 UI

Plan: 修复 DomainPack 多 Artifact 通用契约 → 冻结 M0/M1/M2 机器模型 → 实现连续几何/对应/任务碰撞证据 → 接入 runtime、API/CLI 与网页 UI → 全量验收并发布。

Summary: 已完成 v0.5.0 发布候选。F1 只允许 `GeometryValid` 与 `TaskGeometryCollisionFree`；不产生 M3 运动学、M4 时间律、M5 区间重建或设备安全结论。

### Assumptions

- 一次 Run 保持一个主 Artifact；同一 DomainPack 通过通用 descriptor 声明多个 Artifact 类型。
- 权威 M0 对象是规范化 JSON IR；首个文本输入为严格的 `axiom-cl-subset@1`，不声称完整 ISO/厂商方言兼容。
- 复用 NumPy/SciPy 数值核，不新增必选依赖；认证碰撞先限定为明确声明的解析基本体。
- F0 sampled view 保留为派生视图，不升级为 F1 连续真值。

### Decisions

- 采用通用多 Artifact descriptor + 单主 Artifact Run；拒绝每阶段一个 DomainPack 和无类型 mega-payload。
- 拆分任务几何碰撞与后续配置空间碰撞能力，避免 F1 Claim 暗含 M3。
- 有限采样只能产生 Observed/Validated；Exact/Certified 必须有解析或保守连续区间证书。

### Deviations

### Surprises

- 当前 `DomainPack.artifactType` 的单值约束是进入 F1 前必须修复的 R0 契约缺口，而不是 FiveAxis 私有扩展点。
- Core 的 `caseOutcome = Passed` 表示 Case 预期得到满足，不能替代领域标准 Claim；网页必须单独显示 `executionStatus`、`caseOutcome` 和 Claim verdict。
- 场景切换时 Manifest 必须随 `scenarioId` 一起切换，否则冻结身份会错误复用默认场景。

### Questions for review

### Verification

- Python 全量测试、`compileall`、前端 TypeScript 检查、4 项 UI 测试和生产构建通过。
- 三个工程化参考场景均通过公共 `RunSpec → RunBundle` 路径；名义通过、几何超差和夹具碰撞分别产生预期 Claim/Evidence。
- v0.5.0 wheel/sdist 已构建，并在全新虚拟环境中验证 CLI、内置网页、健康接口、场景目录和夹具碰撞 `Refuted` 声明。
- 桌面 1440×900 与移动 390×844 视觉验收通过；最终生产页面刷新后无新增 console error 或 warning。
- Manifest 场景绑定与发布前代码审查均由独立只读复审确认通过。

## 工作包 11：R2 Math F2 运动学参考栈

Plan: 冻结三类参考 MachineProfile 与 M3 契约 → 实现通用 FK、闭式/数值集合值 IK → 构造连续分支图与限位/wrap/奇异性证书 → 实现 `Q_free` 连续机构碰撞 → 接入 runtime、场景、API/UI 与阶段 Manifest → 全量验收并发布。

Summary: 已完成 v0.6.0 发布候选。F2 交付三类 canonical MachineProfile、M2→M3 首个认证子集、通用 FK、闭式/数值 IK、连续分支与轴限位/奇异性证书，以及路径级 `Q_free` 连续碰撞反例；它不产生 M4/M5、真实设备或加工过程安全声明。

### Assumptions

- 继续复用 NumPy/SciPy/Pydantic，不新增必选运动学依赖；Axiom 自己冻结机器语义、分支和证书格式。
- 首版任务姿态保持轴对称刀轴，不把绕刀轴 roll 引入默认五轴对象。
- 三类 canonical Profile 是公开数学基准，不映射具体厂商设备精度或安全能力。

### Decisions

- `MachineProfile` 按工件侧/工具侧局部运动链显式建模，通用 FK 固定为 `T_W^-1 T_T T_tool`，见 ADR-0010。
- 闭式 IK 枚举姿态分支与周期 wrap；一般数值 IK 未找到解保持 `Inconclusive`。
- `KinematicallyFeasible`、`ConfigurationCollisionFree` 与 F1 `TaskGeometryCollisionFree` 分开发布，禁止证据代用。

### Deviations

- 一般数值 IK 只发布 `Validated` 证据，不提升为 `Exact`；三类 canonical Profile 的闭式 IK 才承担确定性基准职责。
- 首个 M2→M3 认证子集限定为直线位置、恒定刀轴、固定分支/wrap 和局部幂基线性关节路径；更一般连续路径留给后续 F2 扩展，不虚构全覆盖。
- 标准 `ConfigurationCollisionFree` Claim 只允许由完整路径覆盖产生；点查询和单段诊断即使无碰撞也不能冒充路径级结论。

### Surprises

- F0 与 F1 各自已有 Manifest 模型；F2 应复用 F1 证据类型但使用新的 M0～M3 descriptor/Claim 白名单，不能放宽 F1 的越级保护。
- 仓库没有可直接复用的 SE(3) 或机床 IK 内核；可复用的是 Core/DomainPack/证书体系，而不是运动学算法本身。
- 机构碰撞反例必须覆盖“端点均安全但区间内部碰撞”，否则离散采样很容易给出错误的路径安全印象。
- `caseOutcome = Passed` 仍只表示场景预期得到满足；碰撞反例场景可以成功验收，同时其 `ConfigurationCollisionFree` 领域结论必须为 `Refuted`。

### Questions for review

### Verification

- Python 全量测试 407 项、前端 6 项测试、TypeScript 检查、生产构建、F2 定向 Ruff 与 mypy 均通过。
- 三类 canonical Profile 均通过公共 `RunSpec → RunBundle` 路径；运动学可行场景产生 `KinematicallyFeasible = Supported`，区间内部碰撞场景产生带 `sigma = 0.5` witness 的 `ConfigurationCollisionFree = Refuted`。
- v0.6.0 wheel/sdist 已构建；wheel 在全新虚拟环境安装后完成版本、内置网页、场景目录和公共 HTTP 评估端到端重放。
- 桌面 1280 px、紧凑 1024 px、反例场景、证据/Claim 边界和浏览器 console 均完成交互验收；最终视觉复核通过且未发现回归。
- 独立代码终审和交付验证均给出 Pass；发布工作流增加安装后 F2 端到端烟测，防止仅验证源码工作区。

## 工作包 12：R2 Math F3 连续时间与离散重建参考栈

Plan: `.omx/plans/f3-time-discrete-reference-stack.md` → 冻结 F3 M4/M5 机器契约 → 实现二阶解析 TOPP 与严格 Jerk 可行证书 → 实现固定周期采样/区间重建 → 接入 runtime、场景、API/UI → 全量验收并发布 v0.7.0。

Summary: v0.7.0 发布候选已完成实现、双环境验收与安装后制品烟测。F3 只允许 `ContinuouslyFeasible` 与 `IntervalCertified`；不宣称通用 Jerk 全局最优、真实设备安全或加工过程安全，R2 最终阶段门仍属于 F4。

### Assumptions

- 保持 v0.6.0 的 F2 Artifact、MachineProfile 与 Claim 语义冻结；F3 使用独立 MotionConstraintProfile 绑定动态约束。
- 首个 Certified 子集限定为线性 `q(sigma)` 的 stop-to-stop block，复用现有 NumPy/SciPy，不新增必选依赖。
- dwell/feed 与边界状态由 F3 Profile 显式绑定，不从 F2 事件中猜测缺失物理语义。

### Decisions

- 二阶线性子集使用解析三角/梯形时间律并独立重放，允许 `ProvenOptimal`；Jerk 子集使用七次 smoothstep、保守代数上界与向外舍入，只标记 `FeasibleOnly`。
- M5 明确区分 SampledTrajectory 与 DiscreteCommand；reference-M4/polynomial 可形成正向区间证书，FOH/ZOH 严格限制能力范围。
- 不跨量纲汇总误差；每项误差保留 quantity、unit、source、bound 与 method。

### Deviations

- reference-M4 区间验证直接复用独立 M4 verifier 重放源轨迹，没有用采样器内部的松弛幂基上界替代来源真值。
- polynomial 内部违规反例通过比 M4 更严格的 M5 命令速度约束构造，以证明“连续源轨迹合格”不等于“离散命令区间合格”。
- 未新增运行时依赖；F4 的 Reference Solver/SUT 传输 Adapter、真实驱动器与加工过程证据仍按 Roadmap 延后。

### Surprises

- 最初的 Hermite 幂基绝对值界过于松弛，会把本可独立证明的 reference-M4 区间误判为不支持；改为重放 M4 verifier 后闭合。
- 多轴状态聚合曾允许后续 `Unsupported` 覆盖先前 `Refuted`；现已固定为反例优先，避免丢失可验证的失败证据。
- 发布前终审发现离散命令场景的 Manifest 与 UI 仍偏向 sampled-only；现已改为按场景声明真实 M5 artifact，并统一以 `m5Artifact` 展示两类证据。
- 真实浏览器把 JSON 中的 `-0` 规范为 `0`，曾使默认场景的 M5 内容身份在 GET→POST 往返后失效；canonical hash 现按浏览器 JSON 数值语义规范零值，同时保留完整内容寻址校验。
- RunBundle API 使用 `claimDefinitionId`，但共享前端类型曾读取 `claimId`，导致真实 Supported 证据显示为 Inconclusive；F1～F3 已统一到公开 API 字段，Manifest 的 `expectedClaims[].claimId` 保持不变。
- NumPy 2.4/2.5 的 SVD 最低位差异会污染 M3 内容身份；证据现按 12 位有效数字规范化，而具体 Python/NumPy 版本只绑定 RunBundle。所有奇异性门槛仍使用未舍入 binary64 值，禁止让可移植身份策略改变运行结论。
- F3 runtime 最初为每项 metric/capability 重复执行连续轨迹与区间重建 verifier；现改为每次 Run 各执行一次并复用不可变结果，输出契约保持不变。

### Questions for review

- 无阻塞问题；F3 的公开 Claim、数学能力边界与 v0.7.0 发布范围均已在 ADR-0011 冻结。

### Verification

- Python 3.14 / NumPy 2.4 与发布约束 Python 3.12 / NumPy 2.5 均通过 454 项全量测试；F3 覆盖率 88.47%，`compileall` 与本轮 Python 文件 Ruff 检查通过。
- 前端 3 个测试文件、10 项测试通过；TypeScript 检查与 Vite 生产构建通过。
- 7 个 F3 场景覆盖三类 canonical Profile、dwell/mandatory-stop、二阶解析最优、ZOH 不支持与 polynomial 区间内部违规。
- wheel/sdist 已重建；wheel 在全新 NumPy 2.5 环境安装后完成版本、CLI、内置网页、健康接口和公共 HTTP RunSpec 往返，canonical sampled 得到两条 `Supported`，second-order discrete 得到 `Supported` / `Inconclusive`，且均未越权产生设备/过程/模型碰撞安全 Claim。
- 1280×720 桌面与 375×812 移动端完成真实浏览器验收：canonical 为 Supported、ZOH 为 Inconclusive、polynomial 反例为 Refuted，重新评估稳定、下载可用、控制台 0 错误、移动端页面级横向溢出 0 px；最终视觉验收 100/100。
- `/qa` 发现的浏览器 signed-zero 与 Claim 字段两项问题均已修复并回归，健康分数 93→100；两轮独立代码终审确认 0 个 P0/P1/P2。

## 工作包 13：R2 Math F4 参考求解器/SUT 验收闭环

Plan: `.omx/plans/f4-reference-system-acceptance.md` → 冻结 Windows-only F4 Adapter/运行契约 → 补齐 M5 重建区间碰撞与五项总 Claim → 三拓扑 Reference/SUT 交叉验收 → 接入 RunBundle、API/UI 与 R2 总门禁。

Summary: 已完成。F4 现在是 R2 的闭合数学验收门：`five-axis.domain-pack@5`、`five-axis.solver-adapter@1`、独立 reference/SUT in-process adapters、三类 canonical solver 拓扑、`adapter-input-hash-mismatch` 与 `interval-interior-collision` 反例、M0–M5 manifest、以及七条数学 claim 都已收口。R2 现已关闭，后续只进入 R3 设备只读接入。

### Assumptions

- 当前交付矩阵只包含 Windows AMD64 + CPython 3.12.10；Ubuntu/Linux 不作为实现、CI 或发布阻断条件。
- 继续复用现有 Python/Pydantic/FastAPI/React/NumPy/SciPy，不新增运行时依赖。
- 首版 SUT 是仓库内可审计 subject，不代表厂商控制器；真实外部传输和设备只读观测分别留给后续 Adapter 版本与 R3。

### Decisions

- 首版选用静态进程内 `five-axis.solver-adapter@1`；Reference/SUT 身份、实现版本、role 和 receipt 全部进入 F4 typed request，顶层 Run subject 只代表验收运行。
- 新增 `five-axis.domain-pack@5`，一次 Run 继续保持 M5 `DiscreteCommand` 单主制品；跨阶段上下文通过有类型 request/evidence 和 content ID 绑定。
- M5 polynomial reconstruction 必须重新执行连续配置碰撞验证；M3 证书不能代替 M5 区间证书。
- 单次 Run 显式重投影 R2 完整 7 条标准数学 Claim，`F4StageAcceptanceReport` 聚合三拓扑和反例矩阵；不修改 ordered-point 全局比较器。

### Deviations

- 无；本包未把 F4 误写成设备安全、过程安全或控制器上机许可。

### Surprises

- F4 的网页工作台数据面与 API 面已能共享同一份 example payload，前提是严格保持 `manifest / scenario / source / artifacts / evidence / acceptanceReport` 分块。

### Questions for review

- 无；后续如果扩展 R3，仍需先保持 F4 数学闭环不变。

### Verification

- `tests/test_five_axis_f4_api.py` 已覆盖 F4 manifest / scenarios / example payload 端点与正负例契约。
- `tests/test_five_axis_runtime_f4.py`、`tests/test_five_axis_adapters_f4.py`、`tests/test_five_axis_collision_f4.py`、`tests/test_five_axis_models_f4.py`、`tests/test_five_axis_scenarios_f4.py` 覆盖了参考/SUT 闭环、碰撞反例、模型约束与场景构造。
- README 中的 F4 快速开始示例使用 `axiom.evaluate_run` 与 `axiom.five_axis.f4_example_run_spec`，与当前导出一致。

## 工作包 14：R3 Windows 设备只读观测闭环

Plan: `.omx/plans/r3-read-only-machine-observation.md` → 冻结只读设备观测合同 → 实现 Windows 文件遥测导入与 paired/unpaired 谱系 → 接入通用 RunBundle、API 与 Machine Lab → 完成 Windows 发布门。

Summary: 已完成。首个具体源选择 `axiom.windows-file-telemetry-source@1`，只读取已经落盘的 JSON capture；设备观测作为独立 `machine-observation.domain-pack@1` 接入，并通过通用 `importRunnerIds` 与 `contextHashes` 承载导入来源和支持对象身份，不把设备语义塞入 Five-Axis F4。

### Assumptions

- 当前交付矩阵继续只包含 Windows AMD64 + CPython 3.12.10；Ubuntu/Linux 不作为实现、CI 或发布阻断条件。
- 当前没有可稳定访问且许可、版本和权限均已确认的真实厂商控制器，因此首片以明确标注的合成/仿真文件回放证明数据合同，不冒充真实设备证据。
- R3 是可信只读采集链，不是 live control；设备写入、启动、程序传输和联锁操作全部排除。

### Decisions

- 原始 `MachineTelemetryTrace` 是唯一主 Artifact；DeviceProfile、ClockMapping、CoordinateAlignment 和 MachineRunLineage 作为有类型上下文存在，派生结果不得覆盖 raw frames。
- MachineRun 必须显式为 paired 或 unpaired；paired 同时绑定 baseline RunBundle、M5 内容身份和七项 F4 数学 Claim，unpaired 禁止伪造数学来源。
- R3 只发布 raw integrity、read-only capture、lineage completeness、clock alignment 和 coordinate context 五类数据可信性 Claim；Evidence 上限为 Observed。
- Machine Lab 永久显示 `READ ONLY / NOT DEVICE SAFE`，不提供任何设备操作控件。

### Deviations

- 无；当前没有引入网络、轮询、厂商 SDK、新依赖或设备写入路径。

### Surprises

- MTConnect 官方模型浏览器已把 2.7 标为稳定版、2.8 标为开发版，且合规实现还需要单独确认 Implementer License；因此本工作包只把它保留为未来 live source 候选，不宣称兼容。

### Questions for review

- 无阻塞问题；首个真实厂商 source 只有在设备、协议版本、许可和最小权限都可验证后才进入后续工作包。

### Verification

- Windows 本地验收环境全量 Python 为 531 项通过、1 项按精确 CPython 3.12.10 环境绑定规则跳过；R3/Core/CLI/F4 定向回归为 70 项通过、1 项环境跳过。
- 前端 5 个测试文件、16 项测试通过；TypeScript 检查、Vite 生产构建与真实 API 浏览器回归通过，视觉终审为 93/100。
- 干净构建的 `axiom_evaluator-0.9.0` wheel 只包含当前两个网页资源与完整 R3 package fixtures；安装后 paired/forbidden 场景和内容身份 smoke 通过。
- `pip-audit` 未发现已知依赖漏洞；真实控制器协议、live sampling、设备写入和 Ubuntu/Linux 均未测试，也不属于本阶段承诺。

## 工作包 15：R4 物理模型与现实对齐参考链

Plan: `.omx/plans/r4-physical-model-reality-alignment.md` → 冻结物理模型、响应 Artifact 与数值对齐合同 → 用独立 SIL oracle 闭合 calibration/holdout/反例 → 接入 RunBundle、API 与 Physical R4 网页 → 完成 Windows 发布门。

Summary: 实施中。当前目标是 `R4.0 synthetic SIL contract slice`，不是宣称真实设备 reality gate 已关闭。

### Assumptions

- 当前实现、CI 和发布继续只支持 Windows AMD64 + CPython 3.12.10；不实现或验证 Ubuntu/WSL。
- 当前没有可追溯的真实控制器 paired telemetry，首版只能证明 synthetic SIL 合同与验证器可证伪性。
- F4 canonical M5 只充分激励部分线性轴；未激励的旋转轴参数不可辨识。

### Decisions

- 采用 `five-axis.domain-pack@6`，以 `PhysicalResponseTrace` 作为模型执行后的单主 Artifact；模型、M5、R3 raw、标定和对齐是有类型支持上下文。
- 首个候选为逐轴一阶滞后 + bias + exact-ZOH；reference observation 用结构不同的两级滞后 oracle 生成，避免自验证。
- calibration/validation 的 pair、command、trace identity 必须三重隔离；linear `mm` 与 rotary `rad` 指标分开。
- synthetic Case 永久保持 reality validation `Open/Inconclusive`，禁止 DeviceSafe、ProcessSafe、safe-to-run 和设备写入。

### Deviations

### Surprises

- R3 `ClockMapping` / `CoordinateAlignment` 目前只证明上下文身份，不提供 M5-relative 数值时间锚点或变换参数；R4 必须新增并重算 `PhysicalRunAlignment`。
- DomainRuntimeBinding 只返回 EvaluationReport；把模型执行结果显式建模为输入主 `PhysicalResponseTrace`，由 evaluator 独立重放，可在不改 Core 的前提下保持 ExecutedSubject 语义。

### Questions for review

- 真实控制器 source、轨迹激励矩阵和外部计量设备将在用户提供具体设备、许可和数据后单独冻结，不阻塞 synthetic contract slice。

### Verification

- 待实现完成后填写 Windows 定向/全量测试、网页、wheel、安装后 smoke 与发布证据。

## 工作包 16：R5-A 数据集与学习模型合同片

Plan: `.omx/plans/r5-intelligence-contract.md` → 冻结 DatasetSnapshot / split / lineage / governance / OOD / X-only 残差 / ModelBundle 规范 → 同步 README、蓝图、ADR 索引与工作记录 → 做 Markdown 结构校验。

Summary: 已新增 R5 规范和 ADR-0016，并实现 Windows-only R5-A synthetic learning 合同片。`DatasetSnapshot`、分组 split、治理、X-only 残差、OOD、split conformal、JSON ModelBundle、独立纯 Python 目标解释器、有类型 API 和 Intelligence UI 已接入公共 Run；`syntheticLearningContractStatus=Passed`，`realWorldGeneralizationStatus=Open`。

### Decisions

- R5-A 先定义可审计数据面，再谈更复杂的学习模型和真实泛化。
- DatasetSnapshot、SplitManifest 和 DatasetGovernanceManifest 必须是强约束对象，不能退化成目录约定。
- 学习顺序固定为 OOD 优先、X-only 残差头优先，Y/Z/B/C 仍保持未验证状态。
- ModelBundle 使用 JSON + 独立纯 Python 目标解释器，不把 ONNX 写成首版锁定格式。
- typed API/UI、禁语边界和双状态门必须一起出现，避免把学习合同误写成设备安全合同。

### Deviations

- 原计划先完成文档合同，随后在同一工作包继续落地运行时；实现仍严格限制在 R5-A synthetic slice，没有扩展到真实泛化、设备写回或在线学习。
- 全轴学习 spike 未达到门槛，最终只让 X 轴 residual head 进入 `Validated`；Y/Z 保持 `NoValidatedImprovement`，B/C 保持 `InsufficientExcitation`。

### Surprises

- 第一轮全轴学习 spike 未达到预声明改善门，X-only 残差候选才是当前可接受的合同片。

### Questions for review

- R5-B 需要用户提供具有许可、DeviceProfile、clock/coordinate context 和独立 pair identity 的真实只读 holdout；在此之前真实泛化门不关闭。

### Verification

- Windows 本地 Python 全量 `592 passed / 1 skipped`；R5-A 定向 Python/API `23 passed`。
- 网页全量 `22 passed`，TypeScript 检查和生产构建通过；三档响应式视觉终审 `95/100`，无控制台错误。
- X 轴独立 test split 的 RMSE 改善为 `50.43%`，OOD 检出率 `100%`，split conformal coverage `83.33%`，训练端与纯 Python 目标解释器最大差 `1.39e-17`。
- package fixture 冻结 Dataset、split、training receipt、ModelBundle 和 parity receipt 内容身份；wheel 安装后 smoke 与冻结 Windows 3.12.10 发布工作流在制品阶段继续复验。

## 工作包 17：R7-A Windows Shadow 受控运行合同

Plan: `.omx/plans/r7-controlled-runtime-shadow.md` → 冻结 R7 权限与状态机边界 → 实现 synthetic shadow、故障闭锁与审计 Artifact → 接入公共 Run、API/UI → 完成 Windows 发布门。

Summary: 已完成 Windows-only R7-A synthetic shadow contract。独立 AcceptanceRecord、控制包线、fail-closed admission、状态迁移、停止/基线保留 receipt、公共 Run、typed API 和 Controlled Runtime 网页工作台均已闭合；这不等于 Controlled Trial、Closed Loop、设备安全或功能安全合规已经完成。

### Assumptions

- 当前没有真实 paired holdout、真实 shadow Observation、认证身份系统、厂商写协议或安全 PLC receipt。
- 当前交付只支持 Windows AMD64 + CPython 3.12.10，不实现 Ubuntu/WSL。
- Synthetic shadow 只能证明软件合同和故障闭锁可复验，不能证明设备侧停止、回滚或法规符合性。

### Decisions

- R7-A 权限上限固定为 `Shadow`，所有 Artifact、API 和 UI 均保持 `deviceWriteAllowed=false`。
- `RecommendationSet` 与 `AcceptanceRecord` 保持独立内容身份；R7 不改写 R6 候选。
- 主 Artifact 记录入场决定、监控时间线、停止/回退 receipt 和责任快照；Domain runtime 确定性重放验证。
- `syntheticShadowContractStatus` 与 `deploymentShadowStatus`、`controlledTrialStatus`、`closedLoopStatus` 分开，后三者保持 Open。
- ISO/IEC 参考只用于冻结安全边界，不作为合规声明；硬件急停/STO 和安全相关控制系统必须由具体部署独立证明。

### Deviations

- 蓝图中的完整 R7 退出门需要具体部署与真实设备证据；本工作包明确拆为 R7-A Synthetic Shadow Contract，未用合成正例伪装完整 R7 闭合。

### Surprises

- 蓝图的 R7 退出门依赖“具体部署要求”，而仓库没有任何可验证部署目标；因此不能用通用软件状态机替代机床安全论证。

### Questions for review

- 首个真实 Controlled Trial 必须在设备型号、厂商协议、认证主体、隔离工况、停止链和责任方都明确后另行冻结；当前没有可安全默认的答案。

### Verification

- Windows AMD64 / CPython 3.12.10 全量 Python `644 passed`；R7-A 后端/API 定向 `19 passed`。
- 网页全量 `32 passed`，TypeScript 检查与 Vite 生产构建通过；桌面实页视觉终审 `94/100`，顶栏与正文均显示 Shadow/无设备授权/Open 边界，且无水平溢出或设备操作入口。
- 仓库 36 份 Markdown 的单 H1、围栏与本地链接校验通过；差异空白检查通过。
- 干净 `0.14.0` wheel 只包含当前一对网页资源与完整 `axiom/control`，在独立 CPython 3.12.10 环境安装后通过版本、CLI、RunBundle、R7-A Claim、OpenAPI 和包内容 smoke。
- 未测试真实控制器连接、真实 deployment shadow、设备 stop/ack/readback、Controlled Trial、Closed Loop 或 ISO/IEC 符合性；这些仍是后续部署工作包的显式 Open gate。

## 工作包 18：R7-C Windows 虚拟 OPC UA 传输验收

Plan: 冻结 OPC UA 只读边界 → 实现隔离 `.NET 8` Adapter 与独立虚拟 Server → 产出跨语言证据 → 接入 `control.domain-pack@3`、API/UI → 完成 Windows CI 与发布包。

Summary: 已完成 Windows-only R7-C 虚拟 OPC UA 传输合同。官方 OPC Foundation .NET 栈负责证书固定、`SignAndEncrypt`、非匿名 username 和 X/Y/Z/B/C 订阅；Python 负责 typed evidence、确定性审计、RunBundle 与 Web API。该工作包不选择厂商，也不把虚拟网络通过写成现实验证。

### Assumptions

- 当前仍没有已选控制器、厂商许可、真实 namespace/node mapping、只读凭据或独立真实 capture。
- 当前交付只支持 Windows AMD64、CPython 3.12.10 与 .NET 8，不实现或验证 Ubuntu/WSL。
- localhost 虚拟服务端只证明共同传输合同，不证明厂商服务器、固件、时钟、负载或设备行为。

### Decisions

- 生产 Adapter 与 Python Core 隔离，使用锁定的官方 .NET Client 包；测试 Server 使用同版本官方 Server 包。
- 只允许证书固定的 `SignAndEncrypt` 和非匿名 username；密码不进入配置或证据。
- 生产源码不包含 OPC UA Write/Call；写拒绝由独立测试客户端发起并验证。
- `virtualTransportStatus` 可通过，但 vendor/reality/deployment gates 永远 Open，设备/工艺安全为 NotAssessed。
- `.NET` 与 Python 使用同一 canonical JSON/hash 语义，跨语言不重新解释证据。

### Deviations

- 没有实现 Siemens、FANUC、HEIDENHAIN 或其他厂商 Adapter；缺少可验收目标时实现会制造虚假兼容声明。

### Surprises

- 单文件 `win-x64` 发布需要在锁文件中预声明 runtime 和 ILLink restore 输入；已把该条件固化到 Adapter 项目和 NuGet lock。

### Questions for review

- 首个真实厂商 profile 仍需用户提供具体控制器族、版本、许可、证书治理、只读主体和可验收环境。

### Verification

- `.NET 8` locked restore、无警告构建、localhost conformance 与 framework-dependent 单文件 publish 通过。
- Python R7-C 模型/API/跨语言定向 `17 passed`；前端组件 `3 passed`，TypeScript/Vite 通过。
- 实页视觉门 `92/100`，控制台 0 错误，无启动、写入、下发或连接机床按钮。
- 未测试真实控制器、厂商 node mapping、真实时钟/丢包、设备写/停机链、Controlled Trial、Closed Loop 或标准符合性。

## 工作包 19：R7-D Beckhoff TwinCAT 厂商验收

Plan: 选择首个厂商目标 → 冻结开放/绑定 Vendor Profile → 实现 Windows 只读预检与运行时 inspector → 隔离权限 canary verifier → 接入 `control.domain-pack@4`、API/UI → 扩展发布包与文档。

Summary: 已选择 Beckhoff TwinCAT 3 Build 4026+ / TF6100 作为首个厂商路径。Python 层负责 typed Profile、运行时证据、九项审计、Claim/RunBundle 和 Web API；`.NET` 生产 Adapter 负责只读预检、BuildInfo/许可证/节点访问读取和 R7-C transport 绑定；独立程序集只负责专用非执行 canary 的一次拒写验证。当前机器没有 TwinCAT/TF6100，因此交付状态是 Profile 合同闭合、厂商运行时与现实门 Open。

### Assumptions

- 本阶段只支持 Windows AMD64、CPython 3.12.10 和 `.NET 8.0.424`；不考虑 Ubuntu/WSL。
- 部署 endpoint、ApplicationUri、证书、PLC namespace/node id、许可证节点和权限 canary 只能由具体 TwinCAT 工程责任人提供，仓库不猜测。
- 现实验证仍需后续独立 case-scoped capture，以及 R3/R4 的时间、坐标、校准和残差证据。

### Decisions

- Profile 与 Runtime 分门：默认 Open Profile 可以通过 schema，但不产生厂商运行时 Claim。
- 运行时六项 gate 为安装、许可证、BuildInfo、五轴只读 mapping、独立拒写和 R7-C transport；任一缺失保持 Open，任何不匹配为 Blocked。
- 生产 Adapter 没有 OPC UA session Write/Call；权限验证器是不同程序集，显式确认专用非执行 canary 后只允许一次同值 Write。
- 通用/虚拟 OPC UA Server 和 `contract-fixture` 永远不能冒充 `vendor-runtime`；现实与安全状态不会由厂商合同自动升级。

### Deviations

- 未安装 TwinCAT/TF6100，也未自动执行 Beckhoff Package Manager 安装；安装、许可、重启和目标机变更属于部署方权限。
- 未提供伪造的绑定 Profile 或正向运行时夹具；默认示例保持 Open。

### Surprises

- OPC UA 标准 BuildInfo 六个字段有固定 NodeId，可在不依赖厂商 namespace 的情况下读取；五轴、许可证和 canary 仍必须由工程绑定。
- 独立拒写验证既需要证明访问级别为 CurrentRead-only，又需要验证服务端实际拒绝；仅检查 metadata 不足，但该一次 Write 必须从生产 Adapter 严格隔离。

### Questions for review

- 关闭 `vendorRuntimeStatus` 仍需一台经部署方授权的 TwinCAT 3 Build 4026+ / TF6100 环境、Bound Profile、只读主体和专用 canary。

### Verification

- `.NET 8.0.424` locked restore、解决方案无警告构建和 Python 跨语言 preflight 证据重验通过；本机结果为 `TwinCatPackageManagerMissing` / Open。
- Python R7-D 模型/API 定向 `17 passed`；`.NET`/跨语言定向 `3 passed`；前端组件与 App 定向 `14 passed`，TypeScript/Vite 通过。
- 实页视觉门 `93/100`，桌面与 390px 窄屏控制台 0 错误，无安装、连接、写入、下发或控制按钮。
- 未运行真实 TwinCAT、TF6100 许可证读取、节点订阅或独立权限 canary；未测试真实 capture、设备 stop/readback、Controlled Trial、Closed Loop 或标准符合性。

## 工作包 20：R7-E Beckhoff Shadow Witness + R4.1 Reality Alignment

Plan: `.omx/plans/r7e-r41-field-evidence.md`

### Decisions

- R7-E 使用新的 `control.domain-pack@5`，不回写 R7-C/R7-D 已发布的 `declaredReal=false` 与 `realityValidationStatus=Open` 语义。
- 采集合同以 `sampleIndex` 变化为触发器；每次触发批量读取 `commandContentHash`、回读 `sampleIndex` 和 X/Y/Z/B/C，禁止仅凭轴值变化通知推断完整覆盖。
- Deployment Shadow 只在单控制器、单 M5 指令、完整索引覆盖、外部授权、零 Write/Call 的 case 范围内通过；R4 现实验证、Controlled Trial、Closed Loop、DeviceSafe 与 ProcessSafe 均不随之升级。
- 仓库默认场景不包含绑定 NodeId 或伪造真实采集；正向门禁只能消费仓库外的 `controller-live-read` 证据。

### Deviations

- 当前先落 Python 机器契约、确定性审计和默认 Open 场景；真实 TwinCAT 采集仍依赖后续 `.NET` witness 命令和部署环境。

### Surprises

- OPC UA PublishingInterval 与 SamplingInterval 不是一回事，DataChange 也是值变化驱动；驻留点和短瞬态可能不产生逐周期通知，因此必须引入控制器侧单调样本索引。

### Questions for review

- 真实 TwinCAT 工程仍需选择并暴露只读的命令哈希、样本索引及五轴回读节点；仓库不会猜测 PLC namespace 或符号路径。

## 工作包 21：R7-E / R4.1 Windows 现场验收包

Plan: `.omx/plans/r7e-field-acceptance-kit.md`

Summary: 已完成 Windows-only 现场验收包。外部 R7-E assessment 现在显式保留 `caseId`；统一编排器依次重验 calibration/validation 两个 R7-E 输入，仅在双门通过时创建 pair，再执行 R4.1 holdout 验证并冻结最终报告哈希。CLI、HTTP 和网页使用同一逻辑；当前开发机没有 TwinCAT/TF6100，因此公开默认仍为 Open。

### Decisions

- 现场验收包只编排既有 R7-E/R4.1，不创建新的安全 Claim 或设备写入路径。
- `caseId` 在外部 command/Shadow evidence 输入上是必填项；公开空证据 Open 示例继续兼容默认 Case。
- pair 只在两个 R7-E deployment Shadow gate 均为 Passed 时创建；最终状态优先保留 R7-E Blocked，再投影 R4.1 Passed/Open/Blocked/Refuted。
- CLI 退出码固定为 `0=Passed`、`1=有效但未通过`、`2=输入无效`；网页分别导入两份 R7-E payload，不要求用户手工拼 pair。

### Deviations

- 原计划把现有 `R7EAssessmentRequest` 当作完整现场输入；实际模型缺少 `case`，因此先增加显式 Case 绑定，再继续 dossier 编排。
- 没有把编排器包装成新的 R7-F DomainPack；它是既有 R7-E 与 R4.1 的应用层验收 dossier，避免重复 Claim 和 Core 语义。

### Surprises

- [`src/axiom/control/r7e_models.py`](src/axiom/control/r7e_models.py) 的 `R7EAssessmentRequest` 没有 `case`；[`src/axiom/control/r7e_scenarios.py`](src/axiom/control/r7e_scenarios.py) 的 `_run_spec()` 固定写入 `control.r7e.beckhoff-shadow-run.case@1`。R4.1 虽比较两个 pair 的 `case.case_id`，但通过公开 assess 入口生成的 pair 会天然相等，无法排除不同现场 Case。

### Questions for review

- 真实 gate 仍需部署方在具有 TwinCAT 3 Build 4026+、TF6100、Bound Profile、只读主体和授权时间窗的 Windows 环境提供两次独立 capture；当前仓库不能替代该外部条件。

### Verification

- Python 定向覆盖 Open、Passed、Blocked、Refuted、不同 Case、内容篡改、CLI 与 HTTP；Passed 数据只在测试内构造，不进入公共示例。
- Field Evidence 组件测试、TypeScript 和 Vite 生产构建通过；1440×1000 实页视觉门 `94/100`，无横向溢出。
- 未运行真实 TwinCAT/TF6100 双采集、Controlled Trial、Closed Loop、设备写入或安全符合性评估。

## 工作包 24：R7-E / R4.1 现场 dossier 到 R5-B 真实 holdout

Plan: `.omx/plans/r7e-r5b-real-holdout-intake.md`

Summary: 已新增应用层 `axiom.adapter.r7e-to-r5b-holdout@1`。多个不可变 Field Evidence report 与显式 R3 上下文、治理和 R5-B 基线可以经 Python、CLI、HTTP 或既有 R5-B 网页工作台生成同一 `RealPairedHoldoutSet` 与 RunSpec；随后仍由公共 R5-B evaluator 决定 case-scoped 泛化 Claim。

### Decisions

- 不新增 DomainPack 或 Core 字段；输入/输出复用已发布的 FieldEvidence、MachineObservation、PhysicalResponseTrace 和 RealPairedHoldoutSet。
- 每个 dossier 只消费 validation 运行；calibration 只保留为 R4.1 参数识别谱系，不能再次计入 holdout。
- R3 单一时间戳采用版本化 X-source-timestamp 策略，五轴各自 timestamp 与 sample-index 证据完整保存到 vendor metadata。
- Intake Passed 只意味着证据有资格进入 R5-B；Controlled Trial/Closed Loop 固定 Open，DeviceSafe/ProcessSafe 固定 NotAssessed。

### Deviations

- 原计划只增加完整请求入口；实际同时实现多文件 CLI/UI，避免再次要求现场人员手工拼装大 JSON。
- 没有发布正向 fixture 或示例。Passed 数据只在单元测试内构造，公共默认场景继续 Open。

### Surprises

- 把 FieldEvidence report 直接嵌入新请求会让 FastAPI 为既有 R7-E response 生成 `-Output` schema 名，破坏已冻结 OpenAPI。运行时仍使用完整 Pydantic 深度校验，但 intake 的 schema 投影将该嵌套字段保持为 object，从而保留既有 R7-E 公共 schema 名。
- 初版在 evidence 覆盖不足时把已知的治理 attestation 时序错误误报为 Open；现已在生成完整 holdout 前独立验证已投影 capture 的治理时序并 fail closed。

### Verification

- Python 完整本机套件 `785 passed, 1 skipped`；新增 intake 文件 `14 passed`，Python/CLI/HTTP 内容哈希一致。
- Web `14 files / 49 tests`、TypeScript 与生产构建通过。
- .NET SDK 8.0.424 locked restore 与 Release build 为 0 warnings / 0 errors。
- 本机 CPython 3.14.3 不能作为冻结 CPython 3.12.10 的 environment-bound F2/F3 金值证据；该项保留给 Windows CI。

## 工作包 22：R7-E Beckhoff 只读见证部署工具包

Plan: `.omx/plans/r7e-beckhoff-witness-deployment.md`

### Decisions

- 本工作包是 R7-E 应用层部署准备，不创建 R7-F DomainPack、不复制 Claim，也不改变 Core。
- 控制器模板只消费权威 M5 hash/index 和五轴回读；hash/axes 先锁存，sample index 最后发布，七输出均为 TF6100 只读符号。
- deployment request 必须显式提供 Bound Vendor Profile、同一 R7-D runtime、M5 command 和七项有序 namespace/identifier；只有五项检查全通过才生成 Bound Witness Profile。
- `capturePreparationStatus=Passed` 与实际 capture 分开；authorization、Deployment Shadow、Reality、Controlled Trial、Closed Loop 和安全状态不自动升级。

### Deviations

- 当前开发机只有 .NET SDK 10.0.200，仓库固定要求 8.0.424，因此本地两项 `.NET run` 测试不能执行；没有修改 `global.json` 降低发布基线，留给 Windows CI 权威验证。
- 当前没有 TwinCAT/TF6100，模板仅完成 XML/pragma/赋值顺序/打包合同检查，未声称 TwinCAT import、compile 或 runtime 通过。

### Surprises

- OPC UA MonitoredItem 会先报告当前值；`UDINT` 默认 0 会让客户端在样本 0 尚未锁存时读取空 hash，且真正写入 0 不再产生 DataChange。模板因此把公开索引初始化为 `16#FFFFFFFF`，现有 Adapter 会忽略首个非 0 通知，再由有效索引 0 产生确定变化。
- 桌面和移动端在新增部署区后仍无横向溢出；配置列变长但动作层级保持“模板/预检为次级、双证据验收为唯一绿色主动作”。

### Questions for review

- 真实 TwinCAT 工程仍需由部署方提供 PLC 实例路径、namespace URI 与 NodeId，并完成模板导入、编译及授权环境验证。

### Verification

- 部署定向测试覆盖 TcPOU XML、七只读 pragma、哨兵、索引最后赋值、节点顺序/唯一性、完整绑定、runtime 身份错配、重封状态升级拒绝、CLI/HTTP 同义和模板下载。
- Python 除本机缺 SDK 的两项 `.NET run` 外 `746 passed, 1 skipped, 2 deselected`；新增定向最终为 `7 passed`。网页 `14 files / 48 tests`、TypeScript、Vite 和变更文件 Ruff 通过。
- wheel 0.20.0 构建并从隔离目录加载，包含 `r7e_deployment.py`、`FB_AxiomShadowWitness.TcPOU` 和最新网页资产；模板七个只读 pragma 可从 wheel 重读。
- 视觉门 `93/100`；1440×1000 与 390×844 均无横向溢出、控制台错误或控制型按钮。
- 未运行 TwinCAT import/compile/activate、真实 TF6100 ACL、vendor-runtime、现场 capture、设备写入或安全符合性评估。

## 工作包 23：R7-E Windows 离线证据组装与双文件验收

Plan: 从不可变 Shadow capture 到 R7-E assessment 消除手工 JSON 拼装 → 让现场 CLI 直接配对 calibration/validation → 保持既有 R7-E/R4.1 门禁与零写边界 → 完成 Windows 发布验收。

Summary: 已新增离线 `.NET` `beckhoff-shadow-assessment`，对 Profile、runtime、authority、authorization、M5 command 与 Shadow evidence 的跨文件内容身份和约束进行重验，并生成 Python 可直接核验的单次 R7-E 输入；`axiom field-evidence` 现在可以直接消费两份独立输入，旧的完整 dossier 文件入口保持兼容。

### Decisions

- 离线组装器不建立网络连接、不执行 PLC 操作，也不创建新的 DomainPack 或 Claim；它只把既有 R7-E 支持对象确定性封装成可重验输入。
- calibration 与 validation 保持不同 command、authorization、Shadow evidence 和 pair identity，仍由既有应用层编排器执行 R7-E gate 与 R4.1 holdout。
- C# 与 Python 共享 UTF-8 canonical JSON、非 ASCII 字符和五轴 M5 浮点规范化规则，避免跨语言内容身份漂移。
- CLI 的双文件模式要求显式 assessment/pair ID；与旧位置参数请求或不完整选项混用时 fail closed，不静默忽略用户参数。

### Deviations

- 全局 SDK 查询没有暴露 8.0.424，但仓库缓存的精确 SDK 可用于验收；本地已用它运行跨语言测试，发布仍由 Windows CI 与发布工作流再次阻断。
- 当前没有 TwinCAT/TF6100 和经授权的两次现场 capture，因此本包只关闭文件组装缺口，不关闭 deployment Shadow、reality、Controlled Trial 或 Closed Loop gate。

### Surprises

- C# 默认 JSON 字符转义与 Python `ensure_ascii=false` 不同，且 M5 portable identity 还有 8 位有效数字规则；两者必须同时对齐才能复算既有 Python 内容哈希。
- CLI 初版会在旧位置参数模式下静默忽略新增阈值选项；发布前改为显式拒绝混用，并增加回归测试。

### Questions for review

- 无代码阻塞；真实正向验收仍需部署方提供 Bound TwinCAT/TF6100 环境和两次独立、授权、同 Case 的 capture。

### Verification

- Python 全量 `771 passed, 1 skipped`；定向覆盖双文件配对、旧入口兼容、缺失/混用/不可读输入、强类型 support 反例、M5 整数词法兼容、command 身份错配和失败不落文件。
- 网页 `14 files / 48 tests`、TypeScript 检查和 Vite 生产构建通过；本包未增加第二套网页工作台。
- `.NET` 解决方案构建与独立 localhost conformance 通过，生产 Write/Call 计数保持 0；wheel/sdist `0.21.0` 构建通过。
- 未运行真实 TwinCAT/TF6100 双采集、Controlled Trial、Closed Loop、设备写入或安全符合性评估。

## 工作包 25：R5-B 现场 Campaign 预注册

Plan: `.omx/plans/r5b-field-campaign-preregistration.md`

### Decisions

- 先补 selection-before-evaluation 的预注册证据，不创建 R7-F、不增加设备写入或安全 Claim。
- 旧 SelectionReceipt 保持可解析与内容身份稳定；只有显式绑定 Campaign manifest/registration 的新收据才可进入 case-scoped reality gate。
- Campaign 在采集前冻结基线 ModelBundle/训练数据、case/device/condition/task/batch、双运行 pair 与 command 内容身份；严格 intake 在采集后验证登记早于每次 capture `openedAt`，再复用既有 R7-E→R5-B 投影。
- Registration 首版固定为 `external-owner-attestation`。内容哈希与时间比较只证明 Axiom 可重验这些输入，不把外部普通时间戳升级为可信时间戳或物理真实性证明。
- 继续使用现有 R5-B DomainPack、runner 和 evaluator；Campaign/Registration 是应用层治理合同，CLI、HTTP 与网页均调用同一 Python 注册/验收函数。

### Deviations

- 没有加入公开正向真实 fixture。通过路径只在测试内构造，生产入口要求现场人员导入 Campaign、治理与 Case 文件，仓库默认现实门继续 Open。
- 没有在本片引入数字签名、TSA 或外部注册表客户端；这些属于后续更强登记方法，不能静默改变 `external-owner-attestation` 的语义。

### Surprises

- v1 intake 是在看到 dossier 后才创建 selection，因此即使调用方填写 `selectedBeforeEvaluation=true`，也不能形成可验证的预先选择证据。兼容读取与现实门闭合必须拆开处理。
- `RealHoldoutSelectionReceipt` 的旧内容身份可以通过新增可选字段且 canonical JSON 排除 `None` 保持不变；回归金值继续是 `e0ba5a752c5078777e7a7e0ec91dd0f1f2867b7b8e2d142bdc470a366218c966`。

### Questions for review

- 后续若现场治理要求不可抵赖登记，需要选择外部签名/可信时间或注册表验证机制，并新增 versioned registration method；当前没有代码阻塞。
- 真正关闭 `realWorldGeneralizationStatus` 仍需经授权、跨至少两台设备和两种工况的真实 Windows holdout，以及一个独立 OOD probe。

### Verification

- 固定 Windows CPython 3.12.10 全仓 `795 collected`，结果 `791 passed, 4 skipped`；4 个 skip 分别是 1 个环境绑定 F4 金值与 3 个本机缺固定 .NET 8.0.424 SDK 的既有跨语言测试。
- Campaign/模型/runtime 定向 `16 passed`；覆盖确定性登记、覆盖/唯一性、登记晚于采集、身份替换、Manifest 篡改、旧 selection fail-closed，以及 Python/CLI/HTTP portable 输出一致。
- Web `14 files / 49 tests`、TypeScript 检查和 Vite 生产构建通过；新生产资产已写入 `src/axiom/web_dist`。
- 变更 Python 文件 Ruff 与 `git diff --check` 通过；47 份 Markdown 的本地链接检查通过。全仓 Ruff 仍有 6 个本次未触碰的既有基线问题，未越界清理。
- 实页视觉门 `93/100`；1280×720 与 390×843 的默认/预注册区截图无溢出、遮挡或移动端断裂，且页面继续不提供设备写入或闭环动作。

## 工作包 26：R5-C 参数条件效应代理模型

Plan: `.omx/plans/r5c-conditional-effect-surrogate.md`

Summary: 已新增 Windows-only `intelligence.domain-pack@3`，把 canonical head-table 的 R4 synthetic SIL 参数研究封成 25 点 `ConditionalEffectDataset`，以固定 15/5/5 空间 holdout 训练周期与线性跟随误差两个独立输出头，并通过公共 Run、typed HTTP 预测接口和 Intelligence R5-C 网页工作台交付。`syntheticConditionalEffectContractStatus=Passed`，`realWorldGeneralizationStatus=Open`。

### Decisions

- 输入域冻结为五个 `feedOverride` 与五个 `samplePeriod` 的笛卡尔积；逐样本保留 M4、M5 和 `PhysicalResponseTrace` 内容身份以及 synthetic 治理、选择和谱系策略。
- 周期 `s` 与线性误差 `mm` 使用同一组六个归一化物理特征、两个独立 ridge head 和各自的 split-conformal 半径；不合成总分，`commandSampleCount` 只作为来源事实。
- validation 只标定区间，test 只做最终 NRMSE/coverage 验收；域外请求固定返回 `Abstained + OutsideDeclaredDomain`，不输出数值。
- 训练侧依赖 NumPy，目标解释器是独立纯 Python 实现；模型、训练回执、parity 回执和数值环境绑定金值都可在各自冻结环境内确定性重放。
- R6 v1 保持六点完全枚举，不消费 R5-C；R5-C 只提供 Offline 预测，不生成 Recommendation、AcceptanceRecord 或任何设备写权限。

### Deviations

- 没有把代理模型接入 R6 搜索。这样避免在没有新 R6 版本化合同和候选逐项硬门重放前，静默改变既有 Recommendation 语义。
- 没有加入 ONNX、AutoML、神经网络或新的运行时依赖；25 点首片用可解释 ridge 和纯 Python parity 已满足声明门槛。
- 金值同时冻结 Windows CPython 3.14 开发档案与 CPython 3.12.10 + Haswell/单线程 OpenBLAS 发布档案；发布门只接受后者。

### Surprises

- `commandSampleCount` 随采样周期呈离散阶梯，若作为回归目标会让首版模型学习取整边界而不是稳定物理条件效应，因此保留为来源观测。
- 周期几乎被逆进给特征完全解释；线性误差需要交互项和二次项，但仍可在独立 test split 通过预声明的 5% NRMSE 门。
- 给数据集补齐 governance 与 lineage policy 后内容哈希必然变化；fixture 因此冻结最终有治理版本，而非沿用 spike 的临时身份。
- 在有历史 `build/lib` 的工作树里直接执行 `python -m build --wheel` 会把旧哈希网页资产带进本地 wheel；正式发布工作流使用 `python -m build`，从新 sdist 构建 wheel。本包按该洁净路径验收，并要求 wheel 中恰好只有当前两份哈希资产。

### Questions for review

- 没有代码阻塞。未来只有在 R5-B 提供预注册、跨设备/跨工况真实 holdout 后，才能讨论 reality 状态；扩大搜索域则需另发 R6 合同并保留逐候选 R4/数学硬门。

### Verification

- R5-C Python/runtime/API 定向 `9 passed`；Windows 当前 Python 3.14 全仓共收集 804 项，结果 `800 passed, 4 skipped`。4 项为既有环境门；精确 CPython 3.12.10 仍需冻结发布环境重放。
- 网页全量 `15 files / 53 tests`、TypeScript 与 Vite 生产构建通过；生产资产已写入 `src/axiom/web_dist`。
- 本次全部 Python 变更 Ruff、`git diff --check` 和 48 份 Markdown / 177 个本地链接检查通过。
- 与发布工作流一致的 sdist→wheel 构建通过；wheel 包含 R5-C fixture、runtime、网页入口且只包含当前两份哈希网页资产。
- 实页桌面与 390×844 移动端完成默认、滚动和域外弃权交互检查；控制台无错误，视觉门 `94/100`。
- 未运行真实设备 holdout、R5-C→R6 代理搜索、设备写入、在线学习或安全符合性评估。

## Work Package 27 — R6 v2 目标驱动代理筛选与精确回放

Summary: 已新增 Windows-only `optimization.domain-pack@2`。R5-C 在 15×9 共 135 点的冻结参数网格上提供区间筛选，用户以一个主目标和两个显式约束定义意图，最多 27 个候选进入精确 F3/F4/R4 回放；最终 `RecommendationSet@2` 只包含精确证据，最优性范围固定为预算内 best observed。

### Decisions

- R6 v1 完全保留；v2 使用新的 DomainPack、SearchRequest、RecommendationSet、运行时和 API，不改变 v1 portable/environment-bound hash。
- 速度、质量、紧凑指令分别把周期、线性误差、指令样本数设为唯一主目标；另外两项必须提供同量纲上限，不接受 weights 或缺失约束。
- 代理筛选使用区间下界做 possible-feasibility，按主目标下界/预测值和参数确定性排序；连续目标代理排序冻结到微秒级，精确裁决仍使用完整精度。
- R5-C 只负责提议。所有入选候选逐一重放 F3/F4/R4 和七个数学 Gate；代理可能可行不能覆盖精确约束失败。
- 输出只声明 `best-observed-within-exact-validation-budget` 和 `globalOptimalityStatus=NotClaimed`；权限继续是 Offline、零写入、零自动接受、reality Open。

### Deviations

- 没有采用代理三目标 Pareto 截断。冻结网格的代理 Pareto 前沿过密，无法稳定压入 27 次预算。
- 没有增加新的 ML、优化或前端依赖；复用 R5-C 解释器、现有 F3/F4/R4 精确评估与 Optimization Lab 视觉语言。
- 没有把 v2 结果接入 R7。Recommendation 与 AcceptanceRecord 继续分离。

### Surprises

- 代理周期在若干精确同优点上存在约 `1e-8 s` 的预测差，若直接排序会让浮点噪声改变输出顺序；筛选排序因此冻结到微秒级，再用参数顺序确定 tie-break。
- 全网格精确三目标 Pareto 点过多，说明“先算 Pareto 再截断”并不是有效搜索策略；目标加显式约束既更符合用户意图，也能形成可审计预算。
- FastAPI 的 `response_model_exclude_unset` 会移除 discriminated-union 的默认 `primaryObjectiveId`，导致示例回传后无法再次 POST；R6 v2 typed example/search 响应必须保留默认 discriminator。

### Verification

- R6 v1/v2 Python 模型、运行时与 API 联合定向 `31 passed`；三种目标均在不超过 27 次精确回放内恢复冻结 full-grid oracle 最佳已观测点。
- Optimization Lab 定向 `3 passed`、App `12 passed`、TypeScript 与 Vite 生产构建通过。
- 1440×900 和 375×812 实页检查无控制台错误；视觉门 `93/100`。
- Windows 当前 Python 3.14 全仓 `814 passed / 4 skipped`；精确 CPython 3.12.10 的环境绑定门仍须在冻结发布环境重放。
- 网页全量 `15 files / 53 tests`、TypeScript 与 Vite 构建通过；`git diff --check` 和 86 份 Markdown / 200 个本地链接检查通过。
- sdist→wheel 构建、资产计数和隔离安装 smoke 通过；wheel 包含四个 R6 v2 模块、开发/发布双档环境绑定 fixture 和恰好两份当前网页哈希资产。
- R6 v2 变更范围 Ruff 通过。仓库级 Ruff 仍报告 6 个不属于本工作包的既存问题：5 个旧未使用导入和 1 个旧 `__all__` 名称，本包未混入无关清理。

## Work Package 28 — R6 v2 到 R7-A 的显式 Shadow 接力

Plan: `.omx/plans/r6v2-r7a-shadow-handoff.md`

Summary: 已让 `RecommendationSet@2` 通过内容寻址的 `RecommendationEvidenceProjection` 进入既有 Windows synthetic-shadow 状态机。R7-A v1 的 DomainPack、RuntimeAudit、Evaluator、Runner 与 API 保持不变；内容身份分别在冻结的开发和发布数值环境中保持不变。Controlled Runtime 默认展示 v2 接力并可切回 v1。

### Assumptions

- 本片只闭合软件证据接力，不依赖 TwinCAT/TF6100、真实 capture、Ubuntu/WSL 或设备写入能力。
- R6 v2 代理只负责筛选；只有逐候选通过 F3/F4/R4、七个数学 Gate 和 exact user constraints 的结果可以成为 R7-A 入场事实。
- synthetic Shadow 不是 deployment Shadow，也不改变候选自身 `promotionEligible=false` 和 reality Open。

### Decisions

- 复用 `control.domain-pack@1` 与 `axiom.control.runtime-audit@1`，仅给 Recommendation context 增加 schema version 2 描述；没有复制状态机或修改 Core。
- `axiom.adapter.r6v2-to-r7a-shadow@1` 投影 Recommendation、SearchRequest、surrogate context、screening receipt、exact candidate 和 screening estimate 身份，并保留预算内最优性与 `NotClaimed`。
- Projection 与 AcceptanceRecord 永久分离。默认选择 best observed，但其他 exact-eligible 候选可以被独立处置；Optimizer 排序不构成自动接受。
- v2 AcceptanceRecord 的 evidence snapshot 指向 Projection，Recommendation 内容哈希仍单独保留；缺失、篡改、跨候选重绑、exact-ineligible 与设备写请求均 fail closed。

### Deviations

- 没有新增 `control.domain-pack@6` 或 RuntimeAudit@2，因为主 Artifact、权限、状态机、指标和 Claim 均未改变；新能力是版本化只读上下文。
- 没有把 RecommendationSet@2 降级为 v1，也没有把 R7-A v2 自动串到 R7-B–R7-E 或真实设备。
- 没有增加 CLI 或新依赖；公共 RunSpec、typed HTTP API 和现有 Controlled Runtime 工作台已覆盖当前使用路径。

### Surprises

- 现有 R7-A runner 只检查 v1 `hardConstraintsSatisfied`，而 v2 还必须检查 `exactConstraintsSatisfied/recommendationEligible`；只复用旧字段会让代理可能可行候选绕过用户 exact constraints。
- v1 Recommendation/Audit 也间接包含数值求解身份，不能把 Python 3.14 值误称为跨环境金值；现在分别冻结 CPython 3.14 开发档案和 CPython 3.12.10 发布档案，并要求同环境双重放一致。
- R6 v2 所有候选仍固定 `promotionEligible=false`；本片的 Shadow 是进程内合同重放，不能把它误读成现实晋级许可。

### Questions for review

- 当前没有代码阻塞。下一次真正提升权限仍需具体 deployment Shadow、真实只读采集、设备侧停止/回退、独立安全验证和责任方签署；本片不替代这些外部条件。

### Verification

- R7-A v1/v2 Python、公共 Run 和 API 定向 `36 passed`；覆盖 best observed、非 best exact-eligible、包线越界、exact-ineligible、缺 Projection、设备写请求、篡改、跨候选重绑与非 Windows 平台。
- Controlled Runtime 组件与 App 联合 `15 passed`，TypeScript 与 Vite 构建通过；桌面 v2/v1 和 375×812 移动端无横向溢出、控制台错误或设备控制入口，视觉门 `94/100`。
- 变更范围 Ruff、`git diff --check`、112 份 Markdown / 221 个本地链接通过；sdist→wheel、隔离安装与 OpenAPI smoke 通过，wheel 包含两个 R7-A v2 模块和恰好两份当前网页资产。
- 当前本机 Python 3.14 全仓 `831 passed / 4 skipped`；精确 Windows CPython 3.12.10 的环境绑定发布门仍由冻结环境重放。

## Work Package 29 — Goal → exact R4 response → R7-A Synthetic Shadow

Plan: `.omx/plans/goal-to-shadow-rehearsal.md`

Summary: 已把 Optimization Lab 的用户目标、R6 v2 exact candidate、候选自己的 R4 `PhysicalResponseTrace` 和既有 R7-A 状态机接成一条 Windows-only 应用链。服务端不是复用固定四点夹具，而是重新执行候选的 F3/F4/R4 协议并逐项重验内容身份，随后以无插值的 X/Y/Z mm 跟随误差构建 `ShadowTrace`。

### Decisions

- 采用应用层 `GoalToShadowReport`，不新增 DomainPack、Core 对象、指标或 Claim；R6 Recommendation、R4 response 和 R7 RuntimeAudit 继续保持各自权威身份。
- 请求提交原始 R6 v2 SearchRequest 与可选 candidate ID，服务器重新搜索；默认选择第一个 best observed，显式选择只接受 exact-eligible 候选。
- 复用 R6 v2 的精确参数点函数，重验 candidate M4 hash、M5 content ID 和 physical response hash；M5/response 还必须按 sample index、time 和五轴 command 完全相同。
- `PhysicalShadowProjection` 保存 M5、R4 response、ShadowTrace 和映射收据。每个 Shadow 样本只取 X/Y/Z 的最大绝对误差，单位 mm；B/C rad 排除，candidate OOD 按 constant-per-sample 投影。
- 投影通过后继续调用原 R7-A Recommendation Projection、ControlEnvelope 和 fail-closed Admission/Monitor/Stop/Rollback。网页动作不构成 Acceptance、现实证据或设备授权。

### Deviations

- 没有尝试从 response hash 反推数据，也没有把固定四点 R7-A 场景冒充选中候选轨迹；前者不可能，后者会破坏谱系。
- 没有把完整响应塞进 RecommendationSet@2；应用层按冻结协议重放并独立封存投影，避免扩大离线推荐合同。
- 没有增加路由、全局状态、新依赖、缓存、后台任务或历史持久化；结果直接内联显示在用户选择候选的位置。

### Surprises

- Candidate 的 M4 hash 与 M5 内部 `sourceM4ContentId` 使用两个已有的规范化身份协议，值并不相同。投影分别保存并各自重验，禁止把二者当成同一个字段。
- 现有 R7-A v2 已证明“该候选可被状态机处置”，却未证明 trace 的物理来源；直到本包引入第二个 R4-response projection，这条用户链才真正闭合。
- 默认速度目标候选 `feedOverride=0.825`、`samplePeriod=0.05 s` 产生 18 个 exact samples，逐样本投影后的最大线性误差与 Recommendation 的精确目标完全一致。

### Numeric-environment-bound identities

- CPython 3.14 development — Physical Shadow Projection: `a8b7c70578c6f76455393afd1a95d8b490119db4fe1b9b7f5336aaceb493b314`; R7-A Runtime Audit: `0e3b43edf52cfef7e942a8f0d80de7b85fd447381b8f2e0afddcca2fe284751a`; Goal-to-Shadow Report: `716385d0ac9c31a1d0ca5243cf5e636e5cd81087a2f0b0618e29a429000217c6`.
- CPython 3.12.10 release — Physical Shadow Projection: `3adaeb17223558f3fa1cd2b41bc4dfc6086fc0087206f4140316e656d0a581eb`; R7-A Runtime Audit: `002bcf9a812c15e3df9545678e8957f86af83db8f1a5d5441be5e4e7d63b6727`; Goal-to-Shadow Report: `746f283dba4d508cc784df5e7805a3d6d00bc58d26ecc3e03261782d7a14f467`.
- Canonical Shadow Trace 在两个档案中均为 `4b7ddeabde2f2978164470315395acd9b67f1bb039d8533e991652944dbd9765`；这项观察不升级其他对象为跨环境可移植身份。

### Verification

- 定向 R6 v2 / R7-A / Goal-to-Shadow Python 与 API `44 passed`；覆盖默认 best、显式非 best、ineligible/missing、跨候选 replay、篡改、非 Windows、Python/HTTP identity 和 OpenAPI。
- Windows CPython 3.14 开发环境全仓 `844 passed / 4 skipped`；冻结 CPython 3.12.10 + Haswell/单线程 OpenBLAS 发布环境全仓 `845 passed / 3 skipped`。
- 网页全量 `15 files / 55 tests`、TypeScript 与 Vite 生产构建通过；Optimization Lab 桌面和移动端无横向溢出、控制台错误、页面错误或失败请求，视觉门 `94/100`。
- 变更范围 Ruff、`git diff --check` 与 Markdown 本地链接检查通过（0 个缺失）；仓库级 Ruff 仍只有 6 个不属于本工作包的既存问题。
- CPython 3.12.10 下从 sdist 构建 wheel、安装到独立 target 并完成 Goal-to-Shadow/OpenAPI smoke；wheel 包含 R5-C/R6 v2 双环境 fixture、Goal-to-Shadow 模块和恰好两份当前网页资产。
- 未运行真实设备 holdout、TwinCAT compile、设备写入、Deployment Shadow、Controlled Trial、Closed Loop 或安全符合性评估。

## Work Package 30 — R5-D 下一批 synthetic SIL 实验价值规划

Plan: `.omx/plans/r5d-simulation-experiment-planning.md`

Summary: 已补齐蓝图 R5 的“试验价值估计”合同片。Windows-only 纯 Python planner 从冻结 R5-C/R6 v2 设计空间生成有类型 `SimulationExperimentPlan`，Intelligence Lab 可调整 1–10 的批次并查看顺序 G-optimal leverage、单位独立预测和预计样本数；计划不会自动执行、生成标签、更新模型或写设备。

### Decisions

- R5-D 是应用层 planner，不新增 DomainPack、Core 对象、Recommendation、AcceptanceRecord 或 Claim；它绑定并重验既有 R5-C Dataset/Split/ModelBundle 身份。
- 信息矩阵只使用 15 个 train 点。validation/test 不参与设计；全部 25 个已观测点从 135 点网格排除，因此默认候选池为 110。
- 使用与 R5-C 相同的六维归一化特征与 `λ=1e-6`，按 `x^T A^-1 x` 顺序选点，每次用 `A += xx^T` 更新；15 位有效数字和参数升序 tie-break 冻结确定性。
- proposal 上两个预测继续分成周期 `s` 与线性误差 `mm`，只作为理解上下文，不进入首版选择分数。
- 固定 `NotExecuted`、`NotPerformed`、`NotClaimed`、Offline、零自动执行、零设备写入和 reality Open。任何新标签都必须创建新 DatasetSnapshot/ModelBundle 后再规划。

### Deviations

- 没有按 conformal 区间宽度排序：同一输出头的冻结半径对全部域内候选相同，不能表达候选间 epistemic 差异。
- 没有引入 Bayesian optimization、强化学习、深度 ensemble 或新依赖；当前 15 点线性设计用可独立重放的 G-optimal proxy 已足以闭合首片。
- 没有把计划按钮接到 F3/F4/R4 自动执行，也没有新增持久化或后台任务；plan、execution、label acquisition、model update 保持四个独立动作。

### Surprises

- 用全部 25 点排除已观测候选、但只用 train 15 点构造信息矩阵，是同时保持 holdout 角色和避免重复仿真的关键；把 validation/test 加入设计会形成验收泄漏。
- 默认五点顺序不是简单的矩形角点集合。每次 rank-one 更新都会改变剩余候选的 leverage，因此必须逐点重算，不能先算一次后取前五。
- Windows 版 gstack `browse.exe` 安装缺少其所需的 `src/server.ts`，无法启动技能自带浏览器；视觉验收改用仓库现有 Playwright 与系统 Chrome，仍保留实际 API、控制台、溢出和截图证据。

### Numeric-environment-bound identities

- CPython 3.14 development — Request: `352009b47a1e86fc535531b8a7a5272cd3f1f4452fc557665a0b9fea845819c3`; Plan: `3d2d7d43ea156c08cb80cd9089b6f22d33aea4d4022aa17a147501cee0528ed2`.
- CPython 3.12.10 release — Request: `f315e731743f8664d696e4641e42fd485ca39e67c985826742ec1bced83f8947`; Plan: `5c672c640296e7cc52e8a90d9033adc872d1e75975b88b6cdeaa93fe79410fb0`.

### Verification

- R5-D Python/API 在 CPython 3.14 开发档案与冻结 CPython 3.12.10 + Haswell/单线程 OpenBLAS 发布档案各 `12 passed`；独立 NumPy oracle 逐轮重算顺序选择。
- 最终源码全仓共收集 860 项：开发档案 `856 passed / 4 skipped`，发布档案 `857 passed / 3 skipped`。网页全量 `15 files / 56 tests`、TypeScript 和 Vite 构建通过。
- 1440×900 与 375×812 实页复核无横向溢出、页面错误、失败请求或设备动作；移动端 proposal 为完整卡片，视觉门 `94/100`。既有 `/favicon.ico` 请求仍返回单个 404，不属于 R5-D API 或页面逻辑。
- 114 份 Markdown 本地链接 0 缺失，89 份发布相关 JSON 全部可解析；R5-D 变更范围 Ruff 与最终 `git diff --check` 通过。
- CPython 3.12.10 下从最终源码完成 sdist→wheel、独立 target 安装与 R5-D/OpenAPI/前端 smoke；wheel 包含 R5-D 两个模块、fixture，并且恰好只有当前两份网页哈希资产。
- 未运行真实设备试验、模型在线更新、TwinCAT compile、设备写入、Deployment Shadow、Controlled Trial、Closed Loop 或安全符合性评估。

## Work Package 31 — R5-E 离线合成实验反馈闭环

Plan: `.omx/plans/r5e-synthetic-campaign-feedback-loop.md`

Summary: 已把 R5-D 的默认五点计划接入一条 Windows-only、显式批准的 synthetic `plan → acquire → train → replan` 证据链。新流程逐点重放 exact F3/F4/R4，封存 M4/M5/PhysicalResponseTrace 和标签身份，以 v2 数据与模型对象保留 v1 身份，并生成下一份未执行计划。

### Assumptions

- 本片只处理本地 Windows synthetic SIL，不依赖 TwinCAT/TF6100、真实 capture、Ubuntu/WSL 或设备写入。
- R5-D 默认五点可由既有 canonical F3/F4/R4 求值链生成周期 `s` 和线性跟随误差 `mm` 标签。
- 原 validation/test 必须完全冻结；新五点只能追加到 train，否则基线/候选指标不可比。

### Decisions

- R5-E 保持应用层编排，不新增 DomainPack 或 Core 语义；重用 R5-D planner、R5-C 训练原语与 exact R4 参数点求值。
- 批准绑定完整计划内容、按顺序的全部 experiment IDs、责任方和 synthetic-only 确认；部分或错配批准在首个 replay 前 fail closed。
- R5-C v1 对象与金值保持不变；R5-E 发布独立 Dataset/Split/TrainingReceipt/ModelBundle/ParityReceipt v2，并通过 parent/acquisition hash 表达来源。
- 新 Dataset 为 30 点，新 split 为 20/5/5；候选重训、parity 和原 holdout 非回归门彼此独立。
- Campaign execution、candidate gate 和 model promotion 使用三个独立状态。首版永久不自动晋升；重规划从 105 个剩余点中产生新五点，但不递归执行。

### Deviations

- 没有在 R5-D 按钮内直接执行仿真；UI 要求责任方和明确勾选，并且先调用 approve、再调用 execute。
- 没有重新随机切分 30 点数据，也没有把新点混入 validation/test。
- 没有引入新依赖、持久化模型注册、后台任务、真实设备执行或自动回写。

### Surprises

- 冻结默认 fixture 的两个 test RMSE 都改善，但改善幅度中周期指标含跨 Python/BLAS 环境的最后位差异；因此双档金值分开冻结，且不将该观察升级为一般保证。
- Windows 上 gstack browse CLI 的默认启动包缺少 server source；指向本地 gstack 源码并使用独立持久 Node 进程后，完成了真实浏览器批准/执行流与响应式验收。

### Questions for review

- 当前没有代码阻塞。真实设备实验、模型人工晋升、注册/回滚和闭环执行仍需要独立的权限与治理合同。

### Numeric-environment-bound identities

- CPython 3.14 development — Campaign Request: `9d72ce2404beb59c8b85616504869777fc07f46345a925e7fb1eda73a898ed0e`; Acquisition Receipt: `349f76a2ba3be9cd531ddd98af4b7d3997d8d1f075c94d78fdea750469ece357`; Model Bundle: `cc6a08dc31256ca2e3e826d2ff140044ae6f3bb37ee9d6e702b2cc291c02e3cc`; Next Plan: `fd1e730b20e72a22f956d645241888715676bc92ae3d62db1eb62e42a982eda4`; Report: `da0e4df9e940bdbe108763fb40b8690e110a0efaf72d5998d9026990370b06f0`.
- CPython 3.12.10 release — Campaign Request: `4c5e6a0b5481ba119dc32676ef62f8117db9b9e4a9a6bad06adef958274e5812`; Acquisition Receipt: `6222f098bbe77b8de3facaaf78a4d0ae44abb99308492820b5d0f47ef63ae4bb`; Model Bundle: `4e2b92f37cc21c6ee24ff547033622f6f91b94d55f948b561cc50bfffaf0437f`; Next Plan: `f449943c18474265d0e9a7a978849437f63a0d0c7fab3614caffb218ad1a683f`; Report: `b268119e57884a178fc89b6cb6c6515419919aa1277d7ee206466218bd806528`.

### Verification

- R5-E Python/API 在 CPython 3.14 开发档案与冻结 CPython 3.12.10 + Haswell/单线程 OpenBLAS 发布档案各 `15 passed / 1 skipped`；包含最终跨对象 lineage 重封篡改反例。
- 最终源码全仓开发档案 `871 passed / 5 skipped`，发布档案 `872 passed / 4 skipped`；两档 R5-C/R5-D v1 金值与 R5-E 新金值均通过。
- 网页全量 `15 files / 57 tests`、TypeScript 和 Vite 生产构建通过；1440×900、768×1024 与 375×812 实页批准/执行流程无控制台错误、失败请求或设备动作，视觉门 `94/100`。
- 变更范围 Ruff 和格式检查、`git diff --check`、63 份 JSON 解析、54 份 Markdown / 204 个本地链接检查通过。仓库级 Ruff 仍报告 6 个不属于本工作包的既存问题，本包未混入无关清理。
- CPython 3.12.10 下从最终源码完成 sdist→wheel、独立 target 安装与 R5-E/OpenAPI 及跨对象篡改阻断 smoke；wheel 包含 R5-E 模块、fixture 和恰好两份当前网页哈希资产。
- 未运行真实设备实验、真实 holdout、模型晋升/回滚、TwinCAT compile、设备写入、Deployment Shadow、Controlled Trial、Closed Loop 或安全符合性评估。

## Work Package 35 — R5-I 本机模型生命周期与可回滚激活

Plan: `.omx/plans/r5i-model-promotion-transaction.md`

Summary: 已实现 Windows 本机 `ConditionalEffectModelBundle` 的独立签名决定、SQLite Registry 原子切换、提交后读回、运行监控与显式回滚；它不是 CNC 部署、受控试验或设备闭环。

### Decisions

- 晋升前权威重放完整 R5-G dossier 和 R5-H assessment；只有 `Passed + CaseScopedPassed`、内容谱系一致、决定人在 R5-G 准备人之外且授权 proof 有效时，Registry transaction 才可执行。
- 首版 proof 使用调用方注入的 HMAC-SHA256 key provider。密钥不写入请求、响应、数据库、网页或日志；该边界不冒充企业 PKI 或不可否认签名。
- Registry 使用调用方显式传入的本地 SQLite 路径，拒绝 `:memory:`、文件 URI 和 UNC；模型、授权、默认指针、generation、事件与监控窗口持久化。
- 模型注册、默认指针切换、generation、ActivationReceipt 在单一事务提交，随后重新读回。幂等重放、generation 冲突和提交前故障都有独立测试。
- 监控分别处理 bundle/generation、推理完整性、OOD、周期秒与线性误差毫米，不合成总分。`RollbackRequired` 只生成可审计触发证据；回滚仍需独立签名的本机 CLI 命令。
- Web 只提供 manifest、预检、Registry/监控读取和默认模型推理；没有 promote、activate 或 rollback 路由和按钮。有状态操作统一进入 `axiom model-lifecycle`。

### Deviations

- 计划草案把 PromotionDecision 单列为表；实现采用 `lifecycle_authorization` 同时保存 promotion 与 rollback 授权，并用 `kind` 区分，减少两套同构持久化逻辑。外部 schema、身份和权限没有合并。
- 网页预检端点需要验证既有签名，因此可由服务启动参数注入只读 key map；浏览器永远不接收 key，也不能调用 Registry 写操作。
- 监控的 `Open` 与 `RollbackRequired` 在 CLI 分别返回非零，避免自动化把需要人工处置的窗口解释为健康成功。

### Surprises

- 旧 Intelligence 测试的通用 fetch mock 会把未知 R5-I 端点返回成其他对象。R5-I 面板因此增加 schema/数组运行时边界检查；畸形只读响应不会再卸载整个工作台。
- 当前 `pnpm` 启动器因无法在线验证固定版本签名而拒绝运行；已使用仓库现有 `node_modules` 和 `npm run` 执行同一 TypeScript/Vitest/Vite 脚本，没有下载或替换依赖。

### Questions for review

- 后续若接入企业 PKI，应新增版本化非对称 proof/provider，不覆盖 HMAC 历史授权记录。
- 多机并发或集中审批必须另建远程 Registry 服务；本机 SQLite 不应扩展为网络共享事实源。

### Verification

- 最终源码收集 `931` 项；Windows CPython 3.14 开发档案全仓 `924 passed / 7 skipped`，冻结 CPython 3.12.10 发布档案全仓 `925 passed / 6 skipped`，R5-I/CLI/Web 定向终验 `44 passed`。唯一 warning 是既有 Starlette `TestClient` 对 `httpx` 的弃用提示。
- R5-I 变更范围 Ruff、`git diff --check`、65 个 JSON 解析与 58 份 Markdown / 225 个本地链接检查通过；仓库级 Ruff 仍只有 6 个不属于本工作包的既存问题。
- 网页全量 `17 files / 59 tests`、TypeScript 与 Vite 生产构建通过。1280×720 和 375×812 实页均无横向溢出或控制台 error/warning；未配置 Registry 保持只读，R5-I 写动作计数为 0，视觉门 `94/100`。生产 JS 561.72 kB，保留既有大 chunk 警告。
- v0.23.0 从源码构建 sdist，再从洁净解包源码构建 wheel，并安装到全新 CPython 3.12.10 环境。安装后版本、CLI、R5-I manifest、5 条只读/预检 OpenAPI 路由、零生命周期写路由和未初始化 Registry 零落盘 smoke 通过；wheel 仅含当前 `index-BnGCl8ia.css` / `index-DGm2MFL1.js` 两份网页资产，SHA-256 为 `45f10a7bd712d04912ffe45d1b78ab13721acfd1be8aaf1007dd7f558f9e2735`。
- 未运行真实 TwinCAT/TF6100 capture、真实跨设备/工况 holdout、设备部署、设备写入、Controlled Trial、Closed Loop 或设备/过程安全符合性评估。

## Work Package 34 — R5-H 候选条件效应模型真实 holdout 验证

Plan: `.omx/plans/r5h-candidate-real-holdout-validation.md`

Summary: 已实现 Windows-only 候选专属真实 holdout 合同、Python/API/UI 与文档基线。R5-H 将 R5-G 待审候选与采集前 operating-point study、完整 M5、R7-E/R4.1 字段证据绑定，独立验证候选而不复用 R5-B 的 R5-A 模型结论；默认无证据为 Open，任何结果都不执行模型晋升、注册或激活。

### Decisions

- 新建候选专属合同，不修改 R5-B/R5-C/R5-G 既有 schema。周期头只使用 exact M4 计划时长，线性误差头才使用 controller-live-read 的 X/Y/Z command-observation 最大误差。
- OOD probe 表示未见设备或工况；首片 operating point 本身必须留在 R5-C 与 R4 的共同声明域内，避免把参数域外弃权和现实上下文 OOD 混为一谈。
- Manifest 保存完整 planned M5，而不是只保存哈希；现场责任方可以下载原样执行，评估时服务端再重放 R4 并比较完整命令。
- 证据报告顺序也是预注册合同的一部分。相同 assessment 集合被重排时 fail closed 为 `Blocked/UnexpectedEvidence`，不由服务端静默排序。
- HTTP 使用无 `contentHash` 的 typed command，由服务端构造并封存 registration/assessment request；避免让浏览器实现第二套 canonical hash。
- dossier、Registration report 和现场报告是既有服务端输出的 sealed artifact。HTTP command 以 canonical JSON 外壳接收它们，再由服务端恢复完整强类型对象并重验全部嵌套哈希；这样不会因同一模型同时出现在 OpenAPI input/output 而改名既有 R7-E 组件。
- 网页只提供登记、下载、导入与评估动作。真实报告可以得到 `CaseScopedPassed`，但结果永久保持 `AwaitingIndependentHumanDecision`、`NotPerformed` 与零 registry/activation/device write。

### Deviations

- 正向 `CaseScopedPassed` 测试只使用测试代码生成的 controller-live-read 报告；没有新增 packaged real fixture，也没有把测试报告写入产品示例。
- 本片没有新增 CLI。研究包包含完整 M5，主要输入尺寸明显大于普通单次 Run；首版以 Python、HTTP 和网页多文件流闭合，后续若新增 CLI 必须沿用显式总大小预算。

### Surprises

- 第一轮 RED 测试使用了 `samplePeriod=0.12s`，被 R4 applicability 正确拒绝。代码核对确认 R5-C 冻结域是 `0.04…0.08s`；R5-H 已锁回共同适用域，未扩大模型能力。
- M5 的 `sourceM4ContentId` 使用五轴数值身份规范化，和直接对 M4 调用通用 `canonical_hash` 不保证相同。采集计划改为冻结 M5 自带的权威 source M4 identity，避免同一命令出现两种 M4 身份。
- R4.1 对 calibration/validation 要求同控制器身份和采样周期，同时 calibration 必须覆盖五轴激励。测试因此使用单独的五轴 calibration command，但 validation 始终严格使用预注册 planned M5。
- Pydantic 对已解析 float 与原 JSON int 的 canonical 词法可能不同；R5-H 的封存 helper 先构造 typed provisional model 再计算 hash，保证 Python 与 JavaScript JSON 往返使用同一类型化身份。
- JavaScript 原生 `JSON.stringify` 会把 IEEE-754 `-0` 写成 `0`，使冻结 M5 的 `q` 序列在浏览器往返后哈希失配。R5-H 专用序列化器只在遇到负零时写出 `-0.0`，其余 JSON 行为保持不变；组件测试和真实浏览器 Open assessment 流程均覆盖该路径。
- 新增 R5-H 输入模型后，FastAPI 曾把既有 `R7EExamplePayload` 响应组件改名为 `R7EExamplePayload-Output`。回归测试锁定旧引用；最终把三类 sealed artifact 输入隔离为 JSON 外壳并保留运行时完整校验，没有放宽旧 R7-E 契约或启用全局 schema 开关。

### Questions for review

- 暂无；真实样本统计容差仍须在取得现场噪声数据后另发 schema，首片保持预注册的零退化和 100% in-domain interval coverage。

### Verification

- 最终源码共收集 911 项。Windows CPython 3.14 开发档案全仓退出 0，为 `904 passed / 7 skipped`；冻结 CPython 3.12.10、`AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS=1`、Haswell/单线程 OpenBLAS 发布档案为 `905 passed / 6 skipped`。R5-H Python/API 15 项全部执行，覆盖 Open、CaseScopedPassed、Blocked、Refuted、顺序/时序/命令/身份错配、派生状态与聚合篡改、运行时标签伪造和非 Windows 拒绝。
- 网页全量 `16 files / 58 tests`、TypeScript 检查和 Vite 生产构建通过。真实浏览器完成 R5-D→R5-E→R5-F→R5-G→R5-H 预注册及缺证据评估，最终 `overallStatus=Open`、零模型/设备动作、控制台 0 error / 0 warning；桌面与 375px 移动截图视觉 verdict 为 `94 / pass`。
- CPython 3.12.10 按源码→sdist→洁净解包源码→wheel 构建并安装到全新虚拟环境；安装后从 `site-packages` 验证 R5-H manifest、三条 API、旧 `R7EExamplePayload` OpenAPI 引用及恰好两份当前网页资产。wheel SHA-256 为 `45866717945a18959dfbd0798565c015d920a179fbc5cea47419eed6befce2f7`。
- 仓库临时安装锁定 .NET SDK 8.0.424 后，locked restore、Release build、独立 Windows OPC UA conformance 与对应 Python 集成测试 `4 passed`；构建为 0 warning / 0 error，适配器和见证写入计数均为 0。
- R5-H 变更范围 Ruff、`git diff --check` 与 Markdown 本地链接检查通过。唯一保留的工具提示是 FastAPI TestClient 弃用警告和 Vite 551.78 kB 单 chunk 警告。
- 未运行真实 TwinCAT/TF6100 capture、真实跨设备/工况 holdout、独立 PromotionDecision、模型注册/激活/回滚/监控、Deployment Shadow、Controlled Trial、Closed Loop 或设备/过程安全符合性评估。

## Work Package 32 — R5-F 候选模型下游决策影响评估

Plan: `.omx/plans/r5f-candidate-downstream-impact.md`

Summary: 已在模型晋升前新增独立的 Windows-only 下游影响门。R5-F 对 R6 v2 的周期、线性误差和指令数三个意图分别运行 R5-C v1 基线与 R5-E v2 候选；两侧使用同一 135 点网格、同一约束和 27 次 exact F3/F4/R4 预算。冻结场景均无精确主目标退化，但候选仍固定为 `EvaluatedOnly`，没有替换默认模型。

### Assumptions

- 本片只评估 frozen synthetic SIL 决策影响，不依赖 Ubuntu/WSL、TwinCAT/TF6100、真实 capture、模型注册表或设备写入。
- R5-E CampaignReport 是候选的唯一可信来源；候选 Dataset、Split、TrainingReceipt、ParityReceipt、ModelBundle、Assessment 与 Campaign 内容身份必须逐项一致。
- R6 v2 的代理只决定有限预算内先验证哪些点；F3/F4/R4 和七个数学/碰撞门继续承担精确裁决。

### Decisions

- 旧 `optimization.search-request@2`、`axiom.optimization.recommendation-set@2` 和 R5-C v1 金值保持不变。候选消费路径使用独立 `optimization.search-request@3` 与 `axiom.optimization.recommendation-set@3`，没有扩大旧对象含义。
- R5-F 服务端先重放 R5-E，再自行构造两侧 SearchRequest；客户端不能提交自报 RecommendationSet。
- 每个场景保存筛选顺序变化、选择集合重合/差异、两侧 exact 集合、预算内最佳精确目标与共享 exact 点上的两项预测误差差值。预测误差只作诊断，不进入通过门。
- 影响门要求三场景均保持 135/27 且候选精确主目标不劣于基线；`Passed` 不表示一般模型收益、现实泛化、全局最优或安全性。
- 报告永久固定 `candidateUseStatus=EvaluatedOnly`、`modelPromotionStatus=NotPerformed`、Offline、零自动晋升、零设备写入和 reality Open；UI 不提供采用或晋升按钮。

### Deviations

- 初始计划考虑让旧 SearchRequest 接受两种 context；实现时发现这会让 `@2` 序列化语义失真，因此按计划允许的偏差发布候选专用 `@3`，搜索算法、预算和精确门不变。
- 没有增加模型注册、默认指针、审批、回滚、后台任务、持久化或新依赖；本包只生成不可变影响证据。
- 没有用扩大 exact 预算来制造无退化结果，也没有把秒、毫米和样本数合成总分。

### Surprises

- 候选在速度和质量意图中改变了代理排序，但三种意图的 27 个入选点集合仍与基线完全重合，紧凑指令排序也未改变；三种 exact best 值均相同。
- 这说明 holdout 指标改善与下游排序影响是不同证据：当前 fixture 支持“无精确退化”，不支持一般改进保证或自动晋升。
- Windows gstack `browse.exe` 仍缺少启动所需的 `src/server.ts`；本包继续用系统 Chrome 与 Playwright 完成真实 API 流、响应式与截图验收。
- 首次 wheel smoke 已完成实际 R5-E→R5-F 流程，但脚本最后把 fixture 的字符串环境键误当对象读取而非零退出；修正 fixture 路径后完整重跑并以 0 退出，产品逻辑和产物未修改。

### Numeric-environment-bound identities

- CPython 3.14 development — Campaign Report: `da0e4df9e940bdbe108763fb40b8690e110a0efaf72d5998d9026990370b06f0`; Candidate Context: `7c252c4b17dbc1ef3166f24212ca756d52354066777a0a69713cb84ac4de27a5`; Candidate Recommendations: speed `9f13b8556291c4cfdd26ea9bc0556ff191fea4c6f21bbfd37d9013011b977e53`, quality `be7c125e907c4fbd26d7987fd47ae1a03157b2d176ee5d6e35613c3a4ba0b971`, compact `3aee9374ab5cf6cbbe4e42d3a360b4a65e7036983b34c4c575e18da085a96177`; Impact Report: `c995110f3c19217973c4578e6e954370c66d840626ab6680b9e275b3745e671a`.
- CPython 3.12.10 release — Campaign Report: `b268119e57884a178fc89b6cb6c6515419919aa1277d7ee206466218bd806528`; Candidate Context: `81e174e8f931e718443562f71f332a6ff292772f37a68a15d633b264e7df92b4`; Candidate Recommendations: speed `2caefaa03d1d689436884fcf3687a4e974d04c7e6bab49f4d97e22d18caecec5`, quality `65f0d2a3f8e52b2ddcb8d602b2aa081f511504955c39cfc668b96d44c2c89009`, compact `cce6efd794615d59d5013c1c65506269f4e261d7fd95721e8e6dab0b6b5ff7ce`; Impact Report: `f9abd124c7c54513f7d27bad8ca7d829e1e3ba8464294cc84f39c371d338053e`.

### Verification

- 最终源码全仓共 886 项：Windows CPython 3.14 开发档案 `880 passed / 6 skipped`；冻结 CPython 3.12.10 + Haswell/单线程 OpenBLAS 发布档案 `881 passed / 5 skipped`。两档均只出现既有 FastAPI TestClient 弃用警告。
- 网页全量 `15 files / 57 tests`、TypeScript 与 Vite 生产构建通过；1440×900 和 375×812 真实流程无应用请求失败或横向溢出，视觉门 `94/100`。
- 本包 Python 变更范围 Ruff、`git diff --check`、6 份相关 fixture JSON 解析和 210 个 Markdown 本地链接检查通过。仓库级 Ruff 仍为 6 个既存问题（5 个未使用导入、1 个旧 `__all__` 名称），未混入无关清理。
- CPython 3.12.10 下从最终源码生成 sdist，再由 sdist 构建 wheel、安装到独立 target 并完成 R5-E→R5-F、发布金值、OpenAPI 与包内容 smoke。wheel 包含 R5-F 模块/fixture、候选 R6 v2 合同和恰好两份当前网页资产；SHA-256 为 `0513e4038f6926b7cce11eb41084fcb3aaa930e2627e91754058660df4d4ede9`。
- 未运行真实设备实验、真实 holdout、模型晋升/回滚、TwinCAT compile、设备写入、Deployment Shadow、Controlled Trial、Closed Loop 或安全符合性评估。

## Work Package 33 — R5-G 模型晋升就绪审查包

Plan: `.omx/plans/r5g-model-promotion-readiness.md`

Summary: 已把 R5-E 候选与 R5-F 下游影响证据整理为 Windows-only、内容寻址且可确定性重放的 `ModelPromotionReadinessDossier`。默认冻结场景可得到 `ReadyForIndependentReview`，但决定状态固定为 `AwaitingIndependentHumanDecision`；默认模型、registry、activation、deployment 和设备状态均未改变。

### Assumptions

- 本工作包只准备独立审查材料，不实现或模拟模型批准、注册、激活、默认切换、回滚执行与运行监控。
- R5-E 的显式批准仅授权一批 synthetic SIL 实验；它不是模型晋升授权。R7-A 的 policy replay 也不能替代模型责任人的独立决定。
- 当前只支持 Windows。Ubuntu、WSL、真实 TwinCAT capture 和跨设备/工况 holdout 不进入本工作包。

### Decisions

- R5-G 保持应用层有类型对象，不新增 DomainPack 或 Core 状态。服务端接收完整 R5-F 报告后自行重放 R5-E/R5-F，并派生所有检查状态。
- `ReadyForIndependentReview` 精确绑定五项检查：R5-E candidate gate、R5-F impact gate、确定性重放、唯一候选谱系和 rollback baseline 绑定。
- 真实 holdout、独立人工决定、model registry、activation/default switch、rollback execution 与 runtime monitoring 六项门在审查包中逐项保持 `Open`。
- `preparedBy` 与三项确认只记录审查准备者已看见安全边界，不生成 `humanApprovalPresent`，也不改变任何模型状态。
- 网页只提供“生成晋升就绪审查包”；结果展示检查、剩余门、基线/候选身份和永久零状态变更边界。

### Deviations

- 没有实现真正的模型晋升或内存 registry。当前仓库缺少授权主体、持久化、激活读回、回滚和监控合同，用临时状态模拟会制造不可恢复的伪完成。
- 没有把审查准备请求抽成通用审批框架；当前只有 R5 候选模型使用该语义，提前上移到 Core 没有复用证据。
- 没有增加依赖、数据库、后台任务、缓存或设备接口。

### Surprises

- 五项 readiness evidence 已全部存在于 R5-F 报告及其 source Campaign 中；不需要修改 R5-E、R5-F 或 R6 v2 既有 schema 和金值。
- 初始字段名 `notDeviceSafeAcknowledged` 会被仓库禁语扫描机械匹配为 `DeviceSafe`。改为语义等价但边界更准确的 `deviceSafetyNotEstablishedAcknowledged`，既保留显式确认，也避免对外合同出现被禁止的安全 Claim token。
- 首次真实浏览器流程在 R5-G POST 返回 422：JavaScript 把 R6 网格末端的 `feedOverride: 1.0` 序列化为 `1`，而通用 `ParameterSet.values` 保留数值类型，导致九个候选哈希失配。新增回归测试后，只在 R5-G intake 按冻结参数 schema 恢复两个浮点坐标；没有改全局 canonical hash 或任何既有 fixture。
- 单一 candidate context 在三个场景中保持一致，但其内容身份按 CPython 数值环境分别冻结，不能跨开发/发布档案比较。

### Numeric-environment-bound identities

- CPython 3.14 development — Impact Report: `c995110f3c19217973c4578e6e954370c66d840626ab6680b9e275b3745e671a`; Readiness Request: `7c63f19e29700938d918431e91ee48ec238baab428bab89ec29eb709f34a38dc`; Dossier: `61156d92ec989b275e476f30c8f491fc25540686b298922c8a008186ac9311fb`; Baseline: `4202c928a63899da370a12d9a8fe7a90965a497605f79ddc4b2301b3895a36d1`; Candidate: `cc6a08dc31256ca2e3e826d2ff140044ae6f3bb37ee9d6e702b2cc291c02e3cc`.
- CPython 3.12.10 release — Impact Report: `f9abd124c7c54513f7d27bad8ca7d829e1e3ba8464294cc84f39c371d338053e`; Readiness Request: `ac6350e5cc8c12684a0a92c591cc55cb4af4e0f1d45d2d507003c4f562b94504`; Dossier: `f6f0756e12f0ce956b8237e73dbe26612552acdd6715e5d77c2223b0a537d26c`; Baseline: `dbcbfe28aa6513046baf9d4de07785049dae811ff2830d5b874d5eb52b37f222`; Candidate: `4e2b92f37cc21c6ee24ff547033622f6f91b94d55f948b561cc50bfffaf0437f`.

### Verification

- R5-G Python/API 定向测试在 CPython 3.14 开发档案与 CPython 3.12.10 发布档案各为 9 passed / 1 skipped；两档分别只跳过另一环境的 fixture identity。开发环境全仓 896 collected、退出 0，为 889 passed / 7 skipped；冻结 `OPENBLAS_CORETYPE=Haswell`、OpenBLAS/OMP 单线程并启用环境金值阻断的 CPython 3.12.10 发布环境为 890 passed / 6 skipped / 1 warning。
- 网页全量测试为 15 files / 57 tests passed，TypeScript 检查与生产构建通过。真实浏览器完成 R5-D→R5-E→R5-F→R5-G 全流程；1440px 桌面与 375px 移动端均无页面级横向溢出，未发现激活/部署控件，最终视觉 verdict 为 94 / Pass。
- R5-G 相关 Ruff、`git diff --check`、65 个 JSON 文件解析与 161 个本地 Markdown 链接检查通过。发布解释器按 sdist→wheel 洁净路径构建并隔离安装 `axiom_evaluator-0.22.0-py3-none-any.whl`；SHA-256 为 `6fa5607627702103a770ddf2e8f34f06e13696141e7ef63b146aa196497ddb7c`。安装目录重放得到发布档案 Dossier `f6f0756e12f0ce956b8237e73dbe26612552acdd6715e5d77c2223b0a537d26c`，R5-G manifest API 返回 200，且 wheel 只包含当前 `index-Bga9NqZK.css` / `index-BqQrkOI0.js` 两份网页资产。
- 未运行真实设备实验、真实 holdout、模型晋升/回滚、TwinCAT compile、设备写入、Deployment Shadow、Controlled Trial、Closed Loop 或安全符合性评估。
