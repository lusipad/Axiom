# Beckhoff 只读见证部署指南（Windows）

本指南把 Axiom 的七项 R7-E 见证信号接入现有 TwinCAT 3 PLC 工程。仓库提供的是可审计的只读源模板和离线绑定预检器，不是自动部署器；它不会连接 PLC、激活配置、写轴、启停循环或调用 OPC UA Method。

## 交付内容

- `FB_AxiomShadowWitness.TcPOU`：TwinCAT PLC 功能块，锁存 M5 命令内容哈希、样本索引和 X/Y/Z/B/C 五轴回读。
- `axiom.control.beckhoff-shadow-witness-deployment-request@1`：把现场 namespace URI / NodeId、同一 R7-D runtime 的七节点属性验证证据和 M5 command 显式绑定为 Witness Profile 的请求。
- `axiom beckhoff-witness-deployment REQUEST.json`：离线预检命令。
- `POST /api/v1/control/r7e/deployment/assess`：与 CLI 同义的 HTTP 入口。

公开示例 [`examples/beckhoff-witness-deployment.open-request.json`](examples/beckhoff-witness-deployment.open-request.json) 没有真实 runtime、M5 command 或 NodeId，按设计返回 `Open` 和退出码 `1`。

## 1. TwinCAT 工程前置条件

- Windows、TwinCAT 3 Build 4026+ 和 TF6100 OPC UA Server Full license。
- PLC 工程启用 TMC/符号下载，TF6100 能发现目标 PLC runtime。
- 由控制器责任人提供只读 OPC UA 主体；ACL 只授予目标 namespace/node 的 Browse、Read、Subscribe。
- 上游逻辑能在同一个 PLC 周期提供权威 M5 `STRING(64)` content hash、单调 `UDINT` sample index 和五轴回读。sample index 不能由此模板自行递增。

