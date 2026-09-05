# CNC 算法 A/B 对比

首个工作流比较外部算法导出的 XYZ 采样指令。它不调用内置 F4 求解器，不要求 A/B 具有相同的采样数量或运动时长，也不执行用户提供的程序。

## 开始使用

Windows 中按 README 安装后运行：

```powershell
axiom serve
```

打开 `http://127.0.0.1:8000`。默认进入“算法 A/B 对比”，上传案例、基线和候选三个 JSON。点击“载入回归示例”可以检查流程：候选在第 5 个样本、0.05 秒偏离参考直线 0.08 mm，超过案例中的 0.03 mm 限制。该示例始终标记为 `synthetic-example`。

CLI 使用相同分析函数：

```powershell
axiom benchmark --case examples/cnc-benchmark/case.json --baseline examples/cnc-benchmark/baseline.json --candidate examples/cnc-benchmark/candidate.json
```

也可保存并重放完整请求：

```powershell
axiom benchmark-example | Out-File -Encoding utf8 request.json
axiom benchmark request.json | Out-File -Encoding utf8 report.json
$LASTEXITCODE
```

退出码：`0` = 本次采样比较改善或在比较容差内；`1` = 超限、退步、存在取舍或证据不足；`2` = 输入无法解析或不兼容。退出码 0 不是设备安全或完整算法正确性证明。

## 接入 C++、C# 或其他算法

1. 为真实刀路创建 `case.json`，冻结坐标系、单位、固定周期、轴限制、几何限制和比较容差。
2. 运行 `axiom benchmark-case-hash case.json`，取得规范化案例的 SHA-256。
3. 让算法 A、B 分别消费同一案例。各自导出以下 JSON，记录真实版本或构建标识，并把第 2 步的值放入 `caseContentHash`。
4. 将三份文件交给 CLI 或网页。比较器重验内容绑定、坐标系、单位和时钟，再独立计算指标。

导出示意（仅列两个样本说明格式；完整 V/A/J 差分检查至少需要四个样本）：

```json
{
  "schemaId": "axiom.cnc-algorithm-export@1",
  "algorithmId": "your-cnc.feed-planner",
  "algorithmVersion": "commit-sha-build-configuration",
  "sourceKind": "algorithm-export",
  "caseContentHash": "replace-with-benchmark-case-hash-output",
  "coordinateFrame": "workpiece",
  "unit": "mm",
  "samplePeriodSeconds": 0.001,
  "samples": [
    {"sampleIndex": 0, "t": 0.0, "positionMm": [0.0, 0.0, 0.0]},
    {"sampleIndex": 1, "t": 0.001, "positionMm": [0.01, 0.0, 0.0]}
  ],
  "computation": {
    "elapsedSeconds": 0.0023,
    "environmentId": "pc-17-release-one-thread",
    "method": "warmed-monotonic-clock-around-planning-call"
  }
}
```

`computation` 可省略。它是导出器报告的实际测量值，不能由样本数或 deterministic work units 填充。只有 A/B 的 `environmentId` 和 `method` 相同时才比较；一次测量不建立统计显著性。算法版本、构建选项和测量方法应足以定位对应二进制。

内容 hash 绑定的是经过 schema 规范化的案例值，不是 JSON 文件的空格或键顺序，也不采用低有效位舍入。算法导出声明自己消费了该案例；这个声明及 `sourceKind` 不是独立采集或真实性证明。不要把内置示例改个标签就当成生产证据。

## 案例内容

完整可执行输入见 [case.json](examples/cnc-benchmark/case.json)。案例包含：

| 字段 | 含义 |
|---|---|
| `referencePath` | 工件坐标系中的 XYZ 参考折线，单位 mm |
| `samplePeriodSeconds` | 两个算法共同遵守的固定输出周期 |
| `axisLimits` | 按 X、Y、Z 顺序声明行程、速度、加速度、Jerk 限制 |
| `maximumPathDeviationMm` | 采样位置到参考折线的最大允许距离 |
| `maximumEndpointErrorMm` | 指令首尾点到参考路径首尾点的允许距离 |
| `comparisonTolerances` | A/B 的运动时间、采样路径偏差、声明计算耗时的实际差异容差 |

