# Windows 现场证据验收指南

本指南说明如何在 Windows 上把两次独立的 Beckhoff TwinCAT 3 / TF6100 只读 Shadow 采集送入 Axiom，得到一份确定性的 R7-E → R4.1 现场证据报告，并在计划把多个 dossier 用作 R5-B 真实 holdout 时预先登记 Campaign。

这条流程只读取和核验证据。它不连接 PLC、不写参数、不调用方法，也不产生 `DeviceSafe`、`ProcessSafe`、试切许可或闭环控制权限。

## 前置条件

- Windows AMD64；发布验收环境为 CPython 3.12.10 与 .NET SDK 8.0.424。
- 已由部署责任人绑定的 Beckhoff Vendor Profile、TF6100 运行时证据、七节点 Witness Profile 和控制器只读主体。
- 同一 `caseId` 下的两次独立运行：第一次用于 calibration，第二次用于 holdout validation。
- 两次运行必须使用不同的 M5 command 内容身份、采集授权、授权时间窗和 Shadow evidence 内容身份；validation 必须晚于 calibration。
- 每次采集完整覆盖 M5 sample index，且 Write/Method Call 计数均为 0。
- 若本批现场运行将进入 R5-B，必须在任何 calibration/validation capture 打开前完成 §0 的 Campaign Registration；事后生成的 selection 不能关闭 holdout 隔离门。

仓库默认 Profile 和 [`examples/field-evidence.open-request.json`](examples/field-evidence.open-request.json) 只用于演示开放门，不包含真实 NodeId、凭据、许可证或设备数据。

如果现场还没有七节点 Witness Profile，先按 [Beckhoff 只读见证部署指南](BECKHOFF-WITNESS-DEPLOYMENT-WINDOWS.md) 导入 `FB_AxiomShadowWitness.TcPOU`、显式绑定 namespace/NodeId，并运行 `axiom beckhoff-witness-deployment`。该预检即使通过也不代表已经采集。

## 0. 为 R5-B 预先登记现场 Campaign

本节只在这些运行将作为 R5-B 真实 holdout 时必需；仅做单设备 R4.1 双运行验收可以跳过。登记必须发生在采集前，并使用尚未携带 `realHoldoutSet` 的冻结 R5-B 基线 RunSpec。

准备 `axiom.intelligence.real-holdout-campaign-registration-request@1`。请求至少规划三个 slot：两个 in-domain slot 必须跨两个 device 和两个 condition，另一个是 OOD probe。每个 slot 要在采集前冻结 `caseId`、`assessmentId`、calibration/validation pair ID、role、topology、trajectory family、task、condition、batch、device、两份 M5 command content ID 和最大时间误差。计划身份无法提前确定时，不得把之后采集的数据冒充为预注册 holdout。

```powershell
axiom real-holdout-campaign .\real-holdout-campaign-request.json |
  Set-Content -Encoding utf8 .\real-holdout-campaign-report.json
$LASTEXITCODE
```

退出码 `0` 表示 Campaign Manifest 与 Registration 已按请求确定性封存；`2` 表示请求无效。报告中的 `countsTowardReality` 固定为 `false`。`registeredAt`、`registrationAuthorityId` 与 `registrationRecordId` 来自外部数据/试验责任方；Axiom 只验证内容身份和后续 capture 的时间先后，不提供可信时间戳、签名或物理真实性证明。保留完整报告，§6 会使用其中的 `manifest` 与 `registration`。

## 1. 采集并验收两份 R7-E 输入

在部署环境外部运行 `.NET` Witness，分别获得 calibration 与 validation 的 `shadowEvidence`。每份 R7-E assessment 输入都必须包含：

- 相同的显式 `caseId`；
- `vendorProfile`、`runtimeEvidence`、`witnessProfile`；
- `controllerProfile`、`authority`、`captureAuthorization`；
- 对应的 `command` 与 `shadowEvidence`。

采集完成后，不要手工复制这些对象到一个大 JSON。用同一个离线 `.NET` 程序把原始支持文件与本次 Shadow evidence 组装为一份可直接交给 Python 的 R7-E assessment 输入：

