# Five-Axis Math F2 reference fixtures

本套件冻结 F2 的首个可证明子集：同一段严格 CL 输入分别进入双转台 AC、摆头转台 BC、双摆头 CB 三类 canonical `MachineProfile`，另有一个“端点安全、区间内部碰撞”的配置空间反例。

`programs/continuous-five-axis-line.cl` 使用真实 CL 风格的 `UNITS / FROM / FEDRAT / GOTO / END` 指令语义；机床、碰撞体和结果均为确定性工程参考模型，不是厂商控制器输出或真实设备观测，不能建立 `DeviceSafe`、`ProcessSafe` 或上机许可。

`manifest.json` 冻结可移植的 M0/M1/M2/M3 内容身份、MachineProfile、碰撞模型、标准 Claim 状态和证据等级。SVD 派生的奇异性证据按版本化的 12 位有效数字策略规范化；具体 Python/NumPy 版本不进入 M3 内容身份。`RunBundle.bundleHash` 仍绑定数值环境，只在 manifest 所列环境完全匹配时作为金值断言；其他环境继续执行完整性重验和同环境确定性重放。

Python 使用：

```python
from axiom import evaluate_run
from axiom.five_axis.f2_scenarios import validate_f2_example_run_spec

bundle = evaluate_run(validate_f2_example_run_spec("canonical-table-table"))
print(bundle.model_dump_json(indent=2, by_alias=True, exclude_none=True))
```

启动 `axiom serve` 后切换到 **Five-Axis F2**，可查看连续轴路径、分支/wrap、`Q_free` 碰撞证据和 sealed M3 输出；网页仍通过公共 `POST /api/v1/runs/evaluate` 执行同一 `RunSpec`。