首版只接受 3 个线性轴，不接受旋转轴、混合单位或未声明的坐标变换。周期范围为 1 微秒到 1 秒；它是案例条件，不是本工作流的优化变量。

样本索引必须从 0 连续增加；时间必须从 0 按固定周期增加。时间表示容差为 `max(1e-12 s, period × 1e-6)`。不自动排序、补点、插值或补末尾不足一周期的样本。对实际控制器日志，应先通过单独记录的变换得到符合合同的指令轨迹；不要直接把反馈轨迹伪装成算法命令。

## 指标的准确含义

| 指标或检查 | 算法 | 边界 |
|---|---|---|
| 运动时间 | 最后一个命令时间戳 | 与计算耗时分开 |
| 采样路径偏差 | 每个输出点到所有参考线段的最小欧氏距离，再取最大值 | 单向、采样点指标；未证明遍历顺序、路径覆盖或采样间无捷径 |
| 首尾误差 | 命令首尾与参考首尾分别比较 | 不推断输入之外的启停状态 |
| 行程 | 每轴采样位置检查 | 未证明采样之间的行程 |
| 离散速度 | `Δq / T` | 不等于未知插补/重建律的连续速度 |
| 离散加速度 | `Δ²q / T²` | 至少三个样本 |
| 离散 Jerk | `Δ³q / T³` | 至少四个样本；不对缺失项填零 |
| 计算耗时 | 导出器明确提供的计时 | 同环境、同方法才可比较；没有重复试验统计结论 |

点到折线距离使用分块的投影公式，零长度参考段按点处理；结果是 binary64 数值计算，不标记 `Certified`。参考路径最多 10,000 点，每个导出最多 100,000 样本；A/B 总样本数乘参考段数不超过 20,000,000，超过时拒绝并要求拆分案例。网页预览会抽点，服务器检查所有输入样本。

每个超限项保留值、单位、限制、样本索引、时间和相关轴。差分的定位点为参与差分的最后一个样本；采样路径偏差另外标记最近参考段。

## 结果如何解释

- `CandidateViolatesLimits`：候选触犯至少一项本次采样限制。
- `Inconclusive`：基线不满足检查、样本不足，或混用了合成示例与算法导出。
- `Regressed`：至少一个可比较目标退步，且没有改善目标。
- `Tradeoff`：既有改善也有退步，需要工程判断。
- `Improved`：至少一个可比较目标改善，没有目标退步，且 A/B 的采样限制均满足。
- `WithinTolerance`：可比较目标均在预先指定的差异容差内。

未提供或环境不同的计算耗时为 `NotComparable`，不参与总体优劣；其他可比较指标仍可产生有限范围的结果。离散 V/A/J 用作限制检查，不把“更低速度”单独解释成算法更好。

任何结果都带 `scope=sampled-xyz-command` 和未检查性质列表。它不发布连续轨迹证书、碰撞结论、物理模型有效性、实机跟随误差或加工质量结论。后续添加连续检查时，必须先明确被测控制器的重建律及初末状态。

## API 与 Python

- `GET /api/v1/benchmarks/cnc/example`：显式合成的完整请求。
- `POST /api/v1/benchmarks/cnc/case-hash`：案例 hash。
- `POST /api/v1/benchmarks/cnc/compare`：`{case, baseline, candidate}` → 比较报告。
- `/api/docs`：完整输入和输出 schema。

```python
import json
from pathlib import Path
from axiom import compare_cnc_exports

payload = {role: json.loads(Path(f"{role}.json").read_text(encoding="utf-8-sig"))
           for role in ("case", "baseline", "candidate")}
report = compare_cnc_exports(payload)
print(report.outcome)
```

请求文件和报告可分别下载。报告保存两个导出的内容 hash、案例 hash 和报告自身 hash；重放需要保留输入文件。修改或导入失败时网页立即清除旧报告，避免把先前结果应用到新文件。

## 下一步的验收门

下一步接入团队真实算法的两个版本与来源明确的生产刀路，完成一次已知回归定位和另一位工程师的独立重放。之后按实际缺口增加连续重建检查、算法计时的重复统计、Orion 响应与设备观测；不以增加 DomainPack 数量作为进展。
