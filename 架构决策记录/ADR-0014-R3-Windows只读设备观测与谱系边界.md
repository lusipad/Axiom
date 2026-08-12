# ADR-0014：R3 使用 Windows 文件回放冻结只读设备观测与谱系边界

- 状态：Accepted
- 日期：2026-08-12
- 决策范围：R3 首个设备源、领域边界、MachineRun 谱系和安全声明

## 背景

R2 已闭合 M0–M5 数学参考栈和七项数学 Claim。R3 必须开始接收设备或仿真运行观测，但当前没有可在仓库中稳定访问、许可和版本均已确认的真实厂商控制器。直接从 live polling、厂商 SDK 或通用设备抽象开始，会在原始数据、对齐和谱系合同尚未闭合前引入网络、凭据、线程、协议写能力和设备安全风险。

现有 Core 已支持独立 DomainPack、单主 Artifact、运行时绑定和原始 Observation 保存。F4 的 Adapter 只用于进程内数学求解，不能冒充设备 transport，也不能把数学 Claim 升级为设备安全声明。

## 决策

1. R3 首个具体源是 `axiom.windows-file-telemetry-source@1`，只读取已经落盘的 JSON capture。当前实现、测试、CI 和发布只以 Windows AMD64 + CPython 3.12.10 为阻断基线；不增加 Ubuntu/Linux 分支。
2. 首版不开放网络、不轮询控制器、不调用厂商 SDK、不写参数、不传程序、不启动或操纵设备。
3. 设备观测使用独立 `machine-observation.domain-pack@1`、`machine.telemetry-trace` Artifact、`machine-observation-evaluator@1` 和 `machine-trace-import@1`。DomainPack 通过通用 `importRunnerIds` 声明该 Runner 产生 `ImportedArtifact` Observation，不向 Core 或 Five-Axis F4 塞入设备 special-case。
4. 原始 trace 是一次 Run 的唯一主 Artifact。`DeviceProfile`、`ClockMapping`、`CoordinateAlignment` 和 `MachineRunLineage` 是有类型支持对象；派生对齐和指标不得覆盖原始 frame。
5. MachineRun 必须显式为 `paired` 或 `unpaired`。paired 同时绑定 baseline `RunBundle`、来源 M5 内容身份和七项已支持的 F4 数学 Claim；unpaired 禁止伪造这些字段，但仍允许保存历史观测。
6. R3 只发布 raw integrity、read-only capture、lineage completeness、clock alignment 和 coordinate context 五类数据可信性 Claim，Evidence 上限为 `Observed`。
7. R3 永不发布 `DeviceSafe`、`ProcessSafe`、`safe-to-run` 或上机许可。缺时钟、坐标或标定上下文时必须显式 `InsufficientContext` / `Inconclusive`；gap 不得自动插值。
8. 首版 Machine Lab 只导入、回放和展示数据，永久显示 `READ ONLY / NOT DEVICE SAFE`，不提供任何设备操作控件。

## 后果

- R3 可以先用确定性合成/仿真 capture 验证 raw/derived、对齐、谱系和零写入不变量，并通过通用 RunBundle 进入后续 R4/R5。
- 文件回放不能证明某个真实控制器协议已经兼容，也不能证明在线时钟漂移、采集丢包或实际设备权限隔离。
- 将来增加 live read source 时可以复用 Artifact 和评估合同；新增 source/runner 必须另行冻结协议版本、许可、身份、错误、超时和最小权限。
- 将来支持 Ubuntu/Linux 时必须增加独立环境金值、CI 和安装后 smoke，不能从 Windows 结果外推。

## 被拒方案

- **直接连接真实控制器**：当前没有可验证的设备、凭据、许可和稳定 fixture；会让协议细节绑架领域合同。
- **先造通用 Device/Transport 平台**：首个源尚未闭合，属于过早抽象。
- **复用 F4 in-process Adapter 作为设备 Runner**：它的输入输出和信任边界是数学求解，不是不可重放的设备观测。
- **把设备字段附加到五轴 F4 Artifact**：设备观测也可能来自历史运行或非五轴来源，会破坏领域边界。
- **首版同时支持 Windows 与 Ubuntu**：扩大发布矩阵但不能增加 R3 合同证据，且违反当前 Windows-only 阻断基线。
- **宣称 MTConnect/OPC UA 兼容**：本阶段未冻结协议版本、许可、权限和实际 Agent/Server，不应冒充实现。