Beckhoff 官方说明中，`{attribute 'OPC.UA.DA' := '1'}` 用于暴露符号，`{attribute 'OPC.UA.DA.Access' := '1'}` 将其限制为只读；服务端应以 `BadNotWriteable` 拒绝写请求。模板还用 `OPC.UA.DA.Alias` 冻结七个可验证的 BrowseName，避免依赖工程层级对默认名称的影响。见 [OPC UA Data Access pragma](https://infosys.beckhoff.com/content/1033/tf6100_tc3_opcua_server/15620329099.html) 与 [Beckhoff 属性表](https://infosys.beckhoff.com/content/1033/tf6100_tc3_opcua_server/15563857163.html)。

## 2. 导入并实例化功能块

在 TwinCAT PLC 工程中导入发布包 `deployment/FB_AxiomShadowWitness.TcPOU`。TwinCAT 支持导入单个 `.TcPOU` / `.TcGVL` / `.TcDUT` 对象；见 [PLC project import](https://infosys.beckhoff.com/content/1033/tc3_automationinterface/242732427.html)。

在已有程序中实例化并从现有只读状态源调用：

```iecst
VAR
    fbAxiomShadow : FB_AxiomShadowWitness;
END_VAR

fbAxiomShadow(
    bPublishEnabled := bAxiomObservationWindow,
    sCommandContentHash := sAuthoritativeM5ContentHash,
    nSampleIndex := nAuthoritativeM5SampleIndex,
    fAxisX := fActualPositionX,
    fAxisY := fActualPositionY,
    fAxisZ := fActualPositionZ,
    fAxisB := fActualPositionB,
    fAxisC := fActualPositionC
);
```

`bPublishEnabled=FALSE` 时，模板把公开 sample index 保持为 `16#FFFFFFFF` 并清除本次发布状态；重新开窗后，首次有效索引 0 因此一定形成值变化。若观测窗口未关闭就更换 command hash，模板也只发布并保持 sentinel，不会把新命令锁存到旧窗口；部署方必须先关闭窗口，再以新命令重新打开。正常窗口内，模板先锁存 command hash 和五轴值，最后写入公开的 witness sample index。采集端仍会在索引通知后执行一次七节点 batch Read；该次序缩小撕裂窗口，但不把 OPC UA 变成实时总线。Beckhoff 明确说明 OPC UA Client/Server 不是实时通信，无法保证请求的 sampling/publishing interval，见 [TF6100 real-time limitation](https://infosys.beckhoff.com/content/1033/tf6100_tc3_opcua_server/15551515659.html)。

模板不包含 `RETAIN`、运动控制功能块、cycle start、feed hold、reset、jog、程序传输、轴写入或 Method Call。`bPublishEnabled` 只是观测窗口开关，不是设备授权。

## 3. 启用符号并配置只读权限

1. 启用 PLC 工程的 TMC/symbol 下载并重新生成工程。
2. 在 TF6100 Configurator 中只暴露功能块实例的七个输出成员。
3. 为采集主体配置 namespace/node 级 Browse、Read、Subscribe；不要授予 Write 或 Method Call。
4. 通过独立的 R7-D verifier 记录 BuildInfo、TF6100 Full license、五轴访问级别和专用非执行 canary 拒写收据。
5. 记录服务端实际返回的 namespace URI 与 string identifier。NodeId 取决于 PLC 工程名、实例路径和服务端 namespace，仓库不会从变量名猜测。

TF6100 的用户/组和 node 权限配置见 [Security configuration](https://infosys.beckhoff.com/content/1033/tf6100_tc3_opcua_configurator/15555250187.html)。

## 4. 生成部署请求

复制 Open 示例并填入：

- 已通过 R7-D 的 Bound `vendorProfile`；
- 与该 Profile 内容身份一致的 `vendor-runtime` `runtimeEvidence`；
- 本次要观测的完整 M5 `command`；
- 严格按下列顺序排列的七个 `nodes`：
  1. `command.content-hash`
  2. `command.sample-index`
  3. `machine.axis.X.position`
  4. `machine.axis.Y.position`
  5. `machine.axis.Z.position`
  6. `machine.axis.B.position`
  7. `machine.axis.C.position`

每个声明节点只提交 `canonicalSignalId`、绝对 `namespaceUri` 和 NodeId 的 string `identifier`。不要把 `ns=...;s=...` 整串放进 `identifier`；`.NET` Adapter 会根据 namespace URI 解析 namespace index，再用该 identifier 构造 string NodeId。仅有这七个声明不能通过节点门；`witnessNodeVerification.nodes` 必须与其逐项同一身份，并分别观测到 `sWitnessCommandContentHash`、`nWitnessSampleIndex`、`fWitnessAxisX/Y/Z/B/C` 的 BrowseName 和冻结类型/只读访问级别。这样 X/Y 等同类型节点互换也会被阻断。

`maximumTimestampUncertaintyMs` 是该 Case 的显式验收声明，不是 Axiom 自动推荐的安全阈值，必须由现场数据/设备责任人确认。

## 5. 读取七节点运行时属性

先保留上一步填写的七个 `nodes`，暂不填写 `witnessNodeVerification`。使用发布包中的只读 `.NET` Adapter 连接同一 TF6100 runtime；该命令只读取七个节点的 BrowseName、NodeClass、DataType 和访问级别，不执行 Write 或 Method Call：

```powershell
axiom-opcua-shadow beckhoff-witness-inspect `
  --config .\opcua-shadow.json `
  --runtime-evidence .\beckhoff-runtime-evidence.json `
  --deployment-request .\beckhoff-witness-deployment.json `
  --evidence-id site.beckhoff-witness-node-inspection@1 `
  --output .\beckhoff-witness-node-verification.json
```

将输出完整对象放入部署请求的 `witnessNodeVerification`。它必须来自 vendor runtime，逐项记录七节点实际 `BrowseName`、`NodeClass=Variable`、`DataType`、`AccessLevel=1` 和 `UserAccessLevel=1`，且 Write/Method Call 计数均为 0。输出绑定 `runtimeEvidence.contentHash`，不能移用于另一份 runtime receipt。此步骤会建立 OPC UA session，因此需要部署方的只读连接授权；它仍不会修改 PLC 或设备状态。

## 6. 离线预检

```powershell
axiom beckhoff-witness-deployment .\beckhoff-witness-deployment.json |
  Set-Content -Encoding utf8 .\beckhoff-witness-deployment-report.json
$LASTEXITCODE
```

- `0`：模板合同、Bound vendor runtime、M5 identity 和七 NodeId 的运行时属性验证已闭合；报告包含 Bound Witness Profile 与 R7-E request skeleton。
- `1`：请求有效，但某项为 `Open` 或 `Blocked`。
- `2`：JSON/schema/节点顺序无效。

`capturePreparationStatus=Passed` 只表示声明与导入的运行时属性证据闭合，不代表 TwinCAT 编译、激活或真实采集成功。报告中的 `captureAuthorizationStatus`、`deploymentShadowStatus`、`realityValidationStatus`、Controlled Trial 和 Closed Loop 仍为 `Open`，DeviceSafe/ProcessSafe 仍为 `NotAssessed`。

## 7. 进入真实采集

Bound Witness Profile 还必须与原始 `beckhoff-witness-node-verification.json`、Controller Profile、只读 authority、带 UTC 时间窗的数据所有者 capture authorization 一起交给 `.NET` `beckhoff-shadow-capture`；生产采集会重验节点证据内容哈希、runtime 哈希和七节点身份，旧的无验证哈希 Profile 会被拒绝。真实采集步骤和双运行 reality 验收见 [Windows 现场证据验收指南](FIELD-EVIDENCE-WINDOWS.md)。

当前仓库没有 TwinCAT/TF6100 目标机，因此只对 `.TcPOU` XML 外形、七只读 pragma、快照赋值顺序、打包身份和应用层合同做自动验证；TwinCAT 导入、编译、激活和真实运行必须在部署方环境留证。
