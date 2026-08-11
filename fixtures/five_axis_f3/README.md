# Five-Axis F3 时间与离散参考数据

本目录保存 Axiom Math F3 的确定性工程参考输入与可移植身份。CL 文本具有真实 CNC cutter-location 输入的代表性，但机床、动态上限、时间律和结果都是数学参考模型，不是真实设备观测，也不构成上机安全证据。

`manifest.json` 由发布测试冻结 M3/M4/M5 内容身份、重建策略、标准 Claim 和当前数值环境下的完整 RunBundle 身份。任何样本点结论都必须由声明的 reconstruction policy 解释；不得仅凭离散点通过就宣称采样区间安全。

七个场景包括三类 canonical 五轴拓扑的 Jerk 可行基准、解析二阶已证最优子集、显式 dwell/mandatory-stop、移动 ZOH 不支持，以及端点速度均为零但多项式区间内部违反命令速度上限的反例。后两类分别冻结 `Inconclusive` 与 `Refuted`，不能都折叠成普通失败。
