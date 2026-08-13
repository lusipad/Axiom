# Windows 现场证据验收指南

本指南说明如何在 Windows 上把两次独立的 Beckhoff TwinCAT 3 / TF6100 只读 Shadow 采集送入 Axiom，得到一份确定性的 R7-E → R4.1 现场证据报告。

这条流程只读取和核验证据。它不连接 PLC、不写参数、不调用方法，也不产生 `DeviceSafe`、`ProcessSafe`、试切许可或闭环控制权限。

## 前置条件

- Windows AMD64；发布验收环境为 CPython 3.12.10 与 .NET SDK 8.0.424。
- 已由部署责任人绑定的 Beckhoff Vendor Profile、TF6100 运行时证据、七节点 Witness Profile 和控制器只读主体。
- 同一 `caseId` 下的两次独立运行：第一次用于 calibration，第二次用于 holdout validation。
- 两次运行必须使用不同的 M5 command 内容身份、采集授权、授权时间窗和 Shadow evidence 内容身份；validation 必须晚于 calibration。
- 每次采集完整覆盖 M5 sample index，且 Write/Method Call 计数均为 0。

仓库默认 Profile 和 [`examples/field-evidence.open-request.json`](examples/field-evidence.open-request.json) 只用于演示开放门，不包含真实 NodeId、凭据、许可证或设备数据。

如果现场还没有七节点 Witness Profile，先按 [Beckhoff 只读见证部署指南](BECKHOFF-WITNESS-DEPLOYMENT-WINDOWS.md) 导入 `FB_AxiomShadowWitness.TcPOU`、显式绑定 namespace/NodeId，并运行 `axiom beckhoff-witness-deployment`。该预检即使通过也不代表已经采集。

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

## 6. 把多个现场 dossier 送入 R5-B

单个 `field-evidence-report.json` 只证明一台设备、一个 Case 的 R4.1 validation。R5-B 还要求至少两个 in-domain Case 跨两个 device 与两个 condition，并额外提供一个 OOD probe。不要把 calibration 运行再次当作 holdout；每个 dossier 只能贡献自己的 validation 运行。

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

治理记录单独保存为完整 `RealHoldoutGovernance` JSON。其 owner、授权、许可、用途和保留策略由数据责任人提供，`attestedAt` 不得早于所有 Case capture 完成时刻。再保存一个没有 `realHoldoutSet` 的冻结 R5-B 基线 RunSpec。CLI 可直接组装并评估：

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

退出码为 `0=Passed`、`1=Open/Blocked`、`2=Malformed`。完整 `axiom.intelligence.real-holdout-intake-request@1` 文件也可作为位置参数提交。HTTP 入口是 `POST /api/v1/intelligence/r5b/intake/assess`；网页 **Intelligence R5-B** 工作台可多选 Case 文件、导入一个治理文件，并使用内置 Open 基线或先导入的 R5-B RunSpec。Intake 通过后，网页可分别下载投影后的 `RealPairedHoldoutSet` 和可执行 R5-B RunSpec。

`intakeStatus=Passed` 只表示报告包含可执行的 `r5bRunSpec`。继续执行该 RunSpec 后，R5-B 才会计算 improvement、conformal coverage、alignment coverage 与 OOD abstention，并决定是否支持仅限所提交 Case 的泛化 Claim。Intake 和 R5-B 都不会开放 Controlled Trial、Closed Loop、DeviceSafe 或 ProcessSafe。
