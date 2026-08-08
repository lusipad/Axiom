# CNC 工程合成场景数据集

> 数据集 ID：`axiom.cnc-synthetic-scenarios@1`
> 数据性质：确定性工程合成数据，不是机床、控制器、测头或数字孪生的实测输出。

本目录把常见 CNC 运动语义适配为 Axiom 当前可处理的 `ordered-point-sequence@1`。每个 `requests/*.json` 都是可以直接交给 `axiom evaluate` 的完整请求；`manifest.json` 保存场景来源语义与预期结果。

## 场景

| ID | CNC 语义 | 当前模型中的诚实解释 |
|---|---|---|
| `cnc-g1-linear-finishing@1` | G21/G54/G1 风格直线段 | 三维等距点与等周期时间参数；不推断控制器进给行为 |
| `cnc-g2-quarter-arc@1` | G17/G2 顺时针四分之一圆弧 | 固定 Z 平面的离散圆弧点 |
| `cnc-g3-closed-circle@1` | G17/G3 闭合圆轮廓 | 未重复首点、由 `closed=true` 补闭合段的点集 |
| `cnc-g3-helical-ramp@1` | G17/G3 带 Z 下降的两圈螺旋下刀 | 三维螺旋采样点与均匀时间参数 |
| `cnc-sampled-corner@1` | 拐角附近的平滑点列与采样抖动 | 合成位置采样和非等周期时间戳；不绑定 G64 或 look-ahead 实现 |
| `cnc-sampled-corner-missing-timestamps@1` | 只导出位置、缺少时间戳 | 几何仍合法，但时间间隔指标因上下文不足而无法计算 |
| `cnc-contour-observation-pass@1` | 名义直线轮廓与合成观测偏差 | 显式逐点参考比较，通过 0.03 mm 门槛 |
| `cnc-contour-observation-fail@1` | 局部超差的合成观测 | 显式逐点参考比较，硬门槛失败且评分不能抵消 |

## 构造依据与边界

- LinuxCNC 将 G1 定义为协调直线进给，将 G2/G3 定义为顺/逆时针圆弧或螺旋进给；G17 选择 XY 平面，增加 Z 字可形成螺旋运动：[G-code 官方文档](https://linuxcnc.org/docs/stable/html/gcode/g-code.html)。
- G20/G21 分别表示英寸/毫米；本数据集统一使用 G21 风格的 `mm`。
- 真实轨迹规划还受速度、加速度、机床极限和路径控制模式影响，短程序段未必达到编程进给：[轨迹规划说明](https://linuxcnc.org/docs/html/user/user-concepts.html)。因此本数据集不从相邻点推断真实插补器、伺服性能或设备安全性。

本数据集不表达刀具半径补偿、主轴、切削负载、碰撞、过切、控制器 look-ahead、轴限位或五轴姿态。`synthetic observation` 只用于验证评估契约，不是测量精度声明。

## 验证

批量验证请求语义、确定性和 CLI 协议：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_cnc_scenario_files.py -v
```

运行单个场景：

```powershell
.\.venv\Scripts\axiom.exe evaluate .\fixtures\cnc_scenarios\requests\cnc-g1-linear-finishing.json
```
