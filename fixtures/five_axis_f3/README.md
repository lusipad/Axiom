# Five-Axis F3 时间与离散参考数据

本目录保存 Axiom Math F3 的确定性工程参考输入与可移植身份。CL 文本具有真实 CNC cutter-location 输入的代表性，但机床、动态上限、时间律和结果都是数学参考模型，不是真实设备观测，也不构成上机安全证据。

`manifest.json` 由发布测试冻结可跨受支持数值环境重放的 M3/M4/M5 内容身份、重建策略和标准 Claim，并按操作系统、机器架构和完整数值环境分别冻结 `RunBundle` 身份。M3 的 SVD 派生证据保留版本化的 12 位有效数字策略，raw gate 之后的小于 `1e-14` 的 IK 残差证据提升为保守上界；portable Artifact 哈希使用 8 位有效数字和统一 signed zero 的 JSON 浮点表示。证据与身份归一化都不改变连续约束、重建或 Claim 门槛使用的原始 binary64 值。任何样本点结论都必须由声明的 reconstruction policy 解释；不得仅凭离散点通过就宣称采样区间安全。

本目录是源码仓库的发布验收资料，不是已安装 wheel 的稳定文件路径。发布包通过 F3 示例 API 返回同一类完整 envelope，调用方不应依赖 `fixtures/five_axis_f3` 的本地相对路径。

七个场景包括三类 canonical 五轴拓扑的 Jerk 可行基准、解析二阶已证最优子集、显式 dwell/mandatory-stop、移动 ZOH 不支持，以及端点速度均为零但多项式区间内部违反命令速度上限的反例。后两类分别冻结 `Inconclusive` 与 `Refuted`，不能都折叠成普通失败。
