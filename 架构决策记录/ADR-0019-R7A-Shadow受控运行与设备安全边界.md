# ADR-0019：R7-A 先闭合 Synthetic Shadow 合同，不启用真实设备写入

- 状态：Accepted
- 日期：2026-08-12

## 背景

蓝图要求 R7 具备权限、限幅、停止、回滚、审计和在线监控，但当前仓库的 R5 真实 holdout、R6 reality validation、真实 deployment shadow、认证身份、厂商写协议和设备安全停止链均未闭合。仅实现一个软件状态机，不能证明真实机床、加工过程或安全相关控制系统满足部署要求。

## 决策

R7 的首个实现包限定为 Windows-only `synthetic-shadow`。新增独立 `control.domain-pack@1` 和 `ControlledRuntimeAudit` 主 Artifact；R6 Recommendation 作为不可变上下文，R7 另建 `AcceptanceRecord`，二者内容身份和责任保持分离。

权限上限固定为 `Shadow`，全部设备写字段为 false。入场策略 fail closed；运行越界必须产生停止与基线保留 receipt，但 receipt 明确记录没有设备 stop command、ack、write 或 readback。Synthetic contract 与 deployment shadow、Controlled Trial、Closed Loop 和标准符合性分别报告，后四项保持 Open/NotAssessed。

## 后果

- 可以在没有设备写权限的情况下验证状态迁移、包线、篡改拒绝和完整审计链。
- Controlled Runtime UI 可以展示真实的权限升级缺口，而不会提供危险的伪控制入口。
- 后续厂商 Adapter 必须新增版本化合同，不能复用 synthetic receipt 冒充设备侧确认。
- 完整 R7 仍依赖具体设备、权限系统、安全功能、责任方和法规证据；R7-A 通过不等于可上机。

## 被拒方案

- 直接把 R6 Pareto 候选写入设备：真实泛化、shadow 和安全停止链均未闭合。
- 把软件 `StopRequested` 称为急停：没有硬件命令、确认或安全相关控制系统证据。
- 把“基线从未修改”称为设备回滚：没有参数回写与设备读回。
- 在 Core 增加控制专用状态：DomainPack 与 typed context 已能表达，不应泄漏领域概念。
- 宣称符合 ISO/IEC 标准：当前只参考标准范围冻结边界，没有完成符合性评估。
