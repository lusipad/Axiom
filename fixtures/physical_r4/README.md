# R4 物理模型与现实对齐验收数据

该目录冻结 Windows-only R4.0 synthetic SIL 的可移植内容身份和六类场景预期结果。`captures/in-domain-synthetic-sil.response.json` 是由 F4 canonical head-table M5 指令驱动、经校准后独立一阶轴模型生成的主 `PhysicalResponseTrace`。

这些文件只证明物理模型合同、校准/验证隔离、无插值对齐、单位分离残差和确定性重放。它们不是实机数据，不关闭 reality gate，也不产生 `DeviceSafe`、`ProcessSafe`、`safe-to-run` 或上机许可。

`RunBundle.bundleHash` 仍绑定冻结的 Windows 数值环境；本目录仅冻结可跨同契约实现复算的 Artifact、Calibration 与 Analysis 内容身份。
