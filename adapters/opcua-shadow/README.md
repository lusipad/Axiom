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