```powershell
axiom-opcua-shadow beckhoff-shadow-assessment `
  --case-id site.part-family-17@1 `
  --vendor-profile .\beckhoff-bound-profile.json `
  --runtime-evidence .\beckhoff-runtime-evidence.json `
  --witness-profile .\beckhoff-shadow-witness-profile.json `
  --controller-profile .\controller-profile.json `
  --authority .\readonly-authority.json `
  --capture-authorization .\capture-authorization.json `
  --command .\m5-command.json `
  --shadow-evidence .\beckhoff-shadow-calibration.json `
  --output .\calibration.r7e.json
```

该命令不建立网络连接。它重验所有 `contentHash` / `contentId`、Profile/runtime/authority/authorization/command/Shadow 绑定、授权时间窗、`controller-live-read + declaredReal` 来源和零 Write/Call 收据，并用 CreateNew 语义写出文件；任一绑定不一致时不生成输出。对 validation 使用另一组 command、authorization 和 Shadow evidence 重复执行，得到 `validation.r7e.json`。

可先用 `POST /api/v1/control/r7e/assess` 单独重验每份输入。只有两份返回的 `readinessAudit.deploymentShadowStatus` 都是 `Passed`，编排器才会创建 calibration/validation pair。

外部命令或 Shadow evidence 缺少 `caseId` 会被拒绝；Axiom 不再为现场输入填入共享的默认 Case。

## 2. 组成现场验收请求（兼容入口）

请求结构如下。`calibration` 和 `validation` 都是上一步的 R7-E assessment 输入，而不是未经核验的轴数组：

```json
{
  "schemaId": "axiom.field-evidence-assessment-request@1",
  "schemaVersion": 1,
  "assessmentId": "site.line-1.part-family-17.assessment@1",
  "calibrationPairId": "site.line-1.part-family-17.calibration@1",
  "validationPairId": "site.line-1.part-family-17.validation@1",
  "calibration": {
    "caseId": "site.part-family-17@1",
    "vendorProfile": {},
    "runtimeEvidence": {},
    "witnessProfile": {},
    "controllerProfile": {},
    "authority": {},
    "captureAuthorization": {},
    "command": {},
    "shadowEvidence": {}
  },
  "validation": {
    "caseId": "site.part-family-17@1",
    "vendorProfile": {},
    "runtimeEvidence": {},
    "witnessProfile": {},
    "controllerProfile": {},
    "authority": {},
    "captureAuthorization": {},
    "command": {},
    "shadowEvidence": {}
  }
}
```

上面的空对象只是字段示意，不是可通过的真实输入。不要手工修改任何 `contentHash`；内容身份会在 R7-E、pair 和最终报告三个层次重新计算。

## 3. 用 CLI 验收

推荐直接传入上一步的两份 R7-E 文件，不再手工组成双运行请求：

```powershell
axiom field-evidence `
  --calibration .\calibration.r7e.json `
  --validation .\validation.r7e.json `
  --assessment-id site.line-1.part-family-17.assessment@1 `
  --calibration-pair-id site.line-1.part-family-17.calibration@1 `
  --validation-pair-id site.line-1.part-family-17.validation@1 |
  Set-Content -Encoding utf8 .\field-evidence-report.json
$LASTEXITCODE
```

完整 `axiom.field-evidence-assessment-request@1` 文件仍是兼容入口：

```powershell
axiom field-evidence .\field-evidence-request.json |
  Set-Content -Encoding utf8 .\field-evidence-report.json
