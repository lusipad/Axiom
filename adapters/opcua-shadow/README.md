# Axiom OPC UA Shadow Adapter

Windows-only、只读的 OPC UA 传输验收程序。它使用 OPC Foundation 官方 .NET
协议栈建立 `SignAndEncrypt` 会话，并且只创建订阅，不暴露 Write、Call 或设备控制命令。
仓库根目录的 `global.json` 将构建工具链精确冻结为 .NET SDK 8.0.424。
发布的 `win-x64` 单文件是 framework-dependent 制品，运行端需要 .NET 8.0.30
或兼容的更高 8.0 patch runtime。

本程序产生 `axiom.control.opcua-transport-evidence@1` 证据。证据只能证明一次
OPC UA 网络采集的传输合同，不能证明真实厂商兼容、现实对齐、`DeviceSafe`、
`ProcessSafe` 或上机许可。

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
