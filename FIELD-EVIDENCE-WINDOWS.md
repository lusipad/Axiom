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

## 1. 采集并验收两份 R7-E 输入

在部署环境外部运行 `.NET` Witness，分别获得 calibration 与 validation 的 `shadowEvidence`。每份 R7-E assessment 输入都必须包含：

- 相同的显式 `caseId`；
- `vendorProfile`、`runtimeEvidence`、`witnessProfile`；
- `controllerProfile`、`authority`、`captureAuthorization`；
- 对应的 `command` 与 `shadowEvidence`。

先用 `POST /api/v1/control/r7e/assess` 单独重验每份输入。只有两份返回的 `readinessAudit.deploymentShadowStatus` 都是 `Passed`，编排器才会创建 calibration/validation pair。

外部命令或 Shadow evidence 缺少 `caseId` 会被拒绝；Axiom 不再为现场输入填入共享的默认 Case。

## 2. 组成现场验收请求

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