$LASTEXITCODE
```

退出码：

- `0`：同一设备、同一 Case 的两个 R7-E 门和 R4.1 holdout reality gate 均为 `Passed`；
- `1`：报告有效，但结果是 `Open`、`Blocked` 或 `Refuted`；
- `2`：JSON、schema、Case 或 pair 契约无效。

可先运行开放示例检查安装和退出码语义；它按设计返回 `Open` 和退出码 `1`：

```powershell
axiom field-evidence .\examples\field-evidence.open-request.json
```

## 4. 用 HTTP 或网页验收

- `POST /api/v1/field-evidence/assess`：提交完整双运行请求，返回 `axiom.field-evidence-assessment-report@1`。
- 网页的 **Field Evidence** 工作台：分别导入 calibration 与 validation 两份 R7-E payload，再点击“运行双证据验收”。网页会保留各自的 `caseId`，并调用同一个服务端编排器。

报告同时保存两份 R7-E assessment、两个有类型 pair（仅在 R7-E 双门通过时存在）、R4.1 assessment、最终状态和 `contentHash`。重复提交相同输入必须得到相同报告哈希。

## 5. 结果边界

`Passed` 只表示：在一台明确设备、一个明确 Case、两次独立只读运行的范围内，冻结后的物理模型通过了 holdout 拟合和残差分解门。

它不表示：

- 跨设备或跨工况泛化；
- Controlled Trial 或 Closed Loop 已开放；
- 控制器、机床、刀具、夹具或工艺过程安全；
- 可写参数、可启动循环或可绕过现场责任链。

这些状态在现场证据报告中固定为 `Open` 或 `NotAssessed`，不能由客户端覆盖。

## 6. 把预注册的多个现场 dossier 送入 R5-B

单个 `field-evidence-report.json` 只证明一台设备、一个 Case 的 R4.1 validation。R5-B 还要求至少两个 in-domain Case 跨两个 device 与两个 condition，并额外提供一个 OOD probe。不要把 calibration 运行再次当作 holdout；每个 dossier 只能贡献自己的 validation 运行，并且必须与 §0 预登记的对应 slot 完全一致。

为每个 dossier 准备一个 `RealHoldoutIntakeCase` JSON：

```json
{
  "report": {},
  "role": "in-domain",
  "topology": "head-table",
  "trajectoryFamily": "site-family-a",
  "taskId": "site-task-a",
  "conditionId": "site-condition-a",
  "batchId": "site-batch-a",
  "maximumTimeErrorSeconds": 0.000001,
  "deviceProfile": {},
  "clockMapping": {},
  "coordinateAlignment": {},
  "lineage": {},
  "bindings": []
}
```

空对象和空数组仅表示字段位置，不是有效输入。`report` 必须是本指南前几步得到的完整报告；设备 Profile 必须与报告中的 controller machine/vendor/family 一致；坐标对齐必须来自真实 calibration record；lineage 必须绑定 validation M5 command 并保留 F4 七个数学 Claim；bindings 必须按 X/Y/Z/B/C 顺序完整覆盖五个 scalar channel，X/Y/Z 使用 `mm`，B/C 使用 `rad`。

治理记录单独保存为完整 `RealHoldoutGovernance` JSON。其 owner、授权、许可、用途和保留策略由数据责任人提供，`attestedAt` 不得早于所有 Case capture 完成时刻。该采集后治理 attestation 与 §0 的采集前 Campaign Registration 是两个不同对象；前者不能补造后者。

把同一个无 `realHoldoutSet` 的基线 RunSpec、治理记录、§0 报告中的 `manifest` / `registration` 和全部 Case 组成严格请求：

```json
{
  "schemaId": "axiom.intelligence.preregistered-real-holdout-intake-request@1",
  "schemaVersion": 1,
  "intakeId": "site.real-holdout-intake@1",
  "baseRunSpec": {},
  "governance": {},
  "campaignManifest": {},
  "campaignRegistration": {},
  "cases": []
}
```

空对象和空数组只是字段位置，不是有效输入。严格 CLI 接受完整请求文件：

```powershell
axiom real-holdout-intake .\preregistered-real-holdout-intake.json |
  Set-Content -Encoding utf8 .\preregistered-real-holdout-intake-report.json
$LASTEXITCODE
```

退出码为 `0=Passed`、`1=Open/Blocked`、`2=Malformed`。HTTP 入口是 `POST /api/v1/intelligence/r5b/intake/assess-preregistered`；Campaign 登记入口是 `POST /api/v1/intelligence/r5b/campaigns/register`。网页 **Intelligence R5-B** 工作台可导入 Campaign request 进行登记，也可导入已封存的 registration report，再导入 governance 与多个 Case 文件运行同一严格验收。

严格 intake 会验证：Registration 严格早于每个 calibration/validation capture 的 `openedAt`；实际设备、命令、Case、pair、任务、工况、批次与 role 逐项匹配计划 slot；以及既有来源、R3/R4.1、治理、单位、时间、内容身份和隔离门。通过后，输出 selection 必须带 `selectionEvidenceStatus=PreRegistered`，并绑定 Campaign Manifest/Registration 的两个内容哈希。网页可分别下载 Manifest、Registration、`RealPairedHoldoutSet` 和可执行 R5-B RunSpec。

### 6.1 v0.22.0 兼容投影入口

以下多文件命令和 `axiom.intelligence.real-holdout-intake-request@1` 仍用于重放 v0.22.0 投影合同：

```powershell
axiom real-holdout-intake `
  --base-run-spec .\r5b-base-run.json `
  --governance .\real-holdout-governance.json `
  --case .\case-machine-a.json `
  --case .\case-machine-b.json `
  --case .\case-ood.json |
  Set-Content -Encoding utf8 .\real-holdout-intake-report.json
$LASTEXITCODE
```

