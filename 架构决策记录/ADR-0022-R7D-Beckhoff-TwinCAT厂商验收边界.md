# ADR-0022：R7-D 锁定 Beckhoff TwinCAT 厂商验收，但不伪造真实部署结论

- 状态：Accepted
- 日期：2026-08-13

## 背景

R7-C 已闭合 Windows OPC UA 的加密只读传输合同，但虚拟服务端没有厂商 namespace、软件包、许可证、BuildInfo、节点访问控制或固件行为，因此不能证明任何具体控制器兼容。当前产品需要选择首个可执行的厂商路径，才能把“支持 OPC UA”进一步收紧为可审计的部署事实。

首个目标选择 Beckhoff TwinCAT 3 Build 4026+ 与 TF6100 OPC UA Server。Beckhoff 为 Windows 环境提供版本化 XAR/XAE 软件包、`tcpkg` 查询面、标准 OPC UA BuildInfo、PLC 许可证检查结构和只读变量属性，适合构造不依赖设备写入的厂商验收链。但开发机目前没有 TwinCAT/TF6100 运行时、许可证或真实控制器，因此只能交付合同、检查器和开放预检，不能把本地结果写成厂商运行时通过。

## 决策

新增 Windows-only `control.domain-pack@4`，主 Artifact 类型为 `axiom.control.beckhoff-vendor-readiness`、schema version 为 `1`。`axiom.control.beckhoff-twincat-profile@1` 独立记录厂商、控制器族、最低 Build、TF6100 软件包/许可证、服务端身份、五轴节点、权限 canary 与内容身份。

Profile 与运行时是两个不同 gate：

- 默认 `Open` Profile 只冻结 Beckhoff / TwinCAT 3 / Build 4026+ / TF6100、X/Y/Z/B/C 单位和只读语义，不包含猜测的 endpoint 身份、namespace 或 node id；
- `Bound` Profile 必须由部署管理员提供精确 endpoint、ApplicationUri、服务端证书 SHA-256、标准 BuildInfo、五轴 `Double` 节点、`AccessLevel=1`、`UserAccessLevel=1`、TF6100 `FB_CheckLicense` 结果节点，以及专用非执行权限 canary；
- `vendorProfileStatus=Passed` 只表示 Profile schema 成立，不等于 `vendorRuntimeStatus=Passed`。

生产 `axiom-opcua-shadow` 继续只执行 Read/Subscribe。新增只读 `beckhoff-preflight` 和 `beckhoff-inspect`：前者查询 `tcpkg`、`TwinCAT.Standard.XAR`、`TF6100.OpcUaServer.XAR`、Build 与服务端二进制；后者在绑定 Profile 下读取标准 BuildInfo、五轴 DataType/AccessLevel/UserAccessLevel 和绑定的许可证结果节点，并重验 R7-C transport 内容身份。生产源码不得调用 OPC UA Write 或 Method Call。

控制器侧拒写只能由单独发布的 `Axiom.OpcUaShadow.BeckhoffPermissionVerifier` 验证。它必须由部署责任人显式传入 `--acknowledge-non-actuating-probe`，只允许 Profile 中已声明且经责任人确认不驱动执行机构的 canary；先读取并确认两个访问级别都等于 1，再对当前有限 `Double` 值执行恰好一次同值 Write。只有 `BadNotWritable` 或 `BadUserAccessDenied` 且前后值哈希相同时才形成正向拒写收据。该工具不得指向 X/Y/Z/B/C 控制信号，也不属于生产 Adapter。

完整厂商运行时 gate 需要安装、许可证、服务端身份、节点映射、独立拒写和 R7-C transport 六项同时通过。即使该 gate 通过，`deploymentShadowStatus` 与 `realityValidationStatus` 仍保持 `Open`，因为还缺少独立、case-scoped 的真实 capture；`DeviceSafetyStatus` 与 `ProcessSafetyStatus` 保持 `NotAssessed`。

## 后果

- Axiom 首次拥有具体厂商的版本化 Profile、Windows 预检、运行时检查器、独立权限验证器、typed DomainPack/API 和网页审计面。
- 没有 TwinCAT 的机器会稳定返回 `TwinCatPackageManagerMissing` / `vendorRuntimeStatus=Open`，而不是用通用或虚拟 OPC UA Server 伪造 Beckhoff 通过。
- 发布包同时包含生产只读 Adapter、隔离的权限验证器和默认开放 Profile；运行权限验证器仍需部署责任人的现场授权。
- R4/R5/R6 只有在后续取得独立真实 capture 并完成时钟、坐标、校准和 Case 绑定后才能消费现实证据；本 ADR 不授予 Controlled Trial、Closed Loop 或任何设备写回权限。

## 被拒方案

- 把 R7-C localhost conformance 直接标为 Beckhoff 兼容：虚拟服务端没有 TwinCAT 软件、许可证、namespace 或访问控制实现。
- 在默认 Profile 中预填常见 node id：TwinCAT PLC 符号与 namespace 由具体工程决定，猜测映射会制造不可审计的错误绑定。
- 仅凭 endpoint 字符串或厂商名称判断服务器：这些字段可配置，必须同时固定证书、ApplicationUri 和标准 BuildInfo。
- 让生产 Adapter 尝试一次 Write 来证明只读：这会扩大生产权限和攻击面，也无法把验证责任与日常采集分开。
- 对轴位置节点做拒写测试：即使写入同值也可能触发控制器逻辑；只能使用部署责任人确认的专用非执行 canary。
- 自动安装 TwinCAT/TF6100：安装、重启、许可与目标机变更属于部署方权限，不是评估器可隐式执行的操作。

### Questions for review

- 当前仍缺一台由部署方授权的 TwinCAT 3 Build 4026+ / TF6100 环境、绑定 Profile、只读主体和独立真实 capture；这些是关闭厂商运行时与现实门的外部前置条件。

### Verification

- Windows `.NET 8.0.424` locked restore 和解决方案无警告构建通过；生产源码静态证明没有 OPC UA session Write/Call，独立权限工具恰好包含一次 Write。
- 默认 Profile 由 Python 与 `.NET` 重验同一 content hash；本机 `beckhoff-preflight` 产生 hash-closed 证据，并如实返回 `TwinCatPackageManagerMissing` / Open。
- Python R7-D DomainPack、默认/完整/篡改/非 Windows/API 测试通过；网页组件、TypeScript、生产构建和桌面/窄屏视觉门通过。
- 未安装 TwinCAT/TF6100，未运行独立权限 canary，未采集真实控制器数据，也未测试设备停止、回滚、Controlled Trial、Closed Loop 或安全标准符合性。
