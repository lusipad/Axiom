# Axiom OPC UA Shadow Adapter

Windows-only、只读的 OPC UA 传输验收程序。它使用 OPC Foundation 官方 .NET
协议栈建立 `SignAndEncrypt` 会话，并且只创建订阅，不暴露 Write、Call 或设备控制命令。
仓库根目录的 `global.json` 将构建工具链精确冻结为 .NET SDK 8.0.424。
发布的 `win-x64` 单文件是 framework-dependent 制品，运行端需要 .NET 8.0.30
或兼容的更高 8.0 patch runtime。

生产程序可以产生 `axiom.control.opcua-transport-evidence@1`，也可以针对绑定的
Beckhoff TwinCAT 3 / TF6100 Profile 产生
`axiom.control.beckhoff-runtime-evidence@1`。两种证据都不能单独证明现实对齐、
`DeviceSafe`、`ProcessSafe` 或上机许可。

## 构建与验收

```powershell
dotnet restore adapters/opcua-shadow/Axiom.OpcUaShadow.sln --locked-mode
dotnet build adapters/opcua-shadow/Axiom.OpcUaShadow.sln -c Release --no-restore
dotnet run --project adapters/opcua-shadow/tests/Axiom.OpcUaShadow.Conformance -c Release --no-build
```

验收程序在 Windows localhost 上启动独立虚拟 OPC UA Server，显式互信应用证书，
使用非匿名用户名身份订阅 X/Y/Z/B/C 五轴数据，并验证未知证书和写请求均被拒绝。

## 使用

先初始化客户端应用证书，再由控制器管理员把公钥证书加入 OPC UA Server 信任列表：

```powershell
axiom-opcua-shadow init --config opcua-shadow.json
axiom-opcua-shadow capture --config opcua-shadow.json --output capture.json
```

密码不写入配置文件。`passwordEnvironmentVariable` 只声明读取哪个 Windows 进程环境变量。
输出文件使用 CreateNew 语义，已存在时拒绝覆盖。

跨语言验收可把 localhost 虚拟服务端已通过的证据导出给 Python 评估器：

```powershell
dotnet run --project adapters/opcua-shadow/tests/Axiom.OpcUaShadow.Conformance `
  -c Release -- --evidence-output transport-evidence.json
```

## Beckhoff TwinCAT 3 / TF6100

仓库的 [`beckhoff-twincat-profile.windows.json`](../../examples/beckhoff-twincat-profile.windows.json)
是开放 Profile：它冻结 Windows、TwinCAT 3 Build 4026+、TF6100、五轴单位和只读语义，
但故意不猜测具体工程的 endpoint 身份、namespace 或 node id。

只读预检查询 `tcpkg`、`TwinCAT.Standard.XAR`、`TF6100.OpcUaServer.XAR`、Build 和服务端
二进制；它不会安装软件或连接设备：

```powershell
axiom-opcua-shadow beckhoff-preflight `
  --profile beckhoff-twincat-profile.windows.json `
  --output beckhoff-preflight.json
```

没有 TwinCAT/TF6100 时，预检会输出结构化 Open 证据。真实检查需要部署管理员提供
`Bound` Profile：精确固定 endpoint、ApplicationUri、证书、BuildInfo、TF6100
`FB_CheckLicense` 结果节点、X/Y/Z/B/C 节点和专用非执行只读 canary：

```powershell
axiom-opcua-shadow beckhoff-inspect `
  --profile beckhoff-bound-profile.json `
  --config opcua-shadow.json `
  --transport transport-evidence.json `
  --write-receipt write-rejection-receipt.json `
  --output beckhoff-runtime-evidence.json
```

生产程序仍没有 OPC UA session Write/Call。拒写收据由发布包中隔离的
`permission-verifier\Axiom.OpcUaShadow.BeckhoffPermissionVerifier.exe` 生成。该工具只允许
Profile 中由部署责任人确认不驱动执行机构的专用 canary，先确认
`AccessLevel=1` / `UserAccessLevel=1`，再执行恰好一次同值 Write：

```powershell
.\permission-verifier\Axiom.OpcUaShadow.BeckhoffPermissionVerifier.exe `
  --profile beckhoff-bound-profile.json `
  --config opcua-shadow.json `
  --output write-rejection-receipt.json `
  --acknowledge-non-actuating-probe
```

不要对轴位置、控制信号或未经设备责任人授权的节点运行该命令。只有
`BadNotWritable` / `BadUserAccessDenied` 且前后值哈希相同才算拒写通过；这仍不关闭
deployment reality 或设备安全 gate。

## Beckhoff Shadow Witness（R7-E）

R7-E 不把 OPC UA publishing interval 当作 M5 覆盖证明。Bound Witness Profile 必须
额外映射只读 command content hash、`UInt32` sample index 和 X/Y/Z/B/C；Adapter 只订阅
sample index，每个新索引触发一次七节点 batch Read。索引必须从 0 开始并与 M5 完全一致，
缺失索引不会被插值。

发布包同时提供 `deployment/FB_AxiomShadowWitness.TcPOU`。该功能块在关闭观测窗口时保持
sentinel，重新开窗后先锁存 command hash 与五轴回读，最后发布 sample index；窗口内命令
身份变化时也保持 sentinel，避免零索引复用。它不生成索引、不写轴、不启停设备。TwinCAT
导入、实例化、TMC 符号生成、TF6100 ACL、显式 NodeId 绑定及七节点运行时属性验证步骤见
[`BECKHOFF-WITNESS-DEPLOYMENT-WINDOWS.md`](../../BECKHOFF-WITNESS-DEPLOYMENT-WINDOWS.md)。

七节点属性证据由同一只读 Adapter 生成：

```powershell
axiom-opcua-shadow beckhoff-witness-inspect `
  --config opcua-shadow.json `
  --runtime-evidence beckhoff-runtime-evidence.json `
  --deployment-request beckhoff-witness-deployment.json `
  --evidence-id site.beckhoff-witness-node-inspection@1 `
  --output beckhoff-witness-node-verification.json
```

真实采集还需绑定 Vendor Profile、R7-D runtime evidence、Controller Profile、已验证的
只读 authority 和数据所有者 capture authorization。authorization 必须包含带 UTC offset 的
`authorizedFrom` / `authorizedUntil`，且 capture receipt 的打开、关闭与 `capturedAt` 均须落在
该时间窗内：

```powershell
axiom-opcua-shadow beckhoff-shadow-capture `
  --config opcua-shadow.json `
  --vendor-profile beckhoff-bound-profile.json `
  --runtime-evidence beckhoff-runtime-evidence.json `
  --witness-node-evidence beckhoff-witness-node-verification.json `
  --witness-profile beckhoff-shadow-witness-profile.json `
  --controller-profile controller-profile.json `
  --authority readonly-authority.json `
  --capture-authorization capture-authorization.json `
  --command m5-command.json `
  --evidence-id beckhoff.shadow.calibration@1 `
  --output beckhoff-shadow-calibration.json
```

采集命令会重验节点证据与 runtime hash、Bound Witness Profile 和七个实际节点身份；缺少该证据的旧 Profile 不能进入生产采集。输出使用 CreateNew 语义且生产路径仍为零 Write/Call。仓库 conformance 的 witness 输出
固定 `sourceKind=contract-fixture`、`declaredReal=false`，只用于跨语言合同验收；它不能计入
deployment Shadow 或 R4.1 reality gate。真实 R4.1 验证必须另采 calibration 与 validation
两次运行，并使用不同 capture authorization 和时间窗。