完整 v1 request 文件也可作为位置参数提交，对应 HTTP 入口是 `POST /api/v1/intelligence/r5b/intake/assess`。该路径保留解析、投影和历史重放，但它在看到 dossier 后才生成 selection；即使旧报告的 `countsTowardReality=true`，当前 R5-B runtime 也会因缺少 `PreRegistered` Campaign 身份而返回 `InsufficientContext / RealHoldoutSelectionNotPreRegistered`。新的现场泛化工作不得用此兼容入口替代 §0 与严格 intake。

严格 `intakeStatus=Passed` 只表示报告包含带预注册选择证据的可执行 `r5bRunSpec`。继续执行该 RunSpec 后，R5-B 才会计算 improvement、conformal coverage、alignment coverage 与 OOD abstention，并决定是否支持仅限所提交 Case 的泛化 Claim。Campaign Registration、Intake 和 R5-B 都不会开放 Controlled Trial、Closed Loop、DeviceSafe 或 ProcessSafe。

## 7. 用现场报告证伪 R5-G 中的具体候选

R5-H 与 §6 的 R5-B 不是同一个模型评估。R5-B 面向 R5-A 残差 `ModelBundle`；R5-H 面向 R5-G dossier 中唯一的 R5-C/R5-E 双输出条件效应候选。新的候选审查不得拿 R5-B 报告直接关闭 R5-G 的真实门。

在打开任何 validation capture 前，先在 **Intelligence R5-C–R5-H** 工作台完成以下操作：

1. 完成 R5-E、R5-F 和 R5-G，得到 `ReadyForIndependentReview` dossier；
2. 填写外部登记时间、责任方与记录号；
3. 预登记至少两个跨设备/工况的 `in-domain` Case 和一个 `ood-probe`；
4. 生成并下载 R5-H 预注册包。该包包含每个操作点的完整 M5、M4/M5 哈希、精确周期与数值环境；
5. 现场采集时，validation 必须执行对应 Case 的原样 M5，设备、采样周期与 `assessmentId` 不得重绑。

完成每个 Case 的 calibration/validation 后，按本指南 §4 生成一份完整 `FieldEvidenceAssessmentReport`。回到 R5-H 面板，按预登记 Case 顺序一次导入全部 JSON 并运行评估。等价 HTTP 流程为：

- `GET /api/v1/intelligence/r5h/manifest`；
- `POST /api/v1/intelligence/r5h/studies/register`；
- `POST /api/v1/intelligence/r5h/holdout/assess`。

网页会在登记、评估和研究包下载时保留 M5 关节坐标中的 IEEE-754 `-0`，序列化为 `-0.0`。自建 HTTP 客户端也必须满足这一点；JavaScript 原生 `JSON.stringify(-0)` 会输出 `0`，从而改变冻结的 M5 内容身份并被服务端拒绝。dossier、Registration report 和现场报告虽然以 JSON artifact 提交，服务端仍会恢复完整类型并重验所有嵌套哈希。

客户端不提交 actual、RMSE、coverage 或 `Passed`。服务端重放全部上游对象；周期 target 使用预登记 M4 的 exact planner 时长且不计入 reality，线性误差 target 才从 validation X/Y/Z 序列计算 `max(abs(command-observation))`。B/C 的 `rad` 观测不会混入毫米标签。

证据不全返回 `Open`；候选目标退化或区间未覆盖返回 `Refuted`；登记晚于 capture、报告顺序/身份、设备、采样周期、M5 或 R4.1 reality 门不一致返回 `Blocked`。`CaseScopedPassed` 只限本次预登记 Case，仍等待独立人工决定，并且不允许模型 registry 写入、激活、默认切换、部署或设备写入。仓库和发布包不提供可冒充真实现场结果的正向 fixture。
