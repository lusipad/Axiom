# ADR-0021：R7-C 先闭合 Windows 虚拟 OPC UA 传输合同

- 状态：Accepted
- 日期：2026-08-13

## 背景

R7-B 已冻结厂商无关的只读部署证据门，但没有可执行的网络协议 Adapter。当前仍未选定具体控制器，也没有 Siemens、FANUC、HEIDENHAIN 或其他厂商设备、许可、凭据和可验收环境，因此不能诚实地实现或声称厂商兼容。

下一步仍需要把“只读采集”从 JSON 合同推进到真实网络栈，否则证书、安全通道、订阅、通知序号和零写边界都没有被执行验证。OPC UA 有 OPC Foundation 官方 .NET 实现，适合先建立厂商无关的 Windows 传输验收；但 localhost 虚拟服务端不能替代厂商服务器行为或真实设备证据。

## 决策

新增 Windows-only `control.domain-pack@3` 和隔离的 `.NET 8` `axiom.control.opcua-shadow-read-adapter@1`。Adapter 使用锁定版本 `OPCFoundation.NetStandard.Opc.Ua.Client@1.5.378.156`，只建立证书固定的 `SignAndEncrypt` 会话，以非匿名 username 主体订阅 X/Y/Z/B/C 五轴位置。

生产 Adapter 不包含 OPC UA Write 或 Method Call 路径。密码不进入配置或证据，只从配置所命名的 Windows 进程环境变量读取。服务端证书必须按 SHA-256 固定，客户端应用证书必须由服务端管理员独立加入信任列表；双方均不自动接受未知证书。

独立 conformance 程序在 localhost 启动 OPC UA Server，验证五轴订阅、Good quality、protocol sequence、source/server/host timestamp、丢包计数、零写/零方法调用，并由独立测试客户端证明写请求和未知客户端证书会被服务端拒绝。`.NET` 输出的 `axiom.control.opcua-transport-evidence@1` 必须能被 Python 模型和 RunBundle 原样重验。

R7-C 只能关闭 `virtualTransportStatus`。`vendorAdapterStatus`、`realityValidationStatus` 和 `deploymentShadowStatus` 保持 `Open`；设备与工艺安全保持 `NotAssessed`。虚拟网络证据永久 `declaredReal=false`、`countsTowardReality=false`。

## 后果

- Windows 发布物会同时包含 Python wheel/sdist 和独立的 framework-dependent `win-x64` OPC UA Adapter 压缩包。
- CI 和发布门增加 `.NET 8` locked restore、编译、网络 conformance 与跨语言 JSON/哈希验收。
- Web UI 可以导入传输证据并展示安全通道、订阅、零写和开放 gate，但不能连接机床或发出控制操作。
- 后续厂商工作包复用共同证据合同，但必须新增版本化厂商 mapping/verifier，并在真实控制器环境独立验收。

## 被拒方案

- 在 Python 进程内直接实现 OPC UA：会把网络栈、证书生命周期和控制协议攻击面混入评估器；独立 `.NET` 进程边界更清楚，也能使用官方栈。
- 让 Adapter 自动信任首次见到的证书：无法防止 endpoint 被替换，与固定部署证据合同冲突。
- 使用匿名或明文连接：不能证明最小权限主体和传输机密性。
- 在生产 Adapter 中保留“以后可能用到”的 Write/Call API：违反零权限扩张原则，并使静态审计无法证明只读表面。
- 把 localhost 虚拟通过写成厂商兼容或真实 deployment shadow：虚拟服务端没有厂商 namespace、权限实现、负载、时钟和固件行为。
- 同时实现多个厂商 profile：当前没有设备、许可和独立验收环境，无法形成可信正例。

### Questions for review

- 首个厂商 Adapter 仍需部署方选择具体控制器族、版本、协议 profile、许可与只读凭据；R7-C 不替代该选择。

### Verification

- Windows `.NET 8` locked restore、无警告构建和 localhost 网络 conformance 通过；独立写请求与未知客户端应用证书均被拒绝。
- `.NET` 证据由 Python `OpcUaTransportEvidence` 完成 canonical hash 跨语言重验，并保持 vendor/reality Open。
- Python R7-C 模型、Run/API、篡改与非 Windows Unsupported 定向测试通过；前端组件、TypeScript、生产构建和实页视觉门通过。
- 未测试任何真实控制器、厂商 namespace/node mapping、真实时钟/丢包、授权许可、设备侧写/停机链或标准符合性。
