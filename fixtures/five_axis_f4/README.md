# Five-Axis F4 solver adapter 参考夹具

本目录保存 Axiom Math F4 的确定性工程参考输入、可移植内容身份与阶段验收摘要。CL 文本具有真实 CNC cutter-location 输入的代表性，但机床、碰撞几何、adapter 调用与结果都是数学参考模型，不是真实设备观测，也不构成上机安全证据。

`manifest.json` 冻结三类 canonical 五轴拓扑的 solver 正向验收、两个反例、F4 阶段验收报告的 portable 内容身份，以及 Windows AMD64、CPython 3.12.10、numpy 2.5.2、scipy 1.18.0、pint 0.25.3、pydantic 2.13.4、`OPENBLAS_CORETYPE=Haswell`、BLAS/OMP 单线程环境下的精确 `RunBundle` 金值。portable 身份只覆盖 candidate geometry、M3/M4、collision model、adapter invocation 和 M5 command；adapter receipt 携带数值环境，属于环境绑定证据，不纳入 portable fixture 哈希。

阶段验收要求三种正向拓扑全部闭环，并覆盖 `adapter-input-hash-mismatch` 与 `interval-interior-collision` 两个反例。后者必须证明区间端点安全但 `[0.25, 0.5]` 内部存在碰撞 witness `0.375`；不能因为离散端点通过就宣称整个重建区间安全。

本目录是源码仓库的发布验收资料，不是已安装 wheel 的稳定文件路径。发布包通过 F4 示例 API 返回同类完整 envelope，调用方不应依赖 `fixtures/five_axis_f4` 的本地相对路径。
